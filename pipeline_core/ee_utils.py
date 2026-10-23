# -*- coding: utf-8 -*-
"""
Tiện ích Google Earth Engine dùng chung cho 2 pipeline:
- Khởi tạo/xác thực GEE
- Gọi API có thử lại (retry) khi hết quota, quá tải, mất mạng
- Tải ảnh .tif trực tiếp về máy (getDownloadURL), tự chia ô khi ảnh vượt giới hạn và ghép lại
"""
import math
import time
import shutil
import tempfile
from pathlib import Path

import requests

from .config import EE_DOWNLOAD_MAX_BYTES, EE_MAX_RETRIES

RETRYABLE_HINTS = ("429", "quota", "rate", "too many", "timed out", "timeout", "deadline",
                   "503", "502", "500", "internal error", "connection", "temporarily", "unavailable")
TOO_LARGE_HINTS = ("must be less than", "request size", "too large", "pixel grid dimensions")

BYTES_PER_TYPE = {"uint8": 1, "int16": 2, "uint16": 2, "float": 4, "int32": 4}


def init_ee(project, logger=None):
    """Khởi tạo GEE. Lỗi -> RuntimeError kèm hướng dẫn (không chạy chế độ mô phỏng)."""
    try:
        import ee
    except ImportError as e:
        raise RuntimeError("Chưa cài 'earthengine-api'. Chạy: pip install -r requirements.txt") from e
    try:
        ee.Initialize(project=project)
    except Exception as e:
        raise RuntimeError(
            f"Không kết nối được Google Earth Engine (project='{project}'): {e}\n"
            "Chạy 'earthengine authenticate' rồi thử lại, và kiểm tra Project ID đã đăng ký GEE."
        ) from e
    return ee


def is_retryable(err):
    msg = str(err).lower()
    return any(h in msg for h in RETRYABLE_HINTS) and not is_too_large(err)


def is_too_large(err):
    msg = str(err).lower()
    return any(h in msg for h in TOO_LARGE_HINTS)


def with_retry(fn, *args, retries=EE_MAX_RETRIES, base_delay=4.0, sleep=time.sleep, **kwargs):
    """Gọi fn với thử lại lũy thừa (4s, 8s, 16s...) cho lỗi tạm thời."""
    for attempt in range(retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt >= retries or not is_retryable(e):
                raise
            sleep(base_delay * (2 ** attempt))


def get_info(obj):
    return with_retry(obj.getInfo)


def geojson_bbox(geom):
    """(xmin, ymin, xmax, ymax) của geometry GeoJSON."""
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for cc in c:
                walk(cc)
    walk(geom["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


def estimate_bytes(bbox, scale, n_bands, dtype="float"):
    xmin, ymin, xmax, ymax = bbox
    lat = math.radians((ymin + ymax) / 2)
    w = (xmax - xmin) * 111320 * max(math.cos(lat), 0.1) / scale
    h = (ymax - ymin) * 110540 / scale
    return w * h * n_bands * BYTES_PER_TYPE.get(dtype, 4)


def split_bbox(bbox, n):
    """Chia bbox thành lưới n x n ô."""
    xmin, ymin, xmax, ymax = bbox
    dx, dy = (xmax - xmin) / n, (ymax - ymin) / n
    return [(xmin + i * dx, ymin + j * dy, xmin + (i + 1) * dx, ymin + (j + 1) * dy)
            for i in range(n) for j in range(n)]


def plan_tiles(bbox, scale, n_bands, dtype="float", max_bytes=EE_DOWNLOAD_MAX_BYTES):
    est = estimate_bytes(bbox, scale, n_bands, dtype)
    n = max(1, math.ceil(math.sqrt(est / max_bytes)))
    return split_bbox(bbox, n)


def _download_url(url, dest):
    def fetch():
        with requests.get(url, stream=True, timeout=600) as r:
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    f.write(chunk)
            tmp.replace(dest)
    with_retry(fetch)


def _download_tile(ee, image, bbox, scale, dest, crs):
    region = ee.Geometry.Rectangle(list(bbox), proj="EPSG:4326", geodesic=False)
    url = with_retry(image.getDownloadURL, {
        "region": region, "scale": scale, "crs": crs,
        "format": "GEO_TIFF", "filePerBand": False,
    })
    _download_url(url, dest)


def merge_tifs(parts, dest):
    import rasterio
    from rasterio.merge import merge
    srcs = [rasterio.open(p) for p in parts]
    try:
        mosaic, transform = merge(srcs)
        meta = srcs[0].meta.copy()
        meta.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform,
                    compress="deflate", driver="GTiff")
        with rasterio.open(dest, "w", **meta) as out:
            out.write(mosaic)
    finally:
        for s in srcs:
            s.close()


def download_image(ee, image, geom_geojson, scale, dest, n_bands=1, dtype="float",
                   crs="EPSG:4326", overwrite=False):
    """
    Cắt ảnh theo ranh giới huyện và tải về dest (.tif). Ảnh lớn được chia ô theo ước lượng dung lượng;
    nếu GEE vẫn báo quá giới hạn thì chia nhỏ tiếp (2x2) rồi ghép bằng rasterio.
    Trả về số byte của tệp kết quả.
    """
    dest = Path(dest)
    if dest.is_file() and not overwrite:
        return dest.stat().st_size
    dest.parent.mkdir(parents=True, exist_ok=True)
    image = image.clip(ee.Geometry(geom_geojson))
    bbox = geojson_bbox(geom_geojson)

    queue = plan_tiles(bbox, scale, n_bands, dtype)
    if len(queue) == 1:
        try:
            _download_tile(ee, image, queue[0], scale, dest, crs)
            return dest.stat().st_size
        except Exception as e:
            if not is_too_large(e):
                raise
            queue = split_bbox(bbox, 2)

    tmpdir = Path(tempfile.mkdtemp(prefix="vngis_tiles_", dir=dest.parent))
    parts = []
    try:
        while queue:
            tb = queue.pop()
            part = tmpdir / f"part_{len(parts) + len(queue)}_{abs(hash(tb)) % 10**8}.tif"
            try:
                _download_tile(ee, image, tb, scale, part, crs)
                parts.append(part)
            except Exception as e:
                if not is_too_large(e):
                    raise
                queue.extend(split_bbox(tb, 2))
        merge_tifs(parts, dest)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return dest.stat().st_size


def ee_geometry(ee, geom_geojson):
    return ee.Geometry(geom_geojson)
