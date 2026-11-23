"""Thứ tự cột khi xuất: định danh → đầu vào Raw → kết quả Processed."""
IDENTITY_FIELDS=('province_code','province_name','gid_1','name_1','year','month','period','frequency')
RAW_FIELDS=('source','path','avg_rad','cf_cvg','stable_lights','population','gdp','grdp_so_sanh','grdp_hien_hanh',
            'grdp_price_basis','price_base_year','economy_source','is_provisional','grdp_unit','grdp_frequency')


def ordered_fields(fields):
    fields=list(dict.fromkeys(fields))
    leading=[f for f in IDENTITY_FIELDS+RAW_FIELDS if f in fields]
    remaining=[f for f in fields if f not in leading]
    # Phiên bản ánh sáng hiệu chỉnh đứng cuối nhóm Processed.
    calibrated=[f for f in remaining if f in ('sol_cal','calibration')]
    return leading+[f for f in remaining if f not in calibrated]+calibrated
