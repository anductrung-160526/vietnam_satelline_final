"""Fetch ONE raw image (one province, one product, one period) as a timed test.

    python -m task_pipeline.try_one --province 01 --product LANDSAT --period 2005-01 --project vngis-ee-2

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


def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--province',default='01',help='ma_tinh, e.g. 01 = Ha Noi')
    parser.add_argument('--product',default='LANDSAT',choices=['LANDSAT','SENTINEL2','DMSP','VIIRS_MONTHLY'])
    parser.add_argument('--period',default='2005-01',help='YYYY-MM (DMSP: YYYY)')
    parser.add_argument('--project');parser.add_argument('--ee-key')
    parser.add_argument('--root',default=r'E:\SatelliteData_test')
    args=parser.parse_args();logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
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
    began=time.monotonic()
    record=inventory(job,ee.Geometry(boundaries[province['ma_tinh']]['geometry']))
    print('Source scenes:',record.get('count'),'status:',record['status'])
    if record['status']!='AVAILABLE':raise SystemExit('No usable source image for this period')
    job['inventory']=record
    stats={}
    download=province_image.download
    def counted(*a,**k):
        result=download(*a,**k);stats.update(result);return result
    province_image.download=counted
    try:
        receipt=local.export(c,root,control,job,boundaries[province['ma_tinh']])
    finally:
        province_image.download=download
    path=local.resolve(root,control,receipt['relative_path'])
    print(f"DONE in {time.monotonic()-began:.0f} s, {stats.get('requests')} Earth Engine requests "
          f"({stats.get('strategy')}), {int(receipt['file']['size'])/1024**2:.1f} MB")
    print('File:',path)


if __name__=='__main__':main()
