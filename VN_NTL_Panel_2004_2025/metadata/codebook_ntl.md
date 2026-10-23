# CODEBOOK / DATA DICTIONARY: BỘ DỮ LIỆU KINH TẾ ĐÊM CẤP HUYỆN (2004–2025)

**Gói dữ liệu:** VN_NTL_Panel_2004_2025  
**Phạm vi không gian:** Cấp huyện Việt Nam (~705 quận/huyện/thị xã trước sáp nhập)  
**Chuỗi thời gian:** 2004 đến 2025 (22 năm Panel data)  

| Tên biến | Nhãn / Mô tả | Nguồn dữ liệu | Công thức / Thuật toán | Kiểu dữ liệu | Đơn vị đo |
| --- | --- | --- | --- | --- | --- |
| ma_tinh | Mã định danh tỉnh, thành phố trực thuộc Trung ương theo chuẩn phân cấp hành chính (trước sáp nhập) | GADM 4.1 Level 1 / Tổng cục Thống kê | Trích xuất từ thuộc tính ranh giới hành chính | String (Chuỗi) | Mã chuẩn |
| ten_tinh | Tên đầy đủ của tỉnh, thành phố | GADM 4.1 Level 1 | Trích xuất từ thuộc tính ranh giới hành chính | String (Chuỗi) | Danh từ riêng |
| ma_huyen | Mã định danh duy nhất của đơn vị hành chính cấp huyện (quận, huyện, thị xã, thành phố thuộc tỉnh) | GADM 4.1 Level 2 | Khóa định danh cấp huyện kết hợp với 'nam' thành Khóa chính (Primary Key) | String (Chuỗi) | Mã chuẩn |
| ten_huyen | Tên đơn vị hành chính cấp huyện kèm loại hình đơn vị | GADM 4.1 Level 2 | Trích xuất từ thuộc tính ranh giới hành chính | String (Chuỗi) | Danh từ riêng |
| nam | Năm quan sát thống kê (giai đoạn 2004 đến 2025) | Chuỗi thời gian bảng (Panel data) | Năm tổng hợp ảnh viễn thám | Numeric (Số nguyên) | Năm |
| nguon_anh | Loại vệ tinh và cảm biến thu nhận ảnh | NOAA/NCEI và Earth Observation Group | 'DMSP-OLS' (2004–2013) hoặc 'SNPP-VIIRS' (2013–2025) | String (Chuỗi) | Tên cảm biến |
| sol_ntl | Quy mô kinh tế đêm: Tổng lượng ánh sáng tích lũy (Sum of Light) | Ảnh vệ tinh ban đêm đã lọc nhiễu và hiệu chỉnh liên chuẩn (Harmonized) | Tổng giá trị bức xạ của tất cả pixel nằm trong ranh giới huyện (reduceRegion sum) | Numeric (Số thực) | nW/cm²/sr (đã quy chuẩn tương đương) |
| mat_do_ntl | Mật độ kinh tế đêm trên một đơn vị diện tích | Tính toán từ sol_ntl và diện tích tự nhiên của huyện | sol_ntl / dien_tich_huyen_km2 | Numeric (Số thực) | nW/cm²/sr/km² |
| thay_doi_ntl | Tốc độ thay đổi quy mô kinh tế đêm so với năm liền kề trước đó | Tính toán từ chuỗi sol_ntl theo thời gian | [(sol_ntl_t - sol_ntl_{t-1}) / sol_ntl_{t-1}] * 100 | Numeric (Số thực) | % (Phần trăm) |
| dien_tich_huyen_km2 | Diện tích tự nhiên của đơn vị hành chính cấp huyện | Tính toán từ vector ranh giới GADM Level 2 | geometry.area() / 1,000,000 | Numeric (Số thực) | km² |

---
*Ghi chú trích dẫn: Dữ liệu DMSP-OLS và SNPP-VIIRS được cung cấp bởi NOAA/NCEI và Earth Observation Group, truy xuất qua Google Earth Engine API.*