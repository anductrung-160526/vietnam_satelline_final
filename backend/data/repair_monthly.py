"""Đối chiếu raw/filtered VIIRS; sửa vào kho mới theo quy tắc FILTER đã ghi.

Không tạo quan sát khi cf_cvg=0. Không sửa file gốc hoặc tự nạp SQLite.
"""
import argparse
from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import warnings

import numpy as np
import rasterio
from rasterio.shutil import copy as raster_copy

from .calculate_ntl import read_manifest, windows
from .fractional_area import load_area_model
from .prepare_grdp import write_csv

FILTER = 'cf_cvg=0->NoData; negative->0; value>max(3*annual median, median+5)->annual median'
REPAIR_VERSION = 'verified_raw_cf_positive_annual_median_v1'


def valid(image, band, window):
    values = image.read(band, window=window).astype('float64')
    mask = image.read_masks(band, window=window).astype(bool) & np.isfinite(values) & (values != -9999)
    return values, mask


def canonical_months(raw_images, window, domain):
    arrays, clouds, raw_counts, cf_counts, cf_available = [], [], [], [], []
    for image in raw_images:
        radiation, rm = valid(image, 1, window)
        cloud, cm = valid(image, 2, window)
        raw_counts.append(int((domain & rm).sum()))
        cf_counts.append(int((domain & cm & (cloud > 0)).sum()))
        cf_available.append(int((domain & cm & (cloud >= 0)).sum()))
        good = domain & rm & cm & (cloud > 0)
        arrays.append(np.where(good, np.maximum(radiation, 0), np.nan))
        clouds.append(np.where(good, cloud, np.nan))
    stack = np.stack(arrays)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        baseline = np.nanmedian(stack, axis=0)
    limit = np.maximum(3*baseline, baseline+5)
    filtered = np.where(stack > limit, baseline, stack)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        annual = np.nanmedian(filtered, axis=0)
    return filtered, annual, np.isfinite(filtered).sum(axis=0), clouds, raw_counts, cf_counts, cf_available


def same_grid(a, b):
    return (a.crs, a.transform, a.shape) == (b.crs, b.transform, b.shape)


def unresolved(reports, diagnosis):
    """Chưa đọc/đối chiếu pixel thì để số đếm trống, không ghi 0 quan sát giả."""
    for row in reports:
        row['diagnosis'] = diagnosis
        for field in list(row):
            if field.endswith('_pixels'):
                row[field] = None
    return reports, {}, None


