"""Branch invariants, supplied notebook methods and long-running province execution."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from datetime import datetime
from ee import apitestcase
from task_pipeline.scope import RANGES,scope,provinces,configure,PROJECT
from task_pipeline.methods import dates,source_spec
from province_pipeline.jobs import table_job,generate_v2
from province_pipeline.profiles import table_specs
from test_province_v2 import META


def base():
    c=json.loads(Path('province_pipeline/config/example.json').read_text())
    c.update(project=PROJECT,drive_root_id='root',drive_staging_budget_gib=18.6,drive_safety_margin_gib=1.8)
    return c


def selection(start=1,end=11,mode='pilot'):
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'range.json';path.write_text(json.dumps(dict(start=start,end=end)))
        return scope(mode,path,ref=f'vngis-tinh-{start:03}-{end:03}')


class ScopeTests(unittest.TestCase):
    def test_all_sixty_three_numbers_are_covered_exactly_once(self):
        numbers=[i for start,end in RANGES for i in range(start,end+1)]
        self.assertEqual(numbers,list(range(1,64)))
        self.assertEqual([end-start+1 for start,end in RANGES],[11,11,11,10,10,10])
        self.assertEqual(len({p['gid_1'] for p in provinces()}),63)

    def test_each_pilot_is_the_first_whole_province(self):
        for start,end in RANGES:
            s=selection(start,end)
            self.assertEqual([p['number'] for p in s['provinces']],[start])
            self.assertEqual(len(selection(start,end,'full')['provinces']),end-start+1)

    def test_scope_cannot_be_overridden_by_a_wrong_branch(self):
        with self.assertRaisesRegex(ValueError,'Branch name'):
            scope('pilot',ref='main')
        with self.assertRaises(ValueError):scope('all')

    def test_project_and_period_remain_fixed(self):
        c=configure(base(),selection())
        self.assertEqual(c['project'],'vngis-ee-soc-trang-yen-bai');self.assertEqual(c['years'],list(range(2004,2026)))
        self.assertEqual(c['province_codes'],['01']);self.assertEqual(c['crs'],'EPSG:4326')
        with self.assertRaisesRegex(ValueError,'existing project'):
            configure(dict(base(),project='angelic-digit-434804-r9'),selection())

    def test_full_reuses_first_province_pilot_job_identity(self):
        pilot=configure(base(),selection());full=configure(base(),selection(mode='full'))
        spec=next(table_specs(pilot))
        self.assertEqual(table_job(pilot,spec,META)['job_id'],table_job(full,spec,META)['job_id'])

    def test_task_one_strict_month_table_and_task_two_monthly_images(self):
        c=configure(base(),selection());c['years']=[2025]
        bounds={'01':dict(geometry=dict(type='Polygon',coordinates=[[[105,21],[105.01,21],[105.01,21.01],[105,21.01],[105,21]]]))}
        tables=list(generate_v2(c,bounds,META,1));day=list(generate_v2(c,bounds,META,2))
        self.assertEqual(len(tables),24)
        self.assertEqual({j['scale'] for j in tables if j['product']=='SENTINEL2'},{50})
        self.assertEqual({j['period'] for j in day},{f'2025-{m:02}' for m in range(1,13)})
        self.assertTrue(all(j['crs']=='EPSG:4326' and j['grid_resolution']<1 for j in day))

    def test_notebook_collection_and_dates_are_explicit(self):
        self.assertEqual(source_spec('SENTINEL2','2018-01')['collections'],['COPERNICUS/S2_HARMONIZED'])
        self.assertEqual(source_spec('SENTINEL2','2019-01')['collections'],['COPERNICUS/S2_SR_HARMONIZED'])
        self.assertEqual(dates('2024-02'),('2024-02-01','2024-02-29'))
        self.assertEqual(dates('2025-01',15),('2024-12-17','2025-02-15'))

    def test_notebook_night_formulas_match_sample_not_population_model(self):
        from province_pipeline.panels import quantitative,base_row
        c=configure(base(),selection());spec=next(s for s in table_specs(c) if s['product']=='VIIRS_MONTHLY')
        job=table_job(c,spec,META);row=base_row(c,spec)
        record=dict(valid_area=100,total_area=100,province_area=100,avg_rad_w=1000,avg_rad_w2=11000,
            avg_rad_sum=100,avg_rad_mean=10,avg_rad_stdDev=2,avg_rad_min=0,avg_rad_max=50,
            lit_pixels=4,notebook_valid_pixels=20,notebook_lit_pop_proxy=30,source_observations=2.345)
        quantitative(row,record,job)
        self.assertEqual(row['DATA_STATUS'],'OK_NOTEBOOK')
        self.assertEqual(row['LIT_AREA_HA'],100);self.assertEqual(row['ELECTRIFICATION_RATIO_PCT'],20)
        self.assertEqual(row['LIT_POP_PROXY'],30);self.assertEqual(row['SPATIAL_CV'],.2)
        self.assertEqual(row['CLOUD_FREE_OBS'],2.3)


class GraphTests(apitestcase.ApiTestCase):
    def setUp(self):
        import ee
        self.install=ee.data._install_cloud_api_resource
        super().setUp()
    def tearDown(self):
        import ee
        try:super().tearDown()
        finally:ee.data._install_cloud_api_resource=self.install

    def test_all_four_sources_build_with_sdk_and_notebook_reducers(self):
        import ee
        from task_pipeline.methods import composite,statistics
        c=configure(base(),selection())
        for product,period,night in [('SENTINEL2','2025-01',False),('LANDSAT','2005-01',False),('DMSP','2005',True),('VIIRS_MONTHLY','2025-01',True)]:
            with self.subTest(product=product):
                spec=dict(product=product,period=period,night=night,province=provinces()[0])
                j=table_job(c,spec,META);j['inventory']=dict(asset_ids=[source_spec(product,period)['collections'][0]+'/fixture'])
                g=ee.Geometry.Rectangle([105,21,105.1,21.1]);im=composite(c,j,g)
                graph=statistics(im,j,g).serialize()
                if not night:self.assertIn('Image.reduceRegions',graph)
                if product=='SENTINEL2':
                    self.assertIn('QA60',graph);self.assertIn('CLOUDY_PIXEL_PERCENTAGE',graph)
                    self.assertIn('normalizedDifference',graph)
                if product=='VIIRS_MONTHLY':self.assertIn('1.5',graph)
                self.assertIn('EPSG:4326',graph)

    def test_supplied_notebook_mask_and_indices_are_equivalent_graphs(self):
        import ast
        import ee
        from task_pipeline.methods import s2_mask,indices
        nb=json.loads(Path('notebooks/task123/Task1-GEO_Spectral_Indices.ipynb').read_text())
        functions=[]
        for cell in nb['cells']:
            if cell['cell_type']!='code':continue
            try:tree=ast.parse(''.join(cell['source']))
            except SyntaxError:continue
            functions.extend(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('mask_s2_sr','add_indices'))
        ns={'ee':ee};exec(compile(ast.Module(body=functions,type_ignores=[]),'notebook-functions','exec'),ns)
        image=ee.Image('COPERNICUS/S2_SR_HARMONIZED/fixture')
        # Compare exact mask/band/scaling graph; expression whitespace differs only in BSI.
        self.assertEqual(s2_mask(image).serialize(),ns['mask_s2_sr'](image).serialize())
        actual=indices(s2_mask(image)).serialize();expected=ns['add_indices'](ns['mask_s2_sr'](image)).serialize()
        self.assertEqual(''.join(actual.split()),''.join(expected.split()))


class RunnerTests(unittest.TestCase):
    def test_many_batches_share_one_runner_without_workflow_redispatch(self):
        from task_pipeline.runner import run
        from test_province_pipeline import FakeDrive
        c=configure(base(),selection());d=FakeDrive();d.folder=lambda p,n:p+'/'+n;d.find=lambda p,n:None
        d.documents['root/_control','state.json']=dict(jobs={},current_stage='night_images')
        n=[0]
        def plan(*args):
            n[0]+=1
            d.documents['root/_control','state.json']['current_stage']='complete' if n[0]==3 else 'indices_csv'
            return dict(jobs=[] if n[0]==3 else [dict(province=dict(group_id=0),job_id=str(n[0]))])
        transfer=Mock()
        with tempfile.TemporaryDirectory() as tmp,patch('task_pipeline.runner.prepare_priority',side_effect=plan),patch('task_pipeline.runner.reconcile_existing'),patch('task_pipeline.runner.publish'),patch('task_pipeline.runner.atomic_json'),patch('task_pipeline.runner.STOP',False):
            code=run(c,d,{},META,max_seconds=1000,transfer=transfer,clock=lambda:0)
        self.assertEqual(code,0);self.assertEqual(transfer.call_count,2);self.assertEqual(n[0],3)

    def test_cloud_priority_admission_sees_whole_group_instead_of_one_province(self):
        from task_pipeline.runner import run
        from test_province_pipeline import FakeDrive
        c=configure(base(),selection(mode='full'));d=FakeDrive()
        d.folder=lambda p,n:p+'/'+n;d.find=lambda p,n:None
        d.documents['root/_control','state.json']=dict(jobs={},current_stage='night_images')
        seen=[]
        def plan(active,*args):
            seen.append(active['province_codes'])
            d.documents['root/_control','state.json']['current_stage']='complete'
            return dict(jobs=[])
        with patch('task_pipeline.runner.prepare_priority',side_effect=plan),patch('task_pipeline.runner.publish'),patch('task_pipeline.runner.atomic_json'):
            self.assertEqual(run(c,d,{},META,clock=lambda:0),0)
        self.assertEqual(seen,[c['province_codes']])
        self.assertEqual(d.documents['root/_control','branch_progress.json']['completed_provinces'],list(range(1,12)))

    def test_budget_is_six_shares_and_accounts_for_existing_data(self):
        from task_pipeline.runner import resolve
        from test_province_pipeline import FakeDrive
        d=FakeDrive();d.folder=lambda p,n:p+'/'+n
        d.files['old']=dict(id='old',name='old.tif',parents=['root'],size=str(1024**3),mimeType='image/tiff')
        c=configure(base(),selection());resolved=resolve(c,d)
        self.assertAlmostEqual(resolved['drive_staging_budget_gib'],(18.6-1)/6)
        self.assertEqual(c['project'],resolved['project'])
        self.assertTrue(resolved['drive_root_id'].endswith('Task123_branches/001_011'))

class DeliveryTests(unittest.TestCase):
    def test_exact_geographic_tile_validates_metre_scale_and_degree_grid(self):
        import rasterio,numpy as np
        from affine import Affine
        from province_pipeline.receiver import hashes,validate
        resolution=20/111319.49079327358
        transform=Affine(resolution,0,105,0,-resolution,21)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'geo.tif'
            with rasterio.open(path,'w',driver='GTiff',height=2,width=2,count=1,dtype='float32',
                               nodata=-9999,crs='EPSG:4326',transform=transform) as ds:
                ds.write(np.ones((1,2,2),dtype='float32'))
            job=dict(kind='image',bands=['BLUE'],crs='EPSG:4326',scale=20,grid_resolution=resolution,
                     tile=dict(bounds=[105,21-2*resolution,105+2*resolution,21],transform=list(transform)[:6]))
            f=dict(size=str(path.stat().st_size),md5Checksum=hashes(path)[0])
            self.assertEqual(validate(path,f,job),hashes(path)[1])

    def test_drive_exact_lookup_is_server_filtered_and_rejects_duplicates(self):
        from province_pipeline.drive import Drive
        d=Drive.__new__(Drive);d.api=Mock();d.execute=Mock(return_value=dict(files=[dict(id='x')]))
        self.assertEqual(d.find('parent','state.json'),{'id':'x'})
        query=d.api.files.return_value.list.call_args.kwargs['q']
        self.assertIn("name = 'state.json'",query);self.assertIn("'parent' in parents",query)
        d.execute.return_value=dict(files=[dict(id='x'),dict(id='y')])
        with self.assertRaisesRegex(RuntimeError,'Ambiguous'):d.find('parent','state.json')

    def test_windows_receiver_keeps_processing_other_branches_after_one_fails(self):
        from task_pipeline.receiver import receive
        from test_province_pipeline import FakeDrive
        d=FakeDrive()
        def find(parent,name):
            return dict(id=name)
        d.find=find
        with tempfile.TemporaryDirectory() as tmp,patch('task_pipeline.receiver.verify_volume',return_value=Path(tmp)),patch(
                'task_pipeline.receiver.run',side_effect=[RuntimeError('one branch failed'),None,None,None,None,None]) as receiver:
            with self.assertRaisesRegex(RuntimeError,'Some branch receivers failed'):
                receive(dict(local_root=tmp,drive_root_id='root'),d)
        self.assertEqual(receiver.call_count,6)

    def test_lossless_compression_preserves_double_pixels_grid_and_bands(self):
        import rasterio,numpy as np
        from rasterio.transform import from_origin
        from province_pipeline.direct_export import lossless_tiff
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'double.tif';data=np.array([[[.1234567890123,2],[3,-9999]]],dtype='float64')
            transform=from_origin(105,21,.0002,.0002)
            with rasterio.open(path,'w',driver='GTiff',height=2,width=2,count=1,dtype='float64',
                               nodata=-9999,crs='EPSG:4326',transform=transform) as ds:
                ds.write(data);ds.set_band_description(1,'RED')
            lossless_tiff(path)
            with rasterio.open(path) as ds:
                np.testing.assert_array_equal(ds.read(),data)
                self.assertEqual(ds.dtypes,('float64',));self.assertEqual(ds.transform,transform)
                self.assertEqual(ds.descriptions,('RED',));self.assertEqual(ds.nodata,-9999)
