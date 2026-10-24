"""Exactly two consolidated panels with explicit fixed-source missingness."""
import csv
import io
import math
import os
from functools import lru_cache
from pathlib import Path
from .common import atomic_json
from .sources import BANDS, NTL_PACKAGE, DAY_PACKAGE, SOURCES

IDENTITY = ['MA_TINH','NAME_1','GID_1','YEAR','MONTH','TIME','FREQUENCY','SOURCE','SOURCE_COLLECTION',
            'UNIT','PROVINCE_AREA_HA','METHOD_VERSION','CALIBRATION_VERSION','CALIBRATION_STATUS',
            'NATIVE_RESOLUTION_M','ANALYSIS_RESOLUTION_M','SOURCE_SELECTION_REASON','IS_FALLBACK',
            'VALID_OBSERVATIONS','VALID_AREA_PCT','QC_ATTEMPTS','QC_STATUS','PROCESSING_MODE','DATA_STATUS','ERROR','QA_FLAGS']
NIGHT = ['TNL','SOL_NTL','MAT_DO_NTL','MEAN_RAD','STD_RAD','MIN_RAD','MAX_RAD','SPATIAL_CV',
         'LIT_PIXELS','LIT_AREA_HA','ELECTRIFICATION_RATIO_PCT','LIT_POP_PROXY','CLOUD_FREE_OBS',
         'TNL_MA3','TNL_MOM_GROWTH_PCT','TNL_YOY_GROWTH_PCT','THAY_DOI_NTL_PCT',
         'SOL_YEAR','MAT_DO_NTL_YEAR','THAY_DOI_NTL_YEAR_PCT','VALID_MONTHS_YEAR','YEAR_DATA_STATUS',
         'SOL_NTL_CALIBRATED']
DAY = [b+s for b in BANDS+['NDVI','NDBI','MNDWI','BSI'] for s in ('_mean','_stdDev')]


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError,ValueError):
        return None


@lru_cache(maxsize=1)
def gadm_codes():
    with (Path(__file__).parent/'data/gadm41_province_crosswalk.csv').open(encoding='utf-8-sig',newline='') as stream:
        return {r['ma_tinh']:r['gid_1'] for r in csv.DictReader(stream)}


def base_row(config,spec):
    p,product,period = spec['province'],spec['product'],spec['period']
    definition=SOURCES[product]
    if config['quality'].get('processing_mode')=='notebook_tasks':
        from task_pipeline.methods import source_spec
        definition=source_spec(product,period)
    return dict(MA_TINH=p['ma_tinh'],NAME_1=p['ten_tinh'],GID_1=gadm_codes().get(p['ma_tinh'],''),
        YEAR=int(period[:4]),MONTH=int(period[5:]) if len(period)==7 else None,TIME=period,
        FREQUENCY='monthly' if len(period)==7 else 'annual',SOURCE='VIIRS' if product.startswith('VIIRS') else product,
        SOURCE_COLLECTION=';'.join(definition['collections']),UNIT=definition['unit'],
        METHOD_VERSION=config['algorithm_version'],CALIBRATION_VERSION=None,
        CALIBRATION_STATUS='NOT_CALIBRATED' if spec['night'] else 'NOT_APPLICABLE',
        SOURCE_SELECTION_REASON='FIXED_PERIOD_POLICY',IS_FALLBACK=False,
        NATIVE_RESOLUTION_M={'DMSP':927.67,'VIIRS_MONTHLY':463.83}.get(product,SOURCES[product]['scale']),ANALYSIS_RESOLUTION_M=SOURCES[product]['scale'] if spec['night'] else 30,
        PROCESSING_MODE=config['quality'].get('processing_mode','quality_filtered'),
        DATA_STATUS='PENDING',ERROR='NOT_CALCULATED_YET',QA_FLAGS='')


