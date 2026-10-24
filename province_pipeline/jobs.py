"""Deterministic tile jobs and one whole-province statistics job per product/period."""
from .common import digest, provinces, tile_grid
from .sources import SOURCES, NTL_PACKAGE, DAY_PACKAGE


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
                base = dict(province=p, product=product, period=period, boundary_sha256=metadata['sha256'],
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
                        yield item
                item = dict(base, kind='table', variant='statistics', reserved_bytes=4*1048576,
                            local_directory=f"{package}/data_processed/source/{product}/{p['ma_tinh']}_{p['slug']}",
                            prefix=f"{p['ma_tinh']}_{p['slug']}_{product}_{period}_statistics_{config['algorithm_version']}")
                item['job_id'] = digest(item)[:32]
                yield item
