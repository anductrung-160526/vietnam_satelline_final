"""Sửa diện tích và kiểm tra/phục hồi ảnh tháng, chuẩn bị trên SQLite tạm trước khi xuất bản.

Ảnh gốc không đổi; quan sát thật sự thiếu vẫn là thiếu. Dừng app trước --publish.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from .repair_monthly import repair
from .fractional_area import load_area_model
from .load_demo import load, backup_database
from .build_light_classes import build
from .build_light_classes import validate_breaks
from .calculate_ntl import calculate, read_manifest, write_tables
from .economy_indices import read_prices, read_image_quality


def fix(root, prepared, db, method_file, output=None, area_model=None, publish=False):
    root, prepared, db = Path(root).resolve(), Path(prepared).resolve(), Path(db).resolve()
    if not db.is_file():
        raise ValueError('Cần database app đã nạp phần A/B; không tự tạo kho rỗng để sửa.')
    method = json.loads(Path(method_file).read_text(encoding='utf-8'))
    validate_breaks(method['breaks'])
    if method.get('reference_year') != 2020 or method.get('status') != 'empirical_demo':
        raise ValueError('Cần method.json snapshot tham chiếu 2020 đã được chọn.')
    prices = read_prices(prepared/'grdp_all_prices.csv')
    output = Path(output).resolve() if output else root/'_demo_fix'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    if not output.is_relative_to(root):
        raise ValueError('--output phải nằm trong kho --root để app đọc được ảnh sửa.')
    output.mkdir(parents=True, exist_ok=False)
    area_model = area_model or load_area_model(root)
    print('1/5 Đối chiếu raw/filtered và tạo ảnh sửa ở thư mục mới.', flush=True)
    recovery = repair(prepared/'manifest_candidates.csv', db, output/'repair', area_model, apply=True)
    manifest = Path(recovery['manifest'])
    staging = output/'candidate.db'
    with sqlite3.connect(db) as original, sqlite3.connect(staging) as candidate:
        original.backup(candidate)
    # Chưa nạp thống kê cũ vào bản tạm; chỉ đăng ký ảnh sửa, hai giá và support.
    load(root, prepared, staging, output/'no_indices', manifest)
    print('2/5 Tính diện tích giao pixel–tỉnh, kiểm chứng và tái dùng COG phù hợp.', flush=True)
    classes = build(root, staging, area_model=area_model, method_file=method_file, reuse_registered=True)
    print('3/5 Tính lại SOL, diện tích, chuỗi thời gian và hai giá GRDP.', flush=True)
    tables = calculate(read_manifest(manifest), economy_prices=prices,
                       image_quality=read_image_quality(classes['validation_csv']), area_model=area_model, progress=True)
    indices = output/'indices'
    write_tables(tables, indices)
    print('4/5 Nạp và kiểm tra bản SQLite tạm, giữ nguyên database app.', flush=True)
    loaded = load(root, prepared, staging, indices, manifest)
    with sqlite3.connect(staging) as connection:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite tạm không qua integrity_check; chưa cập nhật app.')
    summary = dict(output=str(output), manifest=str(manifest), recovery=recovery, classification=classes,
                   economy_validation=tables['economy_validation'][0], loaded=loaded,
                   published=False, backup=None, area_method='pixel_polygon_intersection_epsg6933_v1',
                   note='Nguồn không có quan sát không thể phục hồi bằng nội suy. Kiểm tra diagnosis_counts và support năm.')
    if publish:
        print('5/5 Sao lưu database gốc và xuất bản toàn bộ snapshot đã tính xong.', flush=True)
        summary['backup'] = backup_database(db)
        with sqlite3.connect(staging) as candidate, sqlite3.connect(db) as original:
            candidate.backup(original)
        summary['published'] = True
    else:
        print('5/5 Đã chuẩn bị candidate.db; chưa cập nhật database app vì không có --publish.', flush=True)
    (output/'fix_report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--prepared',required=True,type=Path)
    parser.add_argument('--method-file',required=True,type=Path,help='method.json gốc để giữ bộ ngưỡng/snapshot tham chiếu.')
    parser.add_argument('--db',type=Path,default=Path(__file__).with_name('vngis.db'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--boundaries',type=Path)
    parser.add_argument('--boundary-metadata',type=Path)
    parser.add_argument('--publish',action='store_true',help='Sau khi tính thành công: sao lưu và cập nhật database app.')
    args=parser.parse_args()
    model=load_area_model(args.root,args.boundaries,args.boundary_metadata)
    print(json.dumps(fix(args.root,args.prepared,args.db,args.method_file,args.output,model,args.publish),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
