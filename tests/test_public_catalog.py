import csv
import io
import sqlite3
import pytest
from fastapi.testclient import TestClient
from test_integration_f import integrated
from backend.api.main import app
from backend.api import store
from backend.core.public_fields import is_public
from backend.data.purge_simulated import purge


def test_catalog_monthly_nulls_and_public_csv(integrated):
    db,*_=integrated
    client=TestClient(app)
    fields={r['ma'] for r in client.get('/api/indicators').json()['chi_so']}
    assert {'grdp_so_sanh','grdp_hien_hanh','min_rad','background_threshold','background_pixels','lit_threshold'}<=fields
    assert 'sol_cal' not in fields and 'NDVI_mean' not in fields and 'cloud_free_obs' not in fields
    data=client.get('/api/demo/data?province_code=01&moc=2022,2022-07').json()
    assert all(is_public(c['field']) for c in data['columns'])
    annual,month=data['rows'];assert annual['grdp_so_sanh']==100
    assert 'population' not in fields and 'population' not in month
    for f in ('grdp_so_sanh','grdp_hien_hanh'):assert month[f] is None
    assert month['min_rad'] is not None and 'dataset_id' not in month and 'valid_area_km2' not in month
    params=dict(province_code='01',moc='2022,2022-07',chi_so='grdp_so_sanh,min_rad,background_threshold')
    export=client.get('/api/demo/data.csv',params=params)
    rows=list(csv.DictReader(io.StringIO(export.content.decode('utf-8-sig'))))
    assert rows[1]['grdp_so_sanh']=='' and 'min_rad' in rows[1]
    panel=client.get('/api/panel?province_code=01&moc=2022,2022-07&chi_so=grdp_so_sanh,min_rad').json()
    assert panel['dong'][0]['gia_tri']==[100,None]
    assert panel['dong'][1]['gia_tri'][1]==month['min_rad']
    economy=client.get('/api/demo/economy.csv?province_code=01&nam_tu=2022&nam_den=2022&thang=7')
    economic_row=next(csv.DictReader(io.StringIO(economy.content.decode('utf-8-sig'))))
    assert economic_row['month']=='7' and economic_row['grdp_so_sanh']==''
    assert all(is_public(k) for k in economic_row)


def test_fake_rows_hidden_then_physically_deleted_and_real_rows_preserved(integrated):
    db,*_=integrated
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO ntl_annual(province_code,year,source,status,sol) VALUES('01',2019,'VIIRS_GIA_LAP','GIA_LAP',999)")
        c.execute("INSERT INTO economy_prices(province_code,year,price_basis,grdp,source) VALUES('01',2019,'so_sanh',999,'GIA_LAP')")
        c.execute("INSERT INTO demo_result VALUES('01',2019,0,'night_data','',?)",('{"sol_raw":999,"min_rad":9}',))
    client=TestClient(app)
    row=client.get('/api/demo/data?province_code=01&moc=2019').json()['rows'][0]
    assert row['sol'] is None and row['sol_raw'] is None and row['grdp_so_sanh'] is None
    result=purge(db);assert result['total_deleted']==3
    assert result['backup']
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM ntl_annual WHERE source LIKE '%GIA_LAP%'").fetchone()[0]==0
        assert c.execute("SELECT sol FROM ntl_annual WHERE year=2022").fetchone()[0]==20


def test_population_is_absent_from_all_public_economic_outputs(integrated):
    client=TestClient(app)
    payload=client.get('/api/demo/economy?province_code=01&nam_tu=2022&nam_den=2022').json()
    assert 'population_missing' not in payload
    assert payload['dong'] and all('population' not in row for row in payload['dong'])
    for endpoint,query in [('data.csv','province_code=01&moc=2022'),('economy.csv','province_code=01&nam_tu=2022&nam_den=2022')]:
        rows=list(csv.DictReader(io.StringIO(client.get('/api/demo/'+endpoint+'?'+query).content.decode('utf-8-sig'))))
        assert rows and 'population' not in rows[0]
    fields=client.get('/api/demo/province?province_code=01&nam=2022').json()['fields']
    assert not any(f['field']=='population' for f in fields)
