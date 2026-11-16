"""VNGISDash API — lớp đọc trên data_processed và các COG.

Chạy thử:
    python3 -m app.data.build_indices --root /data/SatelliteData
    uvicorn app.api.main:app --reload       # rồi mở http://localhost:8000

TiTiler được nạp nếu có cài; không có thì API vẫn chạy, chỉ thiếu ô bản đồ.
"""
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import export, store

WEB = Path(__file__).resolve().parent.parent / 'web'
# Khuôn đường dẫn ô bản đồ của TiTiler. Giao diện nối thẳng ?url=<đường dẫn COG> vào sau.
TILE_URL = '/tiles/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url='
YEAR_MIN, YEAR_MAX = 2004, 2025

app = FastAPI(title='VNGISDash API',
              description='Chỉ số kinh tế – xã hội cấp tỉnh từ ảnh vệ tinh, Việt Nam 2004–2025',
              version='0.1.0')


def _code(province_code: str) -> str:
    code = province_code.strip().zfill(2)
    if not code.isdigit():
        raise HTTPException(400, 'province_code phải là mã số, ví dụ 01 hoặc 27')
    return code


GIAO_DIEN = ('index.html', 'style.css', 'app.js')


def _bam(du_lieu):
    import hashlib
    # Chuẩn hoá xuống dòng: git trên Windows đổi LF thành CRLF khi lấy mã về, nên cùng một
    # nội dung lại ra mã băm khác máy Linux. Không chuẩn hoá thì phép so này vô dụng.
    return hashlib.sha256(du_lieu.replace(b'\r\n', b'\n')).hexdigest()


def van_tay_tung_tep():
    out = {}
    for ten in GIAO_DIEN:
        path = WEB / ten
        out[ten] = _bam(path.read_bytes())[:12] if path.is_file() else None
    return out


def dau_van_giao_dien():
    """Vân tay của bộ tệp giao diện đang nằm trên đĩa.

    Khi màn hình trông không giống bản vừa sửa, câu hỏi đầu tiên là máy chủ đang phục vụ
    tệp nào. So vân tay này với vân tay của repo là biết ngay, khỏi đoán bộ nhớ đệm.
    """
    noi = b''.join((WEB / ten).read_bytes() if (WEB / ten).is_file() else b''
                   for ten in GIAO_DIEN)
    return _bam(noi)[:12]


@app.get('/api/health')
def health():
    try:
        count = len(store.provinces())
    except FileNotFoundError as error:
        return JSONResponse({'ok': False, 'ly_do': str(error)}, status_code=503)
    return {'ok': True, 'so_tinh': count, 'db': str(store.database_path()),
            'thu_muc_giao_dien': str(WEB), 'dau_van_giao_dien': dau_van_giao_dien(),
            'van_tay_tung_tep': van_tay_tung_tep()}


@app.get('/api/provinces')
def list_provinces():
    """63 tỉnh trước sáp nhập, kèm số năm đã có dữ liệu để giao diện biết tỉnh nào còn trống."""
    return {'tinh': store.provinces()}


@app.get('/api/indices')
def get_indices(province_code: str = Query(..., description='Mã tỉnh, ví dụ 01'),
                nam_tu: int = Query(YEAR_MIN, ge=1990, le=2100),
                nam_den: int = Query(YEAR_MAX, ge=1990, le=2100)):
    if nam_tu > nam_den:
        raise HTTPException(400, 'nam_tu phải nhỏ hơn hoặc bằng nam_den')
    data = store.indices(_code(province_code), nam_tu, nam_den)
    if data is None:
        raise HTTPException(404, f'Không có tỉnh với mã {province_code}')
    return data


@app.get('/api/indicators')
def list_indicators():
    """Danh mục chỉ số cho tab dữ liệu, kèm độ phủ thực tế của từng chỉ số."""
    return {'chi_so': store.indicators()}


@app.get('/api/panel')
def get_panel(chi_so: str = Query('sol', description='Một hoặc nhiều mã, ngăn bằng dấu phẩy'),
              moc: str = Query('', description="Mốc đã chọn: '2010' hoặc '2024-07', "
                                               'ngăn bằng dấu phẩy. Trống thì lấy cả khoảng năm'),
              nam_tu: int = Query(YEAR_MIN, ge=1990, le=2100),
              nam_den: int = Query(YEAR_MAX, ge=1990, le=2100),
              province_code: str = Query('', description='Mã tỉnh ngăn bằng dấu phẩy; '
                                                         'để trống là tất cả'),
              ham: str = Query('', description='Hàm thời gian, ngăn bằng dấu phẩy: '
                                               'tong, trung_binh, thay_doi, cagr')):
    """Bảng rộng: mỗi dòng một tỉnh × chỉ số, mỗi cột một mốc thời gian."""
    if nam_tu > nam_den:
        raise HTTPException(400, 'nam_tu phải nhỏ hơn hoặc bằng nam_den')
    data = store.panel(chi_so.split(','), moc.split(',') if moc else None,
                       province_code.split(',') if province_code else None, nam_tu, nam_den,
                       ham.split(',') if ham else None)
    if data is None:
        raise HTTPException(400, f'Mã chỉ số hoặc mốc không hợp lệ: chi_so={chi_so} moc={moc}. '
                                 'Xem /api/indicators')
    return data


