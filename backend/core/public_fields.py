"""Danh mục hiển thị/xuất dữ liệu đã thu gọn theo yêu cầu; metadata kỹ thuật giữ nội bộ."""
ALIASES={'province_name':'name_1','valid_pixels':'total_pixels','rad_mean':'mean_rad','rad_std':'std_rad',
         'rad_min':'min_rad','rad_max':'max_rad','rad_cv':'spatial_cv','lit_pixel_pct':'electrification_ratio_pct'}
PUBLIC_FIELDS=frozenset(['province_code', 'gid_1', 'name_1', 'year', 'month', 'source', 'avg_rad', 'cf_cvg', 'grdp_so_sanh', 'grdp_hien_hanh', 'area_km2', 'total_pixels', 'sol_raw', 'sol', 'background_threshold', 'background_pixels', 'mean_rad', 'std_rad', 'min_rad', 'max_rad', 'spatial_cv', 'lit_threshold', 'lit_pixels', 'lit_sol', 'lit_area_km2', 'lit_area_pct', 'electrification_ratio_pct', 'sol_density', 'tnl_ma3', 'tnl_mom_growth_pct', 'sol_ma3', 'sol_change_mom_pct', 'sol_change_yoy_pct', 'sol_change_pct', 'gdp_change_pct', 'class_index', 'lower_bound', 'upper_bound', 'light_class.area_km2', 'class_area_pct', 'breaks', 'reference_year', 'moran_i'])

def is_public(field):
    return ALIASES.get(field,field) in PUBLIC_FIELDS

def is_fake(row):
    return any(any(marker in str(row.get(key,'')).upper() for marker in ('GIA_LAP','SIMULATED','SYNTHETIC'))
               for key in ('source','status','note','economy_source','image_source'))
