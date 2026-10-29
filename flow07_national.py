"""Monthly country-level Vietnam statistics and resumable, exact-grid national images."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
from xml.sax.saxutils import escape

# Isolate country-level checkpoints from the earlier commune/province flow.
os.environ.setdefault('VNGIS_EE_PROJECT', 'vgis-ee-07')
os.environ.setdefault('VNGIS_DRIVE_FOLDER', 'VNGISDash_2024_FLOW07_NATIONAL'
                      + ('_PILOT' if os.environ.get('VNGIS_MODE', 'pilot') == 'pilot' else ''))
import vngis_2024 as v

COUNTRY = dict(GID_1='VNM', NAME_1='Viet Nam', GID_2='VNM', NAME_2='Viet Nam',
               GID_3='VNM', NAME_3='Viet Nam', TYPE_3='Country')
METHOD = 'NATIONAL_MONTHLY_2024_v1'
DEG = 111319.49079327358
TILE = 512  # 10 Float64 bands < 24 MB, below the direct-download limit.


def national_collection(source):
    """One union feature, so reducers produce one national observation per month."""
    return v.ee.FeatureCollection([v.ee.Feature(source.geometry(maxError=1), COUNTRY)])


def grid(bounds, scale):
    res = scale / DEG
    x0, y0 = math.floor(bounds[0]/res), math.floor(bounds[1]/res)
    x1, y1 = math.ceil(bounds[2]/res), math.ceil(bounds[3]/res)
    return dict(width=x1-x0, height=y1-y0, transform=[res, 0, x0*res, 0, -res, y1*res])


def windows(g, footprint):
    from shapely.geometry import box
    from shapely.prepared import prep
    inside = prep(footprint)
    for row in range(0, g['height'], TILE):
        for col in range(0, g['width'], TILE):
            w, h = min(TILE, g['width']-col), min(TILE, g['height']-row)
            a, _, x, _, e, y = g['transform']
            x, y = x+col*a, y+row*e
            if inside.intersects(box(x, y+h*e, x+w*a, y)):
                yield row, col, w, h


def tile_name(window):
    r, c, w, h = window
    return f'r{r:07d}_c{c:07d}_{w}x{h}.tif'


def tile_transform(g, window):
    r, c, _, _ = window
    a, b, x, d, e, y = g['transform']
    return [a, b, x+c*a, d, e, y+r*e]


def remote_files():
    result = subprocess.run(['rclone', 'lsjson', v.REMOTE_BASE, '--recursive', '--files-only'],
                            capture_output=True, text=True, timeout=600, check=True)
    return {x['Path'] for x in json.loads(result.stdout) if x.get('Size', 0)>0}


def publish(path, relative, known):
    v.check_stop()
    if not v._rclone(['moveto', str(path), f'{v.REMOTE_BASE}/{relative}', *v.RCLONE_COMMON], timeout=900):
        raise RuntimeError(f'Drive upload failed: {relative}; check Drive capacity and credentials')
    known.add(relative)


def fetch(image, g, window, path, bands):
    """Download and validate a bounded window on a fixed national pixel grid."""
    import rasterio
    from affine import Affine
    r, c, w, h = window
    transform = tile_transform(g, window)
    def request():
        url = image.unmask(-9999, sameFootprint=False).toDouble().getDownloadURL(dict(
            crs='EPSG:4326', crs_transform=transform, dimensions=[w, h],
            format='GEO_TIFF', filePerBand=False))
        response = v._http_get(url)
        if response.status_code >= 400:
            raise v._RetryableEEError(f'HTTP {response.status_code}: {response.text[:300]}',
                                      response.headers.get('Retry-After'))
        return response.content
    data = v._ee_call(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.part')
    try:
        with rasterio.MemoryFile(data) as memory, memory.open() as src:
            if (src.width, src.height, src.count) != (w, h, len(bands)):
                raise RuntimeError('Earth Engine returned a different tile layout')
            if not src.transform.almost_equals(Affine(*transform)):
                raise RuntimeError('Earth Engine returned a different pixel grid')
            profile = src.profile.copy()
            profile.update(driver='GTiff', dtype='float64', nodata=-9999, compress='DEFLATE',
                           predictor=3, tiled=True, blockxsize=256, blockysize=256)
            with rasterio.open(tmp, 'w', **profile) as dst:
                dst.write(src.read())
                for i, band in enumerate(bands, 1):
                    dst.set_band_description(i, band)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def fetch_window(image, g, window, base, known, bands, download=fetch):
    relative = f'{base}/tiles/{tile_name(window)}'
    if relative in known:
        return [window]
    path = Path(v.LOCAL_ROOT)/relative
    try:
        download(image, g, window, path, bands)
    except v.TooLargeError:
        r, c, w, h = window
        if min(w, h) <= 128:
            raise
        left, top = (w+1)//2, (h+1)//2
        done = []
        for rr, hh in ((r, top), (r+top, h-top)):
            for cc, ww in ((c, left), (c+left, w-left)):
                if ww and hh:
                    done += fetch_window(image, g, (rr, cc, ww, hh), base, known, bands, download)
        return done
    publish(path, relative, known)
    return [window]


def write_vrt(path, g, completed, bands):
    """Reference uploaded TIFF windows; omitted sea windows are NoData, never zero."""
    import rasterio
    from affine import Affine
    x, a, b, y, d, e = Affine(*g['transform']).to_gdal()
    chunks = [f'<VRTDataset rasterXSize="{g["width"]}" rasterYSize="{g["height"]}">',
              f'<SRS>{escape(rasterio.crs.CRS.from_epsg(4326).to_wkt())}</SRS>',
              f'<GeoTransform>{x},{a},{b},{y},{d},{e}</GeoTransform>',
              f'<Metadata><MDI key="LEVEL">national</MDI><MDI key="METHOD">{METHOD}</MDI></Metadata>']
    for i, band in enumerate(bands, 1):
        chunks += [f'<VRTRasterBand dataType="Float64" band="{i}">',
                   f'<Description>{escape(band)}</Description><NoDataValue>-9999</NoDataValue>']
        for r, c, w, h in completed:
            name = tile_name((r, c, w, h))
            chunks += [f'<ComplexSource><SourceFilename relativeToVRT="1">tiles/{name}</SourceFilename>',
                       f'<SourceBand>{i}</SourceBand><SrcRect xOff="0" yOff="0" xSize="{w}" ySize="{h}"/>',
                       f'<DstRect xOff="{c}" yOff="{r}" xSize="{w}" ySize="{h}"/><NODATA>-9999</NODATA></ComplexSource>']
        chunks += ['</VRTRasterBand>']
    chunks += ['</VRTDataset>']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(chunks), encoding='utf-8')


def publish_image(image, geometry, footprint, kind, month, known):
    scale = 20 if kind == 'DAY' else 500
    bands = v.DAY_BANDS_ALL[:v.DAY_BANDS] if kind == 'DAY' else ['avg_rad', 'cf_cvg']
    base = f'National/{kind}/{v.YEAR}/{month:02d}'
    manifest = f'{base}/complete.json'
    if manifest in known:
        return
    g = grid(footprint.bounds, scale)
    complete = []
    v.log.info(f'National {kind} {v.YEAR}-{month:02d}: grid {g["width"]} x {g["height"]}, nominal {scale} m')
    for index, window in enumerate(windows(g, footprint), 1):
        v.check_stop()
        if v.drive_stop_exists():
            v.request_stop('drive_stop')
            v.check_stop()
        complete += fetch_window(image, g, window, base, known, bands)
        if index % 20 == 0:
            v.log.info(f'{base}: {index} windows verified on Drive')
    path = Path(v.LOCAL_ROOT)/base/f'VNM_{kind}_{v.YEAR}{month:02d}.vrt'
    write_vrt(path, g, complete, bands)
    publish(path, f'{base}/{path.name}', known)
    marker = Path(v.LOCAL_ROOT)/manifest
    marker.write_text(json.dumps(dict(level='national', country='VNM', method=METHOD,
        asset=v.ASSET_ID, year=v.YEAR, month=month, scale_m=scale, bands=bands,
        tile_count=len(complete), grid=g)), encoding='utf-8')
    publish(marker, manifest, known)


def publish_stats(fc, geometry):
    """Country reducers; no average of province/commune averages."""
    day = v.task1_all_months(fc)
    rows = [dict(COUNTRY, **{k:v._clean(p.get(k)) for k in v.T1_FEATURES},
                 YEAR=v.YEAR, MONTH=int(p['MONTH'])) for p in day]
    v.append_parts('day', rows)
    night = v.task3_all_months(geometry, 'VNM', 'Viet Nam', 'VNM', 'Viet Nam')
    v.append_parts('night', [{k:v._clean(value) for k,value in r.items()} for r in night.to_dict('records')])
    v.build_national_csv()
    for name in (v.DAY_CSV, v.NIGHT_CSV):
        path = Path(v.L(name))
        if not path.exists():
            continue
        table = v.pd.read_csv(path)
        table = table.drop(columns=[c for c in v.ADM_COLS if c in table], errors='ignore')
        table = table.rename(columns={'COMMUNE_AREA_HA': 'NATIONAL_AREA_HA'})
        table.insert(0, 'LEVEL', 'national')
        table.insert(1, 'COUNTRY_CODE', 'VNM')
        table.insert(2, 'COUNTRY_NAME', 'Viet Nam')
        table.to_csv(path, index=False, encoding='utf-8-sig')
    v.rclone_sync_once(final=True)


def main():
    v.setup_logging()
    v.init_storage()
    if '--sync-only' in sys.argv:
        v.rclone_sync_once(final=True)
        return 0
    v.MONTHS = [1] if v.MODE == 'pilot' else list(range(1,13))
    v.PARTS_STAMP = f'national_{v.RUN_ID}'
    v.install_signal_handlers()
    timer = threading.Timer(v.MAX_RUNTIME_SEC or 18900, v.request_stop, args=('deadline',))
    timer.daemon = True
    timer.start()
    try:
        if v.drive_stop_exists():
            return 130
        v.init_earth_engine()
        v.log.info(f'National scope: {v.ASSET_ID}; months={v.MONTHS}; project={v.PROJECT_ID}')
        fc = national_collection(v.communes_fc)
        geometry = fc.geometry(maxError=1)
        from shapely.geometry import shape
        footprint = shape(v.ee_getinfo(geometry))
        known = remote_files()
        if 'CSV/day_indices.csv' not in known or 'CSV/night_indices.csv' not in known:
            publish_stats(fc, geometry)
        _, plan = v.fetch_plan(fc, geometry)
        gaps = []
        for m in v.MONTHS:
            choice = plan[m]
            for kind in ('NIGHT','DAY'):
                v.check_stop()
                if kind == 'DAY':
                    window = choice['s2_window']
                    if window is None:
                        gaps.append(f'DAY_{m:02d}')
                        continue
                    image = v.day_image(m, window, geometry).select(v.DAY_BANDS_ALL[:v.DAY_BANDS])
                else:
                    collection = choice['viirs']
                    if collection is None:
                        gaps.append(f'NIGHT_{m:02d}')
                        continue
                    image = v.night_image(m, collection, geometry)
                publish_image(image, geometry, footprint, kind, m, known)
        report = Path(v.L(v.D_CONTROL, 'national_progress.json'))
        report.write_text(json.dumps(dict(level='national', country='VNM', year=v.YEAR,
            months=v.MONTHS, missing=gaps, status='complete_with_gaps' if gaps else 'complete')))
        v.rclone_sync_once(final=True)
        return 0
    except v.StopRequested:
        return 3 if v.STOP_REASON[0] == 'deadline' else 130
    except Exception:
        v.log.exception('National flow failed; remote tiles are retained for the next run')
        return 1
    finally:
        timer.cancel()
        v.rclone_sync_once(final=True)


if __name__ == '__main__':
    raise SystemExit(main())
