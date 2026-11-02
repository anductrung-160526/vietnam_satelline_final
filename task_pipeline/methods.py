"""Task 1/2/3 notebook science, adapted from communes to fixed provincial geometry.

Periods: LANDSAT 2004-2014, SENTINEL2 2015-2025 (never Landsat after 2014); DMSP 2004-2013,
VIIRS 2014-2025. Provider fallbacks/window expansion are explicitly recorded.
"""
import calendar
from datetime import datetime,timedelta
from copy import deepcopy
from province_pipeline.sources import SOURCES,BANDS
DAY_BANDS=BANDS+['NDVI','NDBI','MNDWI','BSI']
VIIRS_A='NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG'
VIIRS_B='NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG'


def source_spec(product,period):
    spec=deepcopy(SOURCES[product])
    if product=='SENTINEL2' and int(period[:4])<2019:
        spec['collections']=['COPERNICUS/S2_HARMONIZED']
        spec['unit']='TOA_reflectance_and_dimensionless_indices'
    if product=='VIIRS_MONTHLY':spec['collections']=[VIIRS_A,VIIRS_B]
    return spec


def dates(period,window=0):
    year=int(period[:4])
    if len(period)==4:return f'{year}-01-01',f'{year+1}-01-01'
    month=int(period[5:]);last=calendar.monthrange(year,month)[1]
    # Exact supplied notebooks: EE exclusive end is the LAST calendar day,
    # not first day of next month. This known last-day omission is documented.
    return ((datetime(year,month,1)-timedelta(days=window)).strftime('%Y-%m-%d'),
            (datetime(year,month,last)+timedelta(days=window)).strftime('%Y-%m-%d'))


def collection(product,period,geometry,window=0,collection_id=None):
    import ee
    start,end=dates(period,window)
    ids=[collection_id] if collection_id else source_spec(product,period)['collections']
    out=ee.ImageCollection(ids[0]).filterBounds(geometry).filterDate(start,end)
    for cid in ids[1:]:out=out.merge(ee.ImageCollection(cid).filterBounds(geometry).filterDate(start,end))
    return out


def inventory(job,geometry):
    import ee
    product,period=job['product'],job['period']
    selected=None;window=0
    if product=='VIIRS_MONTHLY':
        # Notebook Task3 fallback is another VIIRS processing product, never another sensor.
        for cid in (VIIRS_A,VIIRS_B):
            col=collection(product,period,geometry,collection_id=cid)
            if col.size().getInfo()>0:selected=col;break
    elif product in ('LANDSAT','SENTINEL2') and job['kind']=='image':
        for window in (0,15,30):
            col=collection(product,period,geometry,window)
            if col.size().getInfo()>0:selected=col;break
    else:
        selected=collection(product,period,geometry)
    if selected is None:
        return dict(status='UNAVAILABLE',count=0,asset_ids=[],product=product,period=period)
    info=ee.Dictionary(dict(count=selected.size(),asset_ids=selected.aggregate_array('system:id'))).getInfo()
    return dict(info,status='AVAILABLE' if info['count'] else 'UNAVAILABLE',product=product,
                period=period,window_days=window,actual_start=dates(period,window)[0],actual_end_exclusive=dates(period,window)[1],
                collections=[cid] if product=='VIIRS_MONTHLY' else source_spec(product,period)['collections'])


def indices(image):
    # Task1 and Task2 apply indices AFTER median, unlike v2's median of scene indices.
    ndvi=image.normalizedDifference(['NIR','RED']).rename('NDVI')
    ndbi=image.normalizedDifference(['SWIR1','NIR']).rename('NDBI')
    mndwi=image.normalizedDifference(['GREEN','SWIR1']).rename('MNDWI')
    bsi=image.expression('((SWIR1+RED)-(NIR+BLUE))/((SWIR1+RED)+(NIR+BLUE))',
        {b:image.select(b) for b in ('SWIR1','RED','NIR','BLUE')}).rename('BSI')
    return image.addBands([ndvi,ndbi,mndwi,bsi])


def s2_mask(image):
    qa=image.select('QA60')
    mask=qa.bitwiseAnd(1<<10).eq(0).And(qa.bitwiseAnd(1<<11).eq(0))
    return image.updateMask(mask).divide(10000).select(['B2','B3','B4','B8','B11','B12'],BANDS)


