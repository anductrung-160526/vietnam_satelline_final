"""Dữ liệu hiển thị phần B: đọc SQLite, Raw trước Processed; không xử lý raster trong API."""
import json

from . import store
from backend.core.chi_so import do_co_gian


def has_table(connection, name):
    return connection.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?', (name,)).fetchone() is not None


def asset(code, year, month, kind):
    with store.connect() as connection:
        if not has_table(connection, 'demo_asset'):
            return None
        row = connection.execute('SELECT * FROM demo_asset WHERE province_code=? AND year=? AND month=? AND kind=?',
                                 (code, year, month, kind)).fetchone()
    return dict(row) if row else None


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
    for row in connection.execute('SELECT * FROM economy WHERE '+where, args):
        basis = row['grdp_price_basis']
        if basis not in ('so_sanh', 'hien_hanh'):
            continue
        key = (row['province_code'], row['year'], basis)
        if key not in result:
            result[key] = dict(row)
            result[key]['grdp'] = row['grdp'] if row['grdp'] is not None else row['gdp']
            result[key]['unit'] = 'unknown'
    return result



def dictionary_results(connection, year_from, year_to):
    if not has_table(connection, 'demo_result'):
        return {}
    return {(r['province_code'], r['year'], r['month'], r['table_name'], r['price_basis']): json.loads(r['payload'])
            for r in connection.execute('SELECT * FROM demo_result WHERE year BETWEEN ? AND ?', (year_from, year_to))}


def result_number(row, key):
    value = row.get(key)
    return float(value) if value is not None and str(value).strip() else None


def economic_view(year_from=2020, year_to=2024, code=None, basis='so_sanh'):
    with store.connect() as connection:
        data = prices(connection, year_from, year_to, code)
        saved = dictionary_results(connection, year_from, year_to)
        night = {(r['province_code'], r['year']): dict(r) for r in connection.execute(
            'SELECT province_code,year,sol,source,status FROM ntl_annual WHERE year BETWEEN ? AND ?',
            (year_from, year_to))}
        catalog = {r['province_code']: dict(r) for r in connection.execute('SELECT * FROM province')}
    keys = sorted({k[:2] for k in data})
    rows = []
    for province, year in keys:
        a = data.get((province, year, 'so_sanh'), {})
        b = data.get((province, year, 'hien_hanh'), {})
        light = night.get((province, year), {})
        sources = [str(r.get('source') or '') for r in (a, b)]
        fake = any('GIA_LAP' in s.upper() for s in sources) or 'GIA_LAP' in str(light.get('source', '')).upper()
        # Hai mô hình dùng cùng tỉnh–năm với GRDP và SOL dương; dữ liệu giả luôn được gắn nhãn.
        paired = (all(v is not None and v > 0 for v in (a.get('grdp'), b.get('grdp'), light.get('sol')))
                  and a.get('unit') == b.get('unit') == 'ty_vnd')
        selected = a if basis != 'hien_hanh' else b
        result = saved.get((province, year, 0, 'night_economy', 'hien_hanh' if basis == 'hien_hanh' else 'so_sanh'), {})
        population = a.get('population') if a.get('population') is not None else b.get('population')
        rows.append({'province_code': province, 'province_name': catalog[province]['province_name'],
                     'year': year, 'population': population, 'grdp_so_sanh': a.get('grdp'),
                     'grdp_hien_hanh': b.get('grdp'), 'grdp': selected.get('grdp'),
                     'light_gdp_elasticity': result_number(result, 'light_gdp_elasticity'),
                     'predicted_gdp': result_number(result, 'predicted_gdp'),
                     'sol': light.get('sol'), 'paired': paired, 'is_simulated': fake,
                     'sol_per_capita': light['sol']/population
                     if light.get('sol') is not None and population is not None and population > 0 else None,
                     'derived_price_basis': 'hien_hanh' if basis == 'hien_hanh' else 'so_sanh',
                     'unit': selected.get('unit', 'ty_vnd'),
                     'price_base_year': a.get('price_base_year'),
                     'is_provisional': bool(a.get('is_provisional') or b.get('is_provisional')),
                     'quality_flags': ';'.join(filter(None, [a.get('quality_flags'), b.get('quality_flags')])),
                     'source_so_sanh': a.get('source'), 'source_hien_hanh': b.get('source'),
                     'missing_reason': 'Chưa có chỉ số ảnh năm' if light.get('sol') is None else ''})
    fits = {}
    for price in ('so_sanh', 'hien_hanh'):
        sample = [dict(r, grdp=r['grdp_'+price]) for r in rows if r['paired']]
        fits[price] = do_co_gian(sample, gia_so_sanh=price == 'so_sanh')
    warnings = []
    if any(r['is_simulated'] for r in rows):
        warnings.append('SỐ LIỆU GIẢ LẬP — chỉ dùng kiểm thử giao diện, không dùng cho báo cáo.')
    if basis in ('hien_hanh', 'compare'):
        warnings.append('GRDP giá hiện hành dùng đối chiếu; giá so sánh năm gốc 2010 là cơ sở chính thức của bộ dữ liệu cô cung cấp.')
    if any(r['quality_flags'] for r in rows):
        warnings.append('Có dòng cần đối chiếu nguồn; dữ liệu được giữ nguyên và chưa tự động loại khỏi mẫu hồi quy.')
    if rows and not any(r['paired'] for r in rows):
        warnings.append('Chưa có mẫu chung đủ hai loại GRDP và SOL dương; chưa ước lượng mô hình đối chiếu.')
    return {'dong': rows, 'hoi_quy': fits, 'canh_bao': warnings, 'price_basis': basis,
            'nam_tu': year_from, 'nam_den': year_to, 'paired_count': sum(r['paired'] for r in rows),
            'province_code': code, 'population_missing': all(r['population'] is None for r in rows)}


