"""Bounded Earth Engine downloads → user Drive uploads, matching legacy identity separation.

Each image is one tile below EE's 32 MB uncompressed / 10000-dimension download
limit. No service-account My Drive ownership or shared-folder export is assumed.
"""
import csv
import tempfile
import time
from pathlib import Path
from .common import audit
from .projection import ee_crs, same_crs

MAX_DOWNLOAD_BYTES = 32_000_000


def check_tile_limit(config):
    from .sources import SOURCES
    n = config['tile_pixels']
    if n > 10000:
        raise ValueError('Earth Engine download dimensions exceed 10000')
    for product in config['products']:
        if n*n*len(SOURCES[product]['bands'])*(8 if config.get('quality',{}).get('processing_mode')=='notebook_tasks' else 4) >= MAX_DOWNLOAD_BYTES:
            raise ValueError('Direct download exceeds 32 MB uncompressed; reduce tile_pixels (512 recommended)')


def download_image(image, job, path, attempts=4):
    import requests
    scale = job['scale']
    bounds = job['tile']['bounds']
    pixels = round((bounds[2]-bounds[0])/job.get('grid_resolution',scale))
    width=job['tile'].get('width',pixels);height=job['tile'].get('height',pixels)
    if max(width,height)>10000:
        raise ValueError('Download dimensions exceed the 10000-pixel limit')
    if width*height*len(job['bands'])*{'float64':8,'int16':2}.get(job.get('dtype'),4) >= MAX_DOWNLOAD_BYTES:
        raise ValueError('Direct download tile exceeds 32 MB')
    # EE's exact-grid mode is CRS + affine + dimensions, WITHOUT region/scale.
    # The affine origin and dimensions already define the complete tile footprint.
    params = dict(crs=ee_crs(job['crs']), crs_transform=job['tile']['transform'],
                  dimensions=[width,height], format='GEO_TIFF', filePerBand=False)
    # Explicit default value is preserved as NoData metadata by local TIFF rewrite below.
    image = image.unmask(-9999, sameFootprint=False)
    if job.get('dtype') == 'int16':
        image = image.toInt16()  # unmask may widen the type; keep the declared int16 grid.
    for attempt in range(attempts):
        try:
            url = image.getDownloadURL(params)
            with requests.get(url, stream=True, timeout=(20,180)) as response:
                if response.status_code in (429,500,502,503,504):
                    if attempt == attempts-1:
                        raise RuntimeError('Earth Engine download transient failure after bounded retries')
                    time.sleep(min(30,2**attempt))
                    continue
                if response.status_code != 200:
                    raise RuntimeError(f'Earth Engine download HTTP {response.status_code}; no signed URL logged')
                total=0
                with path.open('wb') as stream:
                    for block in response.iter_content(1024*1024):
                        total += len(block)
                        if total > job['reserved_bytes']:
                            raise RuntimeError('Downloaded TIFF exceeded its reserved byte limit')
                        stream.write(block)
            break
        except requests.RequestException:
            if attempt == attempts-1:
                raise RuntimeError('Earth Engine download network failure; signed URL omitted') from None
            time.sleep(min(30,2**attempt))
    import rasterio
    from affine import Affine
    with rasterio.open(path,'r+') as ds:
        expected=Affine(*job['tile']['transform'])
        if (not same_crs(ds.crs,job['crs']) or not ds.transform.almost_equals(expected)
                or ds.width != width or ds.height != height or ds.count != len(job['bands'])):
            raise RuntimeError('Earth Engine returned a different tile grid/band layout')
        ds.nodata=-9999
        for index,name in enumerate(job['bands'],1):
            ds.set_band_description(index,name)
    if job.get('quality',{}).get('processing_mode')=='notebook_tasks' and job.get('image_layout')!='chunk':
        lossless_tiff(path)


def write_statistics(image, job, geometry, path, config=None):
    from .earth_engine import statistics
    if job.get('pipeline_version') == 2:
        from .processing import statistics
    # Whole-province sufficient statistics from the same image and masks, not tile mean averages.
    info=statistics(image, job, geometry).first().toDictionary().getInfo()
    if job.get('pipeline_version') == 2:
        from .quality import reprocess_statistics
        info=reprocess_statistics(info,job,geometry,config)
    from .sources import SOURCES
    fields=['ma_tinh','ten_tinh','nam','thang','nguon_anh','period','job_id','algorithm_version',
            'boundary_sha256','scale','crs','valid_area','total_area']
    fields += [band+suffix for band in SOURCES[job['product']]['bands'] for suffix in ('_w','_w2','_sum')]
    if job.get('pipeline_version') == 2:
        fields = sorted(info)
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        writer.writerow(info)
    return info


