"""Năm mức sáng cho demo VIIRS, ngưỡng cố định từ năm tham chiếu 2020.

0.5: ngưỡng nền dự án; 1.5: ngưỡng sáng Task 3.
Hai mốc còn lại: P50/P90 của pixel sáng (>=1.5) trong 63 ảnh năm tham chiếu.
Đây là phân loại bức xạ thực nghiệm, không phải chuẩn phân lớp kinh tế/phân loại đô thị.
python -m backend.data.build_light_classes --root E:\\SatelliteData
"""
import argparse
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
    areas = np.zeros(5)
    target = Path(target)
    temporary = target.with_suffix('.temporary.tif')
    try:
        with rasterio.open(source) as image:
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


def saved_areas(target, source, breaks, reference_year):
    """Đọc diện tích từ COG đã tạo; chỉ dùng lại khi khớp nguồn và phương pháp."""
    areas = np.zeros(5)
    with rasterio.open(target) as image, rasterio.open(source) as original:
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
            weights = np.broadcast_to(pixel_area_km2(image.transform, window, image.crs), values.shape)
            for index in range(5):
                areas[index] += float(weights[valid & (values == index)].sum())
    return areas.tolist()


def build(root, db, reference_year=2020, resume_dir=None):
    root, db = Path(root).resolve(), Path(db)
    # Đọc UTF-8 ngay từ đầu: Windows có thể mặc định cp1252.
    schema_sql = SCHEMA.read_text(encoding='utf-8')
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        assets = [dict(r) for r in connection.execute(
            "SELECT * FROM demo_asset WHERE kind='processed' AND source='VIIRS' AND year BETWEEN 2020 AND 2024")]
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
    reused = 0
    for i, row in enumerate(assets, 1):
        target = directory/f"{row['province_code']}_VIIRS_{row['year']}_{row['month']:02}_classes.tif"
        if resume_dir is not None and target.exists():
            areas = saved_areas(target, row['path'], breaks, reference_year)
            reused += 1
        else:
            areas = classify_image(row['path'], target, breaks, reference_year)
        for index, area in enumerate(areas):
            records.append((row['province_code'], row['year'], row['month'], index,
                            0 if index == 0 else breaks[index-1], breaks[index] if index < 4 else None,
                            area, f'empirical_reference_{reference_year}', 'nW/cm²/sr', 'VIIRS'))
        paths.append((row['province_code'], row['year'], row['month'], 'classes', str(target), 'VIIRS', '["light_class"]'))
        if i % 100 == 0:
            print(f'Đã kiểm tra/xử lý {i}/{len(assets)} ảnh (dùng lại {reused})', flush=True)
    backup = backup_database(db)
    with sqlite3.connect(db) as connection:
        connection.executescript(schema_sql)
        with connection:
            connection.executemany('INSERT OR REPLACE INTO light_class VALUES(?,?,?,?,?,?,?,?,?,?)', records)
            connection.executemany('INSERT OR REPLACE INTO demo_asset VALUES(?,?,?,?,?,?,?)', paths)
    return {'breaks': breaks, 'images': len(assets), 'reused_images': reused,
            'method': str(directory/'method.json'), 'backup': backup}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--db', type=Path, default=Path(__file__).with_name('vngis.db'))
    parser.add_argument('--reference-year', type=int, default=2020)
    resume = parser.add_mutually_exclusive_group()
    resume.add_argument('--resume-dir', type=Path, help='Thư mục phân lớp đã có method.json.')
    resume.add_argument('--resume-latest', action='store_true', help='Dùng lại lượt phân lớp mới nhất.')
    args = parser.parse_args()
    if args.resume_latest:
        candidates = sorted(p.parent for p in (args.root/'cog/light_classes').glob('*/method.json'))
        if not candidates:
            parser.error('Không tìm thấy lượt phân lớp cũ có method.json.')
        args.resume_dir = candidates[-1]
    print(json.dumps(build(args.root, args.db, args.reference_year, args.resume_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
