"""Raw products must not acquire hidden filters or lose numerics at the 80% gate."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from ee import apitestcase
from province_pipeline.profiles import apply_profile,table_specs
from province_pipeline.jobs import table_job,generate_v2
from province_pipeline.panels import build_panels,archive_remote
from test_province_v2 import config, META,record

class RawGraphs(apitestcase.ApiTestCase):
    def setUp(self):
        import ee
        self.install=ee.data._install_cloud_api_resource
        super().setUp()
    def tearDown(self):
        import ee
        try:super().tearDown()
        finally:ee.data._install_cloud_api_resource=self.install

    def test_real_raw_graph_has_no_pipeline_cloud_fire_or_observation_filters(self):
        import ee
        from province_pipeline.processing import composite,statistics
        from province_pipeline.sources import SOURCES
        c=apply_profile(config(),'test_hanoi_2025','raw_source')
        for product in ('VIIRS_MONTHLY','SENTINEL2','LANDSAT','DMSP'):
            with self.subTest(product=product):
                spec=dict(province=next(table_specs(c))['province'],product=product,period='2025-01',night=product in ('VIIRS_MONTHLY','DMSP'))
                j=table_job(c,spec,META);j['inventory']=dict(asset_ids=[SOURCES[product]['collections'][0]+'/fixture'])
                geometry=ee.Geometry.Rectangle([105,21,105.1,21.1])
                image=composite(c,j,geometry);graph=statistics(image,j,geometry).serialize()
                for forbidden in ('CLOUD_SCORE_PLUS','MOD14A1','QA_PIXEL','QA_RADSAT','focalMin','cs_cdf'):
                    self.assertNotIn(forbidden,graph)
                self.assertIn('_valid_area',graph)

class RawTests(unittest.TestCase):
    def test_raw_identity_differs_and_low_coverage_is_kept_flagged(self):
        c=config();raw=apply_profile(c,c['run_profile'],'raw_source')
        spec=next(table_specs(c));old=table_job(c,spec,META);j=table_job(raw,spec,META)
        self.assertNotEqual(j['job_id'],old['job_id'])
        self.assertEqual(raw['algorithm_version'],'v003raw')
        r=record(j);r.update(valid_area=10,avg_rad_w=100,avg_rad_w2=1000)
        row=build_panels(raw,dict(jobs={},statistics={j['job_id']:r}),META)['night_indices.csv'][0]
        self.assertEqual(row['DATA_STATUS'],'OK_RAW')
        self.assertEqual(row['TNL'],10)
        self.assertIn('LOW_COVERAGE_REVIEW',row['QA_FLAGS'])

    def test_raw_quality_check_never_refilters_or_rejects_source_range(self):
        from province_pipeline.quality import reprocess_statistics
        c=apply_profile(config(),'test_hanoi_2025','raw_source')
        j=table_job(c,next(table_specs(c)),META)
        with patch('province_pipeline.processing.composite') as process:
            info=reprocess_statistics({'avg_rad_min':-1},j,None,c)
        process.assert_not_called();self.assertEqual(info['qc_status'],'RAW_UNFILTERED')
        self.assertEqual(info['avg_rad_min'],-1)

    def test_night_raw_only_generates_source_not_filtered_duplicate(self):
        c=apply_profile(config(),'test_hanoi_2025','raw_source')
        bounds={'01':dict(geometry=dict(type='Polygon',coordinates=[[[105,21],[105.01,21],[105.01,21.01],[105,21.01],[105,21]]]))}
        jobs=list(generate_v2(c,bounds,META,0))
        self.assertTrue(jobs);self.assertEqual({j['variant'] for j in jobs},{'source'})
        self.assertEqual({j['period'] for j in jobs},{f'2025-{m:02}' for m in range(1,13)})

    def test_band_with_no_valid_index_does_not_erase_optical_mean(self):
        from province_pipeline.aggregate import row_statistics
        row=dict(valid_area=100,total_area=100,BLUE_valid_area=100,BLUE_w=20,BLUE_w2=4,
                 NDVI_valid_area=0,NDVI_w=None,NDVI_w2=None)
        result=row_statistics(row,'SENTINEL2')
        self.assertAlmostEqual(result['BLUE_mean'],.2)
        self.assertNotEqual(result['NDVI_mean'],result['NDVI_mean'])

    def test_preview_reads_float_multiband_and_does_not_touch_tiff(self):
        import hashlib
        import rasterio
        import numpy as np
        from rasterio.transform import from_origin
        from province_pipeline.inspect_tiff import inspect
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.tif'
            with rasterio.open(path,'w',driver='GTiff',height=3,width=3,count=2,dtype='float32',nodata=-9999,
                               crs='EPSG:6933',transform=from_origin(1,1,500,500)) as ds:
                values=np.arange(18,dtype='float32').reshape(2,3,3);values[:,0,0]=-9999;ds.write(values)
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            report=inspect(path,Path(tmp)/'preview')
            self.assertTrue(report['has_valid_pixels']);self.assertEqual(report['bands'][0]['valid_pixels'],8)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
            with rasterio.open(Path(tmp)/'preview/source.png') as ds:
                self.assertEqual(ds.count,3);self.assertEqual(ds.dtypes,('uint8',)*3)
                self.assertGreater(ds.read().max(),0)

    def test_no_data_preview_reports_empty_instead_of_claiming_success(self):
        import rasterio
        import numpy as np
        from rasterio.transform import from_origin
        from province_pipeline.inspect_tiff import inspect
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'empty.tif'
            with rasterio.open(path,'w',driver='GTiff',height=2,width=2,count=1,dtype='float32',nodata=-9999,
                               transform=from_origin(1,1,500,500)) as ds:ds.write(np.full((1,2,2),-9999,dtype='float32'))
            report=inspect(path,Path(tmp)/'preview')
            self.assertFalse(report['has_valid_pixels']);self.assertEqual(report['bands'][0]['valid_pct'],0)

    def test_pending_rows_explain_they_have_not_been_calculated(self):
        row=build_panels(config(),{'jobs':{}},META)['night_indices.csv'][0]
        self.assertEqual(row['DATA_STATUS'],'PENDING');self.assertEqual(row['ERROR'],'NOT_CALCULATED_YET')

    def test_old_panels_are_archived_before_changing_method(self):
        import hashlib
        from test_province_pipeline import FakeDrive
        d=FakeDrive();d.folder=lambda parent,name:parent+'/'+name
        content=b'old values';sha=hashlib.sha256(content).hexdigest()
        old=dict(profile='test_hanoi_2025',method_version='v002',files=[dict(id='f',version='1',sha256=sha,local_relative_path='package/night_indices.csv')])
        d.documents['root/_control','panels.json']=old;d.files['f']=dict(version='1');d.read_bytes=lambda fid:content
        d.write_verified_bytes=Mock();d.find=Mock(return_value=None)
        archive_remote(config(),d,dict(profile='test_hanoi_2025',method_version='v003raw'))
        self.assertEqual(d.write_verified_bytes.call_args.args[2],content)

    def test_archived_panel_allows_recovery_after_partial_publish(self):
        import hashlib
        from test_province_pipeline import FakeDrive
        d=FakeDrive();d.folder=lambda parent,name:parent+'/'+name
        content=b'old verified';sha=hashlib.sha256(content).hexdigest()
        d.documents['root/_control','panels.json']=dict(profile='test_hanoi_2025',method_version='v002',
            files=[dict(id='old',version='1',sha256=sha,local_relative_path='package/night_indices.csv')])
        d.find=Mock(return_value=dict(id='backup'))
        d.read_bytes=Mock(return_value=content);d.metadata=Mock(side_effect=RuntimeError('mutable file already changed'))
        archive_remote(config(),d,dict(profile='test_hanoi_2025',method_version='v003raw'))
        d.metadata.assert_not_called()

    def test_empty_download_report_becomes_terminal_quality_failure(self):
        from province_pipeline.controller import reconcile
        from test_province_pipeline import FakeDrive
        d=FakeDrive();job=dict(job_id='j',status='RESERVED',export_backend='direct',attempt=1)
        state=dict(jobs={'j':job});d.documents['reports','j-a1.json']=dict(status='NO_VALID_PIXELS')
        reconcile(d,dict(reports='reports'),state,[])
        self.assertEqual(job['status'],'INSUFFICIENT_QUALITY')
        self.assertEqual(job['error'],'NO_VALID_PIXELS')