def process_year(month_rows, raw_paths, annual_row, output, area_model, apply=False):
    code, year = month_rows[0]['province_code'], month_rows[0]['year']
    by_month = {r['month']: r for r in month_rows}
    missing = [m for m in range(1,13) if m not in by_month or (code,year,m) not in raw_paths]
    if missing:
        return [dict(province_code=code, year=year, month=r['month'], diagnosis='MISSING_RAW_OR_FILTERED_MONTHS',
                     missing_months=json.dumps(missing), repaired=False) for r in month_rows], {}, None
    monthly_report = [dict(province_code=code, year=year, month=m, raw_valid_pixels=0, positive_cf_pixels=0, valid_cf_pixels=0,
                           expected_valid_pixels=0, processed_valid_pixels=0, lost_valid_pixels=0,
                           invalid_extra_pixels=0, wrong_value_pixels=0, diagnosis='', repaired=False,
                           raw_path=raw_paths[code,year,m], processed_path=str(by_month[m]['path'])) for m in range(1,13)]
    with ExitStack() as context:
        processed = [context.enter_context(rasterio.open(by_month[m]['path'])) for m in range(1,13)]
        raw = [context.enter_context(rasterio.open(raw_paths[code,year,m])) for m in range(1,13)]
        template = processed[0]
        if any(not same_grid(template, image) for image in raw+processed):
            return unresolved(monthly_report,'GRID_MISMATCH_REQUIRES_REVIEW')
        if any(image.count != 2 or image.descriptions != ('avg_rad','cf_cvg') or image.scales != (1.,1.) or image.offsets != (0.,0.) for image in raw):
            return unresolved(monthly_report,'RAW_BANDS_OR_SCALE_UNSUPPORTED')
        if any(image.count != 1 or image.scales[0] != 1 or image.offsets[0] != 0 or
               image.tags().get('FILTER','').replace(' ','').lower() != FILTER.replace(' ','').lower() for image in processed):
            return unresolved(monthly_report,'FILTER_RULE_UNVERIFIED')
        weights = area_model.weights(code, template)
        annual_old = context.enter_context(rasterio.open(annual_row['path'])) if annual_row else None
        if annual_old and not same_grid(template, annual_old):
            return unresolved(monthly_report,'ANNUAL_GRID_MISMATCH_REQUIRES_REVIEW')
        profile = template.profile.copy()
        profile.update(driver='GTiff', count=1, dtype='float32', nodata=-9999, compress='DEFLATE')
        annual_candidate = output/f'{code}_{year}_annual_candidate.tif'
        annual_writer = context.enter_context(rasterio.open(annual_candidate, 'w', **profile))
        support_path = output/f'{code}_{year}_valid_month_count.tif'
        support_profile = dict(profile, dtype='uint8', nodata=255)
        support = context.enter_context(rasterio.open(support_path, 'w', **support_profile))
        annual_mismatch = 0
        counts_hist = np.zeros(13, dtype='int64')
        areas_hist = np.zeros(13)
        for window in windows(template.height, template.width):
            domain = weights[window.toslices()] > 0
            filtered, annual, count, clouds, raw_counts, cf_counts, cf_available = canonical_months(raw, window, domain)
            for i, image in enumerate(processed):
                old, old_mask = valid(image,1,window)
                old_mask &= domain
                expected_mask = np.isfinite(filtered[i])
                r = monthly_report[i]
                r['raw_valid_pixels'] += raw_counts[i];r['positive_cf_pixels'] += cf_counts[i]
                r['valid_cf_pixels'] += cf_available[i]
                r['expected_valid_pixels'] += int(expected_mask.sum());r['processed_valid_pixels'] += int(old_mask.sum())
                r['lost_valid_pixels'] += int((expected_mask & ~old_mask).sum())
                r['invalid_extra_pixels'] += int((old_mask & ~expected_mask).sum())
                common = old_mask & expected_mask
                r['wrong_value_pixels'] += int((common & ~np.isclose(old, filtered[i], rtol=1e-5, atol=1e-4, equal_nan=True)).sum())
            mask = np.isfinite(annual)
            if annual_old:
                old, old_mask = valid(annual_old,1,window)
                old_mask &= domain
                annual_mismatch += int((mask != old_mask).sum())
                annual_mismatch += int((mask & old_mask & ~np.isclose(annual,old,rtol=1e-5,atol=1e-4)).sum())
            else:annual_mismatch += int(mask.sum())
            annual_writer.write(np.where(mask,annual,-9999).astype('float32'),1,window=window)
            support.write(np.where(domain,count,255).astype('uint8'),1,window=window)
            for n in range(13):
                select = domain & (count == n)
                counts_hist[n] += int(select.sum())
                areas_hist[n] += float(weights[window.toslices()][select].sum())
        annual_writer.set_band_description(1,'avg_rad_annual')
        annual_writer.update_tags(SOURCE='VIIRS MEDIAN_OF_FILTERED_VIIRS_MONTHS', YEAR=str(year), MONTHS_USED='12',
                                  REPAIR_VERSION=REPAIR_VERSION, province_code=code)
        support.set_band_description(1,'valid_month_count')
        support.update_tags(YEAR=str(year), province_code=code, SOURCE='COUNT_VALID_RAW_CF_POSITIVE_MONTHS', REPAIR_VERSION=REPAIR_VERSION)
        changed = [i for i,r in enumerate(monthly_report) if r['lost_valid_pixels'] or r['invalid_extra_pixels'] or r['wrong_value_pixels']]
        updates = {}
        if apply and changed:
            writers = {}
            cloud_sums, cloud_counts = defaultdict(float), defaultdict(int)
            for i in changed:
                path=output/f'{code}_{year}_{i+1:02}_filtered_repaired.tif'
                writers[i] = context.enter_context(rasterio.open(path,'w',**profile))
                updates[code,year,i+1] = path
            for window in windows(template.height,template.width):
                filtered, _, _, clouds, _, _, _ = canonical_months(raw,window,weights[window.toslices()]>0)
                for i,writer in writers.items():
                    values=filtered[i];mask=np.isfinite(values)
                    writer.write(np.where(mask,values,-9999).astype('float32'),1,window=window)
                    cloud_sums[i] += float(np.nansum(clouds[i]));cloud_counts[i] += int(mask.sum())
            for i,writer in writers.items():
                writer.set_band_description(1,'avg_rad_filtered')
                writer.update_tags(FILTER=FILTER, SOURCE='VIIRS', PERIOD=f'{year}-{i+1:02}', province_code=code,
                                   CF_CVG_MEAN=str(cloud_sums[i]/cloud_counts[i]) if cloud_counts[i] else '',
                                   REPAIR_VERSION=REPAIR_VERSION, RAW_SOURCE=raw_paths[code,year,i+1])
        for i,r in enumerate(monthly_report):
            problem = i in changed
            r['repaired'] = bool(apply and problem)
            r['diagnosis'] = ('REPAIRED_FILTER_MISMATCH' if apply else 'REPAIRABLE_FILTER_MISMATCH') if problem else (
                'MISSING_CF_COVERAGE' if not r['valid_cf_pixels'] else
                'NO_CLOUD_FREE_OBSERVATIONS' if not r['positive_cf_pixels'] else
                'NO_VALID_RADIANCE_DESPITE_CF' if not r['expected_valid_pixels'] else 'MATCHES_RAW_FILTER_RULE')
        positive = sum(counts_hist[1:])
        support_report = dict(province_code=code, year=year, available_month_files=12,
                              valid_month_min=next((n for n in range(1,13) if counts_hist[n]),None),
                              valid_month_max=next((n for n in range(12,0,-1) if counts_hist[n]),None),
                              valid_month_mean=float(sum(n*counts_hist[n] for n in range(13))/positive) if positive else None,
                              pixels_without_observations=int(counts_hist[0]), area_without_observations_km2=float(areas_hist[0]),
                              area_with_one_month_km2=float(areas_hist[1]), support_path=str(support_path),
                              annual_mismatch_pixels=annual_mismatch, annual_repaired=bool(apply and (changed or annual_mismatch)))
    # Tất cả handles đã đóng trước khi đổi COG/đường dẫn, tương thích Windows.
    if support_report['annual_repaired']:
        annual_path=output/f'{code}_{year}_annual_repaired.tif'
        raster_copy(annual_candidate,annual_path,driver='COG',COMPRESS='DEFLATE',RESAMPLING='NEAREST')
        updates[code,year,0]=annual_path
    annual_candidate.unlink(missing_ok=True)
    return monthly_report,updates,support_report


