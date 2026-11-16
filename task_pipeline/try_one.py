"""Fetch ONE raw image (one province, one product, one period) as a timed test.

    python -m task_pipeline.try_one --province 01 --product LANDSAT --period 2005-01 --project vngis-ee-2
    add --no-mask (keep the whole bounding rectangle) and/or --no-compress (plain TIFF)
    add --scenes (Landsat/Sentinel-2): every source scene as delivered, one TIFF each,
        no cloud/QA mask and no median composite, to inspect what the satellite recorded
    add --scale 50 --resample-to 20 [--compare]: fetch at a coarser pixel size, resample it
        onto the finer grid (--resampling nearest|bilinear, default nearest) and write viewable true-colour TIFFs; --compare also
        fetches the native-resolution image for a side-by-side quality check

Writes under a separate test root (default E:\\SatelliteData_test), so the real
E:\\SatelliteData state, receipts and files are never touched.
"""
import argparse
import logging
import shutil
import time
from pathlib import Path
from . import local
from . import province_image
from . import raw as raw_jobs

RANGES=((1,11),(12,22),(23,33),(34,43),(44,53),(54,63))


def uncompress(path):
    """Same pixels, tags and band names; only the compression is removed."""
    import rasterio
    plain=path.with_name(path.stem+'.plain.tif')
    with rasterio.open(path) as src:
        profile=src.profile.copy()
        for key in ('compress','predictor','zstd_level','zlevel'):profile.pop(key,None)
        profile.update(tiled=True,blockxsize=512,blockysize=512,BIGTIFF='IF_SAFER')
        with rasterio.open(plain,'w',**profile) as dst:
            dst.update_tags(**src.tags())
            for b in range(1,src.count+1):
                dst.set_band_description(b,src.descriptions[b-1]);dst.update_tags(b,**src.tags(b))
            for _,window in src.block_windows(1):dst.write(src.read(window=window),window=window)
    plain.replace(path)


SCENE_BANDS={'modern':['SR_B2','SR_B3','SR_B4','SR_B5','SR_B6','SR_B7'],
             'legacy':['SR_B1','SR_B2','SR_B3','SR_B4','SR_B5','SR_B7'],
             'sentinel':['B2','B3','B4','B8','B11','B12']}


def raw_scene(asset_id,bands):
    """One delivered scene in reflectance units: no QA/cloud mask, no compositing."""
    import ee
    image=ee.Image(asset_id)
    if 'COPERNICUS' in asset_id:
        return image.select(SCENE_BANDS['sentinel'],bands).multiply(0.0001)
    names=SCENE_BANDS['modern' if any(s in asset_id for s in ('LC08','LC09')) else 'legacy']
    return image.select(names,bands).multiply(0.0000275).add(-0.2)


def scenes(args,job,boundary,root,config,began):
    import ee
    out=Path(root)/'scenes'/f"{job['province']['ma_tinh']}_{job['product']}_{job['period']}";out.mkdir(parents=True,exist_ok=True)
    geometry=ee.Geometry(boundary['geometry']);ids=job['inventory']['asset_ids']
    print(f'{len(ids)} source scenes; writing each unmasked to {out}')
    for asset_id in ids:
        name=asset_id.split('/')[-1]
        # Landsat ids end with <sensor>_<path><row>_<date>; S2 ids start with the date.
        path=out/(name+'.tif')
        if path.exists():print('  exists',path.name);continue
        part=dict(job,prefix=name)
        result=province_image.download(raw_scene(asset_id,job['bands']).clip(geometry),part,path,boundary,config,mask=False)
        if args.no_compress:uncompress(path)
        import rasterio
        with rasterio.open(path) as ds:
            valid=(ds.read(1)!=-9999).mean()*100
        print(f"  {path.name}: {path.stat().st_size/1024**2:.1f} MB, {result['requests']} requests, {valid:.1f}% pixels with data")
    print(f'DONE in {time.monotonic()-began:.0f} s')
    print('Folder:',out)


def fetch(c,root,control,job,boundary,mask=True):
    """Inventory + export of one job; returns (path, seconds, Earth Engine requests)."""
    import ee
    from .methods import inventory
    began=time.monotonic()
    if not local.prior(c,root,control,job):
        record=inventory(job,ee.Geometry(boundary['geometry']))
        print(f"  {job['scale']} m: {record.get('count')} source scenes, {record['status']}")
        if record['status']!='AVAILABLE':raise SystemExit('No usable source image for this period')
        job['inventory']=record
        stats={};download=province_image.download
        def counted(image,job,path,boundary,config,**k):
            result=download(image,job,path,boundary,config,mask=mask,**k);stats.update(result);return result
        province_image.download=counted
        try:
            local.export(c,root,control,job,boundary)
        finally:
            province_image.download=download
        requests=stats.get('requests')
    else:
        requests='already fetched'
    receipt=local.prior(c,root,control,job)
    return local.resolve(root,control,receipt['relative_path']),time.monotonic()-began,requests


