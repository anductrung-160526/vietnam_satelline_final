"""Nạp data_processed/*.csv vào SQLite cho API đọc. Không tính chỉ số ở đây.

    python3 -m app.data.build_indices --root E:\\SatelliteData --db app/data/vngis.db

Thiếu file CSV nào thì bảng đó để rỗng, không coi là lỗi: app phải chạy được ngay cả khi
chỉ có ảnh đêm mà chưa có ảnh ngày. Mỗi lần chạy nạp lại từ đầu (idempotent).

Tên cột phải trùng khớp tên mà task_pipeline/derive.py sinh ra. Lệch tên thì dòng vẫn vào
bảng nhưng cột để rỗng và không có gì báo lỗi — đã xảy ra thật (app đi tìm 'thay_doi_ntl'
trong khi derive ghi 'thay_doi_ntl_pct'). Vì vậy mỗi lần nạp đều in ra cột nào khớp, cột
nào của bảng không có trong CSV, và cột nào CSV có mà bảng bỏ qua.
"""
import argparse
import csv
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

# Tăng mỗi khi schema.sql đổi cấu trúc bảng. 'CREATE TABLE IF NOT EXISTS' bỏ qua bảng đã
# tồn tại, nên cơ sở dữ liệu cũ sẽ thiếu cột mới mà không báo gì — phải dựng lại.
# An toàn: mọi thứ trong vngis.db đều sinh ra từ CSV, không có dữ liệu gốc nào ở đây.
SCHEMA_VERSION = 3
NTL_PACKAGE = 'VN_NTL_Panel_2004_2025'
DAY_PACKAGE = 'VN_LandCover_Panel_2004_2025'

# Cột chữ; mọi cột khác được đọc thành số.
TEXT_COLUMNS = {'ma_tinh', 'ten_tinh', 'nguon_anh', 'ghi_chu', 'hieu_chinh', 'trang_thai',
                'loai_phan_xa', 'nguon', 'source_collection', 'phuong_phap', 'status'}

# bảng -> các vị trí CSV có thể có, và cách gộp (None = mỗi dòng một năm sẵn rồi)
SOURCES = {
    'ntl_annual': ([f'{NTL_PACKAGE}/data_processed/ntl_annual.csv',
                    f'{NTL_PACKAGE}/data_processed/ntl_indices_ee.csv'], None),
    # derive ghi chỉ số ngày theo THÁNG; app hiển thị theo năm nên gộp trung bình các tháng.
    'day_annual': ([f'{DAY_PACKAGE}/data_processed/day_indices_monthly.csv',
                    f'{DAY_PACKAGE}/data_processed/day_indices_annual.csv',
                    f'{DAY_PACKAGE}/data_processed/day_indices_monthly_ee.csv'], 'thang'),
    'kinh_te': (['data_processed/kinh_te.csv', 'app/data/kinh_te.csv'], None),
}


def load_provinces(connection):
    records = json.loads((REPO / 'task_pipeline' / 'provinces.json').read_text(encoding='utf-8'))
    connection.execute('DELETE FROM tinh')
    connection.executemany(
        'INSERT INTO tinh(ma_tinh,number,ten_tinh,slug,gid_1) VALUES(?,?,?,?,?)',
        [(p['ma_tinh'], p['number'], p['ten_tinh'], p['slug'], p.get('gid_1')) for p in records])
    return len(records)


def mo(db):
    """Mở cơ sở dữ liệu, dựng lại từ đầu nếu schema đã đổi.

    Dựng lại là xoá sạch, nên mọi lối vào đều phải để lại một cơ sở dữ liệu dùng được:
    danh mục 63 tỉnh luôn được nạp. Thiếu bước này thì chạy build_cogs sau khi đổi schema
    sẽ xoá hết tỉnh và giao diện báo "0 tỉnh" — đã xảy ra thật.
    """
    path = Path(db)
    path.parent.mkdir(parents=True, exist_ok=True)
    da_dung_lai = False
    if path.exists():
        thu = sqlite3.connect(path)
        cu = thu.execute('PRAGMA user_version').fetchone()[0]
        thu.close()
        if cu != SCHEMA_VERSION:
            print(f'  Cấu trúc bảng đổi ({cu} -> {SCHEMA_VERSION}): dựng lại {path.name}.')
            print('  >>> Chỉ số đã nạp trước đó MẤT. Chạy lại:'
                  ' python -m app.data.build_indices --root <gốc dữ liệu>')
            path.unlink()
            da_dung_lai = True
    connection = sqlite3.connect(path)
    connection.executescript((HERE / 'schema.sql').read_text(encoding='utf-8'))
    connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
    if connection.execute('SELECT COUNT(*) FROM tinh').fetchone()[0] == 0:
        load_provinces(connection)
        connection.commit()
        if not da_dung_lai:
            print('  Đã nạp danh mục 63 tỉnh.')
    return connection


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


