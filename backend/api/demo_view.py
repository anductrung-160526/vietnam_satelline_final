"""Dữ liệu hiển thị phần B: đọc SQLite, Raw trước Processed; không xử lý raster trong API."""
import json

from . import store
from backend.core.public_fields import is_public
from .provenance import available_asset,observation_info,current_id
from backend.data.dataset import snapshot_status,provenance_rows
from backend.core.chi_so import do_co_gian


def has_table(connection, name):
    return connection.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?', (name,)).fetchone() is not None


def asset(code, year, month, kind):
    with store.connect() as connection:
        return available_asset(connection,code,year,month,kind)


def prices(connection, year_from, year_to, code=None):
    args = [year_from, year_to]
    where = 'year BETWEEN ? AND ?'
    if code:
        where += ' AND province_code=?'
        args.append(code)
    result = {}
    # Bảng mới lưu đồng thời cả hai cơ sở giá, kể cả ô thiếu.
    if has_table(connection, 'economy_prices'):
        for row in connection.execute('SELECT * FROM economy_prices WHERE '+where, args):
            result[(row['province_code'], row['year'], row['price_basis'])] = dict(row)
    # Tương thích DB cũ; không lấy số cũ ghi đè dòng mới, kể cả dòng mới có giá trị NULL.
    if has_table(connection,'economy'):
        for record in connection.execute('SELECT * FROM economy WHERE '+where,args):
            row=dict(record);basis=row.get('grdp_price_basis')
            for target in ('so_sanh','hien_hanh'):
                explicit=row.get('grdp_'+target)
                value=explicit if explicit is not None else (row.get('grdp') if row.get('grdp') is not None else row.get('gdp')) if basis==target else None
                if value is None and row.get('population') is None:continue
                key=(row['province_code'],row['year'],target)
                if key not in result:result[key]=dict(row,grdp=value,price_basis=target,unit=row.get('unit') or 'unknown')
    return result



def dictionary_results(connection, year_from, year_to):
    if not has_table(connection, 'demo_result'):
        return {}
    return {(r['province_code'], r['year'], r['month'], r['table_name'], r['price_basis']): json.loads(r['payload'])
            for r in connection.execute('SELECT * FROM demo_result WHERE year BETWEEN ? AND ?', (year_from, year_to))}


def result_number(row, key):
    value = row.get(key)
    return float(value) if value is not None and str(value).strip() else None


def merged_quality_flags(*rows):
    flags = [flag for row in rows for flag in (row.get('quality_flags') or '').split(';') if flag]
    return ';'.join(dict.fromkeys(flags))


