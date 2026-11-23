"""Bảng ngang tỉnh–năm/tháng; đọc theo lô trong một snapshot SQLite."""
import json
import re
from . import store
from .demo_view import PROCESSED,FIELD_ALIASES,has_table,prices,result_number
from .provenance import current_id
from backend.data.dataset import snapshot_status,provenance_rows
from backend.data.column_order import ordered_fields,IDENTITY_FIELDS,RAW_FIELDS

BASE=['province_code','province_name','gid_1','year','month','frequency','source','avg_rad','cf_cvg',
      'population','grdp_so_sanh','grdp_hien_hanh','price_base_year','is_provisional','grdp_frequency']
NUMERIC={FIELD_ALIASES.get(f,f):name for f,name,unit in PROCESSED}
EXTRA=['background_threshold','background_pixels','lit_threshold','status','obs_status','light_basis','area_method',
       'radiance_unit','grdp_unit','economy_source','dataset_id','stats_version','source_image_path','source_image_sha256']


def data_table(periods,codes=None,selected=None):
    parsed=[]
    for period in dict.fromkeys(periods):
        if not re.fullmatch(r'\d{4}(?:-(?:0[1-9]|1[0-2]))?',period):raise ValueError('Mốc thời gian không hợp lệ: '+period)
        year=int(period[:4]);month=int(period[5:]) if len(period)>4 else 0
        if not 2004<=year<=2025:raise ValueError('Năm ngoài 2004–2025.')
        parsed.append((year,month))
    if not parsed:raise ValueError('Chọn ít nhất một mốc năm hoặc tháng.')
    parsed.sort();first,last=parsed[0][0],parsed[-1][0]
    with store.connect() as connection:
        connection.execute('BEGIN');snapshot=current_id(connection)
        provinces={r['province_code']:dict(r) for r in connection.execute('SELECT * FROM province')}
        chosen=sorted(set(codes or provinces))
        if any(c not in provinces for c in chosen):raise ValueError('Mã tỉnh không hợp lệ.')
        observations={}
        for table in ('ntl_annual','ntl_monthly'):
            for item in connection.execute(f'SELECT * FROM {table} WHERE year BETWEEN ? AND ?',(first,last)):
                row=dict(item);observations[(row['province_code'],row['year'],row.get('month',0))]=row
        saved={}
        if has_table(connection,'demo_result'):
            for r in connection.execute('SELECT * FROM demo_result WHERE year BETWEEN ? AND ?',(first,last)):
                saved[(r['province_code'],r['year'],r['month'],r['table_name'],r['price_basis'])]=json.loads(r['payload'])
        assets={}
        if has_table(connection,'demo_asset'):
            assets={(r['province_code'],r['year'],r['month'],r['kind']):dict(r) for r in connection.execute('SELECT * FROM demo_asset WHERE year BETWEEN ? AND ?',(first,last))}
        checks={}
        if has_table(connection,'demo_asset_check'):
            checks={(r['province_code'],r['year'],r['month']):json.loads(r['payload']) for r in connection.execute("SELECT * FROM demo_asset_check WHERE kind='processed' AND year BETWEEN ? AND ?",(first,last))}
        summaries={}
        if has_table(connection,'light_class_summary'):
            summaries={(r['province_code'],r['year'],r['month']):dict(r) for r in connection.execute('SELECT * FROM light_class_summary WHERE year BETWEEN ? AND ?',(first,last))}
        economy=prices(connection,first,last)
        provenance=provenance_rows(connection);versions=snapshot_status(connection)
        results=[]
        for code in chosen:
            for year,month in parsed:
                key=(code,year,month);obs=observations.get(key,{})
                nd=saved.get((*key,'night_data',''),{});ne=saved.get((*key,'night_economy','so_sanh'),{})
                a=economy.get((code,year,'so_sanh'),{});b=economy.get((code,year,'hien_hanh'),{})
                raw=assets.get((*key,'raw'),{});processed=assets.get((*key,'processed'),{})
                origin=provenance.get((*key,'ntl_monthly' if month else 'ntl_annual',''),{})
                record=checks.get(key,{})
                row=dict(province_code=code,province_name=provinces[code]['province_name'],gid_1=provinces[code].get('gid_1'),
                         year=year,month=month,frequency='monthly' if month else 'annual',source=obs.get('source') or processed.get('source'),
                         avg_rad=raw.get('path')+'#band=1' if raw and obs.get('source')=='VIIRS' else None,
                         cf_cvg=raw.get('path')+'#band=2' if raw and obs.get('source')=='VIIRS' else None,
                         population=a.get('population') if a.get('population') is not None else b.get('population'),
                         grdp_so_sanh=a.get('grdp'),grdp_hien_hanh=b.get('grdp'),price_base_year=a.get('price_base_year'),
                         is_provisional=bool(a.get('is_provisional') or b.get('is_provisional')),
                         grdp_frequency='annual_reference' if month else 'annual',
                         grdp_unit=a.get('unit') or b.get('unit'),economy_source=a.get('source') or b.get('source'),
                         dataset_id=origin.get('dataset_id'),stats_version=versions.get(origin.get('dataset_id'),{}).get('stats_version'),
                         source_image_path=processed.get('path'),source_image_sha256=record.get('source',{}).get('sha256'),
                         radiance_unit='DN' if obs.get('source')=='DMSP' else 'nW/cm²/sr' if obs else None,
                         light_basis=ne.get('light_basis','sol'),area_method=ne.get('area_method',nd.get('area_method')))
                for field,name,unit in PROCESSED:
                    alias=FIELD_ALIASES.get(field,field);value=obs.get('sol_raw' if field=='tnl' else field)
                    payload=nd if alias in nd else ne
                    if alias in payload:value=result_number(payload,alias)
                    if month and field in ('sol_change_pct','sol_cal'):value=None
                    if not month and field in ('sol_change_mom_pct','sol_change_yoy_pct','sol_ma3','tnl_ma3','tnl_mom_growth_pct'):value=None
                    if field in ('valid_area_km2','valid_area_pct') and key in summaries:value=summaries[key][field]
                    row[alias]=value
                for field in ('background_threshold','background_pixels','lit_threshold','status','obs_status'):
                    row[field]=obs.get(field)
                if not obs:row['status']='MISSING_OBSERVATION'
                if any('GIA_LAP' in str(value).upper() for value in (obs.get('source'),obs.get('status'),a.get('source'),b.get('source'))):
                    row['status']='GIA_LAP'
                results.append(row)
    fields=ordered_fields(BASE+list(NUMERIC)+EXTRA)
    if selected is not None:
        wanted={FIELD_ALIASES.get(f,f) for f in selected}
        # Hai field hiệu chỉnh mật độ/tăng trưởng đã gộp vào tên thống nhất.
        fields=[f for f in fields if f not in NUMERIC or f in wanted]
    names={'province_code':'Mã tỉnh','province_name':'Tên tỉnh','gid_1':'Mã GADM','year':'Năm','month':'Tháng (0 = năm)',
           'avg_rad':'Băng bức xạ Raw (tham chiếu file)','cf_cvg':'Băng lượt quan sát Raw (tham chiếu file)',
           'population':'Dân số năm','grdp_so_sanh':'GRDP so sánh (năm, tỷ đồng)','grdp_hien_hanh':'GRDP hiện hành (năm, tỷ đồng)'}
    names.update(NUMERIC)
    columns=[dict(field=f,name=names.get(f,f),group='identity' if f in IDENTITY_FIELDS else 'raw' if f in RAW_FIELDS else 'processed',
                  numeric=f in NUMERIC or f in ('population','grdp_so_sanh','grdp_hien_hanh','year','month','price_base_year')) for f in fields]
    warnings=['GRDP/dân số ở dòng tháng là tham chiếu số liệu năm; không phải GRDP/dân số tháng.',
              'avg_rad/cf_cvg là tham chiếu băng ảnh Raw, không phải một giá trị pixel đại diện cho tỉnh.']
    if snapshot and not versions.get(snapshot,{}).get('available'):warnings.append('CSV snapshot nền đã mất/đổi; cần kiểm chứng lại.')
    if any(r['status']=='GIA_LAP' for r in results):warnings.append('SỐ LIỆU GIẢ LẬP — có dòng chứa ảnh hoặc dữ liệu kinh tế dùng kiểm thử.')
    if any(r['dataset_id'] and r['dataset_id']!=snapshot for r in results):warnings.append('Có dòng thuộc snapshot cũ; xem dataset_id của từng dòng.')
    return dict(snapshot_id=snapshot,columns=columns,rows=[{f:r.get(f) for f in fields} for r in results],warnings=warnings)
