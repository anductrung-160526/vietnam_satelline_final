# -*- coding: utf-8 -*-
"""
Sinh Codebook/Data Dictionary (Markdown + Excel) cho 2 gói dữ liệu cấp huyện:
VN_NTL_Panel_2004_2025 và VN_LandCover_Panel_2004_2025.
"""
import json
from pathlib import Path
import pandas as pd
from pipeline_core.config import LANDCOVER_THRESHOLDS, NTL_PACKAGE, LANDCOVER_PACKAGE
from pipeline_core.utils import df_to_markdown

COLS = ["Tên biến", "Nhãn / Mô tả", "Nguồn dữ liệu", "Công thức / Thuật toán", "Kiểu dữ liệu", "Đơn vị đo"]
STR, NUM, INT = "String (Chuỗi)", "Numeric (Số thực)", "Numeric (Số nguyên)"


def v(name, label, source, formula, dtype, unit):
    return dict(zip(COLS, [name, label, source, formula, dtype, unit]))


COMMON_VARS = [
    v("ma_tinh", "Mã tỉnh/thành phố (bộ mã 63 tỉnh trước sáp nhập)", "Cục Thống kê; nếu chưa có mã thì GADM 4.1",
      "Tra theo tên tỉnh trong pipeline_core/data/gso_district_codes.csv", STR, "Mã 2 chữ số"),
    v("ten_tinh", "Tên tỉnh/thành phố", "GADM 4.1 Level 1", "Thuộc tính ranh giới", STR, ""),
    v("ma_huyen", "Mã quận/huyện/thị xã. Khóa chính cùng 'nam'", "Cục Thống kê; nếu chưa có mã thì GID_2 của GADM",
      "Tra theo tên tỉnh + tên huyện; không tự sinh mã", STR, "Mã 3 chữ số"),
    v("ten_huyen", "Tên đơn vị hành chính cấp huyện", "GADM 4.1 Level 2", "Thuộc tính ranh giới", STR, ""),
    v("ma_huyen_gadm", "Mã GADM của huyện (GID_2), dùng để ghép ranh giới", "GADM 4.1 Level 2", "", STR, ""),
    v("nam", "Năm quan sát", "", "Năm tổng hợp ảnh", INT, "Năm"),
]

NTL_CODEBOOK_DATA = COMMON_VARS + [
    v("nguon_anh", "Nguồn ảnh của năm", "DMSP-OLS (2004–2012), SNPP-VIIRS (2013–2025)",
      "VIIRS ưu tiên bản năm EOG (ANNUAL_V21/V22), thiếu thì tổng hợp từ ảnh tháng", STR, ""),
    v("sol_ntl", "Quy mô kinh tế đêm: tổng lượng ánh sáng (Sum of Light)", "DMSP-OLS / SNPP-VIIRS DNB",
      "Σ(bức xạ pixel × diện tích pixel km²) trong ranh giới huyện, sau lọc nhiễu; DMSP quy đổi về VIIRS",
      NUM, "nW/cm²/sr·km²"),
    v("mat_do_ntl", "Mật độ kinh tế đêm", "Tính toán", "sol_ntl / dien_tich_km2", NUM, "nW/cm²/sr"),
    v("thay_doi_ntl", "Mức độ thay đổi so với năm trước", "Tính toán",
      "(sol_ntl_t − sol_ntl_t−1) / sol_ntl_t−1 × 100; trống nếu thiếu năm trước", NUM, "%"),
    v("dien_tich_km2", "Diện tích tự nhiên của huyện", "GADM 4.1", "Diện tích đa giác (GEE, geodesic)", NUM, "km²"),
    v("sol_ntl_goc", "Tổng lượng ánh sáng của ảnh gốc, chưa lọc nhiễu/hiệu chỉnh", "DMSP-OLS / SNPP-VIIRS",
      "Như sol_ntl nhưng trên ảnh thô", NUM, "DN·km² (DMSP) hoặc nW/cm²/sr·km² (VIIRS)"),
    v("don_vi_goc", "Đơn vị của sol_ntl_goc", "", "", STR, ""),
    v("so_pixel", "Số pixel trong ranh giới huyện", "", "Đếm pixel tại độ phân giải tính toán", INT, "pixel"),
    v("thang", "Tháng (chỉ có trong bảng VIIRS theo tháng)", "SNPP-VIIRS DNB Monthly", "", INT, "Tháng"),
    v("cf_cvg_tb", "Số lượt quan sát không mây trung bình (bảng tháng)", "VIIRS cf_cvg", "Trung bình trong huyện",
      NUM, "lượt"),
    v("ghi_chu", "Ghi chú xử lý", "", "", STR, ""),
]