def quantitative(row,record,job):
    from .aggregate import row_statistics
    computed = row_statistics(dict(record),job['product'])
    area = number(record.get('province_area')) or number(record.get('total_area'))
    valid = number(record.get('valid_area')) or 0
    row.update(PROVINCE_AREA_HA=area/10000 if area else None,
               VALID_AREA_PCT=100*computed['valid_fraction'],
               VALID_OBSERVATIONS=number(record.get('source_observations')))
    row.update(QC_ATTEMPTS=record.get('qc_attempts',1),QC_STATUS=record.get('qc_status','PASS'))
    if record.get('qc_initial_range_flag'):
        row['QA_FLAGS']='REPROCESSED_STRICT_MASK'
    notebook=job['quality'].get('processing_mode')=='notebook_tasks'
    raw=job['quality'].get('processing_mode')=='raw_source' or notebook
    # Never publish low-quality numeric indices as valid observations.
    if valid <= 0 or (not raw and (row['VALID_AREA_PCT'] < job['quality']['min_valid_area_pct'] or record.get('qc_status')=='INSUFFICIENT_QUALITY')):
        row.update(DATA_STATUS='INSUFFICIENT_QUALITY',ERROR='LOW_VALID_PIXEL_COVERAGE')
        return
    row['DATA_STATUS']='OK_NOTEBOOK' if notebook else 'OK_RAW' if raw else 'OK'
    row['ERROR']=''
    product = job['product']
    if product.startswith(('DMSP','VIIRS')):
        band = 'stable_lights' if product=='DMSP' else 'avg_rad'
        mean = number(computed.get(band+'_mean'))
        std = number(computed.get(band+'_std'))
        sol = number(computed.get('sol_ntl'))
        litarea = number(record.get('lit_area'))
        row.update(TNL=sol,SOL_NTL=sol,MAT_DO_NTL=sol/(area/1e6) if sol is not None and area else None,
            MEAN_RAD=mean,STD_RAD=std,MIN_RAD=number(record.get(band+'_min')),
            MAX_RAD=number(record.get(band+'_max')),SPATIAL_CV=std/mean if std is not None and mean and mean>0 else None,
            LIT_PIXELS=number(record.get('lit_pixels')),LIT_AREA_HA=litarea/10000 if litarea is not None else None,
            ELECTRIFICATION_RATIO_PCT=100*litarea/area if litarea is not None and area else None,
            CLOUD_FREE_OBS=row['VALID_OBSERVATIONS'])
        row['QA_FLAGS']='UNHARMONIZED;TRANSIENT_LIGHTS_NOT_FULLY_VALIDATED'
    else:
        for band in BANDS+['NDVI','NDBI','MNDWI','BSI']:
            row[band+'_mean']=number(computed.get(band+'_mean'))
            row[band+'_stdDev']=number(computed.get(band+'_std'))
        # Scaled SR may be negative or >1. Flag; do not silently clip scientific values.
        if any(row[b+'_mean'] is not None and not -0.2 <= row[b+'_mean'] <= 1.6 for b in BANDS):
            row['QA_FLAGS']='REFLECTANCE_RANGE_REVIEW'

    if notebook:
        notebook_metrics(row,record,job)
    if raw and not notebook:
        row['QA_FLAGS']+=';RAW_UNFILTERED'
        if row['VALID_AREA_PCT'] < job['quality']['min_valid_area_pct']:
            row['QA_FLAGS']+=';LOW_COVERAGE_REVIEW'
        if row.get('CLOUD_FREE_OBS')==0:
            row['QA_FLAGS']+=';NO_CLOUD_FREE_OBSERVATIONS'


def percent(current,previous):
    a,b=number(current),number(previous)
    return (a/b-1)*100 if a is not None and b is not None and b>0 else None


