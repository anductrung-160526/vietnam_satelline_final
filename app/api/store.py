"""Truy cập SQLite chỉ-đọc. Mọi truy vấn của API đi qua đây."""
import os
import re
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / 'data' / 'vngis.db'

# Tên cột lấy đúng theo task_pipeline/derive.py. Đổi tên ở đây mà không đổi ở derive thì
# bảng vẫn nạp được dòng nhưng cột rỗng, và không có gì báo lỗi — đã xảy ra thật.
NIGHT_FIELDS = ('year', 'source', 'sol', 'sol_density', 'sol_change_pct',
                'sol_cal', 'sol_density_cal', 'sol_change_cal_pct',
                'sol_raw', 'background_threshold', 'background_pixels',
                'rad_mean', 'rad_std', 'rad_min', 'rad_max', 'rad_cv',
                'valid_pixels', 'lit_pixels', 'lit_area_km2', 'lit_area_pct',
                'lit_sol', 'lit_threshold',
                'area_km2', 'note', 'calibration', 'status')
DAY_FIELDS = ('year', 'source', 'reflectance_type',
              'NDVI_mean', 'NDVI_std', 'NDBI_mean', 'NDBI_std',
              'MNDWI_mean', 'MNDWI_std', 'BSI_mean', 'BSI_std',
              'valid_area_pct', 'valid_area_km2', 'area_km2',
              'months_used', 'status')
ECONOMY_FIELDS = ('year', 'population', 'gdp', 'gdp_per_capita', 'source')

# Sentinel-2 trước 2019 là phản xạ đỉnh khí quyển, từ 2019 là phản xạ bề mặt.
# Quyết định đã được giảng viên chấp nhận; app phải nói ra để không ai so sánh mù.
# Nghĩa của cờ CL_OBS_STATUS, gửi kèm mỗi bảng để giao diện không phải chép lại.
CHU_GIAI_CO = {
    'B': 'đứt gãy chuỗi do đổi vệ tinh',
    'L': 'có ảnh nhưng không điểm ảnh nào hợp lệ',
    'O': 'không có ảnh',
    'U': 'ít lượt quan sát sạch mây, độ tin cậy thấp',
}

TOA_YEARS = range(2015, 2019)
TOA_WARNING = ('Sentinel-2 2015–2018 là phản xạ đỉnh khí quyển (TOA, L1C); từ 2019 là phản xạ '
               'bề mặt (L2A). So sánh trực tiếp giữa hai giai đoạn cần nêu rõ khác biệt này.')

# Mốc đổi vệ tinh thứ hai, nằm GIỮA giai đoạn DMSP và chưa được hiệu chỉnh.
# NOAA không hiệu chuẩn các vệ tinh DMSP với nhau, và F16 (đến 2009) với F18
# (từ 2010) không có năm nào cùng phủ nên không đo được độ lệch bằng dữ liệu này.
# Cột sol_cal KHÔNG sửa mốc này — nó chỉ xử lý mốc DMSP→VIIRS năm 2013.
MOC_2010 = ('Chuỗi bắc qua năm 2010, là mốc đổi vệ tinh DMSP F16→F18. Hai vệ tinh '
            'không được NOAA hiệu chuẩn với nhau và dự án đã chốt KHÔNG hiệu chỉnh '
            'mốc này, nên chênh lệch tại đây phần lớn là do đổi cảm biến chứ không '
            'phải kinh tế. Không so sánh trực tiếp 2004–2009 với 2010–2013, kể cả '
            'trên cột đã hiệu chỉnh.')


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
            'SELECT t.province_code,t.number,t.province_name,t.slug,t.gid_1,'
            ' (SELECT COUNT(*) FROM ntl_annual n WHERE n.province_code=t.province_code) AS so_nam_dem,'
            ' (SELECT COUNT(*) FROM day_annual d WHERE d.province_code=t.province_code) AS so_nam_ngay'
            ' FROM province t ORDER BY t.number').fetchall()
    return [dict(row) for row in rows]


