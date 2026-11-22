"""F: ảnh→CSV→SQLite→API→export, mất/đổi nguồn và metadata không trộn snapshot."""
import csv
import json
from pathlib import Path
import sqlite3

import numpy as np
import pytest
import rasterio
from shapely.geometry import box
from fastapi.testclient import TestClient

from test_fractional_and_repair import prepared_fixture,model_for,raster
from test_economy_indices import inputs
from backend.data.fix_demo_data import fix
from backend.data.verify_demo import verify,inspect_asset
from backend.data.dataset import checked_snapshot,signature_status
from backend.api.main import app


@pytest.fixture
def integrated(tmp_path,monkeypatch):
    prepared,db,method,model=prepared_fixture(tmp_path)
    fixed=fix(tmp_path,prepared,db,method,area_model=model,publish=True)
    report=Path(fixed['output'])/'fix_report.json'
    # Bộ v9 trên máy người dùng chưa có dataset_manifest; bootstrap phải không tính lại chỉ số.
    (Path(fixed['output'])/'indices/dataset_manifest.json').unlink()
    checked=verify(tmp_path,report,db,publish=True,area_model=model)
    monkeypatch.setenv('VNGIS_DB',str(db))
    return db,fixed,checked,model,report


def test_csv_sql_api_and_exports_have_same_snapshot_and_values(integrated):
    db,fixed,checked,model,report=integrated
    assert checked['published'] and checked['demo_schema_version']==2
    assert checked['assets_checked']==39 and checked['outside_valid_values_after']==0
    assert checked['field_contract_rows']==36
    client=TestClient(app)
    data=client.get('/api/demo/province?province_code=01&nam=2022').json()
    assert data['snapshot_id']==data['provenance']['dataset_id']==checked['dataset_id']
    assert data['provenance']['consistent'] and data['provenance']['stats_version']==9
    assert data['processed_asset']['verification_status']=='verified'
    response=client.get('/api/demo/province.csv?province_code=01&nam=2022')
    rows=list(csv.DictReader(response.content.decode('utf-8-sig').splitlines()))
    sol=next(r for r in rows if r['field']=='sol')
    assert float(sol['value'])==20 and sol['dataset_id']==checked['dataset_id']
    assert sol['unit']=='nW/cm²/sr' and len(sol['source_image_sha256'])==64
    assert next(r for r in rows if r['field']=='sol_per_capita')['value']=='0.2'
    image=client.get('/api/demo/image',params=dict(province_code='01',nam=2022,kind='processed',expected_snapshot=checked['dataset_id']))
    assert image.status_code==200 and image.headers['x-snapshot-id']==checked['dataset_id']
    assert image.headers['cache-control']=='no-store'
    for endpoint in ('province.csv','classes.csv','image','economy.csv'):
        args=dict(province_code='01',expected_snapshot='older_snapshot')
        if endpoint=='economy.csv':args.update(nam_tu=2022,nam_den=2022)
        else:args.update(nam=2022)
        assert client.get('/api/demo/'+endpoint,params=args).status_code==409
    economy=client.get('/api/demo/economy?province_code=01&nam_tu=2022&nam_den=2022&price_basis=hien_hanh').json()
    assert economy['dong'][0]['dataset_id']==checked['dataset_id'] and economy['dong'][0]['grdp']==200
    assert economy['dong'][0]['provenance_consistent']
    info=client.get('/api/demo/dataset').json()
    assert info['snapshot_id']==checked['dataset_id'] and info['datasets'][0]['available']
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT COUNT(*) FROM demo_asset').fetchone()[0]==39
        assert connection.execute('SELECT COUNT(*) FROM demo_asset_check').fetchone()[0]==39
        assert connection.execute("SELECT value FROM demo_schema_meta WHERE key='version'").fetchone()[0]=='2'


def test_missing_or_changed_file_is_not_available_or_used_in_model(integrated):
    db,fixed,checked,model,report=integrated
    client=TestClient(app)
    data=client.get('/api/demo/province?province_code=01&nam=2022').json()
    source=Path(data['processed_asset']['path'])
    source.unlink()
    data=client.get('/api/demo/province?province_code=01&nam=2022').json()
    assert not data['processed_asset']['available'] and not data['provenance']['consistent']
    assert next(r for r in data['fields'] if r['field']=='sol')['value']==20 # Số lịch sử vẫn có, kèm nguồn không sẵn có.
    assert client.get('/api/demo/image?province_code=01&nam=2022&kind=processed').status_code==410
    economy=client.get('/api/demo/economy?province_code=01&nam_tu=2022&nam_den=2022').json()
    assert not economy['dong'][0]['paired'] and not economy['dong'][0]['provenance_consistent']
    raw=client.get('/api/demo/province?province_code=01&nam=2022&thang=8').json()['raw_asset']
    with rasterio.open(raw['path'],'r+') as image:image.update_tags(CHANGED='true')
    changed=client.get('/api/demo/province?province_code=01&nam=2022&thang=8').json()
    assert not next(r for r in changed['fields'] if r['field']=='avg_rad')['available']
    assert client.get('/api/demo/image?province_code=01&nam=2022&thang=8&kind=raw').status_code==410