def temporal(rows, anomaly_z=6):
    """Same source, contiguous periods only. Null rows break windows and growth."""
    import statistics
    lookup={(r['MA_TINH'],r['TIME']):r for r in rows}
    annual={}
    for row in rows:
        y,m,code=row['YEAR'],row['MONTH'],row['MA_TINH']
        if row['FREQUENCY']=='annual':
            prev=lookup.get((code,str(y-1)),{})
            if row['SOURCE']==prev.get('SOURCE'):
                row['THAY_DOI_NTL_PCT']=percent(row.get('SOL_NTL'),prev.get('SOL_NTL'))
            row.update(SOL_YEAR=row.get('SOL_NTL'),MAT_DO_NTL_YEAR=row.get('MAT_DO_NTL'),
                       THAY_DOI_NTL_YEAR_PCT=row.get('THAY_DOI_NTL_PCT'),
                       YEAR_DATA_STATUS='COMPLETE' if row['DATA_STATUS'] in ('OK','OK_RAW','OK_NOTEBOOK') else row['DATA_STATUS'])
            continue
        def ago(n):
            ordinal=y*12+m-1-n
            return lookup.get((code,f'{ordinal//12}-{ordinal%12+1:02}'),{})
        prev=ago(1)
        if prev.get('SOURCE')==row['SOURCE']:
            row['TNL_MOM_GROWTH_PCT']=percent(row.get('TNL'),prev.get('TNL'))
        prevyear=ago(12)
        if prevyear.get('SOURCE')==row['SOURCE']:
            row['TNL_YOY_GROWTH_PCT']=percent(row.get('TNL'),prevyear.get('TNL'))
        values=[r.get('TNL') if r.get('SOURCE')==row['SOURCE'] else None for r in (ago(2),ago(1),row)]
        if all(number(v) is not None for v in values):
            row['TNL_MA3']=sum(values)/3
        annual.setdefault((code,y),[]).append(row)
    # Arithmetic temporal mean of *monthly province sums*, NOT a pixel-weighted annual raster.
    # Require all 12 months; label this method explicitly in metadata.
    sums={}
    for key,group in annual.items():
        valid=[r for r in group if r['DATA_STATUS'] in ('OK','OK_RAW','OK_NOTEBOOK') and number(r.get('SOL_NTL')) is not None]
        if len(group)==12 and len(valid)==12:
            sums[key]=sum(r['SOL_NTL'] for r in valid)/12
        for r in group:
            r.update(VALID_MONTHS_YEAR=len(valid),YEAR_DATA_STATUS='COMPLETE' if key in sums else 'INCOMPLETE')
    for key,group in annual.items():
        for r in group:
            if key in sums and r['DATA_STATUS'] in ('OK','OK_RAW','OK_NOTEBOOK'):
                r['SOL_YEAR']=sums[key]
                r['MAT_DO_NTL_YEAR']=sum(x['MAT_DO_NTL'] for x in group)/12
                r['THAY_DOI_NTL_YEAR_PCT']=percent(sums[key],sums.get((key[0],key[1]-1)))
    # Robust, same-calendar-month temporal review; never suppress real changes automatically.
    peer_groups={}
    for r in rows:
        peer_groups.setdefault((r['MA_TINH'],r['SOURCE'],r['MONTH']),[]).append(r)
    for row in rows:
        peers=[r.get('TNL') for r in peer_groups[(row['MA_TINH'],row['SOURCE'],row['MONTH'])]
               if r['TIME']!=row['TIME'] and number(r.get('TNL')) is not None]
        if len(peers)>=5 and number(row.get('TNL')) is not None:
            med=statistics.median(peers); mad=statistics.median(abs(x-med) for x in peers)
            if mad>0 and abs(row['TNL']-med)/(1.4826*mad)>anomaly_z:
                row['QA_FLAGS']+=';TEMPORAL_OUTLIER_REVIEW'


def build_panels(config,state,metadata):
    from .profiles import table_specs
    from .jobs import table_job
    outputs={'night_indices.csv':[],'day_indices.csv':[]}
    for spec in table_specs(config):
        job=table_job(config,spec,metadata)
        row=base_row(config,spec)
        existing=state['jobs'].get(job['job_id'],{})
        status=existing.get('status','PENDING')
        record=state.get('statistics',{}).get(job['job_id'])
        if record is not None:
            if record.get('job_id')!=job['job_id'] or record.get('ma_tinh')!=spec['province']['ma_tinh'] or record.get('period')!=spec['period']:
                raise ValueError('Statistics report identity mismatch')
            quantitative(row,record,job)
        elif status in ('MISSING_SOURCE','INSUFFICIENT_QUALITY','FAILED','BLOCKED_OUTPUT'):
            row.update(DATA_STATUS=status,ERROR=existing.get('error',status))
        outputs['night_indices.csv' if spec['night'] else 'day_indices.csv'].append(row)
    temporal(outputs['night_indices.csv'],config['quality']['anomaly_robust_z'])
    flag_day_outliers(outputs['day_indices.csv'],config['quality']['anomaly_robust_z'])
    if config['quality'].get('processing_mode')=='notebook_tasks':
        notebook_rolling(outputs['night_indices.csv'])
    for name,rows in outputs.items():
        rows.sort(key=lambda r:(r['MA_TINH'],r['TIME']))
    return outputs


