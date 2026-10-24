"""Bounded Earth Engine downloads → user Drive uploads, matching legacy identity separation.

Each image is one tile below EE's 32 MB uncompressed / 10000-dimension download
limit. No service-account My Drive ownership or shared-folder export is assumed.
"""
import csv
import tempfile
import time
from pathlib import Path
from .common import audit

MAX_DOWNLOAD_BYTES = 32_000_000


def check_tile_limit(config):
    from .sources import SOURCES
    n = config['tile_pixels']
    if n > 10000:
        raise ValueError('Earth Engine download dimensions exceed 10000')
    for product in config['products']:
        if n*n*len(SOURCES[product]['bands'])*4 >= MAX_DOWNLOAD_BYTES:
            raise ValueError('Direct download exceeds 32 MB uncompressed; reduce tile_pixels (512 recommended)')


def download_image(image, job, path, attempts=4):
    import requests
    scale = job['scale']
    bounds = job['tile']['bounds']
    pixels = round((bounds[2]-bounds[0])/scale)
    if pixels*pixels*len(job['bands'])*4 >= MAX_DOWNLOAD_BYTES:
        raise ValueError('Direct download tile exceeds 32 MB')
    # EE's exact-grid mode is CRS + affine + dimensions, WITHOUT region/scale.
    # The affine origin and dimensions already define the complete tile footprint.
    params = dict(crs=job['crs'], crs_transform=job['tile']['transform'],
                  dimensions=[pixels,pixels], format='GEO_TIFF', filePerBand=False)
    # Explicit default value is preserved as NoData metadata by local TIFF rewrite below.
    image = image.unmask(-9999, sameFootprint=False)
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
        if (str(ds.crs) != job['crs'] or not ds.transform.almost_equals(expected)
                or ds.width != pixels or ds.height != pixels or ds.count != len(job['bands'])):
            raise RuntimeError('Earth Engine returned a different tile grid/band layout')
        ds.nodata=-9999
        for index,name in enumerate(job['bands'],1):
            ds.set_band_description(index,name)


def write_statistics(image, job, geometry, path):
    from .earth_engine import statistics
    # Whole-province sufficient statistics from the same image and masks, not tile mean averages.
    info=statistics(image, job, geometry).first().toDictionary().getInfo()
    from .sources import SOURCES
    fields=['ma_tinh','ten_tinh','nam','thang','nguon_anh','period','job_id','algorithm_version',
            'boundary_sha256','scale','crs','valid_area','total_area']
    fields += [band+suffix for band in SOURCES[job['product']]['bands'] for suffix in ('_w','_w2','_sum')]
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        writer.writerow(info)


def transfer(config, drive, job, boundary):
    import ee
    from .earth_engine import composite
    geometry=ee.Geometry(boundary['geometry'])
    image=composite(config,job,geometry)
    suffix='.tif' if job['kind']=='image' else '.csv'
    with tempfile.TemporaryDirectory(prefix='province-') as tmp:
        path=Path(tmp)/(job['prefix']+suffix)
        if job['kind']=='image':
            download_image(image,job,path)
        else:
            write_statistics(image,job,geometry,path)
        if path.stat().st_size > job['reserved_bytes']:
            raise RuntimeError('Output exceeded reservation; no upload performed')
        # Validate locally before any upload. Receiver will independently validate its own copy.
        from .receiver import hashes, validate
        expected=dict(size=str(path.stat().st_size),md5Checksum=hashes(path)[0])
        validate(path,expected,job)
        file_id=drive.upload_verified(job['folder_id'],path)
        audit('uploaded',job_id=job['job_id'],backend='direct')
        return dict(file_id=file_id,md5Checksum=expected['md5Checksum'],size=expected['size'])
