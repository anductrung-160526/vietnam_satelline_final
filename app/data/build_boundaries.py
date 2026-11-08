"""Sinh ranh giới 63 tỉnh (GeoJSON rút gọn) cho bản đồ web.

    python3 -m app.data.build_boundaries              # dùng đường dẫn chuẩn của pipeline
    python3 -m app.data.build_boundaries --config <config.json>

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


# Đúng những giá trị task_pipeline.local.prepare() đặt, nên chạy không cần --config.
DEFAULT_CONFIG = {'boundaries': 'province_pipeline/config/boundaries.geojson',
                  'boundary_metadata': 'province_pipeline/config/boundaries.metadata.json',
                  'boundary_provider': 'gadm41', 'boundary_policy': 'gadm41_research'}


def build(config_path=None, out=OUT, tolerance=0.001):
    from shapely.geometry import mapping
    from shapely.geometry import shape
    from province_pipeline.boundaries import load_boundaries

    config = (json.loads(Path(config_path).read_text(encoding='utf-8'))
              if config_path else dict(DEFAULT_CONFIG))
    missing = [config[k] for k in ('boundaries', 'boundary_metadata') if not Path(config[k]).exists()]
    if missing:
        raise SystemExit('Chưa có file ranh giới: ' + ', '.join(missing) +
                         '\nChạy pipeline một lần để sinh ra chúng (prepare_gadm), '
                         'hoặc chỉ --config tới direct-config.json trong _control/<nhánh>/.')
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
    parser.add_argument('--config', default=None,
                        help='Mặc định dùng province_pipeline/config/boundaries*.json')
    parser.add_argument('--out', default=str(OUT))
    parser.add_argument('--tolerance', type=float, default=0.001,
                        help='Độ rút gọn theo độ (0.001 ≈ 100 m)')
    arguments = parser.parse_args()
    path, count, size = build(arguments.config, Path(arguments.out), arguments.tolerance)
    print(f'{count} tỉnh → {path} ({size / 1024:.0f} KB)')


if __name__ == '__main__':
    main()
