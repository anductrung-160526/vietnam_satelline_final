"""No real secrets/network: verify legacy split auth and direct-transfer recovery."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from province_pipeline.auth import RcloneCredentials, drive_credentials, ee_credentials
from province_pipeline.controller import reconcile, work
from province_pipeline.common import digest, load_config
from test_province_pipeline import FakeDrive, candidate


class RcloneAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'rclone.conf';self.path.write_text('[gdrive]\ntype = drive\n')

    def responses(self):
        expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        dump={'gdrive':{'type':'drive','token':json.dumps({'access_token':'TEST_TOKEN_NOT_REAL','expiry':expiry})}}
        return [SimpleNamespace(returncode=0,stdout='{}'),SimpleNamespace(returncode=0,stdout=json.dumps(dump))]

    def test_builtin_client_no_client_secret_or_new_json_required(self):
        with patch('province_pipeline.auth.subprocess.run',side_effect=self.responses()) as run:
            c=RcloneCredentials(self.path)
        self.assertEqual(c.token,'TEST_TOKEN_NOT_REAL')
        self.assertIsNotNone(c.expiry)
        self.assertIn('about',run.call_args_list[0].args[0])
        self.assertEqual(run.call_args_list[1].args[0][-2:],['config','dump'])
        self.assertTrue(run.call_args.kwargs['capture_output'])
        self.assertFalse(c.expired)

    def test_rclone_failure_does_not_expose_output(self):
        result=SimpleNamespace(returncode=1,stdout='DO_NOT_PRINT',stderr='DO_NOT_PRINT')
        with patch('province_pipeline.auth.subprocess.run',return_value=result):
            with self.assertRaises(RuntimeError) as context: RcloneCredentials(self.path)
        self.assertNotIn('DO_NOT_PRINT',str(context.exception))

    def test_missing_local_config_fails_before_launch(self):
        with patch('province_pipeline.auth.subprocess.run') as run:
            with self.assertRaises(ValueError): RcloneCredentials(self.path.parent/'absent')
        run.assert_not_called()

    def test_unsafe_remote_rejected(self):
        with self.assertRaises(ValueError): RcloneCredentials(self.path,'bad:name')

    def test_receiver_needs_no_service_account(self):
        with patch.dict(os.environ,{'PROVINCE_RCLONE_CONFIG':str(self.path)},clear=True),patch(
                'province_pipeline.auth.subprocess.run',side_effect=self.responses()):
            self.assertIsInstance(drive_credentials(),RcloneCredentials)
            with self.assertRaisesRegex(ValueError,'EE_CREDENTIALS'): ee_credentials()

    def test_ee_credentials_independent_of_drive(self):
        with patch.dict(os.environ,{'PROVINCE_EE_CREDENTIALS':'test-key.json'},clear=True),patch(
                'google.oauth2.service_account.Credentials.from_service_account_file',return_value='ee-only') as load:
            self.assertEqual(ee_credentials(),'ee-only')
        self.assertEqual(load.call_args.args[0],'test-key.json')
        self.assertNotIn('https://www.googleapis.com/auth/drive',load.call_args.kwargs['scopes'])

    def test_windows_bom_configuration_is_supported(self):
        path=self.path.parent/'config.json'
        c=json.loads(Path('province_pipeline/config/example.json').read_text())
        path.write_text(json.dumps(c),encoding='utf-8-sig')
        self.assertEqual(load_config(path)['export_backend'],'direct')

    def test_oversized_direct_download_rejected(self):
        path=self.path.parent/'config.json'
        c=json.loads(Path('province_pipeline/config/example.json').read_text());c['tile_pixels']=2048
        path.write_text(json.dumps(c))
        with self.assertRaisesRegex(ValueError,'32 MB'): load_config(path)


class DirectRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.drive=FakeDrive();self.folders=dict(reports='reports',manifests='manifests',receipts='receipts')
        self.job=dict(candidate('j'),export_backend='direct',attempt=1,folder_id='folder',
                      kind='table',prefix='01_ha_noi_test',local_directory='pkg',
                      province=dict(ma_tinh='01',group_id=0),folder_name='01_ha_noi_j')
        self.state={'jobs':{'j':self.job}}

    def test_failed_before_upload_can_retry_with_new_attempt_report(self):
        self.drive.documents['reports','j-a1.json']={'status':'TRANSFERRING'}
        reconcile(self.drive,self.folders,self.state,[])
        self.assertEqual(self.job['status'],'RESERVED');self.assertEqual(self.job['attempt'],2)

    def test_failed_after_unconfirmed_upload_never_overwrites(self):
        self.drive.documents['reports','j-a1.json']={'status':'FAILED'}
        self.drive.files['f']=dict(id='f',parents=['folder'])
        reconcile(self.drive,self.folders,self.state,[])
        self.assertEqual(self.job['status'],'BLOCKED_OUTPUT')

    def test_retry_budget_is_bounded(self):
        self.job['attempt']=4
        self.drive.documents['reports','j-a4.json']={'status':'FAILED'}
        reconcile(self.drive,self.folders,self.state,[])
        self.assertEqual(self.job['status'],'FAILED')

    def test_uploaded_report_and_checksum_produce_manifest(self):
        self.drive.files['f']=dict(id='f',name='01_ha_noi_test.csv',parents=['folder'],
             size='10',mimeType='text/csv',md5Checksum='test-checksum',version='1')
        self.drive.documents['reports','j-a1.json']=dict(status='UPLOADED',file_id='f',md5Checksum='test-checksum')
        reconcile(self.drive,self.folders,self.state,[])
        self.assertEqual(self.job['status'],'REMOTE_READY')
        self.assertEqual(self.drive.documents['manifests','j.json']['files'][0]['id'],'f')

    def test_upload_report_waits_for_visibility_without_reupload(self):
        self.drive.documents['reports','j-a1.json']=dict(status='UPLOADED',file_id='f',md5Checksum='test-checksum')
        reconcile(self.drive,self.folders,self.state,[])
        self.assertEqual(self.job['status'],'RUNNING');self.assertEqual(self.job['attempt'],1)

    def test_worker_uses_direct_transfer_not_service_account_drive_export(self):
        self.drive.files['folder']=dict(id='folder',name=self.job['folder_name'],mimeType='application/vnd.google-apps.folder')
        c=dict(pause=False)
        plan=dict(config_hash=digest(c),folders=self.folders,jobs=[self.job])
        with patch('province_pipeline.direct_export.transfer',return_value=dict(file_id='f',md5Checksum='test')) as transfer,patch(
                'province_pipeline.earth_engine.build_export') as batch:
            work(c,self.drive,plan,0,{'01':{'geometry':{}}})
        transfer.assert_called_once();batch.assert_not_called()
        self.assertEqual(self.drive.documents['reports','j-a1.json']['status'],'UPLOADED')


class CiMaterializationTests(unittest.TestCase):
    def test_old_secret_names_paths_only_and_private_permissions(self):
        from province_pipeline.ci_setup import prepare
        with tempfile.TemporaryDirectory() as tmp:
            prev=Path.cwd();os.chdir(tmp)
            try:
                env=dict(PROVINCE_CONFIG_JSON='{}',EE_SERVICE_ACCOUNT_JSON=json.dumps(dict(
                    type='service_account',client_email='TEST',private_key='TEST_KEY_NOT_REAL',token_uri='TEST')),
                    RCLONE_CONF='[gdrive]\ntype = drive\n',RUNNER_TEMP=tmp,GITHUB_ENV=str(Path(tmp)/'github-env'))
                prepare(env)
                text=Path(env['GITHUB_ENV']).read_text()
                self.assertNotIn('TEST_KEY_NOT_REAL',text)
                self.assertNotIn('[gdrive]',text)
                self.assertIn('PROVINCE_EE_CREDENTIALS=',text)
                self.assertIn('PROVINCE_RCLONE_CONFIG=',text)
                self.assertEqual(json.loads(Path('.province-local/config.json').read_text())['export_backend'],'direct')
                if os.name!='nt': self.assertEqual((Path(tmp)/'province-auth/ee-key.json').stat().st_mode&0o777,0o600)
            finally: os.chdir(prev)


class DirectDownloadTests(unittest.TestCase):
    def test_real_tiff_payload_download_grid_and_nodata(self):
        import numpy as np
        import rasterio
        from affine import Affine
        from province_pipeline.direct_export import download_image
        from province_pipeline.receiver import validate, hashes
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.tif'
            transform=[30,0,0,0,-30,120]
            with rasterio.open(source,'w',driver='GTiff',height=4,width=4,count=1,dtype='float32',
                               transform=Affine(*transform),crs='EPSG:6933') as ds:
                ds.write(np.ones((1,4,4),dtype='float32'))
            body=source.read_bytes()
            response=Mock(status_code=200)
            response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            response.iter_content.return_value=[body]
            image=Mock(); image.unmask.return_value=image
            image.getDownloadURL.return_value='https://example.invalid/test-url'
            job=dict(crs='EPSG:6933',scale=30,bands=['BLUE'],reserved_bytes=100000,
                     tile=dict(bounds=[0,0,120,120],transform=transform),kind='image')
            dest=Path(tmp)/'result.tif'
            with patch('ee.Geometry.Rectangle',return_value='test-region'),patch('requests.get',return_value=response):
                download_image(image,job,dest)
            params=image.getDownloadURL.call_args.args[0]
            self.assertEqual(params['dimensions'],[4,4])
            self.assertEqual(params['crs_transform'],transform)
            self.assertNotIn('region',params)
            self.assertNotIn('scale',params)
            # Exercise the actual SDK parameter validator; only serialization/HTTP are mocked.
            import ee
            fake_image=Mock()
            fake_image._build_download_id_image.return_value=None
            with patch('ee.data.serializer.encode',return_value={}),patch('ee.data._get_cloud_projects'),patch(
                    'ee.data._get_projects_path',return_value='projects/test'),patch('ee.data._maybe_populate_workload_tag'),patch(
                    'ee.data._execute_cloud_call',return_value={'name':'projects/test/thumbnails/test'}):
                result=ee.data.getDownloadId(dict(params,image=fake_image))
                self.assertIsInstance(result,dict)
                with self.assertRaisesRegex(ee.EEException,'simultaneously'):
                    ee.data.getDownloadId(dict(params,image=fake_image,region=[0,0,120,120]))
            self.assertEqual(validate(dest,dict(size=str(dest.stat().st_size),md5Checksum=hashes(dest)[0]),job),hashes(dest)[1])
            with rasterio.open(dest) as ds: self.assertEqual(ds.descriptions,('BLUE',))

    def test_oversized_tile_fails_without_request(self):
        from province_pipeline.direct_export import download_image
        job=dict(crs='EPSG:6933',scale=30,bands=['B']*10,tile=dict(bounds=[0,0,61440,61440],transform=[30,0,0,0,-30,61440]))
        with patch('ee.Geometry.Rectangle',return_value='region'),patch('requests.get') as get:
            with self.assertRaisesRegex(ValueError,'32 MB'): download_image(Mock(),job,Path('unused'))
        get.assert_not_called()


class DriveUploadTests(unittest.TestCase):
    def test_existing_upload_is_reused_by_checksum_not_overwritten(self):
        from province_pipeline.drive import Drive
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'tile.tif';p.write_bytes(b'TEST PAYLOAD')
            d=Drive.__new__(Drive);d.api=Mock()
            d.find=Mock(return_value=dict(id='existing',size=str(p.stat().st_size),md5Checksum=hashlib.md5(p.read_bytes()).hexdigest()))
            self.assertEqual(d.upload_verified('parent',p),'existing')
            d.api.files.assert_not_called()

    def test_conflicting_remote_output_is_not_overwritten(self):
        from province_pipeline.drive import Drive
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'tile.tif';p.write_bytes(b'TEST PAYLOAD')
            d=Drive.__new__(Drive);d.api=Mock();d.find=Mock(return_value=dict(id='existing',size='1',md5Checksum='different'))
            with self.assertRaisesRegex(RuntimeError,'refusing overwrite'): d.upload_verified('parent',p)
            d.api.files.assert_not_called()


if __name__=='__main__': unittest.main()