def csv_bytes(name,rows):
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=IDENTITY+(NIGHT if name.startswith('night') else DAY),extrasaction='ignore')
    writer.writeheader();writer.writerows(rows)
    return stream.getvalue().encode('utf-8-sig')


def publish(config,drive,state,metadata):
    from .controller import control_folders
    import hashlib
    index=dict(profile=config['run_profile'],method_version=config['algorithm_version'],quality=config['quality'],files=[])
    archive_remote(config,drive,index)
    outputs=build_panels(config,state,metadata)
    local=Path('.province-local/panels');local.mkdir(parents=True,exist_ok=True)
    from collections import Counter
    report=dict(profile=config['run_profile'],processing=config['quality'].get('processing_mode','quality_filtered'),
                stage=state.get('current_stage'),notice='PENDING means not calculated yet, not missing source.',
                rows={name:dict(Counter(r['DATA_STATUS'] for r in rows)) for name,rows in outputs.items()})
    atomic_json(local/'quality_summary.json',report)
    for name,rows in outputs.items():
        package=NTL_PACKAGE if name.startswith('night') else DAY_PACKAGE
        parent=drive.folder(drive.folder(config['drive_root_id'],package),'data_processed')
        content=csv_bytes(name,rows)
        (local/name).write_bytes(content)
        info=drive.write_verified_bytes(parent,name,content)
        index['files'].append(dict(info,local_relative_path=f'{package}/data_processed/{name}',
                                   rows=len(rows),sha256=hashlib.sha256(content).hexdigest()))
    drive.write_json(control_folders(drive,config['drive_root_id'])['root'],'panels.json',index)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as stream:
            stream.write('### '+config['run_profile']+' / '+config['quality'].get('processing_mode','quality_filtered')+' — '+str(state.get('current_stage','pending'))+'\n\n')
            stream.write('CSV rows marked PENDING are placeholders, not completed observations.\n\n')
            for name,counts in report['rows'].items():
                stream.write('- '+name+': '+str(counts)+'\n')
            stream.write('\nDMSP–VIIRS calibration: NOT_CALIBRATED. No source substitution.\n')
    return index


def sync(config,drive,root,control):
    """Stable aggregate CSVs are small and retained on Drive; exact file version verified."""
    from .common import local_path
    from .receiver import hashes
    index=drive.read_json(control,'panels.json')
    if not index:
        return
    for f in index['files']:
        expected=f['local_relative_path']
        allowed={f'{NTL_PACKAGE}/data_processed/night_indices.csv',f'{DAY_PACKAGE}/data_processed/day_indices.csv'}
        if expected not in allowed:
            raise ValueError('Unexpected aggregate destination')
        dest=local_path(root,expected);dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and hashes(dest)[1]==f['sha256']:
            continue
        part=dest.with_suffix('.csv.part')
        before=drive.metadata(f['id'])
        if str(before['version'])!=str(f['version']):
            raise RuntimeError('Panel changed; retry next receiver cycle')
        drive.download(f['id'],part)
        md5,sha=hashes(part)
        after=drive.metadata(f['id'])
        if (sha!=f['sha256'] or md5!=f['md5Checksum'] or part.stat().st_size!=int(f['size'])
                or str(after['version'])!=str(before['version'])):
            raise ValueError('Consolidated panel checksum/version mismatch')
        with part.open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream)
            required=IDENTITY+(NIGHT if dest.name.startswith('night') else DAY)
            if reader.fieldnames!=required or sum(1 for _ in reader)!=f['rows']:
                raise ValueError('Consolidated panel schema mismatch')
        if config.get('volume_marker'):
            from .receiver import verify_volume
            if verify_volume(config) != Path(root):
                raise ValueError('Wrong external disk before CSV commit')
        if dest.exists():
            backup=local_path(root,'.panel_history/'+dest.stem+'_'+hashes(dest)[1]+'.csv')
            backup.parent.mkdir(parents=True,exist_ok=True)
            # Preserve previous visible CSV only when method/scope changes, not every batch.
            old_index_path=Path(root)/'.panels.json'
            if old_index_path.exists():
                import json
                previous=json.loads(old_index_path.read_text(encoding='utf-8'))
                if (previous.get('profile'),previous.get('method_version')) != (index.get('profile'),index.get('method_version')):
                    if not backup.exists():
                        import shutil
                        shutil.copyfile(dest,backup)
        os.replace(part,dest)
    atomic_json(Path(root)/'.panels.json',index)
    write_docs(root)


