"""Direct-to-E mode: shared packages, per-branch control, night -> day -> local stages."""
import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch,Mock
import numpy as np
import rasterio
import pandas as pd
from affine import Affine
from task_pipeline.scope import configure
from task_pipeline.local import run,export,prior
from task_pipeline.province_image import output_job,OutputLimit
from task_pipeline import raw
from province_pipeline.jobs import table_job,generate_v2
from province_pipeline.profiles import table_specs
from province_pipeline.common import atomic_json,provinces
from province_pipeline.receiver import hashes
from test_task123_branches import base,selection
from test_province_v2 import META


def config(mode='pilot'):
    c=configure(base(),selection(mode=mode))
    c.update(execution_backend='local',volume_marker='test')
    return c


def image_job(c):
    spec=next(s for s in table_specs(c) if s['period']=='2025-01' and s['night'])
    return output_job(c,table_job(c,spec,META),[105,20,105.01,20.01],0)


def square(c):
    return {'geometry':dict(type='Polygon',coordinates=[[[105,20],[105.01,20],[105.01,20.01],[105,20.01],[105,20]]])}


def fake_download(image,job,path,boundary,config):
    t=job['tile']
    with rasterio.open(path,'w',driver='GTiff',width=t['width'],height=t['height'],count=len(job['bands']),
        dtype=job['dtype'],crs=job['crs'],transform=Affine(*t['transform']),nodata=-9999) as ds:
        ds.write(np.ones((len(job['bands']),t['height'],t['width'])).astype(job['dtype']))
    return dict(strategy='whole',requests=1)


def runner(c,root,source,jobs,exporter=export,local=None):
    local=local or Mock(return_value=0)
    with patch('task_pipeline.local.verify_volume',return_value=root):
        code=run(c,root,{p['ma_tinh']:square(c) for p in c['task_scope']['provinces']},META,inventory=source,
                 exporter=exporter,control=root/'_control/001_011',job_source=jobs,local=local)
    return code,local


class RawJobTests(unittest.TestCase):
    def test_sources_and_years_follow_the_plan(self):
        p=provinces()[0]
        night=Counter(s['product'] for s in raw.specs(p,raw.NIGHT))
        self.assertEqual(night,{'DMSP':10,'VIIRS_MONTHLY':13*12,'VIIRS_ANNUAL_EOG':13})
        day=list(raw.specs(p,raw.DAY))
        self.assertEqual(Counter(s['product'] for s in day),{'LANDSAT':11*12,'SENTINEL2':11*12})
        self.assertEqual({s['period'][:4] for s in day if s['product']=='LANDSAT'},{str(y) for y in range(2004,2015)})
        self.assertEqual(min(s['period'] for s in day if s['product']=='SENTINEL2'),'2015-01')

    def test_night_identity_matches_earlier_releases(self):
        c=config();boundary={'01':square(c)}
        old={(j['product'],j['period']):j['job_id'] for j in generate_v2(c,boundary,META,0)}
        new={(j['product'],j['period']):j['job_id'] for j in raw.jobs(c,boundary,META,raw.NIGHT,c['task_scope']['provinces'][0])}
        shared=set(old)&set(new)
        self.assertGreater(len(shared),100)
        self.assertTrue(all(old[k]==new[k] for k in shared))

    def test_day_jobs_are_int16_six_bands_twenty_metres(self):
        c=config()
        jobs=list(raw.jobs(c,{'01':square(c)},META,raw.DAY,c['task_scope']['provinces'][0]))
        s2=next(j for j in jobs if j['product']=='SENTINEL2');ls=next(j for j in jobs if j['product']=='LANDSAT')
        self.assertEqual((s2['dtype'],len(s2['bands']),s2['scale']),('int16',6,20))
        self.assertEqual(ls['scale'],30);self.assertTrue(s2['prefix'].endswith('_sr6'))
        self.assertTrue(s2['local_directory'].startswith('VN_LandCover_Panel_2004_2025/raw_data/DAY/SENTINEL2/01_ha_noi'))


