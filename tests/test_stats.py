"""Monthly Earth Engine indices: job list, rows, resume, retries and CSV merge (no EE calls)."""
import csv
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from task_pipeline import stats

HN=dict(ma_tinh='01',ten_tinh='Hà Nội')


class StatsTests(unittest.TestCase):
    def test_periods_follow_the_data_plan(self):
        self.assertEqual(len(stats.periods('LANDSAT')),22*12)
        self.assertEqual(stats.periods('LANDSAT')[0],'2004-01');self.assertEqual(stats.periods('LANDSAT')[-1],'2025-12')
        self.assertEqual(len(stats.periods('SENTINEL2')),11*12);self.assertEqual(stats.periods('SENTINEL2')[0],'2015-01')
        self.assertEqual(len(stats.periods('VIIRS')),13*12);self.assertEqual(stats.periods('DMSP'),[str(y) for y in range(2004,2014)])
        self.assertEqual({p:stats.SOURCES[p][1] for p in stats.SOURCES},dict(LANDSAT=30,SENTINEL2=10,VIIRS=500,DMSP=1000))

    def test_day_row(self):
        v={'n_scenes':3,'NDVI_mean':.5,'NDVI_stdDev':.1,'NDBI_mean':-.2,'NDBI_stdDev':.1,'MNDWI_mean':-.3,
           'MNDWI_stdDev':.2,'BSI_mean':-.1,'BSI_stdDev':.05,'valid_m2':75.,'total_m2':100.,'tile_scale':4}
        r=stats.row('SENTINEL2','2020-05',HN,3359.8,v)
        self.assertEqual((r['status'],r['nam'],r['thang'],r['scale_m'],r['ty_le_pixel_hop_le']),('OK',2020,5,10,75.0))
        self.assertEqual(stats.row('LANDSAT','2005-01',HN,1,{'n_scenes':0,'tile_scale':4})['status'],'NO_SCENES')
        self.assertEqual(stats.row('LANDSAT','2005-01',HN,1,dict(v,NDVI_mean=None))['status'],'NO_VALID_PIXELS')
        self.assertEqual(stats.row('LANDSAT','2005-01',HN,1,{'error':'x'})['status'],'FAILED')

    def test_night_row_density(self):
        v={'n_images':1,'rad_sum':1000.,'rad_mean':2.,'rad_count':500,'lit_sol':900.,'lit_pixels':300,'source_collection':'VCMSLCFG','tile_scale':4}
        r=stats.row('VIIRS','2020-05',HN,500.,v)
        self.assertEqual((r['sol_ntl'],r['mat_do_ntl'],r['thang'],r['lit_threshold']),(1000.,2.,5,1.5))
        d=stats.row('DMSP','2010',HN,500.,dict(v,source_collection='F182010'))
        self.assertEqual((d['thang'],d['scale_m'],d['lit_threshold']),(0,1000,None))
        self.assertEqual(stats.row('VIIRS','2013-01',HN,1,{'n_images':0})['status'],'NO_IMAGES')

    def test_resume_ignores_torn_lines_and_retries_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.jsonl'
            ok=dict(ma_tinh='01',nguon_anh='VIIRS',period='2020-01',status='OK')
            bad=dict(ma_tinh='01',nguon_anh='VIIRS',period='2020-02',status='FAILED')
            p.write_text(json.dumps(ok)+'\n'+json.dumps(bad)+'\n{"ma_tinh": "01", "ngu',encoding='utf-8')
            self.assertEqual(set(stats.load_done(p)),{('01','VIIRS','2020-01')})

    def test_merge_builds_csvs_and_year_on_year_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Path(tmp)/'_control'/'stats';store.mkdir(parents=True)
            rows=[stats.row('VIIRS',per,HN,100.,{'n_images':1,'rad_sum':s,'tile_scale':4}) for per,s in (('2019-05',100.),('2020-05',150.),('2020-06',80.))]
            rows+=[stats.row('DMSP',y,HN,100.,{'n_images':1,'rad_sum':s,'tile_scale':4}) for y,s in (('2009',50.),('2010',40.))]
            rows.append(stats.row('LANDSAT','2005-01',HN,100.,{'n_scenes':0,'tile_scale':4}))
            (store/'night_1_11.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows[:5]),encoding='utf-8')
            (store/'day_1_11.jsonl').write_text(json.dumps(rows[5])+'\n',encoding='utf-8')
            self.assertEqual(stats.merge(tmp),(1,5))
            with open(Path(tmp)/'VN_NTL_Panel_2004_2025'/'data_processed'/'ntl_indices_ee.csv',encoding='utf-8-sig') as f:
                ntl={(r['nguon_anh'],r['period']):r for r in csv.DictReader(f)}
            self.assertAlmostEqual(float(ntl['VIIRS','2020-05']['thay_doi_ntl']),50.0)
            self.assertEqual(ntl['VIIRS','2020-06']['thay_doi_ntl'],'')
            self.assertAlmostEqual(float(ntl['DMSP','2010']['thay_doi_ntl']),-20.0)
            self.assertEqual(ntl['VIIRS','2020-05']['mat_do_ntl'],'1.5')
            self.assertTrue((Path(tmp)/'VN_LandCover_Panel_2004_2025'/'data_processed'/'day_indices_monthly_ee.csv').exists())

    def test_compute_escalates_tile_scale_then_retries_transient(self):
        ee=types.SimpleNamespace(EEException=type('EEException',(Exception,),{}))
        seen=[]
        class Req:
            def __init__(self,ts):self.ts=ts
            def getInfo(self):
                seen.append(self.ts)
                if len(seen)==1:raise ee.EEException('Computation timed out.')
                if len(seen)==2:raise ee.EEException('Too many concurrent aggregations.')
                return {'n_images':1,'rad_sum':1.}
        with patch.dict('sys.modules',{'ee':ee}),patch.object(stats,'night_request',lambda p,per,g,ts,th:Req(ts)),\
             patch.object(stats.time,'sleep',lambda s:None):
            out=stats.compute('VIIRS','2020-01',HN,None,5)
        self.assertEqual(seen,[4,8,8]);self.assertEqual(out['tile_scale'],8)

    def test_compute_gives_up_on_permanent_error(self):
        ee=types.SimpleNamespace(EEException=type('EEException',(Exception,),{}))
        class Req:
            def getInfo(self):raise ee.EEException('Permission denied for project')
        with patch.dict('sys.modules',{'ee':ee}),patch.object(stats,'day_request',lambda p,per,g,ts:Req()),\
             patch.object(stats.time,'sleep',lambda s:None):
            out=stats.compute('LANDSAT','2020-01',HN,None,5)
        self.assertIn('Permission',out['error'])
