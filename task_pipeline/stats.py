"""Monthly province indices computed on Earth Engine at each sensor's native resolution.

No image is downloaded: Earth Engine reduces every composite to a few numbers.

    day   LANDSAT    2004-2025  30 m   QA_PIXEL mask (fill, dilated cloud, cirrus, cloud, cloud
                                       shadow, snow) + saturation -> monthly median
          SENTINEL2  2015-2025  10 m   Cloud Score+ cs_cdf >= 0.60 (clouds AND shadows, whole
                                       archive; QA60 is empty Jan 2022 - Feb 2024) -> monthly median
                                       -> NDVI, NDBI, MNDWI, BSI mean/stdDev, valid share, scenes
    night VIIRS      2014-2025  500 m  same filter as derive.viirs_filtered: cf_cvg=0 -> NoData,
                                       negative -> 0, spike > max(3 x annual median, median+5)
                                       -> annual median; then SOL, mean, stdDev, min, max, count,
                                       lit (>= 1.5 nW) SOL/pixels, cloud-free obs, spikes capped
          DMSP       2004-2013  1 km   stable_lights (NOAA already removes fires, ephemeral
                                       lights and background); same statistics, lit >= threshold
    Not applied by decision (hieu_chinh = CHUA_HIEU_CHINH): DMSP-VIIRS inter-calibration (no
    external harmonised product, no VIIRS 2013), DMSP inter-satellite calibration (the newest
    satellite of a year is used) and saturation correction. thay_doi_ntl therefore never
    compares DMSP with VIIRS: 2014 has no previous-year value.
    Land-cover columns (dt_nong_nghiep ... dt_nn_chuyen_doi) are created empty until the
    classification with reference samples is done.

    python -m task_pipeline.stats --range 1-11 --project vngis-ee-2

Results go to <root>/_control/stats/*.jsonl (one line per province/source/period, so a
rerun only computes what is missing) and are merged into
    <root>/VN_LandCover_Panel_2004_2025/data_processed/day_indices_monthly_ee.csv
    <root>/VN_NTL_Panel_2004_2025/data_processed/ntl_indices_ee.csv
with sol_ntl, mat_do_ntl (SOL per km2) and thay_doi_ntl (% change vs the same month of the
previous year; DMSP vs the previous year).
"""
import argparse
import csv
import json
import logging
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from . import local
from .methods import dates,VIIRS_A,VIIRS_B

RANGES=((1,11),(12,22),(23,33),(34,43),(44,53),(54,63))
SOURCES={  # product: (years, scale m)
    'LANDSAT':(range(2004,2026),30),
    'SENTINEL2':(range(2015,2026),10),
    'VIIRS':(range(2014,2026),500),
    'DMSP':(range(2004,2014),1000),
}
KINDS={'day':('LANDSAT','SENTINEL2'),'night':('VIIRS','DMSP')}
INDICES=('NDVI','NDBI','MNDWI','BSI')
VIIRS_LIT=1.5
# Recorded on every line; lines computed with another method version are recomputed.
METHOD={'LANDSAT':'L2_QA_PIXEL_v1','SENTINEL2':'CLOUDSCOREPLUS_0.60_v1',
        'VIIRS':'VCMSLCFG_FILTERED_v1','DMSP':'STABLE_LIGHTS_v1'}
CS_PLUS='GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'
CS_THRESHOLD=0.60
TILE_SCALES=(4,8,16)
HEAVY=('timed out','memory limit','too many pixels','computation timed out','capacity exceeded')
TRANSIENT=('429','too many','rate limit','quota','503','502','500','unavailable','deadline',
           'connection','reset','aborted','temporarily','internal error','timeout')
STOP=threading.Event()


def periods(product):
    years,_=SOURCES[product]
    if product=='DMSP':return [str(y) for y in years]
    return [f'{y}-{m:02}' for y in years for m in range(1,13)]


def landsat(image):
    from province_pipeline.earth_engine import _landsat
    return _landsat(image)


def sentinel(image):
    """Cloud Score+ (clouds and their shadows), scaled to reflectance.

    The notebook's QA60 mask misses shadows, and QA60 is empty from Jan 2022 to Feb 2024,
    so it would leave those months unmasked. Cloud Score+ covers the whole archive.
    """
    from province_pipeline.sources import BANDS
    import ee
    # A scene without a Cloud Score+ match is dropped (fully masked), never left unmasked.
    clear=ee.Image(ee.Algorithms.If(image.bandNames().contains('cs_cdf'),
                                    image.select('cs_cdf').gte(CS_THRESHOLD),ee.Image(0)))
    return image.updateMask(clear).select(['B2','B3','B4','B8','B11','B12'],BANDS).divide(10000)


