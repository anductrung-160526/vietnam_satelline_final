"""Offline regression tests for admission, delivery safety, identities and scientific summaries."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from province_pipeline.common import provinces, local_path, tile_grid, load_config, atomic_json
from province_pipeline.controller import admit, reconcile, _remote_manifest
from province_pipeline.receiver import receive_manifest, validate, hashes
from province_pipeline.aggregate import growth, row_statistics, aggregate


class FakeDrive:
    def __init__(self):
        self.documents = {}
        self.files = {}
        self.contents = {}
        self.events = []
        self.fail_receipt = False
        self.fail_delete_once = False

    def read_json(self, parent, name, default=None):
        return copy.deepcopy(self.documents.get((parent, name), default))

    def write_json(self, parent, name, value):
        self.events.append(('write', parent))
        if parent == 'receipts' and self.fail_receipt:
            raise RuntimeError('Receipt upload unavailable')
        self.documents[parent, name] = copy.deepcopy(value)
        return name

    def children(self, parent):
        return [copy.deepcopy(f) for f in self.files.values() if f.get('parents') == [parent]]

    def metadata(self, file_id):
        if file_id not in self.files:
            error = RuntimeError('Not found')
            error.resp = SimpleNamespace(status=404)
            raise error
        return copy.deepcopy(self.files[file_id])

    def download(self, file_id, dest):
        self.events.append(('download', file_id))
        dest.write_bytes(self.contents[file_id])

    def delete_verified(self, expected, root):
        self.events.append(('delete', expected['id']))
        if self.fail_delete_once:
            self.fail_delete_once = False
            raise RuntimeError('Transient deletion failure')
        current = self.files[expected['id']]
        if current['version'] != expected['version']:
            raise RuntimeError('Source version changed')
        del self.files[expected['id']]


def config():
    return dict(drive_staging_budget_gib=1, drive_safety_margin_gib=0.1,
                high_watermark=0.65, low_watermark=0.3, max_active_exports=2)


def candidate(jid, size=100_000_000):
    return dict(job_id=jid, reserved_bytes=size, status='RESERVED')


class AdmissionTests(unittest.TestCase):
    def test_ten_requests_share_one_global_limit(self):
        state = {'jobs': {}}
        selected = admit(config(), state, [candidate(str(i)) for i in range(10)], 0, 2**30)
        self.assertEqual(len(selected), 2)

    def test_running_and_ambiguous_submissions_keep_reservation(self):
        for status in ('RUNNING', 'SUBMITTING', 'BLOCKED_AMBIGUOUS'):
            job = dict(candidate('old'), status=status)
            state = {'jobs': {'old':job}}
            self.assertEqual(len(admit(config(), state, [candidate('new')],0,2**30)), 1)

    def test_existing_completed_outputs_also_consume_space(self):
        state = {'jobs': {}}
        self.assertEqual(admit(config(), state, [candidate('a')], 650_000_000, 2**30), [])
        self.assertTrue(state['waiting_for_space'])

    def test_external_account_usage_blocks_exports(self):
        self.assertEqual(admit(config(), {'jobs':{}}, [candidate('a')],0,150_000_000), [])

    def test_hysteresis_waits_until_low_threshold(self):
        state = {'jobs':{}, 'waiting_for_space':True}
        self.assertEqual(admit(config(),state,[candidate('a')],400_000_000,2**30),[])
        self.assertEqual(len(admit(config(),state,[candidate('a')],100_000_000,2**30)),1)

    def test_oversize_tile_cannot_be_admitted(self):
        self.assertEqual(admit(config(), {'jobs':{}}, [candidate('a',2**31)],0,2**40),[])

    def test_restart_does_not_reassign_existing_id(self):
        state={'jobs':{'a':candidate('a')}}
        self.assertEqual(admit(config(), state, [candidate('a')], 0,2**30), [])


class IdentityTests(unittest.TestCase):
    def test_63_unique_codes_and_partition(self):
        ps = provinces()
        self.assertEqual(len({p['ma_tinh'] for p in ps}),63)
        self.assertEqual([sum(p['group_id']==i for p in ps) for i in range(10)],[7,7,7,6,6,6,6,6,6,6])
        self.assertEqual(ps[0]['ma_tinh'],'01')
        self.assertEqual(next(p['ten_tinh'] for p in ps if p['ma_tinh']=='46'),'Thừa Thiên Huế')

    def test_traversal_windows_and_posix_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            for value in ('../escape', '/absolute', 'E:/other', 'a\\b', 'a/file:stream', 'a/CON.txt', 'a/trailing.'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    local_path(root,value)
            self.assertEqual(local_path(root,'pkg/01_ha_noi/a.tif'),Path(root)/'pkg/01_ha_noi/a.tif')

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            try:
                (Path(root)/'link').symlink_to(other, target_is_directory=True)
            except OSError:
                self.skipTest('Symlinks unavailable')
            with self.assertRaises(ValueError): local_path(root,'link/x')

    def test_stable_nonoverlapping_grid(self):
        tiles=list(tile_grid([-10,-10,30,30],10,2))
        self.assertEqual(len(tiles),9)
        self.assertEqual(len({tuple(t['bounds']) for t in tiles}),9)
        self.assertEqual(tiles[0]['transform'],[10,0,-20,0,-10,0])

    def test_example_paused_and_no_deletion(self):
        c=load_config('province_pipeline/config/example.json')
        self.assertTrue(c['pause'])
        self.assertFalse(c['allow_remote_delete'])
        with self.assertRaisesRegex(ValueError,'project'):
            load_config('province_pipeline/config/example.json',live=True)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.drive=FakeDrive()
        self.folders=dict(reports='reports',receipts='receipts',manifests='manifests')
        self.job=dict(candidate('a'), folder_id='folder', prefix='01_ha_noi_test',kind='table',local_directory='pkg')
        self.state={'jobs':{'a':self.job}}

    def test_submission_intent_without_task_never_resubmits(self):
        self.drive.documents['reports','a.json']={'status':'SUBMITTING'}
        reconcile(self.drive,self.folders,self.state,[])
        self.assertEqual(self.job['status'],'BLOCKED_AMBIGUOUS')

    def test_no_intent_can_be_dispatched_again(self):
        reconcile(self.drive,self.folders,self.state,[])
        self.assertEqual(self.job['status'],'RESERVED')

    def test_recovered_task_uses_existing_id(self):
        reconcile(self.drive,self.folders,self.state,[dict(description='province_a',id='task1',state='RUNNING')])
        self.assertEqual(self.job['task_id'],'task1')
        self.assertEqual(self.job['status'],'RUNNING')

    def test_duplicate_tasks_stop_reconciliation(self):
        tasks=[dict(description='province_a',id=i,state='RUNNING') for i in ('a','b')]
        with self.assertRaisesRegex(RuntimeError,'Duplicate'): reconcile(self.drive,self.folders,self.state,tasks)

    def test_failed_task_is_distinct_from_complete(self):
        reconcile(self.drive,self.folders,self.state,[dict(description='province_a',id='t',state='FAILED',error_message='quota')])
        self.assertEqual(self.job['status'],'FAILED')
        self.assertEqual(self.job['error'],'quota')

    def test_manifest_requires_closed_checksum_verified_output(self):
        self.assertIsNone(_remote_manifest(self.drive,self.job))
        self.drive.files['f']=dict(id='f',name='unrelated.csv',parents=['folder'],size='1',md5Checksum='x',mimeType='text/csv')
        with self.assertRaises(RuntimeError): _remote_manifest(self.drive,self.job)


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.drive=FakeDrive()
        self.config=dict(local_root=str(self.root),volume_marker='disk1',allow_remote_delete=False,drive_root_id='root')
        self.folders=dict(receipts='receipts')
        self.job=dict(job_id='job1',kind='table',product='LANDSAT',period='2024',province={'ma_tinh':'01'},recipe_hash='recipe')
        body=b'ma_tinh,nam,period,job_id,valid_area,total_area,BLUE_w,BLUE_w2\n01,2024,2024,job1,10,20,20,50\n'
        self.file=dict(id='file1',name='01_ha_noi.csv',mimeType='text/csv',parents=['folder'],size=str(len(body)),
                       version='1',md5Checksum=hashlib.md5(body).hexdigest(),local_relative_path='pkg/01_ha_noi.csv')
        self.drive.files['file1']=copy.deepcopy(self.file)
        self.drive.contents['file1']=body
        self.manifest=dict(job_id='job1',job=self.job,files=[self.file])
        self.volume=patch('province_pipeline.receiver.verify_volume',return_value=self.root)
        self.volume.start()
        self.addCleanup(self.volume.stop)

    def receive(self, **kwargs):
        receive_manifest(self.config,self.drive,self.folders,self.manifest,self.root,**kwargs)

    def test_success_keeps_source_by_default(self):
        self.receive()
        self.assertTrue((self.root/'pkg/01_ha_noi.csv').exists())
        self.assertIn('file1',self.drive.files)
        self.assertTrue(self.drive.documents['receipts','job1.json']['files'][0]['verified'])

    def test_opt_in_delete_occurs_after_receipt(self):
        self.config['allow_remote_delete']=True
        self.receive()
        self.assertNotIn('file1',self.drive.files)
        self.assertLess(self.drive.events.index(('write','receipts')),self.drive.events.index(('delete','file1')))
        self.assertTrue(self.drive.documents['receipts','job1.json']['remote_deleted'])

    def test_bad_checksum_never_deletes(self):
        self.config['allow_remote_delete']=True
        self.drive.contents['file1']=b'x'*int(self.file['size'])
        with self.assertRaisesRegex(ValueError,'MD5'): self.receive()
        self.assertIn('file1',self.drive.files)
        self.assertNotIn(('delete','file1'),self.drive.events)

    def test_failed_receipt_upload_keeps_source_and_can_resume(self):
        self.config['allow_remote_delete']=True
        self.drive.fail_receipt=True
        with self.assertRaises(RuntimeError): self.receive()
        self.assertIn('file1',self.drive.files)
        self.drive.fail_receipt=False
        self.receive()
        self.assertNotIn('file1',self.drive.files)
        self.assertEqual(self.drive.events.count(('download','file1')),1)

    def test_failed_delete_retries_without_redownloading(self):
        self.config['allow_remote_delete']=True
        self.drive.fail_delete_once=True
        with self.assertRaises(RuntimeError): self.receive()
        self.assertIn('file1',self.drive.files)
        self.receive()
        self.assertNotIn('file1',self.drive.files)
        self.assertEqual(self.drive.events.count(('download','file1')),1)

    def test_crash_after_delete_before_final_receipt_can_resume(self):
        self.receive()
        del self.drive.files['file1']
        self.config['allow_remote_delete']=True
        self.receive()
        self.assertTrue(self.drive.documents['receipts','job1.json']['remote_deleted'])

    def test_missing_previously_verified_local_file_does_not_delete(self):
        self.receive()
        (self.root/'pkg/01_ha_noi.csv').unlink()
        self.config['allow_remote_delete']=True
        with self.assertRaisesRegex(RuntimeError,'missing locally'): self.receive()
        self.assertIn('file1',self.drive.files)

    def test_wrong_volume_before_delete_keeps_source(self):
        self.config['allow_remote_delete']=True
        self.volume.stop()
        with patch('province_pipeline.receiver.verify_volume',side_effect=RuntimeError('Wrong disk')):
            with self.assertRaisesRegex(RuntimeError,'Wrong disk'): self.receive()
        self.assertIn('file1',self.drive.files)

    def test_source_version_changed_before_download_keeps_source(self):
        self.drive.files['file1']['version']='2'
        with self.assertRaisesRegex(ValueError,'source changed'): self.receive()
        self.assertIn('file1',self.drive.files)

    def test_local_corruption_after_receipt_keeps_source(self):
        self.receive()
        (self.root/'pkg/01_ha_noi.csv').write_bytes(b'x'*int(self.file['size']))
        self.config['allow_remote_delete']=True
        with self.assertRaises(ValueError): self.receive()
        self.assertIn('file1',self.drive.files)

    def test_no_space_keeps_source(self):
        with patch('province_pipeline.receiver.shutil.disk_usage',return_value=SimpleNamespace(free=1)):
            with self.assertRaisesRegex(RuntimeError,'full'): self.receive()
        self.assertIn('file1',self.drive.files)

    def test_dry_run_performs_no_download_or_receipt(self):
        self.receive(dry_run=True)
        self.assertEqual(self.drive.events,[])

    def test_wrong_csv_identity_never_acknowledged(self):
        self.drive.contents['file1']=self.drive.contents['file1'].replace(b'job1',b'job2')
        self.file['md5Checksum']=hashlib.md5(self.drive.contents['file1']).hexdigest()
        self.drive.files['file1']['md5Checksum']=self.file['md5Checksum']
        with self.assertRaisesRegex(ValueError,'identity'): self.receive()
        self.assertEqual(self.drive.documents,{})

    def test_local_aggregate_exports_all_formats_and_preserves_code(self):
        self.receive()
        # Limit bands to the sufficient statistics in this deterministic test CSV.
        spec={'bands':['BLUE']}
        with patch.dict('province_pipeline.aggregate.SOURCES',{'LANDSAT':spec}):
            # Metadata documentation uses full catalog; write it separately in a normal run.
            with patch('province_pipeline.aggregate.write_package_docs'):
                self.assertEqual(aggregate(self.root),1)
        import pandas as pd
        dest=self.root/'VN_LandCover_Panel_2004_2025/data_processed/panels/LANDSAT_recipe'
        for ext in ('.csv','.xlsx','.dta'):
            self.assertTrue(dest.with_suffix(ext).is_file())
        self.assertEqual(pd.read_stata(dest.with_suffix('.dta')).iloc[0]['ma_tinh'],'01')


class ScientificSummaryTests(unittest.TestCase):
    def test_area_weighted_mean_and_population_std(self):
        row=dict(valid_area=10,total_area=20,BLUE_w=20,BLUE_w2=50)
        result=row_statistics(row,'SENTINEL2_10M')
        self.assertEqual(result['BLUE_mean'],2)
        self.assertEqual(result['BLUE_std'],1)
        self.assertEqual(result['valid_fraction'],0.5)

    def test_no_valid_pixels_are_missing_not_zero(self):
        import math
        row=row_statistics(dict(valid_area=0,total_area=20),'DMSP')
        self.assertTrue(math.isnan(row['sol_ntl']))
        self.assertEqual(row['qa'],'NO_VALID_PIXELS')

    def test_growth_needs_immediately_previous_period_and_nonzero_base(self):
        import pandas as pd
        f=pd.DataFrame(dict(ma_tinh=['01']*5,period=['2020','2021','2023','2024','2025'],sol_ntl=[10,12,20,0,10]))
        result=growth(f,'sol_ntl')
        self.assertAlmostEqual(result.iloc[1]['thay_doi_ntl'],20)
        self.assertTrue(pd.isna(result.iloc[2]['thay_doi_ntl']))
        self.assertTrue(pd.isna(result.iloc[4]['thay_doi_ntl']))

    def test_monthly_growth_handles_year_boundary(self):
        import pandas as pd
        f=pd.DataFrame(dict(ma_tinh=['01']*2,period=['2023-12','2024-01'],sol_ntl=[10,11]))
        self.assertAlmostEqual(growth(f,'sol_ntl').iloc[1]['thay_doi_ntl'],10)


class GeometryAndRasterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def fixture(self):
        from shapely.geometry import box, mapping
        features=[]
        for i,p in enumerate(provinces()):
            features.append(dict(type='Feature',properties={'ma_tinh':p['ma_tinh']},
                            geometry=mapping(box(105+i*0.002,20,105.001+i*0.002,20.001))))
        path=self.root/'boundaries.geojson'
        path.write_text(json.dumps(dict(type='FeatureCollection',features=features)))
        meta=dict(source='TEST FIXTURE ONLY',version='fixture',date='2024-01-01',crosswalk_verified=True,
                  code_reference='TEST ONLY',sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        mp=self.root/'boundaries.metadata.json'; mp.write_text(json.dumps(meta))
        c=load_config('province_pipeline/config/example.json')
        c.update(boundaries=str(path),boundary_metadata=str(mp),boundary_policy='official_2024')
        return c,path,mp

    def test_boundary_checksum_and_exact_code_coverage(self):
        from province_pipeline.boundaries import load_boundaries
        c,path,mp=self.fixture()
        self.assertEqual(len(load_boundaries(c)[0]),63)
        path.write_text(path.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'SHA-256'): load_boundaries(c)

    def test_duplicate_boundary_code_rejected(self):
        from province_pipeline.boundaries import load_boundaries
        c,path,mp=self.fixture()
        data=json.loads(path.read_text()); data['features'][1]['properties']['ma_tinh']='01'; path.write_text(json.dumps(data))
        meta=json.loads(mp.read_text());meta['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();mp.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError,'duplicate'): load_boundaries(c)

    def test_jobs_deterministic_and_recipe_changes_identity(self):
        from province_pipeline.boundaries import load_boundaries
        from province_pipeline.jobs import generate
        c,path,mp=self.fixture(); b,m=load_boundaries(c)
        first=list(generate(c,b,m)); second=list(generate(c,b,m))
        self.assertEqual(first,second)
        self.assertTrue(all(j['prefix'].startswith('01_ha_noi_') for j in first))
        self.assertTrue(all(j['reserved_bytes']>0 for j in first))
        c['season_months']=[1]
        self.assertFalse({j['job_id'] for j in first}&{j['job_id'] for j in generate(c,b,m)})

    def test_tiff_blocks_crs_grid_and_checksum(self):
        import rasterio
        import numpy as np
        from affine import Affine
        path=self.root/'tile.tif'
        transform=[30,0,0,0,-30,120]
        with rasterio.open(path,'w',driver='GTiff',width=4,height=4,count=1,dtype='float32',
                           crs='EPSG:6933',transform=Affine(*transform),nodata=-9999) as ds:
            ds.write(np.ones((1,4,4),dtype='float32'))
        f=dict(size=str(path.stat().st_size),md5Checksum=hashes(path)[0])
        job=dict(kind='image',crs='EPSG:6933',bands=['BLUE'],scale=30,tile=dict(bounds=[0,0,120,120],transform=transform))
        self.assertEqual(validate(path,f,job),hashes(path)[1])
        job['scale']=20
        with self.assertRaisesRegex(ValueError,'dimensions'): validate(path,f,job)


class ConditionalDeleteTests(unittest.TestCase):
    def adapter(self, etag='tag', parent='root', name='folder'):
        from province_pipeline.drive import Drive
        d=Drive.__new__(Drive)
        d.api=Mock()
        f=dict(id='f',version='1',size='1',md5Checksum='md5',parents=['p'],_etag=etag)
        d.metadata=Mock(side_effect=lambda i: copy.deepcopy(f) if i=='f' else dict(id='p',name=name,parents=[parent]))
        return d,f

    def test_missing_etag_blocks_delete(self):
        d,f=self.adapter(etag=None)
        with self.assertRaisesRegex(RuntimeError,'conditional'): d.delete_verified(f,'root')
        d.api.files.assert_not_called()

    def test_control_files_never_deleted(self):
        d,f=self.adapter(name='_control')
        with self.assertRaisesRegex(RuntimeError,'Control'): d.delete_verified(f,'root')
        d.api.files.assert_not_called()

    def test_delete_uses_if_match_and_exact_id(self):
        d,f=self.adapter(); req=d.api.files.return_value.delete.return_value; req.headers={}
        d.delete_verified(f,'root')
        self.assertEqual(req.headers['If-Match'],'tag')
        d.api.files.return_value.delete.assert_called_once_with(fileId='f',supportsAllDrives=True)
        req.execute.assert_called_once()

    def test_source_version_change_blocks_delete(self):
        d,f=self.adapter(); f=dict(f,version='0')
        with self.assertRaisesRegex(RuntimeError,'changed'): d.delete_verified(f,'root')
        d.api.files.assert_not_called()


class ControllerIntegrationTests(unittest.TestCase):
    def drive(self):
        d=FakeDrive()
        d.folder=lambda parent,name: parent+'/'+name
        d.assert_unique_folder_name=lambda name,fid: None
        d.usage=lambda root: 0
        d.account_free=lambda: 2**30
        return d

    def job(self, jid='j'):
        return dict(candidate(jid),province=dict(ma_tinh='01',slug='ha_noi',group_id=0),
                    product='LANDSAT',period='2024',recipe_hash='r',local_directory='pkg/raw',prefix='01_ha_noi_test')

    def test_reservation_saved_before_plan_and_restart_reuses_it(self):
        from province_pipeline.controller import prepare
        d=self.drive(); c=dict(config(),drive_root_id='root',pause=False)
        check=Mock(return_value=dict(status='AVAILABLE',asset_ids=['scene']))
        first=prepare(c,d,[self.job()],check,[])
        second=prepare(c,d,[self.job()],check,[])
        self.assertEqual(first['jobs'],second['jobs'])
        self.assertEqual(check.call_count,1)
        self.assertEqual(d.events[-1],('write','root/_control'))
        self.assertEqual(len(d.documents['root/_control','state.json']['jobs']),1)

    def test_external_tasks_prevent_new_submission_and_inventory_calls(self):
        from province_pipeline.controller import prepare
        d=self.drive(); c=dict(config(),drive_root_id='root',pause=False)
        check=Mock()
        tasks=[dict(state='RUNNING',description='other',id=str(i)) for i in range(2)]
        plan=prepare(c,d,[self.job()],check,tasks)
        self.assertEqual(plan['jobs'],[])
        check.assert_not_called()

    def test_pause_never_allocates(self):
        from province_pipeline.controller import prepare
        d=self.drive(); c=dict(config(),drive_root_id='root',pause=True)
        check=Mock()
        self.assertEqual(prepare(c,d,[self.job()],check,[])['jobs'],[])
        check.assert_not_called()

    def test_partial_source_not_silently_exported(self):
        from province_pipeline.controller import prepare
        d=self.drive(); c=dict(config(),drive_root_id='root',pause=False)
        plan=prepare(c,d,[self.job()],lambda j: dict(status='PARTIAL'),[])
        self.assertEqual(plan['jobs'],[])
        self.assertEqual(len(d.documents['root/_control','state.json']['inventory']),1)


class GadmPreparationTests(unittest.TestCase):
    def fixture(self):
        import csv, io, zipfile
        from province_pipeline import prepare_gadm as gadm
        with Path('province_pipeline/data/gadm41_province_crosswalk.csv').open(encoding='utf-8') as stream:
            rows=list(csv.DictReader(stream))
        features=[]
        for i,row in enumerate(rows):
            x=105+i*0.002
            features.append(dict(type='Feature',properties={'GID_1':row['gid_1'],'NAME_1':row['source_name']},
                geometry=dict(type='Polygon',coordinates=[[[x,20],[x+0.001,20],[x+0.001,20.001],[x,20.001],[x,20]]])))
        raw=json.dumps(dict(type='FeatureCollection',features=features)).encode()
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z: z.writestr(gadm.MEMBER,raw)
        return raw,stream.getvalue()

    def test_crosswalk_has_63_unique_exact_identities(self):
        import csv
        with open('province_pipeline/data/gadm41_province_crosswalk.csv',encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len({r['gid_1'] for r in rows}),63)
        self.assertEqual(len({r['ma_tinh'] for r in rows}),63)
        self.assertEqual(next(r['gid_1'] for r in rows if r['ma_tinh']=='01'),'VNM.27_1')
        self.assertEqual(next(r['ma_tinh'] for r in rows if r['gid_1']=='VNM.1_1'),'89')

    def test_archive_mismatch_is_rejected_before_writing(self):
        from province_pipeline.prepare_gadm import prepare
        with tempfile.TemporaryDirectory() as root:
            c=dict(boundaries=str(Path(root)/'b.json'),boundary_metadata=str(Path(root)/'m.json'))
            with self.assertRaisesRegex(ValueError,'archive checksum'): prepare(c,b'wrong')
            self.assertEqual(list(Path(root).iterdir()),[])

    def test_prepare_metadata_and_idempotent_no_network_resume(self):
        from province_pipeline import prepare_gadm as gadm
        raw,archive=self.fixture()
        with tempfile.TemporaryDirectory() as root:
            c=dict(boundaries=str(Path(root)/'b.json'),boundary_metadata=str(Path(root)/'m.json'),boundary_policy='gadm41_research')
            with patch.object(gadm,'SOURCE_SHA256',hashlib.sha256(raw).hexdigest()),patch.object(gadm,'ZIP_SHA256',hashlib.sha256(archive).hexdigest()):
                self.assertEqual(gadm.prepare(c,archive),63)
                before=Path(c['boundaries']).read_bytes()
                self.assertEqual(gadm.prepare(c),63)
                self.assertEqual(before,Path(c['boundaries']).read_bytes())
            meta=json.loads(Path(c['boundary_metadata']).read_text())
            self.assertEqual(meta['date'],'2022-07-18')
            self.assertEqual(meta['boundary_profile'],gadm.PROFILE)
            self.assertTrue(meta['crosswalk_verified'])

    def test_source_checksum_mismatch_is_rejected(self):
        from province_pipeline.prepare_gadm import convert
        with self.assertRaisesRegex(ValueError,'source checksum'): convert(b'{}')


if __name__ == '__main__':
    unittest.main()
