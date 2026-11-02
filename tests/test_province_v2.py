"""Fixed-source panels, priority barriers, safe snapshots and real EE graph construction."""
import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from collections import Counter
from province_pipeline.profiles import apply_profile,table_specs,source_for
from province_pipeline.jobs import table_job,generate_v2
from province_pipeline.panels import build_panels,csv_bytes,temporal,quantitative,sync
from province_pipeline.priority import prepare_priority
from province_pipeline.common import provinces
from province_pipeline.sources import SOURCES
from test_province_pipeline import FakeDrive

META=dict(sha256='boundary',source='test boundary',version='1',date='2024-01-01',code_reference='verified')

def config(profile='test_hanoi_2025'):
    return apply_profile(dict(drive_root_id='root',pause=False,season_months=[1,2,3,4,11,12],
        drive_staging_budget_gib=18.6,drive_safety_margin_gib=1.8,high_watermark=.65,low_watermark=.3),profile)

def record(job,value=10):
    band='avg_rad' if job['product']=='VIIRS_MONTHLY' else 'stable_lights'
    return dict(ma_tinh=job['province']['ma_tinh'],period=job['period'],job_id=job['job_id'],
        total_area=100,valid_area=100,province_area=100,source_observations=3,
        **{band+'_w':value*100,band+'_w2':value**2*100,band+'_sum':value,band+'_min':value,band+'_max':value},
        lit_pixels=1,lit_area=100)

class ProfilePanelTests(unittest.TestCase):
    def test_default_test_has_twelve_months_each_exact_sources(self):
        specs=list(table_specs(config()))
        self.assertEqual(len(specs),24)
        self.assertEqual(Counter(s['product'] for s in specs),{'VIIRS_MONTHLY':12,'SENTINEL2':12})
        self.assertEqual({s['province']['ma_tinh'] for s in specs},{'01'})
        self.assertEqual({s['period'] for s in specs},{f'2025-{m:02}' for m in range(1,13)})

    def test_full_exact_expected_rows_and_sources(self):
        counts=Counter((s['night'],s['product']) for s in table_specs(config('full_2004_2025')))
        self.assertEqual(counts,{(True,'DMSP'):630,(True,'VIIRS_MONTHLY'):9072,
                                 (False,'LANDSAT'):8316,(False,'SENTINEL2'):8316})

    def test_identity_stable_when_switching_profile(self):
        c=config();s=next(table_specs(c))
        self.assertEqual(table_job(c,s,META)['job_id'],table_job(config('full_2004_2025'),s,META)['job_id'])

    def test_missing_source_never_uses_other_source_record(self):
        c=config();s=next(s for s in table_specs(c) if not s['night']);job=table_job(c,s,META)
        state=dict(jobs={job['job_id']:dict(status='MISSING_SOURCE')},statistics={'foreign':record(job)})
        panels=build_panels(c,state,META)
        row=panels['day_indices.csv'][0]
        self.assertEqual(row['SOURCE'],'SENTINEL2')
        self.assertEqual(row['DATA_STATUS'],'MISSING_SOURCE')
        self.assertNotIn('BLUE_mean',row)
        content=csv_bytes('day_indices.csv',panels['day_indices.csv']).decode('utf-8-sig')
        parsed=list(csv.DictReader(io.StringIO(content)))
        self.assertEqual(parsed[0]['BLUE_mean'],'')
        self.assertEqual(len(parsed),12)

    def test_low_coverage_is_null_not_zero(self):
        c=config();s=next(table_specs(c));j=table_job(c,s,META);r=record(j)
        r['valid_area']=10
        p=build_panels(c,dict(jobs={},statistics={j['job_id']:r}),META)['night_indices.csv'][0]
        self.assertEqual(p['DATA_STATUS'],'INSUFFICIENT_QUALITY')
        self.assertNotIn('TNL',p)

    def test_province_natural_area_density_and_sample_metrics(self):
        c=config();s=next(table_specs(c));j=table_job(c,s,META)
        row=build_panels(c,dict(jobs={},statistics={j['job_id']:record(j)}),META)['night_indices.csv'][0]
        self.assertEqual(row['GID_1'],'VNM.27_1')
        self.assertEqual(row['TNL'],10)
        self.assertEqual(row['MEAN_RAD'],10)
        self.assertEqual(row['STD_RAD'],0)
        self.assertEqual(row['MAT_DO_NTL'],100000)
        self.assertNotIn('LIT_POP_PROXY',row)
        self.assertEqual(row['CALIBRATION_STATUS'],'NOT_CALIBRATED')

    def test_monthly_missing_breaks_windows_and_growth(self):
        rows=[dict(MA_TINH='01',YEAR=2025,MONTH=m,TIME=f'2025-{m:02}',FREQUENCY='monthly',SOURCE='VIIRS',
                   DATA_STATUS='OK' if m!=2 else 'MISSING_SOURCE',TNL=10 if m!=2 else None,
                   SOL_NTL=10 if m!=2 else None,MAT_DO_NTL=1,QA_FLAGS='') for m in range(1,13)]
        temporal(rows)
        self.assertIsNone(rows[2].get('TNL_MA3'))
        self.assertIsNone(rows[2].get('TNL_MOM_GROWTH_PCT'))
        self.assertNotIn('SOL_YEAR',rows[0])
        self.assertEqual(rows[0]['VALID_MONTHS_YEAR'],11)

    def test_no_growth_crosses_annual_monthly_transition(self):
        rows=[dict(MA_TINH='01',YEAR=2013,MONTH=None,TIME='2013',FREQUENCY='annual',SOURCE='DMSP',
                   DATA_STATUS='OK',TNL=100,SOL_NTL=100,MAT_DO_NTL=1,QA_FLAGS=''),
              dict(MA_TINH='01',YEAR=2014,MONTH=1,TIME='2014-01',FREQUENCY='monthly',SOURCE='VIIRS',
                   DATA_STATUS='OK',TNL=10,SOL_NTL=10,MAT_DO_NTL=1,QA_FLAGS='')]
        temporal(rows)
        self.assertIsNone(rows[1].get('TNL_MOM_GROWTH_PCT'))
        self.assertIsNone(rows[1].get('TNL_YOY_GROWTH_PCT'))

    def test_annual_viiirs_mean_not_sum_and_repeated_fields(self):
        rows=[dict(MA_TINH='01',YEAR=2025,MONTH=m,TIME=f'2025-{m:02}',FREQUENCY='monthly',SOURCE='VIIRS',
                   DATA_STATUS='OK',TNL=10,SOL_NTL=10,MAT_DO_NTL=1,QA_FLAGS='') for m in range(1,13)]
        temporal(rows)
        self.assertEqual(rows[0]['SOL_YEAR'],10)
        self.assertEqual(rows[0]['VALID_MONTHS_YEAR'],12)
        self.assertEqual(rows[2]['TNL_MA3'],10)

    def test_generated_day_image_is_annual_and_has_native_grid(self):
        bounds={'01':dict(geometry=dict(type='Polygon',coordinates=[[[105,21],[105.01,21],[105.01,21.01],[105,21.01],[105,21]]]))}
        jobs=list(generate_v2(config(),bounds,META,2))
        self.assertTrue(jobs)
        self.assertEqual({j['period'] for j in jobs},{'2025'})
        self.assertEqual({j['scale'] for j in jobs},{20})
        self.assertTrue(all(j['local_directory'].endswith('/01_ha_noi') for j in jobs))