def write_docs(root):
    import json
    policy=dict(source_policy={'night':'DMSP 2004-2013 annual; VIIRS 2014-2025 monthly',
                              'day':'LANDSAT 2004-2017 monthly; SENTINEL2 2018-2025 monthly'},
        missing='CSV empty field = null; never substitute another source or period',
        calibration='NOT_CALIBRATED. No cross-sensor growth or invented calibrated values.',
        annual='VIIRS SOL_YEAR = arithmetic mean of 12 valid monthly province SOL values; not an official annual image; repeated on monthly rows, do not sum.',
        units='DMSP DN; VIIRS nW/cm2/sr. SOL is pixel sum on source grid. Density=SOL/natural province area km2. Native grid sums are NOT cross-sensor comparable.',
        electrification='ELECTRIFICATION_RATIO_PCT is lit-area percentage, NOT households with electricity.',
        population='LIT_POP_PROXY stays null: no validated population model supplied.',
        quality='MOD14A1 high-confidence fire mask, observation mask, SCL+Cloud Score+, buffered Landsat QA. Ship/background residuals and DMSP saturation/blooming are not fully corrected; review flags retained.',
        raw='raw_data means clipped source products for night / masked annual dry-season composites for day, NOT raw sensor scenes.',
        reference=['https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_CLOUD_SCORE_PLUS_V1_S2_HARMONIZED',
                   'https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD14A1'])
    snapshot=Path(root)/'.panels.json'
    if snapshot.exists():
        policy['quality_settings']=json.loads(snapshot.read_text(encoding='utf-8')).get('quality',{})
    if policy.get('quality_settings',{}).get('processing_mode')=='notebook_tasks':
        policy['quality']='Notebook QA60 bits 10/11; Task1 CLOUDY_PIXEL_PERCENTAGE<85 with same-month fallback and mean/stdDev at 50m EPSG4326. Task2 images use 0/15/30-day windows only when no scenes exist; provenance retained. VIIRS mean, VCMSLCFG then VCMCFG, lit>=1.5; no fire/Cloud Score+ or 80% coverage gate.'
        policy['raw']='Task2 masked monthly day composites at 20m Sentinel/30m Landsat; night catalog composites. EPSG4326 fixed tiles, lossless float64; not untouched sensor scenes.'
        policy['population']='LIT_POP_PROXY follows Task3 sum of radiance above lit threshold; NOT a population estimate.'
    if policy.get('quality_settings',{}).get('processing_mode')=='raw_source':
        policy['quality']='No additional QA/cloud/fire/background/observation-count filtering. Provider masks retained. SR scaling and median compositing remain; this is NOT untouched sensor scenes.'
        policy['raw']='Clipped/resampled catalog source products; day TIFF is unfiltered annual composite, monthly CSV comes from unfiltered monthly composites. RAW_UNFILTERED is NOT quality-validated.'
    for package,columns in ((NTL_PACKAGE,IDENTITY+NIGHT),(DAY_PACKAGE,IDENTITY+DAY)):
        dest=Path(root)/package/'metadata';dest.mkdir(parents=True,exist_ok=True)
        atomic_json(dest/'processing_policy.json',policy)
        # Complete schema plus formulas and semantic caveats, kept with each delivered panel.
        dictionary={c:{'null':'not observed / not applicable; consult DATA_STATUS',
                       'definition':DEFINITIONS.get(c,c)} for c in columns}
        for band in BANDS+['NDVI','NDBI','MNDWI','BSI']:
            for suffix in ('mean','stdDev'):
                if band+'_'+suffix in dictionary:
                    dictionary[band+'_'+suffix]['definition']='Area-weighted population '+suffix+' of monthly masked pixel '+band+' on common 30m grid'
        if policy.get('quality_settings',{}).get('processing_mode')=='notebook_tasks' and 'LIT_POP_PROXY' in dictionary:
            dictionary['LIT_POP_PROXY']['definition']='Task3: sum(radiance where >=1.5); DMSP extension uses DN threshold5. Not number of people.' if 'LIT_POP_PROXY' in dictionary else ''
        atomic_json(dest/'indices_codebook.json',dictionary)