def day_request(product,period,geometry,tile_scale):
    """One server-side dictionary: scene count plus mean/stdDev/valid share of each index."""
    import ee
    from .methods import indices
    start,end=dates(period)
    if product=='LANDSAT':
        col=None
        for cid in ('LANDSAT/LT05/C02/T1_L2','LANDSAT/LE07/C02/T1_L2','LANDSAT/LC08/C02/T1_L2','LANDSAT/LC09/C02/T1_L2'):
            part=ee.ImageCollection(cid).filterBounds(geometry).filterDate(start,end)
            col=part if col is None else col.merge(part)
        clean=col.map(landsat)
    else:
        cid='COPERNICUS/S2_SR_HARMONIZED' if int(period[:4])>=2019 else 'COPERNICUS/S2_HARMONIZED'
        col=ee.ImageCollection(cid).filterBounds(geometry).filterDate(start,end)
        clean=col.linkCollection(ee.ImageCollection(CS_PLUS),['cs_cdf']).map(sentinel)
    _,scale=SOURCES[product]
    # A fully masked placeholder keeps the band names when a month has no scene, so the
    # graph is always valid; the n_scenes==0 branch below then reports NO_SCENES.
    from province_pipeline.sources import BANDS
    empty=ee.Image.constant([0]*len(BANDS)).rename(BANDS).toFloat().updateMask(0)
    # Every image is cast to float32 first: Earth Engine only merges collections whose bands
    # have identical types, and Landsat/Sentinel-2 scaling gives varying numeric ranges.
    image=indices(clean.map(lambda i:i.toFloat()).merge(ee.ImageCollection([empty])).median()).select(list(INDICES))
    reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(),sharedInputs=True)
    stats=image.reduceRegion(reducer,geometry=geometry,scale=scale,crs='EPSG:4326',maxPixels=1e13,tileScale=tile_scale)
    # Share of the province with a valid (cloud-free) composite pixel, area-weighted.
    area=ee.Image.pixelArea()
    valid=area.updateMask(image.select('NDVI').mask()).rename('valid_m2').addBands(area.rename('total_m2'))
    cover=valid.reduceRegion(ee.Reducer.sum(),geometry=geometry,scale=scale,crs='EPSG:4326',maxPixels=1e13,tileScale=tile_scale)
    return ee.Dictionary(ee.Algorithms.If(col.size().gt(0),
        ee.Dictionary(stats).combine(cover).set('n_scenes',col.size()),
        ee.Dictionary({'n_scenes':0})))


