"""P1: kết quả biết trước, miền chung, lưới khác, tái lập và xuất bản không phá dữ liệu."""
import json
from pathlib import Path
import sqlite3

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box,mapping
from fastapi.testclient import TestClient

from test_fractional_and_repair import raster
from backend.data.fractional_area import ProvinceAreas
from backend.data.spatial_analysis import queen_neighbors,global_moran,compare_rasters,displacement
from backend.data.build_spatial import build
from backend.data.dataset import migrate_demo,file_signature,make_snapshot
from backend.api.main import app


def test_queen_edges_corner_gaps_island_and_row_weights():
    neighbors=queen_neighbors({'a':box(0,0,1,1),'b':box(1,0,2,1),'c':box(2,1,3,2),'d':box(20,0,21,1)},0)
    assert neighbors=={'a':['b'],'b':['a','c'],'c':['b'],'d':[]}
    assert queen_neighbors({'a':box(0,0,1,1),'b':box(1.5,0,2,1)},.4)['a']==[]
    assert queen_neighbors({'a':box(0,0,1,1),'b':box(1.5,0,2,1)},.5)['a']==['b']


def test_moran_known_clustering_dispersion_permutations_and_exclusions():
    graph={'a':['b'],'b':['a','c'],'c':['b','d'],'d':['c']}
    clustered=global_moran(dict(a=0,b=0,c=2,d=2),graph,999,42)
    assert clustered['moran_i']==pytest.approx(.5)
    assert clustered['expected_i']==pytest.approx(-1/3)
    assert clustered==global_moran(dict(a=0,b=0,c=2,d=2),graph,999,42)
    assert 1/1000<=clustered['p_value']<=1
    assert global_moran(dict(a=0,b=2,c=0,d=2),graph,999,42)['moran_i']==pytest.approx(-1)
    assert global_moran(dict.fromkeys(graph,0),graph,99)['status']=='zero_variance'
    graph['island']=[];graph['missing']=['d'];graph['d'].append('missing')
    partial=global_moran(dict(a=0,b=0,c=2,d=2,island=10),graph,99)
    assert partial['status']=='partial' and partial['n']==4
    assert partial['excluded']=={'missing':'missing_or_unverified_value','island':'no_observed_neighbor'}
    assert global_moran({'a':0},graph,99)['moran_i'] is None


def area_model(polygon):
    from rasterio.warp import transform_geom
    return ProvinceAreas({'01':{'geometry':transform_geom('EPSG:6933','EPSG:4326',mapping(polygon))}}, {'sha256':'test'})


def test_six_changes_partition_and_transition_matrix(tmp_path):
    a,b=tmp_path/'a.tif',tmp_path/'b.tif'
    raster(a,[[0,2,0],[2,2,5]]);raster(b,[[0,2,2],[0,5,2]])
    model=area_model(box(0,0,3000,2000))
    summary,classes,delta,_=compare_rasters(a,b,'01',model,[.5,1.5,3,10])
    assert classes.tolist()==[[0,1,2],[3,4,5]]
    assert summary['change_areas_km2']==pytest.approx([1]*6)
    assert summary['common_area_km2']==pytest.approx(6)
    assert sum(r['area_km2'] for r in summary['transitions'])==pytest.approx(6)
    assert summary['lit_net_km2']==pytest.approx(0)
    assert delta.tolist()==[[0,0,2],[-2,3,-3]]


def test_missing_is_not_dark_and_fractional_border_is_not_full_pixel(tmp_path):
    a,b=tmp_path/'a.tif',tmp_path/'b.tif'
    raster(a,[[0,-9999,4],[2,2,-9999]])
    raster(b,[[0,2,-9999],[-9999,0,-9999]])
    model=area_model(box(500,0,2500,2000))
    summary,classes,delta,_=compare_rasters(a,b,'01',model,[.5,1.5,3,10])
    assert classes.tolist()==[[0,255,255],[255,3,255]]
    assert delta[0,0]==0 and delta[0,1]==-9999
    assert summary['common_area_km2']==pytest.approx(1.5)
    assert summary['change_areas_km2'][0]==pytest.approx(.5)
    assert summary['start_only_area_km2']==pytest.approx(1)
    assert summary['end_only_area_km2']==pytest.approx(1)
    assert summary['neither_area_km2']==pytest.approx(.5)