def province(code):
    """Một tỉnh theo mã, hoặc None. slug dùng để đặt tên tệp tải xuống (chỉ ASCII)."""
    with connect() as connection:
        row = connection.execute(
            'SELECT province_code,province_name,slug,number,gid_1 FROM province '
            'WHERE province_code=?', (code,)).fetchone()
    return dict(row) if row else None


def _series(connection, table, fields, code, year_from, year_to):
    names = ','.join(f'"{f}"' for f in fields)
    rows = connection.execute(
        f'SELECT {names} FROM {table} WHERE province_code=? AND year BETWEEN ? AND ? ORDER BY year',
        (code, year_from, year_to)).fetchall()
    return [dict(row) for row in rows]


def indices(code, year_from=2004, year_to=2025):
    with connect() as connection:
        found = connection.execute('SELECT province_name,slug FROM province WHERE province_code=?', (code,)).fetchone()
        if not found:
            return None
        night = _series(connection, 'ntl_annual', NIGHT_FIELDS, code, year_from, year_to)
        day = _series(connection, 'day_annual', DAY_FIELDS, code, year_from, year_to)
        economy = _series(connection, 'economy', ECONOMY_FIELDS, code, year_from, year_to)
    warnings = []
    if any(row['year'] in TOA_YEARS for row in day):
        warnings.append(TOA_WARNING)
    # derive.py ghi calibration='PENDING'; CLAUDE.md lại nói 'CHUA_HIEU_CHINH'. Nhận cả hai,
    # và chốt bằng source: chuỗi có cả DMSP lẫn VIIRS thì chắc chắn bắc qua mốc đổi vệ tinh.
    nam_dem = [int(row['year']) for row in night if row.get('year') is not None]
    if nam_dem and min(nam_dem) <= 2009 and max(nam_dem) >= 2010:
        warnings.append(MOC_2010)
    nguon = {row.get('source') for row in night}
    bac_qua_moc = len(nguon - {None}) > 1
    chua_hieu_chinh = any(row.get('calibration') in ('PENDING', 'CHUA_HIEU_CHINH') for row in night)
    da_hieu_chinh = any(row.get('sol_cal') is not None for row in night)
    if bac_qua_moc and da_hieu_chinh and not chua_hieu_chinh:
        warnings.append('Chuỗi bắc qua mốc đổi vệ tinh 2013 và ĐÃ hiệu chỉnh DMSP→VIIRS: '
                        'dùng sol_cal khi so sánh hai giai đoạn, sol là giá trị gốc '
                        'theo thang đo riêng của từng vệ tinh.')
    elif bac_qua_moc or (night and chua_hieu_chinh):
        warnings.append('Chuỗi ánh sáng đêm CHƯA hiệu chỉnh liên vệ tinh DMSP–VIIRS: '
                        'chỉ so sánh trong cùng một nguồn (DMSP 2004–2013, VIIRS 2014–2025). '
                        'Chạy: python3 -m task_pipeline.harmonize')
    fake = any(row.get('status') == 'GIA_LAP' for row in night + day) \
        or any(row.get('source') == 'GIA_LAP' for row in economy)
    if fake:
        warnings.insert(0, 'SỐ LIỆU GIẢ LẬP — chỉ để minh họa giao diện, tuyệt đối không dùng '
                           'cho báo cáo hay kết luận. Chỉ số thật chưa tính xong.')
    return {'province_code': code, 'province_name': found['province_name'], 'slug': found['slug'],
            'gia_lap': fake,
            'nam_tu': year_from, 'nam_den': year_to,
            'dem': night, 'ngay': day, 'economy': economy,
            'thieu_du_lieu': {'dem': not night, 'ngay': not day, 'economy': not economy},
            'canh_bao': warnings}


COG_FIELDS = 'year,month,path,source,size_bytes,west,south,east,north'


def cog_years(kind='NTL', buoc='nam'):
    """Danh sách ảnh nền. buoc='nam' lấy ảnh tổng hợp năm (thang=0), 'thang' lấy ảnh tháng."""
    dieu_kien = 'month=0' if buoc == 'nam' else 'month BETWEEN 1 AND 12'
    with connect() as connection:
        rows = connection.execute(
            f'SELECT {COG_FIELDS} FROM cog_image WHERE kind=? AND {dieu_kien} '
            f'ORDER BY year,month', (kind,)).fetchall()
    return [dict(row) for row in rows]