def resample(source,target,job,method='nearest'):
    """Resample every band onto the finer grid of `job` (nearest or bilinear); NoData stays NoData."""
    import numpy as np
    import rasterio
    from affine import Affine
    from rasterio.warp import reproject,Resampling
    t=job['tile']
    with rasterio.open(source) as src:
        data=np.full((src.count,t['height'],t['width']),-9999,dtype='int16')
        for b in range(src.count):
            reproject(src.read(b+1),data[b],src_transform=src.transform,src_crs=src.crs,src_nodata=-9999,
                      dst_transform=Affine(*t['transform']),dst_crs=src.crs,dst_nodata=-9999,
                      resampling=getattr(Resampling,method))
        profile=dict(driver='GTiff',width=t['width'],height=t['height'],count=src.count,dtype='int16',
                     crs=src.crs,transform=Affine(*t['transform']),nodata=-9999,compress='DEFLATE',
                     predictor=2,tiled=True,BIGTIFF='IF_SAFER')
        with rasterio.open(target,'w',**profile) as dst:
            dst.write(data)
            for b in range(src.count):dst.set_band_description(b+1,src.descriptions[b])
            dst.update_tags(**src.tags(),RESAMPLED_FROM=str(source.name),RESAMPLING=method)


def truecolor(source,target):
    """Plain (non-geo) 8-bit RGB TIFF with ONE fixed stretch, so variants compare fairly."""
    import numpy as np
    import rasterio
    with rasterio.open(source) as src:
        names=list(src.descriptions)
        rgb=src.read([names.index(n)+1 for n in ('RED','GREEN','BLUE')]).astype('float32')
    bad=(rgb==-9999).any(0)
    # Reflectance 0 .. 0.3 (stored x10000) -> 0 .. 255, the usual true-colour range for land.
    out=np.clip(rgb/3000*255,0,255).astype('uint8');out[:,bad]=0
    import warnings
    warnings.filterwarnings('ignore',category=rasterio.errors.NotGeoreferencedWarning)
    with rasterio.open(target,'w',driver='GTiff',width=out.shape[2],height=out.shape[1],count=3,
                       dtype='uint8',photometric='RGB',PROFILE='BASELINE') as dst:
        dst.write(out)


def coarse(args,c,root,control,job,make_job,boundary):
    """Fetch at --scale, optionally resample to --resample-to, write viewable TIFFs."""
    out=Path(root)/'compare'/f"{job['province']['ma_tinh']}_{job['product']}_{job['period']}";out.mkdir(parents=True,exist_ok=True)
    base=f"{job['province']['ma_tinh']}_{job['province']['slug']}_{job['product']}_{job['period']}"
    path,seconds,requests=fetch(c,root,control,job,boundary)
    print(f"Fetched {args.scale} m in {seconds:.0f} s ({requests} requests): {path}")
    truecolor(path,out/f'{base}_{args.scale}m_truecolor.tif')
    if args.resample_to:
        fine=make_job(args.resample_to)
        name=f'{base}_{args.scale}m_resampled_{args.resample_to}m_{args.resampling}'
        geo=out/f'{name}.tif'
        resample(path,geo,fine,args.resampling)
        truecolor(geo,out/f'{name}_truecolor.tif')
        print(f'Resampled {args.scale} m -> {args.resample_to} m ({args.resampling}): {geo}')
    if args.compare:
        native=make_job()
        path,seconds,requests=fetch(c,root,control,native,boundary)
        print(f"Fetched native {native['scale']} m in {seconds:.0f} s ({requests} requests): {path}")
        truecolor(path,out/f"{base}_{native['scale']}m_native_truecolor.tif")
    print('Viewable true-colour TIFFs (same fixed colour stretch):',out)
    for f in sorted(out.glob('*_truecolor.tif')):print('  ',f.name)


