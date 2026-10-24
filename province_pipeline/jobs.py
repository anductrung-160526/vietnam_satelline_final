"""Deterministic tile jobs and one whole-province statistics job per product/period."""
from .common import digest, provinces, tile_grid
from .sources import SOURCES, NTL_PACKAGE, DAY_PACKAGE
from .layout import canonical_job


def periods(config, product):
    for year in sorted(set(config['years'])):
        if product == 'VIIRS_MONTHLY':
            for month in sorted(set(config.get('viirs_months', range(1, 13)))):
                if not 1 <= month <= 12:
                    raise ValueError('Invalid month')
                yield f'{year}-{month:02}'
        else:
            yield str(year)


def generate(config, boundaries, metadata):
    from rasterio.warp import transform_bounds
    from shapely.geometry import shape, box
    from shapely import transform
    import numpy as np
    from rasterio.warp import transform as warp
    selected = set(config['province_codes'])
    for p in provinces():
        if p['ma_tinh'] not in selected:
            continue
        geom = shape(boundaries[p['ma_tinh']]['geometry'])
        def project(xy):
            x, y = warp('EPSG:4326', config['crs'], xy[:, 0], xy[:, 1])
            return np.column_stack([x, y])
        projected = transform(geom, project)
        bounds = transform_bounds('EPSG:4326', config['crs'], *geom.bounds, densify_pts=21)
        for product in config['products']:
            source = SOURCES[product]
            night = product.startswith(('DMSP', 'VIIRS'))
            package = NTL_PACKAGE if night else DAY_PACKAGE
            sensor = 'VIIRS' if product.startswith('VIIRS') else product.split('_')[0]
            for period in periods(config, product):
                base = dict(export_backend=config.get('export_backend','batch'),province=p, product=product, period=period, boundary_sha256=metadata['sha256'],
                            recipe_hash=digest({'settings': {k: config.get(k) for k in ('season_months', 'season_months_by_province', 'crs', 'tile_pixels', 'algorithm_version')}, 'source': source}),
                            source_definition=source,
                            boundary_provenance={k: metadata[k] for k in ('source','version','date','code_reference','sha256')},
                            boundary_id=p['ma_tinh'],
                            algorithm_version=config['algorithm_version'], crs=config['crs'], scale=source['scale'])
                stage = f'raw_data/{"NTL" if night else "DAY"}/{sensor}'
                for tile in tile_grid(bounds, source['scale'], config['tile_pixels']):
                    if not projected.intersects(box(*tile['bounds'])):
                        continue
                    # Night data has both source-product and filtered versions; no fake harmonization.
                    for variant in (['source', 'filtered'] if night else ['composite']):
                        item = dict(base, kind='image', tile=tile, variant=variant, bands=source['bands'])
                        item['reserved_bytes'] = int(config['tile_pixels']**2 * len(source['bands'])*4*2 + 1048576)
                        prefix = f"{p['ma_tinh']}_{p['slug']}_{product}_{period}_{variant}_{tile['x']}_{tile['y']}_{config['algorithm_version']}"
                        directory = stage if variant != 'filtered' else 'data_intermediate/NTL/' + sensor
                        item['local_directory'] = f"{package}/{directory}/{p['ma_tinh']}_{p['slug']}/{period}"
                        item['prefix'] = prefix
                        item['job_id'] = digest(item)[:32]
                        yield canonical_job(item)
                item = dict(base, kind='table', variant='statistics', reserved_bytes=4*1048576,
                            local_directory=f"{package}/data_processed/source/{product}/{p['ma_tinh']}_{p['slug']}",
                            prefix=f"{p['ma_tinh']}_{p['slug']}_{product}_{period}_statistics_{config['algorithm_version']}")
                item['job_id'] = digest(item)[:32]
                yield canonical_job(item)


def table_job(config, spec, metadata):
    """V2 immutable recipe; scope selection and queue priority do not change identity."""
    import copy
    p, product, period = spec['province'], spec['product'], spec['period']
    source = copy.deepcopy(SOURCES[product])
    job = dict(pipeline_version=2, export_backend='direct', province=p, product=product,
               period=period, boundary_sha256=metadata['sha256'],
               boundary_provenance={k: metadata[k] for k in ('source','version','date','code_reference','sha256')},
               boundary_id=p['ma_tinh'], source_definition=source,
               algorithm_version=config['algorithm_version'], crs=config['crs'],
               scale=source['scale'] if spec['night'] else 30,
               quality=config['quality'], bands=source['bands'])
    job['recipe_hash'] = digest(dict(source=source, quality=config['quality'],
        algorithm_version=config['algorithm_version'], crs=config['crs'],
        season_months=config.get('season_months'), season_months_by_province=config.get('season_months_by_province',{})))
    job.update(kind='table', variant='statistics', priority=1, reserved_bytes=4*1048576)
    job['prefix'] = f"{p['ma_tinh']}_{p['slug']}_{product}_{period}_statistics_{config['algorithm_version']}_{job['recipe_hash'][:8]}"
    job['job_id'] = digest(job)[:32]
    return canonical_job(job)


def generate_v2(config, boundaries, metadata, priority):
    from .profiles import table_specs
    from shapely.geometry import shape, box
    from shapely import transform
    import numpy as np
    from rasterio.warp import transform as warp
    geometries = {}
    for spec in table_specs(config):
        if priority == 1:
            yield table_job(config, spec, metadata)
            continue
        if spec['night'] != (priority == 0):
            continue
        if not spec['night'] and not spec['period'].endswith('-01'):
            continue
        if not spec['night']:
            spec = dict(spec, period=spec['period'][:4])
        base = table_job(config, spec, metadata)
        product, p = base['product'], base['province']
        scale = SOURCES[product]['scale']
        if p['ma_tinh'] not in geometries:
            def project(xy):
                x,y = warp('EPSG:4326',config['crs'],xy[:,0],xy[:,1])
                return np.column_stack([x,y])
            geometries[p['ma_tinh']] = transform(shape(boundaries[p['ma_tinh']]['geometry']),project)
        projected = geometries[p['ma_tinh']]
        for tile in tile_grid(projected.bounds,scale,config['tile_pixels']):
            if not projected.intersects(box(*tile['bounds'])):
                continue
            for variant in (['source','filtered'] if spec['night'] else ['composite']):
                job = dict(base,kind='image',priority=priority,variant=variant,scale=scale,tile=tile,
                           reserved_bytes=int(config['tile_pixels']**2*len(base['bands'])*4*2+1048576))
                job.pop('job_id')
                job['prefix'] = f"{p['ma_tinh']}_{p['slug']}_{product}_{spec['period']}_{variant}_{tile['x']}_{tile['y']}_{config['algorithm_version']}_{job['recipe_hash'][:8]}"
                job['job_id'] = digest(job)[:32]
                yield canonical_job(job)