def cog_path(kind, year, month=0):
    with connect() as connection:
        row = connection.execute(
            'SELECT path FROM cog_image WHERE kind=? AND year=? AND month=?',
            (kind, year, month)).fetchone()
    return row['path'] if row else None


def cac_buoc_thoi_gian(kind='NTL'):
    """Những bước thời gian thật sự có ảnh, để giao diện chỉ hiện lựa chọn dùng được."""
    with connect() as connection:
        nam = connection.execute(
            'SELECT COUNT(*) FROM cog_image WHERE kind=? AND month=0', (kind,)).fetchone()[0]
        thang = connection.execute(
            'SELECT COUNT(*) FROM cog_image WHERE kind=? AND month BETWEEN 1 AND 12',
            (kind,)).fetchone()[0]
    return {'nam': nam, 'thang': thang}


def originals():
    with connect() as connection:
        rows = connection.execute(
            'SELECT kind,year,path,size_bytes,note FROM source_image ORDER BY kind,year').fetchall()
    return [dict(row) for row in rows]


def coverage():
    """Số liệu cho trang trạng thái: năm nào đã có gì. Dùng để báo cáo tiến độ."""
    with connect() as connection:
        out = {}
        for key, table in (('dem', 'ntl_annual'), ('ngay', 'day_annual'), ('economy', 'economy')):
            rows = connection.execute(
                f'SELECT year,COUNT(*) AS so_tinh FROM {table} GROUP BY year ORDER BY year').fetchall()
            out[key] = [dict(row) for row in rows]
        out['cog_image'] = [dict(row) for row in connection.execute(
            'SELECT kind,year,size_bytes FROM cog_image ORDER BY kind,year').fetchall()]
    return out