class QueueTests(unittest.TestCase):
    def fixture(self):
        d=FakeDrive();d.folder=lambda parent,name:parent+'/'+name
        d.usage=lambda root:0;d.account_free=lambda:2**40
        d.documents['root/_control','state.json']=dict(jobs={},inventory={},cursor=0,layout_version=3)
        return d

    def jobs(self,priority):
        c=config('full_2004_2025')
        out=[]
        for group in range(10):
            p=next(p for p in provinces() if p['group_id']==group)
            spec=dict(province=p,product='VIIRS_MONTHLY',period='2025-01',night=True)
            j=table_job(c,spec,META);j.update(priority=priority,job_id=f'{priority}-{group}')
            out.append(j)
        return out

    def test_priority_barrier_and_all_ten_groups_admitted(self):
        d=self.fixture()
        with patch('province_pipeline.priority.fair_jobs',side_effect=lambda c,b,m,p,cursor:iter(self.jobs(p))):
            plan=prepare_priority(config('full_2004_2025'),d,{},META,lambda j:dict(status='AVAILABLE',count=1))
        self.assertEqual({j['priority'] for j in plan['jobs']},{0})
        self.assertEqual({j['province']['group_id'] for j in plan['jobs']},set(range(10)))

    def test_missing_source_persisted_and_no_substitution(self):
        d=self.fixture()
        with patch('province_pipeline.priority.fair_jobs',side_effect=lambda c,b,m,p,cursor:iter(self.jobs(p)[:1])):
            plan=prepare_priority(config('full_2004_2025'),d,{},META,lambda j:dict(status='UNAVAILABLE',count=0))
        self.assertFalse(plan['jobs'])
        self.assertEqual(d.documents['root/_control','state.json']['jobs']['0-0']['status'],'MISSING_SOURCE')

    def test_completed_night_stage_advances_to_day_images(self):
        d=self.fixture()
        for j in self.jobs(0):
            d.documents['root/_control','state.json']['jobs'][j['job_id']]=dict(j,status='FAILED')
        with patch('province_pipeline.priority.fair_jobs',side_effect=lambda c,b,m,p,cursor:iter(self.jobs(p))):
            plan=prepare_priority(config('full_2004_2025'),d,{},META,lambda j:dict(status='AVAILABLE',count=1))
        self.assertEqual({j['priority'] for j in plan['jobs']},{2})

    def test_inventory_calls_bounded(self):
        d=self.fixture();c=config('full_2004_2025');c['max_inventory_checks_per_cycle']=2
        callback=Mock(return_value=dict(status='UNAVAILABLE',count=0))
        with patch('province_pipeline.priority.fair_jobs',side_effect=lambda c,b,m,p,cursor:iter(self.jobs(p))):
            prepare_priority(c,d,{},META,callback)
        self.assertEqual(callback.call_count,2)

