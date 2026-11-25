"""Năm mức sáng cho demo VIIRS, ngưỡng cố định từ năm tham chiếu 2020.

0.5: ngưỡng nền dự án; 1.5: ngưỡng sáng Task 3.
Hai mốc còn lại: P50/P90 của pixel sáng (>=1.5) trong 63 ảnh năm tham chiếu.
Đây là phân loại bức xạ thực nghiệm, không phải chuẩn phân lớp kinh tế/phân loại đô thị.
python -m backend.data.build_light_classes --root E:\\SatelliteData
"""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import sqlite3

import numpy as np
import rasterio
from rasterio.shutil import copy as raster_copy

from .calculate_ntl import windows, pixel_area_km2
from .load_demo import backup_database, SCHEMA
from .prepare_grdp import provinces

METHOD_VERSION = 'viirs_brightness_classes_v2'


def validate_breaks(breaks):
    if (len(breaks) != 4 or not all(np.isfinite(b) for b in breaks)
            or breaks[:2] != [0.5, 1.5] or not all(a < b for a, b in zip(breaks, breaks[1:]))):
        raise ValueError('Cần bốn ngưỡng hữu hạn tăng nghiêm ngặt, bắt đầu 0.5 và 1.5.')


def validate_radiance(image):
    valid_bands = image.count == 1 or (image.count == 2 and image.descriptions == ('avg_rad', 'cf_cvg'))
    if not valid_bands or image.scales[0] != 1 or image.offsets[0] != 0:
        raise ValueError('Cần băng bức xạ đã xử lý scale=1, offset=0; một băng hoặc avg_rad/cf_cvg.')


def choose_thresholds(assets, reference_year, expected_codes=None):
    expected = expected_codes or {p['ma_tinh'] for p in provinces()}
    reference = [r for r in assets if r['year'] == reference_year and r['month'] == 0]
    if {r['province_code'] for r in reference} != expected or len(reference) != len(expected):
        raise ValueError('Cần đủ một ảnh VIIRS năm tham chiếu cho mỗi tỉnh, không khớp ngưỡng từ mẫu thiếu.')
    samples = []
    for item in reference:
        with rasterio.open(item['path']) as image:
            if image.scales[0] != 1 or image.offsets[0] != 0:
                raise ValueError('Cần chuẩn hóa scale/offset bức xạ trước khi chọn ngưỡng.')
            for window in windows(image.height, image.width):
                data = image.read(1, window=window).astype(float)
                valid = image.read_masks(1, window=window).astype(bool) & np.isfinite(data) & (data != -9999)
                values = data[valid & (data >= 1.5)]
                if values.size:
                    samples.append(values)
    if not samples:
        raise ValueError('Không có pixel sáng hợp lệ ở năm tham chiếu.')
    bright = np.concatenate(samples)
    q50, q90 = np.quantile(bright, [.5, .9], method='linear')
    breaks = [0.5, 1.5, float(q50), float(q90)]
    if not all(a < b for a, b in zip(breaks, breaks[1:])):
        raise ValueError('Phân bố tham chiếu suy biến; không tự tạo mốc để đủ năm lớp.')
    return breaks, int(bright.size)


def classify_image(source, target, breaks, reference_year=None):
    """Mỗi pixel hợp lệ thuộc đúng một lớp 0..4; NoData=255, không biến mây thành tối."""
    validate_breaks(breaks)
    areas = np.zeros(5)
    target = Path(target)
    temporary = target.with_suffix('.temporary.tif')
    try:
        with rasterio.open(source) as image:
            validate_radiance(image)
            profile = image.profile.copy()
            profile.update(driver='GTiff', dtype='uint8', count=1, nodata=255,
                           compress='DEFLATE', predictor=1, tiled=True, blockxsize=256, blockysize=256)
            with rasterio.open(temporary, 'w', **profile) as result:
                for window in windows(image.height, image.width):
                    data = image.read(1, window=window).astype(float)
                    valid = image.read_masks(1, window=window).astype(bool) & np.isfinite(data) & (data != -9999)
                    if (data[valid] < 0).any():
                        raise ValueError('Ảnh đã xử lý còn bức xạ âm; cần kiểm tra trước khi phân lớp.')
                    classes = np.digitize(data, breaks, right=False).astype('uint8')
                    classes[~valid] = 255
                    result.write(classes, 1, window=window)
                    weights = np.broadcast_to(pixel_area_km2(image.transform, window, image.crs), data.shape)
                    for index in range(5):
                        areas[index] += float(weights[classes == index].sum())
                result.set_band_description(1, 'light_class')
                result.update_tags(THRESHOLDS=json.dumps(breaks), METHOD='PROJECT_0.5_TASK3_1.5_REFERENCE_BRIGHT_P50_P90',
                                   BOUNDARY_RULE='source_intersecting_pixel', SOURCE_IMAGE=str(source),
                                   REFERENCE_YEAR=str(reference_year) if reference_year is not None else 'test_or_unspecified')
        raster_copy(temporary, target, driver='COG', COMPRESS='DEFLATE', RESAMPLING='NEAREST')
    finally:
        temporary.unlink(missing_ok=True)
    return areas.tolist()