def text(value):
    if value is None:
        return None
    return str(value).strip() or None


def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def cell(name, raw):
    return text(raw) if name in TEXT_COLUMNS else number(raw)


def rows_of(records, want, monthly):
    """Chuyển bản ghi CSV thành dòng của bảng, gộp lên năm nếu nguồn ghi theo tháng."""
    gom = {}
    for record in records:
        code = (record.get('ma_tinh') or '').strip()
        year = record.get('nam') or record.get('YEAR') or record.get('year')
        if not code or not str(year or '').strip().isdigit():
            continue
        month = (record.get(monthly) or '').strip() if monthly else ''
        if not monthly and month not in ('', '0', 'ALL', 'NA'):
            continue
        key = (code.zfill(2), int(year))
        row = {name: cell(name, record[name]) for name in want if name in record}
        row['ma_tinh'], row['nam'] = key
        gom.setdefault(key, []).append(row)

    out = []
    for (code, year), phan in sorted(gom.items()):
        if len(phan) == 1 and not monthly:
            out.append(phan[0])
            continue
        hop = {'ma_tinh': code, 'nam': year}
        for name in want:
            if name in ('ma_tinh', 'nam', 'so_thang'):
                continue
            values = [p[name] for p in phan if p.get(name) is not None]
            if not values:
                continue
            if name in TEXT_COLUMNS:
                hop[name] = sorted({str(v) for v in values})[0] if len(set(values)) == 1 \
                    else '/'.join(sorted({str(v) for v in values}))
            else:
                hop[name] = round(sum(values) / len(values), 6)
        if 'so_thang' in want:
            hop['so_thang'] = len(phan)
        out.append(hop)
    return out


def load_table(connection, root, table, candidates, monthly):
    want = columns(connection, table)
    connection.execute(f'DELETE FROM {table}')
    for relative in candidates:
        path = Path(root) / relative
        if not path.exists():
            path = REPO / relative
        if not path.exists():
            continue
        header, records = read_csv(path)
        batch = rows_of(records, want, monthly if monthly and monthly in header else None)
        if not batch:
            continue
        names = sorted({k for row in batch for k in row})
        connection.executemany(
            f'INSERT OR REPLACE INTO {table} ({",".join(names)}) '
            f'VALUES ({",".join("?" * len(names))})',
            [[row.get(n) for n in names] for row in batch])
        return {'rows': len(batch), 'source': str(path),
                'cot_khop': sorted(set(header) & set(want)),
                'cot_bang_thieu_trong_csv': sorted(set(want) - set(header) - {'so_thang'}),
                'cot_csv_khong_dung': sorted(set(header) - set(want))}
    return {'rows': 0, 'source': None, 'cot_khop': [],
            'cot_bang_thieu_trong_csv': [], 'cot_csv_khong_dung': []}


def build(root, db):
    connection = mo(db)
    report = {'tinh': load_provinces(connection)}
    for table, (candidates, monthly) in SOURCES.items():
        report[table] = load_table(connection, root, table, candidates, monthly)
    connection.commit()
    connection.close()
    return report


def main():
    parser = argparse.ArgumentParser(description='Nạp chỉ số vào SQLite cho VNGISDash')
    parser.add_argument('--root', default='/data/SatelliteData',
                        help='Thư mục gốc dữ liệu (E:\\SatelliteData hoặc /data/SatelliteData)')
    parser.add_argument('--db', default=str(HERE / 'vngis.db'))
    parser.add_argument('--chi-tiet', action='store_true', dest='chi_tiet',
                        help='In đầy đủ danh sách cột')
    arguments = parser.parse_args()
    report = build(arguments.root, arguments.db)

    print(f"tinh: {report['tinh']} dòng")
    for table in ('ntl_annual', 'day_annual', 'kinh_te'):
        info = report[table]
        print(f"\n{table}: {info['rows']} dòng")
        if not info['rows']:
            print(f'  CHƯA CÓ DỮ LIỆU — app sẽ báo "chưa có số liệu" cho phần này.')
            continue
        print(f"  nguồn: {info['source']}")
        print(f"  {len(info['cot_khop'])} cột khớp"
              + (f": {', '.join(info['cot_khop'])}" if arguments.chi_tiet else ''))
        if info['cot_bang_thieu_trong_csv']:
            print('  CỘT RỖNG (bảng có, CSV không có): '
                  + ', '.join(info['cot_bang_thieu_trong_csv']))
        if info['cot_csv_khong_dung']:
            print('  cột CSV app chưa dùng: ' + ', '.join(info['cot_csv_khong_dung']))
    print('\nMọi "CỘT RỖNG" là chỉ số sẽ trống trên giao diện. Nếu tên chỉ lệch nhau chút ít '
          '(ví dụ thay_doi_ntl và thay_doi_ntl_pct) thì đó là lỗi, cần sửa schema cho khớp.')


if __name__ == '__main__':
    main()