FIELD_ALIASES = {'valid_pixels':'total_pixels', 'rad_mean':'mean_rad', 'rad_std':'std_rad',
                 'rad_min':'min_rad', 'rad_max':'max_rad', 'rad_cv':'spatial_cv',
                 'lit_sol':'lit_pop_proxy', 'lit_pixel_pct':'electrification_ratio_pct'}


PROCESSED = (
    ('area_km2', 'Diện tích tự nhiên', 'km²'),
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
    raw_asset = asset(code, year, month, 'raw')
    processed_asset = asset(code, year, month, 'processed')
    source = observation.get('source') or (processed_asset or {}).get('source') or 'VIIRS'
    unit = 'DN' if 'DMSP' in source else 'nW/cm²/sr'
    fields = []
    for band, name in [('avg_rad', 'Bức xạ đầu vào'), ('cf_cvg', 'Lượt quan sát sạch mây')]:
        fields.append({'field': band, 'name': name, 'stage': 'Raw', 'value': None,
                       'unit': unit if band == 'avg_rad' else 'lượt', 'is_raster': True,
                       'band': 1 if band == 'avg_rad' else 2, 'available': raw_asset is not None,
                       'reason': '' if raw_asset else ('DMSP không có băng avg_rad/cf_cvg của VIIRS.' if 'DMSP' in source else 'Chưa đăng ký ảnh gốc hai băng ở mốc này; ảnh năm đã tổng hợp không phải băng Raw.')})
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
        stored = ne if field in ('sol_per_capita','light_gdp_elasticity','predicted_gdp') else nd
        if display_name in stored:
            value = result_number(stored, display_name)
        if class_summary is not None and field in ('valid_area_km2', 'valid_area_pct'):
            value = class_summary[field]
        fields.append({'field': display_name, 'name': name, 'stage': 'Processed', 'value': value,
                       'unit': field_unit.replace('bức xạ', unit),
                       'reason': '' if value is not None else 'Chưa có số liệu hoặc chỉ số không tính được ở mốc này.'})
    simulated = 'GIA_LAP' in str(observation.get('source', '')).upper() or observation.get('status') == 'GIA_LAP'
    return {'province': province, 'year': year, 'month': month, 'source': source, 'unit': unit,
            'fields': fields, 'raw_asset': raw_asset, 'processed_asset': processed_asset,
            'classes': classes, 'class_asset': asset(code, year, month, 'classes'), 'is_simulated': simulated,
            'class_summary': class_summary,
            'class_status': 'ready' if len(classes) == 5 else 'missing',
            'class_reason': '' if len(classes) == 5 else 'Chưa có kết quả năm mức sáng và ngưỡng đã cấu hình cho tỉnh/mốc này.'}