LANDCOVER_CODEBOOK_DATA = COMMON_VARS + [
    v("nguon_anh", "Nguồn ảnh của dòng dữ liệu", "Landsat 5/7/8/9 (USGS), Sentinel-2 (Copernicus)",
      "Mỗi huyện-năm có 1 dòng Landsat và (từ 2015) 1 dòng Sentinel-2", STR, ""),
    v("dt_nong_nghiep", "Diện tích đất nông nghiệp", "Ảnh ban ngày", "Lớp 1, phân lớp theo ngưỡng", NUM, "ha"),
    v("dt_do_thi", "Diện tích đất đô thị và dịch vụ", "Ảnh ban ngày", "Lớp 2", NUM, "ha"),
    v("dt_rung", "Diện tích rừng", "Ảnh ban ngày", "Lớp 3", NUM, "ha"),
    v("dt_mat_nuoc", "Diện tích mặt nước", "Ảnh ban ngày", "Lớp 4", NUM, "ha"),
    v("dt_khac", "Diện tích đất khác", "Ảnh ban ngày", "Lớp 5 (còn lại)", NUM, "ha"),
    v("dt_khong_quan_sat", "Diện tích không có ảnh sạch mây trong kỳ ghép", "Ảnh ban ngày",
      "Pixel bị che mây ở mọi cảnh", NUM, "ha"),
    v("tong_dien_tich_ha", "Diện tích tự nhiên của huyện", "GADM 4.1", "Tổng 5 lớp + không quan sát", NUM, "ha"),
    v("ty_le_nong_nghiep", "Tỷ lệ đất nông nghiệp trên diện tích tự nhiên", "Tính toán",
      "dt_nong_nghiep / tong_dien_tich_ha × 100", NUM, "%"),
    v("dt_nn_chuyen_doi", "Diện tích đất nông nghiệp chuyển sang mục đích khác so với năm trước", "Tính toán",
      "Σ diện tích pixel là nông nghiệp năm t−1 và thuộc lớp khác năm t (cùng nguồn ảnh)", NUM, "ha"),
    v("thang", "Tháng (chỉ có trong bảng theo tháng)", "", "Ảnh trung vị các cảnh trong tháng", INT, "Tháng"),
    v("ty_le_quan_sat", "Tỷ lệ diện tích huyện có ảnh sạch mây trong tháng (bảng tháng)", "Tính toán",
      "(tong_dien_tich_ha − dt_khong_quan_sat) / tong_dien_tich_ha × 100", NUM, "%"),
    v("ndvi_tb", "NDVI trung bình trên phần có ảnh (bảng tháng)", "Ảnh ban ngày", "(NIR−RED)/(NIR+RED)", NUM, ""),
    v("mndwi_tb", "MNDWI trung bình (bảng tháng)", "Ảnh ban ngày", "(GREEN−SWIR1)/(GREEN+SWIR1)", NUM, ""),
    v("ndbi_tb", "NDBI trung bình (bảng tháng)", "Ảnh ban ngày", "(SWIR1−NIR)/(SWIR1+NIR)", NUM, ""),
    v("so_canh_anh", "Số cảnh ảnh dùng ghép ảnh (năm hoặc tháng)", "", "", INT, "cảnh"),
    v("ky_ghep_anh", "Khoảng thời gian ghép ảnh (mùa khô)", "", "01/11 năm trước → 30/04 năm hiện tại", STR, ""),
    v("ghi_chu", "Ghi chú xử lý", "", "", STR, ""),
]

CLASS_RULES = [
    ("4 Mặt nước", f"MNDWI > {LANDCOVER_THRESHOLDS['water_mndwi_min']} và NDVI < {LANDCOVER_THRESHOLDS['water_ndvi_max']}"),
    ("2 Đô thị và dịch vụ", f"NDBI > {LANDCOVER_THRESHOLDS['urban_ndbi_min']} và NDVI < {LANDCOVER_THRESHOLDS['urban_ndvi_max']}"),
    ("3 Rừng", f"NDVI ≥ {LANDCOVER_THRESHOLDS['forest_ndvi_min']}, hoặc NDVI ≥ "
               f"{LANDCOVER_THRESHOLDS['forest_slope_ndvi_min']} trên đất dốc ≥ {LANDCOVER_THRESHOLDS['forest_slope_deg']}°"),
    ("1 Đất nông nghiệp", f"NDVI ≥ {LANDCOVER_THRESHOLDS['agri_ndvi_min']} và độ dốc < "
                          f"{LANDCOVER_THRESHOLDS['agri_slope_max_deg']}°"),
    ("5 Đất khác", "Các pixel còn lại"),
]


def _write(meta_dir, stem, title, df, extra_md):
    meta_dir.mkdir(parents=True, exist_ok=True)
    with open(meta_dir / f"{stem}.md", "w", encoding="utf-8") as f:
        f.write(f"# CODEBOOK: {title}\n\n")
        f.write("**Đơn vị:** cấp huyện (~705 quận/huyện/thị xã, địa giới trước sáp nhập)  \n")
        f.write("**Khóa chính:** ma_huyen + nam  \n**Chuỗi thời gian:** 2004–2025  \n\n")
        f.write(df_to_markdown(df) + "\n\n" + extra_md)
    df.to_excel(meta_dir / f"{stem}.xlsx", index=False, engine="openpyxl")


