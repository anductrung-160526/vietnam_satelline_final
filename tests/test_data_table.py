"""Khôi phục bảng ngang: từng tháng, cùng thứ tự cột/số liệu với CSV, không sửa snapshot."""
import csv
import io
from pathlib import Path
from fastapi.testclient import TestClient

from test_integration_f import integrated
from backend.api.main import app
from backend.data.column_order import ordered_fields
from backend.data.calculate_ntl import write_tables


def test_monthly_table_and_csv_share_identity_raw_processed_order(integrated):
    db,fixed,checked,model,report=integrated
    before=db.read_bytes();client=TestClient(app)
    params=dict(province_code='01',moc='2022,2022-07,2022-08')
    response=client.get('/api/demo/data',params=params)
    assert response.status_code==200
    data=response.json();columns=data['columns'];fields=[c['field'] for c in columns]
    groups=[c['group'] for c in columns]
    assert groups==sorted(groups,key=['identity','raw','processed'].index)
    assert fields.index('avg_rad')<fields.index('population')<fields.index('sol_raw')
    assert data['snapshot_id']==checked['dataset_id']
    assert [r['month'] for r in data['rows']]==[0,7,8]
    annual,july,august=data['rows']
    assert annual['avg_rad'] is None and 'grdp_frequency' not in annual
    assert july['avg_rad'].endswith('#band=1') and july['cf_cvg'].endswith('#band=2')
    assert july['grdp_so_sanh'] is None and annual['grdp_so_sanh']==100
    assert july['population'] is None and july['sol']==20
    assert august['sol'] is None and august['total_pixels']==0
    export=client.get('/api/demo/data.csv',params=dict(params,expected_snapshot=data['snapshot_id']))
    reader=csv.DictReader(io.StringIO(export.content.decode('utf-8-sig')));rows=list(reader)
    assert reader.fieldnames==fields and len(rows)==3
    assert rows[2]['sol']=='' and float(rows[2]['total_pixels'])==0
    assert rows[0]['province_code']=='01'
    assert client.get('/api/demo/data.csv',params=dict(params,expected_snapshot='old')).status_code==409
    assert db.read_bytes()==before


def test_filters_missing_month_and_invalid_inputs(integrated):
    client=TestClient(app)
    data=client.get('/api/demo/data?province_code=01&moc=2022-07&chi_so=sol,sol_density_cal').json()
    fields=[c['field'] for c in data['columns']]
    assert 'sol' in fields and 'sol_density' in fields and 'rad_mean' not in fields and 'mean_rad' not in fields
    assert 'avg_rad' in fields and 'grdp_so_sanh' not in fields
    missing=client.get('/api/demo/data?province_code=01&moc=2021-07').json()['rows'][0]
    assert missing['sol'] is None and 'status' not in missing
    assert client.get('/api/demo/data?province_code=999&moc=2022').status_code==400
    assert client.get('/api/demo/data?province_code=01&moc=2022-13').status_code==400


def test_future_csv_writes_keep_column_groups_without_changing_numbers(tmp_path):
    assert ordered_fields(['sol','source','year','population','province_code'])==['province_code','year','source','population','sol']
    tables={'ntl_annual':[dict(sol=5.,source='VIIRS',year=2022,population=0,province_code='01')]}
    write_tables(tables,tmp_path)
    with (tmp_path/'ntl_annual.csv').open(encoding='utf-8-sig') as stream:
        reader=csv.DictReader(stream);row=next(reader)
        assert reader.fieldnames==['province_code','year','source','population','sol']
        assert row['population']=='0' and row['sol']=='5.0'