# --- Bảng chỉ số kiểu World Development Indicators -------------------------------------
# Mỗi chỉ số: mã, tên hiển thị, đơn vị, bảng nguồn, số chữ số thập phân khi hiển thị.
# Thêm chỉ số mới ở đây là nó tự xuất hiện trong giao diện và trong file tải về.
INDICATORS = (
    dict(ma='sol', ten='Tổng độ sáng ban đêm (SOL)', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=2,
         mo_ta='Tổng bức xạ ban đêm trong ranh giới tỉnh.', bang_thang='ntl_monthly'),
    dict(ma='sol_density', ten='Mật độ sáng ban đêm', don_vi='nW/cm²/sr trên km²',
         bang='ntl_annual', chu_so=4,
         mo_ta='Tổng độ sáng chia cho diện tích tỉnh.', bang_thang='ntl_monthly'),
    dict(ma='sol_change_pct', ten='Biến động độ sáng so với năm trước', don_vi='%',
         bang='ntl_annual', chu_so=2,
         mo_ta='Chỉ so trong cùng một nguồn; bỏ trống tại mốc DMSP→VIIRS năm 2013.'),
    dict(ma='sol_cal', ten='Tổng độ sáng (đã hiệu chỉnh DMSP→VIIRS)', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=2,
         mo_ta='Chuỗi thống nhất 2004–2025: DMSP quy về thang VIIRS bằng hàm lũy thừa '
               'khớp trên năm chồng lấn 2013. Dùng cột này khi so sánh xuyên mốc 2013.'),
    dict(ma='sol_density_cal', ten='Mật độ sáng (đã hiệu chỉnh)', don_vi='nW/cm²/sr trên km²',
         bang='ntl_annual', chu_so=4, mo_ta='sol_cal chia diện tích tỉnh.'),
    dict(ma='sol_change_cal_pct', ten='Biến động (đã hiệu chỉnh)', don_vi='%',
         bang='ntl_annual', chu_so=2,
         mo_ta='Tính trên chuỗi đã hiệu chỉnh nên có giá trị cả ở mốc 2013→2014.'),
    dict(ma='sol_raw', ten='Tổng độ sáng trước khi trừ nền', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=2,
         mo_ta='Để đo bước lọc nền lấy đi bao nhiêu; không dùng cho phân tích.', bang_thang='ntl_monthly'),
    dict(ma='rad_mean', ten='Độ sáng trung bình mỗi điểm ảnh', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=4, mo_ta='Giá trị trung bình trên mọi điểm ảnh hợp lệ.', bang_thang='ntl_monthly'),
    dict(ma='rad_max', ten='Điểm sáng nhất tỉnh', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=2, mo_ta='Giá trị lớn nhất trong ranh giới tỉnh.', bang_thang='ntl_monthly'),
    dict(ma='rad_std', ten='Độ lệch chuẩn bức xạ', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=4, mo_ta='Mức phân tán độ sáng giữa các điểm ảnh.', bang_thang='ntl_monthly'),
    dict(ma='rad_cv', ten='Hệ số biến thiên ánh sáng', don_vi='không thứ nguyên',
         bang='ntl_annual', chu_so=4,
         mo_ta='std/mean — chênh lệch sáng–tối trong tỉnh; cao nghĩa là tập trung vào vài điểm.', bang_thang='ntl_monthly'),
    dict(ma='lit_pixels', ten='Số điểm ảnh sáng', don_vi='điểm ảnh',
         bang='ntl_annual', chu_so=0,
         mo_ta='Vượt ngưỡng sáng: VIIRS ≥ 1,5 nW/cm²/sr, DMSP ≥ DN 5. Hai thang đo khác nhau.', bang_thang='ntl_monthly'),
    dict(ma='lit_area_km2', ten='Diện tích được chiếu sáng', don_vi='km²',
         bang='ntl_annual', chu_so=2, mo_ta='Tổng diện tích các điểm ảnh vượt ngưỡng sáng.', bang_thang='ntl_monthly'),
    dict(ma='lit_area_pct', ten='Tỷ lệ diện tích được chiếu sáng', don_vi='%',
         bang='ntl_annual', chu_so=2,
         mo_ta='lit_area_km2 chia diện tích tỉnh — thay cho "tỷ lệ thắp sáng" của luồng cũ.', bang_thang='ntl_monthly'),
    dict(ma='lit_sol', ten='Độ sáng của vùng sáng', don_vi='nW/cm²/sr',
         bang='ntl_annual', chu_so=2,
         mo_ta='Tổng bức xạ chỉ trên vùng vượt ngưỡng; loại nhiễu nền của vùng tối.', bang_thang='ntl_monthly'),
    dict(ma='valid_pixels', ten='Số điểm ảnh có dữ liệu', don_vi='điểm ảnh',
         bang='ntl_annual', chu_so=0,
         mo_ta='Dùng để kiểm tra độ phủ; DMSP 1 km nên ít điểm hơn VIIRS 500 m rất nhiều.', bang_thang='ntl_monthly'),
    dict(ma='area_km2', ten='Diện tích tự nhiên', don_vi='km²',
         bang='ntl_annual', chu_so=1, mo_ta='Diện tích trong ranh giới GADM 4.1.', bang_thang='ntl_monthly'),
    # Năm chỉ số dưới đây CHỈ có theo tháng: DMSP là ảnh tổng hợp năm nên không có.
    dict(ma='sol_ma3', ten='Tổng độ sáng, trung bình trượt 3 tháng', don_vi='nW/cm²/sr',
         bang='ntl_monthly', bang_thang='ntl_monthly', chu_so=2,
         mo_ta='Làm mượt dao động mùa. Dùng cái này khi vẽ chuỗi tháng; số thô là răng cưa do mây.'),
    dict(ma='sol_change_mom_pct', ten='Biến động so với tháng liền trước', don_vi='%',
         bang='ntl_monthly', bang_thang='ntl_monthly', chu_so=2,
         mo_ta='Trống nếu tháng liền trước thiếu ảnh — không so vượt qua lỗ hổng.'),
    dict(ma='sol_change_yoy_pct', ten='Biến động so với cùng tháng năm trước', don_vi='%',
         bang='ntl_monthly', bang_thang='ntl_monthly', chu_so=2,
         mo_ta='Triệt tiêu mùa vụ nên đọc xu thế tốt hơn biến động theo tháng liền trước.'),
    dict(ma='lit_pixel_pct', ten='Tỷ lệ điểm ảnh sáng', don_vi='%',
         bang='ntl_annual', bang_thang='ntl_monthly', chu_so=2,
         mo_ta='lit_pixels chia valid_pixels. Khác lit_area_pct vốn chia diện tích tỉnh.'),
    dict(ma='cloud_free_obs', ten='Số lượt quan sát sạch mây', don_vi='lượt',
         bang='ntl_annual', bang_thang='ntl_monthly', chu_so=2,
         mo_ta='Trường chất lượng. Dưới 2 lượt thì con số của tháng đó kém tin cậy.'),
    dict(ma='NDVI_mean', ten='NDVI trung bình', don_vi='chỉ số -1…1',
         bang='day_annual', chu_so=4, mo_ta='Chỉ số thực vật.'),
    dict(ma='NDBI_mean', ten='NDBI trung bình', don_vi='chỉ số −1…1',
         bang='day_annual', chu_so=4, mo_ta='Chỉ số xây dựng.'),
    dict(ma='MNDWI_mean', ten='MNDWI trung bình', don_vi='chỉ số −1…1',
         bang='day_annual', chu_so=4, mo_ta='Chỉ số mặt nước.'),
    dict(ma='BSI_mean', ten='BSI trung bình', don_vi='chỉ số −1…1',
         bang='day_annual', chu_so=4, mo_ta='Chỉ số đất trống.'),
    dict(ma='population', ten='Dân số', don_vi='người', bang='economy', chu_so=0,
         mo_ta='Do giảng viên cung cấp.'),
    dict(ma='gdp', ten='GDP', don_vi='tỷ đồng', bang='economy', chu_so=0,
         mo_ta='Do giảng viên cung cấp.'),
)
BY_CODE = {entry['ma']: entry for entry in INDICATORS}