def night_request(product,period,geometry,tile_scale,dmsp_threshold):
    import ee
    start,end=dates(period)
    if product=='VIIRS':
        a=ee.ImageCollection(VIIRS_A).filterBounds(geometry).filterDate(start,end)
        b=ee.ImageCollection(VIIRS_B).filterBounds(geometry).filterDate(start,end)
        col=ee.ImageCollection(ee.Algorithms.If(a.size().gt(0),a,b))
        source=ee.String(ee.Algorithms.If(a.size().gt(0),'VCMSLCFG',ee.Algorithms.If(b.size().gt(0),'VCMCFG','none')))
        empty=ee.Image.constant([0,0]).rename(['avg_rad','cf_cvg']).toFloat().updateMask(0)
        image=col.select(['avg_rad','cf_cvg']).map(lambda i:i.toFloat()).merge(ee.ImageCollection([empty])).mean()
        # Same filter as derive.viirs_filtered (the image pipeline), on the server:
        # no cloud-free observation -> NoData; negative -> 0; a spike (fire, boat, flare)
        # above max(3 x the pixel's annual median, median + 5) -> that annual median.
        def clean(img):
            return img.select('avg_rad').max(0).updateMask(img.select('cf_cvg').gt(0)).toFloat()
        year=period[:4]
        annual=ee.ImageCollection(VIIRS_A).filterBounds(geometry).filterDate(f'{year}-01-01',f'{int(year)+1}-01-01')
        median=annual.map(clean).merge(ee.ImageCollection([empty.select('avg_rad')])).median()
        rad=clean(image)
        spike=rad.gt(median.multiply(3).max(median.add(5)))
        rad=rad.where(spike,median)
        threshold=VIIRS_LIT
    else:
        col=ee.ImageCollection('NOAA/DMSP-OLS/NIGHTTIME_LIGHTS').filterBounds(geometry).filterDate(start,end)
        # Several satellites can cover one year: the newest one, as in the image pipeline.
        empty=ee.Image.constant(0).rename('stable_lights').toFloat().updateMask(0)
        image=ee.Image(ee.Algorithms.If(col.size().gt(0),col.sort('system:index',False).first(),empty))
        source=ee.Algorithms.If(col.size().gt(0),image.get('system:index'),'none')
        rad=image.select('stable_lights');threshold=dmsp_threshold
    _,scale=SOURCES[product]
    kw=dict(geometry=geometry,scale=scale,crs='EPSG:4326',maxPixels=1e13,tileScale=tile_scale)
    rad=rad.rename('rad')
    reducer=ee.Reducer.sum().combine(ee.Reducer.mean(),sharedInputs=True).combine(
        ee.Reducer.stdDev(),sharedInputs=True).combine(ee.Reducer.min(),sharedInputs=True).combine(
        ee.Reducer.max(),sharedInputs=True).combine(ee.Reducer.count(),sharedInputs=True)
    stats=ee.Dictionary(rad.reduceRegion(reducer,**kw))
    lit=rad.gte(threshold)
    stats=stats.combine(rad.updateMask(lit).rename('lit_sol').addBands(lit.rename('lit_pixels'))
                        .reduceRegion(ee.Reducer.sum(),**kw))
    if product=='VIIRS':
        stats=stats.combine(image.select('cf_cvg').rename('cf_cvg_mean').reduceRegion(ee.Reducer.mean(),**kw))
        stats=stats.combine(spike.rename('spikes_capped').reduceRegion(ee.Reducer.sum(),**kw))
    return ee.Dictionary(ee.Algorithms.If(col.size().gt(0),
        stats.set('n_images',col.size()).set('source_collection',source),
        ee.Dictionary({'n_images':0})))


def compute(product,period,province,geometry,dmsp_threshold,attempts=6):
    """getInfo with transient retries and tileScale escalation for heavy provinces."""
    import ee
    level=0;error=None
    for attempt in range(attempts):
        if STOP.is_set():return None
        tile_scale=TILE_SCALES[level]
        try:
            if product in KINDS['day']:
                request=day_request(product,period,geometry,tile_scale)
            else:
                request=night_request(product,period,geometry,tile_scale,dmsp_threshold)
            values=request.getInfo()
            return dict(values,tile_scale=tile_scale)
        except ee.EEException as e:
            error=str(e);low=error.lower()
            if any(s in low for s in HEAVY) and level<len(TILE_SCALES)-1:
                level+=1;continue
            if not any(s in low for s in TRANSIENT):break
        except Exception as e:  # network
            error=f'{type(e).__name__}: {e}'
        time.sleep(min(120,5*2**attempt))
    return dict(error=(error or 'unknown')[:300])


def row(product,period,province,area_km2,values):
    base=dict(ma_tinh=province['ma_tinh'],ten_tinh=province['ten_tinh'],nam=int(period[:4]),
              thang=int(period[5:]) if len(period)==7 else 0,nguon_anh=product,period=period,
              scale_m=SOURCES[product][1],dien_tich_km2=round(area_km2,4),tile_scale=values.get('tile_scale'),
              phuong_phap=METHOD[product],hieu_chinh='CHUA_HIEU_CHINH' if product in KINDS['night'] else None)
    if 'error' in values:return dict(base,status='FAILED',error=values['error'])
    if product in KINDS['day']:
        if not values.get('n_scenes'):return dict(base,status='NO_SCENES',n_scenes=0)
        out=dict(base,status='OK',n_scenes=values['n_scenes'])
        for i in INDICES:
            out[f'{i}_mean']=values.get(f'{i}_mean');out[f'{i}_stdDev']=values.get(f'{i}_stdDev')
        total=values.get('total_m2') or 0
        out['ty_le_pixel_hop_le']=round(100*(values.get('valid_m2') or 0)/total,3) if total else None
        if out['NDVI_mean'] is None:out['status']='NO_VALID_PIXELS'
        return out
    if not values.get('n_images'):return dict(base,status='NO_IMAGES',n_images=0)
    sol=values.get('rad_sum')
    return dict(base,status='OK',n_images=values['n_images'],source_collection=values.get('source_collection'),
                sol_ntl=sol,mat_do_ntl=(sol/area_km2 if sol is not None and area_km2 else None),
                rad_mean=values.get('rad_mean'),rad_stdDev=values.get('rad_stdDev'),rad_min=values.get('rad_min'),
                rad_max=values.get('rad_max'),pixel_count=values.get('rad_count'),
                lit_sol=values.get('lit_sol'),lit_pixels=values.get('lit_pixels'),
                lit_threshold=VIIRS_LIT if product=='VIIRS' else None,cf_cvg_mean=values.get('cf_cvg_mean'),
                spikes_capped=values.get('spikes_capped'))


