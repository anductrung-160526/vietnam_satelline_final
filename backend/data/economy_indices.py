"""Phần E: ghép hai cơ sở giá và tính chỉ số kinh tế, không đọc raster lần hai.

Luồng mới tách khóa tỉnh/năm/giá; không thay hợp đồng CSV kinh tế một giá cũ.
"""
import csv
import math
from pathlib import Path

from .calculate_ntl import fit_log_model, growth_pct, number_or_none, rounded, STATS_VERSION
from .prepare_grdp import provinces

BASES = ('so_sanh', 'hien_hanh')


def read_prices(path):
    """Đọc grdp_all_prices.csv phần A, giữ ô thiếu, đơn vị và nguồn gốc."""
    result, populations = {}, {}
    catalog = {p['ma_tinh'] for p in provinces()}
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'province_code', 'year', 'grdp', 'grdp_price_basis', 'unit', 'price_base_year', 'source', 'is_provisional'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('CSV hai giá thiếu cột: '+', '.join(sorted(required-set(reader.fieldnames or []))))
        for row in reader:
            code, year = row['province_code'].strip().zfill(2), int(row['year'])
            basis = row['grdp_price_basis'].strip()
            key = (code, year, basis)
            if key in result:
                raise ValueError(f'Trùng dòng kinh tế hai giá: {key}')
            if code not in catalog or basis not in BASES or not 2004 <= year <= 2025:
                raise ValueError(f'Mã tỉnh/năm/cơ sở giá không hợp lệ: {key}')
            base_year = number_or_none(row['price_base_year'])
            if row['unit'] != 'ty_vnd' or (basis == 'so_sanh' and base_year != 2010) or (basis == 'hien_hanh' and base_year is not None):
                raise ValueError('Cần GRDP tỷ đồng, giá so sánh gốc 2010 và hiện hành không có năm gốc.')
            value = number_or_none(row['grdp'])
            population = number_or_none(row.get('population'))
            if (value is not None and value < 0) or (population is not None and population < 0):
                raise ValueError(f'GRDP/dân số không được âm: {key}')
            if population is not None:
                previous = populations.setdefault((code, year), population)
                if previous != population:
                    raise ValueError(f'Dân số khác nhau giữa hai cơ sở giá: {code}/{year}')
            if row['is_provisional'] not in ('0', '1'):
                raise ValueError('is_provisional phải là 0 hoặc 1.')
            result[key] = dict(gdp=value, population=population, grdp_price_basis=basis,
                               price_base_year=int(base_year) if base_year is not None else None,
                               unit=row['unit'], economy_source=row['source'],
                               is_provisional=int(row['is_provisional']), quality_flags=row.get('quality_flags', ''))
    if not result:
        raise ValueError('CSV kinh tế hai giá không có dữ liệu.')
    # Dân số là thuộc tính tỉnh/năm, không phải thuộc tính cơ sở giá.
    for (code, year, _), row in result.items():
        row['population'] = populations.get((code, year))
    return result


def read_image_quality(path):
    """Đọc báo cáo D tùy chọn; không tự tạo ngưỡng loại mẫu theo độ phủ."""
    if path is None:
        return {}
    result = {}
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'province_code', 'year', 'month', 'valid_pixels', 'valid_area_pct', 'valid_area_km2'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('CSV chất lượng thiếu cột của light_class_validation.csv phần D.')
        for row in reader:
            key = (row['province_code'].zfill(2), int(row['year']), int(row['month']))
            if key in result:
                raise ValueError(f'Trùng dòng báo cáo D: {key}')
            result[key] = row
    return result


