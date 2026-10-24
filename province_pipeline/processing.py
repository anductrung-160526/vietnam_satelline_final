"""V2 quality-aware EE processing. Source products remain immutable; no gap filling."""
from .projection import ee_crs
from .sources import SOURCES


def composite(config, job, geometry):
    if job['quality'].get('processing_mode')=='notebook_tasks':
        from task_pipeline.methods import composite as notebook_composite
        return notebook_composite(config,job,geometry)
    import ee
    from .earth_engine import _landsat, _sentinel, _indices, date_range
    ids = job.get('inventory', {}).get('asset_ids', [])
    if not ids:
        raise ValueError('Missing persisted source inventory')
    coll = ee.ImageCollection.fromImages([ee.Image(asset) for asset in ids])
    q, product = job['quality'], job['product']
    raw=q.get('processing_mode')=='raw_source'
    if product == 'LANDSAT':
        def prepare(img):
            clean = _landsat(img)
            valid = clean.mask().reduce(ee.Reducer.min()).focalMin(
                radius=q['landsat_cloud_buffer_m'], units='meters')
            return _indices(clean.updateMask(valid))
        if raw:
            from .sources import BANDS
            def unfiltered(img):
                modern=ee.List(['LANDSAT_8','LANDSAT_9']).contains(img.get('SPACECRAFT_ID'))
                names=ee.List(ee.Algorithms.If(modern,
                    ['SR_B2','SR_B3','SR_B4','SR_B5','SR_B6','SR_B7'],
                    ['SR_B1','SR_B2','SR_B3','SR_B4','SR_B5','SR_B7']))
                return _indices(img.select(names,BANDS).multiply(0.0000275).add(-0.2))
            processed=coll.map(unfiltered)
        else:
            processed = coll.map(prepare)
    elif product == 'SENTINEL2':
        scores = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED')
        linked = coll.linkCollection(scores, ['cs_cdf'])
        def prepare(img):
            clean = _sentinel(img).updateMask(img.select('cs_cdf').gte(q['sentinel_cloud_score_min']))
            clean = clean.updateMask(img.select('B8A').mask()).updateMask(img.select('B9').mask())
            return _indices(clean.resample('bilinear'))
        if raw:
            from .sources import BANDS
            processed=coll.map(lambda img:_indices(img.select(
                ['B2','B3','B4','B8','B11','B12'],BANDS).multiply(.0001)))
        else:
            processed = linked.map(prepare)
    else:
        band = 'stable_lights' if product == 'DMSP' else 'avg_rad'
        if product == 'DMSP':
            # Deterministic satellite choice, avoiding mixed, uncalibrated satellites in a year.
            chosen = ee.Image(coll.sort('system:index', False).first())
            image = chosen.select('stable_lights')
            observations = chosen.select('cf_cvg')
        else:
            chosen = ee.Image(coll.sort('system:index').first())
            image = chosen.select(['avg_rad','cf_cvg'])
            observations = image.select('cf_cvg')
        if job['variant'] != 'source' and not raw:
            image = image.updateMask(observations.gte(q['min_cloud_free_obs']))
            if product != 'DMSP':
                # Background below zero has no physical radiance meaning; retain valid darkness as zero.
                image = image.addBands(image.select('avg_rad').max(0), overwrite=True)
            if q['mask_fires']:
                start,end = date_range(job['period'])
                fires = ee.ImageCollection('MODIS/061/MOD14A1').filterDate(start,end).filterBounds(geometry)
                # Empty auxiliary coverage is NOT interpreted as proof of no fire.
                fire = ee.Image(ee.Algorithms.If(fires.size().gt(0), fires.select('FireMask').max(),
                    ee.Image.constant(0).updateMask(ee.Image.constant(0))))
                image = image.updateMask(fire.lt(8))
        return image.select(SOURCES[product]['bands']).clip(geometry).toFloat().set(
            'source_observations', observations.reduceRegion(
                ee.Reducer.mean(), geometry, scale=job['scale'], crs=ee_crs(job['crs']),
                maxPixels=1e13, tileScale=4).get('cf_cvg'))
    count = processed.select('BLUE').count()
    image = processed.median()
    if not raw:
        image=image.updateMask(count.gte(q['min_observations_day']))
    return image.select(SOURCES[product]['bands']).clip(geometry).toFloat().set(
        'source_observations', count.reduceRegion(ee.Reducer.mean(), geometry,
            scale=job['scale'], crs=ee_crs(job['crs']), maxPixels=1e13, tileScale=4).get('BLUE'))


def statistics(image, job, geometry):
    if job['quality'].get('processing_mode')=='notebook_tasks':
        from task_pipeline.methods import statistics as notebook_statistics
        return notebook_statistics(image,job,geometry)
    import ee
    from .earth_engine import statistics as legacy
    base = legacy(image,job,geometry).first()
    reducer = ee.Reducer.minMax().combine(ee.Reducer.count(),sharedInputs=True)
    params = dict(geometry=geometry,crs=ee_crs(job['crs']),
                  crsTransform=[job['scale'],0,0,0,-job['scale'],0],maxPixels=1e13,tileScale=4)
    extras = image.reduceRegion(reducer,**params)
    if job['product'].startswith(('DMSP','VIIRS')):
        band = 'stable_lights' if job['product']=='DMSP' else 'avg_rad'
        threshold = job['quality']['lit_threshold_dmsp' if job['product']=='DMSP' else 'lit_threshold_viirs']
        lit = image.select(band).gte(threshold)
        extra_lit = lit.rename('lit_pixels').addBands(
            lit.multiply(ee.Image.pixelArea()).rename('lit_area')).reduceRegion(ee.Reducer.sum(),**params)
        extras = extras.combine(extra_lit)
    if job['quality'].get('processing_mode')=='raw_source':
        bands=SOURCES[job['product']]['bands']
        area=ee.Image.pixelArea()
        stack=image.multiply(area).rename([b+'_w' for b in bands]).addBands(
            image.pow(2).multiply(area).rename([b+'_w2' for b in bands])).addBands(
            image.rename([b+'_sum' for b in bands])).addBands(
            image.mask().multiply(area).rename([b+'_valid_area' for b in bands]))
        primary=bands[:6] if job['product'] in ('LANDSAT','SENTINEL2') else bands[:1]
        valid=image.select(primary).mask().reduce(ee.Reducer.min())
        stack=stack.addBands(area.multiply(valid).rename('valid_area'))
        extras=extras.combine(stack.reduceRegion(ee.Reducer.sum(),**params),overwrite=True)
    properties = dict(province_area=geometry.area(maxError=1),
                      source_observations=image.get('source_observations'))
    return ee.FeatureCollection([base.set(extras).set(properties)])
