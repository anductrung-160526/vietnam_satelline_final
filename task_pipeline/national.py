"""Annual whole-Vietnam composites, downloaded straight to drive E as resumable tiles.

    day   LANDSAT    2004-2014  30 m   QA_PIXEL mask (cloud, shadow, cirrus, snow, saturation)
          SENTINEL2  2015-2025  10 m   Cloud Score+ cs_cdf >= 0.60 (clouds and shadows)
                                       -> per-pixel median of the WHOLE calendar year,
                                       6 bands BLUE..SWIR2, int16 = round(reflectance x 10000)
    night VIIRS      2014-2025  500 m  median of the 12 monthly images after cf_cvg=0 -> NoData
                                       and negative -> 0 (float32, nW/cm2/sr)
          DMSP       2004-2013  1 km   stable_lights of the newest satellite of the year

    python -m task_pipeline.national --product LANDSAT --years 2004-2014 --project vngis-ee-2

Each year is a grid of tiles under
    <root>/<package>/raw_data/<DAY|NTL>/<PRODUCT>/VN_<PRODUCT>_<year>/tiles/
plus VN_<PRODUCT>_<year>.vrt, which GIS software opens as ONE national image. A tile is
written only after Earth Engine returned and it was verified, so a rerun downloads only the
missing tiles. A tile Earth Engine rejects as too heavy is split into quarters (sub-tiles).
Province cutting happens later, locally, from the .vrt.
"""
import argparse
import json
import logging
import math
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from xml.sax.saxutils import escape
from . import local
from . import province_image
from .province_image import DAY_TIFF_BANDS,size_error

# Project rule (CLAUDE.md): one day source per year, Landsat only up to 2014.
PRODUCTS={
    'LANDSAT':dict(years=range(2004,2015),scale=30,kind='DAY',dtype='int16',bands=DAY_TIFF_BANDS),
    'SENTINEL2':dict(years=range(2015,2026),scale=10,kind='DAY',dtype='int16',bands=DAY_TIFF_BANDS),
    'VIIRS':dict(years=range(2014,2026),scale=500,kind='NTL',dtype='float32',bands=['avg_rad']),
    'DMSP':dict(years=range(2004,2014),scale=1000,kind='NTL',dtype='float32',bands=['stable_lights']),
}
METHOD='ANNUAL_FULLYEAR_v1'
TILE_BYTES=24_000_000      # below Earth Engine's 32 MB per direct download
MIN_TILE=128
DEG=111319.49079327358     # metres per degree (EPSG:4326 grid, as in the province pipeline)
STOP=threading.Event()