@app.get('/api/panel.csv')
def panel_csv(chi_so: str = Query('sol'),
              moc: str = Query(''),
              nam_tu: int = Query(YEAR_MIN, ge=1990, le=2100),
              nam_den: int = Query(YEAR_MAX, ge=1990, le=2100),
              province_code: str = Query(''),
              ham: str = Query(''),
              dang: str = Query('rong', description="'rong' một dòng một tỉnh-chỉ số, "
                                                    "'dai' một dòng một tỉnh-chỉ số-mốc")):
    if nam_tu > nam_den:
        raise HTTPException(400, 'nam_tu phải nhỏ hơn hoặc bằng nam_den')
    if dang not in ('rong', 'dai'):
        raise HTTPException(400, "dang phải là 'rong' hoặc 'dai'")
    data = store.panel(chi_so.split(','), moc.split(',') if moc else None,
                       province_code.split(',') if province_code else None, nam_tu, nam_den,
                       ham.split(',') if ham else None)
    if data is None:
        raise HTTPException(400, f'Mã chỉ số hoặc mốc không hợp lệ: chi_so={chi_so} moc={moc}')
    payload = export.panel_csv(data, dang)
    # Tên tệp chỉ dùng ASCII: tên có dấu làm hỏng header HTTP.
    goi = chi_so.replace(',', '-')[:40]
    name = f"vngisdash_{goi}_{nam_tu}_{nam_den}_{dang}.csv"
    return StreamingResponse(
        io.BytesIO(payload), media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{name}"',
                 'Content-Length': str(len(payload))})


@app.get('/api/choropleth')
def get_choropleth(chi_so: str = Query('sol'),
                   nam: int = Query(YEAR_MAX, ge=1990, le=2100)):
    """Một chỉ số, một năm, mọi tỉnh — để tô màu bản đồ toàn quốc."""
    data = store.choropleth(chi_so, nam)
    if data is None:
        raise HTTPException(404, f'Không có chỉ số nào mã {chi_so}')
    return data


@app.get('/api/tong-hop')
def get_tong_hop(nam: int = Query(..., ge=1990, le=2100),
                 thang: int = Query(0, ge=0, le=12)):
    """Tổng cả nước của một mốc — ba số của màn Ảnh đêm khi đang xem toàn quốc."""
    data = store.tong_hop(nam, thang)
    if data is None:
        moc = f'{nam}-{thang:02}' if thang else str(nam)
        raise HTTPException(404, f'Chưa có chỉ số của mốc {moc}.')
    return data


@app.get('/api/kinh-te-dem')
def get_kinh_te_dem(nam_tu: int = Query(2014, ge=1990, le=2100),
                    nam_den: int = Query(YEAR_MAX, ge=1990, le=2100)):
    """Bảng kinh tế đêm và hệ số co giãn β. Chưa có số liệu thì trả mảng rỗng, không lỗi."""
    if nam_tu > nam_den:
        raise HTTPException(400, 'nam_tu phải nhỏ hơn hoặc bằng nam_den')
    return store.kinh_te_dem(nam_tu, nam_den)


@app.get('/api/coverage')
def get_coverage():
    """Năm nào đã có dữ liệu gì — dùng cho trang trạng thái và báo cáo tiến độ."""
    return store.coverage()


@app.get('/api/basemap')
def basemap(buoc: str = Query('nam', description="'nam' hoặc 'thang'")):
    """Danh sách mốc thời gian có ảnh nền đêm, cho thanh trượt trên bản đồ."""
    if buoc not in ('nam', 'thang'):
        raise HTTPException(400, "buoc phải là 'nam' hoặc 'thang'")
    muc = store.cog_years('NTL', buoc)
    # TiTiler 0.19 có {tileMatrixSetId} trong đường dẫn; thiếu đoạn này là 404 mọi ô bản đồ.
    return {'buoc': buoc,
            'co_san': store.cac_buoc_thoi_gian('NTL'),
            'nam': sorted({m['year'] for m in muc}),
            'chi_tiet': muc,
            'tiles': TILE_URL if _titiler_ready() else None,
            'ghi_chu_thang': 'Ảnh theo tháng chỉ có từ 2014: DMSP (2004–2013) là sản phẩm '
                             'tổng hợp năm, NOAA không phát hành theo tháng.'}


