# GÓI DỮ LIỆU: BẢNG CHUỖI THỜI GIAN LỚP PHỦ BỀ MẶT CẤP HUYỆN VIỆT NAM (2004–2025)
**Mã gói:** `VN_LandCover_Panel_2004_2025`

---

## 1. MÔ TẢ TỔNG QUAN
Gói dữ liệu cung cấp chuỗi thời gian dạng bảng (Panel Data) và bản đồ phân loại viễn thám về hiện trạng lớp phủ bề mặt (Land Cover) cho toàn bộ các đơn vị hành chính **cấp huyện** tại Việt Nam (~705 quận, huyện, thị xã, thành phố thuộc tỉnh) giai đoạn **2004 đến 2025** (22 năm).

Dữ liệu tập trung vào theo dõi động thái sử dụng đất, đặc biệt là **diện tích đất nông nghiệp** và **diện tích đất nông nghiệp bị chuyển sang mục đích khác** (đô thị hóa, xây dựng, công nghiệp) theo từng địa phương.

---

## 2. NGUỒN DỮ LIỆU VÀ PHƯƠNG PHÁP XỬ LÝ
1. **Dữ liệu viễn thám:**
   - Landsat 5 TM (2004–2011), Landsat 7 ETM+ (2012), Landsat 8 OLI (2013–2021), Landsat 9 OLI-2 (2022–2025) độ phân giải 30m.
   - Bổ sung Sentinel-2 MSI (từ 2015) độ phân giải 10m.
   - Ưu tiên cửa sổ thời gian mùa khô ít mây, áp dụng thuật toán lọc mây `QA_PIXEL`.
2. **Mô hình học máy phân loại 5 lớp phủ:**
   - Thuật toán: Random Forest (50 cây quyết định trên Google Earth Engine).
   - 5 lớp phủ chuẩn:
     1. `dt_nong_nghiep`: Đất nông nghiệp
     2. `dt_do_thi`: Đất đô thị và dịch vụ, công nghiệp, xây dựng
     3. `dt_rung`: Đất lâm nghiệp, rừng tự nhiên và rừng trồng
     4. `dt_mat_nuoc`: Sông, hồ, đầm phá, mặt nước
     5. `dt_khac`: Đất trống, đồi núi trọc, bãi cát
   - Đánh giá chất lượng phân loại qua ma trận nhầm lẫn dựa trên tập mẫu kiểm chứng mặt đất (`samples/`).

---

## 3. CẤU TRÚC THƯ MỤC
```
VN_LandCover_Panel_2004_2025/
├── README.md                  # Hướng dẫn tổng quan bộ dữ liệu lớp phủ
├── raw_data/
│   └── DAY/
│       ├── LANDSAT/           # Ảnh tổng hợp năm .tif (2004–2025)
│       └── SENTINEL2/         # Ảnh tổng hợp năm .tif (2015–2025)
├── data_intermediate/         # Bản đồ phân loại lớp phủ bề mặt 5 lớp (.tif)
├── data_processed/            # Bảng diện tích và chuyển đổi đất (.csv, .xlsx, .dta)
├── metadata/
│   ├── codebook_landcover.md  # Từ điển dữ liệu chi tiết dạng Markdown
│   └── codebook_landcover.xlsx# Từ điển dữ liệu chi tiết dạng Excel
├── samples/                   # Bộ điểm mẫu kiểm chứng mặt đất (GeoJSON, CSV)
├── code/
│   ├── landcover_pipeline.py  # Mã nguồn Python xử lý và trích xuất diện tích
│   └── accuracy_assessment.py # Mã nguồn đánh giá độ chính xác phân loại
├── docs/
│   ├── HUONG_DAN_CAP_NHAT.md  # Quy trình bổ sung dữ liệu các năm tiếp theo
│   └── BAO_CAO_DO_CHINH_XAC.md# Báo cáo Confusion Matrix và hệ số Kappa
└── logs/                      # Nhật ký tải và xử lý dữ liệu
```

---

## 4. BẢNG BIẾN CHÍNH TRONG `data_processed/`
- Khóa chính kết hợp: `ma_huyen` + `nam`
- `dt_nong_nghiep`, `dt_do_thi`, `dt_rung`, `dt_mat_nuoc`, `dt_khac`: Diện tích từng lớp (ha).
- `ty_le_nong_nghiep`: Tỷ lệ đất nông nghiệp trên tổng diện tích tự nhiên của huyện (%).
- `dt_nn_chuyen_doi`: Diện tích đất nông nghiệp bị chuyển sang mục đích khác so với năm liền kề trước đó (ha).
