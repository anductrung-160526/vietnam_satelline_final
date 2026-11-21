"""Phần A: kiểm kê ảnh thật và GRDP, không thay ảnh, không pull/reset Git.

Windows: python -m backend.data.prepare_demo --root E:\\SatelliteData
Kết quả: <root>/_demo_preparation/<thời điểm>/; mỗi lần chạy tạo thư mục riêng.
Ảnh mẫu được kiểm tra toàn bộ pixel; các ảnh khác chỉ đọc metadata.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import warnings

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from shapely.geometry import shape

from .calculate_ntl import windows
from .prepare_grdp import provinces, prepare_grdp, write_csv
from backend.core.ranh_gioi.boundaries import load_boundaries

REPO = Path(__file__).resolve().parents[2]


def git(*args):
    run = subprocess.run(['git', '-C', str(REPO), *args], capture_output=True)
    if run.returncode:
        raise ValueError(run.stderr.decode('utf-8', errors='replace'))
    return run.stdout.decode('utf-8', errors='replace').strip()


def environment_report(output):
    """Sao lưu diff của cả staged/worktree trước khi làm việc; không bỏ sửa đổi nào."""
    backup = output/'git_backup'
    backup.mkdir()
    for filename, args in [('working_changes.patch', ('diff', '--binary', 'HEAD')),
                           ('staged_changes.patch', ('diff', '--binary', '--cached')),
                           ('status.txt', ('status', '--short'))]:
        # Ghi bytes để patch có thể áp lại và không bị thay xuống dòng trên Windows.
        run = subprocess.run(['git', '-C', str(REPO), *args], capture_output=True)
        if run.returncode:
            raise ValueError('Không sao lưu được Git; dừng trước khi quét dữ liệu.')
        (backup/filename).write_bytes(run.stdout)
    versions = {}
    for package in ('rasterio', 'shapely', 'numpy', 'openpyxl', 'fastapi', 'uvicorn'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = 'MISSING'
    origin = git('remote', 'get-url', 'origin')
    from urllib.parse import urlsplit, urlunsplit
    parsed = urlsplit(origin)
    safe_origin = urlunsplit((parsed.scheme, parsed.hostname or '', parsed.path, '', '')) if parsed.scheme else origin
    try:
        remote = subprocess.run(['git', '-C', str(REPO), 'ls-remote', '--heads', 'origin', 'night-app'],
                                capture_output=True, text=True, timeout=30)
        remote_sha = remote.stdout.split()[0] if remote.returncode == 0 and remote.stdout.strip() else None
    except subprocess.TimeoutExpired:
        remote_sha = None
    report = {'origin': safe_origin, 'remote_night_app_sha': remote_sha,
              'head_matches_remote': git('rev-parse', 'HEAD') == remote_sha if remote_sha else None,
              'scope': 'machine_running_this_command', 'machine': platform.node(),
              'platform': platform.platform(), 'python': sys.version, 'python_executable': sys.executable,
              'repo': str(REPO), 'branch': git('branch', '--show-current'),
              'commit': git('rev-parse', 'HEAD'), 'versions': versions,
              'git_status': git('status', '--short'),
              'backup': str(backup),
              'backup_scope': 'tracked changes only; untracked files are listed in status.txt, not copied',
              'editor_tabs': 'NOT_VERIFIABLE: đóng tab chưa lưu trước khi cập nhật Git'}
    (output/'environment.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def boundary_areas(boundaries, metadata):
    """Chỉ dùng ranh giới GADM gốc đã xác minh SHA/crosswalk, không dùng bản web rút gọn."""
    found, info = load_boundaries({'boundaries': str(boundaries), 'boundary_metadata': str(metadata),
                                   'boundary_policy': 'gadm41_research'})
    areas = {code: shape(transform_geom('EPSG:4326', 'EPSG:6933', f['geometry'])).area/1e6
             for code, f in found.items()}
    return found, areas, info


def image_identity(path, tags, catalog):
    # Chấp nhận mã tỉnh thống kê đầu tên file/thư mục, không dùng mã thứ tự 1..63.
    codes = {m[1] for part in path.parts if (m := re.match(r'^(\d{2})_', part)) and m[1] in catalog}
    tagged_code = tags.get('province_code') or tags.get('ma_tinh')
    if tagged_code:
        codes.add(str(tagged_code).zfill(2))
    if len(codes) != 1 or not codes.issubset(catalog):
        raise ValueError('Không xác định được duy nhất mã tỉnh; cần đổi tên hoặc bổ sung tag province_code.')
    text = (tags.get('SOURCE', '')+' '+path.name).upper()
    source = 'VIIRS' if 'VIIRS' in text else 'DMSP' if 'DMSP' in text else None
    if source is None:
        raise ValueError('Không xác định được nguồn VIIRS/DMSP.')
    period = str(tags.get('PERIOD') or tags.get('YEAR') or path.name)
    match = re.search(r'(20\d{2})(?:-(0[1-9]|1[0-2]))?', period)
    if not match:
        raise ValueError('Không xác định được năm/tháng.')
    year, month = int(match[1]), int(match[2] or 0)
    if not 2004 <= year <= 2025 or (source == 'DMSP' and (month or year > 2013)) or (source == 'VIIRS' and year < 2013):
        raise ValueError('Năm/tháng không khớp phạm vi và nguồn ảnh.')
    return next(iter(codes)), year, month, source


def audit_pixels(image, feature):
    """Kiểm tra mọi pixel của ảnh mẫu: vùng ngoài tỉnh, zero hợp lệ, NoData, số âm."""
    polygon = transform_geom('EPSG:4326', image.crs, feature['geometry'])
    result = dict(valid_pixels=0, outside_valid_pixels=0, outside_zero_pixels=0,
                  valid_zero_pixels=0, negative_pixels=0, nonfinite_unmasked_pixels=0)
    for window in windows(image.height, image.width):
        values = image.read(1, window=window)
        unmasked = image.read_masks(1, window=window).astype(bool)
        finite = np.isfinite(values)
        valid = unmasked & finite & (values != -9999)
        inside = geometry_mask([polygon], out_shape=values.shape,
                               transform=image.window_transform(window), invert=True)
        result['valid_pixels'] += int(valid.sum())
        result['outside_valid_pixels'] += int((valid & ~inside).sum())
        result['outside_zero_pixels'] += int((valid & ~inside & (values == 0)).sum())
        result['valid_zero_pixels'] += int((valid & inside & (values == 0)).sum())
        result['negative_pixels'] += int((valid & (values < 0)).sum())
        result['nonfinite_unmasked_pixels'] += int((unmasked & ~finite).sum())
    return result


def verify_annual(annual_path, month_paths):
    """Đối chiếu ảnh năm với trung vị từng PIXEL của các ảnh tháng đã tìm được."""
    import contextlib
    with contextlib.ExitStack() as stack:
        annual = stack.enter_context(rasterio.open(annual_path))
        months = [stack.enter_context(rasterio.open(p)) for p in month_paths]
        if not months:
            return 'PENDING_NO_MONTHLY_IMAGES'
        if any((m.crs, m.transform, m.width, m.height) !=
               (annual.crs, annual.transform, annual.width, annual.height) for m in months):
            return 'PENDING_DIFFERENT_GRIDS'
        declared = annual.tags().get('MONTHS_USED')
        if declared is None or int(declared) != len(months):
            return 'PENDING_MONTH_COUNT_NOT_CONFIRMED'
        for window in windows(annual.height, annual.width):
            arrays = []
            for month in months:
                a = month.read(1, window=window).astype(float)
                valid = month.read_masks(1, window=window).astype(bool) & np.isfinite(a) & (a != -9999)
                arrays.append(np.where(valid, a, np.nan))
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)
                expected = np.nanmedian(np.stack(arrays), axis=0)
            actual = annual.read(1, window=window).astype(float)
            valid_actual = annual.read_masks(1, window=window).astype(bool) & np.isfinite(actual) & (actual != -9999)
            valid_expected = np.isfinite(expected)
            if not np.array_equal(valid_actual, valid_expected):
                return 'FAIL_VALID_MASK'
            if not np.allclose(actual[valid_actual], expected[valid_expected], atol=1e-4, rtol=1e-5):
                return 'FAIL_PIXEL_MEDIAN'
    return 'PASS_PIXEL_MEDIAN_FOR_DISCOVERED_MONTHS'



def excluded_raster_reason(path):
    """Phân loại ngoài phạm vi, không báo ảnh ngày/ảnh toàn quốc như lỗi ảnh tỉnh."""
    text = str(path).replace('\\', '/').lower()
    parts = text.split('/')
    name = parts[-1]
    if '_control' in parts or '.work' in parts or '.part.' in name or '.masked.' in name:
        return 'TEMPORARY_OR_CONTROL_FILE'
    if ('vn_landcover_panel_2004_2025' in parts or 'day' in parts
            or 'landsat' in text or 'sentinel2' in text):
        return 'DAYTIME_IMAGE'
    if 'cog' in parts or 'cogs' in parts or name.startswith('preview_'):
        return 'DISPLAY_COG_OR_PREVIEW'
    if 'tiles' in parts:
        return 'NATIONAL_TILE_NOT_PROVINCE_IMAGE'
    if re.match(r'^vn_.*(?:viirs|dmsp)', name):
        return 'NATIONAL_MOSAIC_NOT_PROVINCE_IMAGE'
    return None


def inventory(root, output, catalog, geometries, areas, years, sample_codes):
    records, errors, excluded = [], [], []
    if root.is_dir():
        files = sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in ('.tif', '.tiff', '.vrt')
                       and '_demo_preparation' not in p.parts)
    else:
        files = []
        errors.append({'path': str(root), 'reason': 'DATA_ROOT_NOT_ACCESSIBLE'})
    for path in files:
        # Ghi riêng ảnh ngoài phạm vi; file chưa nhận dạng vẫn phải báo lỗi.
        reason = excluded_raster_reason(path)
        if reason:
            excluded.append({'path': str(path), 'reason': reason})
            continue
        row = {'path': str(path.resolve()), 'province_code': '', 'province_name': '',
               'year': '', 'month': '', 'source': '', 'area_km2': '', 'issues': '',
               'crs': '', 'band_names': '', 'band_count': '', 'pixel_size': '', 'nodata': '',
               'scales': '', 'offsets': '', 'dtype': '', 'unit': '', 'filter_evidence': '', 'annual_evidence': '',
               'pixel_audit': 'NOT_SAMPLED', 'annual_pixel_check': 'NOT_SAMPLED'}
        issues = []
        try:
            with rasterio.open(path) as image:
                tags = image.tags()
                code, year, month, source = image_identity(path, tags, catalog)
                row.update(province_code=code, province_name=catalog[code]['ten_tinh'],
                           year=year, month=month, source=source, area_km2=areas.get(code, ''))
                row.update(crs=str(image.crs), band_names=json.dumps(image.descriptions),
                           band_count=image.count, pixel_size=json.dumps(image.res), nodata=str(image.nodata),
                           scales=json.dumps(image.scales), offsets=json.dumps(image.offsets),
                           dtype=json.dumps(image.dtypes), unit=tags.get('UNIT', ''))
                if image.nodata == 0:
                    issues.append('NODATA_ZERO_MASKS_VALID_DARK_PIXELS')
                if image.crs is None:
                    issues.append('MISSING_CRS')
                elif image.crs.to_epsg() != 4326 and not (image.crs.is_projected and image.crs.linear_units == 'metre'):
                    issues.append('UNSUPPORTED_CRS_FOR_CALCULATOR')
                if image.transform.b or image.transform.d:
                    issues.append('ROTATED_GRID')
                if any(s != 1 for s in image.scales) or any(o != 0 for o in image.offsets):
                    issues.append('NON_IDENTITY_SCALE_OFFSET')
                if image.count != 1 and not (image.count == 2 and image.descriptions == ('avg_rad', 'cf_cvg')):
                    issues.append('UNSUPPORTED_BANDS')
                if not row['area_km2']:
                    issues.append('MISSING_VERIFIED_PROVINCE_AREA')
                if source == 'VIIRS' and month:
                    row['filter_evidence'] = tags.get('FILTER', '')
                    if not row['filter_evidence']:
                        issues.append('MONTHLY_FILTER_NOT_DOCUMENTED')
                if source == 'VIIRS' and not month:
                    row['annual_evidence'] = tags.get('SOURCE', '')
                    if 'MEDIAN_OF_FILTERED_VIIRS_MONTHS' not in row['annual_evidence']:
                        issues.append('ANNUAL_PIXEL_COMPOSITE_NOT_DOCUMENTED')
                if code in sample_codes and year in {min(years), max(years)}:
                    if code in geometries and image.crs:
                        counts = audit_pixels(image, geometries[code])
                        row['pixel_audit'] = json.dumps(counts)
                        if counts['outside_valid_pixels']:
                            issues.append('VALID_PIXELS_OUTSIDE_PROVINCE')
                        if counts['negative_pixels']:
                            issues.append('NEGATIVE_RADIANCE_IN_PROCESSED_IMAGE')
                        if counts['nonfinite_unmasked_pixels']:
                            issues.append('NONFINITE_UNMASKED_PIXELS')
                    else:
                        row['pixel_audit'] = 'PENDING_BOUNDARY_OR_CRS'
        except Exception as error:
            issues.append('READ_OR_IDENTITY_ERROR')
            errors.append({'path': str(path), 'reason': str(error)})
        row['issues'] = ';'.join(issues)
        records.append(row)
    # Các file trùng tỉnh/năm/tháng/nguồn phải chọn có căn cứ; không tự lấy file đầu tiên.
    groups = defaultdict(list)
    for row in records:
        if row['province_code']:
            groups[(row['province_code'], row['year'], row['month'], row['source'])].append(row)
    candidates = []
    for group in groups.values():
        clean = [r for r in group if not r['issues']]
        if len(clean) == 1:
            candidates.append(clean[0])
        elif len(clean) > 1:
            for row in clean:
                row['issues'] = 'DUPLICATE_CANDIDATE'
    for row in candidates:
        if row['source'] == 'VIIRS' and not row['month'] and row['province_code'] in sample_codes and row['year'] in {min(years), max(years)}:
            months = [r['path'] for r in candidates if r['source'] == 'VIIRS' and r['province_code'] == row['province_code']
                      and r['year'] == row['year'] and r['month']]
            try:
                row['annual_pixel_check'] = verify_annual(row['path'], months)
            except Exception as error:
                row['annual_pixel_check'] = 'PENDING: '+str(error)
            if row['annual_pixel_check'].startswith('FAIL'):
                row['issues'] = row['annual_pixel_check']
    fields = list(records[0]) if records else ['path', 'province_code', 'year', 'month', 'issues']
    write_csv(output/'image_inventory.csv', records, fields)
    write_csv(output/'image_errors.csv', errors, ['path', 'reason'])
    write_csv(output/'excluded_images.csv', excluded, ['path', 'reason'])
    # Báo cáo nhỏ để chẩn đoán các mẫu bị loại, không cần gửi lại toàn bộ inventory.
    sampled = [r for r in records if r['province_code'] in sample_codes
               and r['year'] in {min(years), max(years)}]
    write_csv(output/'sample_image_checks.csv', sampled, fields)
    # Manifest CANDIDATES là kết quả kiểm kê; tags là khai báo, chưa chứng minh thuật toán lọc.
    fields = ['province_code', 'province_name', 'year', 'month', 'source', 'path', 'area_km2']
    candidates = [r for r in candidates if not r['issues'] and r['year'] in years]
    write_csv(output/'manifest_candidates.csv', [{k: r[k] for k in fields} for r in candidates], fields)
    coverage = []
    for code, province in catalog.items():
        for year in years:
            present = [r for r in records if r['province_code'] == code and r['year'] == year]
            selected = [r for r in candidates if r['province_code'] == code and r['year'] == year]
            coverage.append({'province_code': code, 'province_name': province['ten_tinh'], 'year': year,
                             'files_present': len(present), 'annual_candidates': sum(r['month'] == 0 for r in selected),
                             'monthly_candidates': len({r['month'] for r in selected if r['month']}),
                             'status': 'CANDIDATE_AVAILABLE' if any(r['month'] == 0 for r in selected) else 'NOT_READY'})
    write_csv(output/'coverage_province_year.csv', coverage, list(coverage[0]))
    return {'files': len(records), 'excluded_files': len(excluded),
            'excluded_reasons': dict(Counter(r['reason'] for r in excluded)),
            'manifest_candidates': len(candidates), 'errors': len(errors),
            'annual_candidate_province_years': sum(r['annual_candidates'] > 0 for r in coverage),
            'expected_province_years': len(coverage),
            'sampled_rasters': sum(r['pixel_audit'].startswith('{') for r in records),
            'annual_pixel_checks': dict(Counter(r['annual_pixel_check'] for r in records if r['annual_pixel_check'] != 'NOT_SAMPLED'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Ổ dữ liệu, ví dụ E:\\SatelliteData')
    parser.add_argument('--grdp', type=Path, help='Tự tìm đúng tên Excel trong root nếu không chỉ định')
    parser.add_argument('--boundaries', type=Path)
    parser.add_argument('--boundary-metadata', type=Path)
    parser.add_argument('--output', type=Path, help='Thư mục MỚI, không ghi đè kết quả trước')
    parser.add_argument('--years', nargs='+', type=int, default=list(range(2020, 2025)))
    parser.add_argument('--sample-codes', nargs='+', default=['01', '27', '10'], help='Hà Nội, Bắc Ninh, Lào Cai; kiểm tra pixel ở năm đầu/cuối')
    args = parser.parse_args()
    report_root = args.root if args.root.is_dir() else REPO/'work'
    output = args.output or report_root/'_demo_preparation'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output.mkdir(parents=True, exist_ok=False)
    env = environment_report(output)
    roster = provinces()
    catalog = {p['ma_tinh']: p for p in roster}
    write_csv(output/'province_catalog.csv',
              [dict(province_code=p['ma_tinh'], province_name=p['ten_tinh'], gid_1=p['gid_1'], slug=p['slug']) for p in roster],
              ['province_code', 'province_name', 'gid_1', 'slug'])
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'environment': env,
              'data_root': str(args.root), 'root_accessible': args.root.is_dir(), 'blockers': []}
    if env['branch'] != 'night-app':
        report['blockers'].append('WRONG_BRANCH')
    if any(v == 'MISSING' for v in env['versions'].values()):
        report['blockers'].append('MISSING_PYTHON_DEPENDENCIES')
    boundaries = args.boundaries or REPO/'backend/core/ranh_gioi/config/boundaries.geojson'
    legacy = REPO/'province_pipeline/config/boundaries.geojson'
    if not args.boundaries and not boundaries.exists() and legacy.exists():
        boundaries = legacy  # Chỉ dùng khi load_boundaries xác minh checksum và mã tỉnh thành công.
    metadata = args.boundary_metadata or boundaries.with_name('boundaries.metadata.json')
    found, areas = {}, {}
    try:
        found, areas, info = boundary_areas(boundaries, metadata)
        report['boundaries'] = {'count': len(found), 'sha256': info['sha256'], 'profile': info['boundary_profile']}
    except Exception as error:
        report['blockers'].append('BOUNDARIES: '+str(error))
    write_csv(output/'province_areas.csv', [{'province_code': code, 'area_km2': area} for code, area in areas.items()],
              ['province_code', 'area_km2'])
    grdp_files = [args.grdp] if args.grdp else list(args.root.rglob('GRDP Cấp Tỉnh_So sánh vs Hiện hành.xlsx'))
    try:
        if len(grdp_files) != 1:
            raise ValueError('Cần đúng một file GRDP; chỉ định --grdp nếu có nhiều bản.')
        report['grdp'] = prepare_grdp(grdp_files[0], output)
    except Exception as error:
        report['blockers'].append('GRDP: '+str(error))
    report['images'] = inventory(args.root, output, catalog, found, areas, args.years, set(args.sample_codes))
    if not report['images']['files']:
        report['blockers'].append('NO_REAL_NIGHT_IMAGES_ACCESSIBLE')
    if report['images']['annual_candidate_province_years'] < report['images']['expected_province_years']:
        report['blockers'].append('DEMO_ANNUAL_COVERAGE_INCOMPLETE')
    # Tháng đã lọc chỉ được nhận diện qua tags; chưa kiểm chứng lại với ảnh thô.
    report['limitations'] = ['Chưa kiểm chứng thuật toán lọc từng ảnh tháng với ảnh thô nguồn.',
                              'Manifest là ứng viên; kiểm tra image_inventory.csv trước khi tính chính thức.',
                              'Không thể kiểm tra tab chưa lưu trong IDE; phải đóng chúng trước khi cập nhật Git.']
    (output/'preparation_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Báo cáo:', output/'preparation_report.json')
    print('Ảnh đêm:', report['images']['files'], '; ứng viên manifest:', report['images']['manifest_candidates'])
    print('BLOCKERS:', '\n'.join(report['blockers']) or 'Xem limitations và các kiểm tra mẫu trước khi xác nhận hoàn thành A.')
    return 2 if report['blockers'] else 0


if __name__ == '__main__':
    sys.exit(main())
