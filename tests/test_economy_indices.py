"""Phần E: hai giá riêng biệt, dữ liệu thiếu, mô hình biết trước và CSV→API."""
import csv
import sqlite3

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.data.calculate_ntl import calculate, write_tables
from backend.data.economy_indices import read_prices, read_image_quality
from backend.data.load_demo import load


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


@pytest.fixture
def inputs(tmp_path):
    records, prices = [], []
    for year in range(2013, 2025):
        light = year-2012
        for basis in ('so_sanh', 'hien_hanh'):
            prices.append(dict(province_code='01', year=year, population=100,
                               grdp=3*light**2 if basis == 'so_sanh' else 5*light**3,
                               grdp_price_basis=basis, unit='ty_vnd', price_base_year=2010 if basis == 'so_sanh' else '',
                               source='official', is_provisional=int(year == 2024), quality_flags='SOURCE_REVIEW' if year == 2024 else ''))
        if year < 2014:
            continue
        path = tmp_path/f'{year}.tif'
        with rasterio.open(path, 'w', driver='GTiff', width=2, height=1, count=1,
                           dtype='float32', nodata=-9999, crs='EPSG:6933',
                           transform=from_origin(0, 1000, 1000, 1000)) as image:
            image.write(np.array([[.25, light]], dtype='float32'), 1)
        records.append(dict(province_code='01', province_name='Hà Nội', year=year, month=0,
                            source='VIIRS', path=path, area_km2=10))
    records.append(dict(records[-1], month=1))
    price_file = tmp_path/'grdp_all_prices.csv'
    write_csv(price_file, prices)
    return records, prices, price_file


def test_two_prices_known_models_and_annual_monthly_separation(inputs):
    records, raw_prices, file = inputs
    tables = calculate(records, economy_prices=read_prices(file))
    result = {(r['year'], r['month'], r['grdp_price_basis']): r for r in tables['night_economy']}
    assert len(result) == 26  # 12 annual years × 2 + one month × 2.
    assert len(tables['night_data']) == 12  # one per image, no duplication by price.
    models = {r['price_basis']:r for r in tables['calculation_models']}
    assert models['so_sanh']['n'] == models['hien_hanh']['n'] == 11
    assert models['so_sanh']['beta'] == pytest.approx(2)
    assert models['hien_hanh']['beta'] == pytest.approx(3)
    for basis in ['so_sanh', 'hien_hanh']:
        for year in range(2014, 2025):
            row = result[year, 0, basis]
            assert row['predicted_gdp'] == pytest.approx(row['gdp'])
            assert row['sol_raw'] == row['sol']+.25
            assert row['sol_density'] == pytest.approx(row['sol']/10)
            assert row['sol_per_capita'] == pytest.approx(row['sol']/100)
        assert result[2013, 0, basis]['sol'] is None
        assert result[2013, 0, basis]['gdp'] is not None
        assert result[2024, 1, basis]['gdp'] == result[2024, 0, basis]['gdp']
        assert result[2024, 1, basis]['predicted_gdp'] is None
        assert result[2024, 1, basis]['light_gdp_elasticity'] is None
    assert result[2015, 0, 'so_sanh']['light_gdp_elasticity'] == .4
    assert result[2015, 0, 'hien_hanh']['light_gdp_elasticity'] == pytest.approx(.210526)
    assert result[2024, 0, 'so_sanh']['is_provisional'] == 1
    assert result[2024, 0, 'so_sanh']['quality_flags'] == 'SOURCE_REVIEW'


def test_missing_price_population_and_common_sample(inputs):
    records, prices, file = inputs
    for row in prices:
        row['population'] = ''
        if row['year'] == 2014 and row['grdp_price_basis'] == 'hien_hanh':
            row['grdp'] = ''
    write_csv(file, prices)
    tables = calculate(records, economy_prices=read_prices(file))
    models = tables['calculation_models']
    assert len(models) == 2 and {r['n'] for r in models} == {10}
    row = next(r for r in tables['night_economy'] if r['year'] == 2014 and r['grdp_price_basis'] == 'hien_hanh')
    assert row['gdp'] is None and row['predicted_gdp'] == pytest.approx(40)
    assert not row['paired']
    assert all(r['sol_per_capita'] is None for r in tables['night_economy'])
    with pytest.raises(ValueError, match='Trùng'):
        write_csv(file, prices+[prices[0]])
        read_prices(file)


def test_price_units_population_conflict_and_fake_exclusion(inputs):
    records, prices, file = inputs
    prices[0]['unit'] = 'usd'
    write_csv(file, prices)
    with pytest.raises(ValueError, match='tỷ đồng'):read_prices(file)
    prices[0]['unit'] = 'ty_vnd';prices[1]['population'] = 200
    write_csv(file, prices)
    with pytest.raises(ValueError, match='Dân số khác nhau'):read_prices(file)
    prices[1]['population'] = 100
    for row in prices: row['source'] = 'GIA_LAP'
    write_csv(file, prices)
    tables = calculate(records, economy_prices=read_prices(file))
    assert tables['calculation_models'] == []
    assert not any(r['paired'] for r in tables['night_economy'])


