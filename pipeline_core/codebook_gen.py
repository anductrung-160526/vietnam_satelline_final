# -*- coding: utf-8 -*-
"""
Trình tạo Codebook/Data Dictionary tự động dưới dạng Markdown và Excel (.xlsx)
cho cả 2 gói dữ liệu VN_NTL_Panel_2004_2025 và VN_LandCover_Panel_2004_2025.
"""
import sys
from pathlib import Path
import pandas as pd
from pipeline_core.utils import df_to_markdown

if sys.platform == "win32":

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

NTL_CODEBOOK_DATA = [
    {
        "Tên biến": "ma_tinh",
        "Nhãn / Mô tả": "Mã định danh tỉnh, thành phố trực thuộc Trung ương theo chuẩn phân cấp hành chính (trước sáp nhập)",
        "Nguồn dữ liệu": "GADM 4.1 Level 1 / Tổng cục Thống kê",
        "Công thức / Thuật toán": "Trích xuất từ thuộc tính ranh giới hành chính",
        "Kiểu dữ liệu": "String (Chuỗi)",
        "Đơn vị đo": "Mã chuẩn"
    },
    {
        "Tên biến": "ten_tinh",
        "Nhãn / Mô tả": "Tên đầy đủ của tỉnh, thành phố",
        "Nguồn dữ liệu": "GADM 4.1 Level 1",
        "Công thức / Thuật toán": "Trích xuất từ thuộc tính ranh giới hành chính",
        "Kiểu dữ liệu": "String (Chuỗi)",
        "Đơn vị đo": "Danh từ riêng"
    },
    {
        "Tên biến": "ma_huyen",
        "Nhãn / Mô tả": "Mã định danh duy nhất của đơn vị hành chính cấp huyện (quận, huyện, thị xã, thành phố thuộc tỉnh)",
        "Nguồn dữ liệu": "GADM 4.1 Level 2",
        "Công thức / Thuật toán": "Khóa định danh cấp huyện kết hợp với 'nam' thành Khóa chính (Primary Key)",
        "Kiểu dữ liệu": "String (Chuỗi)",
        "Đơn vị đo": "Mã chuẩn"
    },
    {
        "Tên biến": "ten_huyen",
        "Nhãn / Mô tả": "Tên đơn vị hành chính cấp huyện kèm loại hình đơn vị",
        "Nguồn dữ liệu": "GADM 4.1 Level 2",
        "Công thức / Thuật toán": "Trích xuất từ thuộc tính ranh giới hành chính",
        "Kiểu dữ liệu": "String (Chuỗi)",
        "Đơn vị đo": "Danh từ riêng"
    },
    {
        "Tên biến": "nam",
        "Nhãn / Mô tả": "Năm quan sát thống kê (giai đoạn 2004 đến 2025)",
        "Nguồn dữ liệu": "Chuỗi thời gian bảng (Panel data)",
        "Công thức / Thuật toán": "Năm tổng hợp ảnh viễn thám",
        "Kiểu dữ liệu": "Numeric (Số nguyên)",
        "Đơn vị đo": "Năm"
    },
    {
        "Tên biến": "nguon_anh",
        "Nhãn / Mô tả": "Loại vệ tinh và cảm biến thu nhận ảnh",
        "Nguồn dữ liệu": "NOAA/NCEI và Earth Observation Group",
        "Công thức / Thuật toán": "'DMSP-OLS' (2004–2013) hoặc 'SNPP-VIIRS' (2013–2025)",
        "Kiểu dữ liệu": "String (Chuỗi)",
        "Đơn vị đo": "Tên cảm biến"
    },
    {
        "Tên biến": "sol_ntl",
        "Nhãn / Mô tả": "Quy mô kinh tế đêm: Tổng lượng ánh sáng tích lũy (Sum of Light)",
        "Nguồn dữ liệu": "Ảnh vệ tinh ban đêm đã lọc nhiễu và hiệu chỉnh liên chuẩn (Harmonized)",
        "Công thức / Thuật toán": "Tổng giá trị bức xạ của tất cả pixel nằm trong ranh giới huyện (reduceRegion sum)",
        "Kiểu dữ liệu": "Numeric (Số thực)",
        "Đơn vị đo": "nW/cm²/sr (đã quy chuẩn tương đương)"
    },
    {
        "Tên biến": "mat_do_ntl",
        "Nhãn / Mô tả": "Mật độ kinh tế đêm trên một đơn vị diện tích",
        "Nguồn dữ liệu": "Tính toán từ sol_ntl và diện tích tự nhiên của huyện",
        "Công thức / Thuật toán": "sol_ntl / dien_tich_huyen_km2",
        "Kiểu dữ liệu": "Numeric (Số thực)",
        "Đơn vị đo": "nW/cm²/sr/km²"
    },
    {
        "Tên biến": "thay_doi_ntl",
        "Nhãn / Mô tả": "Tốc độ thay đổi quy mô kinh tế đêm so với năm liền kề trước đó",
        "Nguồn dữ liệu": "Tính toán từ chuỗi sol_ntl theo thời gian",
        "Công thức / Thuật toán": "[(sol_ntl_t - sol_ntl_{t-1}) / sol_ntl_{t-1}] * 100",
        "Kiểu dữ liệu": "Numeric (Số thực)",
        "Đơn vị đo": "% (Phần trăm)"
    },
    {
        "Tên biến": "dien_tich_huyen_km2",
        "Nhãn / Mô tả": "Diện tích tự nhiên của đơn vị hành chính cấp huyện",
        "Nguồn dữ liệu": "Tính toán từ vector ranh giới GADM Level 2",
        "Công thức / Thuật toán": "geometry.area() / 1,000,000",
        "Kiểu dữ liệu": "Numeric (Số thực)",
        "Đơn vị đo": "km²"
    }
]

