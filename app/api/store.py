"""Truy cập SQLite chỉ-đọc. Mọi truy vấn của API đi qua đây."""
import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / 'data' / 'vngis.db'

# Tên cột lấy đúng theo task_pipeline/derive.py. Đổi tên ở đây mà không đổi ở derive thì
# bảng vẫn nạp được dòng nhưng cột rỗng, và không có gì báo lỗi — đã xảy ra thật.
NIGHT_FIELDS = ('nam', 'nguon_anh', 'sol_ntl', 'mat_do_ntl', 'thay_doi_ntl',
                'sol_ntl_hc', 'mat_do_ntl_hc', 'thay_doi_ntl_hc',
                'sol_ntl_tho', 'nguong_nen', 'so_pixel_nen',
                'mean_ntl', 'std_ntl', 'min_ntl', 'max_ntl', 'cv_ntl',
                'so_pixel_hop_le', 'so_pixel_sang', 'dt_sang_km2', 'ty_le_sang_pct',
                'sol_vung_sang', 'nguong_sang',
                'dt_tu_nhien_km2', 'ghi_chu', 'hieu_chinh', 'trang_thai')
DAY_FIELDS = ('nam', 'nguon_anh', 'loai_phan_xa',
              'NDVI_mean', 'NDVI_std', 'NDBI_mean', 'NDBI_std',
              'MNDWI_mean', 'MNDWI_std', 'BSI_mean', 'BSI_std',
              'ty_le_hop_le_pct', 'dt_hop_le_km2', 'dt_tu_nhien_km2',
              'so_thang', 'trang_thai')
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
    # derive.py ghi hieu_chinh='PENDING'; CLAUDE.md lại nói 'CHUA_HIEU_CHINH'. Nhận cả hai,
    # và chốt bằng nguon_anh: chuỗi có cả DMSP lẫn VIIRS thì chắc chắn bắc qua mốc đổi vệ tinh.
    nguon = {row.get('nguon_anh') for row in night}
    bac_qua_moc = len(nguon - {None}) > 1
    chua_hieu_chinh = any(row.get('hieu_chinh') in ('PENDING', 'CHUA_HIEU_CHINH') for row in night)
    da_hieu_chinh = any(row.get('sol_ntl_hc') is not None for row in night)
    if bac_qua_moc and da_hieu_chinh and not chua_hieu_chinh:
        warnings.append('Chuỗi bắc qua mốc đổi vệ tinh 2013 và ĐÃ hiệu chỉnh DMSP→VIIRS: '
                        'dùng sol_ntl_hc khi so sánh hai giai đoạn, sol_ntl là giá trị gốc '
                        'theo thang đo riêng của từng vệ tinh.')
    elif bac_qua_moc or (night and chua_hieu_chinh):
        warnings.append('Chuỗi ánh sáng đêm CHƯA hiệu chỉnh liên vệ tinh DMSP–VIIRS: '
                        'chỉ so sánh trong cùng một nguồn (DMSP 2004–2013, VIIRS 2014–2025). '
                        'Chạy: python3 -m task_pipeline.harmonize')
    fake = any(row.get('trang_thai') == 'GIA_LAP' for row in night + day) \
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
            'SELECT nam,duong_dan,nguon_anh,dung_luong_byte,tay,nam_do,dong,bac '
            'FROM anh_cog WHERE loai=? ORDER BY nam',
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