def saved_areas(target, source, breaks, reference_year, details=False, area_weights=None):
    """Đọc diện tích từ COG đã tạo; chỉ dùng lại khi khớp nguồn và phương pháp."""
    areas = np.zeros(5)
    valid_pixels = nodata_pixels = 0
    valid_area = 0.0
    validate_breaks(breaks)
    with rasterio.open(target) as image, rasterio.open(source) as original:
        validate_radiance(original)
        tags = image.tags()
        if (json.loads(tags.get('THRESHOLDS', 'null')) != breaks
                or tags.get('REFERENCE_YEAR') != str(reference_year)
                or Path(tags.get('SOURCE_IMAGE', '')).resolve() != Path(source).resolve()
                or image.count != 1 or image.dtypes[0] != 'uint8' or image.nodata != 255
                or image.crs != original.crs or image.transform != original.transform
                or image.shape != original.shape):
            raise ValueError(f'Ảnh phân lớp không khớp nguồn/ngưỡng: {target}')
        for window in windows(image.height, image.width):
            values = image.read(1, window=window)
            valid = image.read_masks(1, window=window).astype(bool)
            source_data = original.read(1, window=window)
            source_valid = (original.read_masks(1, window=window).astype(bool)
                            & np.isfinite(source_data) & (source_data != -9999))
            if not np.array_equal(valid, source_valid) or (values[valid] > 4).any():
                raise ValueError(f'Mask hoặc mã lớp không hợp lệ: {target}')
            expected = np.digitize(source_data[source_valid], breaks, right=False)
            if ((source_data[source_valid] < 0).any() or (values[~valid] != 255).any()
                    or not np.array_equal(values[valid], expected)):
                raise ValueError(f'Giá trị lớp không khớp ngưỡng/NoData của ảnh nguồn: {target}')
            weights = (area_weights[window.toslices()] if area_weights is not None else
                       np.broadcast_to(pixel_area_km2(image.transform, window, image.crs), values.shape))
            effective = valid & (weights > 0)
            valid_pixels += int(effective.sum())
            nodata_pixels += int((~effective).sum())
            valid_area += float(weights[effective].sum())
            for index in range(5):
                areas[index] += float(weights[effective & (values == index)].sum())
    error = float(areas.sum()) - valid_area
    if not np.isclose(areas.sum(), valid_area, rtol=1e-10, atol=1e-8):
        raise ValueError(f'Tổng diện tích lớp không bằng diện tích hợp lệ: {target}')
    result = dict(areas=areas.tolist(), valid_pixels=valid_pixels, nodata_pixels=nodata_pixels,
                  valid_area_km2=valid_area, area_balance_error_km2=error)
    return result if details else result['areas']


def province_areas(connection, assets, areas_csv=None):
    """Mẫu số tự nhiên từ bảng chỉ số đã nạp, hoặc CSV diện tích phần A chỉ định rõ."""
    explicit = {}
    if areas_csv is not None:
        with Path(areas_csv).open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                code, value = row['province_code'].zfill(2), float(row['area_km2'])
                if code in explicit or not np.isfinite(value) or value <= 0:
                    raise ValueError('CSV diện tích phải có mã duy nhất, diện tích hữu hạn dương.')
                explicit[code] = value
    result = {}
    for row in assets:
        key = (row['province_code'], row['year'], row['month'])
        if areas_csv is not None:
            result[key] = (explicit.get(key[0]), str(Path(areas_csv).resolve()))
            continue
        table = 'ntl_monthly' if row['month'] else 'ntl_annual'
        query = f'SELECT area_km2 FROM {table} WHERE province_code=? AND year=?'
        args = [row['province_code'], row['year']]
        if row['month']:
            query += ' AND month=?'
            args.append(row['month'])
        found = connection.execute(query, args).fetchone()
        value = found[0] if found else None
        result[key] = (float(value) if value is not None and np.isfinite(value) and value > 0 else None,
                       table+'.area_km2')
    return result


