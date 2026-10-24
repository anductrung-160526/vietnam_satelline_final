"""Real Earth Engine composites only. No synthetic data or geometry fallback."""
from .sources import SOURCES, BANDS


def initialize(config, creds):
    import ee
    ee.Initialize(credentials=creds, project=config['project'])
    ee.data.setDeadline(120000)


def date_range(period):
    year = int(period[:4])
    if len(period) == 7:
        month = int(period[5:])
        return f'{year}-{month:02}-01', f'{year + (month == 12)}-{month % 12 + 1:02}-01'
    return f'{year}-01-01', f'{year+1}-01-01'


def collection(config, product, period, geometry):
    import ee
    start, end = date_range(period)
    collections = [ee.ImageCollection(c).filterDate(start, end).filterBounds(geometry)
                   for c in SOURCES[product]['collections']]
    coll = collections[0]
    for other in collections[1:]:
        coll = coll.merge(other)
    if product.startswith(('LANDSAT', 'SENTINEL2')):
        # Configured months are within the labeled calendar year, not a hidden cross-year window.
        months = config.get('season_months_by_province', {}).get(config.get('_province_code'),
                    config.get('season_months', list(range(1, 13))))
        if not months or any(m not in range(1, 13) for m in months):
            raise ValueError('Invalid season months')
        coll = coll.map(
            lambda i: i.set('_month', ee.Date(i.get('system:time_start')).get('month'))).filter(
                ee.Filter.inList('_month', months))
    return coll


def inventory(config, product, period, geometry):
    import ee
    coll = collection(config, product, period, geometry)
    info = ee.Dictionary({'count': coll.size(), 'dates': coll.aggregate_array('system:time_start'),
                          'asset_ids': coll.aggregate_array('system:id')}).getInfo()
    dates = info.get('dates', [])
    from datetime import datetime, timezone
    months = sorted({datetime.fromtimestamp(t/1000, timezone.utc).month for t in dates})
    status = 'AVAILABLE' if info['count'] else 'UNAVAILABLE'
    if info['count'] and (product == 'VIIRS_ANNUAL' and len(months) != 12):
        status = 'PARTIAL'
    if info['count'] and product.startswith('SENTINEL2') and int(period[:4]) == 2017:
        status = 'PARTIAL'  # SR catalog starts during the year.
    return dict(product=product, period=period, status=status, count=info['count'],
                observed_months=months, collections=SOURCES[product]['collections'], asset_ids=info.get('asset_ids', []))


def _indices(img):
    import ee
    def ratio(a, b, name):
        denominator = a.add(b)
        return a.subtract(b).divide(denominator).updateMask(denominator.abs().gt(1e-8)).rename(name)
    red, green, nir, swir, blue = [img.select(b) for b in ['RED','GREEN','NIR','SWIR1','BLUE']]
    return img.addBands([
        ratio(nir, red, 'NDVI'), ratio(swir, nir, 'NDBI'), ratio(green, swir, 'MNDWI'),
        ratio(swir.add(red), nir.add(blue), 'BSI')])


def _landsat(img):
    import ee
    modern = ee.List(['LANDSAT_8','LANDSAT_9']).contains(img.get('SPACECRAFT_ID'))
    names = ee.List(ee.Algorithms.If(modern,
                    ['SR_B2','SR_B3','SR_B4','SR_B5','SR_B6','SR_B7'],
                    ['SR_B1','SR_B2','SR_B3','SR_B4','SR_B5','SR_B7']))
    valid = img.select('QA_PIXEL').bitwiseAnd(63).eq(0).And(img.select('QA_RADSAT').eq(0))
    return img.select(names, BANDS).multiply(0.0000275).add(-0.2).updateMask(valid)


def _sentinel(img):
    scl = img.select('SCL')
    mask = scl.neq(0).And(scl.neq(1)).And(scl.neq(3)).And(scl.lt(8)).And(scl.neq(7))
    return img.select(['B2','B3','B4','B8','B11','B12'], BANDS).multiply(0.0001).updateMask(mask)