def tile_pixels(product):
    p=PRODUCTS[product];per=len(p['bands'])*(2 if p['dtype']=='int16' else 4)
    return min(4096,int(math.sqrt(TILE_BYTES/per))//256*256)


def national_geometry(boundaries):
    """Union of the 63 provinces (exact, for skipping tiles) and a light version for Earth Engine."""
    from shapely.geometry import shape
    from shapely.ops import unary_union
    exact=unary_union([shape(b['geometry']) for b in boundaries.values()])
    # ~500 m buffer so coastlines and borders are never shaved by the simplification.
    light=exact.buffer(0.005).simplify(0.002)
    return exact,light


def plan(product,bounds):
    """National grid aligned to whole pixels, cut into tile windows (row, col, width, height)."""
    resolution=PRODUCTS[product]['scale']/DEG
    g=province_image.grid(bounds,resolution)
    n=tile_pixels(product)
    tiles=[(r,c,min(n,g['width']-c),min(n,g['height']-r)) for r in range(0,g['height'],n) for c in range(0,g['width'],n)]
    return g,resolution,tiles


def tile_bounds(g,resolution,col,row,width,height):
    x0=g['transform'][2]+col*resolution;y1=g['transform'][5]-row*resolution
    return [x0,y1-height*resolution,x0+width*resolution,y1]


def year_image(product,year,region):
    """Server-side annual composite (only its graph; nothing is computed until a download)."""
    import ee
    p=PRODUCTS[product];start,end=f'{year}-01-01',f'{year+1}-01-01'
    if product in ('LANDSAT','SENTINEL2'):
        from province_pipeline.sources import BANDS
        if product=='LANDSAT':
            from province_pipeline.earth_engine import _landsat
            col=None
            for cid in ('LANDSAT/LT05/C02/T1_L2','LANDSAT/LE07/C02/T1_L2','LANDSAT/LC08/C02/T1_L2','LANDSAT/LC09/C02/T1_L2'):
                part=ee.ImageCollection(cid).filterBounds(region).filterDate(start,end)
                col=part if col is None else col.merge(part)
            clean=col.map(_landsat)
        else:
            from .stats import sentinel,CS_PLUS
            cid='COPERNICUS/S2_SR_HARMONIZED' if year>=2019 else 'COPERNICUS/S2_HARMONIZED'
            col=ee.ImageCollection(cid).filterBounds(region).filterDate(start,end)
            clean=col.linkCollection(ee.ImageCollection(CS_PLUS),['cs_cdf']).map(sentinel)
        empty=ee.Image.constant([0]*len(BANDS)).rename(BANDS).toFloat().updateMask(0)
        image=clean.map(lambda i:i.toFloat()).merge(ee.ImageCollection([empty])).median().select(p['bands'])
        image=province_image.to_int16(image)
    elif product=='VIIRS':
        from .methods import VIIRS_A
        def cleaned(img):
            return img.select('avg_rad').max(0).updateMask(img.select('cf_cvg').gt(0)).toFloat()
        empty=ee.Image.constant(0).rename('avg_rad').toFloat().updateMask(0)
        col=ee.ImageCollection(VIIRS_A).filterDate(start,end)
        image=col.map(cleaned).merge(ee.ImageCollection([empty])).median().rename('avg_rad').toFloat()
    else:
        col=ee.ImageCollection('NOAA/DMSP-OLS/NIGHTTIME_LIGHTS').filterDate(start,end)
        empty=ee.Image.constant(0).rename('stable_lights').toFloat().updateMask(0)
        image=ee.Image(ee.Algorithms.If(col.size().gt(0),col.sort('system:index',False).first(),empty))
        image=image.select('stable_lights').toFloat()
    return image.clip(region)


def tile_name(row,col,suffix=''):
    return f'r{row:06d}_c{col:06d}{suffix}.tif'


def download(image,job,path,attempts=4):
    """Exact-grid GeoTIFF download with a long read timeout (an annual composite is computed
    while the URL is read) and Earth Engine's own error text kept, so 'too heavy' is visible."""
    import requests
    import rasterio
    from affine import Affine
    from province_pipeline.projection import ee_crs
    t=job['tile']
    params=dict(crs=ee_crs(job['crs']),crs_transform=t['transform'],dimensions=[t['width'],t['height']],
                format='GEO_TIFF',filePerBand=False)
    image=image.unmask(-9999,sameFootprint=False)
    image=image.toInt16() if job['dtype']=='int16' else image.toFloat()
    for attempt in range(attempts):
        try:
            url=image.getDownloadURL(params)
            with requests.get(url,stream=True,timeout=(30,900)) as response:
                if response.status_code in (429,500,502,503,504) and attempt<attempts-1:
                    time.sleep(min(60,5*2**attempt));continue
                if response.status_code!=200:
                    try:message=response.json()['error']['message']
                    except Exception:message=response.text[:300]
                    raise RuntimeError(f'Earth Engine HTTP {response.status_code}: {message}')
                with path.open('wb') as stream:
                    for block in response.iter_content(1024*1024):stream.write(block)
            break
        except requests.RequestException as error:
            if isinstance(error,requests.ReadTimeout):
                raise RuntimeError('Earth Engine computation timed out (ReadTimeout)') from None   # heavy: split
            if attempt==attempts-1:raise RuntimeError(f'Earth Engine download network failure: {type(error).__name__}') from None
            time.sleep(min(60,5*2**attempt))
    with rasterio.open(path,'r+') as ds:
        if (ds.width,ds.height,ds.count)!=(t['width'],t['height'],len(job['bands'])) or not ds.transform.almost_equals(Affine(*t['transform'])):
            raise RuntimeError('Earth Engine returned a different tile grid/band layout')
        ds.nodata=-9999
        for i,name in enumerate(job['bands'],1):ds.set_band_description(i,name)


def on_disk(path):
    """True if the file exists and the file system can read it. A file the disk reports as
    corrupted (WinError 1392 after an unplug or power loss) counts as missing."""
    try:
        return path.exists() and path.stat().st_size>0
    except OSError as error:
        logging.warning('Unreadable file on disk, it will be downloaded again: %s (%s)',path.name,error)
        return False


def usable_path(path):
    """Where to write a tile: its own name, or, if a corrupted file that Windows refuses to
    delete sits there, the same name with a 'b' suffix (the VRT lists whatever was written)."""
    try:
        path.exists() and path.stat()
        return path
    except OSError:
        try:
            path.unlink();return path
        except OSError:
            return path.with_name(path.stem+'b.tif')


def fetch_tile(image,product,g,resolution,row,col,width,height,folder,fetch=None,suffix=''):
    """Download one window; on a 'too heavy' error split it into 4 sub-tiles. Returns file names."""
    fetch=fetch or download
    p=PRODUCTS[product];path=folder/tile_name(row,col,suffix)
    if on_disk(path):return [path.name]
    alternate=path.with_name(path.stem+'b.tif')
    if on_disk(alternate):return [alternate.name]
    path=usable_path(path)
    bounds=tile_bounds(g,resolution,col,row,width,height)
    job=dict(scale=p['scale'],grid_resolution=resolution,crs='EPSG:4326',bands=p['bands'],dtype=p['dtype'],
             tile=dict(bounds=bounds,transform=[resolution,0,bounds[0],0,-resolution,bounds[3]],width=width,height=height),
             reserved_bytes=2*width*height*len(p['bands'])*(2 if p['dtype']=='int16' else 4)+1024**2)
    tmp=folder/(path.stem+'.part.tif')
    try:
        fetch(image,job,tmp)
    except Exception as error:
        tmp.unlink(missing_ok=True)
        heavy=size_error(error) or any(s in str(error).lower() for s in ('deadline','timed out','readtimeout'))
        if not heavy or max(width,height)<=MIN_TILE:raise
        w=(width+1)//2;h=(height+1)//2;names=[]
        for i,(r,hh) in enumerate(((row,h),(row+h,height-h))):
            for j,(c,ww) in enumerate(((col,w),(col+w,width-w))):
                if ww>0 and hh>0:
                    names+=fetch_tile(image,product,g,resolution,r,c,ww,hh,folder,fetch,suffix=f'{suffix}_{i}{j}')
        return names
    compress(tmp,p['dtype'])
    tmp.replace(path)
    return [path.name]


def compress(path,dtype):
    """Rewrite in place: lossless ZSTD + predictor, internal tiles; pixels unchanged."""
    import rasterio
    out=path.with_name(path.stem+'.z.tif')
    with rasterio.open(path) as src:
        profile=src.profile.copy()
        profile.update(driver='GTiff',compress='ZSTD',zstd_level=9,predictor=2 if dtype=='int16' else 3,
                       tiled=True,blockxsize=512,blockysize=512,nodata=-9999)
        for key in ('photometric',):profile.pop(key,None)
        with rasterio.open(out,'w',**profile) as dst:
            dst.write(src.read())
            for b in range(src.count):dst.set_band_description(b+1,src.descriptions[b])
            dst.update_tags(**src.tags())
    out.replace(path)


def write_vrt(product,year,folder,g,resolution,tiles):
    """One virtual national mosaic over every tile file (all on the same pixel grid)."""
    import rasterio
    p=PRODUCTS[product];x0,y1=g['transform'][2],g['transform'][5]
    gdal_type={'int16':'Int16','float32':'Float32'}[p['dtype']]
    wkt=rasterio.crs.CRS.from_epsg(4326).to_wkt()
    sources={b:[] for b in range(len(p['bands']))}
    for name in sorted(tiles):
        with rasterio.open(folder/'tiles'/name) as ds:
            col=round((ds.transform.c-x0)/resolution);row=round((y1-ds.transform.f)/resolution)
            for b in range(len(p['bands'])):
                sources[b].append(f'      <ComplexSource><SourceFilename relativeToVRT="1">tiles/{escape(name)}</SourceFilename>'
                                  f'<SourceBand>{b+1}</SourceBand><SrcRect xOff="0" yOff="0" xSize="{ds.width}" ySize="{ds.height}"/>'
                                  f'<DstRect xOff="{col}" yOff="{row}" xSize="{ds.width}" ySize="{ds.height}"/>'
                                  f'<NODATA>-9999</NODATA></ComplexSource>')
    bands=''.join(f'  <VRTRasterBand dataType="{gdal_type}" band="{b+1}">\n'
                  f'    <Description>{p["bands"][b]}</Description>\n    <NoDataValue>-9999</NoDataValue>\n'
                  +'\n'.join(sources[b])+'\n  </VRTRasterBand>\n' for b in range(len(p['bands'])))
    meta=dict(SOURCE=product,YEAR=str(year),METHOD=METHOD,SCALE_M=str(p['scale']),
              VALUE='int16 = reflectance x 10000' if p['dtype']=='int16' else ('nW/cm2/sr' if product=='VIIRS' else 'DN 0-63'))
    items=''.join(f'    <MDI key="{k}">{escape(v)}</MDI>\n' for k,v in meta.items())
    xml=(f'<VRTDataset rasterXSize="{g["width"]}" rasterYSize="{g["height"]}">\n'
         f'  <SRS>{escape(wkt)}</SRS>\n  <GeoTransform>{x0!r}, {resolution!r}, 0.0, {y1!r}, 0.0, {-resolution!r}</GeoTransform>\n'
         f'  <Metadata>\n{items}  </Metadata>\n{bands}</VRTDataset>\n')
    target=folder/f'VN_{product}_{year}.vrt';tmp=target.with_suffix('.vrt.tmp')
    tmp.write_text(xml,encoding='utf-8');tmp.replace(target)
    return target


def run_year(product,year,root,boundaries,workers,fetch=None,image=None,pause_seconds=300,max_idle_rounds=6,shard=(0,1)):
    from shapely.geometry import box
    from shapely.prepared import prep
    from province_pipeline.sources import NTL_PACKAGE,DAY_PACKAGE
    p=PRODUCTS[product]
    if year not in p['years']:raise SystemExit(f'{product} is only used for {p["years"][0]}-{p["years"][-1]} (project rule)')
    package=DAY_PACKAGE if p['kind']=='DAY' else NTL_PACKAGE
    folder=Path(root)/package/'raw_data'/p['kind']/product/f'VN_{product}_{year}'
    (folder/'tiles').mkdir(parents=True,exist_ok=True)
    exact,light=national_geometry(boundaries)
    g,resolution,tiles=plan(product,exact.bounds)
    inside=prep(exact)
    every=[t for t in tiles if inside.intersects(box(*tile_bounds(g,resolution,t[1],t[0],t[2],t[3])))]
    # --shard i/n: this process takes every n-th tile, so n projects share one year.
    index,count=shard
    todo=every[index::count]
    if image is None:
        import ee
        image=year_image(product,year,ee.Geometry(json.loads(json.dumps(light.__geo_interface__))))
    state=folder/('tiles.json' if count==1 else f'tiles_{index+1}of{count}.json')
    saved=json.loads(state.read_text()) if state.exists() else {}
    # files: every tile file on disk (feeds the VRT); complete: top-level tiles fully done
    # (a split tile counts only when ALL its sub-tiles arrived, so nothing is left out).
    done={n for n in saved.get('files',[]) if on_disk(folder/'tiles'/n)}
    complete={k for k in saved.get('complete',[]) if f'r{int(k.split("_")[0]):06d}_c{int(k.split("_")[1]):06d}' in
              {n[:15] for n in done}}
    print(f'{product} {year}: grid {g["width"]} x {g["height"]} px at {p["scale"]} m, '
          f'{len(every)} tiles over Vietnam ({len(tiles)-len(every)} empty skipped), tile {tile_pixels(product)} px'
          +(f'; shard {index+1}/{count} takes {len(todo)}' if count>1 else ''))
    lock=threading.Lock()
    def save():
        tmp=state.with_suffix('.tmp')
        tmp.write_text(json.dumps(dict(product=product,year=year,method=METHOD,files=sorted(done),complete=sorted(complete))))
        tmp.replace(state)
    # Restricted mode answers slowly and often refuses (429): keep retrying the missing tiles
    # in rounds, pausing longer after a round with no progress, instead of giving up.
    idle=0;round_no=0
    while not STOP.is_set():
        remaining=[t for t in todo if f'{t[0]}_{t[1]}' not in complete]
        if not remaining:break
        round_no+=1
        print(f'  round {round_no}: {len(todo)-len(remaining)} tiles done, {len(remaining)} to download',flush=True)
        finished=0;failed=0;began=time.monotonic()
        with ThreadPoolExecutor(workers) as pool:
            futures={pool.submit(fetch_tile,image,product,g,resolution,r,c,w,h,folder/'tiles',fetch):(r,c) for r,c,w,h in remaining}
            for future in as_completed(futures):
                try:
                    names=future.result()
                except Exception as error:
                    failed+=1;logging.warning('Tile %s failed: %s',futures[future],str(error)[:200])
                    if STOP.is_set():break
                    continue
                with lock:
                    done.update(names);complete.add('%d_%d'%futures[future]);finished+=1
                    if finished%20==0 or finished==len(remaining):
                        save();rate=finished/max(1,time.monotonic()-began)*3600
                        print(f'  {product} {year}: {finished}/{len(remaining)} tiles, {failed} failed, '
                              f'{rate:.0f} tiles/h, ~{(len(remaining)-finished)/rate if rate else 0:.1f} h left',flush=True)
                if STOP.is_set():
                    for f in futures:f.cancel()
                    break
        save()
        if not failed:break
        idle=idle+1 if finished==0 else 0
        if idle>=max_idle_rounds:
            print(f'  {product} {year}: {failed} tiles still failing after {idle} rounds without progress; '
                  'run the same command again later.')
            return False
        wait=pause_seconds*(idle+1)
        print(f'  {failed} tiles failed this round; retrying in {wait//60} min',flush=True)
        STOP.wait(wait)
    if STOP.is_set():
        print(f'  {product} {year}: stopped; run the same command again to continue.')
        return False
    # The national VRT needs every shard: union of all state files of this year.
    files=set();finished_tiles=set()
    for path in folder.glob('tiles*.json'):
        try:other=json.loads(path.read_text())
        except ValueError:continue
        files|={n for n in other.get('files',[]) if on_disk(folder/'tiles'/n)}
        finished_tiles|=set(other.get('complete',[]))
    missing=[t for t in every if f'{t[0]}_{t[1]}' not in finished_tiles]
    if missing:
        print(f'  {product} {year}: this shard is done; {len(missing)} tiles of other shards still missing. '
              'The VRT is written by whichever shard finishes last.')
        return True
    vrt=write_vrt(product,year,folder,g,resolution,files)
    print(f'  {product} {year}: COMPLETE -> {vrt}')
    return True


def merge_year(product,year,root,overviews=False,strip_rows=512,strip_cols=8192):
    """Write the year's VRT as ONE GeoTIFF next to it: same pixels, lossless ZSTD, internal
    512 px blocks, BigTIFF. Written strip by strip (bounded memory), then renamed into place,
    so an interrupted merge never leaves a half file under the final name."""
    import numpy as np
    import rasterio
    from rasterio.windows import Window
    from province_pipeline.sources import NTL_PACKAGE,DAY_PACKAGE
    p=PRODUCTS[product]
    package=DAY_PACKAGE if p['kind']=='DAY' else NTL_PACKAGE
    folder=Path(root)/package/'raw_data'/p['kind']/product/f'VN_{product}_{year}'
    vrt=folder/f'VN_{product}_{year}.vrt';target=folder/f'VN_{product}_{year}.tif'
    if not vrt.exists():
        print(f'{product} {year}: no VRT yet (download not complete) - skipped');return False
    if target.exists() and target.stat().st_mtime>=vrt.stat().st_mtime:
        print(f'{product} {year}: {target.name} already up to date');return True
    tmp=target.with_name(target.stem+'.merging.tif')
    began=time.monotonic()
    with rasterio.open(vrt) as src:
        profile=dict(driver='GTiff',width=src.width,height=src.height,count=src.count,dtype=src.dtypes[0],
                     crs=src.crs,transform=src.transform,nodata=-9999,compress='ZSTD',zstd_level=9,
                     predictor=2 if src.dtypes[0]=='int16' else 3,tiled=True,blockxsize=512,blockysize=512,
                     BIGTIFF='YES',NUM_THREADS='ALL_CPUS')
        with rasterio.open(tmp,'w',**profile) as dst:
            for b in range(src.count):dst.set_band_description(b+1,src.descriptions[b])
            dst.update_tags(**src.tags(),MERGED_FROM=vrt.name)
            # Strips of whole 512 px blocks, read 8192 columns at a time (~50 MB): bounded RAM
            # even for the 10 m national grid, and every compressed block is written once.
            for row in range(0,src.height,strip_rows):
                h=min(strip_rows,src.height-row)
                for col in range(0,src.width,strip_cols):
                    window=Window(col,row,min(strip_cols,src.width-col),h)
                    data=src.read(window=window)
                    if (data!=-9999).any():dst.write(data,window=window)   # all-NoData stays empty (tiny)
                if STOP.is_set():raise KeyboardInterrupt
                if row//strip_rows%20==0:
                    print(f'  {product} {year}: {100*(row+h)/src.height:.0f}% merged',flush=True)
            if overviews:
                from rasterio.enums import Resampling
                dst.build_overviews([2,4,8,16,32],Resampling.average)
    # Check the result before it takes the final name.
    with rasterio.open(tmp) as out,rasterio.open(vrt) as src:
        if (out.width,out.height,out.count)!=(src.width,src.height,src.count) or out.transform!=src.transform:
            raise RuntimeError('Merged GeoTIFF grid differs from the VRT')
        for row in np.linspace(0,src.height-1,20).astype(int):
            w=Window(0,int(row),src.width,1)
            if not np.array_equal(out.read(window=w),src.read(window=w)):
                raise RuntimeError(f'Merged GeoTIFF differs from the tiles at row {row}')
    tmp.replace(target)
    print(f'{product} {year}: merged -> {target} ({target.stat().st_size/1024**3:.2f} GB, '
          f'{time.monotonic()-began:.0f} s)')
    return True


def parse_years(text):
    if '-' in text:
        a,b=(int(x) for x in text.split('-'));return list(range(a,b+1))
    return [int(x) for x in text.split(',')]


def main():
    parser=argparse.ArgumentParser(description='Annual whole-Vietnam composites -> resumable tiles on drive E')
    parser.add_argument('--product',required=True,choices=list(PRODUCTS))
    parser.add_argument('--years',required=True,help='e.g. 2004-2014 or 2010,2012')
    parser.add_argument('--project',help='Earth Engine project (not needed with --merge)');parser.add_argument('--ee-key')
    parser.add_argument('--root',default=r'E:\SatelliteData')
    parser.add_argument('--workers',type=int,default=1,help='concurrent downloads (default 1, gentlest on quota)')
    parser.add_argument('--shard',default='1/1',help='i/n: this project takes part i of n of every year (e.g. 3/6)')
    parser.add_argument('--merge',action='store_true',help='no download: turn each finished year VRT into one GeoTIFF')
    parser.add_argument('--overviews',action='store_true',help='with --merge: also build pyramids (faster zooming in QGIS)')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    try:
        part,count=(int(x) for x in args.shard.split('/'));assert 1<=part<=count
    except (ValueError,AssertionError):
        raise SystemExit('--shard must look like 3/6 (part 3 of 6)') from None
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    years=parse_years(args.years);allowed=PRODUCTS[args.product]['years']
    wrong=[y for y in years if y not in allowed]
    if wrong:raise SystemExit(f'{args.product} is only used for {allowed[0]}-{allowed[-1]}; not {wrong} (project rule)')
    signal.signal(signal.SIGINT,lambda *_:(STOP.set(),setattr(province_image,'CANCELLED',True)))
    if args.merge:
        ok=True
        for year in years:
            if STOP.is_set():break
            ok&=merge_year(args.product,year,args.root,args.overviews)
        raise SystemExit(130 if STOP.is_set() else 0 if ok else 2)
    if not args.project:raise SystemExit('--project is required to download')
    c,root,_=local.prepare('full',None,args.root,args.project,'1-11')
    from province_pipeline.prepare_gadm import prepare as prepare_boundaries
    from province_pipeline.boundaries import load_boundaries
    if not Path(c['boundaries']).exists() or not Path(c['boundary_metadata']).exists():prepare_boundaries(c)
    boundaries,_=load_boundaries(c)
    from province_pipeline.earth_engine import initialize
    initialize(c,local.credentials(args.ee_key))
    import ee
    ee.data.setDeadline(300000)   # annual composites need more than the default 2 minutes per tile
    print('Earth Engine project:',c['project'],'| workers',args.workers)
    complete=True
    for year in years:
        if STOP.is_set():break
        complete&=run_year(args.product,year,root,boundaries,args.workers,shard=(part-1,count))
    if STOP.is_set():print('Stopped; run the same command again to continue.');raise SystemExit(130)
    raise SystemExit(0 if complete else 2)


if __name__=='__main__':main()