def transfer(config, drive, job, boundary):
    import ee
    from .earth_engine import composite
    geometry=ee.Geometry(boundary['geometry'])
    image=composite(config,job,geometry)
    suffix='.tif' if job['kind']=='image' else '.csv'
    with tempfile.TemporaryDirectory(prefix='province-') as tmp:
        path=Path(tmp)/(job['prefix']+suffix)
        if job['kind']=='image':
            if job.get('image_layout')=='province':
                from task_pipeline.province_image import download
                packing=download(image,job,path,boundary,config)
            else:
                download_image(image,job,path)
            if job.get('pipeline_version') == 2:
                from .quality import inspect_raster
                import rasterio
                qa=inspect_raster(path,job)
                qa['attempts']=1
                if job.get('image_layout')=='province':qa.update(packing)
                if (job['quality'].get('processing_mode','quality_filtered')=='quality_filtered' and job['product'] in ('LANDSAT','SENTINEL2')
                        and 'VALUE_RANGE_REVIEW' in qa['flags']):
                    strict=dict(job['quality'],sentinel_cloud_score_min=max(.75,job['quality']['sentinel_cloud_score_min']),
                                landsat_cloud_buffer_m=max(120,job['quality']['landsat_cloud_buffer_m']))
                    from .processing import composite as reprocess
                    image=reprocess(config,dict(job,quality=strict),geometry)
                    download_image(image,job,path)
                    qa=inspect_raster(path,job)
                    qa['attempts']=2
                from .inspect_tiff import inspect
                preview=Path('.province-local/previews')
                if job.get('image_layout')=='province':
                    pass  # TIFF-only: retain numeric QA, do not generate a PNG.
                elif job['quality'].get('processing_mode')=='notebook_tasks':
                    preview=preview/job['product']
                    if len(list(preview.glob('*.png')))<12:
                        inspect(path,preview)
                else:
                    inspect(path,preview)
                if qa['valid_pixel_pct']==0:
                    from .quality import NoValidPixels
                    raise NoValidPixels('No valid pixels; see preview JSON; empty TIFF not uploaded')
                with rasterio.open(path,'r+') as ds:
                    ds.update_tags(PROCESSING_MODE=job['quality'].get('processing_mode','quality_filtered'),SOURCE=job['product'],PERIOD=job['period'],METHOD_VERSION=job['algorithm_version'],
                                   QA_FLAGS=';'.join(qa['flags']),VALID_PIXEL_PCT=str(qa['valid_pixel_pct']),
                                   QC_ATTEMPTS=str(qa['attempts']),CALIBRATION_STATUS='NOT_CALIBRATED' if job['priority']==0 else 'NOT_APPLICABLE')
        else:
            record = write_statistics(image,job,geometry,path,config)
        if path.stat().st_size > job['reserved_bytes']:
            if job.get('image_layout')=='province':
                from task_pipeline.province_image import OutputLimit
                raise OutputLimit('TIFF exceeds staging reservation')
            raise RuntimeError('Output exceeded reservation; no upload performed')
        from .receiver import hashes,validate
        expected=dict(size=str(path.stat().st_size),md5Checksum=hashes(path)[0])
        validate(path,expected,job)
        file_id=drive.upload_verified(job['folder_id'],path)
        audit('uploaded',job_id=job['job_id'],backend='direct')
        result = dict(file_id=file_id,md5Checksum=expected['md5Checksum'],size=expected['size'])
        if job['kind']=='image' and job.get('pipeline_version')==2:
            result['image_qa']=qa
        if job['kind'] == 'table' and job.get('pipeline_version') == 2:
            result['statistics'] = record
        return result


def lossless_tiff(path):
    from rasterio.shutil import copy as copy_raster
    import rasterio
    target=path.with_name(path.stem+'.deflate.tif')
    with rasterio.open(path) as ds:
        float_data=ds.dtypes[0].startswith('float')
    copy_raster(path,target,driver='GTiff',compress='DEFLATE',predictor=3 if float_data else 2,
                tiled=True,blockxsize=256,blockysize=256)
    target.replace(path)
