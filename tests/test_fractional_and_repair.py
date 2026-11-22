"""Giao pixel có lỗ/ngoài tỉnh, sửa mask thật từ raw và giữ tháng thật sự thiếu."""
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from shapely.geometry import box, Polygon, mapping, shape

from backend.data.fractional_area import pixel_intersection_areas, ProvinceAreas, AREA_METHOD
from backend.data.calculate_ntl import ntl_stats, calculate
from backend.data.build_light_classes import classify_image, build
from backend.data.build_indices import mo
from backend.data.repair_monthly import process_year, FILTER


def raster(path, values, bands=None, transform=None, crs='EPSG:6933', **tags):
    array=np.asarray(values,dtype='float32')
    if array.ndim==2:array=array[None]
    with rasterio.open(path,'w',driver='GTiff',width=array.shape[2],height=array.shape[1],count=array.shape[0],
                       dtype='float32',nodata=-9999,crs=crs,transform=transform or from_origin(0,2000,1000,1000)) as image:
        image.write(array)
        if bands:
            for i,name in enumerate(bands,1):image.set_band_description(i,name)
        image.update_tags(**tags)


def model_for(polygon):
    return SimpleNamespace(areas={'01':polygon.area/1e6},metadata={'sha256':'synthetic_test_geometry'},
                           weights=lambda code,image:pixel_intersection_areas(image,polygon))


def test_exact_partial_pixels_hole_and_nodata(tmp_path):
    source=tmp_path/'source.tif'
    polygon=Polygon(box(500,0,2500,2000).exterior.coords,[box(1250,250,1750,750).exterior.coords])
    raster(source,[[2,2,2,999],[2,2,2,999]])
    with rasterio.open(source) as image:weights=pixel_intersection_areas(image,polygon)
    assert weights.tolist()==[[.5,1,.5,0],[.5,.75,.5,0]]
    assert weights.sum()==3.75
    stats=ntl_stats(source,1.5,.5,weights)
    assert stats['valid_pixels']==6 and stats['sol']==12  # SOL là tổng pixel, không nhân trọng số diện tích.
    assert stats['lit_area_km2']==stats['valid_area_km2']==3.75
    records=[dict(province_code='01',province_name='Hà Nội',year=2024,month=0,source='VIIRS',path=source,area_km2=3.75)]
    result=calculate(records,area_model=model_for(polygon))
    assert result['ntl_annual'][0]['lit_area_pct']==100
    assert result['night_data'][0]['valid_area_pct']==100
    raster(source,[[2,-9999,2,999],[2,2,2,999]])
    stats=ntl_stats(source,1.5,.5,weights)
    assert stats['valid_area_km2']==2.75


def test_wgs84_equal_area_and_cache_different_grids(tmp_path):
    polygon=box(105.005,21.98,105.025,22)
    feature={'geometry':mapping(polygon)}
    model=ProvinceAreas({'01':feature},{'sha256':'synthetic_test'},tmp_path/'cache')
    source=tmp_path/'wgs84.tif'
    raster(source,[[1,1,1],[1,1,1]],transform=from_origin(105,22,.01,.01),crs='EPSG:4326')
    with rasterio.open(source) as image:
        weights=model.weights('01',image)
        assert weights.sum()==pytest.approx(model.areas['01'],rel=1e-10)
        assert weights[0,0]==pytest.approx(weights[0,1]/2,rel=1e-9)
    # Cache không phụ thuộc mask; đổi lưới phải tạo khóa khác.
    raster(source,[[1,1]],transform=from_origin(105,22,.02,.01),crs='EPSG:4326')
    with rasterio.open(source) as image:assert model.weights('01',image).shape==(1,2)
    assert len(list((tmp_path/'cache').glob('*.npz')))==2


def test_build_fractional_reuses_raster_and_has_no_percentage_over_100(tmp_path,monkeypatch):
    from backend.data import build_light_classes
    source=tmp_path/'source.tif';classes=tmp_path/'old_classes.tif'
    raster(source,[[2,2,2]])
    polygon=box(500,1000,2500,2000)
    classify_image(source,classes,[.5,1.5,10,20],2020)
    original=classes.read_bytes()
    method=tmp_path/'method.json'
    method.write_text(json.dumps(dict(breaks=[.5,1.5,10,20],reference_year=2020,status='empirical_demo')),encoding='utf-8')
    db=tmp_path/'test.db';con=mo(db)
    from backend.data.load_demo import SCHEMA
    con.executescript(SCHEMA.read_text(encoding='utf-8'))
    con.executemany('INSERT INTO demo_asset VALUES(?,?,?,?,?,?,?)',[
        ('01',2024,0,'processed',str(source),'VIIRS','[]'),('01',2024,0,'classes',str(classes),'VIIRS','[]')])
    con.commit();con.close()
    def no_reclassify(*a,**kw):raise AssertionError('Không phân lớp lại nguồn/ngưỡng không đổi.')
    monkeypatch.setattr(build_light_classes,'classify_image',no_reclassify)
    report=build(tmp_path,db,area_model=model_for(polygon),method_file=method,reuse_registered=True)
    assert report['reused_images']==1 and report['coverage_above_100']==0
    assert classes.read_bytes()==original
    with sqlite3.connect(db) as con:
        row=con.execute('SELECT valid_area_pct,lit_area_pct,method_version FROM light_class_summary').fetchone()
        assert row==(100,100,'viirs_brightness_classes_v3_fractional')


