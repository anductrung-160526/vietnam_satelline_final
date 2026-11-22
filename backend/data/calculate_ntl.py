"""Tính lại chỉ số đêm từ GeoTIFF đã lọc, đã cắt/mask theo tỉnh.

Tính từng trường theo Night Data Dictionary; ảnh đầu vào đã lọc, không tính lại ảnh thô.
Xuất night_data.csv, night_economy.csv và các bảng ntl_* tương thích app.
Thêm --economy economy.csv để ghép dân số/GRDP; --calibrate để khớp mô hình năm 2013.
Không tải ảnh, không lọc ảnh thô, không suy ra ảnh năm từ bảng tháng.
Chạy: python -m backend.data.calculate_ntl --manifest danh_sach_anh.csv --root /data/SatelliteData
"""
import argparse
import csv
import json
import math
import os
import tempfile
from pathlib import Path

import numpy as np
from rasterio.windows import Window

NODATA = -9999
STATS_VERSION = 8  # v8: luồng hai giá GRDP, mẫu chung và cờ chất lượng phần E
LIT_THRESHOLD = {'VIIRS': 1.5, 'DMSP': 5.0}
BACKGROUND = {'VIIRS': 0.5, 'DMSP': 0.0}


def windows(height, width):
    for row in range(0, height, 512):
        for col in range(0, width, 512):
            yield Window(col, row, min(512, width-col), min(512, height-row))


def pixel_area_km2(transform, window, crs):
    """Giữ công thức diện tích của pipeline cho WGS84 và lưới chiếu mét."""
    if crs is None:
        raise ValueError('Ảnh thiếu CRS; không thể tính diện tích sáng.')
    if transform.b or transform.d:
        raise ValueError('Chưa hỗ trợ lưới ảnh xoay; cần ảnh north-up.')
    if crs.to_epsg() == 4326:
        rows = np.arange(window.row_off, window.row_off+window.height)+0.5
        lat = transform.f+rows*transform.e
        return (abs(transform.a*transform.e)*111.320**2*np.cos(np.radians(lat)))[:, None]
    if not crs.is_projected or crs.linear_units != 'metre':
        raise ValueError('CRS phải là EPSG:4326 hoặc hệ chiếu có đơn vị mét.')
    return np.full((int(window.height), 1), abs(transform.a*transform.e)/1e6)