def economic_view(year_from=2020, year_to=2024, code=None, basis='so_sanh'):
    with store.connect() as connection:
        connection.execute('BEGIN')
        request_snapshot=current_id(connection)
        data = prices(connection, year_from-1, year_to, code)
        saved = dictionary_results(connection, year_from, year_to)
        night = {(r['province_code'], r['year']): dict(r) for r in connection.execute(
            'SELECT * FROM ntl_annual WHERE year BETWEEN ? AND ?',
            (year_from-1, year_to))}
        catalog = {r['province_code']: dict(r) for r in connection.execute('SELECT * FROM province')}
        versions=snapshot_status(connection);provenance=provenance_rows(connection)
        image_info={key:observation_info(connection,*key,0,versions,provenance) for key in night}
    keys = sorted(k for k in ({k[:2] for k in data} | {k for k in night if not code or k[0]==code}) if year_from<=k[1]<=year_to)
    rows = []
    for province, year in keys:
        a = data.get((province, year, 'so_sanh'), {})
        b = data.get((province, year, 'hien_hanh'), {})
        light = night.get((province, year), {})
        sources = [str(r.get('source') or '') for r in (a, b)]
        fake = any('GIA_LAP' in s.upper() for s in sources) or 'GIA_LAP' in str(light.get('source', '')).upper()
        # Hai mô hình dùng cùng tỉnh–năm với GRDP và SOL dương; dữ liệu giả luôn được gắn nhãn.
        paired = (all(v is not None and v > 0 for v in (a.get('grdp'), b.get('grdp'), light.get('sol')))
                  and a.get('unit') == b.get('unit') == 'ty_vnd'
                  and light.get('source') == 'VIIRS' and not fake)
        selected = a if basis != 'hien_hanh' else b
        result = saved.get((province, year, 0, 'night_economy', 'hien_hanh' if basis == 'hien_hanh' else 'so_sanh'), {})
        info=image_info.get((province,year),{})
        result_provenance=provenance.get((province,year,0,'night_economy','hien_hanh' if basis=='hien_hanh' else 'so_sanh'),{})
        result_id=result_provenance.get('dataset_id')
        consistent=info.get('consistent',True) and (not result_id or info.get('dataset_id')==result_id)
        paired=paired and consistent
        population = a.get('population') if a.get('population') is not None else b.get('population')
        rows.append({'province_code': province, 'province_name': catalog[province]['province_name'],
                     'year': year, 'population': population, 'grdp_so_sanh': a.get('grdp'),
                     'grdp_hien_hanh': b.get('grdp'), 'grdp': selected.get('grdp'),
                     'light_gdp_elasticity': result_number(result, 'light_gdp_elasticity'),
                     'predicted_gdp': result_number(result, 'predicted_gdp'),
                     'gdp_change_pct': result_number(result, 'gdp_change_pct'),
                     'image_quality_flags': result.get('image_quality_flags', ''),
                     'comparison_note': result.get('comparison_note', ''),
                     'light_basis': result.get('light_basis', 'sol'),
                     'model_training_period': result.get('model_training_period', ''),
                     'model_n': result_number(result, 'model_n'),
                     'model_beta': result_number(result, 'model_beta'),
                     'area_method': result.get('area_method', 'whole_pixel_approximation'),
                     'dataset_id':result_id or info.get('dataset_id'),
                     'stats_version':info.get('stats_version') or result_number(result,'stats_version'),
                     'provenance_consistent':consistent,'provenance_reason':info.get('reason','') or
                      ('Ảnh và kết quả kinh tế không cùng snapshot.' if not consistent else ''),
                     'source_image_path':info.get('source_path'),'source_image_sha256':info.get('source_sha256'),
                     'sol_unit':'DN' if light.get('source')=='DMSP' else 'nW/cm²/sr',
                     'sol': light.get('sol'), 'paired': paired, 'is_simulated': fake,
                     'sol_per_capita': light['sol']/population
                     if light.get('sol') is not None and population is not None and population > 0 else None,
                     'derived_price_basis': 'hien_hanh' if basis == 'hien_hanh' else 'so_sanh',
                     'unit': selected.get('unit', 'ty_vnd'),
                     'price_base_year': a.get('price_base_year'),
                     'is_provisional': bool(a.get('is_provisional') or b.get('is_provisional')),
                     'quality_flags': merged_quality_flags(a, b),
                     'source_so_sanh': a.get('source'), 'source_hien_hanh': b.get('source'),
                     'missing_reason': 'Chưa có chỉ số ảnh năm' if light.get('sol') is None else ''})
    fits = {}
    for price in ('so_sanh', 'hien_hanh'):
        sample = [dict(r, grdp=r['grdp_'+price]) for r in rows if r['paired']]
        fits[price] = do_co_gian(sample, gia_so_sanh=price == 'so_sanh')
    from backend.core.economic_metrics import add_economic_metrics
    from backend.core.indicator_catalog import describe_economy
    add_economic_metrics(rows,night,data,basis,fits)
    warnings = []
    if any(not r['provenance_consistent'] for r in rows):
        warnings.append('Có dòng chưa khớp nguồn gốc dữ liệu; hệ thống loại khỏi mẫu hồi quy hiện tại. Kiểm tra kết quả nạp và kiểm chứng dữ liệu.')
    if any(r['area_method'] == 'whole_pixel_approximation' for r in rows):
        warnings.append('Có kết quả diện tích dùng toàn bộ pixel giao biên; cần tính lại theo phần giao pixel–tỉnh. SOL là tổng bức xạ pixel, chưa quy đổi thành giá trị tiền tệ kinh tế đêm.')
    if any(r['image_quality_flags'] for r in rows):
        warnings.append('Kiểm tra nội bộ phát hiện ảnh cần rà soát; biến động độ phủ có thể ảnh hưởng chỉ số ánh sáng.')
    if any(r['is_simulated'] for r in rows):
        warnings.append('SỐ LIỆU GIẢ LẬP — chỉ dùng kiểm thử giao diện, không dùng cho báo cáo.')
    if basis in ('hien_hanh', 'compare'):
        warnings.append('GRDP giá hiện hành dùng đối chiếu; giá so sánh năm gốc 2010 là cơ sở chính thức của bộ dữ liệu cô cung cấp.')
    if any(r['quality_flags'] for r in rows):
        warnings.append('Có dòng cần đối chiếu nguồn; dữ liệu được giữ nguyên và chưa tự động loại khỏi mẫu hồi quy.')
    if rows and not any(r['paired'] for r in rows):
        warnings.append('Chưa có mẫu chung đủ hai loại GRDP và SOL dương; chưa ước lượng mô hình đối chiếu.')
    return {'dong': rows, 'columns':describe_economy(), 'hoi_quy': fits, 'canh_bao': warnings, 'price_basis': basis,
            'snapshot_id':request_snapshot,
            'nam_tu': year_from, 'nam_den': year_to, 'paired_count': sum(r['paired'] for r in rows),
            'province_code': code, 'population_missing': all(r['population'] is None for r in rows)}