def test_nearest_grid_alignment_and_common_domain_centroid_east(tmp_path):
    a,b=tmp_path/'a.tif',tmp_path/'b.tif'
    raster(a,[[10,0]],transform=from_origin(0,1000,1000,1000))
    raster(b,[[0,0,10,10],[0,0,10,10]],transform=from_origin(0,1000,500,500))
    summary,classes,delta,_=compare_rasters(a,b,'01',area_model(box(0,0,2000,1000)),[.5,1.5,3,20])
    assert summary['grid_reprojected']
    assert classes.tolist()==[[3,3,2,2],[3,3,2,2]]
    assert summary['direction']=='Đông' and summary['centroid_shift_km']>0
    assert summary['centroid_bearing_deg']==pytest.approx(90,abs=.001)
    assert summary['lit_gain_km2']==pytest.approx(1)
    assert summary['lit_loss_km2']==pytest.approx(1)
    assert displacement(None,summary['centroid_end'])['direction'] is None


def test_no_common_data_and_no_weighted_light_give_null_not_fake_direction(tmp_path):
    a,b=tmp_path/'a.tif',tmp_path/'b.tif'
    raster(a,[[0,-9999]]);raster(b,[[-9999,10]])
    result,classes,delta,_=compare_rasters(a,b,'01',area_model(box(0,1000,2000,2000)),[.5,1.5,3,20])
    assert result['status']=='no_common_observations' and result['common_area_km2']==0
    assert result['centroid_shift_km'] is None and result['mean_radiance_change'] is None
    assert (classes==255).all() and (delta==-9999).all()


