"""Configuration, identity, bounded retries, and path safety (no live API imports)."""
import hashlib
import json
import logging
import math
import random
import re
import time
from pathlib import Path, PurePosixPath, PureWindowsPath

LOG = logging.getLogger('province')


def audit(event, **fields):
    LOG.info(json.dumps({'event': event, **fields}, ensure_ascii=False, default=str))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        import os
        os.fsync(stream.fileno())
    temp.replace(path)


def provinces():
    path = Path(__file__).parent / 'config' / 'provinces.json'
    rows = json.loads(path.read_text(encoding='utf-8'))['provinces']
    assert len(rows) == len({r['ma_tinh'] for r in rows}) == 63
    assert [sum(r['group_id'] == i for r in rows) for i in range(10)] == [7]*3 + [6]*7
    return rows


def load_config(path, live=False):
    c = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    required = ('project', 'drive_root_id', 'boundaries', 'boundary_metadata', 'years',
                'province_codes', 'products', 'tile_pixels', 'crs', 'algorithm_version',
                'max_active_exports', 'high_watermark', 'low_watermark')
    for key in required:
        if key not in c:
            raise ValueError(f'Missing configuration: {key}')
    if not 0 < c['low_watermark'] < c['high_watermark'] < 1:
        raise ValueError('Require 0 < low_watermark < high_watermark < 1')
    if not 128 <= c['tile_pixels'] <= 2048 or not 1 <= c['max_active_exports'] <= 10:
        raise ValueError('Invalid tile size or global concurrency')
    if c['crs'] != 'EPSG:6933' and not (c['crs']=='EPSG:4326' and c.get('quality',{}).get('processing_mode')=='notebook_tasks'):
        raise ValueError('v1 supports the documented equal-area EPSG:6933 grid only')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,24}', c['algorithm_version']):
        raise ValueError('Unsafe algorithm version')
    if type(c.get('max_inventory_checks_per_cycle', 20)) is not int or not 1 <= c.get('max_inventory_checks_per_cycle', 20) <= 100:
        raise ValueError('Inventory checks per cycle must be in 1..100')
    if not c['years'] or any(type(y) is not int or not 2004 <= y <= 2025 for y in c['years']):
        raise ValueError('Select years in 2004..2025')
    known = {p['ma_tinh'] for p in provinces()}
    if not c['province_codes'] or not set(c['province_codes']) <= known:
        raise ValueError('Province codes must be two-character strings from the 63-province manifest')
    from .sources import SOURCES
    if not c['products'] or not set(c['products']) <= set(SOURCES):
        raise ValueError('Unsupported product')
    if c.get('pipeline_version') == 2:
        from .profiles import validate_quality, PROFILES
        if c.get('run_profile') not in PROFILES and not re.fullmatch(r'task123_\d{3}_\d{3}_(pilot|full)',c.get('run_profile','')):
            raise ValueError('Select a supported run profile')
        validate_quality(c.get('quality',{}))
    backend = c.get('export_backend', 'batch')
    if backend not in ('batch', 'direct'):
        raise ValueError('export_backend must be batch or direct')
    if backend == 'direct':
        from .direct_export import check_tile_limit
        check_tile_limit(c)
    if live:
        for key in ('project', 'drive_root_id', 'drive_staging_budget_gib', 'drive_safety_margin_gib'):
            if not c.get(key):
                raise ValueError(f'Configure {key} before contacting services')
        if c['drive_safety_margin_gib'] <= 0 or c['drive_staging_budget_gib'] <= c['drive_safety_margin_gib']:
            raise ValueError('Invalid storage budget/margin')
    return c


def local_path(root, relative):
    """Reject POSIX/Windows traversal, drives, alternate streams, and symlink escape."""
    if not relative or '\\' in relative or ':' in relative:
        raise ValueError('Unsafe destination path')
    path = PurePosixPath(relative)
    if path.is_absolute() or PureWindowsPath(relative).drive or '..' in path.parts:
        raise ValueError('Unsafe destination path')
    for part in path.parts:
        if part.endswith((' ', '.')) or part.split('.')[0].upper() in {
            'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
            raise ValueError('Unsafe Windows filename')
    root = Path(root).resolve()
    dest = root.joinpath(*path.parts).resolve()
    if not dest.is_relative_to(root):
        raise ValueError('Destination escapes local root')
    return dest


def retry(call, attempts=4):
    """Retry only known transient HTTP failures; permission/schema errors propagate."""
    for attempt in range(attempts):
        try:
            return call()
        except Exception as error:
            status = getattr(getattr(error, 'resp', None), 'status', None)
            if status not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
            time.sleep(min(30, 2**attempt) + random.random())


def tile_grid(bounds, scale, pixels):
    size = scale * pixels
    xmin, ymin, xmax, ymax = bounds
    for x in range(math.floor(xmin/size), math.ceil(xmax/size)):
        for y in range(math.floor(ymin/size), math.ceil(ymax/size)):
            yield {'x': x, 'y': y, 'bounds': [x*size, y*size, (x+1)*size, (y+1)*size],
                   'transform': [scale, 0, x*size, 0, -scale, (y+1)*size]}
