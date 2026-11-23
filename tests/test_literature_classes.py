"""Ngưỡng tài liệu, diện tích độc lập ngưỡng pixel sáng, xuất bản cùng nguồn F."""
import json
from pathlib import Path
import sqlite3

import pytest
import rasterio
from fastapi.testclient import TestClient

from test_demo_view import make_raster
from test_integration_f import integrated
from test_spatial_p1 import spatial_fixture
from backend.api.main import app
from backend.core.light_classification import BREAKS, METHOD_VERSION
from backend.data.build_light_classes import classify_image, saved_areas
from backend.data.update_light_classes import update
from backend.data.dataset import sha256, signature_status


def test_exact_thresholds_and_lit_area_are_distinct(tmp_path):
    source=tmp_path/'radiance.tif';target=tmp_path/'classes.tif'
    make_raster(source,[[0,.49,.5,1.49,1.5,1.99,2,9.99,10,19.99,20,100,-9999]])
    classify_image(source,target,BREAKS,0)
    with rasterio.open(target) as image:
        assert image.read(1).tolist()==[[0,0,1,1,1,1,2,2,3,3,4,4,255]]
    result=saved_areas(target,source,BREAKS,0,True)
    assert result['areas']==[2,4,2,2,2]
    assert result['valid_area_km2']==12 and result['lit_area_km2']==8
    assert sum(result['areas'][2:])==6  # >=2 khác diện tích pixel sáng >=1,5.


def table_rows(db):
    with sqlite3.connect(db) as connection:
        return {table:connection.execute(f'SELECT * FROM {table} ORDER BY 1,2').fetchall()
                for table in ('ntl_annual','ntl_monthly','economy_prices','demo_result','demo_schema_meta')}


def test_publish_changes_only_classification_and_verifies_exports(integrated):
    db,fixed,verified,model,_=integrated
    client=TestClient(app)
    old=client.get('/api/demo/province?province_code=01&nam=2022').json()
    assert old['class_status']=='ready' and not old['classification_current']
    before=table_rows(db)
    old_class=Path(old['class_asset']['path']);old_hash=sha256(old_class)
    result=update(db.parent,db,publish=True,area_model=model)
    assert result['published'] and result['backup'] and result['images']==13
    assert result['dataset_id']==verified['dataset_id'] and result['breaks']==BREAKS
    assert before==table_rows(db) and sha256(old_class)==old_hash
    data=client.get('/api/demo/province?province_code=01&nam=2022').json()
    assert data['classification_current']
    assert [r['lower_bound'] for r in data['classes']]==[0,.5,2,10,20]
    assert data['class_summary']['method_version']==METHOD_VERSION
    assert data['class_summary']['reference_year']==0
    assert data['class_asset']['verification_status']=='verified'
    assert data['snapshot_id']==old['snapshot_id']
    with sqlite3.connect(db) as connection:
        check=json.loads(connection.execute("SELECT payload FROM demo_asset_check WHERE province_code='01' AND year=2022 AND month=0 AND kind='classes'").fetchone()[0])
    assert signature_status(check['source'])==signature_status(check['export'])=='ready'
    csv=client.get('/api/demo/classes.csv?province_code=01&nam=2022')
    assert csv.status_code==200 and '20.0' in csv.content.decode('utf-8-sig')
    method=Path(result['classification']['method'])
    assert json.loads(method.read_text(encoding='utf-8'))['status']=='literature_based'
    # Tiếp tục một lượt tài liệu không đổi ảnh, không quay lại bộ P50/P90.
    again=update(db.parent,db,publish=False,area_model=model,resume_dir=method.parent)
    assert again['classification']['reused_images']==13 and table_rows(db)==before


def test_classification_dry_run_keeps_original_database(integrated):
    db,_,_,model,_=integrated
    before=sha256(db)
    result=update(db.parent,db,publish=False,area_model=model)
    assert not result['published'] and result['backup'] is None
    assert sha256(db)==before


def test_updating_classes_preserves_existing_verified_moran(spatial_fixture):
    from backend.data.build_spatial import build
    root,db,report,model=spatial_fixture
    build(root,report,db,2020,2021,99,7,publish=True,area_model=model,expected_count=4)
    client=TestClient(app)
    old=client.get('/api/spatial?year_start=2020&year_end=2021').json()
    assert old['status']=='ready'
    update(root,db,publish=True,area_model=model)
    assert client.get('/api/spatial?year_start=2020&year_end=2021').json()==old


def test_changed_radiance_source_blocks_publish(integrated):
    import os
    db,_,_,model,_=integrated
    data=TestClient(app).get('/api/demo/province?province_code=01&nam=2022').json()
    source=Path(data['processed_asset']['path']);stat=source.stat()
    os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns+1_000_000_000))
    before=sha256(db)
    with pytest.raises(ValueError,match='chưa khớp'):
        update(db.parent,db,publish=True,area_model=model)
    assert sha256(db)==before
