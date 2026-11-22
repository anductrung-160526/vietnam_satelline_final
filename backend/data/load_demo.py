"""Nạp dữ liệu phần B bằng transaction; sao lưu SQLite, không reset bảng/COG cũ.

python -m backend.data.load_demo --root E:\\SatelliteData --prepared E:\\SatelliteData\\_demo_preparation\\<thời điểm>
Có thể thêm --indices-dir <thư mục ntl_annual.csv, ntl_monthly.csv đã tính>.
"""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from .build_indices import mo, load_provinces, TEXT_COLUMNS, number
from .prepare_grdp import provinces

SCHEMA = Path(__file__).with_name('demo_schema.sql')


def read_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def backup_database(db):
    db = Path(db)
    if not db.exists():
        return None
    backup = db.with_name(db.name+'.backup_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    with sqlite3.connect(db) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    return str(backup)


def load(root, prepared, db, indices_dir=None, manifest_path=None):
    root, prepared, db = Path(root).resolve(), Path(prepared).resolve(), Path(db)
    catalog = {p['ma_tinh'] for p in provinces()}
    prices = read_rows(prepared/'grdp_all_prices.csv')
    manifest = read_rows(manifest_path or prepared/'manifest_candidates.csv')
    inventory = read_rows(prepared/'image_inventory.csv')
    seen = set()
    for row in prices:
        key = (row['province_code'], int(row['year']), row['grdp_price_basis'])
        if key in seen or key[0] not in catalog or key[2] not in ('so_sanh', 'hien_hanh'):
            raise ValueError(f'GRDP trùng khóa/không hợp lệ: {key}')
        seen.add(key)
        if row['unit'] != 'ty_vnd':
            raise ValueError('App hiện hiển thị GRDP theo tỷ đồng; cần đổi đơn vị trước khi nạp.')
    assets = {}
    supports = []
    recovery_rows = []
    for kind, items in [('processed', manifest), ('raw', inventory)]:
        for row in items:
            if row.get('province_code') not in catalog:
                continue
            if kind == 'raw':
                # Raw là file avg_rad/cf_cvg gốc; không lấy nhầm avg_rad_filtered.
                if json.loads(row.get('band_names') or '[]') != ['avg_rad', 'cf_cvg']:
                    continue
                if row.get('filter_evidence') or 'raw_data' not in Path(row['path']).parts:
                    continue
            path = Path(row['path']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError(f'Đường dẫn ảnh không tồn tại hoặc ngoài --root: {path}')
            key = (row['province_code'], int(row['year']), int(row['month']), kind)
            if key in assets and assets[key]['path'] != str(path):
                raise ValueError(f'Trùng ảnh {key}; cần chọn nguồn trước khi nạp.')
            assets[key] = dict(path=str(path), source=row['source'], band_names=row.get('band_names', '[]'))
    support_file = Path(manifest_path).parent/'annual_observation_support.csv' if manifest_path else None
    if support_file is not None and support_file.is_file():
        for row in read_rows(support_file):
            code, year = row['province_code'], int(row['year'])
            path = Path(row['support_path']).resolve()
            if code not in catalog or not path.is_relative_to(root) or not path.is_file():
                raise ValueError('Bản đồ số tháng hợp lệ không đúng mã tỉnh/đường dẫn trong kho.')
            supports.append((code, year, json.dumps(row, ensure_ascii=False)))
            assets[(code,year,0,'support')] = dict(path=str(path), source='VIIRS', band_names='["valid_month_count"]')
    recovery_file = Path(manifest_path).parent/'monthly_recovery_audit.csv' if manifest_path else None
    if recovery_file is not None and recovery_file.is_file():
        for row in read_rows(recovery_file):
            code, year, month = row['province_code'], int(row['year']), int(row['month'])
            if code not in catalog or not 1 <= month <= 12:
                raise ValueError('Khóa báo cáo kiểm tra ảnh tháng không hợp lệ.')
            recovery_rows.append((code,year,month,json.dumps(row,ensure_ascii=False)))
    # Kết quả đã tính theo dictionary: tên gid_1 được ánh xạ bằng danh mục chính thức.
    dictionary_rows = []
    dictionary_keys = set()
    by_gid = {p['gid_1']: p['ma_tinh'] for p in provinces()}
    directory = Path(indices_dir) if indices_dir else root/'VN_NTL_Panel_2004_2025/data_processed'
    from .dataset import checked_snapshot, migrate_demo, register_snapshot
    for table_name in ('night_data', 'night_economy'):
        file = directory/(table_name+'.csv')
        if not file.exists():
            continue
        for row in read_rows(file):
            code = row.get('province_code') or by_gid.get(row.get('gid_1'))
            if code not in catalog:
                raise ValueError(f'{file}: mã tỉnh/GADM không hợp lệ.')
            basis = row.get('grdp_price_basis', '') if table_name == 'night_economy' else ''
            if basis not in ('', 'so_sanh', 'hien_hanh'):
                raise ValueError(f'{file}: cơ sở giá không hợp lệ.')
            key = (code, int(row['year']), int(row['month']), table_name, basis)
            if key in dictionary_keys:
                raise ValueError(f'{file}: trùng khóa kết quả {key}')
            dictionary_keys.add(key)
            # Không dùng kết quả thiếu nhãn giá làm kết quả chính thức của giá so sánh.
            dictionary_rows.append((*key, json.dumps(row, ensure_ascii=False)))
    snapshot = checked_snapshot(directory)
    backup = backup_database(db)
    if db.exists():
        # Không gọi mo trên database cũ: tránh cơ chế dựng lại schema xóa COG.
        connection = sqlite3.connect(db)
    else:
        connection = mo(db)
    try:
        migrate_demo(connection)
        with connection:
            load_provinces(connection)
            connection.executemany(
                'INSERT OR REPLACE INTO economy_prices VALUES(?,?,?,?,?,?,?,?,?,?)',
                [(r['province_code'], int(r['year']), r['grdp_price_basis'], number(r['grdp']),
                  number(r.get('population')), number(r['price_base_year']), r['unit'],
                  int(r['is_provisional']), r['source'], r.get('quality_flags', '')) for r in prices])
            # Chỉ cập nhật các mốc được nạp, không xóa tài sản ở mốc khác.
            connection.executemany('INSERT OR REPLACE INTO demo_asset VALUES(?,?,?,?,?,?,?)',
                                   [(*key, r['path'], r['source'], r['band_names']) for key, r in assets.items()])
            connection.executemany('INSERT OR REPLACE INTO annual_observation_support VALUES(?,?,?)', supports)
            connection.executemany('INSERT OR REPLACE INTO monthly_recovery_audit VALUES(?,?,?,?)', recovery_rows)
            connection.executemany('INSERT OR REPLACE INTO demo_result VALUES(?,?,?,?,?,?)', dictionary_rows)
            imported = {}
            directory = Path(indices_dir) if indices_dir else root/'VN_NTL_Panel_2004_2025/data_processed'
            for table in ('ntl_annual', 'ntl_monthly'):
                path = directory/(table+'.csv')
                imported[table] = 0
                if not path.exists():
                    continue
                columns = {r[1] for r in connection.execute(f'PRAGMA table_info({table})')}
                for row in read_rows(path):
                    code = row.get('province_code', '').zfill(2)
                    if code not in catalog or not row.get('year'):
                        raise ValueError(f'{path}: thiếu khóa tỉnh/năm hợp lệ.')
                    values = {k: (v if k in TEXT_COLUMNS else number(v)) for k, v in row.items() if k in columns}
                    values['province_code'] = code
                    if table == 'ntl_monthly' and not row.get('month'):
                        raise ValueError(f'{path}: thiếu khóa tháng.')
                    keys = list(values)
                    sql = f'INSERT OR REPLACE INTO {table} ({",".join(keys)}) VALUES ({",".join("?" for _ in keys)})'
                    connection.execute(sql, [values[k] for k in keys])
                    imported[table] += 1
            register_snapshot(connection,snapshot,directory,manifest)
    finally:
        connection.close()
    return {'backup': backup, 'prices': len(prices), 'assets': len(assets), 'dictionary_results': len(dictionary_rows), 'indices': imported}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--db', type=Path, default=Path(__file__).with_name('vngis.db'))
    parser.add_argument('--indices-dir', type=Path)
    parser.add_argument('--manifest', type=Path, help='Manifest mới sau sửa ảnh; giữ nguyên bộ chuẩn bị gốc.')
    args = parser.parse_args()
    print(json.dumps(load(args.root, args.prepared, args.db, args.indices_dir, args.manifest), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