def year_fixture(tmp_path,empty_raw=False,grid_mismatch=False):
    months=[];raw={}
    for m in range(1,13):
        rp=tmp_path/f'raw_{m}.tif';fp=tmp_path/f'filtered_{m}.tif'
        # Tháng 7 raw còn quan sát nhưng filtered bị xóa mask. Tháng 8 thật sự cf=0.
        cf=0 if empty_raw or m==8 else 3
        value=100 if m==7 else 10
        raster(rp,[[[value,value]],[[cf,cf]]],bands=['avg_rad','cf_cvg'])
        raster(fp,[[-9999,-9999]] if m in (7,8) or empty_raw else [[10,10]],FILTER=FILTER)
        months.append(dict(province_code='01',province_name='Hà Nội',year=2022,month=m,source='VIIRS',path=fp,area_km2=2))
        raw['01',2022,m]=str(rp)
    if grid_mismatch:raster(tmp_path/'raw_7.tif',[[[100]],[[3]]],bands=['avg_rad','cf_cvg'])
    annual=tmp_path/'annual.tif'
    raster(annual,[[10,10]] if not empty_raw else [[-9999,-9999]])
    return months,raw,dict(months[0],path=annual,month=0)


def test_repair_recovers_lost_mask_uses_spike_rule_and_preserves_true_gap(tmp_path):
    months,raw,annual=year_fixture(tmp_path)
    before={p:p.read_bytes() for p in list(tmp_path.glob('*.tif'))}
    out=tmp_path/'repair';out.mkdir()
    audit,updates,support=process_year(months,raw,annual,out,model_for(box(0,1000,2000,2000)),apply=True)
    assert audit[6]['diagnosis']=='REPAIRED_FILTER_MISMATCH' and audit[6]['lost_valid_pixels']==2
    assert audit[7]['diagnosis']=='NO_CLOUD_FREE_OBSERVATIONS' and not audit[7]['repaired']
    with rasterio.open(updates['01',2022,7]) as image:
        assert image.read(1).tolist()==[[10,10]]  # 100 vượt max(3×median, median+5), đưa về 10.
        assert image.tags()['CF_CVG_MEAN']=='3.0'
    with rasterio.open(updates['01',2022,0]) as image:assert image.read(1).tolist()==[[10,10]]
    with rasterio.open(support['support_path']) as image:assert image.read(1).tolist()==[[11,11]]
    assert support['valid_month_min']==support['valid_month_max']==11
    assert all(p.read_bytes()==data for p,data in before.items())


def test_all_cf_zero_cannot_be_filled_and_unknown_grid_not_silently_resampled(tmp_path):
    months,raw,annual=year_fixture(tmp_path,empty_raw=True)
    out=tmp_path/'empty';out.mkdir()
    audit,updates,support=process_year(months,raw,annual,out,model_for(box(0,1000,2000,2000)),apply=True)
    assert not updates and all(r['diagnosis']=='NO_CLOUD_FREE_OBSERVATIONS' for r in audit)
    assert support['valid_month_min'] is None
    with rasterio.open(support['support_path']) as image:assert image.read(1).tolist()==[[0,0]]
    missing=raw.copy();missing.pop(('01',2022,7))
    audit,updates,support=process_year(months,missing,annual,out,model_for(box(0,1000,2000,2000)),apply=True)
    assert not updates and support is None and audit[0]['diagnosis']=='MISSING_RAW_OR_FILTERED_MONTHS'
    raster(Path(raw['01',2022,7]),[[[100]],[[3]]],bands=['avg_rad','cf_cvg'])
    audit,updates,support=process_year(months,raw,annual,out,model_for(box(0,1000,2000,2000)),apply=True)
    assert not updates and audit[0]['diagnosis']=='GRID_MISMATCH_REQUIRES_REVIEW'


