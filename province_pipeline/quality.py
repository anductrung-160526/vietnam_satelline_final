"""Conservative QC: same-source reprocessing; anomalies are never filled with another source."""

def out_of_range(info,job):
    if job['product'].startswith(('DMSP','VIIRS')):
        band='stable_lights' if job['product']=='DMSP' else 'avg_rad'
        lo,hi=info.get(band+'_min'),info.get(band+'_max')
        return (lo is not None and lo<0) or (job['product']=='DMSP' and hi is not None and hi>63)
    from .sources import BANDS
    # Deliberately conservative SR envelope; negative atmospheric-correction values are allowed.
    return any((info.get(b+'_min') is not None and info[b+'_min'] < -0.2-1e-6)
               or (info.get(b+'_max') is not None and info[b+'_max'] > 1.6) for b in BANDS)


def reprocess_statistics(info,job,geometry,config):
    if job['quality'].get('processing_mode')=='notebook_tasks':
        return dict(info,qc_attempts=1,qc_status='NOTEBOOK_TASKS')
    if job['quality'].get('processing_mode')=='raw_source':
        return dict(info,qc_attempts=1,qc_status='RAW_UNFILTERED')
    info=dict(info,qc_attempts=1,qc_status='PASS')
    if not out_of_range(info,job):
        return info
    if job['product'] in ('LANDSAT','SENTINEL2') and config is not None:
        from .processing import composite,statistics
        strict=dict(job['quality'])
        strict.update(sentinel_cloud_score_min=max(.75,strict['sentinel_cloud_score_min']),
                      landsat_cloud_buffer_m=max(120,strict['landsat_cloud_buffer_m']))
        candidate=dict(job,quality=strict)
        image=composite(config,candidate,geometry)
        info=statistics(image,candidate,geometry).first().toDictionary().getInfo()
        info.update(qc_attempts=2,qc_status='REPROCESSED_STRICT_MASK',
                    qc_reason='SR_RANGE_REVIEW_STRICT_SAME_SOURCE_SAME_ASSETS',
                    qc_initial_range_flag=True)
    if out_of_range(info,job):
        info['qc_status']='INSUFFICIENT_QUALITY'
    return info


def inspect_raster(path,job):
    """Inspect every tile after download; record anomalies, never erase real changes."""
    import rasterio
    import numpy as np
    valid=0;total=0;flags=[];mins={};maxs={}
    with rasterio.open(path) as ds:
        for _,window in ds.block_windows(1):
            data=ds.read(window=window,masked=True)
            primary=data[:6] if job.get('quality',{}).get('processing_mode')=='raw_source' and job['product'] in ('LANDSAT','SENTINEL2') else data
            common=~np.ma.getmaskarray(primary).any(axis=0)
            total+=common.size;valid+=int(common.sum())
            for i,b in enumerate(job['bands']):
                values=data[i].compressed()
                if values.size:
                    if not np.isfinite(values).all():
                        raise ValueError('Non-finite valid raster pixels')
                    mins[b]=min(mins.get(b,float('inf')),float(values.min()))
                    maxs[b]=max(maxs.get(b,float('-inf')),float(values.max()))
    if not valid:
        flags.append('NO_VALID_PIXELS')
    bounds={**{b+'_min':v for b,v in mins.items()},**{b+'_max':v for b,v in maxs.items()}}
    # Source VIIRS can contain negative background: inspect, but do not alter raw source.
    if job['variant']!='source' and out_of_range(bounds,job):
        flags.append('VALUE_RANGE_REVIEW')
    if mins and all(mins[b]==maxs[b] for b in mins):
        flags.append('CONSTANT_TILE_REVIEW')
    if job['product'].startswith(('DMSP','VIIRS')):
        flags.append('TRANSIENT_LIGHTS_RESIDUAL_REVIEW')
    return dict(valid_pixel_pct=100*valid/total if total else 0,flags=flags)


class NoValidPixels(RuntimeError):
    pass
