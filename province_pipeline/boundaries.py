"""Load attributed geometry with an explicit boundary policy; never fuzzy-match province IDs."""
import hashlib
import json
from pathlib import Path
from .common import provinces


def load_boundaries(config):
    from shapely.geometry import shape
    path = Path(config['boundaries'])
    meta = json.loads(Path(config['boundary_metadata']).read_text(encoding='utf-8'))
    for key in ('source', 'version', 'date', 'sha256', 'code_reference', 'crosswalk_verified'):
        if not meta.get(key):
            raise ValueError(f'Boundary metadata missing: {key}')
    if meta['crosswalk_verified'] is not True:
        raise ValueError('Require verified provincial identity crosswalk')
    policy = config.get('boundary_policy', 'official_2024')
    if policy == 'gadm41_research':
        from .prepare_gadm import PROFILE, SOURCE_SHA256, ZIP_SHA256
        if (meta.get('boundary_profile') != PROFILE or meta.get('source_sha256') != SOURCE_SHA256
                or meta.get('archive_sha256') != ZIP_SHA256 or meta.get('version') != 'GADM 4.1'):
            raise ValueError('Expected pinned GADM 4.1 research metadata')
    elif policy != 'official_2024' or meta['date'][:4] != '2024':
        raise ValueError('Require verified 2024 provincial crosswalk or explicit gadm41_research policy')
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    if checksum != meta['sha256']:
        raise ValueError('Boundary SHA-256 mismatch')
    fc = json.loads(path.read_text(encoding='utf-8'))
    if fc.get('type') != 'FeatureCollection' or len(fc['features']) != 63:
        raise ValueError('Require a GeoJSON FeatureCollection with exactly 63 provinces in WGS84')
    expected = {p['ma_tinh'] for p in provinces()}
    found = {}
    for f in fc['features']:
        code = f['properties'].get('ma_tinh')
        geom = shape(f['geometry'])
        if code not in expected or code in found or geom.geom_type not in ('Polygon', 'MultiPolygon'):
            raise ValueError('Invalid/duplicate province code or geometry')
        if geom.is_empty or not geom.is_valid:
            raise ValueError(f'Invalid geometry for {code}')
        x0, y0, x1, y1 = geom.bounds
        if not (100 <= x0 < x1 <= 120 and 5 <= y0 < y1 <= 26):
            raise ValueError('GeoJSON coordinates must be WGS84 longitude/latitude in Vietnam')
        found[code] = f
    if set(found) != expected:
        raise ValueError('Boundary codes do not cover all 63 provinces')
    return found, meta