def prepared_fixture(tmp_path):
    import csv
    from backend.data.load_demo import SCHEMA
    months,raw,annual=year_fixture(tmp_path)
    prepared=tmp_path/'prepared';prepared.mkdir()
    def write(name,rows):
        with (prepared/name).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write('manifest_candidates.csv',months+[annual])
    (prepared/'image_inventory.csv').write_text('province_code,path\n',encoding='utf-8')
    write('grdp_all_prices.csv',[dict(province_code='01',year=2022,grdp=100 if b=='so_sanh' else 200,
          population=100,grdp_price_basis=b,price_base_year=2010 if b=='so_sanh' else '',unit='ty_vnd',
          source='official',is_provisional=0,quality_flags='') for b in ['so_sanh','hien_hanh']])
    method=tmp_path/'method.json'
    method.write_text(json.dumps(dict(breaks=[.5,1.5,10,20],reference_year=2020,status='empirical_demo')),encoding='utf-8')
    db=tmp_path/'app.db';connection=mo(db)
    connection.executescript(SCHEMA.read_text(encoding='utf-8'))
    connection.executemany('INSERT INTO demo_asset VALUES(?,?,?,?,?,?,?)',
                           [(c,y,m,'raw',p,'VIIRS','[]') for (c,y,m),p in raw.items()])
    connection.commit();connection.close()
    return prepared,db,method,model_for(box(0,1000,2000,2000))


def test_fix_publishes_complete_snapshot_and_exposes_annual_support(tmp_path,monkeypatch):
    from backend.data.fix_demo_data import fix
    from backend.api.main import app
    from fastapi.testclient import TestClient
    prepared,db,method,model=prepared_fixture(tmp_path)
    result=fix(tmp_path,prepared,db,method,area_model=model,publish=True)
    assert result['published'] and Path(result['backup']).exists()
    assert result['recovery']['monthly_repaired']==1
    assert result['classification']['coverage_above_100']==0
    assert result['economy_validation']['empty_images']==1
    monkeypatch.setenv('VNGIS_DB',str(db))
    client=TestClient(app)
    data=client.get('/api/demo/province?province_code=01&nam=2022').json()
    assert data['class_summary']['valid_area_pct']==100
    assert data['observation_support']['valid_month_min']=='11'
    assert client.get('/api/demo/image?province_code=01&nam=2022&kind=support').status_code==200
    july=client.get('/api/demo/province?province_code=01&nam=2022&thang=7').json()
    assert next(r for r in july['fields'] if r['field']=='sol')['value']==20
    assert july['recovery_audit']['diagnosis']=='REPAIRED_FILTER_MISMATCH'
    august=client.get('/api/demo/province?province_code=01&nam=2022&thang=8').json()
    assert next(r for r in august['fields'] if r['field']=='sol')['value'] is None
    assert august['recovery_audit']['diagnosis']=='NO_CLOUD_FREE_OBSERVATIONS'


def test_fix_failure_before_publish_leaves_original_database_unchanged(tmp_path,monkeypatch):
    from backend.data import fix_demo_data
    prepared,db,method,model=prepared_fixture(tmp_path)
    before=db.read_bytes()
    def fail(*a,**kw):raise ValueError('forced validation failure')
    monkeypatch.setattr(fix_demo_data,'calculate',fail)
    with pytest.raises(ValueError,match='forced'):
        fix_demo_data.fix(tmp_path,prepared,db,method,area_model=model,publish=True)
    assert db.read_bytes()==before


def test_missing_cf_information_and_unknown_filter_are_not_guessed(tmp_path):
    months,raw,annual=year_fixture(tmp_path)
    raster(Path(raw['01',2022,7]),[[[100,100]],[[-9999,-9999]]],bands=['avg_rad','cf_cvg'])
    out=tmp_path/'audit';out.mkdir()
    audit,updates,support=process_year(months,raw,annual,out,model_for(box(0,1000,2000,2000)),apply=True)
    assert audit[6]['diagnosis']=='MISSING_CF_COVERAGE'
    assert audit[7]['diagnosis']=='NO_CLOUD_FREE_OBSERVATIONS'
    with rasterio.open(months[0]['path'],'r+') as image:image.update_tags(FILTER='unknown custom filter')
    audit,updates,support=process_year(months,raw,annual,out,model_for(box(0,1000,2000,2000)),apply=True)
    assert not updates and support is None and audit[0]['diagnosis']=='FILTER_RULE_UNVERIFIED'


def test_fix_without_publish_keeps_database_unchanged(tmp_path):
    from backend.data.fix_demo_data import fix
    prepared,db,method,model=prepared_fixture(tmp_path)
    before=db.read_bytes()
    result=fix(tmp_path,prepared,db,method,area_model=model,publish=False)
    assert not result['published'] and db.read_bytes()==before
    assert (Path(result['output'])/'candidate.db').exists()
