"""Các công thức thật: mẫu hồi quy chung, tham chiếu ngoài bộ lọc, mẫu số 0 và thiếu dữ liệu."""
import csv
import io
import math
import pytest
from fastapi.testclient import TestClient
from test_demo_view import database
from test_integration_f import integrated
from backend.api.main import app
from backend.core.economic_metrics import add_economic_metrics
from backend.core.indicator_catalog import ECONOMY_FIELDS,ECONOMY_PRIMARY,CATALOG


def test_growth_density_and_ratios_use_previous_calendar_year_and_selected_price():
    rows=[dict(province_code='01',year=2021,sol=120,grdp_so_sanh=55,grdp_hien_hanh=121,paired=False)]
    obs={('01',2020):dict(sol=100,source='VIIRS'),('01',2021):dict(sol=120,source='VIIRS',area_km2=12)}
    prices={('01',2020,'so_sanh'):{'grdp':50},('01',2021,'so_sanh'):{'grdp':55},('01',2020,'hien_hanh'):{'grdp':100},('01',2021,'hien_hanh'):{'grdp':121}}
    fits={p:dict(alpha=None,beta=None) for p in ('so_sanh','hien_hanh')}
    add_economic_metrics(rows,obs,prices,'so_sanh',fits);r=rows[0]
    assert r['sol_density']==10 and r['sol_change_pct']==pytest.approx(20)
    assert r['gdp_change_pct']==pytest.approx(10) and r['light_gdp_elasticity']==pytest.approx(2)
    assert r['sol_gdp_ratio']==pytest.approx(120/55) and r['predicted_gdp'] is None
    add_economic_metrics(rows,obs,prices,'hien_hanh',fits)
    assert r['light_gdp_elasticity']==pytest.approx(20/21)
    prices['01',2020,'hien_hanh']['grdp']=121
    add_economic_metrics(rows,obs,prices,'hien_hanh',fits);assert r['light_gdp_elasticity'] is None
    obs['01',2020]['source']='DMSP';add_economic_metrics(rows,obs,prices,'hien_hanh',fits)
    assert r['sol_change_pct'] is None


def test_prediction_uses_exact_model_of_same_positive_common_sample():
    rows=[dict(province_code='01',year=2015+i,sol=s,grdp_so_sanh=3*s*s,grdp_hien_hanh=5*s*s,paired=True) for i,s in enumerate(range(10,110,10))]
    obs={('01',r['year']):dict(sol=r['sol'],source='VIIRS',area_km2=10) for r in rows}
    prices={('01',r['year'],p):dict(grdp=r['grdp_'+p]) for r in rows for p in ('so_sanh','hien_hanh')}
    fits={p:dict(alpha=None,beta=None) for p in ('so_sanh','hien_hanh')}
    add_economic_metrics(rows,obs,prices,'so_sanh',fits)
    assert fits['so_sanh']['beta']==pytest.approx(2) and fits['so_sanh']['n']==10
    assert all(r['predicted_gdp']==pytest.approx(3*r['sol']**2) for r in rows)
    add_economic_metrics(rows,obs,prices,'hien_hanh',fits)
    assert all(r['predicted_gdp']==pytest.approx(5*r['sol']**2) for r in rows)
    # Không hạ điều kiện 10 quan sát của dự án hoặc tái dùng hệ số mẫu trước.
    add_economic_metrics(rows[:9],obs,prices,'hien_hanh',fits)
    assert fits['hien_hanh']['beta'] is None
    assert all(r['predicted_gdp'] is None for r in rows[:9])


def test_dictionary_and_filter_definitions_are_identical():
    from pathlib import Path
    lines=[line for line in (Path(__file__).parents[1]/'docs/NIGHT_DATA_DICTIONARY.md').read_text(encoding='utf-8').splitlines() if line.startswith('|')]
    header=[c.strip() for c in lines[0].strip('|').split('|')]
    for line in lines[2:]:
        row=dict(zip(header,[c.strip().strip('`') for c in line.strip('|').split('|')]))
        entry=CATALOG[row['field']]
        assert entry['definition']==row['description']
        assert entry['formula']==row['formula']
        assert entry['stage']==row['note']


def test_scopes_definitions_and_complete_economy_columns(database):
    client=TestClient(app);catalog=client.get('/api/indicators').json()['chi_so']
    assert catalog and all(e['scope']=='Night Data' and e['definition'] and e['formula'] for e in catalog)
    assert not {e['field'] for e in catalog}&ECONOMY_PRIMARY
    data=client.get('/api/demo/economy?nam_tu=2020&nam_den=2024').json()
    assert [c['field'] for c in data['columns']]==ECONOMY_FIELDS
    assert [c['stage'] for c in data['columns']][:2]==['Raw','Raw']
    forbidden={'chenh_lech_gdp_anh','cuong_do_vung_sang','ty_trong_sol_quoc_gia','sol_bq_dau_nguoi','sol_cal','light_basis','valid_pixels','area_km2','source','note','calibration','status'}
    assert not forbidden&set(ECONOMY_FIELDS)
    assert all(c['definition'] and c['formula'] for c in data['columns'])
    assert all(r['predicted_gdp'] is not None for r in data['dong'])
    csv_data=client.get('/api/demo/economy.csv?nam_tu=2020&nam_den=2024&fields=grdp_so_sanh,sol,sol_gdp_ratio,predicted_gdp')
    reader=csv.DictReader(io.StringIO(csv_data.content.decode('utf-8-sig')));rows=list(reader)
    assert reader.fieldnames==['province_code','province_name','year','month','grdp_so_sanh','sol','sol_gdp_ratio','predicted_gdp']
    assert len(rows)==10 and float(rows[0]['sol_gdp_ratio'])>0


def test_month_table_keeps_grdp_null_and_annual_regression_intact(integrated):
    client=TestClient(app)
    data=client.get('/api/demo/economy?province_code=01&nam_tu=2022&nam_den=2022&view_frequency=monthly').json()
    assert len(data['dong'])==12 and len(data['regression_rows'])==1
    assert all(r['grdp_so_sanh'] is None and r['grdp_hien_hanh'] is None and r['sol_gdp_ratio'] is None for r in data['dong'])
    assert data['dong'][0]['sol'] is not None
    assert client.get('/api/demo/economy?fields=area_km2').status_code==400


def test_economy_does_not_merge_two_different_snapshots(database,monkeypatch):
    from backend.api import data_table
    monkeypatch.setattr(data_table,'data_table',lambda *a,**k:dict(snapshot_id='changed',rows=[]))
    response=TestClient(app).get('/api/demo/economy?view_frequency=monthly')
    assert response.status_code==409
