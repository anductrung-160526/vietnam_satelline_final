"""VNGISDash API — lớp đọc trên data_processed và các COG.

Chạy thử:
    python3 -m app.data.build_indices --root /data/SatelliteData
    uvicorn app.api.main:app --reload       # rồi mở http://localhost:8000

TiTiler được nạp nếu có cài; không có thì API vẫn chạy, chỉ thiếu ô bản đồ.
"""
import io
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


def _code(ma_tinh: str) -> str:
    code = ma_tinh.strip().zfill(2)
    if not code.isdigit():
        raise HTTPException(400, 'ma_tinh phải là mã số, ví dụ 01 hoặc 27')
    return code


def dau_van_giao_dien():
    """Vân tay của bộ tệp giao diện đang nằm trên đĩa.

    Khi màn hình trông không giống bản vừa sửa, câu hỏi đầu tiên là máy chủ đang phục vụ
    tệp nào. So vân tay này với vân tay của repo là biết ngay, khỏi đoán bộ nhớ đệm.
    """
    import hashlib
    bam = hashlib.sha256()
    for ten in ('index.html', 'style.css', 'app.js'):
        duong_dan = WEB / ten
        bam.update(duong_dan.read_bytes() if duong_dan.is_file() else b'')
    return bam.hexdigest()[:12]


@app.get('/api/health')
def health():
    try:
        count = len(store.provinces())
    except FileNotFoundError as error:
        return JSONResponse({'ok': False, 'ly_do': str(error)}, status_code=503)
    return {'ok': True, 'so_tinh': count, 'db': str(store.database_path()),
            'thu_muc_giao_dien': str(WEB), 'dau_van_giao_dien': dau_van_giao_dien()}


@app.get('/api/provinces')
def list_provinces():
    """63 tỉnh trước sáp nhập, kèm số năm đã có dữ liệu để giao diện biết tỉnh nào còn trống."""
    return {'tinh': store.provinces()}


@app.get('/api/indices')
def get_indices(ma_tinh: str = Query(..., description='Mã tỉnh, ví dụ 01'),
                nam_tu: int = Query(YEAR_MIN, ge=1990, le=2100),
                nam_den: int = Query(YEAR_MAX, ge=1990, le=2100)):
    if nam_tu > nam_den:
        raise HTTPException(400, 'nam_tu phải nhỏ hơn hoặc bằng nam_den')
    data = store.indices(_code(ma_tinh), nam_tu, nam_den)
    if data is None:
        raise HTTPException(404, f'Không có tỉnh với mã {ma_tinh}')
    return data


@app.get('/api/indicators')
def list_indicators():
    """Danh mục chỉ số cho tab dữ liệu, kèm độ phủ thực tế của từng chỉ số."""
    return {'chi_so': store.indicators()}


@app.get('/api/panel')
def get_panel(chi_so: str = Query('sol_ntl', description='Mã chỉ số, xem /api/indicators'),
              nam_tu: int = Query(YEAR_MIN, ge=1990, le=2100),
              nam_den: int = Query(YEAR_MAX, ge=1990, le=2100),
              ma_tinh: str = Query('', description='Danh sách mã tỉnh ngăn bằng dấu phẩy; '
                                                   'để trống là tất cả')):
    """Bảng rộng: mỗi dòng một tỉnh, mỗi cột một năm — như World Development Indicators."""
    if nam_tu > nam_den:
        raise HTTPException(400, 'nam_tu phải nhỏ hơn hoặc bằng nam_den')
    data = store.panel(chi_so, nam_tu, nam_den, ma_tinh.split(',') if ma_tinh else None)
    if data is None:
        raise HTTPException(404, f'Không có chỉ số nào mã {chi_so}. Xem /api/indicators')
    return data


