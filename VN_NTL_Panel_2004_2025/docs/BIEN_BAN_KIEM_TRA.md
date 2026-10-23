# BIÊN BẢN KIỂM TRA CHẤT LƯỢNG VÀ TÍNH TOÀN VẸN DỮ LIỆU KINH TẾ ĐÊM (NTL)

**Gói dữ liệu:** VN_NTL_Panel_2004_2025  
**Cấp hành chính:** Cấp huyện (~705 quận/huyện/thị xã)  
**Thời gian kiểm tra:** Định kỳ theo từng chu kỳ xử lý dữ liệu  

---

## 1. TIÊU CHÍ ĐÁNH GIÁ CHẤT LƯỢNG

| STT | Tiêu chí kiểm tra | Chuẩn chấp nhận | Phương pháp kiểm tra | Trạng thái |
|:---:|---|---|---|:---:|
| 1 | **Tính đầy đủ của đơn vị hành chính** | Đủ 100% các huyện theo GADM 4.1 Level 2 (705 đơn vị) | Đếm số lượng `ma_huyen` duy nhất trong bảng | **ĐẠT** |
| 2 | **Tính toàn vẹn chuỗi thời gian** | Đủ 22 năm liên tục (2004 đến 2025), tổng số bản ghi = 705 × 22 = 15.510 dòng | Kiểm tra `count(ma_huyen, nam)` | **ĐẠT** |
| 3 | **Giá trị khuyết thiếu (Missing values / NaN)** | 0% giá trị NaN trong các cột khóa và chỉ số chính | Hàm `df.isna().sum()` | **ĐẠT** |
| 4 | **Tính liên tục khi chuyển đổi cảm biến (2012–2013)** | Không có bước nhảy đột ngột bất thường giữa DMSP và VIIRS tại năm giao thoa 2013 | Phân tích hồi quy tương quan và kiểm định phân phối | **ĐẠT** |
| 5 | **Độ hợp lý của chỉ số mật độ (`mat_do_ntl`)** | Mật độ các quận trung tâm đô thị (Hà Nội, TP.HCM, Đà Nẵng) phải cao hơn rõ rệt so với các huyện miền núi | Phân tích Boxplot và xếp hạng phân vị | **ĐẠT** |

---

## 2. KẾT QUẢ ĐỐI SOÁT CHI TIẾT
- **Khóa chính duy nhất:** Cặp `(ma_huyen, nam)` không tồn tại bản ghi trùng lặp nào.
- **Tính tương thích định dạng:**
  - Tệp `.csv` nạp trơn tru trong Python và R (mã hóa UTF-8 with BOM hiển thị đúng tiếng Việt).
  - Tệp `.xlsx` mở bình thường trong Microsoft Excel, không vượt giới hạn dòng/cột.
  - Tệp `.dta` mở thành công trong Stata 16/17/18, các biến chuỗi không bị lỗi ký tự Unicode hoặc lỗi biến strL.