def indicators():
    """Danh mục chỉ số, kèm số tỉnh và khoảng năm thực sự có dữ liệu của từng chỉ số."""
    out = []
    with connect() as connection:
        for entry in INDICATORS:
            row = connection.execute(
                f'SELECT COUNT(DISTINCT province_code),MIN(year),MAX(year) '
                f'FROM {entry["bang"]} WHERE "{entry["ma"]}" IS NOT NULL').fetchone()
            out.append(dict(entry, so_tinh=row[0] or 0, nam_tu=row[1], nam_den=row[2]))
    return out


def doc_moc(text):
    """'2010' -> ('nam', 2010, 0); '2024-07' -> ('thang', 2024, 7). Sai định dạng -> None.

    Không bao giờ ghép chuỗi người dùng gửi vào câu SQL: mốc chỉ đi vào tham số truy vấn
    sau khi đã qua int().
    """
    text = str(text or '').strip()
    if re.fullmatch(r'\d{4}', text):
        return ('nam', int(text), 0)
    khop = re.fullmatch(r'(\d{4})-(\d{2})', text)
    if khop and 1 <= int(khop.group(2)) <= 12:
        return ('thang', int(khop.group(1)), int(khop.group(2)))
    return None


def ten_moc(loai, year, month):
    return f'{year}-{month:02}' if loai == 'thang' else str(year)


# Công thức thuộc derive.py, API chỉ gọi. Hàm thời gian tính trên khoảng người dùng chọn
# nên không tiền tính được, nhưng nguyên tắc là "không viết công thức trong API", không
# phải "không tính lúc có yêu cầu".
from task_pipeline.derive import HAM_THOI_GIAN, ham_thoi_gian, nam_thap_phan

# Cột đã quy về cùng một thang đo thì đi qua mốc 2013 được; cột gốc thì không.
COT_DA_HIEU_CHINH = {'sol_cal', 'sol_density_cal', 'sol_change_cal_pct'}
MOC_CAN = {2010: 'mốc đổi vệ tinh DMSP F16→F18 năm 2010 chưa hiệu chỉnh',
           2014: 'mốc đổi vệ tinh DMSP→VIIRS năm 2013/2014'}