def load_done(path):
    """Keys already computed with the current method (FAILED rows, lines of an older method
    and periods no longer in scope are recomputed or dropped). Torn last lines are ignored."""
    done={}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:rec=json.loads(line)
            except ValueError:continue
            product=rec.get('nguon_anh')
            if (rec.get('status')!='FAILED' and product in METHOD and rec.get('phuong_phap')==METHOD[product]
                    and rec.get('period') in periods(product)):
                done[(rec['ma_tinh'],product,rec['period'])]=rec
    return done


# Codebook land-cover variables (ha / %); empty until the 5-class classification exists.
LANDCOVER_COLUMNS=['dt_nong_nghiep','dt_do_thi','dt_rung','dt_mat_nuoc','dt_dat_khac',
                   'ty_le_nong_nghiep','dt_nn_chuyen_doi']
DAY_COLUMNS=['ma_tinh','ten_tinh','nam','thang','nguon_anh','period','scale_m','status','n_scenes',
             *[f'{i}_{s}' for i in INDICES for s in ('mean','stdDev')],'ty_le_pixel_hop_le','dien_tich_km2',
             'phuong_phap','tile_scale',*LANDCOVER_COLUMNS]
NTL_COLUMNS=['ma_tinh','ten_tinh','nam','thang','nguon_anh','period','scale_m','status','n_images','source_collection',
              'sol_ntl','mat_do_ntl','thay_doi_ntl','rad_mean','rad_stdDev','rad_min','rad_max','pixel_count',
              'lit_sol','lit_pixels','lit_threshold','cf_cvg_mean','spikes_capped','dien_tich_km2',
              'phuong_phap','hieu_chinh','tile_scale']


def merge(root):
    """Union of every range's lines -> the two CSVs (atomic replace; safe with 6 writers)."""
    from province_pipeline.sources import NTL_PACKAGE,DAY_PACKAGE
    records={}
    for path in sorted((Path(root)/'_control'/'stats').glob('*.jsonl')):
        for key,rec in load_done(path).items():records[key]=rec
    day=[r for r in records.values() if r['nguon_anh'] in KINDS['day']]
    ntl=[r for r in records.values() if r['nguon_anh'] in KINDS['night']]
    by_key={(r['ma_tinh'],r['nguon_anh'],r['nam'],r['thang']):r for r in ntl}
    for r in ntl:
        prev=by_key.get((r['ma_tinh'],r['nguon_anh'],r['nam']-1,r['thang']))
        if r.get('sol_ntl') is not None and prev and prev.get('sol_ntl'):
            r['thay_doi_ntl']=100*(r['sol_ntl']-prev['sol_ntl'])/prev['sol_ntl']
    for package,name,rows,columns in ((DAY_PACKAGE,'day_indices_monthly_ee.csv',day,DAY_COLUMNS),
                                      (NTL_PACKAGE,'ntl_indices_ee.csv',ntl,NTL_COLUMNS)):
        out=Path(root)/package/'data_processed'/name;out.parent.mkdir(parents=True,exist_ok=True)
        rows=sorted(rows,key=lambda r:(r['ma_tinh'],r['nguon_anh'],r['period']))
        tmp=out.with_name(out.name+f'.{os.getpid()}.tmp')
        with tmp.open('w',newline='',encoding='utf-8-sig') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
        for _ in range(10):
            try:tmp.replace(out);break
            except PermissionError:time.sleep(1)   # another range or Excel has it open
        else:
            tmp.unlink(missing_ok=True);logging.warning('Could not replace %s (open in Excel?); next merge retries',out)
    return len(day),len(ntl)


