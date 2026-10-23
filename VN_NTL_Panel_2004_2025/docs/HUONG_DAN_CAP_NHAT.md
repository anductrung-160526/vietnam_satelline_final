# HƯỚNG DẪN CẬP NHẬT DỮ LIỆU KINH TẾ ĐÊM CHO CÁC NĂM TIẾP THEO

Tài liệu này quy định quy trình chuẩn để bổ sung dữ liệu ảnh vệ tinh ánh sáng ban đêm cho các năm tiếp theo (từ năm 2026 trở đi) nhằm bảo đảm tính nhất quán kiến trúc và tính liên tục của chuỗi thời gian.

---

## 1. NGUYÊN TẮC BẮT BUỘC
1. **Nhất quán kiến trúc:**
   - Giữ nguyên cấu trúc cây thư mục gốc.
   - Giữ nguyên quy cách đặt tên file GeoTIFF: `<ma_huyen>_ntl_<nam>.tif`.
   - Giữ nguyên danh sách tên cột, thứ tự và định dạng kiểu dữ liệu trong bảng `data_processed/`.
2. **Nguồn dữ liệu cập nhật:**
   - Tiếp tục sử dụng ảnh vệ tinh SNPP-VIIRS DNB hoặc NOAA-20 VIIRS DNB (bộ sản phẩm VCMSLCFG hoặc v22).
3. **Nhật ký cập nhật (`logs/`):**
   - Mọi lượt cập nhật dữ liệu phải ghi vào file log với cú pháp:
     `[YYYY-MM-DD HH:MM:SS] | Người thực hiện | SNPP-VIIRS | Nội dung cập nhật chi tiết...`

---

## 2. QUY TRÌNH THỰC HIỆN 4 BƯỚC

### Bước 1: Kiểm tra tính sẵn sàng của dữ liệu vệ tinh
Vào đầu quý 1 năm sau (khi NOAA công bố đủ dữ liệu tổng hợp năm cũ):
Kiểm tra trên Google Earth Engine bộ sưu tập `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG` cho năm cần cập nhật.

### Bước 2: Chạy script cập nhật
Chạy lệnh trích xuất với tham số năm bổ sung:
```bash
python code/ntl_pipeline.py --years 2026
```

### Bước 3: Nối tiếp bảng số liệu (Data Append)
Script sẽ tự động:
1. Tính Zonal Statistics cho ~705 huyện của năm mới.
2. Tính toán tốc độ tăng trưởng `thay_doi_ntl` so với năm liền kề trước đó.
3. Nối các dòng mới vào các file bảng hiện có:
   - `data_processed/vietnam_district_ntl_panel_2004_2025.csv`
   - `data_processed/vietnam_district_ntl_panel_2004_2025.xlsx`
   - `data_processed/vietnam_district_ntl_panel_2004_2025.dta`

### Bước 4: Kiểm tra và ghi log
Mở file `logs/ntl_pipeline_<timestamp>.log` để xác nhận tất cả các huyện đều đạt trạng thái thành công và không phát sinh lỗi ngoại lệ.
