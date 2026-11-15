# Chỉ số kinh tế đêm — danh mục và phương pháp

Tài liệu này liệt kê các chỉ số kinh tế đêm của dự án: cái gì đã tính, cái gì còn thiếu,
công thức, đơn vị, và những ràng buộc phương pháp phải tôn trọng khi dùng.

Khoá chính mọi bảng: `ma_tinh + nam` (63 tỉnh trước sáp nhập 01/7/2025).

---

## 1. Nhóm A — đã tính xong, thuần từ ảnh vệ tinh

Nguồn: `task_pipeline/derive.py`, bảng `data_processed/ntl_annual.csv`.

### 1.1. Ba chỉ số kế hoạch quản lý dữ liệu bắt buộc

| Cột | Tên | Công thức | Đơn vị |
|---|---|---|---|
| `sol_ntl` | **Quy mô kinh tế đêm** | tổng giá trị mọi pixel hợp lệ trong tỉnh, sau khi trừ nền | nW/cm²/sr (VIIRS) · DN (DMSP) |
| `mat_do_ntl` | **Mật độ kinh tế đêm** | `sol_ntl ÷ dt_tu_nhien_km2` | đơn vị bức xạ trên km² |
| `thay_doi_ntl` | **Mức độ thay đổi** | `(sol_t − sol_{t−1}) ÷ sol_{t−1} × 100` | % |

`thay_doi_ntl` **chỉ so trong cùng một nguồn ảnh** và bỏ trống tại mốc đổi vệ tinh
2013→2014. Muốn so xuyên mốc thì dùng `thay_doi_ntl_hc`.

### 1.2. Chuỗi đã hiệu chỉnh liên vệ tinh

| Cột | Ý nghĩa |
|---|---|
| `sol_ntl_hc` | `sol_ntl` sau khi quy DMSP về thang VIIRS |
| `mat_do_ntl_hc` | `sol_ntl_hc ÷ diện tích` |
| `thay_doi_ntl_hc` | biến động trên chuỗi đã hiệu chỉnh, **có giá trị cả ở mốc 2013→2014** |

Phương pháp: hồi quy log–log `sol_viirs = a × sol_dmsp^b` khớp trên các tỉnh có cả hai
nguồn ở năm chồng lấn 2013. Tham số lưu tại `metadata/hieu_chinh_dmsp_viirs.json`.

> **Dùng cột nào:** phân tích bắc qua 2013 → luôn dùng `_hc`. Phân tích chỉ trong
> 2014–2025 → dùng cột gốc, không cần hiệu chỉnh.

### 1.3. Phân bố và vùng sáng

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| `mean_ntl` | Bức xạ trung bình mỗi pixel | nW/cm²/sr · DN |
| `std_ntl` | Độ lệch chuẩn trong tỉnh | nW/cm²/sr · DN |
| `min_ntl`, `max_ntl` | Nhỏ nhất, lớn nhất | nW/cm²/sr · DN |
| `cv_ntl` | `std ÷ mean` — mức chênh lệch sáng–tối trong tỉnh | không thứ nguyên |
| `so_pixel_sang` | Số pixel vượt ngưỡng sáng | pixel |
| `dt_sang_km2` | Diện tích được chiếu sáng | km² |
| `ty_le_sang_pct` | `dt_sang_km2 ÷ diện tích tỉnh × 100` | % |
| `sol_vung_sang` | Tổng bức xạ **chỉ trên vùng vượt ngưỡng** | nW/cm²/sr · DN |

Ngưỡng sáng: VIIRS **1,5** nW/cm²/sr; DMSP **DN 5**. Hai thang đo khác nhau, không dùng
chung một con số. Ngưỡng thật đã dùng được ghi ở cột `nguong_sang`.

### 1.4. Cột kiểm chứng

`sol_ntl_tho` (tổng trước khi trừ nền), `nguong_nen`, `so_pixel_nen`, `so_pixel_hop_le`,
`dt_tu_nhien_km2`, `nguon_anh`, `ghi_chu`, `hieu_chinh`, `trang_thai`.

Ngưỡng nền: VIIRS **0,5** nW/cm²/sr; DMSP **0** vì `stable_lights` của NOAA đã loại nền sẵn.

---

## 2. Nhóm B — chưa tính, cần ghép ánh sáng với dân số và GDP

Đây mới là **chỉ số kinh tế đêm theo nghĩa kinh tế học**. Nhóm A mô tả ánh sáng;
nhóm B nối ánh sáng với hoạt động kinh tế.

Điều kiện: bảng `kinh_te(ma_tinh, nam, dan_so, gdp, …)` phải có số liệu.

### 2.1. Ba chỉ số cốt lõi