def main():
    parser=argparse.ArgumentParser(description='Monthly indices on Earth Engine at native resolution; no images')
    parser.add_argument('--range',required=True,choices=[f'{a}-{b}' for a,b in RANGES])
    parser.add_argument('--project');parser.add_argument('--ee-key')
    parser.add_argument('--root',default=r'E:\SatelliteData')
    parser.add_argument('--kinds',default='night,day',help='night,day (order = run order)')
    parser.add_argument('--workers',type=int,default=8,help='concurrent Earth Engine requests')
    parser.add_argument('--merge-only',action='store_true',help='only rebuild the CSVs from finished lines')
    args=parser.parse_args();logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    if args.merge_only:
        print('rows (day, night):',merge(args.root));return
    c,root,control=local.prepare('full',None,args.root,args.project,args.range)
    from province_pipeline.prepare_gadm import prepare as prepare_boundaries
    from province_pipeline.boundaries import load_boundaries
    if not Path(c['boundaries']).exists() or not Path(c['boundary_metadata']).exists():prepare_boundaries(c)
    boundaries,_=load_boundaries(c)
    from province_pipeline.earth_engine import initialize
    initialize(c,local.credentials(args.ee_key))
    import ee
    from shapely.geometry import shape
    from rasterio.warp import transform_geom
    print('Earth Engine project:',c['project'],'| range',args.range,'| workers',args.workers)
    signal.signal(signal.SIGINT,lambda *_:STOP.set());signal.signal(signal.SIGTERM,lambda *_:STOP.set())
    threshold=c['quality'].get('lit_threshold_dmsp',5)
    store=Path(root)/'_control'/'stats';store.mkdir(parents=True,exist_ok=True)
    for kind in [k.strip() for k in args.kinds.split(',') if k.strip()]:
        products=KINDS[kind]
        path=store/f"{kind}_{args.range.replace('-','_')}.jsonl";done=load_done(path)
        tasks=[]
        for province in c['task_scope']['provinces']:
            boundary=boundaries[province['ma_tinh']]['geometry']
            # Natural area in km2 on an equal-area projection (EASE-Grid 2.0 global).
            area=shape(transform_geom('EPSG:4326','EPSG:6933',boundary)).area/1e6
            geometry=ee.Geometry(boundary)
            for product in products:
                for period in periods(product):
                    if (province['ma_tinh'],product,period) not in done:
                        tasks.append((product,period,province,geometry,area))
        total=len(tasks);print(f'[{kind}] {total} to compute ({len(done)} already done)')
        lock=threading.Lock();finished=0;failed=0;began=time.monotonic()
        with path.open('a',encoding='utf-8') as stream,ThreadPoolExecutor(args.workers) as pool:
            futures={pool.submit(compute,p,per,prov,g,threshold):(p,per,prov,area) for p,per,prov,g,area in tasks}
            for future in as_completed(futures):
                product,period,province,area=futures[future];values=future.result()
                if values is None:continue
                rec=row(product,period,province,area,values)
                with lock:
                    stream.write(json.dumps(rec,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno())
                    finished+=1;failed+=rec['status']=='FAILED'
                if rec['status']=='FAILED':
                    logging.warning('FAILED %s %s %s: %s',province['ma_tinh'],product,period,rec['error'][:160])
                if finished%50==0 or finished==total:
                    rate=finished/max(1,time.monotonic()-began)*3600
                    left=(total-finished)/rate if rate else 0
                    print(f'[{kind}] {finished}/{total} done, {failed} failed, {rate:.0f}/h, ~{left:.1f} h left')
                if finished%500==0:merge(root)
                if STOP.is_set():
                    for f in futures:f.cancel()
                    break
        print('rows (day, night):',merge(root))
        if STOP.is_set():print('Stopped; run the same command again to continue.');raise SystemExit(130)
    failed=set();ok=set()
    for p in store.glob(f"*_{args.range.replace('-','_')}.jsonl"):
        ok|=set(load_done(p))
        for line in p.read_text(encoding='utf-8').splitlines():
            try:rec=json.loads(line)
            except ValueError:continue
            if rec.get('status')=='FAILED':failed.add((rec['ma_tinh'],rec['nguon_anh'],rec['period']))
    left=len(failed-ok)
    print(f'Finished with {left} FAILED item(s); run the same command again to retry them.' if left else 'Finished: all items computed.')


if __name__=='__main__':main()