FIELD_ALIASES = {'valid_pixels':'total_pixels', 'rad_mean':'mean_rad', 'rad_std':'std_rad',
                 'rad_min':'min_rad', 'rad_max':'max_rad', 'rad_cv':'spatial_cv',
                  'lit_pixel_pct':'electrification_ratio_pct'}


PROCESSED = (
    ('area_km2', 'Diện tích tự nhiên', 'km²'),
    ('background_threshold','Ngưỡng nền','bức xạ'), ('background_pixels','Pixel dưới ngưỡng nền','pixel'),
    ('lit_threshold','Ngưỡng pixel sáng','bức xạ'),
    ('valid_area_km2', 'Diện tích có dữ liệu', 'km²'), ('valid_area_pct', 'Độ phủ dữ liệu', '%'),
    ('tnl', 'Tổng bức xạ cùng tập pixel đầu vào', 'bức xạ'), ('sol_raw', 'Tổng sáng trước loại nền', 'bức xạ'),
    ('sol', 'Tổng sáng sau loại nền', 'bức xạ'), ('sol_density', 'Mật độ sáng', 'bức xạ/km²'),
    ('valid_pixels', 'Pixel hợp lệ', 'pixel'), ('rad_mean', 'Bức xạ trung bình', 'bức xạ'),
    ('rad_std', 'Độ lệch chuẩn', 'bức xạ'), ('rad_min', 'Bức xạ nhỏ nhất', 'bức xạ'),
    ('rad_max', 'Bức xạ lớn nhất', 'bức xạ'), ('rad_cv', 'Hệ số biến thiên', ''),
    ('cloud_free_obs', 'Quan sát sạch mây trung bình', 'lượt'), ('lit_pixels', 'Pixel sáng', 'pixel'),
    ('lit_sol', 'Tổng sáng vùng sáng', 'bức xạ'), ('lit_area_km2', 'Diện tích sáng', 'km²'),
    ('lit_area_pct', 'Tỷ lệ diện tích sáng', '%'), ('lit_pixel_pct', 'Tỷ lệ pixel sáng', '%'),
    ('sol_change_pct', 'Thay đổi so năm trước', '%'),
    ('sol_change_mom_pct', 'Thay đổi so tháng trước', '%'),
    ('sol_change_yoy_pct', 'Thay đổi cùng tháng năm trước', '%'), ('sol_ma3', 'SOL trung bình ba tháng lịch', 'bức xạ'),
    ('tnl_ma3', 'TNL trung bình ba quan sát tháng', 'bức xạ'),
    ('tnl_mom_growth_pct', 'Biến động TNL so quan sát tháng trước', '%'),
    ('sol_cal', 'Tổng sáng đã hiệu chỉnh', 'bức xạ'),
    ('sol_per_capita', 'Ánh sáng bình quân đầu người', 'bức xạ/người'),
    ('light_gdp_elasticity', 'Tỷ số tăng trưởng ánh sáng/GRDP', ''),
    ('predicted_gdp', 'GRDP dự báo từ ánh sáng', 'tỷ đồng'),
)