@app.get('/api/boundaries-info')
def thong_tin_ranh_gioi():
    """Thống kê file ranh giới đang dùng: bao nhiêu tỉnh, mã nào, hình phức tạp cỡ nào.

    Mặt nạ che vùng ngoài ranh giới được dựng từ chính các vòng của file này. Khi nó không
    che đúng, hai nguyên nhân có thể: mã tỉnh không khớp với danh mục, hoặc hình quá nhiều
    đỉnh khiến trình duyệt dựng hỏng. Đầu mối này trả lời cả hai mà không phải đoán.
    """
    path = Path(os.environ.get(
        'VNGIS_BOUNDARIES', Path(__file__).resolve().parent.parent / 'data' / 'provinces.geojson'))
    if not path.exists():
        raise HTTPException(404, f'Chưa có {path}')
    fc = json.loads(path.read_text(encoding='utf-8'))
    ma_danh_muc = {t['province_code'] for t in store.provinces()}
    ket_qua, tong_dinh = [], 0
    for feature in fc.get('features', []):
        hinh = feature.get('geometry') or {}
        toa_do = hinh.get('coordinates') or []
        vong = toa_do if hinh.get('type') == 'Polygon' else [r for p in toa_do for r in p]
        dinh = sum(len(r) for r in vong)
        tong_dinh += dinh
        ket_qua.append({'province_code': feature.get('properties', {}).get('province_code'),
                        'loai_hinh': hinh.get('type'), 'so_vong': len(vong), 'so_dinh': dinh})
    ma_file = {str(r['province_code']) for r in ket_qua}
    nang = sorted(ket_qua, key=lambda r: -r['so_dinh'])[:5]
    return {'path': str(path), 'so_tinh': len(ket_qua), 'tong_dinh': tong_dinh,
            'phuc_tap_nhat': nang,
            'ma_khong_khop_danh_muc': sorted(ma_file - ma_danh_muc)[:10],
            'ma_danh_muc_thieu_trong_file': sorted(ma_danh_muc - ma_file)[:10]}


def _duong_ranh_gioi():
    return Path(os.environ.get(
        'VNGIS_BOUNDARIES', Path(__file__).resolve().parent.parent / 'data' / 'provinces.geojson'))


def _hinh_tinh(province_code):
    """Polygon của một tỉnh, lấy từ tệp ranh giới đã dựng sẵn."""
    path = _duong_ranh_gioi()
    if not path.is_file():
        return None
    for f in json.loads(path.read_text(encoding='utf-8'))['features']:
        if str(f['properties'].get('province_code', '')).zfill(2) == province_code:
            return f
    return None


def _cat_theo_tinh(nguon, hinh):
    """Cắt COG toàn quốc theo ranh giới tỉnh, trả về bytes GeoTIFF.

    Ngoài ranh giới thành NoData chứ không thành 0: 0 là một giá trị bức xạ hợp lệ,
    dùng nó cho vùng không thuộc tỉnh là bịa ra số liệu.
    """
    import rasterio
    from rasterio.mask import mask as cat_mask
    with rasterio.open(nguon) as ds:
        anh, bien_doi = cat_mask(ds, [hinh['geometry']], crop=True,
                                 nodata=ds.nodata if ds.nodata is not None else -9999)
        ho_so = ds.profile | {'height': anh.shape[1], 'width': anh.shape[2],
                              'transform': bien_doi, 'driver': 'GTiff',
                              'nodata': ds.nodata if ds.nodata is not None else -9999}
    bo_nho = rasterio.io.MemoryFile()
    with bo_nho.open(**ho_so) as ra:
        ra.write(anh)
    return bo_nho.read()