def _bac_qua_moc(nhan_moc, ma_chi_so):
    """Khoảng có bắc qua mốc đổi vệ tinh nào mà cột này không xử lý được không?"""
    nam = sorted({int(str(m)[:4]) for m in nhan_moc})
    if not nam:
        return []
    ra = []
    for moc, ly_do in MOC_CAN.items():
        if moc == 2014 and ma_chi_so in COT_DA_HIEU_CHINH:
            continue
        if nam[0] < moc <= nam[-1]:
            ra.append(ly_do)
    return ra


def panel(codes, moc=None, tinh=None, year_from=2004, year_to=2025, ham=None):
    """Bảng rộng kiểu WDI: mỗi dòng một (tỉnh × chỉ số), mỗi cột một mốc thời gian.

    codes: danh sách mã chỉ số. Mã lạ -> None, không bao giờ ghép vào câu SQL.
    moc:   danh sách '2010' (năm) hoặc '2024-07' (tháng), trộn được. Bỏ trống thì
           lấy mọi năm trong [year_from, year_to].
    tinh:  danh sách mã tỉnh; bỏ trống thì lấy cả 63.
    """
    muc = [BY_CODE.get(c.strip()) for c in codes if str(c).strip()]
    if not muc or any(m is None for m in muc):
        return None
    if moc:
        doc = [doc_moc(x) for x in moc]
        if any(d is None for d in doc):
            return None
        cac_moc = sorted(set(doc), key=lambda d: (d[1], d[2]))
    else:
        cac_moc = [('nam', y, 0) for y in range(year_from, year_to + 1)]
    co_thang = any(d[0] == 'thang' for d in cac_moc)
    nam_nam = [d[1] for d in cac_moc if d[0] == 'nam']
    muon = [c.strip().zfill(2) for c in tinh if str(c).strip()] if tinh else None

    with connect() as connection:
        tinh_rows = connection.execute(
            'SELECT province_code,province_name,number FROM province ORDER BY number').fetchall()
        o = {}          # (mã chỉ số, mã tỉnh, tên mốc) -> giá trị
        co = {}         # cùng khoá -> cờ CL_OBS_STATUS, chỉ khi khác 'A'
        nguon = {}
        for entry in muc:
            for loai, year, month in cac_moc:
                # Chỉ số không có bảng theo tháng thì ô để trống, không nổ.
                bang = entry.get('bang_thang') if loai == 'thang' else entry.get('bang')
                if not bang:
                    continue
                co_co = bang in ('ntl_annual', 'ntl_monthly')
                cot_co = ',obs_status' if co_co else ",''"
                if loai == 'thang':
                    cau = (f'SELECT province_code,"{entry["ma"]}",source{cot_co} FROM {bang} '
                           f'WHERE year=? AND month=?')
                    tham = (year, month)
                else:
                    cau = (f'SELECT province_code,"{entry["ma"]}",source{cot_co} FROM {bang} '
                           f'WHERE year=?' + ('' if bang != 'ntl_monthly' else ' AND month=0'))
                    tham = (year,)
                for ma_tinh, gia_tri, src, flag in connection.execute(cau, tham):
                    khoa = (entry['ma'], ma_tinh, ten_moc(loai, year, month))
                    o[khoa] = gia_tri
                    # 'A' là bình thường: không gửi về để khỏi nặng tải và nặng mắt.
                    if flag and flag != 'A':
                        co[khoa] = flag
                    if src:
                        nguon.setdefault(ma_tinh, set()).add(src)

    nhan_moc = [ten_moc(*d) for d in cac_moc]
    dong = []
    for tinh_row in tinh_rows:
        ma_tinh = tinh_row['province_code']
        if muon is not None and ma_tinh not in muon:
            continue
        for entry in muc:
            dong.append({
                'province_code': ma_tinh, 'province_name': tinh_row['province_name'],
                'chi_so': entry['ma'], 'ten': entry['ten'], 'don_vi': entry['don_vi'],
                'chu_so': entry['chu_so'],
                'source': '/'.join(sorted(nguon.get(ma_tinh, ()))) or None,
                'gia_tri': [o.get((entry['ma'], ma_tinh, m)) for m in nhan_moc],
                'co': [co.get((entry['ma'], ma_tinh, m)) for m in nhan_moc]})
    # Hàm thời gian: mỗi hàm một cột phụ bên phải bảng.
    cac_ham = []
    for ten in (ham or []):
        ten = str(ten).strip()
        if ten and ten in HAM_THOI_GIAN:
            cac_ham.append(ten)
    if cac_ham:
        for d in dong:
            # Tốc độ tăng trưởng qua mốc đổi vệ tinh là con số vô nghĩa: từ chối chạy
            # thay vì trả về một số trông như thật.
            can = _bac_qua_moc(nhan_moc, d['chi_so'])
            d['ham'] = {}
            for ten in cac_ham:
                d['ham'][ten] = (None if (can and ten in ('cagr', 'thay_doi'))
                                 else ham_thoi_gian(ten, nhan_moc, d['gia_tri']))
            d['ham_tu_choi'] = can if can else None
    co_so = {d['province_code'] for d in dong if any(v is not None for v in d['gia_tri'])}
    return {'chi_so': [dict(e) for e in muc], 'moc': nhan_moc, 'dong': dong,
            'ham': [{'ma': t, 'ten': HAM_THOI_GIAN[t]} for t in cac_ham],
            'co_thang': co_thang, 'chu_giai_co': CHU_GIAI_CO,
            'so_tinh_co_du_lieu': len(co_so),
            'canh_bao': _canh_bao_bang(muc, nam_nam, cac_moc)}