LANDCOVER_CODEBOOK_DATA = [
    {
        "Tên biến": "ma_tinh",
        "Nhãn / Mô tả": "Mã định danh tỉnh, thành phố trực thuộc Trung ương",
        "Nguồn dữ liệu": "GADM 4.1 Level 1",
        "Công thức / Thuật toán": "Trích xuất từ ranh giới hành chính",
        "Kiểu dữ liệu": "String (Chuỗi)",
        "Đơn vị đo": "Mã chuẩn"
    },
    {
        "Tên biến": "ten_tinh",
        "Nhãn / Mô tả": "Tên tỉnh, thành phố",
        "Nguồn dữ liệu": "GADM 4.1 Level 1",
        "Công thức / Thuật toán": "Trích xuất từ ranh giới hành chính",
        "Kiểu dữ liệu": "String (Chuỗi)",
        "Đơn vị đo": "Danh từ riêng"
    },
    {
        "Tên biến": "ma_huyen",
        "Nhãn / Mô tả": "Mã định danh cấp huyện",
        "Nguồn dữ liệu": "GADM 4.1 Level 2",
        "Công thức / Thuật toán": "Khóa định danh cấp huyện kết hợp với 'nam' thành Khóa chính",
        "Kiểu dữ liệu": "String (Chuỗi)",
        "Đơn vị đo": "Mã chuẩn"
    },
    {
        "Tên biến": "ten_huyen",
        "Nhãn / Mô tả": "Tên đơn vị cấp huyện",
        "Nguồn dữ liệu": "GADM 4.1 Level 2",
        "Công thức / Thuật toán": "Trích xuất từ ranh giới hành chính",
        "Kiểu dữ liệu": "String (Chuỗi)",
        "Đơn vị đo": "Danh từ riêng"
    },
    {
        "Tên biến": "nam",
        "Nhãn / Mô tả": "Năm quan sát chuỗi thời gian (2004 đến 2025)",
        "Nguồn dữ liệu": "Chuỗi thời gian bảng (Panel data)",
        "Công thức / Thuật toán": "Năm tổng hợp ảnh viễn thám",
        "Kiểu dữ liệu": "Numeric (Số nguyên)",
        "Đơn vị đo": "Năm"
    },
    {
        "Tên biến": "nguon_anh",
        "Nhãn / Mô tả": "Loại vệ tinh thu nhận ảnh ban ngày",
        "Nguồn dữ liệu": "USGS / Copernicus qua Google Earth Engine",
        "Công thức / Thuật toán": "'Landsat-5/7/8/9' (30m) hoặc 'Sentinel-2' (10m)",
        "Kiểu dữ liệu": "String (Chuỗi)",
        "Đơn vị đo": "Tên vệ tinh"
    },
    {
        "Tên biến": "dt_nong_nghiep",
        "Nhãn / Mô tả": "Diện tích đất nông nghiệp (Lớp 1: đất trồng lúa, cây hoa màu, cây hàng năm và lâu năm)",
        "Nguồn dữ liệu": "Mô hình Machine Learning (Random Forest) phân loại ảnh đa phổ",
        "Công thức / Thuật toán": "Tổng diện tích pixel phân loại lớp 1 (ha = m² / 10.000)",
        "Kiểu dữ liệu": "Numeric (Số thực)",
        "Đơn vị đo": "ha (Hécta)"
    },
    {
        "Tên biến": "dt_do_thi",
        "Nhãn / Mô tả": "Diện tích đất đô thị và dịch vụ (Lớp 2: khu dân cư, công trình xây dựng, khu công nghiệp)",
        "Nguồn dữ liệu": "Mô hình Machine Learning (Random Forest)",
        "Công thức / Thuật toán": "Tổng diện tích pixel phân loại lớp 2",
        "Kiểu dữ liệu": "Numeric (Số thực)",
        "Đơn vị đo": "ha (Hécta)"
    },
    {
        "Tên biến": "dt_rung",
        "Nhãn / Mô tả": "Diện tích rừng (Lớp 3: rừng tự nhiên, rừng phòng hộ, rừng trồng cây gỗ)",
        "Nguồn dữ liệu": "Mô hình Machine Learning (Random Forest)",
        "Công thức / Thuật toán": "Tổng diện tích pixel phân loại lớp 3",
        "Kiểu dữ liệu": "Numeric (Số thực)",
        "Đơn vị đo": "ha (Hécta)"
    },
    {
        "Tên biến": "dt_mat_nuoc",
        "Nhãn / Mô tả": "Diện tích mặt nước (Lớp 4: sông ngòi, kênh rạch, hồ chứa, đầm phá, mặt nước nuôi trồng)",
        "Nguồn dữ liệu": "Mô hình Machine Learning (Random Forest)",
        "Công thức / Thuật toán": "Tổng diện tích pixel phân loại lớp 4",
        "Kiểu dữ liệu": "Numeric (Số thực)",
        "Đơn vị đo": "ha (Hécta)"
    },
    {
        "Tên biến": "dt_khac",
        "Nhãn / Mô tả": "Diện tích đất khác (Lớp 5: đất trống, bãi cát, đồi núi trọc, đất ngập mặn khác)",
        "Nguồn dữ liệu": "Mô hình Machine Learning (Random Forest)",
        "Công thức / Thuật toán": "Tổng diện tích pixel phân loại lớp 5",
        "Kiểu dữ liệu": "Numeric (Số thực)",
        "Đơn vị đo": "ha (Hécta)"
    },
    {
        "Tên biến": "ty_le_nong_nghiep",
        "Nhãn / Mô tả": "Tỷ lệ đất nông nghiệp trên tổng diện tích tự nhiên của huyện",
        "Nguồn dữ liệu": "Tính toán từ diện tích các lớp phủ",
        "Công thức / Thuật toán": "(dt_nong_nghiep / tong_dien_tich_ha) * 100",
        "Kiểu dữ liệu": "Numeric (Số thực)",
        "Đơn vị đo": "% (Phần trăm)"
    },
    {
        "Tên biến": "dt_nn_chuyen_doi",
        "Nhãn / Mô tả": "Diện tích đất nông nghiệp bị chuyển sang mục đích khác so với năm liền kề trước đó",
        "Nguồn dữ liệu": "So sánh chuỗi không gian theo thời gian",
        "Công thức / Thuật toán": "max(0, dt_nong_nghiep_{t-1} - dt_nong_nghiep_t)",
        "Kiểu dữ liệu": "Numeric (Số thực)",
        "Đơn vị đo": "ha (Hécta)"
    },
    {
        "Tên biến": "tong_dien_tich_ha",
        "Nhãn / Mô tả": "Tổng diện tích đất của toàn bộ đơn vị cấp huyện",
        "Nguồn dữ liệu": "Tổng diện tích 5 lớp phủ phân loại",
        "Công thức / Thuật toán": "dt_nong_nghiep + dt_do_thi + dt_rung + dt_mat_nuoc + dt_khac",
        "Kiểu dữ liệu": "Numeric (Số thực)",
        "Đơn vị đo": "ha (Hécta)"
    }
]

