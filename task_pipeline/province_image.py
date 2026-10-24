"""One province TIFF: bounded downloads and streaming lossless mosaicking."""
import math
import time
import shutil
import tempfile
from pathlib import Path
CANCELLED=False
class ExportInterrupted(BaseException):
    pass
class OutputLimit(RuntimeError):
    pass

def grid(bounds,resolution):
    x0=math.floor(bounds[0]/resolution);x1=math.ceil(bounds[2]/resolution)
    y0=math.floor(bounds[1]/resolution);y1=math.ceil(bounds[3]/resolution)
    return dict(bounds=[x0*resolution,y0*resolution,x1*resolution,y1*resolution],
        transform=[resolution,0,x0*resolution,0,-resolution,y1*resolution],
        width=x1-x0,height=y1-y0,x0=x0,y1=y1)

def output_job(config,base,bounds,priority):
    from province_pipeline.common import digest
    from province_pipeline.layout import canonical_job
    from province_pipeline.sources import SOURCES
    scale=SOURCES[base['product']]['scale']
    resolution=scale/111319.49079327358 if config['crs']=='EPSG:4326' else scale
    whole=grid(bounds,resolution);p=base['province']
    job=dict(base,kind='image',priority=priority,variant='source' if priority==0 else 'composite',
        scale=scale,grid_resolution=resolution,dtype='float64',tile=whole,image_layout='province',
        chunk_pixels=config['tile_pixels'],preview_required=False)
    job.pop('job_id',None);job.pop('reserved_bytes',None)
    job['prefix']=f"{p['ma_tinh']}_{p['slug']}_{job['product']}_{job['period']}_province_{job['algorithm_version']}_{job['recipe_hash'][:8]}"
    identity={k:v for k,v in job.items() if k!='chunk_pixels'}
    # Preserve completed TIFF identities from the initial province export release.
    # Disabling a display sidecar must not cause satellite data to be fetched again.
    identity['preview_required']=True
    job['job_id']=digest(identity)[:32]
    raw=whole['width']*whole['height']*len(job['bands'])*8
    cap=int(config['drive_staging_budget_gib']*1024**3*config['high_watermark']*.90)
    # Enforced output limit, not a promise of compression or permission to exceed quota.
    job['reserved_bytes']=min(2*raw+1024**2,cap)
    return canonical_job(job)

def small(job):
    t=job['tile']
    return max(t['width'],t['height'])<=10000 and t['width']*t['height']*len(job['bands'])*8<32_000_000

def size_error(error):
    return any(s in str(error).lower() for s in ('request size','request too large','download limit',
        'pixel grid dimensions','user memory limit','must be less than or equal','too many pixels'))

def check_stop(config):
    if CANCELLED or time.monotonic()>=config.get('_task_deadline',float('inf')):
        raise ExportInterrupted('Resume this province output in the next runner')

def download(image,job,path,boundary,config,fetch=None):
    from province_pipeline.direct_export import download_image
    fetch=fetch or download_image;path=Path(path);check_stop(config)
    if shutil.disk_usage(path.parent).free<job['reserved_bytes']+512*1024**2:
        raise OutputLimit('Not enough runner disk for reserved province output')
    try:
        if small(job):
            try:
                fetch(image,job,path)
                return dict(strategy='whole',requests=1)
            except Exception as error:
                if not size_error(error):raise
                path.unlink(missing_ok=True)
        return stitch(image,job,path,boundary,config,fetch)
    except BaseException:
        path.unlink(missing_ok=True)
        raise

def stitch(image,job,path,boundary,config,fetch):
    import rasterio
    import numpy as np
    from affine import Affine
    from rasterio.windows import Window
    from shapely.geometry import shape,box
    from shapely import transform
    from rasterio.warp import transform as warp
    geometry=shape(boundary['geometry'])
    if job['crs']!='EPSG:4326':
        def project(xy):
            x,y=warp('EPSG:4326',job['crs'],xy[:,0],xy[:,1]);return np.column_stack([x,y])
        geometry=transform(geometry,project)
    tile=job['tile'];n=job['chunk_pixels'];res=job['grid_resolution'];requests=0
    profile=dict(driver='GTiff',width=tile['width'],height=tile['height'],count=len(job['bands']),
        dtype=job['dtype'],crs=job['crs'],transform=Affine(*tile['transform']),nodata=-9999,
        compress='DEFLATE',predictor=3,tiled=True,blockxsize=256,blockysize=256,BIGTIFF='IF_SAFER')
    with tempfile.TemporaryDirectory(prefix='chunks-',dir=path.parent) as tmp,rasterio.Env(GDAL_CACHEMAX=64*1024**2):
        with rasterio.open(path,'w',**profile) as output:
            for b,name in enumerate(job['bands'],1):output.set_band_description(b,name)
            for row in range(0,tile['height'],n):
                for col in range(0,tile['width'],n):
                    check_stop(config)
                    width=min(n,tile['width']-col);height=min(n,tile['height']-row)
                    window=Window(col,row,width,height);affine=output.window_transform(window)
                    bounds=[affine.c,affine.f-height*res,affine.c+width*res,affine.f]
                    if not geometry.intersects(box(*bounds)):
                        output.write(np.full((len(job['bands']),height,width),-9999,dtype=job['dtype']),window=window)
                        continue
                    patch=dict(job,tile=dict(bounds=bounds,transform=list(affine)[:6],width=width,height=height),image_layout='chunk')
                    local=Path(tmp)/'chunk.tif';fetch(image,patch,local);requests+=1
                    with rasterio.open(local) as source:
                        if source.width!=width or source.height!=height or source.count!=len(job['bands']) or not source.transform.almost_equals(affine) or source.crs!=rasterio.crs.CRS.from_user_input(job['crs']) or any(t!=job['dtype'] for t in source.dtypes) or source.nodata!=-9999:
                            raise ValueError('Chunk shape/grid differs from target window')
                        output.write(source.read(),window=window)
                    local.unlink()
                    if path.stat().st_size>job['reserved_bytes']:
                        raise OutputLimit('Compressed province output exceeded staging reservation')
        if path.stat().st_size>job['reserved_bytes']:
            raise OutputLimit('Compressed province output exceeded staging reservation')
    return dict(strategy='internal_chunks',requests=requests)