def image_flags(row, quality):
    """Kiểm tra SOL trước/sau nền và truyền giới hạn diện tích sang kết quả E."""
    fractional = row is not None and row.get('area_method') == 'pixel_polygon_intersection_epsg6933_v1'
    flags = [] if fractional else ['WHOLE_PIXEL_AREA_APPROXIMATION']
    if row is None:
        return ['MISSING_IMAGE']
    raw, sol = row['sol_raw'], row['sol']
    if raw is not None and sol is not None and (sol < 0 or raw < sol-1e-4):
        raise ValueError('SOL phải không âm và không vượt sol_raw trên cùng đầu vào.')
    if not row['valid_pixels']:
        flags.append('NO_VALID_PIXELS')
    if quality:
        from backend.core.light_classification import METHOD_VERSION as class_version
        if fractional and quality.get('method_version') not in ('viirs_brightness_classes_v3_fractional',class_version):
            raise ValueError('Cần báo cáo D v3 fractional cùng phương pháp diện tích; không ghép báo cáo v2 cũ.')
        if int(quality['valid_pixels']) != row['valid_pixels']:
            raise ValueError('Số pixel hợp lệ của ảnh tính lại khác báo cáo D; kiểm tra đúng phiên bản ảnh.')
        coverage = number_or_none(quality['valid_area_pct'])
        if coverage is not None and coverage > 100:
            flags.append('COVERAGE_ABOVE_100')
        if fractional and not math.isclose(float(quality['valid_area_km2']), row['valid_area_km2'], rel_tol=1e-9, abs_tol=1e-8):
            raise ValueError('Diện tích hợp lệ khác báo cáo D v3; kiểm tra manifest/ảnh sửa.')
    else:
        flags.append('PART_D_NOT_LINKED')
    if row['lit_area_pct'] is not None and row['lit_area_pct'] > 100:
        flags.append('LIT_AREA_ABOVE_100')
    if row['cloud_free_obs'] is not None and row['cloud_free_obs'] < 2:
        flags.append('LOW_CLOUD_FREE_OBSERVATIONS')
    return flags


