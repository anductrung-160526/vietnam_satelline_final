"""Không reset khi đổi schema; khôi phục đúng bộ ảnh, GRDP và Moran cùng snapshot."""
import json
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient
from test_spatial_p1 import spatial_fixture
from backend.data.build_spatial import build
from backend.data.build_indices import mo,SCHEMA_VERSION
from backend.data.recover_demo import recover
from backend.data.database_status import inspect_database
from backend.api.main import app


def test_schema_upgrade_preserves_extra_tables_images_prices_and_rows(tmp_path):
    db=tmp_path/'app.db';connection=mo(db)
    connection.execute('CREATE TABLE spatial_run(run_id TEXT,payload TEXT)')
    connection.execute("INSERT INTO spatial_run VALUES('run','{}')")
    connection.execute("INSERT INTO economy(province_code,year,population,grdp,source) VALUES('01',2024,100,200,'official')")
    connection.execute("INSERT INTO cog_image(kind,year,month,path) VALUES('NTL',2024,0,'existing.tif')")
    connection.execute('PRAGMA user_version=8');connection.commit();connection.close()
    connection=mo(db)
    assert connection.execute('SELECT run_id FROM spatial_run').fetchone()[0]=='run'
    assert connection.execute('SELECT grdp FROM economy').fetchone()[0]==200
    assert connection.execute('SELECT path FROM cog_image').fetchone()[0]=='existing.tif'
    assert connection.execute('PRAGMA user_version').fetchone()[0]==SCHEMA_VERSION
    connection.close();assert list(tmp_path.glob('app.db.backup_migration_*'))


def test_recovery_restores_all_screens_without_recalculating_images(spatial_fixture):
    root,db,report,model=spatial_fixture
    with sqlite3.connect(db) as c:c.execute("INSERT INTO economy_prices(province_code,year,price_basis,grdp,unit,source) VALUES('01',2020,'so_sanh',100,'ty_vnd','official')")
    result=build(root,report,db,2020,2021,99,7,publish=True,area_model=model,expected_count=4)
    spatial_report=Path(result['output'])/'spatial_report.json'
    with sqlite3.connect(db) as c:
        for table in ('economy_prices','demo_asset','light_class','spatial_run'):c.execute('DROP TABLE '+table)
    before=inspect_database(db);assert before['missing_demo_components']
    restored=recover(root,db,spatial_report,publish=True)
    assert restored['published'] and Path(restored['backup']).exists()
    assert not restored['after']['missing_demo_components']
    client=TestClient(app)
    # Fixture province has a minimal schema; inspect payload and real app-independent tables.
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT grdp FROM economy_prices').fetchone()[0]==100
        assert c.execute("SELECT COUNT(*) FROM demo_asset WHERE kind='processed'").fetchone()[0]==8
        assert c.execute('SELECT COUNT(*) FROM light_class').fetchone()[0]==40
    timeline=client.get('/api/basemap?province_code=01&buoc=nam').json()
    assert timeline['nam']==[2020,2021] and timeline['co_san']['nam']==2
    assert client.get('/api/spatial?year_start=2020&year_end=2021').json()['status']=='ready'
    assert client.get('/api/demo/status').json()['grdp_by_price'][0]['population_values']==0


def test_recovery_refuses_missing_source_and_preserves_current_database(spatial_fixture):
    root,db,report,model=spatial_fixture
    result=build(root,report,db,2020,2021,99,7,publish=True,area_model=model,expected_count=4)
    Path(result['source_signatures'][0]['path']).unlink()
    baseline=db.read_bytes()
    with pytest.raises(ValueError,match='mất/đổi'):
        recover(root,db,Path(result['output'])/'spatial_report.json',publish=True)
    assert db.read_bytes()==baseline


def test_both_legacy_grdp_columns_are_read_even_without_price_label(tmp_path,monkeypatch):
    db=tmp_path/'app.db';c=mo(db)
    c.execute("INSERT INTO economy(province_code,year,population,grdp_so_sanh,grdp_hien_hanh,source) VALUES('01',2024,8500000,100,200,'official')")
    c.commit();c.close();monkeypatch.setenv('VNGIS_DB',str(db))
    client=TestClient(app)
    for _ in range(2):
        data=client.get('/api/panel?province_code=01&moc=2024,2024-07&chi_so=grdp_so_sanh,grdp_hien_hanh').json()
        assert [r['gia_tri'] for r in data['dong']]==[[100,None],[200,None]]
        # An empty modern table must not make genuine legacy values disappear.
        from backend.data.dataset import migrate_demo
        with sqlite3.connect(db) as c:migrate_demo(c)
    row=client.get('/api/demo/economy?province_code=01&nam_tu=2024&nam_den=2024').json()['dong'][0]
    assert row['grdp_so_sanh']==100 and row['grdp_hien_hanh']==200