| Chỉ số đề xuất | Công thức | Vì sao cần |
|---|---|---|
| `sol_bq_dau_nguoi` | `sol_ntl_hc ÷ dan_so` | Proxy **mức sống**. Hai tỉnh cùng tổng sáng nhưng khác dân số là hai câu chuyện khác hẳn |
| `do_co_gian_sol_gdp` | `%Δ sol_ntl_hc ÷ %Δ gdp` | **Chỉ số trung tâm** của Henderson–Storeygard–Weil [1]. Cho biết ánh sáng phản ánh tăng trưởng tốt đến đâu |
| `gdp_du_bao_tu_anh` | hồi quy `ln(gdp) ~ ln(sol_ntl_hc)` trên 63 tỉnh, rồi dự báo | **Giá trị thực tiễn lớn nhất**: ước lượng GDP cho đơn vị hoặc năm chưa có số liệu thống kê |

### 2.2. Bốn chỉ số bổ sung

| Chỉ số đề xuất | Công thức | Ý nghĩa |
|---|---|---|
| `chenh_lech_gdp_anh` | `(gdp − gdp_du_bao) ÷ gdp_du_bao × 100` | Tỉnh sáng hơn hoặc tối hơn mức GDP giải thích được — gợi ý kinh tế phi chính thức hoặc cơ cấu đặc thù |
| `sol_tren_gdp` | `sol_ntl_hc ÷ gdp` | Cường độ sáng trên một đồng GDP. Công nghiệp sáng nhiều, dịch vụ và nông nghiệp ít — phản ánh cơ cấu kinh tế |
| `cuong_do_vung_sang` | `sol_vung_sang ÷ dt_sang_km2` | Cường độ ở chính nơi có sáng, loại bỏ ảnh hưởng của việc tỉnh rộng hay hẹp |
| `ty_trong_sol_quoc_gia` | `sol tỉnh ÷ tổng sol cả nước × 100` | Theo dõi **dịch chuyển kinh tế giữa các vùng** qua 22 năm |

---

## 3. Ba ràng buộc phương pháp

### 3.1. GDP phải ở giá so sánh

Nếu `gdp` là **giá hiện hành**, độ co giãn ánh sáng–GDP sẽ bị lạm phát làm sai lệch nặng:
GDP danh nghĩa tăng một phần chỉ vì giá tăng, trong khi ánh sáng không phản ứng với giá.

**Phải khử lạm phát trước khi tính nhóm B.** Đây là câu hỏi quan trọng nhất cần làm rõ
với người cung cấp số liệu — sai ở đây thì toàn bộ nhóm B sai theo.

### 3.2. Bắc qua 2013 thì dùng cột `_hc`

DMSP (DN 0–63, bão hoà ở lõi đô thị) và VIIRS (bức xạ, không bão hoà) là hai thang đo
khác nhau. Dùng `sol_ntl` gốc cho chuỗi 2004–2025 sẽ tạo một bước nhảy giả ở mốc 2013→2014,
và mọi độ co giãn tính qua mốc đó đều vô nghĩa.

### 3.3. Thận trọng với DMSP ở tỉnh nhỏ và nghèo

Gibson và cộng sự [8] chỉ ra DMSP kém tin cậy ở đơn vị địa lý nhỏ và vùng nông thôn, do
bão hoà ở đô thị và nhiễu nền ở nông thôn. Nếu một kết luận phụ thuộc vào các tỉnh nhỏ
hoặc thu nhập thấp, nên giới hạn ở giai đoạn VIIRS 2014–2025 và **nói rõ trong báo cáo**.

---

## 4. Trạng thái

| | |
|---|---|
| Nhóm A | ✅ đã tính cho 63 tỉnh × 22 năm |
| Nhóm B | ⬜ chưa làm — chờ dân số và GDP |
| Bảng `kinh_te` | ⬜ rỗng — giảng viên cung cấp |

Khi có số liệu kinh tế: bảy chỉ số nhóm B tính trong `task_pipeline/derive.py`, app chỉ
đọc — đúng nguyên tắc dự án là không tính chỉ số trong API.

---

## Tài liệu tham khảo

Đánh số theo danh mục trong đề cương thực tập.

- **[1]** Henderson, Storeygard, Weil (2012), *Measuring economic growth from outer space*,
  American Economic Review 102(2), 994–1028.
- **[2]** Chen, Nordhaus (2011), *Using luminosity data as a proxy for economic statistics*,
  PNAS 108(21), 8589–8594.
- **[3]** Gibson, Olivia, Boe-Gibson (2020), *Night lights in economics: sources and uses*,
  Journal of Economic Surveys 34(5), 955–980.
- **[8]** Gibson, Olivia, Boe-Gibson, Li (2021), *Which night lights data should I use in
  economics, and where?*, Journal of Development Economics 149, 102602.