DEFINITIONS={
 'TNL':'sum(valid light pixels) on documented source grid; alias SOL_NTL',
 'SOL_NTL':'sum(valid light pixels), not harmonized across sources',
 'MAT_DO_NTL':'SOL_NTL / natural province area km2',
 'SPATIAL_CV':'area-weighted population STD_RAD / MEAN_RAD; null if mean<=0',
 'TNL_MA3':'mean of three contiguous valid VIIRS monthly SOL observations',
 'TNL_MOM_GROWTH_PCT':'100*(TNL/current previous month - 1); positive denominator, same source',
 'TNL_YOY_GROWTH_PCT':'100*(TNL/same month prior year - 1); same source',
 'THAY_DOI_NTL_PCT':'DMSP annual growth; null on monthly rows',
 'THAY_DOI_NTL_YEAR_PCT':'growth of complete same-source annual SOL; no 2013-2014 crossing',
 'MEAN_RAD':'area-weighted light mean: DN for DMSP, radiance for VIIRS',
 'STD_RAD':'area-weighted population standard deviation in source units',
 'ELECTRIFICATION_RATIO_PCT':'100*lit area/natural province area; NOT real electrification rate',
 'LIT_POP_PROXY':'null: population data/model not supplied',
 'CLOUD_FREE_OBS':'mean source cf_cvg; definition/units depend on source',
 'SOL_NTL_CALIBRATED':'null until independent intersensor calibration is validated',
 'VALID_AREA_PCT':'100*common-mask valid raster area / rasterized province area',
 'LIT_AREA_HA':'sum(pixelArea for valid light>=source threshold)/10000',
 'LIT_PIXELS':'count of valid light pixels above configured source-specific threshold',
 'SOL_YEAR':'DMSP annual SOL or mean of 12 valid VIIRS monthly SOL; repeated in monthly rows',
}


def flag_day_outliers(rows,anomaly_z=6):
    import statistics
    groups={}
    for row in rows:
        groups.setdefault((row['MA_TINH'],row['SOURCE'],row['MONTH']),[]).append(row)
    for group in groups.values():
        for band in ('NDVI','NDBI','MNDWI','BSI'):
            field=band+'_mean'
            values=[r[field] for r in group if number(r.get(field)) is not None]
            if len(values)<6:
                continue
            med=statistics.median(values);mad=statistics.median(abs(v-med) for v in values)
            for row in group:
                if mad>0 and number(row.get(field)) is not None and abs(row[field]-med)/(1.4826*mad)>anomaly_z:
                    row['QA_FLAGS']+=';'+band+'_TEMPORAL_OUTLIER_REVIEW'


def archive_remote(config,drive,new_index):
    """Preserve visible previous-method CSVs before publishing new empty placeholders."""
    import hashlib
    from .controller import control_folders
    control=control_folders(drive,config['drive_root_id'])['root']
    old=drive.read_json(control,'panels.json')
    if not old or (old.get('profile'),old.get('method_version')) == (new_index.get('profile'),new_index.get('method_version')):
        return
    folder=drive.folder(control,'panel_history')
    for f in old['files']:
        backup_name=Path(f['local_relative_path']).stem+'_'+f['sha256']+'.csv'
        backup=drive.find(folder,backup_name)
        if backup:
            if hashlib.sha256(drive.read_bytes(backup['id'])).hexdigest()!=f['sha256']:
                raise ValueError('Archived panel checksum mismatch')
            continue  # a previous interrupted publish already secured the old bytes
        meta=drive.metadata(f['id'])
        if str(meta['version'])!=str(f['version']):
            raise RuntimeError('Previous panel changed; refusing to overwrite before backup')
        content=drive.read_bytes(f['id'])
        if hashlib.sha256(content).hexdigest()!=f['sha256']:
            raise ValueError('Previous panel checksum mismatch before backup')
        drive.write_verified_bytes(folder,backup_name,content)
    drive.write_json(folder,'index_'+__import__('hashlib').sha256(str(old).encode()).hexdigest()+'.json',old)


