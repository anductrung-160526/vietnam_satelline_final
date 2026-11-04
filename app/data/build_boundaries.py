"""Sinh ranh giới 63 tỉnh (GeoJSON rút gọn) cho bản đồ web.

    python3 -m app.data.build_boundaries --config .province-local/config.json

Đọc qua province_pipeline.boundaries.load_boundaries nên vẫn chịu mọi kiểm tra của
pipeline: GADM 4.1 đúng SHA-256, đủ 63 mã tỉnh, hình học hợp lệ, toạ độ nằm trong
Việt Nam. Không có bản sao ranh giới thứ hai trong app.

Hình học được rút gọn cho web (mặc định ~100 m) vì bản đồ chỉ cần đường bao để bấm chọn;
phép cắt ảnh vẫn dùng ranh giới gốc, không dùng file này.
"""
import argparse
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'provinces.geojson'


def build(config_path, out=OUT, tolerance=0.001):
    from shapely.geometry import mapping
    from shapely.geometry import shape
    from province_pipeline.boundaries import load_boundaries

    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    found, meta = load_boundaries(config)
    features = []
    for code in sorted(found):
        feature = found[code]
        geometry = shape(feature['geometry']).simplify(tolerance, preserve_topology=True)
        if geometry.is_empty:                       # rút gọn quá tay thì giữ bản gốc
            geometry = shape(feature['geometry'])
        properties = feature.get('properties', {})
        features.append({'type': 'Feature',
                         'properties': {'ma_tinh': code,
                                        'ten_tinh': properties.get('ten_tinh'),
                                        'gid_1': properties.get('gid_1')},
                         'geometry': mapping(geometry)})
    collection = {'type': 'FeatureCollection',
                  'metadata': {'nguon': meta.get('source'), 'phien_ban': meta.get('version'),
                               'sha256_goc': meta.get('sha256'), 'rut_gon_do': tolerance,
                               'ghi_chu': 'Chỉ dùng để hiển thị và bấm chọn trên web; '
                                          'phép cắt ảnh dùng ranh giới gốc.'},
                  'features': features}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(collection, ensure_ascii=False), encoding='utf-8')
    return out, len(features), out.stat().st_size


def main():
    parser = argparse.ArgumentParser(description='Sinh ranh giới tỉnh cho bản đồ web')
    parser.add_argument('--config', default='.province-local/config.json')
    parser.add_argument('--out', default=str(OUT))
    parser.add_argument('--tolerance', type=float, default=0.001,
                        help='Độ rút gọn theo độ (0.001 ≈ 100 m)')
    arguments = parser.parse_args()
    path, count, size = build(arguments.config, Path(arguments.out), arguments.tolerance)
    print(f'{count} tỉnh → {path} ({size / 1024:.0f} KB)')


if __name__ == '__main__':
    main()