def ntl_stats(path, threshold=None, background=0.0):
    """Tính từng thống kê từ ảnh đã lọc theo tỉnh; đọc theo ô để tiết kiệm RAM.

    Băng 1 = bức xạ; băng 2 tùy chọn phải có tên cf_cvg.
    Các tên rad_* là cột tương thích SQLite; tên dictionary được xuất ở bước cuối.
    """
    import rasterio

    # Bộ cộng dồn: đọc ảnh một lần, không tải cả tỉnh vào RAM.
    count = 0
    raw_sum = 0.0
    square_sum = 0.0
    light_sum = 0.0
    background_count = 0
    minimum = None
    maximum = None
    lit_count = 0
    lit_sum = 0.0
    lit_area = 0.0
    cloud_sum = 0.0
    cloud_count = 0

    with rasterio.open(path) as image:
        if image.count != 1 and not (
            image.count == 2 and image.descriptions == ('avg_rad', 'cf_cvg')
        ):
            raise ValueError('Cần ảnh bức xạ một băng hoặc hai băng avg_rad, cf_cvg đã lọc.')
        pixel_area_km2(image.transform, Window(0, 0, 1, 1), image.crs)
        cloud_tag = image.tags().get('CF_CVG_MEAN')

        for window in windows(image.height, image.width):
            radiation = image.read(1, window=window).astype('float64')
            valid = image.read_masks(1, window=window).astype(bool)
            valid &= np.isfinite(radiation) & (radiation != NODATA)
            values = radiation[valid]
            if values.size == 0:
                continue

            # total_pixels: đếm pixel hợp lệ; 0 là giá trị hợp lệ, không phải NoData.
            count += int(values.size)

            # tnl và sol_raw: tổng bức xạ TRƯỚC loại nền, trên cùng tập pixel.
            raw_sum += float(values.sum())

            # sol: pixel dưới ngưỡng nền đóng góp 0, không trừ ngưỡng khỏi pixel.
            above_background = values >= background if background else np.ones(values.shape, bool)
            light_sum += float(values[above_background].sum())
            background_count += int((~above_background).sum())

            # mean_rad, std_rad: cộng tổng và tổng bình phương để tính sau vòng lặp.
            square_sum += float(np.square(values).sum())

            # min_rad, max_rad: bức xạ nhỏ nhất/lớn nhất của tỉnh.
            minimum = float(values.min()) if minimum is None else min(minimum, float(values.min()))
            maximum = float(values.max()) if maximum is None else max(maximum, float(values.max()))

            if threshold is not None:
                lit_mask = valid & (radiation >= threshold)
                # lit_pixels: số pixel đạt ngưỡng sáng.
                lit_count += int(lit_mask.sum())
                # lit_pop_proxy: tổng bức xạ CHỈ trên vùng sáng, không phải dân số.
                lit_sum += float(radiation[lit_mask].sum())
                # lit_area_km2: cộng diện tích pixel sáng theo CRS và vĩ độ.
                areas = np.broadcast_to(
                    pixel_area_km2(image.transform, window, image.crs), radiation.shape
                )
                lit_area += float(areas[lit_mask].sum())

            if image.count == 2:
                # cloud_free_obs: trung bình cf_cvg trên cùng các pixel bức xạ hợp lệ.
                cloud = image.read(2, window=window).astype('float64')
                cloud_valid = valid & image.read_masks(2, window=window).astype(bool)
                cloud_valid &= np.isfinite(cloud) & (cloud >= 0)
                cloud_sum += float(cloud[cloud_valid].sum())
                cloud_count += int(cloud_valid.sum())

    # cloud_free_obs: ảnh một băng dùng thẻ do bước lọc ảnh đã ghi.
    cloud_mean = cloud_sum / cloud_count if cloud_count else None
    if cloud_mean is None and cloud_tag is not None:
        try:
            cloud_mean = number_or_none(cloud_tag)
        except ValueError:
            cloud_mean = None

    mean = raw_sum / count if count else None
    # Độ lệch chuẩn tổng thể (ddof=0), như công thức pipeline cũ.
    std = math.sqrt(max(square_sum / count - mean ** 2, 0)) if count else None
    # spatial_cv: thiếu dữ liệu -> trống; mean không dương -> 0 theo Task 3.
    cv = std / mean if count and mean > 0 else (0.0 if count else None)

    # Trả từng chỉ số; None xuất CSV thành ô trống, không biến thiếu dữ liệu thành 0.
    return {
        'valid_pixels': count,                       # total_pixels
        'sol_raw': rounded(raw_sum, 4) if count else None,  # tnl = sol_raw
        'sol': rounded(light_sum, 4) if count else None,
        'background_pixels': background_count if count else None,
        'background_threshold': background,
        'rad_mean': rounded(mean),                   # mean_rad
        'rad_std': rounded(std),                     # std_rad
        'rad_min': rounded(minimum, 4),              # min_rad
        'rad_max': rounded(maximum, 4),              # max_rad
        'rad_cv': rounded(cv, 4) if count and mean > 0 else None,
        'spatial_cv': rounded(cv, 4),
        'lit_pixels': lit_count if count and threshold is not None else None,
        'lit_sol': rounded(lit_sum, 4) if count and threshold is not None else None,
        'lit_area_km2': rounded(lit_area, 4) if count and threshold is not None else None,
        'lit_pixel_pct': rounded(100 * lit_count / count, 4)
                         if count and threshold is not None else None,
        'cloud_free_obs': rounded(cloud_mean, 4),
    }


def rounded(value, digits=6):
    return round(float(value), digits) if value is not None else None


def number_or_none(value):
    """Đọc số kinh tế/thẻ ảnh: ô rỗng là thiếu dữ liệu, không phải 0."""
    if value is None or str(value).strip() == '':
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f'Giá trị không hữu hạn: {value}')
    return number