class ContinuationTests(unittest.TestCase):
    def test_stops_on_capacity_or_complete_or_limit(self):
        from province_pipeline.continuation import decision
        self.assertEqual(decision(dict(jobs={},waiting_for_space=True),20),'DRIVE_CAPACITY')
        self.assertEqual(decision(dict(jobs={},current_stage='complete'),20),'COMPLETE')
        self.assertEqual(decision(dict(jobs={}),1),'CYCLE_LIMIT')
        self.assertIsNone(decision(dict(jobs={}),2))
        with self.assertRaises(ValueError):decision(dict(jobs={}),21)

from ee import apitestcase

class EarthEngineGraphTests(apitestcase.ApiTestCase):
    def setUp(self):
        import ee
        self.original_install=ee.data._install_cloud_api_resource
        super().setUp()

    def tearDown(self):
        import ee
        try:
            super().tearDown()
        finally:
            ee.data._install_cloud_api_resource=self.original_install

    def test_quality_composites_and_statistics_serialize_with_real_sdk(self):
        import ee
        from province_pipeline.processing import composite,statistics
        c=config('full_2004_2025')
        examples=[(2005,True),(2017,False),(2025,True),(2025,False)]
        for year,night in examples:
            with self.subTest(year=year,night=night):
                product=source_for(year,night)
                spec=dict(province=provinces()[0],period=str(year) if product=='DMSP' else f'{year}-01',
                          product=product,night=night)
                job=table_job(c,spec,META)
                job['inventory']=dict(asset_ids=[SOURCES[product]['collections'][0]+'/example'])
                geometry=ee.Geometry.Rectangle([105,21,105.1,21.1])
                image=composite(c,job,geometry)
                serialized=statistics(image,job,geometry).serialize()
                self.assertIn('Image.reduceRegion',serialized)
                if product=='SENTINEL2':
                    self.assertIn('CLOUD_SCORE_PLUS',serialized)
                if night:
                    self.assertIn('MOD14A1',serialized)

    def test_monthly_day_collection_does_not_use_dry_season_filter(self):
        import ee
        from province_pipeline.earth_engine import collection
        monthly=collection(config(),'SENTINEL2','2025-08',ee.Geometry.Point([105,21])).serialize()
        annual=collection(config(),'SENTINEL2','2025',ee.Geometry.Point([105,21])).serialize()
        self.assertNotIn('Filter.listContains',monthly)
        self.assertIn('Filter.listContains',annual)

class QualityTests(unittest.TestCase):
    def test_same_source_strict_reprocessing_is_bounded(self):
        from province_pipeline.quality import reprocess_statistics
        c=config();spec=next(s for s in table_specs(c) if not s['night']);job=table_job(c,spec,META)
        bad={'BLUE_max':2.0}
        good={'BLUE_max':.9}
        image=Mock();stats=Mock();stats.first.return_value.toDictionary.return_value.getInfo.return_value=good
        with patch('province_pipeline.processing.composite',return_value=image) as build,patch('province_pipeline.processing.statistics',return_value=stats):
            result=reprocess_statistics(bad,job,'geometry',c)
        rebuilt=build.call_args.args[1]
        self.assertEqual(rebuilt['product'],'SENTINEL2')
        self.assertEqual(rebuilt['period'],job['period'])
        self.assertEqual(result['qc_attempts'],2)
        self.assertEqual(result['qc_status'],'REPROCESSED_STRICT_MASK')
        build.assert_called_once()

    def test_reprocessing_still_bad_is_insufficient_not_fallback(self):
        from province_pipeline.quality import reprocess_statistics
        c=config();spec=next(s for s in table_specs(c) if not s['night']);job=table_job(c,spec,META)
        stats=Mock();stats.first.return_value.toDictionary.return_value.getInfo.return_value={'RED_max':3}
        with patch('province_pipeline.processing.composite'),patch('province_pipeline.processing.statistics',return_value=stats):
            result=reprocess_statistics({'RED_max':3},job,'geometry',c)
        self.assertEqual(result['qc_status'],'INSUFFICIENT_QUALITY')