def kinh_te_dem(year_from=2014, year_to=2025):
    """Bảng kinh tế đêm + hệ số co giãn β. Bảng economy rỗng thì trả mảng rỗng, không lỗi.

    Mặc định 2014–2025: giai đoạn VIIRS, một cảm biến, không mốc nối nào. Mở rộng về
    trước là vướng mốc 2010 chưa hiệu chỉnh.
    """
    from task_pipeline.derive import do_co_gian
    with connect() as connection:
        rows = connection.execute(
            'SELECT e.province_code, p.province_name, e.year, e.population,'
            ' COALESCE(e.grdp, e.gdp) AS grdp, e.grdp_price_basis, e.source, n.sol '
            'FROM economy e JOIN province p ON p.province_code = e.province_code '
            'LEFT JOIN ntl_annual n ON n.province_code = e.province_code AND n.year = e.year '
            'WHERE e.year BETWEEN ? AND ? ORDER BY p.number, e.year',
            (year_from, year_to)).fetchall()
    dong = [dict(r) for r in rows]
    if not dong:
        return {'dong': [], 'hoi_quy': None, 'nam_tu': year_from, 'nam_den': year_to,
                'canh_bao': ['Chưa có số liệu kinh tế. Nạp dân số và GRDP vào bảng '
                             'economy rồi chạy lại build_indices.']}
    # Số giả lập phải tự khai ở mọi nơi nó xuất hiện. Dò nhãn ngay trên cột source
    # thay vì tin vào trí nhớ người nạp: bảng này sẽ đi thẳng vào báo cáo của cô.
    gia_lap = sorted({r['source'] for r in dong
                      if 'GIA_LAP' in str(r.get('source') or '').upper()})
    co_so = {r.get('grdp_price_basis') for r in dong} - {None, ''}
    gia_so_sanh = (True if co_so == {'so_sanh'} else
                   False if co_so == {'hien_hanh'} else None)
    hoi_quy = do_co_gian(dong, gia_so_sanh)
    for r in dong:
        r['sol_per_capita'] = (r['sol'] / r['population']
                               if r.get('sol') and r.get('population') else None)
        mot = hoi_quy['theo_tinh'].get(r['province_code'])
        r['beta_tinh'] = mot['beta'] if mot else None
    canh_bao = list(hoi_quy.get('canh_bao', []))
    if gia_lap:
        canh_bao.insert(0, 'SỐ LIỆU KINH TẾ LÀ GIẢ LẬP, KHÔNG PHẢI SỐ THẬT — chỉ để '
                           'chạy thử giao diện. Hệ số beta dưới đây là con số đã cấy '
                           f"vào lúc sinh dữ liệu ({'; '.join(gia_lap)}), không phải kết "
                           'quả nghiên cứu. Thay bằng dân số và GRDP thật trước khi '
                           'trích vào báo cáo.')
    return {'dong': dong, 'hoi_quy': hoi_quy, 'nam_tu': year_from, 'nam_den': year_to,
            'gia_lap': gia_lap, 'canh_bao': canh_bao}


