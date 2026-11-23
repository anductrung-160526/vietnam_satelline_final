"""Chỉ số kinh tế từ số liệu đã nạp; không xử lý ảnh hoặc nội suy ô thiếu."""
import math
from .chi_so import TOI_THIEU_QUAN_SAT

# Xuất các thống kê ảnh đã tính, dùng cùng tên trường trong Data Dictionary.
OBSERVATION_FIELDS = {
    'sol_raw': 'sol_raw', 'sol': 'sol', 'sol_density': 'sol_density',
    'sol_change_pct': 'sol_change_pct', 'sol_ma3': 'sol_ma3',
    'sol_change_mom_pct': 'sol_change_mom_pct', 'sol_change_yoy_pct': 'sol_change_yoy_pct',
    'mean_rad': 'rad_mean', 'std_rad': 'rad_std', 'min_rad': 'rad_min',
    'max_rad': 'rad_max', 'spatial_cv': 'rad_cv',
    'lit_threshold': 'lit_threshold', 'lit_pixels': 'lit_pixels', 'lit_sol': 'lit_sol',
    'lit_area_km2': 'lit_area_km2', 'lit_area_pct': 'lit_area_pct',
    'background_threshold': 'background_threshold', 'background_pixels': 'background_pixels',
}


def growth(value, previous):
    """Tốc độ thay đổi (%); không thể chia cho mốc thiếu hoặc không dương."""
    if value is None or previous is None or previous <= 0:
        return None
    return 100 * (value / previous - 1)


def add_economic_metrics(rows, observations, prices, basis, fits):
    chosen = 'hien_hanh' if basis == 'hien_hanh' else 'so_sanh'

    # Hồi quy log–log: tính hệ số chưa làm tròn trên đúng mẫu chung của biểu đồ.
    for price, fit in fits.items():
        pairs = [(math.log(r['sol']), math.log(r['grdp_' + price])) for r in rows if r['paired']]
        fit.update(alpha=None, beta=None, r2=None, n=len(pairs))
        if len(pairs) < TOI_THIEU_QUAN_SAT:
            continue
        mean_x = sum(x for x, y in pairs) / len(pairs)
        mean_y = sum(y for x, y in pairs) / len(pairs)
        sxx = sum((x - mean_x) ** 2 for x, y in pairs)
        if sxx == 0:
            continue
        beta = sum((x - mean_x) * (y - mean_y) for x, y in pairs) / sxx
        alpha = mean_y - beta * mean_x
        total = sum((y - mean_y) ** 2 for x, y in pairs)
        residual = sum((y - alpha - beta * x) ** 2 for x, y in pairs)
        fit.update(alpha=alpha, beta=beta, r2=1 - residual / total if total else None, n=len(pairs))

    fit = fits[chosen]
    for row in rows:
        code, year = row['province_code'], row['year']
        observation = observations.get((code, year), {})
        previous = observations.get((code, year - 1), {})
        for field, column in OBSERVATION_FIELDS.items():
            row[field] = observation.get(column)

        # Mật độ kinh tế đêm theo ánh sáng: SOL chia diện tích tự nhiên tỉnh.
        area = observation.get('area_km2')
        row['sol_density'] = row['sol'] / area if row['sol'] is not None and area and area > 0 else None

        # Tăng trưởng SOL và GRDP: tham chiếu đúng năm lịch trước, cùng cơ sở đo.
        comparable = (observation.get('source') is not None
                      and observation.get('source') == previous.get('source')
                      and year not in (2010, 2014))
        row['sol_change_pct'] = growth(row['sol'], previous.get('sol')) if comparable else None
        current_grdp = prices.get((code, year, chosen), {}).get('grdp')
        previous_grdp = prices.get((code, year - 1, chosen), {}).get('grdp')
        row['gdp_change_pct'] = growth(current_grdp, previous_grdp)

        # Tỷ số tăng trưởng ánh sáng–GRDP; khác với beta của mô hình hồi quy.
        light_growth, grdp_growth = row['sol_change_pct'], row['gdp_change_pct']
        row['light_gdp_elasticity'] = (light_growth / grdp_growth
                                      if light_growth is not None and grdp_growth not in (None, 0) else None)

        # Cường độ ánh sáng trên GRDP: U trên một tỷ đồng, cùng cơ sở giá đã chọn.
        row['sol_gdp_ratio'] = (row['sol'] / current_grdp
                               if row['sol'] is not None and current_grdp is not None and current_grdp > 0 else None)

        # GRDP ước lượng từ ánh sáng: chuyển ngược mô hình log–log, không dự báo thời gian.
        row['predicted_gdp'] = None
        if (row['sol'] is not None and row['sol'] > 0 and observation.get('source') == 'VIIRS'
                and row.get('provenance_consistent', True) and fit.get('beta') is not None):
            exponent = fit['alpha'] + fit['beta'] * math.log(row['sol'])
            if exponent < 709:
                row['predicted_gdp'] = math.exp(exponent)
    return rows
