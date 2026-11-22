"""P1: chuẩn bị Moran và thay đổi 2020–2024 từ snapshot đã kiểm chứng F."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

import numpy as np
import rasterio
from rasterio.shutil import copy as raster_copy
from rasterio.warp import transform_geom
from shapely.geometry import mapping

from .dataset import file_signature,signature_status,snapshot_status
from .fractional_area import load_area_model,AREA_METHOD
from .load_demo import backup_database
from .prepare_grdp import write_csv
from .spatial_analysis import queen_neighbors,global_moran,compare_rasters,CHANGE_NAMES,CHANGE_COLORS
from backend.api.provenance import available_asset,current_id,observation_info

SPATIAL_VERSION=1
SCHEMA='''CREATE TABLE IF NOT EXISTS spatial_run(
 run_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, payload TEXT NOT NULL
);'''


def write_cog(path,array,profile,nodata,description,tags):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as temp:
        draft=Path(temp)/'draft.tif'
        with rasterio.open(draft,'w',**profile,dtype=str(array.dtype),nodata=nodata) as image:
            image.write(array,1);image.set_band_description(1,description);image.update_tags(**tags)
        raster_copy(draft,path,driver='COG',compress='DEFLATE',overview_resampling='NEAREST')
    with rasterio.open(path) as image:
        if not np.array_equal(image.read(1),array):raise ValueError('COG xuất không khớp mảng đã tính.')
    return file_signature(path,True)


def thresholds(connection,code,year):
    summary=connection.execute('SELECT * FROM light_class_summary WHERE province_code=? AND year=? AND month=0',(code,year)).fetchone()
    rows=connection.execute('SELECT * FROM light_class WHERE province_code=? AND year=? AND month=0 ORDER BY class_index',(code,year)).fetchall()
    if summary is None or len(rows)!=5:raise ValueError(f'Thiếu phân lớp {code}/{year}.')
    if [r['class_index'] for r in rows]!=list(range(5)):raise ValueError('Mã lớp không đủ 0–4.')
    breaks=[r['lower_bound'] for r in rows[1:]]
    from .build_light_classes import validate_breaks
    validate_breaks(breaks)
    if rows[0]['lower_bound']!=0 or rows[-1]['upper_bound'] is not None:raise ValueError('Cận lớp đầu/cuối không đúng.')
    for i in range(4):
        if rows[i]['upper_bound']!=breaks[i]:raise ValueError('Khoảng lớp không liên tục.')
    return dict(breaks=breaks,method_version=summary['method_version'],reference_year=summary['reference_year'],
                unit=rows[0]['unit'])


def build(root,integration_report,db,year_start=2020,year_end=2024,permutations=9999,seed=20261123,
          tolerance_m=1.,publish=False,output=None,area_model=None,expected_count=63):
    root,db=Path(root).resolve(),Path(db).resolve()
    if not 2004<=year_start<year_end<=2025:raise ValueError('Chọn hai năm tăng dần trong 2004–2025.')
    if not 0<=seed<2**32-2025:raise ValueError('Seed phải là số nguyên không âm nhỏ hơn 2^32−2025.')
    verified=json.loads(Path(integration_report).read_text(encoding='utf-8'))
    if not verified.get('published') or verified.get('outside_valid_values_after')!=0:raise ValueError('Cần báo cáo F đã published và đạt mask.')
    baseline=file_signature(db,True)
    output=Path(output).resolve() if output else root/'_demo_spatial'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    if not output.is_relative_to(root):raise ValueError('Thư mục kết quả phải trong --root.')
    output.mkdir(parents=True,exist_ok=False);candidate=output/'candidate.db'
    with sqlite3.connect(db) as source,sqlite3.connect(candidate) as target:source.backup(target)
    area_model=area_model or load_area_model(root)
    if len(area_model.polygons)!=expected_count:raise ValueError(f'Cần đúng {expected_count} ranh giới tỉnh, không dùng bản rút gọn.')
    neighbors=queen_neighbors(area_model.polygons,tolerance_m)
    sources={};assets={};moran=[];values_rows=[]
    with sqlite3.connect(candidate) as connection:
        connection.row_factory=sqlite3.Row
        dataset=current_id(connection)
        if dataset!=verified['dataset_id']:raise ValueError('Database khác snapshot đã kiểm F; chạy lại F đúng bộ hiện tại.')
        versions=snapshot_status(connection)
        if not versions.get(dataset,{}).get('available'):raise ValueError('CSV snapshot đã mất/đổi; cần kiểm lại F.')
        provinces={r['province_code']:r['province_name'] for r in connection.execute('SELECT * FROM province')}
        if set(provinces)!=set(neighbors):raise ValueError('Danh mục tỉnh và ranh giới không khớp.')
        for year in range(year_start,year_end+1):
            values={};reasons={}
            for code in sorted(neighbors):
                row=connection.execute('SELECT * FROM ntl_annual WHERE province_code=? AND year=?',(code,year)).fetchone()
                if row is None:reasons[code]='missing_annual_row';continue
                if row['source']!='VIIRS':reasons[code]='not_viirs';continue
                if 'status' in row.keys() and row['status']=='GIA_LAP':reasons[code]='simulated_data';continue
                info=observation_info(connection,code,year,0,versions)
                item=available_asset(connection,code,year,0,'processed')
                if not info['consistent'] or info['dataset_id']!=dataset or not item or item['verification_status']!='verified':
                    raise ValueError(f'Nguồn {code}/{year} chưa khớp F; không dùng số lưu cũ để tính P1.')
                record=connection.execute("SELECT payload FROM demo_asset_check WHERE province_code=? AND year=? AND month=0 AND kind='processed'",(code,year)).fetchone()
                check=json.loads(record[0])
                if check['boundary_sha256']!=area_model.metadata['sha256']:raise ValueError('Ranh giới khác bộ kiểm F.')
                checked_sol=check.get('statistics',{}).get('sol')
                if row['sol'] is not None and (checked_sol is None or not np.isclose(row['sol'],checked_sol,rtol=1e-10,atol=1e-8)):
                    raise ValueError('SOL trong SQLite khác thống kê ảnh đã kiểm F.')
                if row['area_km2'] is None or not np.isclose(row['area_km2'],area_model.areas[code],rtol=1e-8,atol=1e-8):
                    raise ValueError('Diện tích tỉnh trong SQLite khác ranh giới đã kiểm F.')
                sources[item['path']]=dict(check['source'],province_code=code,year=year)
                assets[(code,year)]=item['path']
                value=row['sol_density']
                if value is None:reasons[code]='missing_sol_density';continue
                # Moran dùng sol_density chưa hiệu chỉnh của bảng năm: sol / diện tích tự nhiên.
                if row['area_km2'] is None or row['area_km2']<=0 or not np.isclose(value,row['sol']/row['area_km2'],rtol=1e-6,atol=1e-6):
                    raise ValueError('sol_density không khớp SOL/diện tích tỉnh.')
                values[code]=float(value)
            result=global_moran(values,neighbors,permutations,seed+year)
            result.update(year=year,variable='sol_density',unit='nW/cm²/sr/km²',tolerance_m=tolerance_m,dataset_id=dataset)
            result['exclusion_details']={c:reasons.get(c,r) for c,r in result['excluded'].items()}
            moran.append(result)
            for code in sorted(neighbors):
                values_rows.append(dict(province_code=code,province_name=provinces[code],year=year,
                                        variable='sol_density',value=values.get(code),included=code in result['included'],
                                        reason=result['exclusion_details'].get(code,''),dataset_id=dataset))
        changes=[];transitions=[];exports={};reference_spec=None
        for index,code in enumerate(sorted(neighbors),1):
            base=dict(province_code=code,province_name=provinces[code],year_start=year_start,year_end=year_end,dataset_id=dataset)
            if (code,year_start) not in assets or (code,year_end) not in assets:
                changes.append(dict(base,status='missing_viirs_pair'));continue
            spec=thresholds(connection,code,year_start)
            if spec!=thresholds(connection,code,year_end):raise ValueError('Hai năm khác ngưỡng/phiên bản/đơn vị; không so sánh lớp.')
            if reference_spec is not None and spec!=reference_spec:raise ValueError('Các tỉnh không cùng bộ ngưỡng cố định.')
            reference_spec=spec
            summary,classes,delta,profile=compare_rasters(assets[(code,year_start)],assets[(code,year_end)],code,area_model,spec['breaks'])
            summary.update(base,thresholds=spec['breaks'],classification_method=spec['method_version'],
                           area_method=AREA_METHOD,source_start=assets[(code,year_start)],source_end=assets[(code,year_end)])
            for transition in summary.pop('transitions'):transitions.append(dict(base,**transition))
            tags=dict(DATASET_ID=dataset,YEAR_START=str(year_start),YEAR_END=str(year_end),AREA_METHOD=AREA_METHOD,
                      THRESHOLDS=json.dumps(spec['breaks']),METHOD='common_valid_nearest_to_end_grid_v1',
                      SOURCE_START_SHA256=sources[summary['source_start']]['sha256'],SOURCE_END_SHA256=sources[summary['source_end']]['sha256'])
            summary['exports']={
                'change':write_cog(output/'rasters'/f'{code}_change.tif',classes,profile,255,'light_change_class',dict(tags,UNIT='class_code')),
                'delta':write_cog(output/'rasters'/f'{code}_delta.tif',delta,profile,-9999.,'radiance_end_minus_start',dict(tags,UNIT='nW/cm^2/sr'))}
            for kind,record in summary['exports'].items():exports[f'{code}_{kind}']=record
            changes.append(summary)
            print(f'Đã so sánh ảnh {index}/{len(neighbors)} tỉnh',flush=True)
        # Không công bố số liệu nếu nguồn thay đổi trong lúc chạy.
        if any(signature_status(r)!='ready' for r in sources.values()):raise ValueError('Ảnh nguồn đã thay đổi trong lúc tính P1.')
        if not snapshot_status(connection)[dataset]['available']:raise ValueError('CSV thay đổi trong lúc tính P1.')
        config=dict(version=SPATIAL_VERSION,dataset_id=dataset,year_start=year_start,year_end=year_end,
                    permutations=permutations,seed=seed,tolerance_m=tolerance_m,boundary_sha256=area_model.metadata['sha256'])
        identity=dict(config,sources={k:v['sha256'] for k,v in sources.items()})
        run_id=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        moran_rows=[{k:v for k,v in r.items() if not isinstance(v,(dict,list))} for r in moran]
        change_rows=[]
        for row in changes:
            flat={k:v for k,v in row.items() if not isinstance(v,(dict,list))}
            for i,name in enumerate(('persistent_unlit','stable_lit','lit_gain','lit_loss','lit_intensification','lit_dimming')):
                flat[name+'_area_km2']=row.get('change_areas_km2',[None]*6)[i]
            for when in ('start','end'):
                for field in ('longitude','latitude'):
                    flat['centroid_'+when+'_'+field]=(row.get('centroid_'+when) or {}).get(field)
            change_rows.append(flat)
        weight_rows=[]
        for result in moran:
            active=set(result['included'])
            for code in sorted(active):
                observed=[n for n in neighbors[code] if n in active]
                for neighbor in observed:
                    weight_rows.append(dict(year=result['year'],province_code=code,neighbor_code=neighbor,
                                            weight=1/len(observed),tolerance_m=tolerance_m,dataset_id=dataset))
        csvs={'moran':moran_rows,'moran_values':values_rows,'changes':change_rows,'transitions':transitions,'neighbors':weight_rows}
        files=dict(exports)
        for name,rows in csvs.items():
            for row in rows:row['run_id']=run_id
            fields=list(dict.fromkeys(k for row in rows for k in row)) or ['province_code']
            write_csv(output/(name+'.csv'),rows,fields);files[name]=file_signature(output/(name+'.csv'),True)
        features=[]
        for row in changes:
            polygon=area_model.polygons[row['province_code']]
            properties={k:v for k,v in row.items() if not isinstance(v,(dict,list))}
            properties['run_id']=run_id
            features.append(dict(type='Feature',properties=properties,geometry=transform_geom('EPSG:6933','EPSG:4326',mapping(polygon))))
        geojson=output/'province_changes.geojson'
        geojson.write_text(json.dumps(dict(type='FeatureCollection',features=features),ensure_ascii=False),encoding='utf-8')
        files['province_changes']=file_signature(geojson,True)
        report=dict(config,run_id=run_id,output=str(output),published=False,backup=None,
                    moran=moran,changes=changes,neighbors=neighbors,source_signatures=list(sources.values()),files=files,
                    change_names=CHANGE_NAMES,change_colors=CHANGE_COLORS,expected_provinces=expected_count,
                    complete_pairs=sum(r['status']=='ready' for r in changes),
                    centroid_method='radiance_ge_0.5_times_intersection_area_cell_centers_epsg6933_common_domain',
                    displacement_method='haversine_sphere_radius_6371.0088_km_initial_bearing_north_clockwise',
                    warnings=['Moran đo tự tương quan không gian, không chứng minh lan tỏa hay nhân quả.',
                              'Trọng tâm xấp xỉ theo tâm ô; tái lấy mẫu nearest không làm tăng độ phân giải thực.',
                              'Chỉ so sánh miền quan sát chung; ô thiếu không được thay bằng 0.',
                              'Chưa có lớp đường/biển/cảng/khu công nghiệp để gán nguyên nhân thay đổi.'])
        connection.executescript(SCHEMA)
        connection.execute('INSERT OR REPLACE INTO spatial_run VALUES(?,?,?)',(run_id,dataset,json.dumps(report,ensure_ascii=False)));connection.commit()
        if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database P1 không toàn vẹn.')
    if publish:
        if any(signature_status(r)!='ready' for r in list(sources.values())+list(files.values())):
            raise ValueError('Nguồn hoặc file xuất thay đổi trước xuất bản; chưa cập nhật app.')
        if file_signature(db,True)['sha256']!=baseline['sha256']:raise ValueError('Database đã đổi; không ghi đè kết quả mới hơn.')
        report['backup']=backup_database(db);report['published']=True
        with sqlite3.connect(candidate) as source:
            source.execute('UPDATE spatial_run SET payload=? WHERE run_id=?',(json.dumps(report,ensure_ascii=False),run_id));source.commit()
            with sqlite3.connect(db) as target:source.backup(target)
    (output/'spatial_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--integration-report',type=Path,required=True)
    parser.add_argument('--db',type=Path,default=Path(__file__).with_name('vngis.db'))
    parser.add_argument('--year-start',type=int,default=2020);parser.add_argument('--year-end',type=int,default=2024)
    parser.add_argument('--permutations',type=int,default=9999);parser.add_argument('--seed',type=int,default=20261123)
    parser.add_argument('--tolerance-m',type=float,default=1.);parser.add_argument('--publish',action='store_true')
    parser.add_argument('--boundaries',type=Path);parser.add_argument('--boundary-metadata',type=Path)
    args=parser.parse_args();model=load_area_model(args.root,args.boundaries,args.boundary_metadata)
    report=build(args.root,args.integration_report,args.db,args.year_start,args.year_end,args.permutations,args.seed,args.tolerance_m,args.publish,area_model=model)
    print(json.dumps({k:v for k,v in report.items() if k in ('run_id','dataset_id','output','published','backup','complete_pairs')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
