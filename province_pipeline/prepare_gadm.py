"""Reproducible GADM 4.1 download; upstream geometry stays outside Git history."""
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .common import atomic_json, provinces

URL = 'https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_VNM_1.json.zip'
ZIP_SHA256 = '1b82c4005ed5b4a0fead3c39c09720aa4664a394ed3b4c3e8056bca27a2fd989'
SOURCE_SHA256 = 'fb7473e5f30c1de63d851c7505b3929527cdc6ceb82757ee765201a4b240ce9e'
MEMBER = 'gadm41_VNM_1.json'
PROFILE = 'gadm41_63_provinces_research'


def convert(raw):
    """Use a checked-in exact GID+name crosswalk, never infer statistical codes from GIDs."""
    from shapely.geometry import shape
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('GADM source checksum mismatch; do not change the expected hash to bypass this')
    source = json.loads(raw)
    crosswalk_path = Path(__file__).parent/'data'/'gadm41_province_crosswalk.csv'
    with crosswalk_path.open(encoding='utf-8', newline='') as stream:
        crosswalk = list(csv.DictReader(stream))
    known = {p['ma_tinh']: p for p in provinces()}
    if len(crosswalk) != 63 or {r['ma_tinh'] for r in crosswalk} != set(known):
        raise ValueError('Crosswalk must cover all 63 statistical codes exactly once')
    by_gid = {r['gid_1']: r for r in crosswalk}
    if len(by_gid) != 63 or len(source['features']) != 63:
        raise ValueError('Duplicate crosswalk IDs or source features')
    features, seen = [], set()
    for feature in source['features']:
        props = feature['properties']
        row = by_gid[props['GID_1']]
        if row['source_name'] != props['NAME_1'] or row['ma_tinh'] in seen:
            raise ValueError('GADM identity differs from the reviewed crosswalk')
        if known[row['ma_tinh']]['ten_tinh'] != row['ten_tinh']:
            raise ValueError('Statistical manifest and crosswalk disagree')
        seen.add(row['ma_tinh'])
        geom = shape(feature['geometry'])
        if geom.is_empty or not geom.is_valid or geom.geom_type not in ('Polygon','MultiPolygon'):
            raise ValueError('Invalid source geometry; do not silently repair it')
        features.append(dict(type='Feature', properties={**props, 'ma_tinh':row['ma_tinh'],
                             'ten_tinh':row['ten_tinh']}, geometry=feature['geometry']))
    # Coordinates and polygons are preserved, not simplified, repaired, extended or redrawn.
    features.sort(key=lambda f: f['properties']['ma_tinh'])
    output = json.dumps(dict(type='FeatureCollection',features=features),ensure_ascii=False,separators=(',',':')).encode('utf-8')+b'\n'
    meta = dict(source=URL,version='GADM 4.1',date='2022-07-18',
        date_meaning='Date of source ZIP member, not certified legal boundary effective date',
        boundary_profile=PROFILE, intended_code_roster='63-provinces-2024-v1',
        code_reference='province_pipeline/data/gadm41_province_crosswalk.csv; statistical code roster province_pipeline/config/provinces.json; https://danhmuchanhchinh.gso.gov.vn/',
        crosswalk_verified=True, crosswalk_scope='Exact GADM province identity to statistical code; not legal geometry certification',
        crosswalk_sha256=hashlib.sha256(crosswalk_path.read_bytes()).hexdigest(),
        sha256=hashlib.sha256(output).hexdigest(),source_sha256=SOURCE_SHA256,archive_sha256=ZIP_SHA256,
        license_url='https://gadm.org/license.html',
        limitations=['Research footprint from GADM 4.1, not official 2024 boundaries',
                    'Only source polygons are included; no assertion of complete offshore/island or disputed-area coverage',
                    'No historical reconstruction or administrative changes after the source version'])
    # Quantify small overlaps introduced by the distributed source's polygon boundaries.
    import numpy as np
    from shapely import transform
    from shapely.ops import unary_union
    from rasterio.warp import transform as warp
    def project(xy):
        x, y = warp('EPSG:4326','EPSG:6933',xy[:,0],xy[:,1])
        return np.column_stack([x,y])
    projected = [transform(shape(f['geometry']),project) for f in features]
    pairs=[]
    for i,g in enumerate(projected):
        for j in range(i):
            overlap=g.intersection(projected[j]).area
            if overlap > 1:
                pairs.append(dict(ma_tinh_a=features[i]['properties']['ma_tinh'],
                                  ma_tinh_b=features[j]['properties']['ma_tinh'],overlap_m2=overlap))
    excess=sum(g.area for g in projected)-unary_union(projected).area
    meta['geometry_audit']=dict(crs='EPSG:6933',valid_count=len(projected),
        overlap_pairs_above_1m2=pairs,overlap_excess_km2=excess/1e6,
        overlap_fraction=excess/sum(g.area for g in projected),
        action='Source polygons retained; no automatic topology repair or legal completeness certification')
    if pairs:
        meta['limitations'].append('Source contains polygon overlap slivers; see geometry_audit before aggregating national totals')
    return output, meta


def prepare(config, archive=None):
    path, metadata = Path(config['boundaries']), Path(config['boundary_metadata'])
    if path.exists() or metadata.exists():
        if not (path.is_file() and metadata.is_file()):
            raise ValueError('Only one boundary file exists; preserve and resolve it before downloading')
        from .boundaries import load_boundaries
        found, meta = load_boundaries(config)
        if meta.get('boundary_profile') != PROFILE:
            raise ValueError('Existing non-GADM boundaries will not be overwritten')
        return len(found)
    if archive is None:
        import requests
        response = requests.get(URL, timeout=(15,120))
        response.raise_for_status()
        archive = response.content
    if hashlib.sha256(archive).hexdigest() != ZIP_SHA256:
        raise ValueError('GADM archive checksum mismatch; preserve verification')
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        raw = z.read(MEMBER)  # Named member only; never extract arbitrary archive paths.
    output, meta = convert(raw)
    meta['retrieved_at'] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:
        stream.write(output)
    atomic_json(metadata, meta)
    from .boundaries import load_boundaries
    return len(load_boundaries(config)[0])
