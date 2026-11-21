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


def build(root, db, reference_year=2020):
    root, db = Path(root).resolve(), Path(db)
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        assets = [dict(r) for r in connection.execute(
            "SELECT * FROM demo_asset WHERE kind='processed' AND source='VIIRS' AND year BETWEEN 2020 AND 2024")]
    if not assets:
        raise ValueError('Chưa nạp ảnh VIIRS cho demo; chạy load_demo trước.')
    for row in assets:
        if not Path(row['path']).resolve().is_relative_to(root):
            raise ValueError('Ảnh tham chiếu nằm ngoài --root.')
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
    for i, row in enumerate(assets, 1):
        target = directory/f"{row['province_code']}_VIIRS_{row['year']}_{row['month']:02}_classes.tif"
        areas = classify_image(row['path'], target, breaks, reference_year)
        for index, area in enumerate(areas):
            records.append((row['province_code'], row['year'], row['month'], index,
                            0 if index == 0 else breaks[index-1], breaks[index] if index < 4 else None,
                            area, f'empirical_reference_{reference_year}', 'nW/cm²/sr', 'VIIRS'))
        paths.append((row['province_code'], row['year'], row['month'], 'classes', str(target), 'VIIRS', '["light_class"]'))
        if i % 100 == 0:
            print(f'Đã phân lớp {i}/{len(assets)} ảnh', flush=True)
    backup = backup_database(db)
    with sqlite3.connect(db) as connection:
        connection.executescript(SCHEMA.read_text())
        with connection:
            connection.executemany('INSERT OR REPLACE INTO light_class VALUES(?,?,?,?,?,?,?,?,?,?)', records)
            connection.executemany('INSERT OR REPLACE INTO demo_asset VALUES(?,?,?,?,?,?,?)', paths)
    return {'breaks': breaks, 'images': len(assets), 'method': str(directory/'method.json'), 'backup': backup}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--db', type=Path, default=Path(__file__).with_name('vngis.db'))
    parser.add_argument('--reference-year', type=int, default=2020)
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.db, args.reference_year), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
