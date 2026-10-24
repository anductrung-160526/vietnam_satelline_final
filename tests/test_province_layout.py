"""Canonical package paths, shared folders, stable identities and resumable migration."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from province_pipeline.layout import output_directory,canonical_job,relative_output,PACKAGE_DIRECTORIES
from province_pipeline.sources import NTL_PACKAGE,DAY_PACKAGE
from province_pipeline.controller import _remote_manifest,reconcile
from province_pipeline.organize import organize,organize_local
from province_pipeline.common import digest,load_config,atomic_json
from test_province_pipeline import FakeDrive


def job(kind='image',product='LANDSAT',variant='composite'):
    return dict(job_id='job1',kind=kind,product=product,variant=variant,period='2024',
        province=dict(ma_tinh='01',ten_tinh='Hà Nội',slug='ha_noi',group_id=0),
        recipe_hash='recipe',export_backend='direct',reserved_bytes=100000,
        prefix='01_ha_noi_test',folder_id='legacy',folder_name='legacy',
        local_directory='legacy/01_ha_noi/2024',status='REMOTE_READY')


class LayoutTests(unittest.TestCase):
    def test_province_is_immediate_child_of_each_requested_data_directory(self):
        for product in ('DMSP','VIIRS_MONTHLY','VIIRS_ANNUAL','LANDSAT','SENTINEL2','SENTINEL2_10M'):
            item=job(product=product)
            path=output_directory(item).split('/')
            self.assertIn(path[0],(NTL_PACKAGE,DAY_PACKAGE))
            self.assertEqual(path[4],'01_ha_noi')
            self.assertEqual(path.count('01_ha_noi'),1)
            processed=output_directory(job(kind='table',product=product,variant='statistics')).split('/')
            self.assertEqual(processed[1:3],['data_processed','01_ha_noi'])
        filtered=output_directory(job(product='VIIRS_MONTHLY',variant='filtered')).split('/')
        self.assertEqual(filtered[1:3],['data_intermediate','01_ha_noi'])

    def test_all_pdf_package_directories_are_reserved(self):
        for paths in PACKAGE_DIRECTORIES.values():
            self.assertTrue({'metadata','code','docs','logs','dashboard','data_processed','data_intermediate'}<=set(paths))
        self.assertIn('samples',PACKAGE_DIRECTORIES[DAY_PACKAGE])

    def test_layout_change_keeps_old_scientific_job_ids(self):
        from province_pipeline.jobs import generate
        c=load_config('province_pipeline/config/example.json')
        c['products']=['LANDSAT','VIIRS_MONTHLY','DMSP']
        b={'01':dict(geometry=dict(type='Polygon',coordinates=[[[105,20],[105.001,20],[105.001,20.001],[105,20.001],[105,20]]]))}
        m=dict(sha256='test',source='test',version='test',date='2024-01-01',code_reference='test')
        items=list(generate(c,b,m))
        for item in items:
            legacy=dict(item)
            jid=legacy.pop('job_id');legacy.pop('layout_version')
            night=item['product'].startswith(('DMSP','VIIRS'))
            package=NTL_PACKAGE if night else DAY_PACKAGE
            sensor='VIIRS' if item['product'].startswith('VIIRS') else item['product'].split('_')[0]
            if item['kind']=='table':
                legacy['local_directory']=f'{package}/data_processed/source/{item["product"]}/01_ha_noi'
            elif item['variant']=='filtered':
                legacy['local_directory']=f'{package}/data_intermediate/NTL/{sensor}/01_ha_noi/2024-01'
                if item['product']=='DMSP':legacy['local_directory']=legacy['local_directory'].replace('2024-01','2024')
            else:
                stage='NTL' if night else 'DAY'
                legacy['local_directory']=f'{package}/raw_data/{stage}/{sensor}/01_ha_noi/{item["period"]}'
            self.assertEqual(jid,digest(legacy)[:32])
            self.assertEqual(item['layout_version'],2)

    def test_shared_folder_selects_exact_job_filename(self):
        d=FakeDrive();j=canonical_job(job())
        d.files={'a':dict(id='a',parents=['legacy'],name=j['prefix']+'.tif',mimeType='image/tiff',size='10',md5Checksum='md5'),
                 'b':dict(id='b',parents=['legacy'],name=j['prefix']+'_another.tif',mimeType='image/tiff',size='10',md5Checksum='other')}
        result=_remote_manifest(d,j)
        self.assertEqual(result['files'][0]['id'],'a')
        self.assertEqual(result['files'][0]['local_relative_path'],relative_output(j,j['prefix']+'.tif'))
        d.files['c']=dict(d.files['a'],id='c')
        with self.assertRaises(RuntimeError):_remote_manifest(d,j)

    def test_other_jobs_in_shared_folder_do_not_block_failed_retry(self):
        d=FakeDrive();j=canonical_job(job());j['status']='RUNNING';j['attempt']=1
        folders=dict(reports='reports',receipts='receipts',manifests='manifests')
        d.documents['reports','job1-a1.json']={'status':'FAILED'}
        d.files['other']=dict(id='other',parents=['legacy'],name='other_job.tif')
        reconcile(d,folders,{'jobs':{'job1':j}},[])
        self.assertEqual(j['status'],'RESERVED');self.assertEqual(j['attempt'],2)


class MigrationDrive(FakeDrive):
    def __init__(self):
        super().__init__();self.fail_after_move=False
    def folder(self,parent,name):return parent+'/'+name
    def move_verified(self,expected,parent,root):
        state=self.documents[root+'/_control','state.json']
        assert state['jobs']['job1']['status']=='MIGRATING'
        current=self.files[expected['id']]
        assert current['md5Checksum']==expected['md5Checksum']
        if current['parents']!=[parent]:
            current['parents']=[parent];current['version']=str(int(current['version'])+1)
            self.events.append(('move',expected['id']))
        if self.fail_after_move:
            self.fail_after_move=False
            raise RuntimeError('Lost move response')
        return copy.deepcopy(current)


class MigrationTests(unittest.TestCase):
    def fixture(self):
        d=MigrationDrive();j=job(kind='table',variant='statistics')
        f=dict(id='f',name='01_ha_noi_test.csv',mimeType='text/csv',parents=['legacy'],size='10',
               md5Checksum='md5',version='1',local_relative_path='legacy/01_ha_noi/2024/01_ha_noi_test.csv')
        d.files['f']=copy.deepcopy(f)
        d.files['unrelated']=dict(id='unrelated',parents=['legacy'],name='personal.csv')
        d.documents['root/_control','state.json']={'jobs':{'job1':j},'inventory':{},'cursor':0}
        d.documents['root/_control/manifests','job1.json']=dict(job_id='job1',job=copy.deepcopy(j),files=[f])
        return d,dict(pause=True,drive_root_id='root')

    def test_move_keeps_file_id_and_does_not_touch_unrelated_files(self):
        d,c=self.fixture();self.assertEqual(organize(c,d),(1,0))
        expected='root/'+output_directory(job(kind='table',variant='statistics'))
        self.assertEqual(d.files['f']['parents'],[expected])
        self.assertEqual(d.files['unrelated']['parents'],['legacy'])
        self.assertFalse(any(e[0]=='delete' for e in d.events))
        final=d.documents['root/_control','state.json']['jobs']['job1']
        self.assertEqual(final['job_id'],'job1');self.assertEqual(final['layout_version'],2)
        manifest=d.documents['root/_control/manifests','job1.json']
        self.assertEqual(manifest['files'][0]['version'],'2')
        self.assertTrue(manifest['files'][0]['legacy_local_relative_paths'])
        self.assertEqual(organize(c,d),(0,0))

    def test_lost_move_response_resumes_without_duplicate_move_or_download(self):
        d,c=self.fixture();d.fail_after_move=True
        with self.assertRaisesRegex(RuntimeError,'Lost move'):organize(c,d)
        self.assertEqual(d.documents['root/_control','state.json']['jobs']['job1']['status'],'MIGRATING')
        self.assertEqual(organize(c,d),(1,0))
        self.assertEqual(d.events.count(('move','f')),1)
        self.assertEqual(d.documents['root/_control','state.json']['jobs']['job1']['status'],'REMOTE_READY')

    def test_migration_requires_paused_exports(self):
        d,c=self.fixture();c['pause']=False
        with self.assertRaisesRegex(ValueError,'pause=true'):organize(c,d)
        self.assertFalse(any(e[0]=='move' for e in d.events))

    def test_unresolved_jobs_not_moved(self):
        d,c=self.fixture();d.documents['root/_control','state.json']['jobs']['job1']['status']='FAILED'
        self.assertEqual(organize(c,d),(0,1))
        self.assertEqual(d.files['f']['parents'],['legacy'])


class LocalCompatibilityTests(unittest.TestCase):
    def fixture(self,root):
        from province_pipeline.receiver import hashes
        j=job(kind='table',variant='statistics')
        data=b'ma_tinh,nam,period,job_id,valid_area,total_area\n01,2024,2024,job1,10,20\n'
        path=root/'legacy'/'old.csv';path.parent.mkdir();path.write_bytes(data)
        f=dict(id='f',name='01_ha_noi_test.csv',size=str(len(data)),md5Checksum=hashes(path)[0],version='1',
               parents=['remote_old'],local_relative_path='legacy/old.csv')
        manifest=dict(job_id='job1',job=j,files=[f])
        receipt=dict(job_id='job1',volume_marker='disk',files=[dict(id='f',verified=True,sha256=hashes(path)[1],
                     local_relative_path='legacy/old.csv',deleted=True)])
        atomic_json(root/'.manifests/job1.json',manifest);atomic_json(root/'.receipts/job1.json',receipt)
        return manifest,receipt,path

    def test_local_organization_preserves_verified_bytes_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m,r,old=self.fixture(root)
            expected=old.read_bytes()
            self.assertEqual(organize_local(root),1)
            dest=root/relative_output(m['job'],m['files'][0]['name'])
            self.assertEqual(dest.read_bytes(),expected);self.assertFalse(old.exists())
            self.assertEqual(organize_local(root),0)
            receipt=json.loads((root/'.receipts/job1.json').read_text())
            self.assertEqual(receipt['files'][0]['local_relative_path'],dest.relative_to(root).as_posix())

    def test_resume_after_rename_before_manifest_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m,r,old=self.fixture(root)
            dest=root/relative_output(m['job'],m['files'][0]['name']);dest.parent.mkdir(parents=True)
            old.replace(dest)
            self.assertEqual(organize_local(root),0)
            self.assertEqual(json.loads((root/'.manifests/job1.json').read_text())['local_layout_version'],2)

    def test_receiver_reuses_old_verified_copy_without_redownloading(self):
        from province_pipeline.receiver import receive_manifest
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m,r,old=self.fixture(root);r['files'][0]['deleted']=False
            atomic_json(root/'.receipts/job1.json',r)
            d=FakeDrive();c=dict(volume_marker='disk',allow_remote_delete=False)
            receive_manifest(c,d,dict(receipts='receipts'),m,root)
            dest=root/relative_output(m['job'],m['files'][0]['name'])
            self.assertTrue(dest.is_file());self.assertFalse(old.exists())
            self.assertFalse(any(e[0]=='download' for e in d.events))

    def test_local_corruption_blocks_reorganization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m,r,old=self.fixture(root);old.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):organize_local(root)
            self.assertTrue(old.exists())


class DriveRelocationTests(unittest.TestCase):
    def fixture(self):
        from province_pipeline.drive import Drive
        d=Drive.__new__(Drive);d.api=Mock()
        nodes={'new':dict(id='new',name='2024',parents=['root']),
               'old':dict(id='old',name='old_job',parents=['root']),
               'f':dict(id='f',name='image.tif',parents=['old'],md5Checksum='md5',size='10',version='1',_etag='etag')}
        d.metadata=Mock(side_effect=lambda key:copy.deepcopy(nodes[key]))
        request=d.api.files.return_value.update.return_value;request.headers={}
        def moved():nodes['f'].update(parents=['new'],version='2')
        request.execute.side_effect=moved
        return d,nodes

    def test_move_preserves_id_and_checks_version_and_parent(self):
        d,nodes=self.fixture();expected=copy.deepcopy(nodes['f'])
        result=d.move_verified(expected,'new','root')
        self.assertEqual(result['id'],'f');self.assertEqual(result['parents'],['new'])
        call=d.api.files.return_value.update.call_args.kwargs
        self.assertEqual(call['fileId'],'f');self.assertEqual(call['removeParents'],'old');self.assertEqual(call['addParents'],'new')
        self.assertEqual(d.api.files.return_value.update.return_value.headers['If-Match'],'etag')
        d.api.files.return_value.delete.assert_not_called()
        d.api.files.return_value.update.reset_mock()
        self.assertEqual(d.move_verified(expected,'new','root')['id'],'f')
        d.api.files.return_value.update.assert_not_called()

    def test_changed_source_content_blocks_move(self):
        d,nodes=self.fixture();expected=copy.deepcopy(nodes['f']);nodes['f']['md5Checksum']='different'
        with self.assertRaisesRegex(RuntimeError,'content changed'):d.move_verified(expected,'new','root')
        d.api.files.return_value.update.assert_not_called()

    def test_outside_root_target_is_rejected(self):
        d,nodes=self.fixture();nodes['new']['parents']=[]
        with self.assertRaisesRegex(RuntimeError,'staging tree'):d.move_verified(nodes['f'],'new','root')
        d.api.files.return_value.update.assert_not_called()


if __name__=='__main__':unittest.main()
