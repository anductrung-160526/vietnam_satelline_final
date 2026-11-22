"""F: đối chiếu ảnh/CSV/SQLite và mask GeoTIFF, không thay kết quả D/E đã xuất."""
import argparse
import csv
from datetime import datetime
import json
import math
from pathlib import Path
import sqlite3

import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.shutil import copy as raster_copy

from .calculate_ntl import windows,ntl_stats,fit_log_model,LIT_THRESHOLD,BACKGROUND
from .dataset import (write_snapshot,make_snapshot,checked_snapshot,migrate_demo,register_snapshot,
                      file_signature,signature_status,DEMO_SCHEMA_VERSION)
from .fractional_area import load_area_model
from .load_demo import backup_database,read_rows
from .prepare_grdp import provinces
from .field_contract import check_fields


def equivalent(a,b):
    if a in (None,'') or b in (None,''):return a in (None,'') and b in (None,'')
    try:return math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-8)
    except (ValueError,TypeError):return str(a)==str(b)


def compare_models(directory):
    path=Path(directory)/'calculation_models.csv'
    models=read_rows(path)
    required={'model','alpha','beta','n','price_basis','r2','stats_version','training_period'}
    if models and not required.issubset(models[0]):raise ValueError('calculation_models.csv thiếu cột; kiểm tra dấu phân cách CSV gốc.')
    gdp={r['price_basis']:r for r in models if r['model']=='gdp_log_regression'}
    if len(gdp)!=sum(r['model']=='gdp_log_regression' for r in models):raise ValueError('Trùng mô hình cơ sở giá.')
    points=set()
    pairs={basis:[] for basis in gdp}
    for row in read_rows(Path(directory)/'night_economy.csv'):
        model=gdp.get(row.get('grdp_price_basis'))
        if row.get('model_n') not in (None,''):
            if not model or not equivalent(row['model_n'],model['n']):raise ValueError('Số điểm mô hình khác metadata kết quả.')
            if not math.isclose(float(row['model_beta']),float(model['beta']),abs_tol=1e-6,rel_tol=1e-10):
                raise ValueError('Beta mô hình khác metadata kết quả.')
            if row['model_training_period']!=model['training_period']:raise ValueError('Thời kỳ mô hình khác kết quả.')
        if row.get('predicted_gdp') not in (None,''):
            if not model or int(row['month'])!=0:raise ValueError('Ước lượng thiếu mô hình hoặc bị gán thành GRDP tháng.')
            light=row.get(model.get('light_basis','sol'))
            if light in (None,'') or float(light)<=0:raise ValueError('Ước lượng dùng ánh sáng thiếu/không dương.')
            expected=math.exp(float(model['alpha'])+float(model['beta'])*math.log(float(light)))
            if not math.isclose(expected,float(row['predicted_gdp']),rel_tol=1e-10,abs_tol=1e-6):
                raise ValueError('Ước lượng GRDP không khớp mô hình đã xuất.')
        if row.get('paired')=='True':
            points.add((row.get('province_code') or row['gid_1'],row['year']))
            if row['grdp_price_basis'] in pairs:
                pairs[row['grdp_price_basis']].append((float(row[gdp[row['grdp_price_basis']].get('light_basis','sol')]),float(row['gdp'])))
    if gdp and any(int(float(m['n']))!=len(points) for m in gdp.values()):
        raise ValueError('Số cặp chung khác số điểm mô hình.')
    for basis,model in gdp.items():
        fitted=fit_log_model(pairs[basis],minimum=10)
        if fitted is None or any(not equivalent(fitted[field],model[field]) for field in ('alpha','beta','r2','n')):
            raise ValueError('Hệ số/R² không khớp mẫu chung đã xuất.')
    return len(models)