def test_csv_missing_is_visible_and_zero_is_preserved(integrated):
    db,fixed,checked,model,report=integrated
    (Path(fixed['output'])/'indices/night_data.csv').unlink()
    client=TestClient(app)
    data=client.get('/api/demo/province?province_code=01&nam=2022&thang=8').json()
    assert data['provenance']['dataset_available'] is False and data['provenance']['reason']
    assert next(r for r in data['fields'] if r['field']=='total_pixels')['value']==0
    assert next(r for r in data['fields'] if r['field']=='sol')['value'] is None
    info=client.get('/api/demo/dataset').json()
    assert info['datasets'][0]['files']['night_data']=='missing'


def test_geo_export_crops_masks_outside_and_keeps_zero_and_original(tmp_path):
    source=tmp_path/'source.tif'
    raster(source,[[[0,2,3,4],[5,6,7,8]],[[0,1,2,3],[4,5,6,7]]],bands=['avg_rad','cf_cvg'])
    original=source.read_bytes()
    model=model_for(box(500,0,2500,2000))
    row=dict(province_code='01',year=2024,month=1,kind='raw',source='VIIRS',path=str(source))
    result=inspect_asset(row,model,tmp_path/'exports')
    assert result['masked_copy'] and result['outside_valid_values_before']==4
    assert result['outside_valid_values_after']==0 and source.read_bytes()==original
    with rasterio.open(result['export']['path']) as image:
        assert image.width==3 and image.height==2 and image.count==2
        assert image.read(1).tolist()==[[0,2,3],[5,6,7]]
        assert image.read_masks(1)[0,0]==255 and image.read(2)[0,0]==0
        assert image.descriptions==('avg_rad','cf_cvg')
    assert inspect_asset(row,model,tmp_path/'exports',result)==result


def test_mismatch_aborts_without_publishing_and_tampered_csv_is_rejected(integrated,tmp_path):
    db,fixed,checked,model,report=integrated
    with sqlite3.connect(db) as connection:connection.execute("UPDATE ntl_annual SET sol=999 WHERE province_code='01' AND year=2022")
    before=db.read_bytes()
    with pytest.raises(ValueError,match='CSV/SQLite'):
        verify(tmp_path,report,db,publish=True,area_model=model)
    assert db.read_bytes()==before
    path=Path(fixed['output'])/'indices/ntl_annual.csv'
    with path.open('a',encoding='utf-8') as stream:stream.write('\n')
    with pytest.raises(ValueError,match='dataset_manifest'):
        checked_snapshot(path.parent)


def test_raster_changed_even_when_sql_csv_match_is_detected(integrated,tmp_path):
    db,fixed,checked,model,report=integrated
    with sqlite3.connect(db) as connection:
        path=connection.execute("SELECT path FROM demo_asset WHERE province_code='01' AND year=2022 AND month=0 AND kind='processed'").fetchone()[0]
    # Thay pixel nguồn trong khi CSV/SQLite giữ giá trị cũ: không được chỉ kiểm mask rồi công bố.
    with rasterio.open(path,'r+',IGNORE_COG_LAYOUT_BREAK='YES') as image:image.write(np.array([[11,11]],dtype='float32'),1)
    before=db.read_bytes()
    with pytest.raises(ValueError,match='Ảnh/CSV'):
        verify(tmp_path,report,db,publish=True,area_model=model)
    assert db.read_bytes()==before


def test_models_and_forecasts_are_checked_against_exported_coefficients(inputs,tmp_path):
    from backend.data.calculate_ntl import calculate,write_tables
    from backend.data.economy_indices import read_prices
    from backend.data.verify_demo import compare_models
    records,prices,file=inputs
    tables=calculate(records,economy_prices=read_prices(file))
    output=tmp_path/'models'
    write_tables(tables,output)
    assert compare_models(output)==2
    path=output/'calculation_models.csv'
    rows=list(csv.DictReader(path.open(encoding='utf-8-sig')))
    rows[0]['beta']=str(float(rows[0]['beta'])+.1)
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError,match='Beta mô hình'):compare_models(output)


def test_newer_schema_is_rejected_without_resetting_old_data(integrated,tmp_path):
    from backend.data.dataset import migrate_demo
    db,fixed,checked,model,report=integrated
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE demo_schema_meta SET value='999' WHERE key='version'")
    before=db.read_bytes()
    with sqlite3.connect(db) as connection:
        with pytest.raises(ValueError,match='schema mới hơn'):migrate_demo(connection)
    assert db.read_bytes()==before