def write_report(path, rows):
    """UTF-8 BOM để Excel Windows đọc tiếng Việt; thay file sau khi ghi xong."""
    temporary = path.with_suffix('.csv.tmp')
    with temporary.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def build(root, db, reference_year=2020, resume_dir=None, areas_csv=None,
          area_model=None, method_file=None, reuse_registered=False):
    root, db = Path(root).resolve(), Path(db)
    # Đọc UTF-8 ngay từ đầu: Windows có thể mặc định cp1252.
    schema_sql = SCHEMA.read_text(encoding='utf-8')
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        assets = [dict(r) for r in connection.execute(
            "SELECT * FROM demo_asset WHERE kind='processed' AND source='VIIRS' AND year BETWEEN 2020 AND 2024")]
        denominators = province_areas(connection, assets, areas_csv)
        registered = {(r['province_code'], r['year'], r['month']): r['path'] for r in connection.execute(
            "SELECT * FROM demo_asset WHERE kind='classes'")} if reuse_registered else {}
    fractional = area_model is not None
    version = 'viirs_brightness_classes_v3_fractional' if fractional else METHOD_VERSION
    if fractional:
        for row in assets:
            key = (row['province_code'], row['year'], row['month'])
            expected = area_model.areas[row['province_code']]
            if areas_csv is not None and (denominators[key][0] is None or not np.isclose(denominators[key][0], expected, rtol=1e-8)):
                raise ValueError('CSV diện tích không khớp ranh giới đã xác minh; không trộn hai mẫu số.')
            denominators[key] = (expected, 'verified_polygon_epsg6933:'+area_model.metadata['sha256'])
    if not assets:
        raise ValueError('Chưa nạp ảnh VIIRS cho demo; chạy load_demo trước.')
    for row in assets:
        if not Path(row['path']).resolve().is_relative_to(root):
            raise ValueError('Ảnh tham chiếu nằm ngoài --root.')
    if resume_dir is not None:
        directory = Path(resume_dir).resolve()
        if not directory.is_relative_to(root/'cog/light_classes'):
            raise ValueError('Thư mục tiếp tục phải nằm trong <root>/cog/light_classes.')
        method = json.loads((directory/'method.json').read_text(encoding='utf-8'))
        breaks = method['breaks']
        if (method['reference_year'] != reference_year or method.get('status') != 'empirical_demo'
                or len(breaks) != 4 or not all(np.isfinite(b) for b in breaks)
                or breaks[:2] != [0.5, 1.5] or not all(a < b for a, b in zip(breaks, breaks[1:]))):
            raise ValueError('method.json không khớp năm tham chiếu hoặc bộ ngưỡng.')
        print(f'Tiếp tục từ: {directory}', flush=True)
    elif method_file is not None:
        method = json.loads(Path(method_file).read_text(encoding='utf-8'))
        breaks = method['breaks']
        validate_breaks(breaks)
        if method.get('reference_year') != reference_year or method.get('status') != 'empirical_demo':
            raise ValueError('method.json không khớp phương pháp/năm tham chiếu.')
        directory = root/'cog/light_classes'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        directory.mkdir(parents=True)
        method = dict(method, preserved_reference_snapshot=str(Path(method_file).resolve()))
        (directory/'method.json').write_text(json.dumps(method, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        breaks, sample_count = choose_thresholds(assets, reference_year)
        directory = root/'cog/light_classes'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        directory.mkdir(parents=True, exist_ok=False)
        method = {'breaks': breaks, 'reference_year': reference_year, 'bright_pixel_count': sample_count,
              'unit': 'nW/cm²/sr', 'status': 'empirical_demo',
              'interpretation': 'Mức bức xạ tương đối; không chứng minh loại đất hoặc mức hoạt động kinh tế.',
              'sampling': 'Tất cả pixel sáng hợp lệ trong 63 ảnh năm tham chiếu; các pixel giao biên có thể lặp giữa tỉnh.',
              'sources': ['Task3-GEO_NTL_Images.ipynb (ngưỡng 1.5)', 'CLAUDE.md (ngưỡng nền 0.5)',
                          'https://eogdata.mines.edu/products/vnl/index.html (xử lý nhất quán giữa các năm; không quy định năm ngưỡng của dự án)']}
        (directory/'method.json').write_text(json.dumps(method, ensure_ascii=False, indent=2), encoding='utf-8')
    records, paths = [], []
    summaries, class_report, summary_report = [], [], []
    reused = 0
    for i, row in enumerate(assets, 1):
        target = directory/f"{row['province_code']}_VIIRS_{row['year']}_{row['month']:02}_classes.tif"
        candidate = registered.get((row['province_code'], row['year'], row['month']))
        if candidate and Path(candidate).is_file():
            with rasterio.open(candidate) as old:
                tags = old.tags()
                if (Path(tags.get('SOURCE_IMAGE', '')).resolve() == Path(row['path']).resolve()
                        and json.loads(tags.get('THRESHOLDS', 'null')) == breaks
                        and tags.get('REFERENCE_YEAR') == str(reference_year)):
                    target = Path(candidate)
        if (resume_dir is not None or candidate) and target.exists():
            reused += 1
        else:
            classify_image(row['path'], target, breaks, reference_year)
        # Đối chiếu mã lớp từng pixel với ảnh nguồn kể cả khi dùng lại COG cũ.
        weights = None
        if fractional:
            with rasterio.open(row['path']) as source:
                weights = area_model.weights(row['province_code'], source)
        checked = saved_areas(target, row['path'], breaks, reference_year, details=True, area_weights=weights)
        areas = checked['areas']
        key = (row['province_code'], row['year'], row['month'])
        area, area_source = denominators[key]
        valid_area = checked['valid_area_km2']
        valid_pct = 100*valid_area/area if area is not None else None
        lit_area = sum(areas[2:])
        lit_pct = 100*lit_area/area if area is not None and checked['valid_pixels'] else None
        class_percentages = [100*a/area if area is not None and checked['valid_pixels'] else None for a in areas]
        if fractional:
            from .fractional_area import percent_area
            valid_pct = percent_area(valid_area, area)
            lit_pct = percent_area(lit_area, area) if checked['valid_pixels'] else None
            class_percentages = [percent_area(a, area) if checked['valid_pixels'] else None for a in areas]
        validation = 'no_valid_pixels' if not checked['valid_pixels'] else 'passed'
        summary = dict(province_code=key[0], year=key[1], month=key[2], area_km2=area,
                       area_source=area_source, valid_pixels=checked['valid_pixels'],
                       nodata_pixels=checked['nodata_pixels'], valid_area_km2=valid_area,
                       valid_area_pct=valid_pct, lit_area_km2=lit_area, lit_area_pct=lit_pct,
                       area_balance_error_km2=checked['area_balance_error_km2'], validation_status=validation,
                       reference_year=reference_year, method_version=version,
                       class_area_pcts=json.dumps(class_percentages))
        summaries.append(tuple(summary.values()))
        summary_report.append(dict(summary, coverage_note='missing_province_area' if area is None else
                                   'coverage_above_polygon' if valid_pct > 100 else 'fractional_intersection' if fractional else 'intersecting_pixel',
                                   source_path=row['path'], class_path=str(target)))
        for index, area in enumerate(areas):
            records.append((row['province_code'], row['year'], row['month'], index,
                            0 if index == 0 else breaks[index-1], breaks[index] if index < 4 else None,
                            area, f'empirical_reference_{reference_year}', 'nW/cm²/sr', 'VIIRS'))
            class_report.append(dict(province_code=key[0], year=key[1], month=key[2],
                                     class_index=index, lower_bound=0 if index == 0 else breaks[index-1],
                                     upper_bound=breaks[index] if index < 4 else None,
                                     class_area_km2=area,
                                     class_area_pct=class_percentages[index],
                                     area_km2=summary['area_km2'], valid_area_km2=valid_area,
                                     unit='nW/cm²/sr', reference_year=reference_year,
                                     method_version=version, validation_status=validation))
        paths.append((row['province_code'], row['year'], row['month'], 'classes', str(target), 'VIIRS', '["light_class"]'))
        if i % 100 == 0:
            print(f'Đã kiểm tra/xử lý {i}/{len(assets)} ảnh (dùng lại {reused})', flush=True)
    write_report(directory/'light_class_areas.csv', class_report)
    write_report(directory/'light_class_validation.csv', summary_report)
    # Giữ method gốc khi tiếp tục; nhật ký kiểm chứng có phiên bản riêng.
    report = dict(method_version=version, images=len(assets), reused_images=reused,
                  empty_images=sum(r['valid_pixels'] == 0 for r in summary_report),
                  missing_province_area=sum(r['area_km2'] is None for r in summary_report),
                  coverage_above_100=sum((r['valid_area_pct'] or 0) > 100 for r in summary_report),
                  max_area_balance_error_km2=max(abs(r['area_balance_error_km2']) for r in summary_report),
                  breaks=breaks, reference_year=reference_year,
                  boundary_rule='pixel_polygon_intersection' if fractional else 'source_intersecting_pixel',
                  area_method='pixel_polygon_intersection_epsg6933_v1' if fractional else 'calculate_ntl.pixel_area_km2',
                  boundary_sha256=area_model.metadata['sha256'] if fractional else None,
                  checks=['threshold_values', 'source_mask', 'nodata_255', 'class_area_balance'],
                  completed_at=datetime.now().isoformat())
    (directory/'validation_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    backup = backup_database(db)
    with sqlite3.connect(db) as connection:
        connection.executescript(schema_sql)
        with connection:
            connection.executemany('INSERT OR REPLACE INTO light_class VALUES(?,?,?,?,?,?,?,?,?,?)', records)
            connection.executemany('INSERT OR REPLACE INTO demo_asset VALUES(?,?,?,?,?,?,?)', paths)
            connection.executemany('INSERT OR REPLACE INTO light_class_summary VALUES('+','.join(['?']*16)+')', summaries)
    return {'breaks': breaks, 'images': len(assets), 'reused_images': reused,
            'method': str(directory/'method.json'), 'backup': backup,
            'class_csv': str(directory/'light_class_areas.csv'),
            'validation_csv': str(directory/'light_class_validation.csv'),
            'validation_report': str(directory/'validation_report.json'), **{k: report[k] for k in
                ('empty_images', 'missing_province_area', 'coverage_above_100', 'max_area_balance_error_km2')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--db', type=Path, default=Path(__file__).with_name('vngis.db'))
    parser.add_argument('--reference-year', type=int, default=2020)
    parser.add_argument('--areas', type=Path, help='CSV province_areas.csv của phần A để chỉ định mẫu số tự nhiên.')
    parser.add_argument('--fractional-area', action='store_true', help='Diện tích phần giao pixel–tỉnh trong EPSG:6933.')
    parser.add_argument('--boundaries', type=Path)
    parser.add_argument('--boundary-metadata', type=Path)
    parser.add_argument('--method-file', type=Path, help='Giữ ngưỡng của snapshot tham chiếu đã chọn, tạo báo cáo mới.')
    parser.add_argument('--reuse-registered', action='store_true', help='Dùng COG đã đăng ký nếu đúng nguồn/ngưỡng.')
    resume = parser.add_mutually_exclusive_group()
    resume.add_argument('--resume-dir', type=Path, help='Thư mục phân lớp đã có method.json.')
    resume.add_argument('--resume-latest', action='store_true', help='Dùng lại lượt phân lớp mới nhất.')
    args = parser.parse_args()
    if (args.resume_dir or args.resume_latest) and args.method_file:
        parser.error('--method-file tạo lượt mới; không dùng cùng tùy chọn resume.')
    if args.resume_latest:
        candidates = sorted(p.parent for p in (args.root/'cog/light_classes').glob('*/method.json'))
        if not candidates:
            parser.error('Không tìm thấy lượt phân lớp cũ có method.json.')
        args.resume_dir = candidates[-1]
    area_model = None
    if args.fractional_area:
        from .fractional_area import load_area_model
        area_model = load_area_model(args.root, args.boundaries, args.boundary_metadata)
    print(json.dumps(build(args.root, args.db, args.reference_year, args.resume_dir, args.areas,
                           area_model, args.method_file, args.reuse_registered), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