def repair(manifest, db, output, area_model, apply=False):
    records=read_manifest(manifest)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    with sqlite3.connect(db) as con:
        raw={(r[0],r[1],r[2]):r[3] for r in con.execute("SELECT province_code,year,month,path FROM demo_asset WHERE kind='raw' AND source='VIIRS'")}
    groups=defaultdict(list);annual={}
    for r in records:
        if r['source']!='VIIRS':continue
        if r['month']:groups[r['province_code'],r['year']].append(r)
        else:annual[r['province_code'],r['year']]=r
    audits=[];updates={};supports=[]
    for i,(key,months) in enumerate(sorted(groups.items()),1):
        print(f'Đối chiếu raw/filtered {i}/{len(groups)}: {key[0]}/{key[1]}',flush=True)
        try:
            report,changed,support=process_year(months,raw,annual.get(key),output,area_model,apply)
        except (OSError,rasterio.errors.RasterioError) as error:
            report=[dict(province_code=key[0],year=key[1],month=r['month'],diagnosis='SOURCE_READ_ERROR',repaired=False,error=str(error)) for r in months]
            changed={};support=None
        audits.extend(report);updates.update(changed)
        if support:supports.append(support)
    result=[]
    for r in records:
        key=(r['province_code'],r['year'],r['month'])
        result.append(dict(r,path=str(updates.get(key,r['path']))))
    for (code,year,month),path in updates.items():
        if month==0 and (code,year) not in annual:
            result.append(dict(groups[code,year][0],month=0,path=str(path)))
    fields=sorted({k for r in audits for k in r})
    write_csv(output/'monthly_recovery_audit.csv',audits,fields)
    if supports:write_csv(output/'annual_observation_support.csv',supports,list(supports[0]))
    write_csv(output/'manifest_repaired.csv',result,list(result[0]))
    summary=dict(apply_repairs=apply,method=REPAIR_VERSION,boundary_sha256=area_model.metadata['sha256'],
                 months_audited=len(audits),monthly_repaired=sum(r.get('repaired',False) for r in audits),
                 annual_repaired=sum(r['annual_repaired'] for r in supports),
                 diagnosis_counts={d:sum(r['diagnosis']==d for r in audits) for d in sorted({r['diagnosis'] for r in audits})},
                 manifest=str(output/'manifest_repaired.csv'),database_changed=False,source_images_overwritten=False)
    (output/'recovery_report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--db',type=Path,default=Path(__file__).with_name('vngis.db'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--boundaries',type=Path)
    parser.add_argument('--boundary-metadata',type=Path)
    parser.add_argument('--apply-repairs',action='store_true')
    args=parser.parse_args()
    model=load_area_model(args.root,args.boundaries,args.boundary_metadata)
    output=args.output or args.root/'_demo_repaired'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    print(json.dumps(repair(args.manifest,args.db,output,model,args.apply_repairs),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
