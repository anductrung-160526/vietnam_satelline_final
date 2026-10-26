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

DAY_PRODUCTS=('LANDSAT','SENTINEL2')
# Day TIFFs are stored as int16 = round(value*10000); GDAL scale 0.0001 restores the value.
# Reflectance (-0.2..1.6) and indices (-1..1) fit; max rounding error 0.00005.
DAY_SCALE=10000
DTYPE_BYTES={'float64':8,'float32':4,'int16':2}
# Day TIFFs keep only the 6 measured reflectance bands. NDVI/NDBI/MNDWI/BSI are exact
# formulas of these bands (recomputable at any time) and remain in the CSV statistics.
DAY_TIFF_BANDS=['BLUE','GREEN','RED','NIR','SWIR1','SWIR2']
# Final day TIFFs: lossless ZSTD (+ horizontal predictor for integers) instead of DEFLATE.
DAY_COMPRESSION=dict(compress='ZSTD',zstd_level=19,blockxsize=512,blockysize=512)

def nbytes(job):
    return DTYPE_BYTES.get(job.get('dtype'),8)

def predictor(dtype):
    return 3 if str(dtype).startswith('float') else 2

def to_int16(image):
    """EE side: scale, round, keep -9999 free for NoData, clamp to int16."""
    scaled=image.multiply(DAY_SCALE).round()
    scaled=scaled.where(scaled.eq(-9999),-9998).max(-32767).min(32767)
    return scaled.toInt16()

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
    day=base['product'] in DAY_PRODUCTS
    dtype='int16' if day else 'float64'
    if day:base=dict(base,bands=list(DAY_TIFF_BANDS))
    job=dict(base,kind='image',priority=priority,variant='source' if priority==0 else 'composite',
        scale=scale,grid_resolution=resolution,dtype=dtype,tile=whole,image_layout='province',
        chunk_pixels=config['tile_pixels'],preview_required=False)
    job.pop('job_id',None);job.pop('reserved_bytes',None)
    job['prefix']=f"{p['ma_tinh']}_{p['slug']}_{job['product']}_{job['period']}_province_{job['algorithm_version']}_{job['recipe_hash'][:8]}"+('_sr6' if day else '')
    identity={k:v for k,v in job.items() if k!='chunk_pixels'}
    # Preserve completed TIFF identities from the initial province export release.
    # Disabling a display sidecar must not cause satellite data to be fetched again.
    identity['preview_required']=True
    job['job_id']=digest(identity)[:32]
    raw=whole['width']*whole['height']*len(job['bands'])*nbytes(job)
    cap=(int(config.get('local_output_limit_bytes',1024**4)) if config.get('execution_backend')=='local'
         else int(config['drive_staging_budget_gib']*1024**3*config['high_watermark']*.90))
    # Enforced output limit, not a promise of compression or permission to exceed quota.
    job['reserved_bytes']=min(2*raw+1024**2,cap)
    return canonical_job(job)

def small(job):
    t=job['tile']
    return max(t['width'],t['height'])<=10000 and t['width']*t['height']*len(job['bands'])*nbytes(job)<32_000_000

def size_error(error):
    return any(s in str(error).lower() for s in ('request size','request too large','download limit',
        'pixel grid dimensions','user memory limit','must be less than or equal','too many pixels'))

def check_stop(config):
    if CANCELLED or time.monotonic()>=config.get('_task_deadline',float('inf')):
        raise ExportInterrupted('Resume this province output in the next runner')

def boundary_geometry(boundary,crs):
    from shapely.geometry import shape
    geometry=shape(boundary['geometry'])
    if crs!='EPSG:4326':
        import numpy as np
        from shapely import transform
        from rasterio.warp import transform as warp
        def project(xy):
            x,y=warp('EPSG:4326',crs,xy[:,0],xy[:,1]);return np.column_stack([x,y])
        geometry=transform(geometry,project)
    return geometry

