# -*- coding: utf-8 -*-
"""
Cấu hình tập trung cho toàn bộ hệ thống Pipeline Viễn thám cấp huyện (2004–2025)
"""
import os
from pathlib import Path

# Chuỗi thời gian chuẩn
START_YEAR = 2004
END_YEAR = 2025
YEARS = list(range(START_YEAR, END_YEAR + 1))
MONTHS = list(range(1, 13))

# Dự án Google Earth Engine
DEFAULT_EE_PROJECT = os.environ.get("VNGIS_EE_PROJECT", "vngis-ee-soc-trang-yen-bai")

# Đường dẫn GADM 4.1 cho Việt Nam
GADM_VNM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/shp/gadm41_VNM_shp.zip"

# Danh mục 5 lớp phủ chuẩn
LANDCOVER_CLASSES = {
    1: {"name": "Đất nông nghiệp", "code": "dt_nong_nghiep", "color": "#FFD700"},
    2: {"name": "Đô thị và dịch vụ", "code": "dt_do_thi", "color": "#DC143C"},
    3: {"name": "Rừng", "code": "dt_rung", "color": "#228B22"},
    4: {"name": "Mặt nước", "code": "dt_mat_nuoc", "color": "#1E90FF"},
    5: {"name": "Đất khác", "code": "dt_khac", "color": "#D2B48C"}
}

def resolve_output_dir(custom_path=None):
    """
    Xác định đường dẫn lưu trữ gốc:
    1. Tham số dòng lệnh custom_path
    2. Biến môi trường OUTPUT_ROOT
    3. Mặc định là thư mục chứa dự án hiện tại
    """
    if custom_path and str(custom_path).strip():
        p = Path(custom_path).resolve()
    elif os.environ.get("OUTPUT_ROOT", "").strip():
        p = Path(os.environ["OUTPUT_ROOT"].strip()).resolve()
    else:
        p = Path(__file__).resolve().parent.parent

    p.mkdir(parents=True, exist_ok=True)
    return p

def get_ntl_package_dir(base_dir):
    d = Path(base_dir) / "VN_NTL_Panel_2004_2025"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_landcover_package_dir(base_dir):
    d = Path(base_dir) / "VN_LandCover_Panel_2004_2025"
    d.mkdir(parents=True, exist_ok=True)
    return d