@pytest.fixture
def spatial_fixture(tmp_path,monkeypatch):
    polygons={f'{i+1:02}':box(i*2000,0,(i+1)*2000,2000) for i in range(4)}
    from rasterio.warp import transform_geom
    model=ProvinceAreas({c:{'geometry':transform_geom('EPSG:6933','EPSG:4326',mapping(p))} for c,p in polygons.items()}, {'sha256':'p1_fixture'})
    db=tmp_path/'app.db';csv=tmp_path/'ntl_annual.csv';csv.write_text('year,sol\n2020,10\n',encoding='utf-8')
    snapshot=make_snapshot(tmp_path,9);sid=snapshot['dataset_id']
    with sqlite3.connect(db) as connection:
        migrate_demo(connection)
        connection.executescript('''CREATE TABLE province(province_code TEXT PRIMARY KEY,province_name TEXT);
        CREATE TABLE ntl_annual(province_code TEXT,year INTEGER,source TEXT,sol REAL,sol_density REAL,area_km2 REAL);''')
        connection.execute('INSERT INTO demo_dataset VALUES(?,?,?)',(sid,str(tmp_path),json.dumps(snapshot)))
        connection.execute("INSERT INTO demo_schema_meta VALUES('current_dataset',?)",(sid,))
        for index,(code,polygon) in enumerate(polygons.items()):
            connection.execute('INSERT INTO province VALUES(?,?)',(code,'Test '+code))
            for year in (2020,2021):
                path=tmp_path/f'{code}_{year}.tif'
                raster(path,[[index+1,2],[0,4+index+(year-2020)*3]],transform=from_origin(index*2000,2000,1000,1000))
                sig=file_signature(path,True)
                sol=index+7+index+(year-2020)*3
                check=dict(source=sig,export=sig,masked_copy=False,mask_rule='test',boundary_sha256='p1_fixture',statistics={'sol':sol})
                connection.execute('INSERT INTO demo_asset VALUES(?,?,?,?,?,?,?)',(code,year,0,'processed',str(path),'VIIRS','[]'))
                connection.execute('INSERT INTO demo_asset_check VALUES(?,?,?,?,?)',(code,year,0,'processed',json.dumps(check)))
                connection.execute('INSERT INTO demo_provenance VALUES(?,?,?,?,?,?,?)',(code,year,0,'ntl_annual','',sid,str(path)))
                connection.execute('INSERT INTO ntl_annual VALUES(?,?,?,?,?,?)',(code,year,'VIIRS',sol,sol/4,4))
                connection.execute('INSERT INTO light_class_summary VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (code,year,0,4,'test',4,0,4,100,2,50,0,'OK',2020,'test_fixed','[]'))
                bounds=[0,.5,1.5,3,10,None]
                for i in range(5):connection.execute('INSERT INTO light_class VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (code,year,0,i,bounds[i],bounds[i+1],1,'OK','nW/cm²/sr','VIIRS'))
    report=tmp_path/'integration_report.json';report.write_text(json.dumps(dict(dataset_id=sid,published=True,outside_valid_values_after=0)),encoding='utf-8')
    monkeypatch.setenv('VNGIS_DB',str(db))
    return tmp_path,db,report,model


def test_build_publish_export_guards_and_no_overwrite_of_f(spatial_fixture):
    root,db,report,model=spatial_fixture
    result=build(root,report,db,2020,2021,99,7,publish=True,area_model=model,expected_count=4)
    assert result['published'] and result['complete_pairs']==4 and Path(result['backup']).exists()
    assert all(r['n']==4 for r in result['moran'])
    client=TestClient(app);data=client.get('/api/spatial?year_start=2020&year_end=2021').json()
    assert data['status']=='ready' and data['run_id']==result['run_id']
    params=dict(year_start=2020,year_end=2021,kind='change',province_code='01',expected_snapshot=result['dataset_id'],run_id=result['run_id'])
    response=client.get('/api/spatial/file',params=params)
    assert response.status_code==404
    moran=client.get('/api/spatial/file',params=dict(params,kind='moran'))
    assert moran.status_code==200 and moran.content.decode('utf-8-sig').splitlines()[0]=='year,moran_i'
    assert set(data['moran'][0])=={'year','moran_i'}
    with rasterio.open(result['files']['01_delta']['path']) as image:
        assert image.nodata==-9999 and image.descriptions==('radiance_end_minus_start',)
        assert image.tags()['DATASET_ID']==result['dataset_id']
    assert client.get('/api/spatial/file',params=dict(params,run_id='old')).status_code==409
    assert client.get('/api/spatial/file',params=dict(params,kind='../app.db')).status_code==400
    assert client.get('/api/spatial?year_start=2022&year_end=2024').json()['status']=='missing'
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE demo_schema_meta SET value='newer_dataset' WHERE key='current_dataset'")
    assert client.get('/api/spatial?year_start=2020&year_end=2021').json()['status']=='stale'
    assert client.get('/api/spatial/file',params=params).status_code==409
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE demo_schema_meta SET value=? WHERE key='current_dataset'",(result['dataset_id'],))
    # Đổi nguồn giữ nguyên snapshot cũng phải vô hiệu hóa kết quả P1.
    Path(result['source_signatures'][0]['path']).unlink()
    assert client.get('/api/spatial?year_start=2020&year_end=2021').json()['status']=='stale'
    assert client.get('/api/spatial/file',params=params).status_code!=200
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT COUNT(*) FROM ntl_annual').fetchone()[0]==8
        assert connection.execute("SELECT value FROM demo_schema_meta WHERE key='version'").fetchone()[0]=='2'


def test_invalid_pair_or_different_thresholds_never_publish(spatial_fixture):
    root,db,report,model=spatial_fixture
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE light_class SET lower_bound=4 WHERE province_code='01' AND year=2021 AND class_index=3")
    before=db.read_bytes()
    with pytest.raises(ValueError,match='Khoảng lớp'):
        build(root,report,db,2020,2021,99,publish=True,area_model=model,expected_count=4)
    assert db.read_bytes()==before


def test_changed_sql_statistics_cannot_be_published_as_same_f_snapshot(spatial_fixture):
    root,db,report,model=spatial_fixture
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE ntl_annual SET sol=100,sol_density=25 WHERE province_code='01' AND year=2020")
    before=db.read_bytes()
    with pytest.raises(ValueError,match='SOL trong SQLite'):
        build(root,report,db,2020,2021,99,publish=True,area_model=model,expected_count=4)
    assert db.read_bytes()==before


def test_moran_can_show_single_year_of_existing_run(spatial_fixture):
    root,db,report,model=spatial_fixture
    result=build(root,report,db,2020,2021,99,7,publish=True,area_model=model,expected_count=4)
    client=TestClient(app)
    data=client.get('/api/spatial?year_start=2021&year_end=2021').json()
    assert data['status']=='ready' and data['moran']==[dict(year=2021,moran_i=result['moran'][1]['moran_i'])]
    csv_response=client.get('/api/spatial/file',params=dict(kind='moran',year_start=2021,year_end=2021,run_id=result['run_id'],expected_snapshot=result['dataset_id']))
    assert csv_response.status_code==200
    assert len(csv_response.content.decode('utf-8-sig').splitlines())==2