def composite(config,job,geometry):
    import ee
    ids=job.get('inventory',{}).get('asset_ids',[])
    if not ids:raise ValueError('No persisted source snapshot')
    coll=ee.ImageCollection.fromImages([ee.Image(i) for i in ids])
    p=job['product']
    if p in ('LANDSAT','SENTINEL2'):
        if p=='SENTINEL2':
            if job['kind']=='table':
                filtered=coll.filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',85))
                coll=ee.ImageCollection(ee.Algorithms.If(filtered.size().gt(0),filtered,coll))
            clean=coll.map(s2_mask)
        else:
            from province_pipeline.earth_engine import _landsat
            clean=coll.map(_landsat)
        image=indices(clean.median())
    elif p=='DMSP':
        image=ee.Image(coll.sort('system:index',False).first()).select('stable_lights')
    else:
        image=coll.select(['avg_rad','cf_cvg']).mean()
    return image.clip(geometry).toDouble().set('source_count',coll.size())


def statistics(image,job,geometry):
    import ee
    p=job['product'];bands=source_spec(p,job['period'])['bands']
    scale=50 if p in ('LANDSAT','SENTINEL2') else job['scale']
    kw=dict(geometry=geometry,scale=scale,crs='EPSG:4326',maxPixels=1e13,tileScale=4)
    if p in ('LANDSAT','SENTINEL2'):
        # Same reduceRegions(mean+stdDev,50m,tileScale4,EPSG4326), one province feature.
        reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(),sharedInputs=True)
        stats=image.reduceRegions(ee.FeatureCollection([ee.Feature(geometry)]),reducer,
                                  scale=50,crs='EPSG:4326',tileScale=4).first().toDictionary()
    else:
        reducer=ee.Reducer.sum().combine(ee.Reducer.mean(),sharedInputs=True).combine(
            ee.Reducer.stdDev(),sharedInputs=True).combine(ee.Reducer.min(),sharedInputs=True).combine(
            ee.Reducer.max(),sharedInputs=True).combine(ee.Reducer.count(),sharedInputs=True)
        stats=image.reduceRegion(reducer,**kw)
    # Retain sufficient per-band statistics for validated receiver and old panel helpers.
    area=ee.Image.pixelArea()
    valid=image.select(bands[:6] if p in ('LANDSAT','SENTINEL2') else bands[:1]).mask().reduce(ee.Reducer.min())
    stack=image.multiply(area).rename([b+'_w' for b in bands]).addBands(
        image.pow(2).multiply(area).rename([b+'_w2' for b in bands])).addBands(
        image.rename([b+'_sum' for b in bands])).addBands(
        image.mask().multiply(area).rename([b+'_valid_area' for b in bands])).addBands(
        area.multiply(valid).rename('valid_area')).addBands(area.rename('total_area'))
    sufficient=stack.reduceRegion(ee.Reducer.sum(),**kw)
    # Keep notebook reducer's pixel sums (not a sum on a different projection).
    result=ee.Dictionary(sufficient).combine(stats,overwrite=True)
    if p.startswith(('DMSP','VIIRS')):
        b='stable_lights' if p=='DMSP' else 'avg_rad'
        threshold=job['quality']['lit_threshold_dmsp'] if p=='DMSP' else 1.5
        lit=image.select(b).gte(threshold).rename('is_lit')
        count=lit.reduceRegion(ee.Reducer.sum(),**kw).get('is_lit')
        proxy=image.select(b).updateMask(lit).rename('lit_rad').reduceRegion(ee.Reducer.sum(),**kw).get('lit_rad')
        result=result.set('lit_pixels',count).set('notebook_lit_pop_proxy',proxy).set('notebook_valid_pixels',stats.get(b+'_count'))
        cf=image.select('cf_cvg').reduceRegion(ee.Reducer.mean(),**kw).get('cf_cvg') if p=='VIIRS_MONTHLY' else None
    else:cf=image.get('source_count')
    identity=dict(ma_tinh=job['province']['ma_tinh'],ten_tinh=job['province']['ten_tinh'],
                  nam=int(job['period'][:4]),thang=int(job['period'][5:]) if len(job['period'])==7 else 0,
                  nguon_anh=p,period=job['period'],job_id=job['job_id'],algorithm_version=job['algorithm_version'],
                  boundary_sha256=job['boundary_sha256'],scale=scale,crs='EPSG:4326',
                  province_area=geometry.area(maxError=1),source_observations=cf,
                  actual_source_collections=','.join(job['inventory'].get('collections',[])),
                  qc_status='NOTEBOOK_TASKS',qc_attempts=1)
    return ee.FeatureCollection([ee.Feature(None,result).set(identity)])