def test_quality_changed_support_and_2010_transition(inputs):
    records, prices, file = inputs
    quality = {('01', 2014, 0):dict(valid_pixels='2', valid_area_pct='20', valid_area_km2='2')}
    tables = calculate(records, economy_prices=read_prices(file), image_quality=quality)
    row = next(r for r in tables['night_economy'] if r['year'] == 2014)
    assert 'PART_D_NOT_LINKED' not in row['image_quality_flags']
    quality[('01', 2014, 0)]['valid_pixels'] = '3'
    with pytest.raises(ValueError, match='khác báo cáo D'):
        calculate(records, economy_prices=read_prices(file), image_quality=quality)
    with rasterio.open(records[0]['path'], 'r+') as image:
        image.write_mask(np.array([[0, 255]], dtype='uint8'))
    changed = calculate(records, economy_prices=read_prices(file))
    row = next(r for r in changed['night_economy'] if r['year'] == 2015)
    assert 'VALID_PIXEL_COUNT_CHANGED' in row['image_quality_flags']
    assert row['comparison_note']
    first = dict(records[0], year=2009, source='DMSP')
    second = dict(first, year=2010)
    legacy = calculate([first, second])
    assert legacy['ntl_annual'][1]['sol_change_pct'] is None
    assert legacy['ntl_annual'][1]['sol_change_cal_pct'] is None
    assert legacy['night_economy'][1]['sol_change_pct'] is None


def test_two_price_export_load_and_filtered_api(inputs, tmp_path, monkeypatch):
    records, prices, file = inputs
    prepared = tmp_path/'prepared';prepared.mkdir()
    write_csv(prepared/'grdp_all_prices.csv', prices)
    write_csv(prepared/'manifest_candidates.csv', records)
    (prepared/'image_inventory.csv').write_text('province_code,path\n', encoding='utf-8')
    tables = calculate(records, economy_prices=read_prices(file))
    output = tmp_path/'output'
    write_tables(tables, output)
    db = tmp_path/'app.db'
    result = load(tmp_path, prepared, db, output)
    assert result['dictionary_results'] == 38
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT COUNT(*) FROM economy_prices').fetchone()[0] == 24
        assert connection.execute("SELECT COUNT(*) FROM demo_result WHERE table_name='night_economy'").fetchone()[0] == 26
    monkeypatch.setenv('VNGIS_DB', str(db))
    client = TestClient(app)
    so = client.get('/api/demo/economy?province_code=01&nam_tu=2024&nam_den=2024').json()['dong'][0]
    hh = client.get('/api/demo/economy?province_code=01&nam_tu=2024&nam_den=2024&price_basis=hien_hanh').json()['dong'][0]
    assert so['predicted_gdp'] == pytest.approx(3*12**2)
    assert hh['predicted_gdp'] == pytest.approx(5*12**3)
    assert so['model_training_period'] == '2014-2024' and so['model_n'] == 11
    assert so['image_quality_flags'] and so['quality_flags'] == 'SOURCE_REVIEW'
    body = client.get('/api/demo/economy.csv?province_code=01&nam_tu=2024&nam_den=2024&price_basis=hien_hanh').content.decode('utf-8-sig')
    row = next(csv.DictReader(body.splitlines()))
    assert 'derived_price_basis' not in row and 'predicted_gdp' not in row and float(row['sol'])==12
    # Duplicate result keys must fail before overwriting the database.
    duplicate = tables['night_economy'][0]
    with (output/'night_economy.csv').open('a', encoding='utf-8-sig', newline='') as stream:
        fields = list(csv.DictReader((output/'night_economy.csv').open(encoding='utf-8-sig')).fieldnames)
        csv.DictWriter(stream, fieldnames=fields).writerow(duplicate)
    with pytest.raises(ValueError, match='trùng khóa kết quả'):
        load(tmp_path, prepared, db, output)


def test_cli_two_prices_quality_and_no_overwrite(inputs, tmp_path):
    import subprocess
    import sys
    records, prices, file = inputs
    manifest = tmp_path/'manifest.csv'
    write_csv(manifest, records)
    quality = tmp_path/'quality.csv'
    write_csv(quality, [dict(province_code=r['province_code'], year=r['year'], month=r['month'],
                           valid_pixels=2, valid_area_km2=2, valid_area_pct=20) for r in records])
    assert len(read_image_quality(quality)) == len(records)
    output = tmp_path/'results'
    command = [sys.executable, '-m', 'backend.data.calculate_ntl', '--manifest', str(manifest),
               '--economy-prices', str(file), '--class-validation', str(quality), '--output', str(output)]
    run = subprocess.run(command, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    rows = list(csv.DictReader((output/'night_economy.csv').open(encoding='utf-8-sig')))
    assert len(rows) == 26 and {r['grdp_price_basis'] for r in rows} == {'so_sanh', 'hien_hanh'}
    assert all('PART_D_NOT_LINKED' not in r['image_quality_flags'] for r in rows if 'MISSING_IMAGE' not in r['image_quality_flags'])
    before = (output/'night_economy.csv').read_bytes()
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert (output/'night_economy.csv').read_bytes() == before


def test_empty_month_preserves_grdp_but_does_not_become_zero_light(inputs, tmp_path):
    records, prices, file = inputs
    empty = tmp_path/'empty.tif'
    with rasterio.open(records[-1]['path']) as source:
        profile = source.profile
    with rasterio.open(empty, 'w', **profile) as image:
        image.write(np.array([[-9999, -9999]], dtype='float32'), 1)
    records[-1] = dict(records[-1], path=empty)
    tables = calculate(records, economy_prices=read_prices(file))
    months = [r for r in tables['night_economy'] if r['month']]
    assert len(months) == 2
    for row in months:
        assert row['gdp'] is not None and row['sol'] is None and row['sol_raw'] is None
        assert 'NO_VALID_PIXELS' in row['image_quality_flags']
        assert row['predicted_gdp'] is None
    report = tables['economy_validation'][0]
    assert report['empty_images'] == 1 and report['empty_image_result_rows'] == 2