def attach_two_prices(tables, prices, quality=None, calibrate=False):
    """Xuất từng giá một dòng; giữ cả dòng có GRDP nhưng không có ảnh và ngược lại."""
    quality = quality or {}
    catalog = {p['ma_tinh']: p for p in provinces()}
    observations = {(r['province_code'], r['year'], r['month']): r
                    for r in tables['ntl_annual']+tables['ntl_monthly']}
    base_rows = {(r['gid_1'], r['year'], r['month']): r for r in tables['night_economy']}
    keys = set(observations) | {(code, year, 0) for code, year, basis in prices}
    annual = {(code, year): row for (code, year, month), row in observations.items() if month == 0}
    light_key = 'sol_cal' if calibrate else 'sol'

    # Mẫu hồi quy dùng CHUNG hai giá, chỉ VIIRS năm, cặp dương và nguồn thật.
    paired_keys = set()
    for key, row in annual.items():
        values = [prices.get((*key, basis), {}) for basis in BASES]
        light = row.get(light_key)
        positive = light is not None and light > 0 and all(r.get('gdp') is not None and r['gdp'] > 0 for r in values)
        if row['source'] == 'VIIRS' and row['year'] >= 2014 and positive:
            paired_keys.add(key)
    models = {}
    for basis in BASES:
        pairs = [(annual[k][light_key], prices[(*k, basis)]['gdp']) for k in sorted(paired_keys)]
        models[basis] = fit_log_model(pairs, minimum=10)

    output = []
    training_period = f'{min(y for c,y in paired_keys)}-{max(y for c,y in paired_keys)}' if paired_keys else ''
    for code, year, month in sorted(keys):
        observation = observations.get((code, year, month))
        province = catalog[code]
        template = base_rows.get((province['gid_1'], year, month), {})
        quality_row = quality.get((code, year, month))
        flags = image_flags(observation, quality_row)
        if observation and month == 0 and year in (2010, 2014):
            flags.append('SENSOR_TRANSITION')
        previous = annual.get((code, year-1)) if not month else None
        previous_image = previous
        if month:
            previous_image = observations.get((code, year if month > 1 else year-1, month-1 if month > 1 else 12))
        if observation and previous_image and observation['valid_pixels'] != previous_image['valid_pixels']:
            flags.append('VALID_PIXEL_COUNT_CHANGED')
        for basis in BASES:
            values = prices.get((code, year, basis), {})
            population = next((prices.get((code, year, b), {}).get('population') for b in BASES
                               if prices.get((code, year, b), {}).get('population') is not None), None)
            row = dict(template, gid_1=province['gid_1'], name_1=province['ten_tinh'], year=year, month=month,
                       province_code=code, **values)
            row.update(grdp_price_basis=basis, unit=values.get('unit', 'ty_vnd'),
                       light_basis=light_key, light_source=observation['source'] if observation else '',
                       image_quality_flags=';'.join(flags), paired=not month and (code, year) in paired_keys,
                       valid_pixels=observation['valid_pixels'] if observation else None,
                       valid_area_pct=number_or_none(quality_row['valid_area_pct']) if quality_row else None,
                       valid_area_km2=number_or_none(quality_row['valid_area_km2']) if quality_row else None,
                       stats_version=STATS_VERSION, gdp_change_pct=None,
                       sol_per_capita=None, light_gdp_elasticity=None, predicted_gdp=None,
                       derived_price_basis=basis, model_light_basis=light_key,
                       model_training_period=training_period if models[basis] else '',
                       model_n=models[basis]['n'] if models[basis] else None,
                       model_beta=rounded(models[basis]['beta']) if models[basis] else None,
                       area_method=observation.get('area_method', 'whole_pixel_approximation') if observation else '', comparison_note='')
            if not values:
                # Không để các giá trị cũ trong template bị gán sang cơ sở giá khác.
                row.update(gdp=None, population=population, economy_source='', price_base_year=2010 if basis == 'so_sanh' else None,
                           is_provisional=0, quality_flags='MISSING_GRDP_ROW')
            if observation is None:
                row.update(sol=None, sol_raw=None, sol_cal=None, sol_density=None, sol_change_pct=None,
                           lit_area_km2=None, lit_area_pct=None, calibration='PENDING', obs_status='O')
            if month:
                row['comparison_note'] = 'GRDP theo năm, lặp tham chiếu; không phải GRDP tháng.'
                if 'VALID_PIXEL_COUNT_CHANGED' in flags:
                    row['comparison_note'] += ' Số pixel hợp lệ thay đổi so tháng trước; thận trọng với biến động sáng.'
            else:
                previous_economy = prices.get((code, year-1, basis), {})
                row['gdp_change_pct'] = rounded(growth_pct(row.get('gdp'), previous_economy.get('gdp')), 4)
            if not month and observation:
                light = observation.get('sol_cal')
                population = row.get('population')
                row['sol_per_capita'] = rounded(light/population) if light is not None and population is not None and population > 0 else None
                # Tỷ số tăng trưởng khác β; không so xuyên mốc F16/F18 năm 2010.
                if previous and year != 2010:
                    dl = growth_pct(observation.get('sol_cal'), previous.get('sol_cal'))
                    dg = growth_pct(row.get('gdp'), previous_economy.get('gdp'))
                    if dl is not None and dg not in (None, 0):
                        row['light_gdp_elasticity'] = rounded(dl/dg)
                selected = observation.get(light_key)
                model = models[basis]
                if model and selected is not None and selected > 0 and observation['source'] == 'VIIRS':
                    row['predicted_gdp'] = rounded(math.exp(model['alpha']+model['beta']*math.log(selected)))
                if 'VALID_PIXEL_COUNT_CHANGED' in flags:
                    row['comparison_note'] = 'Số pixel hợp lệ thay đổi; biến động sáng có thể chịu ảnh hưởng độ phủ.'
            output.append(row)
    tables['night_economy'] = output
    # Giữ mô hình hiệu chỉnh riêng; thay mô hình GDP một giá bằng hai mô hình có mẫu chung.
    tables['calculation_models'] = [r for r in tables['calculation_models'] if r['model'] != 'gdp_log_regression']
    for basis, model in models.items():
        if model:
            years = [year for code, year in paired_keys]
            tables['calculation_models'].append(dict(model='gdp_log_regression', **model, price_basis=basis,
                                                     training_period=f'{min(years)}-{max(years)}',
                                                     light_basis=light_key, unit='ty_vnd', stats_version=STATS_VERSION,
                                                     common_sample=True))
    tables['economy_validation'] = [dict(
        input_price_rows=len(prices), output_rows=len(output), image_rows=len(observations),
        annual_rows=sum(not r['month'] for r in output), monthly_rows=sum(bool(r['month']) for r in output),
        common_model_sample=len(paired_keys), model_so_sanh=models['so_sanh'] is not None,
        model_hien_hanh=models['hien_hanh'] is not None,
        missing_population_rows=sum(r.get('population') is None for r in output),
        missing_grdp_input_values=sum(r['gdp'] is None for r in prices.values()),
        missing_image_result_rows=sum('MISSING_IMAGE' in r['image_quality_flags'] for r in output),
        empty_image_result_rows=sum('NO_VALID_PIXELS' in r['image_quality_flags'] for r in output),
        empty_images=sum(not r['valid_pixels'] for r in observations.values()),
        quality_linked_images=sum(key in quality for key in observations),
        quality_unlinked_images=sum(key not in quality for key in observations),
        area_method=next(iter({r.get('area_method', 'whole_pixel_approximation') for r in observations.values()}), ''), stats_version=STATS_VERSION)]
