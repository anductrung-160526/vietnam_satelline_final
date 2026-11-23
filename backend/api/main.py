"""VNGISDash API — lớp đọc trên data_processed và các COG.

Chạy thử:
    python3 -m backend.data.build_indices --root /data/SatelliteData
    uvicorn backend.api.main:app --reload       # rồi mở http://localhost:8000

TiTiler được nạp nếu có cài; không có thì API vẫn chạy, chỉ thiếu ô bản đồ.
"""
import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import export, store
from backend.core.public_fields import is_public

WEB = Path(__file__).resolve().parent.parent.parent / 'frontend'
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


GIAO_DIEN = ('index.html', 'style.css', 'app.js', 'demo.js', 'spatial.js', 'data-table.js')


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
    from backend.data.database_status import inspect_database
    return {'ok': True, 'so_tinh': count, 'data_status':inspect_database(store.database_path()), 'db': str(store.database_path()),
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


@app.get('/api/coverage')
def get_coverage():
    """Năm nào đã có dữ liệu gì — dùng cho trang trạng thái và báo cáo tiến độ."""
    return store.coverage()


@app.get('/api/basemap')
def basemap(buoc: str = Query('nam', description="'nam' hoặc 'thang'"),province_code: str=''):
    """Danh sách mốc thời gian có ảnh nền đêm, cho thanh trượt trên bản đồ."""
    if buoc not in ('nam', 'thang'):
        raise HTTPException(400, "buoc phải là 'nam' hoặc 'thang'")
    muc = store.cog_years('NTL', buoc)
    steps=store.cac_buoc_thoi_gian('NTL')
    if province_code:
        from .provenance import has_table,available_asset
        code=_code(province_code)
        with store.connect() as connection:
            if has_table(connection,'demo_asset'):
                registered=[]
                for row in connection.execute("SELECT year,month FROM demo_asset WHERE province_code=? AND kind='processed' ORDER BY year,month",(code,)):
                    item=available_asset(connection,code,row['year'],row['month'],'processed')
                    if item and item['available']:registered.append(dict(year=row['year'],month=row['month'],path=item['export_path'],source=item['source']))
                if registered:
                    muc=[r for r in registered if (r['month']==0)==(buoc=='nam')]
                    steps={'nam':sum(r['month']==0 for r in registered),'thang':sum(r['month']>0 for r in registered)}
    # TiTiler 0.19 có {tileMatrixSetId} trong đường dẫn; thiếu đoạn này là 404 mọi ô bản đồ.
    return {'buoc': buoc,
            'co_san': steps,
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
        ma_hinh = feature.get('properties', {})
        ket_qua.append({'province_code': ma_hinh.get('province_code') or ma_hinh.get('ma_tinh'),
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
        thuoc_tinh = f['properties']
        # Tệp dựng trước đợt đổi tên cột còn mang khoá ma_tinh; đọc cả hai.
        ma = thuoc_tinh.get('province_code') or thuoc_tinh.get('ma_tinh') or ''
        if str(ma).zfill(2) == province_code:
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
        lenh = ('python -m backend.data.build_monthly_cogs' if thang
                else 'python -m backend.data.build_cogs --kinds VIIRS DMSP')
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
                                 'python3 -m backend.data.build_boundaries --tai-gadm')
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
        raise HTTPException(404, 'Chưa có ranh giới. Chạy: python3 -m backend.data.build_boundaries '
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
    from titiler.core.errors import add_exception_handlers, DEFAULT_STATUS_CODES
    add_exception_handlers(app, DEFAULT_STATUS_CODES)
    tiler = TilerFactory()
    app.include_router(tiler.router, prefix='/tiles/cog', tags=['tiles'])
    return True


# Phần B: các API chỉ đọc phục vụ nhóm Raw/Processed và đối chiếu GRDP.
from . import demo_view


def demo_snapshot_id():
    try:
        with store.connect() as connection:
            if not demo_view.has_table(connection,'demo_schema_meta'):return None
            row=connection.execute("SELECT value FROM demo_schema_meta WHERE key='current_dataset'").fetchone()
            return row[0] if row else None
    except sqlite3.Error:return None


@app.middleware('http')
async def same_snapshot_for_api(request,call_next):
    if not request.url.path.startswith('/api/'):return await call_next(request)
    before=demo_snapshot_id()
    response=await call_next(request)
    after=demo_snapshot_id()
    if before!=after:
        return JSONResponse(status_code=409,content={'detail':'Bộ dữ liệu vừa thay đổi. Tải lại trang để đồng bộ.'},
                            headers={'X-Snapshot-ID':after or ''})
    response.headers['X-Snapshot-ID']=before or ''
    response.headers['Cache-Control']='no-store'
    return response


@app.get('/api/demo/province')
def demo_province(province_code: str, nam: int = Query(..., ge=2004, le=2025),
                  thang: int = Query(0, ge=0, le=12)):
    result = demo_view.province_view(_code(province_code), nam, thang)
    if result is None:
        raise HTTPException(404, 'Không có mã tỉnh này.')
    result['tiles'] = TILE_URL if _titiler_ready() else None
    result.setdefault('snapshot_id',demo_snapshot_id())
    return result


@app.get('/api/demo/economy')
def demo_economy(nam_tu: int = Query(2020, ge=2004, le=2025),
                 nam_den: int = Query(2024, ge=2004, le=2025),
                 province_code: str = '', price_basis: str = 'so_sanh', thang: int=Query(0,ge=0,le=12)):
    if nam_tu > nam_den or price_basis not in ('so_sanh', 'hien_hanh', 'compare'):
        raise HTTPException(400, 'Khoảng năm hoặc cơ sở giá không hợp lệ.')
    result=demo_view.economic_view(nam_tu, nam_den, _code(province_code) if province_code else None, price_basis)
    for row in result['dong']:row['month']=thang
    if thang:
        for row in result['dong']:
            for field in ('population','grdp','grdp_so_sanh','grdp_hien_hanh','gdp_change_pct'):row[field]=None
    for row in result['dong']:
        row.pop('population',None);row.pop('sol_per_capita',None)
    result.pop('population_missing',None)
    result.setdefault('snapshot_id',demo_snapshot_id())
    return result


@app.get('/api/demo/economy.csv')
def demo_economy_csv(nam_tu: int = Query(2020, ge=2004, le=2025),
                     nam_den: int = Query(2024, ge=2004, le=2025),
                     province_code: str = '', price_basis: str = 'so_sanh',expected_snapshot: str='',thang: int=Query(0,ge=0,le=12)):
    import csv
    data = demo_economy(nam_tu, nam_den, province_code, price_basis,thang)
    if expected_snapshot and data.get('snapshot_id')!=expected_snapshot:
        raise HTTPException(409,'Bộ dữ liệu đã đổi; tải lại trang trước khi tải CSV.')
    fields = ['province_code', 'province_name', 'year', 'month', 'population', 'grdp_so_sanh',
              'grdp_hien_hanh', 'sol', 'sol_per_capita', 'light_gdp_elasticity', 'predicted_gdp', 'derived_price_basis', 'paired', 'unit',
              'price_base_year', 'is_provisional', 'quality_flags', 'source_so_sanh', 'source_hien_hanh',
              'gdp_change_pct', 'image_quality_flags', 'comparison_note', 'light_basis', 'area_method',
              'model_training_period', 'model_n', 'model_beta','dataset_id','stats_version','sol_unit',
              'provenance_consistent','provenance_reason','source_image_path','source_image_sha256']
    fields=[f for f in fields if is_public(f) or f=='class_area_km2']
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(data['dong'])
    return StreamingResponse(io.BytesIO(stream.getvalue().encode('utf-8-sig')), media_type='text/csv',
                             headers={'Content-Disposition': 'attachment; filename="night_economy_comparison.csv"'})


@app.get('/api/demo/image')
def demo_image(province_code: str, nam: int = Query(..., ge=2004, le=2025),
               thang: int = Query(0, ge=0, le=12), kind: str = 'raw',expected_snapshot: str=''):
    if kind not in ('raw', 'processed', 'classes', 'support'):
        raise HTTPException(400, 'Loại ảnh không hợp lệ.')
    from .provenance import available_asset,current_id
    with store.connect() as connection:
        connection.execute('BEGIN')
        snapshot=current_id(connection)
        if expected_snapshot and snapshot!=expected_snapshot:
            raise HTTPException(409,'Bộ dữ liệu đã đổi; tải lại trang trước khi tải ảnh.')
        item=available_asset(connection,_code(province_code),nam,thang,kind)
    if not item:
        raise HTTPException(404, 'Chưa đăng ký ảnh ở mốc này.')
    if not item['available']:
        raise HTTPException(410, item['reason'])
    return FileResponse(item.get('export_path') or item['path'], media_type='image/tiff',
                        headers={'X-Source-SHA256':item.get('source_sha256') or 'unverified',
                                 'X-Snapshot-ID':snapshot or 'unverified','X-Mask-Rule':item.get('mask_rule') or 'unverified'},
                        filename=f"night_{_code(province_code)}_{nam}_{thang:02}_{kind}.tif")


@app.get('/api/demo/classes.csv')
def demo_classes_csv(province_code: str, nam: int = Query(..., ge=2004, le=2025),
                     thang: int = Query(0, ge=0, le=12),expected_snapshot: str=''):
    """Xuất số đã kiểm chứng từ SQLite; không đọc/tính raster trong API."""
    import csv
    data = demo_view.province_view(_code(province_code), nam, thang)
    if data is None:
        raise HTTPException(404, 'Không có mã tỉnh này.')
    if expected_snapshot and data.get('snapshot_id')!=expected_snapshot:
        raise HTTPException(409,'Bộ dữ liệu đã đổi; tải lại trang trước khi tải CSV.')
    if data['class_status'] != 'ready' or data['class_summary'] is None:
        raise HTTPException(404, 'Chưa có kết quả kiểm chứng phần D; chạy build_light_classes trước.')
    summary = data['class_summary']
    fields = ['province_code', 'year', 'month', 'class_index', 'lower_bound', 'upper_bound',
              'class_area_km2', 'class_area_pct', 'area_km2', 'valid_area_km2', 'valid_area_pct',
              'validation_status', 'reference_year', 'method_version', 'unit', 'area_source','dataset_id','stats_version','source_image_sha256']
    fields=[f for f in fields if is_public(f) or f=='class_area_km2']
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in data['classes']:
        writer.writerow(dict(summary, **{k: v for k, v in row.items() if k != 'area_km2'},
                             class_area_km2=row['area_km2'],dataset_id=data['provenance']['dataset_id'],
                             stats_version=data['provenance']['stats_version'],source_image_sha256=data['provenance']['source_sha256']))
    return StreamingResponse(io.BytesIO(stream.getvalue().encode('utf-8-sig')), media_type='text/csv',
                             headers={'Content-Disposition': 'attachment; filename="night_light_classes.csv"'})


@app.get('/api/demo/province.csv')
def demo_province_csv(province_code: str,nam: int=Query(...,ge=2004,le=2025),thang: int=Query(0,ge=0,le=12),expected_snapshot: str=''):
    """Bảng dài một field một dòng, cùng giá trị/đơn vị/Raw–Processed với màn chỉ số."""
    import csv
    data=demo_province(province_code,nam,thang)
    if expected_snapshot and data.get('snapshot_id')!=expected_snapshot:
        raise HTTPException(409,'Bộ dữ liệu đã đổi; tải lại trang trước khi tải CSV.')
    columns=['province_code','province_name','year','month','field','stage','value','unit','reason',
             'dataset_id','stats_version','light_basis','area_method','grdp_price_basis',
             'source_image_path','source_image_sha256','provenance_consistent']
    columns=[c for c in columns if is_public(c) or c in ('field','stage','value','unit')]
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=columns,extrasaction='ignore');writer.writeheader()
    for field in data['fields']:
        value=field['value']
        if field.get('is_raster') and field.get('available'):
            value=data['raw_asset']['path']+'#band='+str(field['band'])
        basis='hien_hanh' if field['field']=='grdp_hien_hanh' else 'so_sanh' if field['field'] in ('grdp_so_sanh','predicted_gdp','light_gdp_elasticity') else ''
        writer.writerow(dict(province_code=_code(province_code),province_name=data['province']['province_name'],year=nam,month=thang,
                             field=field['field'],stage=field['stage'],value=value,unit=field['unit'],reason=field.get('reason',''),
                             dataset_id=data['provenance']['dataset_id'],stats_version=data['provenance']['stats_version'],
                             light_basis=data['light_basis'],area_method=data['area_method'],grdp_price_basis=basis,
                             source_image_path=(data['raw_asset'] or {}).get('path') if field.get('is_raster') else data['provenance']['source_path'],
                             source_image_sha256=(data['raw_asset'] or {}).get('source_sha256') if field.get('is_raster') else data['provenance']['source_sha256'],
                             provenance_consistent=data['provenance']['consistent']))
    return StreamingResponse(io.BytesIO(stream.getvalue().encode('utf-8-sig')),media_type='text/csv',
                             headers={'Content-Disposition':'attachment; filename="night_province_fields.csv"'})


@app.get('/api/demo/dataset')
def demo_dataset():
    from backend.data.dataset import snapshot_status
    with store.connect() as connection:
        datasets=snapshot_status(connection)
        row=connection.execute("SELECT value FROM demo_schema_meta WHERE key='version'").fetchone() if demo_view.has_table(connection,'demo_schema_meta') else None
    return dict(snapshot_id=demo_snapshot_id(),demo_schema_version=int(row[0]) if row else None,datasets=list(datasets.values()))


@app.get('/api/demo/status')
def demo_status():
    from backend.data.database_status import inspect_database
    return inspect_database(store.database_path())


@app.get('/api/demo/data')
def demo_data(moc: str='2024',province_code: str='',chi_so: str=''):
    from .data_table import data_table
    try:
        return data_table(moc.split(','),[_code(c) for c in province_code.split(',')] if province_code else None,
                          chi_so.split(',') if chi_so else None)
    except ValueError as error:raise HTTPException(400,str(error))


@app.get('/api/demo/data.csv')
def demo_data_csv(moc: str='2024',province_code: str='',chi_so: str='',expected_snapshot: str=''):
    import csv
    data=demo_data(moc,province_code,chi_so)
    if expected_snapshot and data['snapshot_id']!=expected_snapshot:
        raise HTTPException(409,'Bộ dữ liệu đã đổi; tải lại bảng trước khi xuất CSV.')
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=[c['field'] for c in data['columns']])
    writer.writeheader();writer.writerows(data['rows'])
    return StreamingResponse(io.BytesIO(stream.getvalue().encode('utf-8-sig')),media_type='text/csv',
                             headers={'Content-Disposition':'attachment; filename="night_data_monthly.csv"'})


@app.get('/api/spatial')
def spatial(year_start: int=Query(2020,ge=2004,le=2025),year_end: int=Query(2024,ge=2004,le=2025)):
    if year_start>=year_end:raise HTTPException(400,'Năm đầu phải nhỏ hơn năm cuối.')
    from .spatial_view import read_spatial
    result=read_spatial(year_start,year_end)
    if result['status']!='ready':return {k:result[k] for k in ('status','snapshot_id','message','available_pairs') if k in result}
    return dict(status='ready',snapshot_id=result['snapshot_id'],run_id=result['run_id'],moran=[dict(year=r['year'],moran_i=r['moran_i']) for r in result['moran']])


@app.get('/api/spatial/file')
def spatial_file(kind: str,run_id: str,expected_snapshot: str,
                 year_start: int=Query(2020,ge=2004,le=2025),year_end: int=Query(2024,ge=2004,le=2025),province_code: str=''):
    from .spatial_view import read_spatial
    result=read_spatial(year_start,year_end)
    if result['snapshot_id']!=expected_snapshot or result.get('run_id')!=run_id:
        raise HTTPException(409,'Kết quả P1 đã đổi; tải lại màn phân tích trước khi tải file.')
    if result['status']!='ready':raise HTTPException(410,result.get('message','Kết quả P1 không sẵn có.'))
    if kind in ('change','delta'):
        key=_code(province_code)+'_'+kind
    elif kind in ('moran','moran_values','changes','transitions','neighbors','province_changes'):key=kind
    else:raise HTTPException(400,'Loại file P1 không hợp lệ.')
    if kind!='moran':raise HTTPException(404,'Trường phân tích này đã được bỏ khỏi app.')
    import csv
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=['year','moran_i']);writer.writeheader()
    writer.writerows({'year':r['year'],'moran_i':r['moran_i']} for r in result['moran'])
    return StreamingResponse(io.BytesIO(stream.getvalue().encode('utf-8-sig')),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="moran.csv"'})



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