def pct(current, previous):
    value = growth_pct(current, previous)
    return rounded(value, 4)



def growth_pct(current, previous):
    """Giữ đủ độ chính xác khi tính tỷ số tăng trưởng, chỉ làm tròn lúc xuất."""
    if current is None or previous is None or previous <= 0:
        return None
    return 100 * (current / previous - 1)


def read_manifest(path):
    """Mỗi dòng là một ảnh tỉnh, area_km2 là diện tích TỰ NHIÊN, không phải vùng hợp lệ."""
    path = Path(path).resolve()
    records, seen = [], set()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'province_code', 'province_name', 'year', 'month', 'source', 'path', 'area_km2'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('Manifest thiếu cột: '+', '.join(sorted(required-set(reader.fieldnames or []))))
        for number, raw in enumerate(reader, 2):
            if any(raw.get(k) is None for k in required):
                raise ValueError(f'Dòng {number}: thiếu ô dữ liệu trong CSV.')
            code = raw['province_code'].strip().zfill(2)
            year, month = int(raw['year']), int(raw['month'] or 0)
            source = raw['source'].strip().upper()
            area = float(raw['area_km2'])
            if not code.isdigit() or len(code) != 2 or not raw['province_name'].strip():
                raise ValueError(f'Dòng {number}: mã/tên tỉnh không hợp lệ.')
            if not 2004 <= year <= 2025 or not 0 <= month <= 12:
                raise ValueError(f'Dòng {number}: năm/tháng ngoài phạm vi.')
            if source not in LIT_THRESHOLD or (source == 'DMSP' and (month or year > 2013)) or (source == 'VIIRS' and year < 2013):
                raise ValueError(f'Dòng {number}: nguồn ảnh không khớp giai đoạn/tần suất.')
            if not math.isfinite(area) or area <= 0:
                raise ValueError(f'Dòng {number}: area_km2 phải dương và hữu hạn.')
            key = (code, year, month, source)
            if key in seen:
                raise ValueError(f'Dòng {number}: trùng ảnh {key}.')
            seen.add(key)
            image = Path(raw['path'].strip())
            if not raw['path'].strip():
                raise ValueError(f'Dòng {number}: thiếu đường dẫn ảnh.')
            image = image if image.is_absolute() else path.parent/image
            if not image.is_file():
                raise FileNotFoundError(image)
            records.append(dict(province_code=code, province_name=raw['province_name'].strip(),
                                year=year, month=month, source=source, path=image, area_km2=area))
    if not records:
        raise ValueError('Manifest không có ảnh nào.')
    return records