def province_view(code, year, month):
    province = store.province(code)
    if province is None:
        return None
    table = 'ntl_monthly' if month else 'ntl_annual'
    with store.connect() as connection:
        connection.execute('BEGIN')
        request_snapshot=current_id(connection)
        data_provenance=observation_info(connection,code,year,month)
        query = f'SELECT * FROM {table} WHERE province_code=? AND year=?'
        args = [code, year]
        if month:
            query += ' AND month=?'
            args.append(month)
        found = connection.execute(query, args).fetchone()
        observation = dict(found) if found else {}
        economy = prices(connection, year, year, code)
        saved = dictionary_results(connection, year, year)
        nd = saved.get((code, year, month, 'night_data', ''), {})
        ne = saved.get((code, year, month, 'night_economy', 'so_sanh'), {})
        classes = []
        class_summary = None
        observation_support = None
        recovery_audit = None
        if month and has_table(connection, 'monthly_recovery_audit'):
            found_recovery = connection.execute('SELECT payload FROM monthly_recovery_audit WHERE province_code=? AND year=? AND month=?', (code,year,month)).fetchone()
            if found_recovery:
                recovery_audit = json.loads(found_recovery['payload'])
        if has_table(connection, 'annual_observation_support'):
            found_support = connection.execute('SELECT payload FROM annual_observation_support WHERE province_code=? AND year=?', (code,year)).fetchone()
            if found_support:
                observation_support = json.loads(found_support['payload'])
        if has_table(connection, 'light_class'):
            classes = [dict(r) for r in connection.execute(
                'SELECT * FROM light_class WHERE province_code=? AND year=? AND month=? ORDER BY class_index',
                (code, year, month))]
        if has_table(connection, 'light_class_summary'):
            found_summary = connection.execute(
                'SELECT * FROM light_class_summary WHERE province_code=? AND year=? AND month=?',
                (code, year, month)).fetchone()
            if found_summary:
                class_summary = dict(found_summary)
                percentages = json.loads(class_summary.pop('class_area_pcts'))
                for item in classes:
                    item['class_area_pct'] = percentages[item['class_index']]
        raw_asset=available_asset(connection,code,year,month,'raw')
        processed_asset=available_asset(connection,code,year,month,'processed')
        class_asset=available_asset(connection,code,year,month,'classes')
        support_asset=available_asset(connection,code,year,0,'support')
    source = observation.get('source') or (processed_asset or {}).get('source') or 'VIIRS'
    unit = 'DN' if 'DMSP' in source else 'nW/cm²/sr'
    fields = []
    for band, name in [('avg_rad', 'Bức xạ đầu vào'), ('cf_cvg', 'Lượt quan sát sạch mây')]:
        fields.append({'field': band, 'name': name, 'stage': 'Raw', 'value': None,
                       'unit': unit if band == 'avg_rad' else 'lượt', 'is_raster': True,
                       'band': 1 if band == 'avg_rad' else 2, 'available': bool(raw_asset and raw_asset['available']),
                       'reason': raw_asset.get('reason','') if raw_asset else ('DMSP không có băng avg_rad/cf_cvg của VIIRS.' if 'DMSP' in source else 'Chưa đăng ký ảnh gốc hai băng ở mốc này; ảnh năm đã tổng hợp không phải băng Raw.')})
    for basis in ('so_sanh', 'hien_hanh'):
        item = economy.get((code, year, basis), {})
        fields.append({'field': 'grdp_'+basis, 'name': 'GRDP '+('giá so sánh' if basis == 'so_sanh' else 'giá hiện hành'),
                       'stage': 'Raw', 'value': item.get('grdp'), 'unit': 'tỷ đồng' if item.get('unit') == 'ty_vnd' else '',
                       'reason': '' if item.get('grdp') is not None else 'Chưa có GRDP ở cơ sở giá/năm này.',
                       'is_provisional': bool(item.get('is_provisional')), 'source': item.get('source')})
    pop = next((r.get('population') for r in economy.values() if r.get('population') is not None), None)
    fields.insert(2, {'field': 'population', 'name': 'Dân số', 'stage': 'Raw', 'value': pop, 'unit': 'người',
                      'reason': '' if pop is not None else 'Bộ GRDP đã nhận chưa có dân số.'})
    for field, name, field_unit in PROCESSED:
        if (month and field in ('sol_change_pct', 'sol_cal')) or (not month and field in ('sol_change_mom_pct', 'sol_change_yoy_pct', 'sol_ma3', 'tnl_ma3', 'tnl_mom_growth_pct')):
            continue
        value = observation.get('sol_raw' if field == 'tnl' else field)
        display_name = FIELD_ALIASES.get(field, field)
        stored = nd if display_name in nd else ne
        if display_name in stored and field not in ('sol','sol_density','sol_change_pct'):
            value = result_number(stored, display_name)
        if class_summary is not None and field in ('valid_area_km2', 'valid_area_pct'):
            value = class_summary[field]
        field_radiance_unit='nW/cm²/sr' if field in ('sol_cal','sol_per_capita') or (field=='sol_density' and ne.get('light_basis')=='sol_cal') else unit
        fields.append({'field': display_name, 'name': name, 'stage': 'Processed', 'value': value,
                       'unit': field_unit.replace('bức xạ', field_radiance_unit) if field_unit else 'không thứ nguyên',
                       'reason': '' if value is not None else 'Chưa có số liệu hoặc chỉ số không tính được ở mốc này.'})
    if month:
        for item in fields:
            if item['field'] in ('population','grdp_so_sanh','grdp_hien_hanh'):item.update(value=None,reason='Chỉ có dữ liệu theo năm.')
    from backend.core.indicator_catalog import describe
    for item in fields:
        definition=describe(item['field'])
        if definition:
            item.update(name=definition['name'],definition=definition['definition'],formula=definition['formula'])
    simulated = 'GIA_LAP' in str(observation.get('source', '')).upper() or observation.get('status') == 'GIA_LAP'
    return {'province': province, 'year': year, 'month': month, 'source': source, 'unit': unit,
            'fields': [f for f in fields if is_public(f['field'])], 'raw_asset': raw_asset, 'processed_asset': processed_asset,
            'classes': classes, 'class_asset': class_asset, 'is_simulated': simulated,
            'snapshot_id':request_snapshot,
            'class_summary': class_summary,
            'observation_support': observation_support,
            'support_asset':support_asset,
            'recovery_audit': recovery_audit,
            'provenance':data_provenance,
            'light_basis':ne.get('light_basis','sol'),'area_method':ne.get('area_method',nd.get('area_method','unknown')),
            'class_status': 'ready' if len(classes) == 5 else 'missing',
            'class_reason': '' if len(classes) == 5 else 'Chưa có kết quả năm mức sáng và ngưỡng đã cấu hình cho tỉnh/mốc này.'}