def compare_csv_sql(connection,directory,class_csv=None,validation_csv=None):
    """Kiểm mọi dòng nhập, không chỉ so tổng số dòng hoặc vài ví dụ."""
    checked={};errors=[]
    gid={r['gid_1']:r['ma_tinh'] for r in provinces()}
    def mismatch(table,key,field):
        if len(errors)<20:errors.append(dict(table=table,key=list(key),field=field))
    for table in ('ntl_annual','ntl_monthly','night_data','night_economy'):
        path=Path(directory)/(table+'.csv')
        if not path.exists():raise ValueError(f'Thiếu CSV để kiểm chứng: {path}')
        rows=read_rows(path);seen=set()
        columns={r[1] for r in connection.execute(f'PRAGMA table_info({table})')} if table.startswith('ntl_') else set()
        for row in rows:
            code=(row.get('province_code') or gid.get(row.get('gid_1')) or '').zfill(2)
            year,month=int(row['year']),int(row.get('month') or 0)
            basis=row.get('grdp_price_basis','') if table=='night_economy' else ''
            key=(code,year,month,basis)
            if key in seen:raise ValueError(f'CSV trùng khóa {table}: {key}')
            seen.add(key)
            if table.startswith('ntl_'):
                sql=f'SELECT * FROM {table} WHERE province_code=? AND year=?'
                args=[code,year]
                if table=='ntl_monthly':sql+=' AND month=?';args.append(month)
                saved=connection.execute(sql,args).fetchone()
                if saved is None:mismatch(table,key,'missing_row');continue
                for field in set(row)&columns:
                    if not equivalent(row[field],saved[field]):mismatch(table,key,field)
            else:
                saved=connection.execute('SELECT payload FROM demo_result WHERE province_code=? AND year=? AND month=? AND table_name=? AND price_basis=?',
                                         (code,year,month,table,basis)).fetchone()
                if saved is None:mismatch(table,key,'missing_row');continue
                payload=json.loads(saved['payload'])
                for field,value in row.items():
                    if not equivalent(value,payload.get(field)):mismatch(table,key,field)
                if table=='night_economy' and basis in ('so_sanh','hien_hanh'):
                    price=connection.execute('SELECT * FROM economy_prices WHERE province_code=? AND year=? AND price_basis=?',(code,year,basis)).fetchone()
                    if price:
                        for field,target in [('gdp','grdp'),('population','population'),('unit','unit'),('price_base_year','price_base_year'),('is_provisional','is_provisional'),('economy_source','source')]:
                            if not equivalent(row.get(field),price[target]):mismatch('economy_prices',key,field)
        checked[table]=len(rows)
    if class_csv:
        rows=read_rows(class_csv)
        for row in rows:
            key=(row['province_code'].zfill(2),int(row['year']),int(row['month']),int(row['class_index']))
            saved=connection.execute('SELECT * FROM light_class WHERE province_code=? AND year=? AND month=? AND class_index=?',key).fetchone()
            if saved is None:mismatch('light_class',key,'missing_row');continue
            for field,target in [('class_area_km2','area_km2'),('lower_bound','lower_bound'),('upper_bound','upper_bound'),('unit','unit')]:
                if not equivalent(row[field],saved[target]):mismatch('light_class',key,field)
            summary=connection.execute('SELECT class_area_pcts FROM light_class_summary WHERE province_code=? AND year=? AND month=?',key[:3]).fetchone()
            if summary is None or not equivalent(row['class_area_pct'],json.loads(summary[0])[key[3]]):
                mismatch('light_class_summary',key,'class_area_pct')
        checked['light_class']=len(rows)
    if validation_csv:
        rows=read_rows(validation_csv)
        for row in rows:
            key=(row['province_code'].zfill(2),int(row['year']),int(row['month']))
            saved=connection.execute('SELECT * FROM light_class_summary WHERE province_code=? AND year=? AND month=?',key).fetchone()
            if saved is None:mismatch('light_class_summary',key,'missing_row');continue
            for field in set(row)&set(saved.keys()):
                if not equivalent(row[field],saved[field]):mismatch('light_class_summary',key,field)
        checked['light_class_summary']=len(rows)
    if errors:raise ValueError('CSV/SQLite không khớp: '+json.dumps(errors,ensure_ascii=False))
    checked['calculation_models']=compare_models(directory)
    return checked


