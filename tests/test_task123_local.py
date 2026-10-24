"""Direct-to-E mode: no Drive calls, atomic local commits, verified restart."""
import copy
import json
import tempfile
import unittest
import csv
import hashlib
from pathlib import Path
from unittest.mock import patch,Mock
import numpy as np
import rasterio
from affine import Affine
from task_pipeline.scope import configure
from task_pipeline.local import run,export,prior,panels
from task_pipeline.province_image import output_job,OutputLimit
from province_pipeline.jobs import table_job
from province_pipeline.profiles import table_specs
from province_pipeline.common import atomic_json
from province_pipeline.receiver import hashes
from test_task123_branches import base,selection
from test_province_v2 import META


def config():
    c=configure(base(),selection())
    c.update(execution_backend='local',local_output_limit_bytes=40*1024**3,volume_marker='test')
    return c


def image_job(c):
    spec=next(s for s in table_specs(c) if s['period']=='2025-01' and s['night'])
    return output_job(c,table_job(c,spec,META),[105,20,105.01,20.01],0)


class LocalTests(unittest.TestCase):
    def test_all_group_night_images_precede_any_tables_and_day_images(self):
        c=configure(base(),selection(mode='full'));c['task_scope']['provinces']=c['task_scope']['provinces'][:2]
        c['province_codes']=[p['ma_tinh'] for p in c['task_scope']['provinces']]
        c.update(execution_backend='local',volume_marker='test',local_output_limit_bytes=40*1024**3)
        template=image_job(c);visited=[]
        def jobs(active,boundaries,metadata,stage):
            code=active['province_codes'][0];visited.append((stage,code))
            job=copy.deepcopy(template)
            job['job_id']=f'{stage}-{code}';job['province']['ma_tinh']=code
            return iter([job])
        source=Mock(return_value=dict(status='UNAVAILABLE',count=0))
        expected=[(stage,code) for stage in range(3) for code in c['province_codes']]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('task_pipeline.local.verify_volume',return_value=root),patch('task_pipeline.local.generate_v2',side_effect=jobs),patch('task_pipeline.local.panels',return_value={}):
                self.assertEqual(run(c,root,{},META,inventory=source),0)
                self.assertEqual(visited,expected)
                visited.clear()
                self.assertEqual(run(c,root,{},META,inventory=source),0)
                self.assertEqual(visited,expected)
            # Synthetic stages share the same source/period, so inventory is cached.
            self.assertEqual(source.call_count,2)
            state=json.loads((root/'.local_state/state.json').read_text())
            self.assertEqual(len(state['jobs']),6)

    def test_night_failure_stops_group_before_csv_or_day_images(self):
        c=config();c['task_scope']['provinces']=selection(mode='full')['provinces'][:2]
        c['province_codes']=[p['ma_tinh'] for p in c['task_scope']['provinces']]
        j=image_job(c);visited=[]
        def jobs(active,boundaries,metadata,stage):
            visited.append((stage,active['province_codes'][0]))
            return iter([j])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('task_pipeline.local.verify_volume',return_value=root),patch('task_pipeline.local.generate_v2',side_effect=jobs),patch('task_pipeline.local.panels',return_value={}):
                code=run(c,root,{},META,inventory=Mock(side_effect=RuntimeError('network')))
            self.assertEqual(code,2)
            self.assertEqual(visited,[(0,'01')])

    def test_direct_output_limit_uses_external_disk_not_drive_budget(self):
        c=config();c['drive_staging_budget_gib']=None
        j=image_job(c)
        self.assertGreater(j['reserved_bytes'],0)
        self.assertEqual(j['image_layout'],'province')
        self.assertFalse(j['preview_required'])

    def test_image_is_committed_directly_and_restart_uses_its_receipt(self):
        c=config();j=image_job(c)
        def download(image,job,path,boundary,config):
            t=job['tile']
            with rasterio.open(path,'w',driver='GTiff',width=t['width'],height=t['height'],count=2,
                dtype='float64',crs=job['crs'],transform=Affine(*t['transform']),nodata=-9999) as ds:
                ds.write(np.ones((2,t['height'],t['width']),dtype='float64'))
            return dict(strategy='whole',requests=1)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('task_pipeline.local.verify_volume',return_value=root),patch('task_pipeline.methods.composite'),patch('ee.Geometry'),patch('task_pipeline.local.province_image.download',side_effect=download),patch('province_pipeline.auth.drive_credentials',side_effect=AssertionError('Drive must not be used')):
                proof=export(c,root,j,{'geometry':None})
                self.assertEqual(prior(c,root,j)['sha256'],proof['sha256'])
            dest=root/proof['relative_path']
            self.assertTrue(dest.exists());self.assertFalse(list(root.rglob('*.png')))
            self.assertEqual(hashes(dest)[1],proof['sha256'])
            self.assertEqual(list((root/'.work').iterdir()),[])

    def test_untracked_existing_file_is_not_overwritten(self):
        c=config();j=image_job(c)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dest=root/j['local_directory']/(j['prefix']+'.tif');dest.parent.mkdir(parents=True)
            dest.write_bytes(b'user file')
            with patch('task_pipeline.local.verify_volume',return_value=root):
                with self.assertRaisesRegex(RuntimeError,'refusing overwrite'):export(c,root,j,{'geometry':None})
            self.assertEqual(dest.read_bytes(),b'user file')

    def test_failed_download_does_not_create_final_output_or_receipt(self):
        c=config();j=image_job(c)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('task_pipeline.local.verify_volume',return_value=root),patch('task_pipeline.methods.composite'),patch('ee.Geometry'),patch('task_pipeline.local.province_image.download',side_effect=RuntimeError('network')):
                with self.assertRaisesRegex(RuntimeError,'network'):export(c,root,j,{'geometry':None})
            self.assertFalse(list(root.rglob('*.tif')))
            self.assertFalse((root/'.local_state/receipts'/f"{j['job_id']}.json").exists())

    def test_resume_and_missing_source_without_any_drive_credentials(self):
        c=config();c['years']=[2025];j=image_job(c)
        record=dict(ma_tinh='01',job_id='stat',period='2025-01',nam=2025,total_area=1,valid_area=0)
        source=Mock(return_value=dict(status='UNAVAILABLE',count=0))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('task_pipeline.local.verify_volume',return_value=root),patch('task_pipeline.local.generate_v2',side_effect=lambda c,b,m,s:iter([j]) if s==0 else iter([])),patch('task_pipeline.local.panels',return_value={}),patch('province_pipeline.auth.drive_credentials',side_effect=AssertionError('Drive must not be used')):
                self.assertEqual(run(c,root,{'01':{}},META,inventory=source),0)
                self.assertEqual(run(c,root,{'01':{}},META,inventory=source),0)
            self.assertEqual(source.call_count,1)
            state=json.loads((root/'.local_state/state.json').read_text())
            self.assertEqual(state['execution_backend'],'local')
            self.assertEqual(state['jobs'][j['job_id']]['status'],'MISSING_SOURCE')

    def test_pause_on_local_disk_limit_keeps_job_resumable(self):
        c=config();c['years']=[2025];j=image_job(c)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('task_pipeline.local.verify_volume',return_value=root),patch('task_pipeline.local.generate_v2',side_effect=lambda c,b,m,s:iter([j]) if s==0 else iter([])),patch('task_pipeline.local.panels',return_value={}):
                code=run(c,root,{'01':{}},META,inventory=lambda j:dict(status='AVAILABLE',count=1),exporter=Mock(side_effect=OutputLimit('disk')))
            self.assertEqual(code,4)
            state=json.loads((root/'.local_state/state.json').read_text())
            self.assertEqual(state['jobs'][j['job_id']]['status'],'RETRY_PENDING')

    def test_verified_old_receiver_tiff_is_adopted_without_network(self):
        c=config();j=image_job(c)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dest=root/j['local_directory']/(j['prefix']+'.tif');dest.parent.mkdir(parents=True)
            t=j['tile']
            with rasterio.open(dest,'w',driver='GTiff',width=t['width'],height=t['height'],count=2,dtype='float64',
                crs=j['crs'],transform=Affine(*t['transform']),nodata=-9999) as ds:ds.write(np.ones((2,t['height'],t['width'])))
            md5,sha=hashes(dest)
            atomic_json(root/'.manifests'/f"{j['job_id']}.json",dict(job_id=j['job_id'],job=j,files=[dict(id='f',local_relative_path=str(dest.relative_to(root)),size=str(dest.stat().st_size),md5Checksum=md5)]))
            atomic_json(root/'.receipts'/f"{j['job_id']}.json",dict(volume_marker='test',files=[dict(id='f',verified=True,sha256=sha)]))
            self.assertEqual(prior(c,root,j)['sha256'],sha)

    def test_local_csv_is_published_and_reused_without_reexport(self):
        from province_pipeline.jobs import table_job
        c=config();c['years']=[2025]
        j=table_job(c,next(s for s in table_specs(c) if not s['night']),META)
        source=Mock(return_value=dict(status='AVAILABLE',count=1))
        calls=[]
        def write(config,root,job,boundary):
            calls.append(job['job_id'])
            row=dict(ma_tinh='01',nam=2025,period='2025-01',job_id=job['job_id'],
                valid_area=100,total_area=100,province_area=100,source_observations=3)
            for b in job['bands']:
                row.update({b+'_w':20,b+'_w2':5,b+'_sum':20,b+'_mean':.2,b+'_stdDev':.1})
            relative=job['local_directory']+'/'+job['prefix']+'.csv';dest=root/relative
            dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=list(row));writer.writeheader();writer.writerow(row)
            md5,sha=hashes(dest)
            proof=dict(job_id=job['job_id'],relative_path=relative,file=dict(size=str(dest.stat().st_size),md5Checksum=md5),sha256=sha)
            atomic_json(root/'.local_state/receipts'/(job['job_id']+'.json'),proof)
            return proof
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('task_pipeline.local.verify_volume',return_value=root),patch('task_pipeline.local.generate_v2',side_effect=lambda c,b,m,s:iter([j]) if s==1 else iter([])),patch('province_pipeline.auth.drive_credentials',side_effect=AssertionError('No Drive')):
                self.assertEqual(run(c,root,{'01':{}},META,inventory=source,exporter=write),0)
                self.assertEqual(run(c,root,{'01':{}},META,inventory=source,exporter=write),0)
            self.assertEqual(len(calls),1)
            path=root/'VN_LandCover_Panel_2004_2025/data_processed/day_indices.csv'
            with path.open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),12)
            self.assertEqual(rows[0]['MA_TINH'],'01');self.assertEqual(float(rows[0]['BLUE_mean']),.2)
            self.assertEqual(rows[1]['BLUE_mean'],'')
            self.assertEqual(json.loads((root/'branch_progress.json').read_text())['status'],'complete_with_gaps')

    def test_no_valid_pixels_is_recorded_once_without_stopping_remaining_jobs(self):
        from province_pipeline.quality import NoValidPixels
        c=config();c['years']=[2025];j=image_job(c)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('task_pipeline.local.verify_volume',return_value=root),patch('task_pipeline.local.generate_v2',side_effect=lambda c,b,m,s:iter([j]) if s==0 else iter([])),patch('task_pipeline.local.panels',return_value={}):
                self.assertEqual(run(c,root,{'01':{}},META,inventory=lambda j:dict(status='AVAILABLE',count=1),exporter=Mock(side_effect=NoValidPixels())),0)
            state=json.loads((root/'.local_state/state.json').read_text())
            self.assertEqual(state['jobs'][j['job_id']]['status'],'INSUFFICIENT_QUALITY')
            self.assertEqual(state['status'],'complete_with_gaps')