class SnapshotTests(unittest.TestCase):
    def fixture(self,root,version='1'):
        import hashlib
        d=FakeDrive();panels=build_panels(config(),dict(jobs={}),META)
        content=csv_bytes('night_indices.csv',panels['night_indices.csv'])
        f=dict(id='panel',version='1',md5Checksum=hashlib.md5(content).hexdigest(),size=str(len(content)),
               sha256=hashlib.sha256(content).hexdigest(),rows=12,
               local_relative_path='VN_NTL_Panel_2004_2025/data_processed/night_indices.csv')
        d.documents['control','panels.json']=dict(profile='test_hanoi_2025',files=[f])
        d.files['panel']=dict(f,version=version);d.contents['panel']=content
        dest=Path(root)/f['local_relative_path'];dest.parent.mkdir(parents=True);dest.write_text('old verified panel')
        return d,dest

    def test_verified_snapshot_can_replace_older_consolidated_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            d,dest=self.fixture(tmp)
            sync({},d,Path(tmp),'control')
            with dest.open(encoding='utf-8-sig') as stream:rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),12)
            self.assertTrue((Path(tmp)/'.panels.json').exists())
            self.assertFalse(any(e[0]=='delete' for e in d.events))

    def test_changed_drive_version_preserves_old_local_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            d,dest=self.fixture(tmp,version='2')
            with self.assertRaisesRegex(RuntimeError,'Panel changed'):sync({},d,Path(tmp),'control')
            self.assertEqual(dest.read_text(),'old verified panel')

    def test_wrong_checksum_preserves_old_local_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            d,dest=self.fixture(tmp);d.contents['panel']=b'wrong'
            with self.assertRaisesRegex(ValueError,'checksum'):sync({},d,Path(tmp),'control')
            self.assertEqual(dest.read_text(),'old verified panel')

class StageIntegrationTests(unittest.TestCase):
    def test_hanoi_twelve_months_finishes_all_stages_without_duplicate_jobs(self):
        bounds={'01':dict(geometry=dict(type='Polygon',coordinates=[[[105,21],[105.01,21],[105.01,21.01],[105,21.01],[105,21]]]))}
        c=config();d=FakeDrive();d.folder=lambda parent,name:parent+'/'+name
        d.usage=lambda root:0;d.account_free=lambda:2**40
        observed=[];seen=set()
        with patch('province_pipeline.controller.reconcile'):
            for _ in range(20):
                plan=prepare_priority(c,d,bounds,META,lambda j:dict(status='AVAILABLE',count=1,asset_ids=['fixture']))
                state=d.documents['root/_control','state.json']
                for job in plan['jobs']:
                    self.assertNotIn(job['job_id'],seen)
                    seen.add(job['job_id']);observed.append(job['priority'])
                    state['jobs'][job['job_id']]['status']='DELETED_REMOTE'
                if state['current_stage']=='complete':break
        self.assertEqual(state['current_stage'],'complete')
        order={0:0,2:1,1:2}  # night images -> day images -> tables
        self.assertEqual(observed,sorted(observed,key=order.get))
        tables=[j for j in state['jobs'].values() if j['kind']=='table']
        self.assertEqual(len(tables),24)

    def test_real_round_robin_does_not_drain_first_group(self):
        from province_pipeline.priority import fair_jobs
        from itertools import islice
        c=config('full_2004_2025')
        first=list(islice(fair_jobs(c,{},META,1,3),10))
        self.assertEqual([j['province']['group_id'] for j in first],[3,4,5,6,7,8,9,0,1,2])

    def test_image_qc_flags_are_scientific_not_silent_pixel_replacement(self):
        import rasterio
        import numpy as np
        from rasterio.transform import from_origin
        from province_pipeline.quality import inspect_raster
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'tile.tif'
            with rasterio.open(path,'w',driver='GTiff',height=2,width=2,count=1,dtype='float32',
                               nodata=-9999,crs='EPSG:6933',transform=from_origin(1,1,1,1)) as ds:
                ds.write(np.full((1,2,2),10,dtype='float32'))
            qa=inspect_raster(path,dict(product='DMSP',variant='filtered',bands=['stable_lights']))
            self.assertIn('CONSTANT_TILE_REVIEW',qa['flags'])
            self.assertEqual(qa['valid_pixel_pct'],100)
            with rasterio.open(path) as ds:self.assertTrue((ds.read()==10).all())
