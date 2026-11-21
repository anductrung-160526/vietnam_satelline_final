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


def test_dictionary_fields_and_different_tnl_sol_series(tmp_path):
    from backend.data.calculate_ntl import NIGHT_DATA_FIELDS, NIGHT_ECONOMY_FIELDS
    first = image(tmp_path, 'first.tif', [[.25, 2]])
    second = image(tmp_path, 'second.tif', [[.25, 4]])
    tables = calculate([record(first, month=1), record(second, month=3)])
    data = tables['night_data']
    economy = tables['night_economy']
    assert data[0]['gid_1'] == 'VNM.27_1'
    assert data[0]['total_pixels'] == 2
    assert data[0]['tnl'] == economy[0]['sol_raw'] == 2.25
    assert economy[0]['sol'] == 2
    assert data[1]['tnl_ma3'] == 3.25
    # Task 3 compares observation rows across the missing February.
    assert data[1]['tnl_mom_growth_pct'] == pytest.approx(88.8889)
    # The app calendar series still leaves the gap empty.
    assert tables['ntl_monthly'][1]['sol_change_mom_pct'] is None
    assert data[0]['avg_rad'].endswith('#band=1')
    assert data[0]['cf_cvg'] is None  # A one-band image cannot invent this pixel array.
    assert economy[0]['population'] is None
    assert economy[0]['sol_per_capita'] is None
    assert economy[0]['light_basis'] == 'sol'
    assert set(NIGHT_DATA_FIELDS) <= data[0].keys()
    assert set(NIGHT_ECONOMY_FIELDS) <= economy[0].keys()
    write_tables(tables, tmp_path/'output')
    with (tmp_path/'output/night_data.csv').open(encoding='utf-8-sig') as stream:
        assert next(csv.reader(stream)) == list(NIGHT_DATA_FIELDS)


def test_two_band_cloud_mean_and_empty_quality(tmp_path):
    path = tmp_path/'two_bands.tif'
    with rasterio.open(path, 'w', driver='GTiff', width=3, height=1, count=2,
                       dtype='float32', crs='EPSG:6933', nodata=-9999,
                       transform=from_origin(0, 1000, 1000, 1000)) as dst:
        dst.write(np.array([[[1, 2, -9999]], [[2, 4, 100]]], dtype='float32'))
        dst.set_band_description(1, 'avg_rad')
        dst.set_band_description(2, 'cf_cvg')
    tables = calculate([record(path, month=1)])
    assert tables['night_data'][0]['cloud_free_obs'] == 3
    assert tables['night_data'][0]['cf_cvg'].endswith('#band=2')


def test_economy_formulas_and_known_gdp_regression(tmp_path):
    records = []
    economy = {}
    for i in range(11):
        year = 2014+i
        light = float(i+2)
        records.append(record(image(tmp_path, f'{year}.tif', [[light]]), year))
        economy[('01', year)] = {'population': 100, 'gdp': 3*light**2,
                                 'price_basis': 'so_sanh', 'economy_source': 'official'}
    tables = calculate(records, economy=economy)
    rows = tables['night_economy']
    assert rows[0]['sol_per_capita'] == .02
    assert rows[0]['light_gdp_elasticity'] is None
    assert rows[1]['light_gdp_elasticity'] == .4  # 50% light / 125% GDP
    for row in rows:
        assert row['predicted_gdp'] == pytest.approx(row['gdp'])
    assert tables['calculation_models'][0]['beta'] == pytest.approx(2)
    # Nominal or unknown price basis must not be used for regression/elasticity.
    for item in economy.values():
        item['price_basis'] = 'hien_hanh'
    rows = calculate(records, economy=economy)['night_economy']
    assert all(r['predicted_gdp'] is None and r['light_gdp_elasticity'] is None for r in rows)


def test_calibration_requires_30_provinces_and_preserves_raw(tmp_path):
    import json
    from pathlib import Path
    config = Path(__file__).parents[1]/'backend/core/ranh_gioi/config/danh_muc_tinh.json'
    provinces = json.loads(config.read_text())[:30]
    records = []
    for i, province in enumerate(provinces):
        light = float(i+2)
        for source, year, value in [('DMSP', 2013, light), ('VIIRS', 2013, 2*light**1.5),
                                     ('VIIRS', 2014, 2*light**1.5*1.1)]:
            r = record(image(tmp_path, f'{i}_{year}_{source}.tif', [[value]]), year, source=source)
            r.update(province_code=province['ma_tinh'], province_name=province['ten_tinh'])
            records.append(r)
    with pytest.raises(ValueError, match='30 tỉnh'):
        calculate(records[:3], calibrate=True)
    tables = calculate(records, calibrate=True)
    first = tables['night_economy'][0]
    second = tables['night_economy'][1]
    assert first['sol'] == 2  # Never overwrite the original DMSP total.
    assert first['sol_cal'] == pytest.approx(2*2**1.5, abs=1e-3)
    assert first['sol_density'] == pytest.approx(first['sol_cal']/10, abs=1e-4)
    assert second['sol_change_pct'] == pytest.approx(10, abs=.02)
    assert first['light_basis'] == 'sol_cal'
    assert tables['ntl_annual'][0]['sol_density'] == .2  # app's original column stays raw
    assert tables['ntl_panel'][0]['calibration'] != 'PENDING'


def test_read_economy_and_duplicate_input(tmp_path):
    from backend.data.calculate_ntl import read_economy
    path = tmp_path/'economy.csv'
    path.write_text('province_code,year,population,grdp,grdp_price_basis,source\n'
                    '01,2024,100,200,so_sanh,official\n')
    assert read_economy(path)[('01', 2024)]['gdp'] == 200
    with path.open('a') as stream:
        stream.write('01,2024,100,200,so_sanh,official\n')
    with pytest.raises(ValueError, match='Trùng dòng kinh tế'):
        read_economy(path)


def test_command_line_exports_and_rejects_overwrite(tmp_path):
    import subprocess
    import sys
    path = image(tmp_path, 'cli.tif', [[.25, 2]])
    manifest = tmp_path/'images.csv'
    row = record(path)
    with manifest.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    output = tmp_path/'results'
    command = [sys.executable, '-m', 'backend.data.calculate_ntl',
               '--manifest', str(manifest), '--output', str(output)]
    run = subprocess.run(command, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    with (output/'night_economy.csv').open(encoding='utf-8-sig') as stream:
        result = next(csv.DictReader(stream))
    assert result['sol_raw'] == '2.25' and result['sol'] == '2.0'
    assert result['sol_per_capita'] == ''
    original = (output/'night_economy.csv').read_bytes()
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert (output/'night_economy.csv').read_bytes() == original