def mask_outside(path,job,boundary):
    """Keep only pixels touching this province's polygon; everything else becomes NoData.

    The bounding-box grid is unchanged (same transform/size/job identity), but pixels of
    neighbouring provinces are written as -9999 and excluded by an internal GDAL mask, so
    GIS viewers show the province outline instead of a rectangle. Returns pixel counts.
    """
    import numpy as np
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import Window
    from shapely.geometry import mapping
    path=Path(path);target=path.with_name(path.stem+'.masked.tif')
    shapes=[mapping(boundary_geometry(boundary,job['crs']))]
    inside_total=outside_cleared=0
    try:
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True,GDAL_CACHEMAX=64*1024**2),rasterio.open(path) as src:
            profile=src.profile.copy()
            profile.update(driver='GTiff',nodata=-9999,compress='DEFLATE',predictor=predictor(src.dtypes[0]),tiled=True,
                           blockxsize=256,blockysize=256,BIGTIFF='IF_SAFER')
            if job.get('product') in DAY_PRODUCTS:
                profile.update(DAY_COMPRESSION)
            # Write whole tile rows so every compressed tile is written exactly once.
            rows=profile['blockysize']
            with rasterio.open(target,'w',**profile) as dst:
                dst.update_tags(**src.tags())
                for b in range(1,src.count+1):
                    dst.set_band_description(b,src.descriptions[b-1])
                if src.dtypes[0]=='int16':
                    dst.scales=[1/DAY_SCALE]*src.count;dst.offsets=[0.0]*src.count
                    dst.update_tags(SCALE_FACTOR=str(1/DAY_SCALE),VALUE='stored_int16 * 0.0001')
                else:
                    dst.scales=src.scales;dst.offsets=src.offsets
                for row in range(0,src.height,rows):
                    window=Window(0,row,src.width,min(rows,src.height-row))
                    inside=~geometry_mask(shapes,out_shape=(window.height,window.width),
                                          transform=src.window_transform(window),all_touched=True)
                    data=src.read(window=window)
                    outside_cleared+=int(((data!=-9999).any(axis=0)&~inside).sum())
                    data[:,~inside]=-9999
                    dst.write(data,window=window)
                    valid=inside&(data!=-9999).any(axis=0)
                    dst.write_mask((valid*255).astype('uint8'),window=window)
                    inside_total+=int(inside.sum())
                dst.update_tags(BOUNDARY_MASK='province_polygon_all_touched',
                                BOUNDARY_SHA256=str(job.get('boundary_sha256','')))
        target.replace(path)
    finally:
        target.unlink(missing_ok=True)
    return dict(boundary_mask=True,inside_pixels=inside_total,outside_pixels_cleared=outside_cleared)

def download(image,job,path,boundary,config,fetch=None,mask=True):
    from province_pipeline.direct_export import download_image
    fetch=fetch or download_image;path=Path(path);check_stop(config)
    if image is not None and job.get('product') in DAY_PRODUCTS:
        image=image.select(job['bands'])
    if image is not None and job.get('dtype')=='int16':
        image=to_int16(image)
    if shutil.disk_usage(path.parent).free<job['reserved_bytes']+512*1024**2:
        raise OutputLimit('Not enough runner disk for reserved province output')
    try:
        if small(job):
            try:
                fetch(image,job,path)
                result=dict(strategy='whole',requests=1)
            except Exception as error:
                if not size_error(error):raise
                path.unlink(missing_ok=True)
                result=stitch(image,job,path,boundary,config,fetch)
        else:
            result=stitch(image,job,path,boundary,config,fetch)
        # Day images: the province shape only, never the rectangle of neighbouring land.
        if mask and job.get('product') in DAY_PRODUCTS:
            result.update(mask_outside(path,job,boundary))
        return result
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
        compress='DEFLATE',predictor=predictor(job['dtype']),tiled=True,blockxsize=256,blockysize=256,BIGTIFF='IF_SAFER')
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
