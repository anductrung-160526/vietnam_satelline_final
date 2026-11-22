"""Diện tích giao pixel–tỉnh trong EPSG:6933; cache độc lập mask từng ảnh."""
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
import shapely
from shapely.geometry import shape
from rasterio.warp import transform, transform_geom

from backend.core.ranh_gioi.boundaries import load_boundaries

AREA_METHOD = 'pixel_polygon_intersection_epsg6933_v1'


def pixel_intersection_areas(image, polygon):
    """Pixel EPSG:4326/6933 thành hình chữ nhật EPSG:6933, giao đúng polygon kể cả lỗ/đảo."""
    t = image.transform
    if t.b or t.d or t.a <= 0 or t.e >= 0:
        raise ValueError('Diện tích giao chỉ hỗ trợ raster north-up, không xoay.')
    x = t.c + np.arange(image.width+1)*t.a
    y = t.f + np.arange(image.height+1)*t.e
    if image.crs.to_epsg() == 4326:
        x, _ = transform(image.crs, 'EPSG:6933', x.tolist(), [0.]*len(x))
        _, y = transform(image.crs, 'EPSG:6933', [0.]*len(y), y.tolist())
        x, y = np.asarray(x), np.asarray(y)
    elif image.crs.to_epsg() != 6933:
        raise ValueError('Diện tích giao cần EPSG:4326 hoặc EPSG:6933; không tự đổi lưới khác.')
    weights = np.zeros((image.height, image.width), dtype='float64')
    shapely.prepare(polygon)
    # Giới hạn lượng hình học trong RAM, không intersection chậm cho pixel hoàn toàn trong/ngoài.
    for first in range(0, image.height*image.width, 32768):
        index = np.arange(first, min(first+32768, image.height*image.width))
        row, col = index//image.width, index % image.width
        boxes = shapely.box(x[col], y[row+1], x[col+1], y[row])
        inside = shapely.covers(polygon, boxes)
        values = np.zeros(len(index))
        values[inside] = (x[col[inside]+1]-x[col[inside]])*(y[row[inside]]-y[row[inside]+1])/1e6
        fringe = ~inside & shapely.intersects(polygon, boxes)
        values[fringe] = shapely.area(shapely.intersection(boxes[fringe], polygon))/1e6
        weights.ravel()[index] = values
    area = polygon.area/1e6
    if not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() > area+max(1e-8, area*1e-10):
        raise ValueError('Diện tích giao không hữu hạn/âm hoặc vượt diện tích polygon.')
    return weights


class ProvinceAreas:
    def __init__(self, features, metadata, cache_dir=None):
        self.metadata = metadata
        self.polygons = {code: shape(transform_geom('EPSG:4326', 'EPSG:6933', f['geometry'])) for code,f in features.items()}
        self.areas = {code: p.area/1e6 for code,p in self.polygons.items()}
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.memory = OrderedDict()

    def weights(self, code, image):
        if code not in self.polygons:
            raise ValueError(f'Không có ranh giới tỉnh {code}.')
        spec = dict(code=code, shape=image.shape, crs=str(image.crs), transform=tuple(image.transform),
                    geometry=hashlib.sha256(self.polygons[code].wkb).hexdigest(), method=AREA_METHOD)
        fingerprint = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        if fingerprint in self.memory:
            self.memory.move_to_end(fingerprint)
            return self.memory[fingerprint]
        path = self.cache_dir/(fingerprint+'.npz') if self.cache_dir else None
        if path and path.exists():
            with np.load(path, allow_pickle=False) as stored:
                weights = stored['weights']
                if str(stored['fingerprint']) != fingerprint or weights.shape != image.shape:
                    raise ValueError('Cache diện tích không khớp lưới/ranh giới.')
            if not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() > self.areas[code]+1e-7:
                raise ValueError('Cache diện tích không hợp lệ.')
        else:
            weights = pixel_intersection_areas(image, self.polygons[code])
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    np.savez_compressed(stream, weights=weights, fingerprint=fingerprint)
                temporary.replace(path)
        weights.flags.writeable = False
        self.memory[fingerprint] = weights
        if len(self.memory) > 4:
            self.memory.popitem(last=False)
        return weights


def load_area_model(root, boundaries=None, boundary_metadata=None):
    repo = Path(__file__).resolve().parents[2]
    path = Path(boundaries) if boundaries else repo/'backend/core/ranh_gioi/config/boundaries.geojson'
    if boundaries is None and not path.exists():
        path = repo/'province_pipeline/config/boundaries.geojson'
    metadata = Path(boundary_metadata) if boundary_metadata else path.with_name('boundaries.metadata.json')
    features, info = load_boundaries(dict(boundaries=str(path), boundary_metadata=str(metadata), boundary_policy='gadm41_research'))
    return ProvinceAreas(features, info, Path(root)/'_demo_area_weights')


def percent_area(part, total):
    # Chỉ làm tròn sai số số thực; mọi sai lệch thực vượt 100% đều làm dừng.
    if part < -1e-9 or part > total+max(1e-8, total*1e-10):
        raise ValueError('Diện tích trong tỉnh vượt polygon, cần kiểm tra lưới/ranh giới.')
    return round(100*part/total, 8)