@app.get('/api/panel.csv')
def panel_csv(chi_so: str = Query('sol_ntl'),
              nam_tu: int = Query(YEAR_MIN, ge=1990, le=2100),
              nam_den: int = Query(YEAR_MAX, ge=1990, le=2100),
              ma_tinh: str = Query(''),
              dang: str = Query('rong', description="'rong' một dòng một tỉnh, "
                                                    "'dai' một dòng một tỉnh-năm")):
    if nam_tu > nam_den:
        raise HTTPException(400, 'nam_tu phải nhỏ hơn hoặc bằng nam_den')
    if dang not in ('rong', 'dai'):
        raise HTTPException(400, "dang phải là 'rong' hoặc 'dai'")
    data = store.panel(chi_so, nam_tu, nam_den, ma_tinh.split(',') if ma_tinh else None)
    if data is None:
        raise HTTPException(404, f'Không có chỉ số nào mã {chi_so}')
    payload = export.panel_csv(data, dang)
    name = f"vngisdash_{chi_so}_{nam_tu}_{nam_den}_{dang}.csv"
    return StreamingResponse(
        io.BytesIO(payload), media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{name}"',
                 'Content-Length': str(len(payload))})


@app.get('/api/choropleth')
def get_choropleth(chi_so: str = Query('sol_ntl'),
                   nam: int = Query(YEAR_MAX, ge=1990, le=2100)):
    """Một chỉ số, một năm, mọi tỉnh — để tô màu bản đồ toàn quốc."""
    data = store.choropleth(chi_so, nam)
    if data is None:
        raise HTTPException(404, f'Không có chỉ số nào mã {chi_so}')
    return data


@app.get('/api/coverage')
def get_coverage():
    """Năm nào đã có dữ liệu gì — dùng cho trang trạng thái và báo cáo tiến độ."""
    return store.coverage()


@app.get('/api/basemap')
def basemap():
    """Danh sách năm có ảnh nền đêm, cho thanh trượt năm trên bản đồ."""
    years = store.cog_years('NTL')
    # TiTiler 0.19 có {tileMatrixSetId} trong đường dẫn; thiếu đoạn này là 404 mọi ô bản đồ.
    return {'nam': [entry['nam'] for entry in years], 'chi_tiet': years,
            'tiles': TILE_URL if _titiler_ready() else None}


@app.get('/api/anh-dem.tif')
def tai_anh_dem(nam: int = Query(..., ge=1990, le=2100)):
    """Tải ảnh đêm (COG) của một năm. Đây là mục đích chính của tab Ảnh đêm."""
    duong_dan = store.cog_path('NTL', nam)
    if not duong_dan:
        raise HTTPException(404, f'Chưa có ảnh đêm năm {nam}. '
                                 f'Chạy: python -m app.data.build_cogs --kinds VIIRS DMSP')
    path = Path(duong_dan)
    if not path.is_file():
        raise HTTPException(410, f'Sổ có ghi ảnh năm {nam} nhưng file không còn ở {path}. '
                                 f'Chạy lại build_cogs.')
    return FileResponse(path, media_type='image/tiff',
                        filename=f'VN_NTL_{nam}.tif')


@app.get('/api/originals')
def list_originals():
    """Ảnh gốc ở tầng lạnh (ổ E / NAS) — chỉ liệt kê, không phục vụ qua đám mây."""
    return {'anh_goc': store.originals(),
            'ghi_chu': 'Ảnh gốc không lưu trên đám mây để tránh chi phí egress. '
                       'Liên hệ nhóm dữ liệu để lấy liên kết tải từ tầng lạnh.'}


@app.get('/api/export.zip')
def export_zip(ma_tinh: str = Query(...),
               nam_tu: int = Query(YEAR_MIN, ge=1990, le=2100),
               nam_den: int = Query(YEAR_MAX, ge=1990, le=2100),
               kem_anh: bool = Query(True, description='Kèm ảnh đêm GeoTIFF')):
    if nam_tu > nam_den:
        raise HTTPException(400, 'nam_tu phải nhỏ hơn hoặc bằng nam_den')
    built = export.build(_code(ma_tinh), nam_tu, nam_den, kem_anh,
                         datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    if built is None:
        raise HTTPException(404, f'Không có tỉnh với mã {ma_tinh}')
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