def generate_codebooks(base_dir):
    """
    Sinh tài liệu Codebook dạng Markdown và Excel (.xlsx) cho cả 2 gói dữ liệu
    """
    base_dir = Path(base_dir)

    # 1. Gói NTL
    ntl_dir = base_dir / "VN_NTL_Panel_2004_2025" / "metadata"
    ntl_dir.mkdir(parents=True, exist_ok=True)
    df_ntl = pd.DataFrame(NTL_CODEBOOK_DATA)


    # Xuất Markdown
    with open(ntl_dir / "codebook_ntl.md", "w", encoding="utf-8") as f:
        f.write("# CODEBOOK / DATA DICTIONARY: BỘ DỮ LIỆU KINH TẾ ĐÊM CẤP HUYỆN (2004–2025)\n\n")
        f.write(f"**Gói dữ liệu:** VN_NTL_Panel_2004_2025  \n")
        f.write(f"**Phạm vi không gian:** Cấp huyện Việt Nam (~705 quận/huyện/thị xã trước sáp nhập)  \n")
        f.write(f"**Chuỗi thời gian:** 2004 đến 2025 (22 năm Panel data)  \n\n")
        f.write(df_to_markdown(df_ntl, index=False))
        f.write("\n\n---\n*Ghi chú trích dẫn: Dữ liệu DMSP-OLS và SNPP-VIIRS được cung cấp bởi NOAA/NCEI và Earth Observation Group, truy xuất qua Google Earth Engine API.*")

    # Xuất Excel
    df_ntl.to_excel(ntl_dir / "codebook_ntl.xlsx", index=False, engine="openpyxl")

    # 2. Gói Land Cover
    lc_dir = base_dir / "VN_LandCover_Panel_2004_2025" / "metadata"
    lc_dir.mkdir(parents=True, exist_ok=True)
    df_lc = pd.DataFrame(LANDCOVER_CODEBOOK_DATA)

    # Xuất Markdown
    with open(lc_dir / "codebook_landcover.md", "w", encoding="utf-8") as f:
        f.write("# CODEBOOK / DATA DICTIONARY: BỘ DỮ LIỆU LỚP PHỦ BỀ MẶT CẤP HUYỆN (2004–2025)\n\n")
        f.write(f"**Gói dữ liệu:** VN_LandCover_Panel_2004_2025  \n")
        f.write(f"**Phạm vi không gian:** Cấp huyện Việt Nam (~705 quận/huyện/thị xã)  \n")
        f.write(f"**Chuỗi thời gian:** 2004 đến 2025 (22 năm Panel data)  \n\n")
        f.write(df_to_markdown(df_lc, index=False))
        f.write("\n\n---\n*Ghi chú trích dẫn: Dữ liệu ảnh Landsat (USGS) và Sentinel-2 (Copernicus) được phân loại bằng mô hình học máy Random Forest 5 lớp phủ trên Google Earth Engine.*")


    # Xuất Excel
    df_lc.to_excel(lc_dir / "codebook_landcover.xlsx", index=False, engine="openpyxl")

    print(f"[*] Đã sinh tài liệu Codebook (MD & XLSX) thành công cho cả 2 gói dữ liệu.")