def inspect_asset(row,area_model,export_dir,cached=None,processed_path=None):
    """Ảnh gốc giữ nguyên; bản tải được crop/mask riêng nếu còn pixel ngoài tỉnh."""
    source=Path(row['path']).resolve()
    if not source.is_file():raise FileNotFoundError(f'Ảnh đã đăng ký bị mất: {source}')
    if (cached and cached.get('boundary_sha256')==area_model.metadata['sha256']
            and cached['source']['path']==str(source) and signature_status(cached['source'])=='ready'
            and signature_status(cached['export'])=='ready'
            and (row['kind']!='processed' or 'statistics' in cached)
            and (row['kind']!='classes' or (processed_path is not None and cached.get('source_radiance',{}).get('path')==str(Path(processed_path).resolve())
                                            and signature_status(cached.get('source_radiance'))=='ready'))):
        return cached
    source_info=file_signature(source,True)
    outside=inside=0
    with rasterio.open(source) as image:
        weights=area_model.weights(row['province_code'],image)
        domain=weights>0
        yy,xx=np.nonzero(domain)
        if not yy.size:raise ValueError(f'Ảnh không giao tỉnh {row["province_code"]}: {source}')
        crop=Window(int(xx.min()),int(yy.min()),int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1))
        for window in windows(image.height,image.width):
            region=domain[window.toslices()]
            for band in range(1,image.count+1):
                mask=image.read_masks(band,window=window).astype(bool)
                values=image.read(band,window=window)
                mask &= np.isfinite(values)
                outside+=int((mask & ~region).sum());inside+=int((mask & region).sum())
                if row['kind']=='classes' and (mask & region & (values>4)).any():
                    raise ValueError(f'Mã lớp ngoài 0–4: {source}')
        needs_copy=outside>0 or crop.width!=image.width or crop.height!=image.height
        export=source
        if needs_copy:
            export_dir=Path(export_dir);export_dir.mkdir(parents=True,exist_ok=True)
            export=export_dir/f"{row['province_code']}_{row['year']}_{row['month']:02}_{row['kind']}_{source_info['sha256'][:12]}.tif"
            temporary=export.with_suffix('.temporary.tif')
            nodata=image.nodata
            if nodata is None:
                if image.dtypes[0].startswith('float'):nodata=-9999
                else:raise ValueError('Ảnh số nguyên thiếu NoData; không tự đoán mã thiếu.')
            profile=image.profile.copy()
            profile.update(driver='GTiff',height=int(crop.height),width=int(crop.width),
                           transform=image.window_transform(crop),nodata=nodata)
            try:
                with rasterio.open(temporary,'w',**profile) as output:
                    for window in windows(int(crop.height),int(crop.width)):
                        original=Window(window.col_off+crop.col_off,window.row_off+crop.row_off,window.width,window.height)
                        region=domain[original.toslices()]
                        for band in range(1,image.count+1):
                            values=image.read(band,window=original)
                            mask=image.read_masks(band,window=original).astype(bool)&np.isfinite(values)&region
                            output.write(np.where(mask,values,nodata).astype(image.dtypes[band-1]),band,window=window)
                            if image.descriptions[band-1]:output.set_band_description(band,image.descriptions[band-1])
                        output.update_tags(**image.tags())
                    output.scales=image.scales;output.offsets=image.offsets
                    output.update_tags(MASK_RULE='positive_pixel_polygon_intersection',BOUNDARY_SHA256=area_model.metadata['sha256'],SOURCE_SHA256=source_info['sha256'])
                raster_copy(temporary,export,driver='COG',COMPRESS='DEFLATE',RESAMPLING='NEAREST')
            finally:temporary.unlink(missing_ok=True)
    # Kiểm lại bản xuất, không suy "đạt" chỉ từ thao tác ghi mask.
    with rasterio.open(export) as checked:
        domain=area_model.weights(row['province_code'],checked)>0
        export_outside=0
        for window in windows(checked.height,checked.width):
            for band in range(1,checked.count+1):
                export_outside+=int((checked.read_masks(band,window=window).astype(bool)&~domain[window.toslices()]).sum())
        if export_outside:raise ValueError(f'Bản xuất còn pixel ngoài tỉnh: {export}')
    result=dict(source=source_info,export=file_signature(export,True),boundary_sha256=area_model.metadata['sha256'],
                mask_rule='positive_pixel_polygon_intersection',outside_valid_values_before=outside,
                outside_valid_values_after=export_outside,inside_valid_values=inside,masked_copy=needs_copy)
    if row['kind']=='processed':
        result['statistics']=ntl_stats(source,LIT_THRESHOLD[row['source']],BACKGROUND[row['source']],weights)
    if row['kind']=='classes':
        if not processed_path:raise ValueError('Lớp sáng thiếu đăng ký ảnh bức xạ nguồn.')
        from .build_light_classes import saved_areas
        with rasterio.open(source) as image:tags=image.tags()
        checked=saved_areas(source,processed_path,json.loads(tags['THRESHOLDS']),int(tags['REFERENCE_YEAR']),True,weights)
        result['class_areas']=checked['areas']
        result['source_radiance']=file_signature(processed_path)
    return result


