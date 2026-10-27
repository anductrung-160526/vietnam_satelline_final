"""Fetch ONE raw image (one province, one product, one period) as a timed test.

    python -m task_pipeline.try_one --province 01 --product LANDSAT --period 2005-01 --project vngis-ee-2
    add --no-mask (keep the whole bounding rectangle) and/or --no-compress (plain TIFF)

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


def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--province',default='01',help='ma_tinh, e.g. 01 = Ha Noi')
    parser.add_argument('--product',default='LANDSAT',choices=['LANDSAT','SENTINEL2','DMSP','VIIRS_MONTHLY'])
    parser.add_argument('--period',default='2005-01',help='YYYY-MM (DMSP: YYYY)')
    parser.add_argument('--project');parser.add_argument('--ee-key')
    parser.add_argument('--root',default=r'E:\SatelliteData_test')
    parser.add_argument('--no-mask',action='store_true',help='keep pixels outside the province boundary')
    parser.add_argument('--no-compress',action='store_true',help='write an uncompressed TIFF')
    args=parser.parse_args()
    # Each variant gets its own test folder, so variants never collide with each other.
    args.root+=('_nomask' if args.no_mask else '')+('_nocompress' if args.no_compress else '');logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
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
    job=next((j for j in raw_jobs.jobs(c,boundaries,metadata,kind,province)
              if j['product']==args.product and j['period']==args.period),None)
    if job is None:raise SystemExit(f'No {args.product} job for period {args.period}')
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