def calculate(records, economy=None, calibrate=False, economy_prices=None, image_quality=None, progress=False):
    annual, monthly, overlap = [], [], []
    lookup = {}
    for image_index, record in enumerate(records, 1):
        row = {k: v for k, v in record.items() if k != 'path'}
        source = row['source']
        row.update(ntl_stats(record['path'], LIT_THRESHOLD[source], BACKGROUND[source]))
        row['lit_threshold'] = LIT_THRESHOLD[source]
        # sol_density: SOL sau loại nền chia diện tích tự nhiên tỉnh.
        row['sol_density'] = (round(row['sol']/row['area_km2'], 6)
                              if row['sol'] is not None else None)
        # lit_area_pct: diện tích sáng / diện tích tự nhiên tỉnh * 100.
        row['lit_area_pct'] = (round(100*row['lit_area_km2']/row['area_km2'], 4)
                               if row['lit_area_km2'] is not None else None)
        row['period'] = f"{row['year']}-{row['month']:02}" if row['month'] else str(row['year'])
        row['frequency'] = 'monthly' if row['month'] else 'annual'
        row['calibration'] = 'PENDING'
        row['status'] = 'OK' if row['valid_pixels'] else 'INSUFFICIENT_QUALITY'
        row['obs_status'] = ('L' if not row['valid_pixels'] else
                             'B' if not row['month'] and row['year'] in (2010, 2014) else
                             'U' if row['cloud_free_obs'] is not None and row['cloud_free_obs'] < 2 else 'A')
        lookup[(row['province_code'], row['year'], row['month'], source)] = row
        if row['month']:
            monthly.append(row)
        elif source == 'DMSP' or row['year'] >= 2014:
            annual.append(row)
        if progress and (image_index % 100 == 0 or image_index == len(records)):
            print(f'Đã tính chỉ số {image_index}/{len(records)} ảnh', flush=True)
    # Chuỗi năm: VIIRS 2013 chỉ dùng làm cặp chồng lấn, không vào bảng ntl_annual.
    for row in annual:
        previous = (lookup.get((row['province_code'], row['year']-1, 0, row['source']))
                    if row['year'] not in (2010, 2014) else None)
        row['sol_change_pct'] = pct(row['sol'], previous['sol']) if previous else None
        row['note'] = 'DOI_NGUON_ANH_CHUA_HIEU_CHINH' if row['year'] == 2014 else ''
    for row in monthly:
        code, year, month = row['province_code'], row['year'], row['month']
        previous_year = lookup.get((code, year-1, month, 'VIIRS'))
        previous_month = lookup.get((code, year if month > 1 else year-1, month-1 if month > 1 else 12, 'VIIRS'))
        row['sol_change_yoy_pct'] = pct(row['sol'], previous_year['sol']) if previous_year else None
        row['sol_change_mom_pct'] = pct(row['sol'], previous_month['sol']) if previous_month else None
        # sol_ma3 của app dùng ba tháng LỊCH; tnl_ma3 theo Task 3 được tính riêng.
        values = []
        for offset in range(3):
            index = year*12+month-1-offset
            item = lookup.get((code, index//12, index % 12+1, 'VIIRS'))
            if item and item['sol'] is not None:
                values.append(item['sol'])
        row['sol_ma3'] = round(sum(values)/len(values), 4) if values else None
    for code in sorted({r['province_code'] for r in records}):
        dmsp = lookup.get((code, 2013, 0, 'DMSP'))
        viirs = lookup.get((code, 2013, 0, 'VIIRS'))
        if dmsp and viirs:
            overlap.append(dict(province_code=code, province_name=dmsp['province_name'], year=2013,
                                sol_dmsp=dmsp['sol'], sol_viirs=viirs['sol'], area_km2=dmsp['area_km2']))
    tables = dict(ntl_annual=annual, ntl_monthly=monthly,
                  ntl_panel=[], ntl_overlap_2013=overlap)
    # Xuất bảng dictionary; các bảng ntl_* phía trên giữ tên cột mà app đang đọc.
    add_dictionary_tables(tables, records, economy or {}, calibrate)
    if economy_prices is not None:
        from .economy_indices import attach_two_prices
        attach_two_prices(tables, economy_prices, image_quality, calibrate)
    return tables


# Tên cột theo dictionary; định danh lặp lại ở hai CSV để ghép theo tỉnh/năm/tháng.

NIGHT_DATA_FIELDS = (
    'gid_1', 'name_1', 'year', 'month', 'avg_rad', 'cf_cvg', 'area_km2',
    'total_pixels', 'cloud_free_obs', 'tnl', 'mean_rad', 'std_rad', 'min_rad',
    'max_rad', 'spatial_cv', 'lit_pixels', 'lit_pop_proxy',
    'electrification_ratio_pct', 'tnl_ma3', 'tnl_mom_growth_pct',
)
NIGHT_ECONOMY_FIELDS = (
    'gid_1', 'name_1', 'year', 'month', 'population', 'gdp',
    'sol_raw', 'sol', 'lit_area_km2', 'lit_area_pct', 'sol_density',
    'sol_change_pct', 'sol_cal', 'sol_per_capita', 'light_gdp_elasticity',
    'predicted_gdp',
)


def read_economy(path):
    """Đọc population, gdp/GRDP theo khóa province_code + year; không sinh số giả."""
    if path is None:
        return {}
    result = {}
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            key = (row['province_code'].strip().zfill(2), int(row['year']))
            if key in result:
                raise ValueError(f'Trùng dòng kinh tế {key}')
            # gdp của dictionary dùng GRDP tỉnh khi file có cột grdp.
            gdp = number_or_none(row.get('grdp'))
            if gdp is None:
                gdp = number_or_none(row.get('gdp'))
            result[key] = {
                'population': number_or_none(row.get('population')),
                'gdp': gdp,
                'price_basis': row.get('grdp_price_basis', '').strip(),
                'economy_source': row.get('source', ''),
            }
    return result


def fit_log_model(pairs, minimum):
    """OLS rõ từng bước: ln(y) = alpha + beta * ln(x), chỉ nhận số dương."""
    points = [(math.log(x), math.log(y)) for x, y in pairs
              if x is not None and y is not None and x > 0 and y > 0]
    if len(points) < minimum:
        return None
    x = np.array([p[0] for p in points])
    y = np.array([p[1] for p in points])
    denominator = float(np.square(x - x.mean()).sum())
    if denominator == 0:
        return None
    beta = float(((x - x.mean()) * (y - y.mean())).sum() / denominator)
    alpha = float(y.mean() - beta * x.mean())
    residual = float(np.square(y - alpha - beta * x).sum())
    total = float(np.square(y - y.mean()).sum())
    return {'alpha': alpha, 'beta': beta, 'n': len(points),
            'r2': 1 - residual / total if total else None}


def add_dictionary_tables(tables, records, economy, calibrate):
    """Tính chỉ số dictionary, xuất Night Data và Night Economy theo cấp tỉnh.

    Chuỗi TNL giữ đúng phép tính Task 3. Chuỗi SOL dùng bảng năm riêng.
    Hiệu chỉnh chỉ chạy khi yêu cầu --calibrate, cần >=30 tỉnh chồng lấn 2013.
    Không hiệu chỉnh F16/F18 năm 2010. Không ghi đè sol gốc.
    """
    import rasterio

    catalog_path = Path(__file__).resolve().parents[1] / 'core/ranh_gioi/config/danh_muc_tinh.json'
    catalog = {p['ma_tinh']: p for p in json.loads(catalog_path.read_text(encoding='utf-8'))}
    images = {(r['province_code'], r['year'], r['month'], r['source']): r['path']
              for r in records}
    annual = tables['ntl_annual']
    monthly = tables['ntl_monthly']

    # sol_cal: khớp DMSP -> VIIRS bằng cặp SOL 2013, cùng ngưỡng nền đã tính ở trên.
    calibration = None
    if calibrate:
        pairs = [(r['sol_dmsp'], r['sol_viirs']) for r in tables['ntl_overlap_2013']]
        calibration = fit_log_model(pairs, minimum=30)
        if calibration is None or calibration['beta'] <= 0:
            raise ValueError('Hiệu chỉnh cần >=30 tỉnh có cặp SOL 2013 dương và mô hình hợp lệ.')

    for row in annual + monthly:
        if row['source'] == 'VIIRS':
            row['sol_cal'] = row['sol']  # VIIRS đã ở thang đích.
        elif calibration and row['sol'] is not None and row['sol'] >= 0:
            value = row['sol']
            row['sol_cal'] = (math.exp(calibration['alpha']) * value ** calibration['beta']
                              if value > 0 else 0.0)
        else:
            row['sol_cal'] = None
        if calibration:
            row['calibration'] = 'DMSP_TO_VIIRS_POWER_OVERLAP2013_v1'

    # Các cột _cal chỉ để tương thích schema app; dictionary gộp trong một tên.
    annual_by_key = {(r['province_code'], r['year']): r for r in annual}
    for row in annual:
        value = row['sol_cal']
        row['sol_density_cal'] = rounded(value / row['area_km2']) if value is not None else None
        previous = annual_by_key.get((row['province_code'], row['year']-1))
        row['sol_change_cal_pct'] = pct(value, previous['sol_cal']) if previous and row['year'] != 2010 else None

    # tnl_ma3 và tnl_mom_growth_pct: theo các DÒNG tháng của từng tỉnh, như Task 3.
    # Không thay thế chúng bằng sol_ma3/sol_change_mom_pct của app (cửa sổ tháng lịch).
    for code in {r['province_code'] for r in monthly}:
        series = sorted([r for r in monthly if r['province_code'] == code],
                        key=lambda r: (r['year'], r['month']))
        for i, row in enumerate(series):
            window = [r['sol_raw'] for r in series[max(0, i-2):i+1]
                      if r['sol_raw'] is not None]
            row['tnl_ma3'] = sum(window) / len(window) if window else None
            row['tnl_mom_growth_pct'] = pct(row['sol_raw'], series[i-1]['sol_raw']) if i else None

    # Ghép population và gdp: số kinh tế theo năm, không suy từ độ sáng.
    for row in annual + monthly:
        values = economy.get((row['province_code'], row['year']), {})
        row['population'] = values.get('population')
        row['gdp'] = values.get('gdp')
        row['price_basis'] = values.get('price_basis', '')
        row['economy_source'] = values.get('economy_source', '')

    # predicted_gdp: khớp mô hình trên VIIRS 2014–2025, GRDP giá so sánh, >=10 điểm.
    # Không dùng hệ số này như light_gdp_elasticity: hai phép tính khác nhau.
    training = [(r['sol_cal'], r['gdp']) for r in annual
                if r['year'] >= 2014 and r['price_basis'] == 'so_sanh'
                and 'GIA_LAP' not in r['economy_source'].upper()]
    gdp_model = fit_log_model(training, minimum=10)
    annual_lookup = {(r['province_code'], r['year']): r for r in annual}
    for row in annual:
        # sol_per_capita: dùng SOL đã hiệu chỉnh chia dân số, không chia SOL thô.
        light = row['sol_cal']
        population = row['population']
        row['sol_per_capita'] = (light / population
                                 if light is not None and population is not None and population > 0 else None)
        # light_gdp_elasticity: %Δ sol_cal / %Δ gdp giữa hai năm liền kề.
        previous = annual_lookup.get((row['province_code'], row['year']-1))
        row['light_gdp_elasticity'] = None
        if (previous and row['year'] != 2010 and row['price_basis'] == 'so_sanh'
                and previous['price_basis'] == 'so_sanh'):
            light_growth = growth_pct(light, previous['sol_cal'])
            gdp_growth = growth_pct(row['gdp'], previous['gdp'])
            if light_growth is not None and gdp_growth not in (None, 0):
                row['light_gdp_elasticity'] = light_growth / gdp_growth
        # predicted_gdp: đổi dự báo log về mức GDP; không tự hiệu chỉnh sai lệch log.
        row['predicted_gdp'] = (math.exp(gdp_model['alpha'] + gdp_model['beta'] * math.log(light))
                                if gdp_model and light is not None and light > 0 else None)

    data_rows = []
    economy_rows = []
    for row in sorted(annual + monthly, key=lambda r: (r['province_code'], r['year'], r['month'])):
        province = catalog.get(row['province_code'])
        if province is None:
            raise ValueError(f"Không có mã tỉnh trong danh mục: {row['province_code']}")
        # Xuất gid_1, name_1, year, month: định danh tỉnh, không còn mã xã.
        identity = {'gid_1': province['gid_1'], 'name_1': row['province_name'],
                    'year': row['year'], 'month': row['month']}
        image_path = images[(row['province_code'], row['year'], row['month'], row['source'])]
        with rasterio.open(image_path) as image:
            # avg_rad/cf_cvg là mảng pixel: CSV chỉ lưu tham chiếu băng ảnh, không ép thành số.
            radiation_ref = str(image_path.resolve()) + '#band=1' if row['source'] == 'VIIRS' else None
            cloud_ref = str(image_path.resolve()) + '#band=2' if image.count == 2 else None
        # Xuất Night Data: từng cột tương ứng chính xác tên trong dictionary.
        data = dict(identity)
        data['avg_rad'] = radiation_ref
        data['cf_cvg'] = cloud_ref
        data['area_km2'] = row['area_km2']
        data['total_pixels'] = row['valid_pixels']
        data['cloud_free_obs'] = row['cloud_free_obs']
        data['tnl'] = row['sol_raw']
        data['mean_rad'] = row['rad_mean']
        data['std_rad'] = row['rad_std']
        data['min_rad'] = row['rad_min']
        data['max_rad'] = row['rad_max']
        data['spatial_cv'] = row['spatial_cv']
        data['lit_pixels'] = row['lit_pixels']
        data['lit_pop_proxy'] = row['lit_sol']
        data['electrification_ratio_pct'] = row['lit_pixel_pct']
        data['tnl_ma3'] = rounded(row.get('tnl_ma3'), 4)
        data['tnl_mom_growth_pct'] = row.get('tnl_mom_growth_pct')
        data_rows.append(data)

        # Xuất Night Economy: sol_raw/sol luôn giữ trước/sau loại nền để tham chiếu.
        output = dict(identity)
        output['population'] = row['population']
        output['gdp'] = row['gdp']
        output['sol_raw'] = row['sol_raw']
        output['sol'] = row['sol']
        output['lit_area_km2'] = row['lit_area_km2']
        output['lit_area_pct'] = row['lit_area_pct']
        output['sol_cal'] = rounded(row['sol_cal'], 4)
        # sol_density: một tên, chọn chuỗi theo --calibrate, ghi nguồn ở light_basis.
        selected_light = row['sol_cal'] if calibrate else row['sol']
        output['sol_density'] = (rounded(selected_light / row['area_km2'])
                                 if selected_light is not None else None)
        # sol_change_pct: thay đổi NĂM; dòng tháng để trống, không so với dòng năm.
        output['sol_change_pct'] = None
        if row['month'] == 0 and row['year'] != 2010:
            previous = annual_lookup.get((row['province_code'], row['year']-1))
            if previous and (calibrate or previous['source'] == row['source']):
                previous_light = previous['sol_cal'] if calibrate else previous['sol']
                output['sol_change_pct'] = pct(selected_light, previous_light)
        # Ba chỉ số ghép kinh tế chỉ tính trên dòng NĂM, không giả thành số tháng.
        output['sol_per_capita'] = rounded(row.get('sol_per_capita'))
        output['light_gdp_elasticity'] = rounded(row.get('light_gdp_elasticity'))
        output['predicted_gdp'] = rounded(row.get('predicted_gdp'))
        # Metadata đi cùng CSV để không nhầm chuỗi thô/hiệu chỉnh hay nguồn kinh tế.
        output['light_basis'] = 'sol_cal' if calibrate else 'sol'
        output['grdp_price_basis'] = row['price_basis']
        output['economy_source'] = row['economy_source']
        output['calibration'] = row['calibration']
        output['obs_status'] = row['obs_status']
        economy_rows.append(output)

    # Xuất panel: DMSP theo năm + VIIRS theo tháng từ 2014, cùng metadata hiệu chỉnh.
    tables['ntl_panel'] = [dict(r) for r in annual if r['source'] == 'DMSP']
    tables['ntl_panel'] += [dict(r) for r in monthly if r['year'] >= 2014]
    tables['night_data'] = data_rows
    tables['night_economy'] = economy_rows
    # Xuất mô hình kèm số quan sát để tái lập các giá trị hiệu chỉnh và dự báo.
    # GDP khớp trên VIIRS từ 2014, giá so sánh; dự báo là exp của đường hồi quy log.
    tables['calculation_models'] = []
    for name, model in [('dmsp_to_viirs', calibration), ('gdp_log_regression', gdp_model)]:
        if model:
            tables['calculation_models'].append({'model': name, **model,
                                                 'stats_version': STATS_VERSION,
                                                 'price_basis': 'so_sanh' if name == 'gdp_log_regression' else '',
                                                 'training_period': '2014-2025' if name == 'gdp_log_regression' else '2013'})


def write_tables(tables, directory, overwrite=False):
    """Xuất từng file nguyên tử; chặn ghi đè mặc định để giữ kết quả đang dùng."""
    directory = Path(directory)
    paths = {name: directory/(name+'.csv') for name in tables}
    if not overwrite and any(p.exists() for p in paths.values()):
        raise FileExistsError('Đã có bảng kết quả; chọn thư mục khác hoặc thêm --overwrite.')
    directory.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        known = {'night_data': NIGHT_DATA_FIELDS, 'night_economy': NIGHT_ECONOMY_FIELDS}
        fields = list(known.get(name, ()))
        extra = sorted({k for row in rows for k in row} - set(fields))
        fields += extra
        if not fields:
            fields = ['province_code', 'year']
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8-sig', newline='',
                                             dir=directory, delete=False) as stream:
                temporary = Path(stream.name)
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(sorted(rows, key=lambda r: (r.get('province_code', r.get('gid_1', '')), r.get('year', 0), r.get('month', 0))))
            os.replace(temporary, paths[name])
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path, help='CSV danh sách ảnh theo tỉnh')
    parser.add_argument('--root', type=Path, default=Path('/data/SatelliteData'))
    parser.add_argument('--output', type=Path, help='Thư mục CSV; mặc định <root>/VN_NTL_Panel_2004_2025/data_processed')
    prices = parser.add_mutually_exclusive_group()
    prices.add_argument('--economy', type=Path, help='CSV kinh tế một giá cũ: province_code + year')
    prices.add_argument('--economy-prices', type=Path, help='grdp_all_prices.csv hai cơ sở giá của phần A')
    parser.add_argument('--class-validation', type=Path, help='light_class_validation.csv phần D, dùng cùng --economy-prices')
    parser.add_argument('--calibrate', action='store_true', help='Khớp hiệu chỉnh từ >=30 cặp tỉnh DMSP/VIIRS 2013')
    parser.add_argument('--overwrite', action='store_true', help='Cho phép thay các bảng kết quả đã có')
    args = parser.parse_args()
    directory = args.output or args.root/'VN_NTL_Panel_2004_2025'/'data_processed'
    try:
        records = read_manifest(args.manifest)
        # Chặn ghi đè trước khi đọc ảnh lớn. --output cho phép tính thử ở thư mục khác.
        if not args.overwrite and any((directory/(n+'.csv')).exists() for n in ('ntl_annual', 'ntl_monthly', 'ntl_panel', 'ntl_overlap_2013',
                                                                                   'night_data', 'night_economy', 'calculation_models', 'economy_validation')):
            raise FileExistsError('Đã có bảng kết quả; chọn --output khác hoặc thêm --overwrite.')
        if args.class_validation and not args.economy_prices:
            raise ValueError('--class-validation cần đi cùng --economy-prices.')
        price_rows, quality_rows = None, None
        if args.economy_prices:
            from .economy_indices import read_prices, read_image_quality
            price_rows = read_prices(args.economy_prices)
            quality_rows = read_image_quality(args.class_validation)
        tables = calculate(records, economy=read_economy(args.economy), calibrate=args.calibrate,
                           economy_prices=price_rows, image_quality=quality_rows, progress=True)
        write_tables(tables, directory, args.overwrite)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Lỗi: {error}\n')
    for name, rows in tables.items():
        print(f'{name}: {len(rows)} dòng -> {directory/(name+".csv")}')
    print('Đã hiệu chỉnh DMSP–VIIRS.' if args.calibrate else
          'Chưa hiệu chỉnh DMSP; sol_cal của VIIRS bằng sol, DMSP để trống.')
    if args.output is None:
        print('Nạp vào app bằng load_demo --indices-dir tới thư mục kết quả; không reset database/COG.')
    else:
        print('Kết quả ở thư mục --output; kiểm tra trước khi dùng làm dữ liệu của app.')
    print('Các chỉ số kinh tế thiếu đầu vào/mô hình hợp lệ được để trống trong CSV.')


if __name__ == '__main__':
    main()