class LocalTests(unittest.TestCase):
    def test_night_then_day_for_every_province_then_local_stages(self):
        c=config('full');c['task_scope']['provinces']=c['task_scope']['provinces'][:2]
        c['province_codes']=[p['ma_tinh'] for p in c['task_scope']['provinces']]
        template=image_job(c);visited=[]
        def jobs(active,boundaries,metadata,kind,province):
            visited.append((kind,province['ma_tinh']))
            job=copy.deepcopy(template);job['job_id']=f"{kind}-{province['ma_tinh']}";job['province']['ma_tinh']=province['ma_tinh']
            return iter([job])
        source=Mock(return_value=dict(status='UNAVAILABLE',count=0))
        with tempfile.TemporaryDirectory() as tmp:
            code,local=runner(c,Path(tmp),source,jobs)
            self.assertEqual(code,0)
            self.assertEqual(visited,[(k,p) for k in ('night','day') for p in c['province_codes']])
            local.assert_called_once()
            state=json.loads((Path(tmp)/'_control/001_011/.local_state/state.json').read_text())
            self.assertEqual(Counter(j['status'] for j in state['jobs'].values()),{'MISSING_SOURCE':4})

    def test_night_failure_stops_before_day_and_local_stages(self):
        c=config();j=image_job(c);visited=[]
        def jobs(active,boundaries,metadata,kind,province):
            visited.append(kind);return iter([j])
        with tempfile.TemporaryDirectory() as tmp:
            code,local=runner(c,Path(tmp),Mock(side_effect=RuntimeError('network')),jobs)
        self.assertEqual(code,2);self.assertEqual(visited,['night']);local.assert_not_called()

    def test_image_goes_to_shared_package_and_restart_uses_receipt(self):
        c=config();j=image_job(c)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);control=root/'_control/001_011'
            with patch('task_pipeline.local.verify_volume',return_value=root),patch('task_pipeline.methods.composite'),\
                 patch('ee.Geometry'),patch('task_pipeline.local.province_image.download',side_effect=fake_download):
                proof=export(c,root,control,j,square(c))
                self.assertEqual(prior(c,root,control,j)['sha256'],proof['sha256'])
            dest=root/proof['relative_path']
            self.assertTrue(dest.exists());self.assertTrue(proof['relative_path'].startswith('VN_NTL_Panel_2004_2025/raw_data/NTL/VIIRS/01_ha_noi/'))
            self.assertTrue((control/'.local_state/receipts'/f"{j['job_id']}.json").exists())
            self.assertEqual(list((control/'.work').iterdir()),[])
            log=(root/'VN_NTL_Panel_2004_2025/logs/nhat_ky_cap_nhat.txt').read_text(encoding='utf-8')
            self.assertIn('Ngày cập nhật | Người thực hiện',log);self.assertIn('| VIIRS |',log)
            with rasterio.open(dest) as ds:self.assertEqual(ds.tags()['WINDOW_DAYS'],'0')

    def test_untracked_valid_file_is_adopted_and_invalid_one_is_never_overwritten(self):
        c=config();j=image_job(c)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);control=root/'_control/001_011'
            dest=root/j['local_directory']/(j['prefix']+'.tif');dest.parent.mkdir(parents=True)
            dest.write_bytes(b'user file')
            with patch('task_pipeline.local.verify_volume',return_value=root):
                self.assertIsNone(prior(c,root,control,j))
                with self.assertRaisesRegex(RuntimeError,'refusing overwrite'):export(c,root,control,j,square(c))
            self.assertEqual(dest.read_bytes(),b'user file')
            dest.unlink();fake_download(None,j,dest,None,c)
            info=prior(c,root,control,j)
            self.assertTrue(info['adopted']);self.assertEqual(info['sha256'],hashes(dest)[1])
            self.assertTrue((control/'.local_state/receipts'/f"{j['job_id']}.json").exists())

    def test_failed_download_leaves_no_output_or_receipt(self):
        c=config();j=image_job(c)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);control=root/'_control/001_011'
            with patch('task_pipeline.local.verify_volume',return_value=root),patch('task_pipeline.methods.composite'),\
                 patch('ee.Geometry'),patch('task_pipeline.local.province_image.download',side_effect=RuntimeError('network')):
                with self.assertRaisesRegex(RuntimeError,'network'):export(c,root,control,j,square(c))
            self.assertFalse(list(root.rglob('*.tif')))

    def test_missing_source_recorded_once_and_reused(self):
        c=config();j=image_job(c);source=Mock(return_value=dict(status='UNAVAILABLE',count=0))
        jobs=lambda a,b,m,kind,p:iter([j]) if kind=='night' else iter([])
        with tempfile.TemporaryDirectory() as tmp,patch('province_pipeline.auth.drive_credentials',side_effect=AssertionError('No Drive')):
            self.assertEqual(runner(c,Path(tmp),source,jobs)[0],0)
            self.assertEqual(runner(c,Path(tmp),source,jobs)[0],0)
            state=json.loads((Path(tmp)/'_control/001_011/.local_state/state.json').read_text())
        self.assertEqual(source.call_count,1)
        self.assertEqual(state['jobs'][j['job_id']]['status'],'MISSING_SOURCE');self.assertEqual(state['status'],'complete_with_gaps')

    def test_disk_limit_pauses_and_keeps_job_resumable(self):
        c=config();j=image_job(c)
        jobs=lambda a,b,m,kind,p:iter([j]) if kind=='night' else iter([])
        with tempfile.TemporaryDirectory() as tmp:
            code,local=runner(c,Path(tmp),lambda job:dict(status='AVAILABLE',count=1),jobs,exporter=Mock(side_effect=OutputLimit('disk')))
            state=json.loads((Path(tmp)/'_control/001_011/.local_state/state.json').read_text())
        self.assertEqual(code,4);local.assert_not_called()
        self.assertEqual(state['jobs'][j['job_id']]['status'],'RETRY_PENDING')

    def test_no_valid_pixels_recorded_without_stopping(self):
        from province_pipeline.quality import NoValidPixels
        c=config();j=image_job(c)
        jobs=lambda a,b,m,kind,p:iter([j]) if kind=='night' else iter([])
        with tempfile.TemporaryDirectory() as tmp:
            code,local=runner(c,Path(tmp),lambda job:dict(status='AVAILABLE',count=1),jobs,exporter=Mock(side_effect=NoValidPixels()))
            state=json.loads((Path(tmp)/'_control/001_011/.local_state/state.json').read_text())
        self.assertEqual(code,0);local.assert_called_once()
        self.assertEqual(state['jobs'][j['job_id']]['status'],'INSUFFICIENT_QUALITY')

    def test_verified_old_receiver_tiff_is_adopted(self):
        c=config();j=image_job(c)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);control=root/'_control/001_011'
            dest=root/j['local_directory']/(j['prefix']+'.tif');dest.parent.mkdir(parents=True)
            fake_download(None,j,dest,None,c);md5,sha=hashes(dest)
            rel=str(dest.relative_to(root).as_posix())
            atomic_json(control/'.manifests'/f"{j['job_id']}.json",dict(job_id=j['job_id'],job=j,files=[dict(id='f',local_relative_path=rel,size=str(dest.stat().st_size),md5Checksum=md5)]))
            atomic_json(control/'.receipts'/f"{j['job_id']}.json",dict(volume_marker='test',files=[dict(id='f',verified=True,sha256=sha)]))
            self.assertEqual(prior(c,root,control,j)['sha256'],sha)