# --- Bảng chỉ số kiểu World Development Indicators -------------------------------------
# Mỗi chỉ số: mã, tên hiển thị, đơn vị, bảng nguồn, số chữ số thập phân khi hiển thị.
# Thêm chỉ số mới ở đây là nó tự xuất hiện trong giao diện và trong file tải về.
INDICATORS = (
    dict(ma='sol_ntl', ten='Tổng độ sáng ban đêm (SOL)', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=2,
         mo_ta='Tổng bức xạ ban đêm trong ranh giới tỉnh.'),
    dict(ma='mat_do_ntl', ten='Mật độ sáng ban đêm', don_vi='nW/cm²/sr trên km²',
         bang='ntl_annual', chu_so=4,
         mo_ta='Tổng độ sáng chia cho diện tích tỉnh.'),
    dict(ma='thay_doi_ntl', ten='Biến động độ sáng so với năm trước', don_vi='%',
         bang='ntl_annual', chu_so=2,
         mo_ta='Chỉ so trong cùng một nguồn; bỏ trống tại mốc DMSP→VIIRS năm 2013.'),
    dict(ma='sol_ntl_hc', ten='Tổng độ sáng (đã hiệu chỉnh DMSP→VIIRS)', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=2,
         mo_ta='Chuỗi thống nhất 2004–2025: DMSP quy về thang VIIRS bằng hàm lũy thừa '
               'khớp trên năm chồng lấn 2013. Dùng cột này khi so sánh xuyên mốc 2013.'),
    dict(ma='mat_do_ntl_hc', ten='Mật độ sáng (đã hiệu chỉnh)', don_vi='nW/cm²/sr trên km²',
         bang='ntl_annual', chu_so=4, mo_ta='sol_ntl_hc chia diện tích tỉnh.'),
    dict(ma='thay_doi_ntl_hc', ten='Biến động (đã hiệu chỉnh)', don_vi='%',
         bang='ntl_annual', chu_so=2,
         mo_ta='Tính trên chuỗi đã hiệu chỉnh nên có giá trị cả ở mốc 2013→2014.'),
    dict(ma='sol_ntl_tho', ten='Tổng độ sáng trước khi trừ nền', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=2,
         mo_ta='Để đo bước lọc nền lấy đi bao nhiêu; không dùng cho phân tích.'),
    dict(ma='mean_ntl', ten='Độ sáng trung bình mỗi điểm ảnh', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=4, mo_ta='Giá trị trung bình trên mọi điểm ảnh hợp lệ.'),
    dict(ma='max_ntl', ten='Điểm sáng nhất tỉnh', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=2, mo_ta='Giá trị lớn nhất trong ranh giới tỉnh.'),
    dict(ma='std_ntl', ten='Độ lệch chuẩn bức xạ', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=4, mo_ta='Mức phân tán độ sáng giữa các điểm ảnh.'),
    dict(ma='cv_ntl', ten='Hệ số biến thiên ánh sáng', don_vi='không thứ nguyên',
         bang='ntl_annual', chu_so=4,
         mo_ta='std/mean — chênh lệch sáng–tối trong tỉnh; cao nghĩa là tập trung vào vài điểm.'),
    dict(ma='so_pixel_sang', ten='Số điểm ảnh sáng', don_vi='điểm ảnh',
         bang='ntl_annual', chu_so=0,
         mo_ta='Vượt ngưỡng sáng: VIIRS ≥ 1,5 nW/cm²/sr, DMSP ≥ DN 5. Hai thang đo khác nhau.'),
    dict(ma='dt_sang_km2', ten='Diện tích được chiếu sáng', don_vi='km²',
         bang='ntl_annual', chu_so=2, mo_ta='Tổng diện tích các điểm ảnh vượt ngưỡng sáng.'),
    dict(ma='ty_le_sang_pct', ten='Tỷ lệ diện tích được chiếu sáng', don_vi='%',
         bang='ntl_annual', chu_so=2,
         mo_ta='dt_sang_km2 chia diện tích tỉnh — thay cho "tỷ lệ thắp sáng" của luồng cũ.'),
    dict(ma='sol_vung_sang', ten='Độ sáng của vùng sáng', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=2,
         mo_ta='Tổng bức xạ chỉ trên vùng vượt ngưỡng; loại nhiễu nền của vùng tối.'),
    dict(ma='so_pixel_hop_le', ten='Số điểm ảnh có dữ liệu', don_vi='điểm ảnh',
         bang='ntl_annual', chu_so=0,
         mo_ta='Dùng để kiểm tra độ phủ; DMSP 1 km nên ít điểm hơn VIIRS 500 m rất nhiều.'),
    dict(ma='dt_tu_nhien_km2', ten='Diện tích tự nhiên', don_vi='km²',
         bang='ntl_annual', chu_so=1, mo_ta='Diện tích trong ranh giới GADM 4.1.'),
    dict(ma='NDVI_mean', ten='NDVI trung bình', don_vi='chỉ số -1…1',
         bang='day_annual', chu_so=4, mo_ta='Chỉ số thực vật.'),
    dict(ma='NDBI_mean', ten='NDBI trung bình', don_vi='chỉ số −1…1',
         bang='day_annual', chu_so=4, mo_ta='Chỉ số xây dựng.'),
    dict(ma='MNDWI_mean', ten='MNDWI trung bình', don_vi='chỉ số −1…1',
         bang='day_annual', chu_so=4, mo_ta='Chỉ số mặt nước.'),
    dict(ma='BSI_mean', ten='BSI trung bình', don_vi='chỉ số −1…1',
         bang='day_annual', chu_so=4, mo_ta='Chỉ số đất trống.'),
    dict(ma='dan_so', ten='Dân số', don_vi='người', bang='kinh_te', chu_so=0,
         mo_ta='Do giảng viên cung cấp.'),
    dict(ma='gdp', ten='GDP', don_vi='tỷ đồng', bang='kinh_te', chu_so=0,
         mo_ta='Do giảng viên cung cấp.'),
)
BY_CODE = {entry['ma']: entry for entry in INDICATORS}


