# GÓI DỮ LIỆU: BẢNG CHUỖI THỜI GIAN KINH TẾ ĐÊM CẤP HUYỆN VIỆT NAM (2004–2025)
**Mã gói:** `VN_NTL_Panel_2004_2025`

---

## 1. MÔ TẢ TỔNG QUAN
Gói dữ liệu cung cấp chuỗi thời gian dạng bảng (Panel Data) và ảnh vệ tinh viễn thám ánh sáng ban đêm (Nighttime Light - NTL) cho toàn bộ các đơn vị hành chính **cấp huyện** tại Việt Nam (~705 quận, huyện, thị xã, thành phố thuộc tỉnh trước sáp nhập) xuyên suốt giai đoạn 22 năm từ **2004 đến 2025**.

Dữ liệu được hiệu chuẩn liên chuẩn đồng nhất (Harmonized) giữa hai thế hệ cảm biến vệ tinh DMSP-OLS và SNPP-VIIRS, cho phép thực hiện các nghiên cứu kinh tế lượng, theo dõi tăng trưởng kinh tế, đô thị hóa và tiêu thụ năng lượng ở cấp địa phương.

---

## 2. NGUỒN DỮ LIỆU VÀ CẢM BIẾN
1. **DMSP-OLS (2004–2013):**
   - Nguồn: Cảm biến Operational Linescan System thuộc Chương trình Vệ tinh Khí tượng Quốc phòng Hoa Kỳ (DMSP), cung cấp bởi NOAA/NCEI và Earth Observation Group (EOG).
   - Sản phẩm: Ảnh tổng hợp hằng năm không mây (Version 4 DMSP-OLS Nighttime Lights).
   - Độ phân giải: 30 arc-seconds (~1 km).
2. **SNPP-VIIRS DNB (2013–2025):**
   - Nguồn: Cảm biến Day/Night Band trên vệ tinh Suomi NPP, cung cấp bởi NOAA/EOG.
   - Sản phẩm: Ảnh tổng hợp tháng và năm đã khử lạc sáng (Stray Light Corrected - VCMSLCFG).
   - Độ phân giải: 15 arc-seconds (~500 m).

---

## 3. CẤU TRÚC THƯ MỤC
```
VN_NTL_Panel_2004_2025/
├── README.md                  # Tài liệu hướng dẫn tổng quan bộ dữ liệu
├── raw_data/
│   └── NTL/
│       ├── DMSP/              # Ảnh GeoTIFF thô .tif giai đoạn 2004–2013
│       └── VIIRS/             # Ảnh GeoTIFF thô .tif giai đoạn 2013–2025
├── data_intermediate/         # Ảnh GeoTIFF sau khi lọc nhiễu, chuẩn hóa và cắt theo huyện
├── data_processed/            # Bảng chỉ số hoàn chỉnh (.csv, .xlsx, .dta) theo mã huyện và năm
├── metadata/
│   ├── codebook_ntl.md        # Từ điển dữ liệu chi tiết dạng Markdown
│   └── codebook_ntl.xlsx      # Từ điển dữ liệu chi tiết dạng Excel
├── code/
│   └── ntl_pipeline.py        # Mã nguồn Python xử lý và trích xuất chỉ số
├── docs/
│   ├── HUONG_DAN_CAP_NHAT.md  # Hướng dẫn bổ sung dữ liệu các năm tiếp theo
│   └── BIEN_BAN_KIEM_TRA.md   # Biên bản kiểm tra tính toàn vẹn và độ lệch số liệu
└── logs/                      # Nhật ký chi tiết tiến trình tải và lỗi phát sinh
```

---

## 4. BẢNG BIẾN CHÍNH TRONG `data_processed/`
- Khóa chính kết hợp: `ma_huyen` + `nam`
- `sol_ntl`: Quy mô kinh tế đêm (Sum of Light - Tổng bức xạ ánh sáng, nW/cm²/sr).
- `mat_do_ntl`: Mật độ kinh tế đêm (Bức xạ trung bình trên mỗi km² diện tích tự nhiên).
- `thay_doi_ntl`: Tốc độ tăng trưởng quy mô kinh tế đêm so với năm trước (%).

---

## 5. HƯỚNG DẪN MÔI TRƯỜNG CHẠY MÃ XỬ LÝ
- Python 3.10 trở lên.
- Cài đặt thư viện: `pip install -r requirements.txt`.
- Đăng nhập xác thực Google Earth Engine: `earthengine authenticate`.
- Chạy trích xuất dữ liệu:
  ```bash
  python code/ntl_pipeline.py
  ```
