"""Truy cập SQLite chỉ-đọc. Mọi truy vấn của API đi qua đây."""
import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / 'data' / 'vngis.db'

NIGHT_FIELDS = ('nam', 'nguon_anh', 'sol_ntl', 'mat_do_ntl', 'thay_doi_ntl',
                'rad_mean', 'rad_stdDev', 'rad_min', 'rad_max',
                'lit_sol', 'lit_pixels', 'lit_threshold', 'dien_tich_km2',
                'phuong_phap', 'hieu_chinh', 'status')
DAY_FIELDS = ('nam', 'nguon_anh', 'NDVI_mean', 'NDVI_stdDev', 'NDBI_mean', 'NDBI_stdDev',
              'MNDWI_mean', 'MNDWI_stdDev', 'BSI_mean', 'BSI_stdDev',
              'ty_le_pixel_hop_le', 'dien_tich_km2', 'scale_m', 'phuong_phap', 'status')
ECONOMY_FIELDS = ('nam', 'dan_so', 'gdp', 'grdp_bq_dau_nguoi', 'nguon')

# Sentinel-2 trước 2019 là phản xạ đỉnh khí quyển, từ 2019 là phản xạ bề mặt.
# Quyết định đã được giảng viên chấp nhận; app phải nói ra để không ai so sánh mù.
TOA_YEARS = range(2015, 2019)
TOA_WARNING = ('Sentinel-2 2015–2018 là phản xạ đỉnh khí quyển (TOA, L1C); từ 2019 là phản xạ '
               'bề mặt (L2A). So sánh trực tiếp giữa hai giai đoạn cần nêu rõ khác biệt này.')


def database_path():
    return Path(os.environ.get('VNGIS_DB', DEFAULT_DB))


def connect():
    path = database_path()
    if not path.exists():
        raise FileNotFoundError(
            f'Chưa có cơ sở dữ liệu {path}. Chạy: python3 -m app.data.build_indices --root <gốc dữ liệu>')
    connection = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def provinces():
    with connect() as connection:
        rows = connection.execute(
            'SELECT t.ma_tinh,t.number,t.ten_tinh,t.slug,t.gid_1,'
            ' (SELECT COUNT(*) FROM ntl_annual n WHERE n.ma_tinh=t.ma_tinh) AS so_nam_dem,'
            ' (SELECT COUNT(*) FROM day_annual d WHERE d.ma_tinh=t.ma_tinh) AS so_nam_ngay'
            ' FROM tinh t ORDER BY t.number').fetchall()
    return [dict(row) for row in rows]


def _series(connection, table, fields, code, year_from, year_to):
    names = ','.join(f'"{f}"' for f in fields)
    rows = connection.execute(
        f'SELECT {names} FROM {table} WHERE ma_tinh=? AND nam BETWEEN ? AND ? ORDER BY nam',
        (code, year_from, year_to)).fetchall()
    return [dict(row) for row in rows]


def indices(code, year_from=2004, year_to=2025):
    with connect() as connection:
        found = connection.execute('SELECT ten_tinh,slug FROM tinh WHERE ma_tinh=?', (code,)).fetchone()
        if not found:
            return None
        night = _series(connection, 'ntl_annual', NIGHT_FIELDS, code, year_from, year_to)
        day = _series(connection, 'day_annual', DAY_FIELDS, code, year_from, year_to)
        economy = _series(connection, 'kinh_te', ECONOMY_FIELDS, code, year_from, year_to)
    warnings = []
    if any(row['nam'] in TOA_YEARS for row in day):
        warnings.append(TOA_WARNING)
    if night and all(row.get('hieu_chinh') in (None, 'CHUA_HIEU_CHINH') for row in night):
        warnings.append('Chuỗi ánh sáng đêm chưa hiệu chỉnh liên vệ tinh DMSP–VIIRS: '
                        'chỉ so sánh trong cùng một nguồn (DMSP 2004–2013, VIIRS 2014–2025).')
    fake = any(row.get('status') == 'GIA_LAP' for row in night + day) \
        or any(row.get('nguon') == 'GIA_LAP' for row in economy)
    if fake:
        warnings.insert(0, 'SỐ LIỆU GIẢ LẬP — chỉ để minh họa giao diện, tuyệt đối không dùng '
                           'cho báo cáo hay kết luận. Chỉ số thật chưa tính xong.')
    return {'ma_tinh': code, 'ten_tinh': found['ten_tinh'], 'slug': found['slug'],
            'gia_lap': fake,
            'nam_tu': year_from, 'nam_den': year_to,
            'dem': night, 'ngay': day, 'kinh_te': economy,
            'thieu_du_lieu': {'dem': not night, 'ngay': not day, 'kinh_te': not economy},
            'canh_bao': warnings}


def cog_years(kind='NTL'):
    with connect() as connection:
        rows = connection.execute(
            'SELECT nam,duong_dan,nguon_anh,dung_luong_byte FROM anh_cog WHERE loai=? ORDER BY nam',
            (kind,)).fetchall()
    return [dict(row) for row in rows]


def cog_path(kind, year):
    with connect() as connection:
        row = connection.execute('SELECT duong_dan FROM anh_cog WHERE loai=? AND nam=?',
                                 (kind, year)).fetchone()
    return row['duong_dan'] if row else None


def originals():
    with connect() as connection:
        rows = connection.execute(
            'SELECT loai,nam,duong_dan,dung_luong_byte,ghi_chu FROM anh_goc ORDER BY loai,nam').fetchall()
    return [dict(row) for row in rows]


def coverage():
    """Số liệu cho trang trạng thái: năm nào đã có gì. Dùng để báo cáo tiến độ."""
    with connect() as connection:
        out = {}
        for key, table in (('dem', 'ntl_annual'), ('ngay', 'day_annual'), ('kinh_te', 'kinh_te')):
            rows = connection.execute(
                f'SELECT nam,COUNT(*) AS so_tinh FROM {table} GROUP BY nam ORDER BY nam').fetchall()
            out[key] = [dict(row) for row in rows]
        out['anh_cog'] = [dict(row) for row in connection.execute(
            'SELECT loai,nam,dung_luong_byte FROM anh_cog ORDER BY loai,nam').fetchall()]
    return out