def generate_codebooks(base_dir):
    base_dir = Path(base_dir)
    _write(base_dir / NTL_PACKAGE / "metadata", "codebook_ntl", "KINH TẾ ĐÊM CẤP HUYỆN",
           pd.DataFrame(NTL_CODEBOOK_DATA),
           "## Tệp dữ liệu\n\n"
           "- `data_processed/vietnam_district_ntl_panel_2004_2025.{csv,xlsx,dta}`: bảng năm\n"
           "- `data_processed/vietnam_district_ntl_viirs_monthly.{csv,xlsx,dta}`: bảng VIIRS theo tháng (từ 04/2012; "
           "DMSP-OLS chỉ có ảnh năm)\n"
           "- `raw_data/NTL/DMSP/DMSP_<ma_huyen>_<nam>.tif`, `raw_data/NTL/VIIRS/VIIRS_<ma_huyen>_<nam>[_<thang>].tif`: ảnh gốc\n"
           "- `data_intermediate/NTL_<ma_huyen>_<nam>.tif`: ảnh đã lọc nhiễu, quy về thang VIIRS\n\n"
           "## Lọc nhiễu và hiệu chỉnh\n\n"
           "- Mây: VIIRS tháng lấy trung bình có trọng số theo cf_cvg; DMSP dùng stable_lights.\n"
           "- Ánh sáng nền: VIIRS < 0.5 nW/cm²/sr và DMSP DN ≤ 6 đặt về 0.\n"
           "- Cháy rừng: loại pixel có điểm cháy FIRMS trong kỳ (đệm 1 km).\n"
           "- Tàu thuyền, đốt khí ngoài khơi: loại bằng ranh giới đất liền của huyện; bản năm EOG đã che ngoại lai.\n"
           "- Hiệu chỉnh liên kết: ln(VIIRS) = a + b·ln(DN) ước lượng trên năm chồng lấn 2013 "
           "(hệ số tại docs/hieu_chinh_dmsp_viirs.json).\n\n"
           "*Trích dẫn nguồn: NOAA/NCEI và Earth Observation Group (Colorado School of Mines), qua Google Earth Engine.*\n")
    rules = pd.DataFrame(CLASS_RULES, columns=["Lớp (theo thứ tự ưu tiên)", "Luật ngưỡng"])
    _write(base_dir / LANDCOVER_PACKAGE / "metadata", "codebook_landcover", "LỚP PHỦ BỀ MẶT CẤP HUYỆN",
           pd.DataFrame(LANDCOVER_CODEBOOK_DATA),
           "## Phân lớp (không dùng machine learning)\n\n"
           "NDVI = (NIR−RED)/(NIR+RED); MNDWI = (GREEN−SWIR1)/(GREEN+SWIR1); NDBI = (SWIR1−NIR)/(SWIR1+NIR); "
           "độ dốc từ SRTM 30 m.\n\n" + df_to_markdown(rules) + "\n\n"
           "Ngưỡng hiện hành:\n\n```json\n" + json.dumps(LANDCOVER_THRESHOLDS, indent=2) + "\n```\n\n"
           "## Tệp dữ liệu\n\n"
           "- `data_processed/vietnam_district_landcover_panel_2004_2025.{csv,xlsx,dta}`: bảng năm (ảnh mùa khô)\n"
           "- `data_processed/vietnam_district_landcover_monthly.{csv,xlsx,dta}`: bảng 12 tháng; tháng mùa mưa thường "
           "bị mây che, cần đọc kèm `ty_le_quan_sat` (dt_nn_chuyen_doi chỉ tính theo năm)\n"
           "- Ảnh tháng: `..._<ma_huyen>_<nam>_<thang>.tif` trong cùng các thư mục dưới đây\n"
           "- `raw_data/DAY/LANDSAT/LANDSAT_<ma_huyen>_<nam>.tif`, `raw_data/DAY/SENTINEL2/SENTINEL2_<ma_huyen>_<nam>.tif`: "
           "ảnh tổng hợp mùa khô đã che mây, 6 kênh BLUE, GREEN, RED, NIR, SWIR1, SWIR2 (phản xạ × 10000, int16)\n"
           "- `data_intermediate/LC_<LANDSAT|SENTINEL2>_<ma_huyen>_<nam>.tif`: bản đồ phân lớp (0 = không quan sát, 1–5)\n\n"
           "*Trích dẫn nguồn: Landsat Collection 2 (USGS), Sentinel-2 (ESA Copernicus), SRTM (NASA), qua Google Earth Engine.*\n")
    print("[*] Đã sinh Codebook (MD & XLSX) cho 2 gói dữ liệu.")