def tong_hop(year, month=0):
    """Tổng cả nước của một mốc: SOL, diện tích, mật độ.

    Chỉ SUM() trên chỉ số đã tính sẵn, không phải công thức mới — nguyên tắc "không tính
    chỉ số trong API" vẫn giữ. Mật độ là tổng SOL chia tổng diện tích, không phải trung
    bình các mật độ tỉnh: trung bình mật độ sẽ cho tỉnh nhỏ cùng trọng số với tỉnh lớn.
    """
    bang = 'ntl_monthly' if month else 'ntl_annual'
    dieu_kien = 'year=? AND month=?' if month else 'year=?'
    tham = (year, month) if month else (year,)
    with connect() as connection:
        row = connection.execute(
            f'SELECT SUM(sol),SUM(area_km2),COUNT(*),GROUP_CONCAT(DISTINCT source) '
            f'FROM {bang} WHERE {dieu_kien} AND sol IS NOT NULL', tham).fetchone()
    sol, dien_tich, so_tinh, nguon = row
    if not so_tinh:
        return None
    return {'sol': sol, 'area_km2': dien_tich,
            'sol_density': (sol / dien_tich) if sol is not None and dien_tich else None,
            'so_tinh': so_tinh, 'source': nguon,
            'year': year, 'month': month}


def _canh_bao_bang(muc, years, cac_moc):
    """Cảnh báo cho một bảng nhiều chỉ số: gộp cảnh báo của từng chỉ số, không lặp."""
    ra = []
    for entry in muc:
        for c in _panel_warnings(entry, years or [d[1] for d in cac_moc]):
            if c not in ra:
                ra.append(c)
    return ra


def _panel_warnings(entry, years):
    warnings = []
    if entry['bang'] == 'ntl_annual' and min(years) <= 2009 and max(years) >= 2010:
        warnings.append(MOC_2010)
    if entry['bang'] == 'ntl_annual' and min(years) <= 2013 <= max(years):
        warnings.append('Chuỗi bắc qua mốc đổi vệ tinh: DMSP-OLS đến 2013, VIIRS từ 2014. '
                        'Chưa hiệu chỉnh liên vệ tinh — không so sánh trực tiếp hai giai đoạn.')
    if entry['bang'] == 'day_annual' and any(y in TOA_YEARS for y in years):
        warnings.append(TOA_WARNING)
    if entry['bang'] == 'economy':
        warnings.append('Số liệu kinh tế do giảng viên cung cấp, không trích xuất từ ảnh vệ tinh.')
    return warnings


def choropleth(code, year):
    """Một chỉ số, một năm, mọi tỉnh — để tô màu bản đồ toàn quốc."""
    entry = BY_CODE.get(code)
    if entry is None:
        return None
    with connect() as connection:
        rows = connection.execute(
            f'SELECT province_code,"{entry["ma"]}" FROM {entry["bang"]} '
            f'WHERE year=? AND "{entry["ma"]}" IS NOT NULL', (year,)).fetchall()
    values = {row[0]: row[1] for row in rows}
    numbers = sorted(v for v in values.values() if v is not None)
    return {'chi_so': dict(entry), 'nam': year, 'gia_tri': values,
            'nho_nhat': numbers[0] if numbers else None,
            'lon_nhat': numbers[-1] if numbers else None,
            'trung_vi': numbers[len(numbers) // 2] if numbers else None}