@app.get('/api/anh-dem.tif')
def tai_anh_dem(nam: int = Query(..., ge=1990, le=2100),
                thang: int = Query(0, ge=0, le=12, description='0 = ảnh cả năm'),
                province_code: str = Query('', description='Bỏ trống = ảnh toàn quốc')):
    """Tải ảnh đêm (COG) của một mốc thời gian, cả nước hoặc cắt theo một tỉnh."""
    path = store.cog_path('NTL', nam, thang)
    moc = f'{nam}-{thang:02}' if thang else str(nam)
    if not path:
        lenh = ('python -m app.data.build_monthly_cogs' if thang
                else 'python -m app.data.build_cogs --kinds VIIRS DMSP')
        raise HTTPException(404, f'Chưa có ảnh đêm {moc}. Chạy: {lenh}')
    path = Path(path)
    if not path.is_file():
        raise HTTPException(410, f'Sổ có ghi ảnh {moc} nhưng file không còn ở {path}.')
    if not province_code:
        return FileResponse(path, media_type='image/tiff', filename=f'VN_NTL_{moc}.tif')

    code = _code(province_code)
    tinh = store.province(code)
    if tinh is None:
        raise HTTPException(404, f'Không có tỉnh với mã {province_code}')
    hinh = _hinh_tinh(code)
    if hinh is None:
        raise HTTPException(404, 'Chưa có ranh giới tỉnh để cắt ảnh. Chạy: '
                                 'python3 -m app.data.build_boundaries --tai-gadm')
    try:
        payload = _cat_theo_tinh(path, hinh)
    except Exception as loi:                                        # noqa: BLE001
        raise HTTPException(500, f'Không cắt được ảnh {moc} theo tỉnh {code}: {loi}')
    # Tên tệp chỉ ASCII: tên có dấu làm hỏng header HTTP (lỗi latin-1 đã gặp một lần).
    ten = f"VN_NTL_{code}_{tinh['slug']}_{moc}.tif"
    return StreamingResponse(
        io.BytesIO(payload), media_type='image/tiff',
        headers={'Content-Disposition': f'attachment; filename="{ten}"',
                 'Content-Length': str(len(payload))})


@app.get('/api/originals')
def list_originals():
    """Ảnh gốc ở tầng lạnh (ổ E / NAS) — chỉ liệt kê, không phục vụ qua đám mây."""
    return {'source_image': store.originals(),
            'note': 'Ảnh gốc không lưu trên đám mây để tránh chi phí egress. '
                       'Liên hệ nhóm dữ liệu để lấy liên kết tải từ tầng lạnh.'}


@app.get('/api/export.zip')
def export_zip(province_code: str = Query(...),
               nam_tu: int = Query(YEAR_MIN, ge=1990, le=2100),
               nam_den: int = Query(YEAR_MAX, ge=1990, le=2100),
               kem_anh: bool = Query(True, description='Kèm ảnh đêm GeoTIFF')):
    if nam_tu > nam_den:
        raise HTTPException(400, 'nam_tu phải nhỏ hơn hoặc bằng nam_den')
    built = export.build(_code(province_code), nam_tu, nam_den, kem_anh,
                         datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    if built is None:
        raise HTTPException(404, f'Không có tỉnh với mã {province_code}')
    name, payload = built
    return StreamingResponse(
        io.BytesIO(payload), media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{name}"',
                 'Content-Length': str(len(payload))})


@app.get('/api/boundaries.geojson')
def boundaries():
    path = Path(os.environ.get('VNGIS_BOUNDARIES',
                               Path(__file__).resolve().parent.parent / 'data' / 'provinces.geojson'))
    if not path.exists():
        raise HTTPException(404, 'Chưa có ranh giới. Chạy: python3 -m app.data.build_boundaries '
                                 '--config <config.json> (cần GADM 4.1 đã kiểm tra SHA-256)')
    return FileResponse(path, media_type='application/geo+json')


def _titiler_ready():
    try:
        import titiler.core  # noqa: F401
    except ImportError:
        return False
    return True


def _mount_tiles():
    """Ô bản đồ đọc trực tiếp COG; TiTiler tự giữ bộ đệm ở lớp HTTP phía trước."""
    if not _titiler_ready():
        return False
    from titiler.core.factory import TilerFactory
    tiler = TilerFactory()
    app.include_router(tiler.router, prefix='/tiles/cog', tags=['tiles'])
    return True


TILES_MOUNTED = _mount_tiles()

class KhongDemFile(StaticFiles):
    """Phục vụ tệp tĩnh kèm Cache-Control: no-cache.

    Đây là nguyên mẫu đang sửa liên tục. Trình duyệt giữ style.css cũ trong bộ nhớ đệm
    rồi ghép với index.html mới, ra một giao diện lai không giống bản nào — đã làm mất
    thời gian hai lần. no-cache không có nghĩa là không lưu: trình duyệt vẫn lưu nhưng
    phải hỏi lại máy chủ trước khi dùng, nên tệp không đổi vẫn trả 304, rất nhẹ.
    """

    def file_response(self, *args, **kwargs):
        phan_hoi = super().file_response(*args, **kwargs)
        phan_hoi.headers['Cache-Control'] = 'no-cache, must-revalidate'
        return phan_hoi


if WEB.is_dir():
    app.mount('/', KhongDemFile(directory=WEB, html=True), name='web')
