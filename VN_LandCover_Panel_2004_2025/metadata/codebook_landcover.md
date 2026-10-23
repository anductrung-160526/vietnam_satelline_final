# CODEBOOK / DATA DICTIONARY: BỘ DỮ LIỆU LỚP PHỦ BỀ MẶT CẤP HUYỆN (2004–2025)

**Gói dữ liệu:** VN_LandCover_Panel_2004_2025  
**Phạm vi không gian:** Cấp huyện Việt Nam (~705 quận/huyện/thị xã)  
**Chuỗi thời gian:** 2004 đến 2025 (22 năm Panel data)  

| Tên biến | Nhãn / Mô tả | Nguồn dữ liệu | Công thức / Thuật toán | Kiểu dữ liệu | Đơn vị đo |
| --- | --- | --- | --- | --- | --- |
| ma_tinh | Mã định danh tỉnh, thành phố trực thuộc Trung ương | GADM 4.1 Level 1 | Trích xuất từ ranh giới hành chính | String (Chuỗi) | Mã chuẩn |
| ten_tinh | Tên tỉnh, thành phố | GADM 4.1 Level 1 | Trích xuất từ ranh giới hành chính | String (Chuỗi) | Danh từ riêng |
| ma_huyen | Mã định danh cấp huyện | GADM 4.1 Level 2 | Khóa định danh cấp huyện kết hợp với 'nam' thành Khóa chính | String (Chuỗi) | Mã chuẩn |
| ten_huyen | Tên đơn vị cấp huyện | GADM 4.1 Level 2 | Trích xuất từ ranh giới hành chính | String (Chuỗi) | Danh từ riêng |
| nam | Năm quan sát chuỗi thời gian (2004 đến 2025) | Chuỗi thời gian bảng (Panel data) | Năm tổng hợp ảnh viễn thám | Numeric (Số nguyên) | Năm |
| nguon_anh | Loại vệ tinh thu nhận ảnh ban ngày | USGS / Copernicus qua Google Earth Engine | 'Landsat-5/7/8/9' (30m) hoặc 'Sentinel-2' (10m) | String (Chuỗi) | Tên vệ tinh |
| dt_nong_nghiep | Diện tích đất nông nghiệp (Lớp 1: đất trồng lúa, cây hoa màu, cây hàng năm và lâu năm) | Mô hình Machine Learning (Random Forest) phân loại ảnh đa phổ | Tổng diện tích pixel phân loại lớp 1 (ha = m² / 10.000) | Numeric (Số thực) | ha (Hécta) |
| dt_do_thi | Diện tích đất đô thị và dịch vụ (Lớp 2: khu dân cư, công trình xây dựng, khu công nghiệp) | Mô hình Machine Learning (Random Forest) | Tổng diện tích pixel phân loại lớp 2 | Numeric (Số thực) | ha (Hécta) |
| dt_rung | Diện tích rừng (Lớp 3: rừng tự nhiên, rừng phòng hộ, rừng trồng cây gỗ) | Mô hình Machine Learning (Random Forest) | Tổng diện tích pixel phân loại lớp 3 | Numeric (Số thực) | ha (Hécta) |
| dt_mat_nuoc | Diện tích mặt nước (Lớp 4: sông ngòi, kênh rạch, hồ chứa, đầm phá, mặt nước nuôi trồng) | Mô hình Machine Learning (Random Forest) | Tổng diện tích pixel phân loại lớp 4 | Numeric (Số thực) | ha (Hécta) |
| dt_khac | Diện tích đất khác (Lớp 5: đất trống, bãi cát, đồi núi trọc, đất ngập mặn khác) | Mô hình Machine Learning (Random Forest) | Tổng diện tích pixel phân loại lớp 5 | Numeric (Số thực) | ha (Hécta) |
| ty_le_nong_nghiep | Tỷ lệ đất nông nghiệp trên tổng diện tích tự nhiên của huyện | Tính toán từ diện tích các lớp phủ | (dt_nong_nghiep / tong_dien_tich_ha) * 100 | Numeric (Số thực) | % (Phần trăm) |
| dt_nn_chuyen_doi | Diện tích đất nông nghiệp bị chuyển sang mục đích khác so với năm liền kề trước đó | So sánh chuỗi không gian theo thời gian | max(0, dt_nong_nghiep_{t-1} - dt_nong_nghiep_t) | Numeric (Số thực) | ha (Hécta) |
| tong_dien_tich_ha | Tổng diện tích đất của toàn bộ đơn vị cấp huyện | Tổng diện tích 5 lớp phủ phân loại | dt_nong_nghiep + dt_do_thi + dt_rung + dt_mat_nuoc + dt_khac | Numeric (Số thực) | ha (Hécta) |

---
*Ghi chú trích dẫn: Dữ liệu ảnh Landsat (USGS) và Sentinel-2 (Copernicus) được phân loại bằng mô hình học máy Random Forest 5 lớp phủ trên Google Earth Engine.*