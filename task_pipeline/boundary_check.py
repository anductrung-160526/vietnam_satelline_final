"""Pilot check for one province/month day TIFF cut to the province boundary.

Builds the same job, composite and download as the production runner, but writes only
to a local folder (uploaded as a GitHub artifact). No Drive state, receipts or panels.

    python -m task_pipeline.boundary_check --province 01 --period 2025-01 --product SENTINEL2
"""
import argparse
import json
import logging
from pathlib import Path


def preview(path,out,boundary,job,size=1600):
    """RGB PNG (2-98% stretch), transparent outside the mask, province outline in red."""
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.features import rasterize
    from rasterio.shutil import copy as copy_raster
    from shapely.geometry import mapping
    from .province_image import boundary_geometry
    with rasterio.open(path) as ds:
        scale=max(ds.width,ds.height)/size if max(ds.width,ds.height)>size else 1
        w,h=max(1,round(ds.width/scale)),max(1,round(ds.height/scale))
        idx=[job['bands'].index(b)+1 for b in ('RED','GREEN','BLUE')]
        rgb=ds.read(idx,out_shape=(3,h,w),resampling=Resampling.nearest)
        alpha=ds.dataset_mask(out_shape=(h,w),resampling=Resampling.nearest)
        transform=ds.transform*ds.transform.scale(ds.width/w,ds.height/h)
    valid=(alpha>0)&(rgb!=-9999).all(axis=0)
    out_rgb=np.zeros((3,h,w),dtype='uint8')
    for i in range(3):
        band=rgb[i];values=band[valid]
        if values.size:
            lo,hi=np.percentile(values,[2,98]);hi=hi if hi>lo else lo+1e-6
            out_rgb[i][valid]=(255*np.clip((band[valid]-lo)/(hi-lo),0,1)).astype('uint8')
    a=np.where(valid,255,0).astype('uint8')
    line=rasterize([mapping(boundary_geometry(boundary,job['crs']).boundary)],out_shape=(h,w),
                   transform=transform,all_touched=True,dtype='uint8')>0
    out_rgb[0][line]=255;out_rgb[1][line]=0;out_rgb[2][line]=0;a[line]=255
    tmp=Path(out).with_suffix('.tmp.tif')
    with rasterio.open(tmp,'w',driver='GTiff',width=w,height=h,count=4,dtype='uint8') as dst:
        dst.write(np.concatenate([out_rgb,a[None]]))
    copy_raster(tmp,out,driver='PNG');tmp.unlink()
    return dict(png=str(out),width=w,height=h,valid_pct=round(100*float(valid.mean()),2))


def outside_valid(path,boundary,job):
    """Pixels not touching the province polygon that still carry data (neighbouring land)."""
    import numpy as np
    import rasterio
    from rasterio.features import geometry_mask
    from shapely.geometry import mapping
    from .province_image import boundary_geometry
    shapes=[mapping(boundary_geometry(boundary,job['crs']))]
    count=total=0
    with rasterio.open(path) as ds:
        for _,window in ds.block_windows(1):
            outside=geometry_mask(shapes,out_shape=(window.height,window.width),
                                  transform=ds.window_transform(window),all_touched=True)
            data=ds.read(1,window=window)
            count+=int(((data!=-9999)&outside).sum());total+=int(outside.sum())
    return dict(outside_pixels=total,outside_pixels_with_data=count)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default='.province-local/config.json')
    parser.add_argument('--province',default='01');parser.add_argument('--period',default='2025-01')
    parser.add_argument('--product',default='SENTINEL2');parser.add_argument('--out',default='boundary_check')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    import ee
    from province_pipeline.boundaries import load_boundaries
    from province_pipeline.common import provinces
    from province_pipeline.auth import ee_credentials
    from province_pipeline.earth_engine import initialize
    from province_pipeline.jobs import table_job
    from shapely.geometry import shape
    from .province_image import output_job,download,mask_outside
    from .methods import inventory,composite
    c=json.loads(Path(args.config).read_text(encoding='utf-8'))
    boundaries,metadata=load_boundaries(c)
    initialize(c,ee_credentials())
    p=next(x for x in provinces() if x['ma_tinh']==args.province)
    boundary=boundaries[args.province]
    base=table_job(c,dict(province=p,product=args.product,period=args.period,night=False),metadata)
    job=output_job(c,base,shape(boundary['geometry']).bounds,2)
    geometry=ee.Geometry(boundary['geometry'])
    job['inventory']=inventory(job,geometry)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    report=dict(project=c['project'],province=p['ten_tinh'],product=args.product,period=args.period,
                grid=dict(width=job['tile']['width'],height=job['tile']['height'],resolution_deg=job['grid_resolution']),
                inventory=dict((k,job['inventory'].get(k)) for k in ('status','count','window_days','collections')))
    if job['inventory']['status']!='AVAILABLE':
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        raise SystemExit('No source scenes for this province/month')
    path=out/(job['prefix']+'.tif')
    report['download']=download(composite(c,job,geometry),job,path,boundary,c,mask=False)
    report['before_mask']=outside_valid(path,boundary,job)
    report['preview_before']=preview(path,out/'preview_before_mask.png',boundary,job)
    report['mask']=mask_outside(path,job,boundary)
    report['after_mask']=outside_valid(path,boundary,job)
    report['preview_after']=preview(path,out/'preview_after_mask.png',boundary,job)
    report['tiff']=dict(name=path.name,size_mb=round(path.stat().st_size/1024**2,1))
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['after_mask']['outside_pixels_with_data']:
        raise SystemExit('Pixels outside the province still carry data')


if __name__=='__main__':
    main()