def verify(root,fix_report,db,publish=False,output=None,area_model=None):
    root,db=Path(root).resolve(),Path(db).resolve()
    fixed=json.loads(Path(fix_report).read_text(encoding='utf-8'))
    if not fixed.get('published'):raise ValueError('Cần fix_report đã published để kiểm bộ app hiện tại.')
    original_output=Path(fixed['output']).resolve()
    directory=original_output/'indices';manifest=Path(fixed['manifest']).resolve()
    if not original_output.is_relative_to(root) or not manifest.is_relative_to(root):raise ValueError('Báo cáo nằm ngoài kho --root.')
    if not db.is_file():raise ValueError('Database app không tồn tại.')
    original_db_hash=file_signature(db,True)['sha256']
    version=fixed['economy_validation']['stats_version']
    declared={int(float(r['stats_version'])) for r in read_rows(directory/'night_economy.csv') if r.get('stats_version')}
    if declared!={version}:raise ValueError('stats_version trong CSV khác báo cáo hoặc chưa xác định được.')
    # Bootstrap metadata cho CSV v9 đã có; không chạy lại raster/statistics.
    snapshot=checked_snapshot(directory)
    if snapshot is None:snapshot=make_snapshot(directory,version)
    if snapshot['stats_version']!=version:raise ValueError('Phiên bản CSV không khớp fix_report.')
    output=Path(output).resolve() if output else root/'_demo_verify'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    if not output.is_relative_to(root):raise ValueError('Thư mục kết quả phải nằm trong --root.')
    output.mkdir(parents=True,exist_ok=False)
    candidate=output/'candidate.db'
    with sqlite3.connect(db) as source,sqlite3.connect(candidate) as target:source.backup(target)
    area_model=area_model or load_area_model(root)
    with sqlite3.connect(candidate) as connection:
        connection.row_factory=sqlite3.Row;migrate_demo(connection)
        checked=compare_csv_sql(connection,directory,fixed['classification'].get('class_csv'),fixed['classification'].get('validation_csv'))
        field_contract=check_fields(directory)
        records=read_rows(manifest)
        with connection:register_snapshot(connection,snapshot,directory,records)
        keys={(r['province_code'].zfill(2),int(r['year']),int(r['month'])) for r in records}
        keys|={(code,year,0) for code,year,month in keys}
        assets=[dict(r) for r in connection.execute('SELECT * FROM demo_asset')
                if (r['province_code'],r['year'],r['month']) in keys]
        processed_paths={(r['province_code'],r['year'],r['month']):r['path'] for r in assets if r['kind']=='processed'}
        numeric_rows={}
        for table in ('ntl_annual','ntl_monthly'):
            for row in read_rows(directory/(table+'.csv')):
                numeric_rows[(row['province_code'].zfill(2),int(row['year']),int(row.get('month') or 0))]=row
        existing={(r['province_code'],r['year'],r['month'],r['kind']):json.loads(r['payload']) for r in connection.execute('SELECT * FROM demo_asset_check')}
        results=[]
        for i,row in enumerate(assets,1):
            key=(row['province_code'],row['year'],row['month'],row['kind'])
            payload=inspect_asset(row,area_model,output/'exports',existing.get(key),processed_paths.get(key[:3]))
            if row['kind']=='processed':
                expected=numeric_rows.get(key[:3])
                if expected is None:raise ValueError(f'Ảnh xử lý không có dòng CSV tương ứng: {key}')
                fields=['sol','sol_raw','valid_pixels','rad_mean','rad_std','rad_min','rad_max','lit_pixels','lit_sol',
                        'lit_area_km2','lit_pixel_pct','cloud_free_obs','valid_area_km2']
                for field in fields:
                    if field in expected and not equivalent(payload['statistics'].get(field),expected[field]):
                        raise ValueError(f'Ảnh/CSV không khớp {key}, {field}; cần tính lại D/E đúng nguồn.')
            if row['kind']=='classes':
                stored=[r[0] for r in connection.execute('SELECT area_km2 FROM light_class WHERE province_code=? AND year=? AND month=? ORDER BY class_index',key[:3])]
                if len(stored)!=5 or any(not equivalent(a,b) for a,b in zip(stored,payload['class_areas'])):
                    raise ValueError(f'Diện tích COG lớp/SQLite không khớp: {key}')
            results.append((*key,json.dumps(payload,ensure_ascii=False)))
            if i%100==0 or i==len(assets):print(f'Đã kiểm tra ảnh xuất {i}/{len(assets)}',flush=True)
        with connection:connection.executemany('INSERT OR REPLACE INTO demo_asset_check VALUES(?,?,?,?,?)',results)
        if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite không qua integrity_check.')
    if make_snapshot(directory,version)['dataset_id']!=snapshot['dataset_id']:
        raise ValueError('CSV thay đổi trong khi kiểm chứng; chưa xuất bản.')
    if any(signature_status(item)!='ready' for item in snapshot['files'].values()):
        raise ValueError('CSV đổi trong khi kiểm chứng; chưa xuất bản.')
    for entry in results:
        item=json.loads(entry[-1])
        if signature_status(item['source'])!='ready' or signature_status(item['export'])!='ready':
            raise ValueError('Ảnh thay đổi trong khi kiểm chứng; chưa xuất bản.')
    report=dict(dataset_id=snapshot['dataset_id'],stats_version=version,demo_schema_version=DEMO_SCHEMA_VERSION,
                field_contract_rows=len(field_contract),
                checked_csv_rows=checked,assets_checked=len(results),masked_export_copies=sum(json.loads(r[-1])['masked_copy'] for r in results),
                outside_valid_values_after=0,published=False,backup=None,output=str(output),
                scope='all_registered_assets_for_manifest_periods',source_indices=str(directory),
                models=read_rows(directory/'calculation_models.csv'))
    if not (directory/'dataset_manifest.json').is_file():write_snapshot(directory,version)
    from .prepare_grdp import write_csv
    write_csv(output/'field_contract.csv',field_contract,list(field_contract[0]))
    if publish:
        if file_signature(db,True)['sha256']!=original_db_hash:
            raise ValueError('Database app đã đổi trong lúc chuẩn bị; chưa ghi đè snapshot mới hơn.')
        report['backup']=backup_database(db)
        with sqlite3.connect(candidate) as source,sqlite3.connect(db) as target:source.backup(target)
        report['published']=True
    (output/'integration_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--fix-report',required=True,type=Path)
    parser.add_argument('--db',type=Path,default=Path(__file__).with_name('vngis.db'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--boundaries',type=Path)
    parser.add_argument('--boundary-metadata',type=Path)
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    model=load_area_model(args.root,args.boundaries,args.boundary_metadata)
    print(json.dumps(verify(args.root,args.fix_report,args.db,args.publish,args.output,model),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
