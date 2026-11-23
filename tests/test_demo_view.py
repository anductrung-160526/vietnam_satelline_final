"""Phần B: hai cơ sở giá không ghi đè nhau, mẫu chung, NULL/0, Raw trước Processed."""
import csv
import json
from pathlib import Path
import sqlite3

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.data.build_indices import mo
from backend.data.load_demo import load, SCHEMA
from backend.data.build_light_classes import classify_image, choose_thresholds


@pytest.fixture
def database(tmp_path, monkeypatch):
    db = tmp_path/'demo.db'
    con = mo(db)
    con.executescript(SCHEMA.read_text(encoding='utf-8'))
    for code in ['01','27']:
        for year in range(2015,2025):
            light = (int(code)+year-2010)*100
            con.execute('INSERT INTO ntl_annual(province_code,year,source,sol,sol_raw,area_km2,sol_density,lit_area_km2,lit_area_pct) VALUES(?,?,?,?,?,?,?,?,?)',
                        (code,year,'VIIRS',light,light+2,1000,light/1000,20,2))
            for basis,factor in [('so_sanh',1),('hien_hanh',2)]:
                con.execute('INSERT INTO economy_prices VALUES(?,?,?,?,?,?,?,?,?,?)',
                            (code,year,basis,light**.8*factor,None,2010 if basis=='so_sanh' else None,'ty_vnd',int(year==2024),'official',''))
    con.commit(); con.close()
    monkeypatch.setenv('VNGIS_DB', str(db))
    return db


def test_raw_before_processed_and_no_fake_population(database):
    client = TestClient(app)
    data = client.get('/api/demo/province?province_code=01&nam=2024').json()
    stages = [r['stage'] for r in data['fields']]
    assert stages == sorted(stages,key=lambda s:0 if s=='Raw' else 1)
    assert not any(r['field']=='population' for r in data['fields'])
    assert next(r for r in data['fields'] if r['field']=='sol_raw')['stage']=='Processed'
    assert data['class_status']=='missing' and data['classes']==[]
    assert client.get('/api/demo/image?province_code=01&nam=2024&kind=raw').status_code==404
    assert client.get('/api/demo/province?province_code=99&nam=2024').status_code==404


def test_paired_regressions_same_sample_and_csv(database):
    con=sqlite3.connect(database)
    con.execute("UPDATE economy_prices SET grdp=NULL WHERE province_code='01' AND year=2015 AND price_basis='hien_hanh'")
    con.commit();con.close()
    client=TestClient(app)
    query='nam_tu=2015&nam_den=2024&price_basis=compare'
    data=client.get('/api/demo/economy?'+query).json()
    assert len(data['dong'])==20 and data['paired_count']==19
    assert data['hoi_quy']['so_sanh']['n']==data['hoi_quy']['hien_hanh']['n']==19
    assert data['hoi_quy']['so_sanh']['beta']==pytest.approx(.8)
    assert data['hoi_quy']['hien_hanh']['beta']==pytest.approx(.8)
    body=client.get('/api/demo/economy.csv?'+query).content.decode('utf-8-sig')
    assert 'grdp_so_sanh' in body and 'grdp_hien_hanh' in body
    assert 'province_code' in body
    assert client.get('/api/demo/economy?price_basis=bad').status_code==400


def make_raster(path, values, count=1):
    values=np.asarray(values,dtype='float32')
    with rasterio.open(path,'w',driver='GTiff',width=values.shape[-1],height=values.shape[-2],count=count,
                       dtype='float32',crs='EPSG:6933',nodata=-9999,transform=from_origin(0,1000,1000,1000)) as image:
        image.write(values.reshape(count,values.shape[-2],values.shape[-1]))
        for i,name in enumerate(['avg_rad','cf_cvg'][:count],1):image.set_band_description(i,name)


def test_class_area_threshold_edges_and_nodata(tmp_path):
    source=tmp_path/'source.tif';target=tmp_path/'classes.tif'
    make_raster(source,[[0,.5,1.5,10,20,-9999]])
    before=source.read_bytes()
    assert classify_image(source,target,[.5,1.5,10,20])==[1,1,1,1,1]
    assert source.read_bytes()==before
    with rasterio.open(target) as image:
        assert image.read(1).tolist()==[[0,1,2,3,4,255]]
        assert image.nodata==255
    assets=[dict(province_code='01',year=2020,month=0,path=str(source))]
    breaks,n=choose_thresholds(assets,2020,{'01'})
    assert breaks[:2]==[.5,1.5] and breaks[2:]==pytest.approx([10,18]) and n==3
    with pytest.raises(ValueError,match='mỗi tỉnh'):choose_thresholds(assets,2020,{'01','27'})


