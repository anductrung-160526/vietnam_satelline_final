"""Nạp data_processed/*.csv vào SQLite cho API đọc. Không tính chỉ số ở đây.

    python3 -m app.data.build_indices --root E:\\SatelliteData --db app/data/vngis.db

Thiếu file CSV nào thì bảng đó để rỗng, không coi là lỗi: app phải chạy được ngay cả khi
chỉ có ảnh đêm mà chưa có ảnh ngày. Mỗi lần chạy nạp lại từ đầu (idempotent).
"""
import argparse
import csv
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
NTL_PACKAGE = 'VN_NTL_Panel_2004_2025'
DAY_PACKAGE = 'VN_LandCover_Panel_2004_2025'

# (bảng, các vị trí CSV có thể có, cột khoá bắt buộc)
SOURCES = {
    'ntl_annual': ([f'{NTL_PACKAGE}/data_processed/ntl_annual.csv',
                    f'{NTL_PACKAGE}/data_processed/ntl_indices_ee.csv',
                    f'{NTL_PACKAGE}/data_processed/vietnam_district_ntl_panel_2004_2025.csv'],),
    'day_annual': ([f'{DAY_PACKAGE}/data_processed/day_indices_annual.csv',
                    f'{DAY_PACKAGE}/data_processed/day_indices_monthly.csv',
                    f'{DAY_PACKAGE}/data_processed/day_indices_monthly_ee.csv'],),
    'kinh_te': (['data_processed/kinh_te.csv', 'app/data/kinh_te.csv'],),
}


def columns(connection, table):
    return [r[1] for r in connection.execute(f'PRAGMA table_info({table})')]


def number(value):
    """CSV của pipeline dùng -9999 và chuỗi rỗng cho 'không có dữ liệu'."""
    if value is None:
        return None
    text = str(value).strip()
    if text in ('', 'NA', 'NaN', 'nan', 'None', '-9999', '-9999.0'):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def rows_of(path, table, want):
    """Đọc CSV, chỉ giữ các cột bảng có, bỏ dòng theo tháng (chỉ lấy tổng hợp năm)."""
    with open(path, encoding='utf-8-sig', newline='') as stream:
        for record in csv.DictReader(stream):
            code = (record.get('ma_tinh') or '').strip()
            year = record.get('nam') or record.get('YEAR') or record.get('year')
            if not code or not str(year or '').strip().isdigit():
                continue
            month = (record.get('thang') or record.get('MONTH') or '').strip()
            if month not in ('', '0', 'ALL', 'NA'):
                continue            # dòng theo tháng: bảng năm không nhận
            row = {'ma_tinh': code.zfill(2), 'nam': int(year)}
            for name in want:
                if name in ('ma_tinh', 'nam') or name not in record:
                    continue
                raw = record[name]
                row[name] = raw.strip() or None if isinstance(raw, str) and not _numeric(name) else number(raw)
            yield row


def _numeric(name):
    return name not in ('nguon_anh', 'phuong_phap', 'hieu_chinh', 'status', 'nguon', 'source_collection')


def load_table(connection, root, table, candidates):
    want = columns(connection, table)
    connection.execute(f'DELETE FROM {table}')
    for relative in candidates:
        path = Path(root) / relative
        if not path.exists():
            path = REPO / relative
        if not path.exists():
            continue
        batch = list(rows_of(path, table, want))
        if not batch:
            continue
        names = sorted({k for row in batch for k in row})
        statement = (f'INSERT OR REPLACE INTO {table} ({",".join(names)}) '
                     f'VALUES ({",".join("?" * len(names))})')
        connection.executemany(statement, [[row.get(n) for n in names] for row in batch])
        return path, len(batch)
    return None, 0


def load_provinces(connection):
    records = json.loads((REPO / 'task_pipeline' / 'provinces.json').read_text(encoding='utf-8'))
    connection.execute('DELETE FROM tinh')
    connection.executemany(
        'INSERT INTO tinh(ma_tinh,number,ten_tinh,slug,gid_1) VALUES(?,?,?,?,?)',
        [(p['ma_tinh'], p['number'], p['ten_tinh'], p['slug'], p.get('gid_1')) for p in records])
    return len(records)


def build(root, db):
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db)
    connection.executescript((HERE / 'schema.sql').read_text(encoding='utf-8'))
    report = {'tinh': load_provinces(connection)}
    for table, (candidates,) in SOURCES.items():
        path, count = load_table(connection, root, table, candidates)
        report[table] = {'rows': count, 'source': str(path) if path else None}
    connection.commit()
    connection.close()
    return report


def main():
    parser = argparse.ArgumentParser(description='Nạp chỉ số vào SQLite cho VNGISDash')
    parser.add_argument('--root', default='/data/SatelliteData',
                        help='Thư mục gốc dữ liệu (E:\\SatelliteData hoặc /data/SatelliteData)')
    parser.add_argument('--db', default=str(HERE / 'vngis.db'))
    arguments = parser.parse_args()
    report = build(arguments.root, arguments.db)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    for table in ('ntl_annual', 'day_annual', 'kinh_te'):
        if not report[table]['rows']:
            print(f'  CHƯA CÓ DỮ LIỆU: {table} — app sẽ báo "chưa có số liệu" cho phần này.')


if __name__ == '__main__':
    main()
