# HƯỚNG DẪN CẬP NHẬT DỮ LIỆU LỚP PHỦ BỀ MẶT CHO CÁC NĂM TIẾP THEO

Tài liệu này quy định quy trình chuẩn để cập nhật định kỳ bản đồ và chỉ số diện tích lớp phủ bề mặt cấp huyện cho các năm tiếp theo (từ 2026 trở đi).

---

## 1. NGUYÊN TẮC CẬP NHẬT
1. **Tính nhất quán phân loại:**
   - Sử dụng thống nhất 5 lớp phủ chuẩn: Đất nông nghiệp, Đô thị/dịch vụ, Rừng, Mặt nước, Đất khác.
   - Giữ nguyên cấu trúc bảng dữ liệu, tên biến và đơn vị tính (hecta, %).
2. **Nguồn ảnh:**
   - Tiếp tục khai thác dữ liệu ảnh Landsat 8/9 kết hợp Sentinel-2 từ kho lưu trữ Google Earth Engine.
   - Ưu tiên cửa sổ quan sát mùa khô (tháng 11 năm trước đến tháng 4 năm hiện tại) để giảm thiểu tỷ lệ che phủ mây.
3. **Quy chuẩn nhật ký (`logs/`):**
   - Mọi hoạt động cập nhật phải ghi vào file log:
     `[YYYY-MM-DD HH:MM:SS] | Người thực hiện | Landsat/Sentinel-2 | Nội dung chi tiết...`

---

## 2. QUY TRÌNH THỰC HIỆN 4 BƯỚC

### Bước 1: Kiểm tra ảnh viễn thám
Sau khi kết thúc mùa khô hàng năm (khoảng tháng 5), kiểm tra bộ sưu tập Landsat 9 và Sentinel-2 đã cập nhật đầy đủ ảnh Surface Reflectance trên GEE.

### Bước 2: Chạy script phân loại và trích xuất diện tích
Chạy lệnh cho năm mới:
```bash
python code/landcover_pipeline.py --years 2026
```

### Bước 3: Đánh giá độ chính xác phân loại
Chạy kiểm định độ chính xác trên tập mẫu kiểm chứng:
```bash
python code/accuracy_assessment.py
```
Kiểm tra báo cáo tại `docs/BAO_CAO_DO_CHINH_XAC.md`, đảm bảo Overall Accuracy $\ge 85\%$ và Kappa $\ge 0.80$.

### Bước 4: Kiểm tra và xuất bảng số liệu
Xác nhận dữ liệu năm mới đã được nối vào các bảng kết quả:
- `data_processed/vietnam_district_landcover_panel_2004_2025.csv`
- `data_processed/vietnam_district_landcover_panel_2004_2025.xlsx`
- `data_processed/vietnam_district_landcover_panel_2004_2025.dta`
Kiểm tra biến `dt_nn_chuyen_doi` để xác định biến động đất nông nghiệp của từng huyện so với năm trước.
