"""Use explicit OGC WKT for EE, preserving the existing equal-area grid and tile IDs."""
from functools import lru_cache


@lru_cache(maxsize=16)
def ee_crs(crs):
    from rasterio.crs import CRS
    # EE Projection accepts OGC WKT. WKT1 avoids newer WKT2-only constructs while
    # spelling out the ellipsoid, projection parameters, axes and units explicitly.
    return CRS.from_user_input(crs).to_wkt(version='WKT1_GDAL')


def same_crs(actual, expected):
    from rasterio.crs import CRS
    return actual is not None and CRS.from_user_input(actual) == CRS.from_user_input(expected)


def probe_download_projection(config):
    """Read-only 4x4 constant-image request. No satellite retrieval or Drive writes.

    Let the live EE service validate both projection parsing and the exact-grid
    thumbnail request, not merely the Python SDK's local argument validation.
    Never print/persist the signed URL. Success still does not validate source images.
    """
    import ee
    crs=ee_crs(config['crs'])
    if ee.Projection(crs).nominalScale().getInfo() <= 0:
        raise RuntimeError('Earth Engine projection probe returned an invalid scale')
    params=dict(crs=crs,crs_transform=[30,0,0,0,-30,120],dimensions=[4,4],
                format='GEO_TIFF',filePerBand=False)
    url=ee.Image.constant(1).toFloat().getDownloadURL(params)
    if not url:
        raise RuntimeError('Earth Engine projection/download request probe returned no URL')
