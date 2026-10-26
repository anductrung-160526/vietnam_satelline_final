"""One TIFF per province/period: exact pixels, bounded requests, complete bundles."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
import numpy as np
import rasterio
from affine import Affine
from task_pipeline.province_image import download,small,grid,OutputLimit,ExportInterrupted
from task_pipeline.scope import configure
from province_pipeline.jobs import generate_v2
from province_pipeline.receiver import validate,hashes
from test_task123_branches import base,selection
from test_province_v2 import META
from test_province_pipeline import FakeDrive


def fixture(width=5,height=3):
    res=.01
    return dict(kind='image',job_id='whole',product='VIIRS_MONTHLY',period='2025-01',image_layout='province',
        scale=res*111319.49079327358,grid_resolution=res,dtype='float64',bands=['avg_rad'],chunk_pixels=2,
        crs='EPSG:4326',quality=dict(processing_mode='notebook_tasks'),reserved_bytes=1024**2,
        tile=dict(width=width,height=height,bounds=[105,20,105+width*res,20+height*res],
                  transform=[res,0,105,0,-res,20+height*res]))


def boundary(job):
    x0,y0,x1,y1=job['tile']['bounds']
    return dict(geometry=dict(type='Polygon',coordinates=[[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]]))


def fetcher(whole,calls):
    origin=Affine(*whole['tile']['transform'])
    def fetch(image,part,path):
        t=part['tile'];affine=Affine(*t['transform']);h,w=t['height'],t['width']
        col=round((affine.c-origin.c)/origin.a);row=round((affine.f-origin.f)/origin.e)
        values=100*np.arange(row,row+h)[:,None]+np.arange(col,col+w)[None,:]+.1234567890123
        calls.append((w,h))
        with rasterio.open(path,'w',driver='GTiff',width=w,height=h,count=1,dtype='float64',
                           crs=part['crs'],transform=affine,nodata=-9999) as ds:
            ds.write(values[None,:,:]);ds.set_band_description(1,'avg_rad')
    return fetch


class MosaicTests(unittest.TestCase):
    def test_small_province_is_one_direct_request_and_rectangular_tiff(self):
        j=fixture();calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'province.tif'
            result=download(None,j,path,boundary(j),{},fetcher(j,calls))
            self.assertEqual(result,dict(strategy='whole',requests=1));self.assertEqual(calls,[(5,3)])
            f=dict(size=str(path.stat().st_size),md5Checksum=hashes(path)[0])
            self.assertEqual(validate(path,f,j),hashes(path)[1])

    def test_streaming_chunks_match_whole_exactly_including_narrow_edges(self):
        j=fixture();calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'whole.tif'
            with patch('task_pipeline.province_image.small',return_value=False):
                result=download(None,j,path,boundary(j),{},fetcher(j,calls))
            self.assertEqual(result['requests'],6)
            self.assertIn((1,1),calls);self.assertIn((2,1),calls)
            with rasterio.open(path) as ds:
                expected=100*np.arange(3)[:,None]+np.arange(5)[None,:]+.1234567890123
                np.testing.assert_array_equal(ds.read(1),expected)
                self.assertEqual(ds.transform,Affine(*j['tile']['transform']))
                self.assertEqual(ds.dtypes,('float64',));self.assertEqual(ds.descriptions,('avg_rad',))
                self.assertEqual(ds.nodata,-9999)
            self.assertEqual([p.name for p in Path(tmp).iterdir()],['whole.tif'])

    def test_failed_chunk_never_leaves_partial_tiff(self):
        j=fixture();calls=[];real=fetcher(j,calls)
        def fail(image,part,path):
            if calls:raise RuntimeError('simulated lost connection')
            real(image,part,path)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'partial.tif'
            with patch('task_pipeline.province_image.small',return_value=False):
                with self.assertRaisesRegex(RuntimeError,'lost connection'):download(None,j,path,boundary(j),{},fail)
            self.assertFalse(path.exists())

    def test_size_failure_falls_back_but_permission_failure_does_not(self):
        j=fixture();calls=[];real=fetcher(j,calls);first=[True]
        def size(image,part,path):
            if first[0]:first[0]=False;raise RuntimeError('Total request size too large')
            real(image,part,path)
        with tempfile.TemporaryDirectory() as tmp:
            result=download(None,j,Path(tmp)/'ok.tif',boundary(j),{},size)
            self.assertEqual(result['strategy'],'internal_chunks')
            denied=Mock(side_effect=RuntimeError('permission denied'))
            with self.assertRaisesRegex(RuntimeError,'permission'):download(None,j,Path(tmp)/'bad.tif',boundary(j),{},denied)
            denied.assert_called_once()

    def test_deadline_and_quota_do_not_publish_partial_files(self):
        j=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'quota.tif'
            with self.assertRaises(ExportInterrupted):download(None,j,path,boundary(j),{'_task_deadline':0},Mock())
            j['reserved_bytes']=1
            with patch('task_pipeline.province_image.small',return_value=False):
                with self.assertRaises(OutputLimit):download(None,j,path,boundary(j),{},fetcher(j,[]))
            self.assertFalse(path.exists())

    def test_generator_has_exactly_one_image_per_province_period(self):
        c=configure(base(),selection());c['years']=[2025]
        b={'01':boundary(fixture())}
        for stage in (0,2):
            jobs=list(generate_v2(c,b,META,stage))
            self.assertEqual(len(jobs),12)
            self.assertEqual(len({(j['province']['ma_tinh'],j['period']) for j in jobs}),12)
            self.assertTrue(all(j['image_layout']=='province' and '_province_' in j['prefix'] for j in jobs))

    def test_reservation_changes_do_not_duplicate_scientific_outputs(self):
        c=configure(base(),selection());c['years']=[2025];b={'01':boundary(fixture())}
        j=next(generate_v2(c,b,META,0));c['drive_staging_budget_gib']=4
        other=next(generate_v2(c,b,META,0));self.assertEqual(j['job_id'],other['job_id'])
        self.assertFalse(j['preview_required'])
        from province_pipeline.profiles import in_scope
        self.assertTrue(in_scope(c,j));self.assertFalse(in_scope(c,dict(j,image_layout='chunk')))


class PreviewTests(unittest.TestCase):
    def test_night_preview_reveals_rare_lights_and_preserves_scientific_tiff(self):
        from province_pipeline.inspect_tiff import inspect
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'night.tif';data=np.zeros((1,100,100),dtype='float64');data[0,50,50]=50
            with rasterio.open(path,'w',driver='GTiff',width=100,height=100,count=1,dtype='float64',
                               nodata=-9999,transform=Affine(.01,0,105,0,-.01,21)) as ds:
                ds.write(data);ds.set_band_description(1,'avg_rad')
            checksum=hashes(path)[1];report=inspect(path,Path(tmp)/'preview')
            self.assertEqual(report['display'],'night_log1p_positive_99pct')
            png=Path(tmp)/'preview/night.png'
            with rasterio.open(png) as ds:
                self.assertEqual(ds.read(1)[50,50],255);self.assertEqual(ds.read(1)[0,0],0)
            self.assertEqual(hashes(path)[1],checksum)
            expected=dict(size=str(png.stat().st_size),md5Checksum=hashes(png)[0],role='preview')
            self.assertEqual(validate(png,expected,fixture()),hashes(png)[1])

    def test_manifest_requires_both_tiff_and_png_and_counts_total_bytes(self):
        from province_pipeline.controller import _remote_manifest
        d=FakeDrive();d.find=lambda parent,name:next((f for f in d.children(parent) if f['name']==name),None)
        j=dict(job_id='j',kind='image',preview_required=True,layout_version=3,prefix='province',
               folder_id='out',local_directory='data',reserved_bytes=100)
        d.files['t']=dict(id='t',name='province.tif',parents=['out'],mimeType='image/tiff',size='60',md5Checksum='t')
        self.assertIsNone(_remote_manifest(d,j))
        d.files['p']=dict(id='p',name='province.png',parents=['out'],mimeType='image/png',size='30',md5Checksum='p')
        manifest=_remote_manifest(d,j)
        self.assertEqual(len(manifest['files']),2);self.assertEqual(manifest['files'][1]['role'],'preview')
        d.files['p']['size']='50'
        with self.assertRaisesRegex(RuntimeError,'combined reservation'):_remote_manifest(d,j)

class BundleIntegrationTests(unittest.TestCase):
    def test_whole_tiff_is_received_without_creating_or_uploading_png(self):
        import os,hashlib
        from province_pipeline.direct_export import transfer
        from province_pipeline.controller import reconcile
        from province_pipeline.receiver import receive_manifest
        from province_pipeline.common import provinces
        from task_pipeline.province_image import download as real_download
        j=dict(fixture(),variant='source',prefix='hanoi_2025_01_province',preview_required=False,pipeline_version=2,
            layout_version=3,folder_id='data',local_directory='unused',province=provinces()[0],
            algorithm_version='v004tasks',priority=0,export_backend='direct',attempt=1,status='RESERVED')
        d=FakeDrive();d.find=lambda parent,name:next((f for f in d.children(parent) if f['name']==name),None)
        def upload(parent,path):
            fid=path.suffix.removeprefix('.')
            content=path.read_bytes()
            d.contents[fid]=content
            d.files[fid]=dict(id=fid,name=path.name,parents=[parent],version='1',
                mimeType='image/png' if fid=='png' else 'image/tiff',size=str(len(content)),
                md5Checksum=hashlib.md5(content).hexdigest())
            return fid
        d.upload_verified=upload
        def local_download(image,job,path,geometry,config):
            return real_download(image,job,path,geometry,config,fetcher(job,[]))
        cwd=Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch('ee.Geometry',return_value=None),patch('province_pipeline.earth_engine.composite',return_value=None),patch('task_pipeline.province_image.download',side_effect=local_download):
                    output=transfer({},d,j,boundary(j))
                d.documents['reports','whole-a1.json']=dict(status='UPLOADED',**output)
                state=dict(jobs={'whole':j})
                folders=dict(reports='reports',manifests='manifests',receipts='receipts')
                reconcile(d,folders,state,[])
                self.assertEqual(j['status'],'REMOTE_READY')
                manifest=d.documents['manifests','whole.json']
                self.assertEqual({f['id'] for f in manifest['files']},{'tif'})
                self.assertNotIn('preview',output)
                self.assertFalse(list(Path(tmp).rglob('*.png')))
                root=Path(tmp)/'E';root.mkdir()
                with patch('province_pipeline.receiver.verify_volume',return_value=root):
                    receive_manifest(dict(volume_marker='test',allow_remote_delete=True,drive_root_id='root'),
                                     d,folders,manifest,root)
                self.assertFalse(d.files)
                self.assertEqual(len(list(root.rglob('*.tif'))),1)
                self.assertEqual(len(list(root.rglob('*.png'))),0)
                self.assertTrue(d.documents['receipts','whole.json']['remote_deleted'])
            finally:os.chdir(cwd)

class TiffOnlyCompatibilityTests(unittest.TestCase):
    def test_completed_province_tiff_identity_does_not_change_when_disabling_png(self):
        from task_pipeline.province_image import output_job
        from province_pipeline.jobs import table_job
        from province_pipeline.profiles import table_specs
        c=configure(base(),selection());spec=next(table_specs(c))
        job=output_job(c,table_job(c,spec,META),[105,20,105.1,20.1],0)
        self.assertEqual(job['job_id'],'c44d370c6267bf363665d4fd1ad78a8c')
        self.assertFalse(job['preview_required'])

    def test_existing_unsubmitted_bundle_reservation_is_changed_to_tiff_only(self):
        from province_pipeline.priority import prepare_priority
        c=configure(base(),selection());c['years']=[2025]
        bounds={'01':boundary(fixture())};j=next(generate_v2(c,bounds,META,0))
        j.update(status='RESERVED',preview_required=True,folder_id='data',folder_name='data',attempt=1)
        d=FakeDrive();d.folder=lambda p,n:p+'/'+n;d.usage=lambda root:0;d.account_free=lambda:2**40
        d.documents['root/_control','state.json']=dict(jobs={j['job_id']:j},inventory={},cursor=0,layout_version=3)
        plan=prepare_priority(c,d,bounds,META,lambda j:dict(status='UNAVAILABLE',count=0))
        pending=next(job for job in plan['jobs'] if job['job_id']==j['job_id'])
        self.assertFalse(pending['preview_required'])


class LargeDayChunkTests(unittest.TestCase):
    def test_day_jobs_use_large_windows_without_changing_identity(self):
        from task_pipeline import province_image
        from task_pipeline.province_image import output_job,DAY_TIFF_BANDS
        base=dict(product='SENTINEL2',period='2025-01',province=dict(ma_tinh='01',slug='ha_noi'),
                  bands=DAY_TIFF_BANDS,algorithm_version='v',recipe_hash='abcdef0123')
        config=dict(crs='EPSG:4326',tile_pixels=512,drive_staging_budget_gib=10,high_watermark=.6)
        job=output_job(config,base,[105,20,105.5,20.5],2)
        self.assertEqual(job['chunk_pixels'],1280)
        self.assertLess(1280*1280*len(DAY_TIFF_BANDS)*2,32_000_000)
        with patch.object(province_image,'chunk_pixels',lambda c,b,d:c['tile_pixels']):
            old=output_job(config,base,[105,20,105.5,20.5],2)
        self.assertEqual(old['chunk_pixels'],512);self.assertEqual(job['job_id'],old['job_id'])
        night=output_job(config,dict(base,product='VIIRS_MONTHLY',bands=['avg_rad']),[105,20,105.5,20.5],0)
        self.assertEqual(night['chunk_pixels'],512)

    def test_rejected_large_window_is_split_into_identical_pixels(self):
        j=dict(fixture(9,7),chunk_pixels=8);calls=[];real=fetcher(j,calls);rejected=[]
        def fetch(image,part,path):
            t=part['tile']
            if t['width']*t['height']>9:
                rejected.append((t['width'],t['height']));raise RuntimeError('User memory limit exceeded')
            real(image,part,path)
        with tempfile.TemporaryDirectory() as tmp,patch('task_pipeline.province_image.MIN_CHUNK',1):
            path=Path(tmp)/'split.tif'
            with patch('task_pipeline.province_image.small',return_value=False):
                result=download(None,j,path,boundary(j),{},fetch)
            with rasterio.open(path) as ds:
                expected=100*np.arange(7)[:,None]+np.arange(9)[None,:]+.1234567890123
                np.testing.assert_array_equal(ds.read(1),expected)
        self.assertIn((8,7),rejected);self.assertEqual(result['requests'],len(calls))
        self.assertTrue(all(w*h<=9 for w,h in calls))

    def test_other_failures_are_not_split(self):
        j=dict(fixture(9,7),chunk_pixels=8);calls=[]
        def fetch(image,part,path):
            calls.append(1);raise RuntimeError('Permission denied')
        with tempfile.TemporaryDirectory() as tmp:
            with patch('task_pipeline.province_image.small',return_value=False):
                with self.assertRaisesRegex(RuntimeError,'Permission'):
                    download(None,j,Path(tmp)/'x.tif',boundary(j),{},fetch)
        self.assertEqual(len(calls),1)