def notebook_metrics(row,record,job):
    p=job['product']
    row['QA_FLAGS']+=';NOTEBOOK_TASKS;NOT_HARMONIZED'
    row['SOURCE_COLLECTION']=record.get('actual_source_collections',row['SOURCE_COLLECTION'])
    row['ANALYSIS_RESOLUTION_M']=50 if p in ('LANDSAT','SENTINEL2') else job['scale']
    row['UNIT']=job['source_definition']['unit']
    if p in ('LANDSAT','SENTINEL2'):
        for b in BANDS+['NDVI','NDBI','MNDWI','BSI']:
            row[b+'_mean']=number(record.get(b+'_mean'))
            row[b+'_stdDev']=number(record.get(b+'_stdDev'))
        return
    b='stable_lights' if p=='DMSP' else 'avg_rad'
    for suffix,out in (('_mean','MEAN_RAD'),('_stdDev','STD_RAD'),('_min','MIN_RAD'),('_max','MAX_RAD')):
        row[out]=number(record.get(b+suffix))
    row['TNL']=row['SOL_NTL']=number(record.get(b+'_sum'))
    area=row.get('PROVINCE_AREA_HA')
    row['MAT_DO_NTL']=row['SOL_NTL']/(area/100) if row['SOL_NTL'] is not None and area else None
    count=number(record.get('lit_pixels'));total=number(record.get('notebook_valid_pixels'))
    row['LIT_PIXELS']=int(count) if count is not None else None
    row['LIT_AREA_HA']=count*(25 if p=='VIIRS_MONTHLY' else 100) if count is not None else None
    row['ELECTRIFICATION_RATIO_PCT']=100*count/total if count is not None and total and total>0 else None
    row['LIT_POP_PROXY']=number(record.get('notebook_lit_pop_proxy'))
    if count==0 and total and total>0:row['LIT_POP_PROXY']=0.0
    mean,std=row.get('MEAN_RAD'),row.get('STD_RAD')
    row['SPATIAL_CV']=std/mean if std is not None and mean and mean>0 else 0.0 if mean is not None else None
    for key in ('TNL','SOL_NTL','MEAN_RAD','STD_RAD','MIN_RAD','MAX_RAD','SPATIAL_CV','LIT_POP_PROXY'):
        if row.get(key) is not None:row[key]=round(row[key],4)
    for key in ('PROVINCE_AREA_HA','LIT_AREA_HA','ELECTRIFICATION_RATIO_PCT'):
        if row.get(key) is not None:row[key]=round(row[key],2)
    if row.get('CLOUD_FREE_OBS') is not None:row['CLOUD_FREE_OBS']=round(row['CLOUD_FREE_OBS'],1)


def notebook_rolling(rows):
    groups={}
    for row in rows:
        if row['SOURCE']=='VIIRS' and row['DATA_STATUS']=='OK_NOTEBOOK':
            groups.setdefault(row['MA_TINH'],[]).append(row)
    for group in groups.values():
        for i,row in enumerate(group):
            window=group[max(0,i-2):i+1]
            row['TNL_MA3']=sum(r['TNL'] for r in window)/len(window)
            ordinals=[int(r['TIME'][:4])*12+int(r['TIME'][5:]) for r in window]
            if ordinals[-1]-ordinals[0]!=len(ordinals)-1:
                row['QA_FLAGS']+=';NONCONSECUTIVE_OBSERVATIONS'
            # Notebook rolling(min_periods=1) on observed rows. Flag any skipped month.
            y,m=int(row['TIME'][:4]),int(row['TIME'][5:])
            if i:
                prev=group[i-1];py,pm=int(prev['TIME'][:4]),int(prev['TIME'][5:])
                # Preserve null on a missing immediate previous month rather than
                # mislabel multi-month growth as month-on-month.
                if (y-py)*12+m-pm==1:row['TNL_MOM_GROWTH_PCT']=percent(row['TNL'],prev['TNL'])
