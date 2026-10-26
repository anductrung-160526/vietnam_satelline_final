"""Raw image jobs (Earth Engine) for one province: night first, then day.

Night raw keeps the job identities of earlier releases (same table_job -> output_job
path as generate_v2), so TIFFs already on disk are recognised and never fetched twice.

    night: DMSP annual 2004-2013, VIIRS monthly 2013-2025 (annual VIIRS is built locally)
    day:   LANDSAT monthly 2004-2014 (30 m), SENTINEL2 monthly 2015-2025 (20 m)
"""
DMSP_YEARS=range(2004,2014)
VIIRS_YEARS=range(2013,2026)
LANDSAT_YEARS=range(2004,2015)
SENTINEL_YEARS=range(2015,2026)
NIGHT='night'
DAY='day'


def specs(province,kind):
    if kind==NIGHT:
        for y in DMSP_YEARS:
            yield dict(province=province,product='DMSP',period=str(y),night=True)
        for y in VIIRS_YEARS:
            for m in range(1,13):
                yield dict(province=province,product='VIIRS_MONTHLY',period=f'{y}-{m:02}',night=True)
    elif kind==DAY:
        for product,years in (('LANDSAT',LANDSAT_YEARS),('SENTINEL2',SENTINEL_YEARS)):
            for y in years:
                for m in range(1,13):
                    yield dict(province=province,product=product,period=f'{y}-{m:02}',night=False)
    else:
        raise ValueError('kind must be night or day')


def projected_bounds(config,boundary):
    import numpy as np
    from shapely.geometry import shape
    from shapely import transform
    from rasterio.warp import transform as warp
    def project(xy):
        x,y=warp('EPSG:4326',config['crs'],xy[:,0],xy[:,1])
        return np.column_stack([x,y])
    return transform(shape(boundary['geometry']),project).bounds


def jobs(config,boundaries,metadata,kind,province):
    """Province-wide TIFF jobs, identical construction to the notebook-mode generator."""
    from province_pipeline.jobs import table_job
    from province_pipeline.common import provinces
    from .province_image import output_job
    # Canonical province record (not the branch roster row) keeps old job identities.
    province=next(p for p in provinces() if p['ma_tinh']==province['ma_tinh'])
    bounds=projected_bounds(config,boundaries[province['ma_tinh']])
    for spec in specs(province,kind):
        yield output_job(config,table_job(config,spec,metadata),bounds,0 if kind==NIGHT else 2)
