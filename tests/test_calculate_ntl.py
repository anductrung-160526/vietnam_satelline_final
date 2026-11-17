"""Ảnh tổng hợp nhỏ với kết quả biết trước; kiểm cả luồng CSV -> SQLite."""
import csv

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from backend.data.calculate_ntl import calculate, ntl_stats, read_manifest, write_tables
from backend.data.build_indices import build


def image(tmp_path, name, values, crs='EPSG:6933'):
    path = tmp_path/name
    data = np.asarray(values, dtype='float32')
    with rasterio.open(path, 'w', driver='GTiff', width=data.shape[1], height=data.shape[0],
                       count=1, dtype='float32', crs=crs, nodata=-9999,
                       transform=from_origin(0, 2000, 1000, 1000)) as dst:
        dst.write(data, 1)
    return path


def record(path, year=2024, month=0, source='VIIRS'):
    return dict(province_code='01', province_name='Hà Nội', year=year,
                month=month, source=source, path=path, area_km2=10)


def test_known_pixel_statistics_and_invalid_values(tmp_path):
    path = image(tmp_path, 'stats.tif', [[0, .25, .5, 1.5], [2, -9999, np.nan, np.inf]])
    stats = ntl_stats(path, 1.5, .5)
    assert stats['valid_pixels'] == 5
    assert stats['sol'] == 4
    assert stats['sol_raw'] == 4.25
    assert stats['background_pixels'] == 2
    assert stats['lit_pixels'] == 2
    assert stats['lit_area_km2'] == 2
    assert stats['rad_mean'] == pytest.approx(.85)
    assert stats['rad_std'] == pytest.approx(np.std([0, .25, .5, 1.5, 2]), abs=1e-6)
    with rasterio.open(path, 'r+') as dst:
        dst.write_mask(np.array([[255, 255, 255, 0], [255, 255, 255, 255]], dtype='uint8'))
    assert ntl_stats(path, 1.5, .5)['sol'] == 2.5


def test_empty_raster_is_missing_not_zero(tmp_path):
    rows = calculate([record(image(tmp_path, 'empty.tif', [[-9999, np.nan]]))])['ntl_annual']
    assert rows[0]['sol'] is None
    assert rows[0]['sol_density'] is None
    assert rows[0]['obs_status'] == 'L'
    assert rows[0]['status'] == 'INSUFFICIENT_QUALITY'


def test_monthly_calendar_gap_and_year_boundary(tmp_path):
    path = image(tmp_path, 'monthly.tif', [[2]])
    items = [record(path, 2023, 10), record(path, 2023, 12), record(path, 2024, 1), record(path, 2024, 3)]
    result = calculate(items)['ntl_monthly']
    assert result[1]['sol_change_mom_pct'] is None
    assert result[2]['sol_change_mom_pct'] == 0
    assert result[3]['sol_change_mom_pct'] is None
    # October's large value must not leak into January's three calendar months.
    items[0]['path'] = image(tmp_path, 'large.tif', [[200]])
    assert calculate(items)['ntl_monthly'][2]['sol_ma3'] == 2


def test_overlap_and_sensor_transition(tmp_path):
    path = image(tmp_path, 'annual.tif', [[10]])
    rows = [record(path, 2013, source='DMSP'), record(path, 2013), record(path, 2014)]
    tables = calculate(rows)
    assert len(tables['ntl_annual']) == 2
    assert tables['ntl_overlap_2013'][0]['sol_viirs'] == 10
    assert tables['ntl_annual'][1]['sol_change_pct'] is None
    assert tables['ntl_annual'][1]['obs_status'] == 'B'
    assert all(r['calibration'] == 'PENDING' for r in tables['ntl_annual'])


def test_export_import_keeps_columns_and_province_code(tmp_path):
    path = image(tmp_path, 'input.tif', [[2, 4]])
    root = tmp_path/'data'
    output = root/'VN_NTL_Panel_2004_2025'/'data_processed'
    tables = calculate([record(path), record(path, month=1)])
    write_tables(tables, output)
    db = tmp_path/'app.db'
    report = build(root, db, repo_fallback=False)
    assert report['ntl_annual']['rows'] == 1
    assert report['ntl_monthly']['rows'] == 1
    import sqlite3
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT province_code, sol, sol_density, lit_area_pct FROM ntl_annual').fetchone() == ('01', 6, .6, 20)
    with pytest.raises(FileExistsError):
        write_tables(tables, output)


def test_manifest_relative_paths_and_duplicates(tmp_path):
    path = image(tmp_path, 'input.tif', [[2]])
    manifest = tmp_path/'images.csv'
    row = dict(record(path.name))
    with manifest.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    assert read_manifest(manifest)[0]['path'] == path
    with manifest.open('a', newline='', encoding='utf-8') as stream:
        csv.DictWriter(stream, fieldnames=list(row)).writerow(row)
    with pytest.raises(ValueError, match='trùng ảnh'):
        read_manifest(manifest)


def test_unknown_crs_rejected(tmp_path):
    path = image(tmp_path, 'no_crs.tif', [[2]], crs=None)
    with pytest.raises(ValueError, match='CRS'):
        ntl_stats(path, 1.5, .5)


def test_cloud_quality_and_real_zero(tmp_path):
    path = image(tmp_path, 'zero.tif', [[0]])
    with rasterio.open(path, 'r+') as dst:
        dst.update_tags(CF_CVG_MEAN='1.5')
    row = calculate([record(path, month=1)])['ntl_monthly'][0]
    assert row['sol'] == 0
    assert row['sol_density'] == 0
    assert row['status'] == 'OK'
    assert row['obs_status'] == 'U'
