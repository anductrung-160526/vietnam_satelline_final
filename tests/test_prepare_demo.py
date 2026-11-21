import csv
import json
from pathlib import Path

import numpy as np
import openpyxl
import pytest
import rasterio
from rasterio.transform import from_origin

from backend.data.prepare_grdp import prepare_grdp, provinces
from backend.data.prepare_demo import inventory, image_identity, verify_annual


def make_image(path, values, year=2020, month=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.array(values, dtype='float32')
    with rasterio.open(path, 'w', driver='GTiff', height=data.shape[0], width=data.shape[1],
                       count=1, dtype='float32', crs='EPSG:4326', nodata=-9999,
                       transform=from_origin(105, 22, .01, .01)) as dst:
        dst.write(data, 1)
        dst.update_tags(SOURCE='VIIRS_MONTHLY' if month else 'MEDIAN_OF_FILTERED_VIIRS_MONTHS',
                        PERIOD=f'{year}-{month:02}' if month else str(year),
                        FILTER='cf_cvg=0->NoData; negative->0', MONTHS_USED='2')


def test_grdp_63_provinces_both_prices_and_missing(tmp_path):
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, basis in [('GRDP_So Sánh', 'so_sanh'), ('GRDP_Hiện hành', 'hien_hanh')]:
        s = workbook.create_sheet(name)
        s.append(['Title'])
        s.append(['Source'])
        s.append(['', 'Loại', '2015', 'Sơ bộ 2024'] if basis == 'so_sanh' else ['', '2015', 'Sơ bộ 2024'])
        for i, province in enumerate(provinces()):
            label = 'TP.Hồ Chí Minh' if province['ma_tinh'] == '79' else province['ten_tinh']
            if basis == 'so_sanh':
                s.append([label, 'Tổng số', 100+i, 104+i])
                for sector, value in [('Nông nghiệp', 25), ('Công nghiệp', 25), ('Dịch vụ', 25), ('Thuế', 25+i)]:
                    s.append([label, sector, value, value+1])
            else:
                s.append([label, 'N/a' if i == 0 else 200+i, 204+i])
    source = tmp_path/'source.xlsx'
    workbook.save(source)
    output = tmp_path/'prepared'
    summary = prepare_grdp(source, output)
    assert summary['rows'] == 252 and summary['missing_values'] == 1
    with (output/'grdp_all_prices.csv').open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    assert len({(r['province_code'], r['year'], r['grdp_price_basis']) for r in rows}) == 252
    assert all(r['is_provisional'] == '1' for r in rows if r['year'] == '2024')
    assert next(r for r in rows if r['province_code'] == '01' and r['year'] == '2015' and r['grdp_price_basis'] == 'hien_hanh')['grdp'] == ''
    assert next(r for r in rows if r['province_code'] == '79')['province_name'] == next(p['ten_tinh'] for p in provinces() if p['ma_tinh'] == '79')


def test_manifest_no_duplicate_choice_and_mask_failure(tmp_path):
    root = tmp_path/'data'
    a = root/'01_ha_noi_VIIRS_2020-01_filtered.tif'
    make_image(a, [[0, 2]], month=1)
    # Polygon covers only the first pixel: zero inside valid, brightness outside invalid.
    feature = {'geometry': {'type': 'Polygon', 'coordinates': [[[105,21.99],[105.01,21.99],[105.01,22],[105,22],[105,21.99]]]}}
    output = tmp_path/'report'
    output.mkdir()
    catalog = {'01': provinces()[0]}
    summary = inventory(root, output, catalog, {'01': feature}, {'01': 10}, [2020], {'01'})
    assert summary['files'] == 1 and summary['manifest_candidates'] == 0
    with (output/'image_inventory.csv').open(encoding='utf-8-sig') as f:
        row = next(csv.DictReader(f))
    assert 'VALID_PIXELS_OUTSIDE_PROVINCE' in row['issues']
    assert json.loads(row['pixel_audit'])['valid_zero_pixels'] == 1
    # Without pixel sampling, duplicate candidates must be quarantined, not silently selected.
    b = root/'copy/01_ha_noi_VIIRS_2020-01_filtered.tif'
    make_image(b, [[0, 2]], month=1)
    summary = inventory(root, output, catalog, {}, {'01': 10}, [2020], set())
    assert summary['manifest_candidates'] == 0
    assert 'DUPLICATE_CANDIDATE' in (output/'image_inventory.csv').read_text(encoding='utf-8-sig')


def test_pixel_median_is_not_median_of_sols(tmp_path):
    first = tmp_path/'01_VIIRS_2020-01.tif'
    second = tmp_path/'01_VIIRS_2020-02.tif'
    annual = tmp_path/'01_VIIRS_2020.tif'
    make_image(first, [[1, -9999]], month=1)
    make_image(second, [[3, 10]], month=2)
    make_image(annual, [[2, 10]])
    assert verify_annual(annual, [first, second]).startswith('PASS_PIXEL_MEDIAN')
    make_image(annual, [[2, 5]])
    assert verify_annual(annual, [first, second]) == 'FAIL_PIXEL_MEDIAN'


def test_identity_rejects_ambiguous_and_nonstatistical_codes():
    catalog = {p['ma_tinh']: p for p in provinces()}
    with pytest.raises(ValueError):
        image_identity(Path('01_ha_noi/27_bac_ninh_VIIRS_2020.tif'), {}, catalog)
    with pytest.raises(ValueError):
        image_identity(Path('03_unknown_VIIRS_2020.tif'), {}, catalog)


def test_missing_data_root_is_reported_not_ready(tmp_path):
    output = tmp_path/'report'; output.mkdir()
    summary = inventory(tmp_path/'missing', output, {'01': provinces()[0]}, {}, {}, [2020,2021], {'01'})
    assert summary['files'] == 0 and summary['annual_candidate_province_years'] == 0
    assert summary['expected_province_years'] == 2
    assert 'DATA_ROOT_NOT_ACCESSIBLE' in (output/'image_errors.csv').read_text()


def test_environment_snapshot_preserves_staged_and_worktree(tmp_path, monkeypatch):
    import subprocess
    from backend.data import prepare_demo
    repo = tmp_path/'repo'; repo.mkdir()
    def command(*args):
        return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, check=True).stdout
    command('init', '-b', 'night-app')
    command('config', 'user.name', 'Test')
    command('config', 'user.email', 'test@example.invalid')
    file = repo/'file.txt'; file.write_text('original\n')
    command('add', 'file.txt'); command('commit', '-m', 'initial')
    command('remote', 'add', 'origin', str(repo))
    file.write_text('staged\n'); command('add', 'file.txt')
    file.write_text('worktree\n')
    (repo/'untracked.txt').write_text('not in patch')
    before = command('status', '--short')
    monkeypatch.setattr(prepare_demo, 'REPO', repo)
    output = tmp_path/'output'; output.mkdir()
    report = prepare_demo.environment_report(output)
    assert report['branch'] == 'night-app' and report['head_matches_remote']
    assert command('status', '--short') == before
    assert file.read_text() == 'worktree\n'
    assert b'+worktree' in (output/'git_backup/working_changes.patch').read_bytes()
    assert b'+staged' in (output/'git_backup/staged_changes.patch').read_bytes()
