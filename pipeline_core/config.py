# -*- coding: utf-8 -*-
"""
Cấu hình tập trung cho toàn bộ hệ thống Pipeline Viễn thám cấp huyện (2004–2025)
"""
import os
import sys
from pathlib import Path

# Chuỗi thời gian chuẩn
START_YEAR = 2004
END_YEAR = 2025
YEARS = list(range(START_YEAR, END_YEAR + 1))
MONTHS = list(range(1, 13))

# Dự án Google Earth Engine
DEFAULT_EE_PROJECT = os.environ.get("VNGIS_EE_PROJECT", "vngis-ee-2")

# Đường dẫn GADM 4.1 cho Việt Nam (ranh giới huyện trước sáp nhập)
GADM_VNM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/shp/gadm41_VNM_shp.zip"

# Thư mục gốc mặc định: ổ C trên Windows, thư mục home trên Linux/macOS
DEFAULT_OUTPUT_ROOT = r"C:\VNGIS_Data" if sys.platform == "win32" else str(Path.home() / "VNGIS_Data")

NTL_PACKAGE = "VN_NTL_Panel_2004_2025"
LANDCOVER_PACKAGE = "VN_LandCover_Panel_2004_2025"

# Danh mục 5 lớp phủ chuẩn
LANDCOVER_CLASSES = {
    1: {"name": "Đất nông nghiệp", "code": "dt_nong_nghiep", "color": "#FFD700"},
    2: {"name": "Đô thị và dịch vụ", "code": "dt_do_thi", "color": "#DC143C"},
    3: {"name": "Rừng", "code": "dt_rung", "color": "#228B22"},
    4: {"name": "Mặt nước", "code": "dt_mat_nuoc", "color": "#1E90FF"},
    5: {"name": "Đất khác", "code": "dt_khac", "color": "#D2B48C"}
}

# ---------------------------------------------------------------------------
# ẢNH BAN NGÀY: phân lớp bằng LUẬT NGƯỠNG CHỈ SỐ PHỔ (không dùng machine learning)
# Thứ tự ưu tiên: mặt nước -> đô thị -> rừng -> nông nghiệp -> đất khác.
# Chỉnh ngưỡng tại đây rồi chạy lại; mọi ngưỡng được ghi vào codebook.
# ---------------------------------------------------------------------------
LANDCOVER_THRESHOLDS = {
    "water_mndwi_min": 0.10,      # MNDWI > 0.10 và NDVI < water_ndvi_max -> mặt nước
    "water_ndvi_max": 0.20,
    "urban_ndbi_min": -0.05,      # NDBI > -0.05 và NDVI < urban_ndvi_max -> đô thị
    "urban_ndvi_max": 0.30,
    "forest_ndvi_min": 0.65,      # NDVI >= 0.65 -> rừng
    "forest_slope_ndvi_min": 0.50,  # hoặc NDVI >= 0.50 trên đất dốc >= forest_slope_deg
    "forest_slope_deg": 10.0,
    "agri_ndvi_min": 0.25,        # NDVI trong [0.25, ngưỡng rừng) -> nông nghiệp
    "agri_slope_max_deg": 15.0,   # nông nghiệp chỉ trên đất dốc < 15 độ
}

# Mùa khô dùng ghép ảnh năm: từ tháng 11 năm trước đến hết tháng 4 năm hiện tại
DRY_SEASON = {"start_month_prev_year": 11, "end_month": 4}
MAX_SCENE_CLOUD = 60  # % mây tối đa của cảnh trước khi che mây theo pixel

# Độ phân giải tải/tính toán (m)
SCALE = {"LANDSAT": 30, "SENTINEL2": 10, "DMSP": 1000, "VIIRS": 500}
# Sentinel-2 10 m rất nặng khi tải: cho phép tải ở độ phân giải thô hơn
SENTINEL2_DOWNLOAD_SCALE = int(os.environ.get("VNGIS_S2_SCALE", "10"))

# Ánh sáng ban đêm
DMSP_LAST_YEAR = 2013
VIIRS_FIRST_YEAR = 2013  # năm chồng lấn để hiệu chỉnh liên kết DMSP -> VIIRS
VIIRS_BACKGROUND_THRESHOLD = 0.5  # nW/cm²/sr, dưới ngưỡng coi là ánh sáng nền
DMSP_BACKGROUND_DN = 6            # DN <= 6 coi là nhiễu nền
VIIRS_MAX_RADIANCE = 300.0        # chặn điểm lóa

# Giới hạn dung lượng một lần getDownloadURL của GEE (~48 MB); để dư an toàn
EE_DOWNLOAD_MAX_BYTES = 32 * 1024 * 1024
EE_MAX_RETRIES = 5


def resolve_output_dir(custom_path=None):
    """
    Xác định đường dẫn lưu trữ gốc:
    1. Tham số dòng lệnh custom_path
    2. Biến môi trường OUTPUT_ROOT
    3. Mặc định C:\\VNGIS_Data (Windows) hoặc ~/VNGIS_Data
    """
    if custom_path and str(custom_path).strip():
        p = Path(custom_path).expanduser().resolve()
    elif os.environ.get("OUTPUT_ROOT", "").strip():
        p = Path(os.environ["OUTPUT_ROOT"].strip()).expanduser().resolve()
    else:
        p = Path(DEFAULT_OUTPUT_ROOT)

    p.mkdir(parents=True, exist_ok=True)
    return p


def get_ntl_package_dir(base_dir):
    d = Path(base_dir) / NTL_PACKAGE
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_landcover_package_dir(base_dir):
    d = Path(base_dir) / LANDCOVER_PACKAGE
    d.mkdir(parents=True, exist_ok=True)
    return d
