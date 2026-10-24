"""Explicit run scopes. Scientific identity is independent of test/full selection."""
from .common import provinces
PROFILES = ('test_hanoi_2025', 'full_2004_2025')

def apply_profile(config, profile):
    if profile not in PROFILES:
        raise ValueError('Unknown run profile')
    c = dict(config)
    c.update(pipeline_version=2, run_profile=profile, export_backend='direct',
             years=[2025] if profile == PROFILES[0] else list(range(2004, 2026)),
             province_codes=['01'] if profile == PROFILES[0] else [p['ma_tinh'] for p in provinces()],
             products=['DMSP', 'VIIRS_MONTHLY', 'LANDSAT', 'SENTINEL2'],
             viirs_months=list(range(1, 13)), algorithm_version='v002',
             max_active_exports=10, max_inventory_checks_per_cycle=20,
             tile_pixels=512, crs='EPSG:6933')
    quality = dict(min_valid_area_pct=80, min_observations_day=2,
                   min_cloud_free_obs=1, sentinel_cloud_score_min=0.60,
                   landsat_cloud_buffer_m=60, lit_threshold_dmsp=5,
                   lit_threshold_viirs=0.5, mask_fires=True,
                   anomaly_robust_z=6, max_transfer_attempts=4)
    quality.update(c.get('quality', {}))
    validate_quality(quality)
    c['quality'] = quality
    return c

def source_for(year, night):
    return ('DMSP' if year <= 2013 else 'VIIRS_MONTHLY') if night else ('LANDSAT' if year <= 2017 else 'SENTINEL2')

def table_specs(config):
    selected = set(config['province_codes'])
    for p in provinces():
        if p['ma_tinh'] not in selected:
            continue
        for night in (True, False):
            for year in sorted(set(config['years'])):
                product = source_for(year, night)
                for month in ([None] if product == 'DMSP' else range(1, 13)):
                    period = str(year) if month is None else f'{year}-{month:02}'
                    yield dict(province=p, product=product, period=period, night=night)

def in_scope(config, job):
    if job.get('pipeline_version') != 2:
        return False
    if job['province']['ma_tinh'] not in config['province_codes'] or int(job['period'][:4]) not in config['years']:
        return False
    from .common import digest
    from .sources import SOURCES
    expected=digest(dict(source=SOURCES[job['product']],quality=config['quality'],
        algorithm_version=config['algorithm_version'],crs=config['crs'],
        season_months=config.get('season_months'),season_months_by_province=config.get('season_months_by_province',{})))
    return (job.get('recipe_hash')==expected and
            job['product'] == source_for(int(job['period'][:4]), job['product'].startswith(('DMSP','VIIRS'))))


def validate_quality(q):
    import math
    limits={'min_valid_area_pct':(0,100),'min_observations_day':(1,1000),
            'min_cloud_free_obs':(1,10000),'sentinel_cloud_score_min':(0,1),
            'landsat_cloud_buffer_m':(0,1000),'lit_threshold_dmsp':(0,63),
            'lit_threshold_viirs':(0,100000),'anomaly_robust_z':(1,100),
            'max_transfer_attempts':(1,4)}
    for key,(lo,hi) in limits.items():
        if isinstance(q.get(key),bool) or not isinstance(q.get(key),(int,float)) or not math.isfinite(q[key]) or not lo<=q[key]<=hi:
            raise ValueError('Invalid quality setting: '+key)
    if type(q.get('mask_fires')) is not bool:
        raise ValueError('mask_fires must be boolean')