def test_loader_both_prices_backup_and_cog_preserved(database,tmp_path):
    root=tmp_path/'data';root.mkdir();prepared=tmp_path/'prepared';prepared.mkdir()
    raw=root/'raw_data/01_VIIRS_2024-01.tif';raw.parent.mkdir()
    make_raster(raw,[[[1,2]],[[3,4]]],count=2)
    processed=root/'01_VIIRS_2024.tif';make_raster(processed,[[1,2]])
    def write(name,rows):
        with (prepared/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write('grdp_all_prices.csv',[dict(province_code='01',year=2024,grdp=100 if basis=='so_sanh' else 200,
          grdp_price_basis=basis,price_base_year='2010' if basis=='so_sanh' else '',unit='ty_vnd',
          is_provisional=1,source='official',quality_flags='') for basis in ['so_sanh','hien_hanh']])
    write('manifest_candidates.csv',[dict(province_code='01',year=2024,month=0,source='VIIRS',path=str(processed))])
    write('image_inventory.csv',[dict(province_code='01',year=2024,month=1,source='VIIRS',path=str(raw),
                                     band_names=json.dumps(['avg_rad','cf_cvg']),filter_evidence='')])
    con=sqlite3.connect(database);con.execute("INSERT INTO cog_image(kind,year,path) VALUES('NTL',2024,'keep.tif')");con.commit();con.close()
    result=load(root,prepared,database)
    assert Path(result['backup']).exists() and result['assets']==2
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT path FROM cog_image WHERE year=2024").fetchone()==('keep.tif',)
        assert con.execute("SELECT grdp FROM economy_prices WHERE province_code='01' AND year=2024 ORDER BY price_basis").fetchall()==[(200,),(100,)]
    client=TestClient(app)
    assert client.get('/api/demo/image?province_code=01&nam=2024&thang=1&kind=raw').content==raw.read_bytes()


def test_outside_raster_tile_is_404_not_server_crash(database,tmp_path):
    source=tmp_path/'source.tif';make_raster(source,[[1,2]])
    response=TestClient(app).get('/tiles/cog/tiles/WebMercatorQuad/8/0/0.png',params={'url':str(source),'bidx':1})
    assert response.status_code==404


def test_resume_classes_after_windows_schema_error(database, tmp_path, monkeypatch):
    from backend.data import build_light_classes as module
    source = tmp_path/'source.tif'
    make_raster(source, [[0, .5, 1.5, 10, 20, -9999]])
    directory = tmp_path/'cog/light_classes/20261121_235900'
    directory.mkdir(parents=True)
    breaks = [.5, 1.5, 10., 20.]
    (directory/'method.json').write_text(json.dumps(dict(
        breaks=breaks, reference_year=2020, status='empirical_demo')), encoding='utf-8')
    target = directory/'01_VIIRS_2024_00_classes.tif'
    expected = classify_image(source, target, breaks, 2020)
    before = target.read_bytes()
    with sqlite3.connect(database) as con:
        con.execute('INSERT INTO demo_asset VALUES(?,?,?,?,?,?,?)',
                    ('01', 2024, 0, 'processed', str(source), 'VIIRS', '[]'))
    def forbidden(*args, **kwargs):
        raise AssertionError('Không được phân lớp/chọn ngưỡng lại khi phục hồi ảnh đã có.')
    monkeypatch.setattr(module, 'classify_image', forbidden)
    monkeypatch.setattr(module, 'choose_thresholds', forbidden)
    original_read_text = Path.read_text
    def windows_read_text(path, *args, **kwargs):
        if path == SCHEMA:
            assert kwargs.get('encoding') == 'utf-8'
        return original_read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', windows_read_text)
    result = module.build(tmp_path, database, resume_dir=directory)
    assert result['images'] == result['reused_images'] == 1
    assert target.read_bytes() == before
    with sqlite3.connect(database) as con:
        areas = [r[0] for r in con.execute('SELECT area_km2 FROM light_class ORDER BY class_index')]
    assert areas == expected
    report = json.loads(Path(result['validation_report']).read_text(encoding='utf-8'))
    assert report['images'] == 1 and report['missing_province_area'] == 0
    with Path(result['class_csv']).open(encoding='utf-8-sig') as stream:
        exported = list(csv.DictReader(stream))
    assert len(exported) == 5
    assert sum(float(r['class_area_km2']) for r in exported) == 5
    assert sum(float(r['class_area_pct']) for r in exported) == pytest.approx(.5)
    client = TestClient(app)
    data = client.get('/api/demo/province?province_code=01&nam=2024').json()
    assert data['class_summary']['valid_pixels'] == 5
    assert data['class_summary']['nodata_pixels'] == 1
    assert data['class_summary']['valid_area_pct'] == .5
    assert sum(c['class_area_pct'] for c in data['classes']) == pytest.approx(.5)
    assert not any(r['field']=='valid_area_km2' for r in data['fields'])
    csv_result = client.get('/api/demo/classes.csv?province_code=01&nam=2024')
    records = list(csv.DictReader(csv_result.content.decode('utf-8-sig').splitlines()))
    assert len(records) == 5 and float(records[0]['area_km2']) == 1000
    assert float(records[0]['class_area_km2']) == 1
    assert client.get('/api/demo/classes.csv?province_code=01&nam=2023').status_code == 404
    (directory/'method.json').write_text(json.dumps(dict(
        breaks=[.5, 1.5, 11., 20.], reference_year=2020, status='empirical_demo')), encoding='utf-8')
    with pytest.raises(ValueError, match='không khớp'):
        module.build(tmp_path, database, resume_dir=directory)
    with sqlite3.connect(database) as con:
        assert con.execute('SELECT COUNT(*) FROM light_class').fetchone()[0] == 5


def test_classification_rejects_bad_values_and_corrupt_saved_class(tmp_path):
    from backend.data.build_light_classes import saved_areas
    source, target = tmp_path/'radiance.tif', tmp_path/'classes.tif'
    make_raster(source, [[-.1, 2]])
    with pytest.raises(ValueError, match='âm'):
        classify_image(source, target, [.5, 1.5, 10, 20], 2020)
    assert not target.exists()
    make_raster(source, [[0, 2]])
    with pytest.raises(ValueError, match='ngưỡng'):
        classify_image(source, target, [.5, 1.5, 1.5, 20], 2020)
    classify_image(source, target, [.5, 1.5, 10, 20], 2020)
    with rasterio.open(target, 'r+', IGNORE_COG_LAYOUT_BREAK='YES') as image:
        image.write(np.array([[0, 4]], dtype='uint8'), 1)
    with pytest.raises(ValueError, match='không khớp ngưỡng'):
        saved_areas(target, source, [.5, 1.5, 10, 20], 2020)


def test_geographic_class_area_uses_latitude_and_nodata_stays_empty(tmp_path):
    from backend.data.build_light_classes import saved_areas
    source, target = tmp_path/'radiance.tif', tmp_path/'classes.tif'
    transform = from_origin(105, 22, .01, .01)
    with rasterio.open(source, 'w', driver='GTiff', width=2, height=2, count=1,
                       dtype='float32', nodata=-9999, crs='EPSG:4326', transform=transform) as image:
        image.write(np.array([[0, 1.5], [10, -9999]], dtype='float32'), 1)
    classify_image(source, target, [.5, 1.5, 10, 20], 2020)
    result = saved_areas(target, source, [.5, 1.5, 10, 20], 2020, details=True)
    top = .01**2 * 111.320**2 * np.cos(np.radians(21.995))
    bottom = .01**2 * 111.320**2 * np.cos(np.radians(21.985))
    assert result['areas'] == pytest.approx([top, 0, top, bottom, 0])
    assert result['valid_area_km2'] == pytest.approx(2*top + bottom)
    assert result['valid_pixels'] == 3 and result['nodata_pixels'] == 1
    make_raster(source, [[-9999, -9999]])
    classify_image(source, target, [.5, 1.5, 10, 20], 2020)
    empty = saved_areas(target, source, [.5, 1.5, 10, 20], 2020, details=True)
    assert empty['areas'] == [0]*5 and empty['valid_pixels'] == 0
    with rasterio.open(target) as image:
        assert image.read(1).tolist() == [[255, 255]]


@pytest.mark.parametrize('values,area,expected_status', [
    ([[-9999, -9999]], 6, 'no_valid_pixels'),
    ([[0, 2]], 1, 'passed'),
    ([[0, 2]], None, 'passed'),
])
def test_class_summary_missing_empty_and_coverage_above_100(database, tmp_path, values, area, expected_status):
    from backend.data.build_light_classes import build
    source = tmp_path/'source.tif'
    make_raster(source, values)
    directory = tmp_path/'cog/light_classes/test'
    directory.mkdir(parents=True)
    (directory/'method.json').write_text(json.dumps(dict(
        breaks=[.5, 1.5, 10, 20], reference_year=2020, status='empirical_demo')), encoding='utf-8')
    classify_image(source, directory/'01_VIIRS_2024_00_classes.tif', [.5, 1.5, 10, 20], 2020)
    with sqlite3.connect(database) as con:
        con.execute('INSERT INTO demo_asset VALUES(?,?,?,?,?,?,?)',
                    ('01', 2024, 0, 'processed', str(source), 'VIIRS', '[]'))
    area_file = tmp_path/'province_areas.csv'
    area_file.write_text('province_code,area_km2\n'+('01,'+str(area) if area is not None else '27,6')+'\n', encoding='utf-8')
    result = build(tmp_path, database, resume_dir=directory, areas_csv=area_file)
    data = TestClient(app).get('/api/demo/province?province_code=01&nam=2024').json()
    summary = data['class_summary']
    assert summary['validation_status'] == expected_status
    if area is None:
        assert summary['area_km2'] is None and summary['valid_area_pct'] is None
        assert result['missing_province_area'] == 1
        assert all(c['class_area_pct'] is None for c in data['classes'])
    elif expected_status == 'no_valid_pixels':
        assert result['empty_images'] == 1 and summary['valid_area_pct'] == 0
        assert all(c['class_area_pct'] is None for c in data['classes'])
    else:
        assert summary['valid_area_pct'] == 200 and result['coverage_above_100'] == 1
        assert sum(c['class_area_pct'] for c in data['classes']) == 200