class RangeTests(unittest.TestCase):
    def test_one_checkout_can_run_every_range_with_its_own_project(self):
        from task_pipeline.local import selection_for,RANGE_PROJECTS
        from task_pipeline.scope import RANGES
        self.assertEqual(set(RANGE_PROJECTS),set(RANGES))
        s=selection_for('full','54-63')
        self.assertEqual([p['number'] for p in s['provinces']],list(range(54,64)))
        self.assertEqual(RANGE_PROJECTS[(54,63)],'vgis-ee-6')
        with self.assertRaises(ValueError):selection_for('full','50-63')


class EndToEndTests(unittest.TestCase):
    def test_full_local_flow_for_one_province(self):
        from task_pipeline.local import local_stages
        c=config();boundaries={'01':square(c)}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('task_pipeline.local.verify_volume',return_value=root),patch('task_pipeline.methods.composite'),\
                 patch('ee.Geometry'),patch('task_pipeline.local.province_image.download',side_effect=fake_download),\
                 patch('province_pipeline.quality.inspect_raster',return_value=dict(valid_pixel_pct=100,flags=[])):
                code=run(c,root,boundaries,META,inventory=lambda j:dict(status='AVAILABLE',count=1,window_days=0,collections=['x']),
                         control=root/'_control/001_011')
            self.assertEqual(code,0)
            ntl=root/'VN_NTL_Panel_2004_2025';day=root/'VN_LandCover_Panel_2004_2025'
            self.assertEqual(len(list((day/'raw_data/DAY/SENTINEL2/01_ha_noi').glob('*_sr6.tif'))),132)
            self.assertEqual(len(list((ntl/'data_intermediate/VIIRS_MONTHLY/01_ha_noi').glob('*.tif'))),156)
            self.assertEqual(len(list((day/'data_intermediate/annual_composite/LANDSAT/01_ha_noi').glob('*.tif'))),11)
            annual=pd.read_csv(ntl/'data_processed/ntl_annual.csv',dtype={'ma_tinh':str})
            self.assertEqual(list(annual['nam']),list(range(2004,2026)))
            monthly=pd.read_csv(day/'data_processed/day_indices_monthly.csv',dtype={'ma_tinh':str})
            self.assertEqual(len(monthly),264);self.assertTrue((monthly['trang_thai'].str.startswith('OK')).all())
            progress=json.loads((root/'_control/001_011/branch_progress.json').read_text())
            self.assertEqual(progress['landcover'],'PENDING_SAMPLES')
            before=sorted(p.stat().st_mtime_ns for p in (ntl/'data_intermediate').rglob('*.tif'))
            with patch('task_pipeline.local.verify_volume',return_value=root):
                self.assertEqual(run(c,root,boundaries,META,inventory=Mock(side_effect=AssertionError('no EE on resume')),control=root/'_control/001_011'),0)
            self.assertEqual(sorted(p.stat().st_mtime_ns for p in (ntl/'data_intermediate').rglob('*.tif')),before)


if __name__=='__main__':
    unittest.main()