def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--province',default='01',help='ma_tinh, e.g. 01 = Ha Noi')
    parser.add_argument('--product',default='LANDSAT',choices=['LANDSAT','SENTINEL2','DMSP','VIIRS_MONTHLY'])
    parser.add_argument('--period',default='2005-01',help='YYYY-MM (DMSP: YYYY)')
    parser.add_argument('--project');parser.add_argument('--ee-key')
    parser.add_argument('--root',default=r'E:\SatelliteData_test')
    parser.add_argument('--no-mask',action='store_true',help='keep pixels outside the province boundary')
    parser.add_argument('--no-compress',action='store_true',help='write an uncompressed TIFF')
    parser.add_argument('--scenes',action='store_true',help='each raw source scene, unmasked, one TIFF each')
    parser.add_argument('--scale',type=int,help='fetch at this pixel size in metres instead of the native one')
    parser.add_argument('--resample-to',type=int,help='resample the fetched image to this pixel size')
    parser.add_argument('--resampling',choices=['nearest','bilinear'],default='nearest',
                        help='resampling method for --resample-to (default: nearest neighbour)')
    parser.add_argument('--compare',action='store_true',help='also fetch the native-resolution image')
    args=parser.parse_args()
    if (args.resample_to or args.compare) and not args.scale:raise SystemExit('--resample-to/--compare need --scale')
    if args.scale and args.scenes:raise SystemExit('--scale cannot be combined with --scenes')
    if args.scenes and args.product not in ('LANDSAT','SENTINEL2'):raise SystemExit('--scenes is for LANDSAT/SENTINEL2')
    # Each variant gets its own test folder, so variants never collide with each other.
    args.root+=('_nomask' if args.no_mask else '')+('_nocompress' if args.no_compress else '')+(f'_s{args.scale}' if args.scale else '');logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    from .scope import provinces
    province=next((p for p in provinces() if p['ma_tinh']==args.province),None)
    if province is None:raise SystemExit(f'Unknown province code {args.province}')
    start,end=next(r for r in RANGES if r[0]<=province['number']<=r[1])
    c,root,control=local.prepare('full',None,args.root,args.project,f'{start}-{end}')
    from province_pipeline.prepare_gadm import prepare as prepare_boundaries
    from province_pipeline.boundaries import load_boundaries
    if not Path(c['boundaries']).exists() or not Path(c['boundary_metadata']).exists():prepare_boundaries(c)
    boundaries,metadata=load_boundaries(c)
    from province_pipeline.earth_engine import initialize
    initialize(c,local.credentials(args.ee_key))
    print('Earth Engine project:',c['project'])
    if args.no_mask and c['crs']!='EPSG:4326':raise SystemExit('--no-mask expects the EPSG:4326 grid')
    c=dict(c,province_codes=[province['ma_tinh']],
           local_output_limit_bytes=max(0,(shutil.disk_usage(root).free-2*1024**3)//2))
    kind=raw_jobs.DAY if args.product in ('LANDSAT','SENTINEL2') else raw_jobs.NIGHT
    def make_job(scale=None):
        from province_pipeline.sources import SOURCES
        native=SOURCES[args.product]['scale']
        SOURCES[args.product]['scale']=scale or native
        try:
            found=next((j for j in raw_jobs.jobs(c,boundaries,metadata,kind,province)
                        if j['product']==args.product and j['period']==args.period),None)
        finally:
            SOURCES[args.product]['scale']=native
        if found is None:raise SystemExit(f'No {args.product} job for period {args.period}')
        if scale and scale!=native:found['prefix']+=f'_{scale}m'
        return found
    job=make_job(args.scale)
    if args.scale:
        return coarse(args,c,root,control,job,make_job,boundaries[province['ma_tinh']])
    t=job['tile']
    print(f"Grid {t['width']} x {t['height']} px, {len(job['bands'])} bands {job['dtype']}, "
          f"window {job['chunk_pixels']} px, scale {job['scale']} m")
    if local.prior(c,root,control,job):
        raise SystemExit(f'Already fetched in {root}; delete that test folder to fetch again')
    import ee
    from .methods import inventory
    boundary=boundaries[province['ma_tinh']]
    if args.no_mask:
        # The whole grid rectangle: Earth Engine clips to it and every window is fetched.
        x0,y0,x1,y1=t['bounds']
        boundary=dict(boundary,geometry=dict(type='Polygon',coordinates=[[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]]))
    began=time.monotonic()
    record=inventory(job,ee.Geometry(boundary['geometry']))
    print('Source scenes:',record.get('count'),'status:',record['status'])
    if record['status']!='AVAILABLE':raise SystemExit('No usable source image for this period')
    job['inventory']=record
    if args.scenes:
        return scenes(args,job,boundary,root,c,began)
    stats={}
    download=province_image.download
    def counted(image,job,path,boundary,config,**k):
        result=download(image,job,path,boundary,config,mask=not args.no_mask,**k)
        if args.no_compress:uncompress(path)
        stats.update(result);return result
    province_image.download=counted
    try:
        receipt=local.export(c,root,control,job,boundary)
    finally:
        province_image.download=download
    path=local.resolve(root,control,receipt['relative_path'])
    print('Boundary mask:','off (full rectangle)' if args.no_mask else 'on (province only)',
          '| Compression:','none' if args.no_compress else 'lossless')
    print(f"DONE in {time.monotonic()-began:.0f} s, {stats.get('requests')} Earth Engine requests "
          f"({stats.get('strategy')}), {int(receipt['file']['size'])/1024**2:.1f} MB")
    print('File:',path)


if __name__=='__main__':main()