def composite(config, job, geometry):
    import ee
    product = job['product']
    c = dict(config, _province_code=job['province']['ma_tinh'])
    ids = job.get('inventory', {}).get('asset_ids', [])
    if not ids:
        raise ValueError('Export requires a persisted source asset snapshot from inventory')
    coll = ee.ImageCollection.fromImages([ee.Image(asset_id) for asset_id in ids])
    if product == 'LANDSAT':
        image = _indices(coll.map(_landsat).median())
    elif product.startswith('SENTINEL2'):
        # Optical bands are bilinear-resampled; categorical SCL is masked before resampling.
        image = _indices(coll.map(lambda i: _sentinel(i).resample('bilinear')).median())
    elif product == 'DMSP':
        image = coll.select('stable_lights').median()  # median across available satellite annual composites
    elif product == 'VIIRS_ANNUAL':
        def weighted(i):
            valid = i.select('cf_cvg').gt(0)
            return i.select('avg_rad').multiply(i.select('cf_cvg')).rename('weighted').addBands(
                i.select('cf_cvg')).updateMask(valid)
        sums = coll.map(weighted).sum()
        image = sums.select('weighted').divide(sums.select('cf_cvg')).rename('avg_rad').addBands(
            sums.select('cf_cvg')).updateMask(sums.select('cf_cvg').gt(0))
    else:
        image = coll.select(['avg_rad','cf_cvg']).first()
        image = ee.Image(image).updateMask(ee.Image(image).select('cf_cvg').gt(0))
    if job['variant'] in ('filtered', 'statistics') and product.startswith('VIIRS'):
        image = image.updateMask(image.select('avg_rad').gte(0))
    return image.select(SOURCES[product]['bands']).clip(geometry).toFloat()


def statistics(image, job, geometry):
    import ee
    from .sources import SOURCES
    area = ee.Image.pixelArea()
    valid = image.mask().reduce(ee.Reducer.min())
    area_valid = area.updateMask(valid).rename('valid_area')
    bands = SOURCES[job['product']]['bands']
    weighted = image.multiply(area_valid).rename([b+'_w' for b in bands])
    squares = image.pow(2).multiply(area_valid).rename([b+'_w2' for b in bands])
    sums = image.rename([b+'_sum' for b in bands])
    stack = weighted.addBands(squares).addBands(sums).addBands(area_valid).addBands(area.rename('total_area'))
    scale = job['scale']
    stats = stack.reduceRegion(ee.Reducer.sum(), geometry, crs=job['crs'],
                              crsTransform=[scale,0,0,0,-scale,0], maxPixels=1e13, tileScale=4)
    # Leave raw sufficient statistics in the CSV; local aggregation handles nulls without ee.Number(null).
    properties = dict(ma_tinh=job['province']['ma_tinh'], ten_tinh=job['province']['ten_tinh'],
                      nam=int(job['period'][:4]), thang=int(job['period'][5:]) if len(job['period']) == 7 else 0,
                      nguon_anh=job['product'], period=job['period'], job_id=job['job_id'],
                      algorithm_version=job['algorithm_version'], boundary_sha256=job['boundary_sha256'],
                      scale=scale, crs=job['crs'])
    return ee.FeatureCollection([ee.Feature(None, stats).set(properties)])


def build_export(config, job, boundary):
    import ee
    geometry = ee.Geometry(boundary['geometry'])
    image = composite(config, job, geometry)
    common = dict(description='province_'+job['job_id'], folder=job['folder_name'], fileNamePrefix=job['prefix'])
    if job['kind'] == 'table':
        selectors = ['ma_tinh','ten_tinh','nam','thang','nguon_anh','period','job_id','algorithm_version',
                     'boundary_sha256','scale','crs','valid_area','total_area']
        selectors += [band+suffix for band in SOURCES[job['product']]['bands'] for suffix in ('_w','_w2','_sum')]
        return ee.batch.Export.table.toDrive(collection=statistics(image, job, geometry),
                selectors=selectors, fileFormat='CSV', **common)
    tile = job['tile']
    region = ee.Geometry.Rectangle(tile['bounds'], proj=job['crs'], geodesic=False)
    return ee.batch.Export.image.toDrive(image=image.unmask(-9999, sameFootprint=False), region=region,
            crs=job['crs'], crsTransform=tile['transform'], maxPixels=config['tile_pixels']**2+1,
            fileFormat='GeoTIFF', formatOptions={'cloudOptimized': True, 'noData': -9999}, **common)


def submit_with_request_id(task, request_id):
    """Use supported data export APIs, keeping request identity across a bounded retry."""
    import ee
    from .common import retry
    if task.task_type == ee.batch.Task.Type.EXPORT_IMAGE:
        return retry(lambda: ee.data.exportImage(request_id, task.config))['name']
    return retry(lambda: ee.data.exportTable(request_id, task.config))['name']


def operations():
    import ee
    # getTaskList paginates via the supported EE client implementation.
    return ee.data.getTaskList()