def indicators():
    """Danh mục chỉ số, kèm số tỉnh và khoảng năm thực sự có dữ liệu của từng chỉ số."""
    out = []
    with connect() as connection:
        for entry in INDICATORS:
            row = connection.execute(
                f'SELECT COUNT(DISTINCT ma_tinh),MIN(nam),MAX(nam) '
                f'FROM {entry["bang"]} WHERE "{entry["ma"]}" IS NOT NULL').fetchone()
            out.append(dict(entry, so_tinh=row[0] or 0, nam_tu=row[1], nam_den=row[2]))
    return out


def panel(code, year_from=2004, year_to=2025, codes=None):
    """Bảng rộng kiểu WDI: mỗi dòng một tỉnh, mỗi cột một năm.

    Trả về None nếu mã chỉ số không có trong danh mục — không bao giờ ghép chuỗi mã
    người dùng gửi vào câu SQL.
    """
    entry = BY_CODE.get(code)
    if entry is None:
        return None
    wanted = [c.strip().zfill(2) for c in codes if c.strip()] if codes else None
    years = list(range(year_from, year_to + 1))
    with connect() as connection:
        provinces_rows = connection.execute(
            'SELECT ma_tinh,ten_tinh,number FROM tinh ORDER BY number').fetchall()
        values = connection.execute(
            f'SELECT ma_tinh,nam,"{entry["ma"]}" FROM {entry["bang"]} '
            f'WHERE nam BETWEEN ? AND ? AND "{entry["ma"]}" IS NOT NULL',
            (year_from, year_to)).fetchall()
        sources = {row[0]: row[1] for row in connection.execute(
            f'SELECT ma_tinh,GROUP_CONCAT(DISTINCT nguon_anh) FROM {entry["bang"]} '
            f'WHERE nam BETWEEN ? AND ? GROUP BY ma_tinh', (year_from, year_to))
        } if entry['bang'] != 'kinh_te' else {}
    grid = {}
    for code_, year, value in values:
        grid.setdefault(code_, {})[year] = value
    rows = []
    for province in provinces_rows:
        if wanted is not None and province['ma_tinh'] not in wanted:
            continue
        series = grid.get(province['ma_tinh'], {})
        rows.append({'ma_tinh': province['ma_tinh'], 'ten_tinh': province['ten_tinh'],
                     'nguon_anh': sources.get(province['ma_tinh']),
                     'gia_tri': [series.get(year) for year in years]})
    return {'chi_so': dict(entry), 'nam': years, 'dong': rows,
            'so_tinh_co_du_lieu': sum(1 for r in rows if any(v is not None for v in r['gia_tri'])),
            'canh_bao': _panel_warnings(entry, years)}


def _panel_warnings(entry, years):
    warnings = []
    if entry['bang'] == 'ntl_annual' and min(years) <= 2013 <= max(years):
        warnings.append('Chuỗi bắc qua mốc đổi vệ tinh: DMSP-OLS đến 2013, VIIRS từ 2014. '
                        'Chưa hiệu chỉnh liên vệ tinh — không so sánh trực tiếp hai giai đoạn.')
    if entry['bang'] == 'day_annual' and any(y in TOA_YEARS for y in years):
        warnings.append(TOA_WARNING)
    if entry['bang'] == 'kinh_te':
        warnings.append('Số liệu kinh tế do giảng viên cung cấp, không trích xuất từ ảnh vệ tinh.')
    return warnings


def choropleth(code, year):
    """Một chỉ số, một năm, mọi tỉnh — để tô màu bản đồ toàn quốc."""
    entry = BY_CODE.get(code)
    if entry is None:
        return None
    with connect() as connection:
        rows = connection.execute(
            f'SELECT ma_tinh,"{entry["ma"]}" FROM {entry["bang"]} '
            f'WHERE nam=? AND "{entry["ma"]}" IS NOT NULL', (year,)).fetchall()
    values = {row[0]: row[1] for row in rows}
    numbers = sorted(v for v in values.values() if v is not None)
    return {'chi_so': dict(entry), 'nam': year, 'gia_tri': values,
            'nho_nhat': numbers[0] if numbers else None,
            'lon_nhat': numbers[-1] if numbers else None,
            'trung_vi': numbers[len(numbers) // 2] if numbers else None}
