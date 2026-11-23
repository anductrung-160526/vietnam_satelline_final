# Chỉ số kinh tế đêm — danh mục và phương pháp

## Phạm vi và thuật ngữ

Tab **Chỉ số đêm** trình bày đặc trưng bức xạ và điểm ảnh. Tab **Chỉ số kinh tế đêm** trình bày GRDP, các chỉ báo kinh tế từ ánh sáng, quan hệ ánh sáng–GRDP và hồi quy. Một số thống kê bức xạ xuất hiện ở cả hai tab để hỗ trợ diễn giải; tên gọi và công thức giữ thống nhất. SOL, mật độ, tăng trưởng SOL và hai trường GRDP không còn trong bộ lọc Chỉ số đêm.

`sol` có tên thống nhất **Quy mô kinh tế đêm theo ánh sáng (SOL)**. Đây là chỉ báo đại diện từ tổng bức xạ sau lọc nền, không phải giá trị gia tăng, doanh thu hay GRDP riêng của kinh tế đêm. `sol_density` là **Mật độ kinh tế đêm theo ánh sáng**, tức SOL chia diện tích tự nhiên tỉnh. Diện tích được chiếu sáng và tổng bức xạ là hai đại lượng khác nhau.

`predicted_gdp` là **GRDP ước lượng từ ánh sáng**, không gọi là dự báo tương lai hoặc GDP kinh tế đêm. `light_gdp_elasticity` là **Tỷ số tăng trưởng ánh sáng–GRDP**, không đồng nhất với hệ số β của hồi quy mức log–log và không diễn giải như quan hệ nhân quả.

## Danh mục hiển thị

Khoá dòng: `province_code`, `province_name`, `year`, `month`; tháng bằng 0 là dòng năm. Các khoá đứng trước 25 trường dưới đây: 2 Raw, 23 Processed. Trong mỗi nhóm, các biến có cùng cách đo lường đặt liền nhau. `U` là DN với DMSP hoặc nW/cm²/sr với VIIRS; chỉ so sánh trong cùng thang đo. Raw là dữ liệu đầu vào của dự án; tổng và thống kê tính từ ảnh, kể cả `sol_raw`, đều là Processed.

| field | Tên chuẩn | Loại | Định nghĩa | Công thức | Đơn vị |
|---|---|---|---|---|---|
| `grdp_so_sanh` | GRDP theo giá so sánh | Raw | GRDP tỉnh giá so sánh năm gốc 2010, cơ sở chính thức cho phân tích tăng trưởng. | Đọc sheet giá so sánh. | tỷ đồng, giá 2010 |
| `grdp_hien_hanh` | GRDP theo giá hiện hành | Raw | GRDP tỉnh giá hiện hành, dùng đối chiếu. | Đọc sheet giá hiện hành. | tỷ đồng, giá từng năm |
| `background_threshold` | Ngưỡng lọc bức xạ nền | Processed | Ngưỡng nền đang dùng: VIIRS 0,5; DMSP 0. Tham số xử lý, không phải biến ảnh Raw. | b = 0,5 với VIIRS; b = 0 với DMSP. | U |
| `background_pixels` | Số pixel dưới ngưỡng nền | Processed | Số pixel dưới ngưỡng nền; vẫn là pixel hợp lệ nhưng đóng góp 0 vào SOL. | Số i thuộc V có R_i < b. | pixel |
| `sol_raw` | Tổng bức xạ trước lọc nền | Processed | Tổng bức xạ trên tập pixel hợp lệ trước bước lọc nền SOL, không nhân trọng số diện tích. Đây là thống kê tính từ ảnh thuộc nhóm Processed, dù tên trường chứa raw; không khôi phục tín hiệu đã bị loại ở bước xử lý đầu vào. | S_raw = tổng R_i, i thuộc V. | U |
| `sol` | Quy mô kinh tế đêm theo ánh sáng (SOL) | Processed | Chỉ báo đại diện cho quy mô hoạt động kinh tế đêm, đo bằng tổng bức xạ của các pixel hợp lệ đạt ngưỡng nền trong tỉnh. Chỉ số phản ánh ánh sáng quan sát được; không đo trực tiếp doanh thu hoặc giá trị gia tăng của kinh tế đêm. | S = tổng R_i × 1[R_i ≥ b]. Pixel dưới nền đóng góp 0; không lấy R_i trừ b. | U |
| `sol_density` | Mật độ kinh tế đêm theo ánh sáng | Processed | Chỉ báo mật độ hoạt động kinh tế đêm dựa trên tổng bức xạ sau lọc nền trên một đơn vị diện tích tự nhiên tỉnh. Không phải mật độ GDP hoặc dân số. | SOL / diện tích tự nhiên tỉnh, diện tích phải dương; dùng SOL chưa hiệu chỉnh. | U/km² |
| `lit_threshold` | Ngưỡng xác định pixel sáng | Processed | Ngưỡng xác định pixel sáng, khác ngưỡng nền: VIIRS 1,5; DMSP 5. | h = 1,5 VIIRS; h = 5 DMSP. | U |
| `lit_pixels` | Số pixel được chiếu sáng | Processed | Số pixel bức xạ hợp lệ đạt ngưỡng sáng. | L = tổng 1[R_i ≥ h], i thuộc V. | pixel |
| `lit_sol` | Tổng bức xạ trên vùng được chiếu sáng | Processed | Tổng bức xạ vùng sáng; tên lịch sử có pop nhưng không phải số dân. | T_lit = tổng R_i × 1[R_i ≥ h]. | U |
| `lit_area_km2` | Diện tích được chiếu sáng | Processed | Diện tích pixel sáng nằm thực sự trong tỉnh; v9 fractional cộng phần giao EPSG:6933, không cộng cả ô chạm biên hoặc nhân cố định 0,25 km². | A_lit = tổng area(pixel_i ∩ tỉnh)/10⁶ × 1[R_i ≥ h]. | km² |
| `lit_area_pct` | Tỷ lệ diện tích được chiếu sáng | Processed | Tỷ lệ diện tích sáng trên diện tích tự nhiên tỉnh; mẫu số A. | 100 × A_lit / A. | % |
| `min_rad` | Bức xạ nhỏ nhất | Processed | Bức xạ nhỏ nhất trên pixel hợp lệ. | min(R_i), i thuộc V. | U |
| `mean_rad` | Bức xạ trung bình | Processed | Bức xạ trung bình trên pixel hợp lệ. | μ = T / N. | U |
| `max_rad` | Bức xạ lớn nhất | Processed | Bức xạ lớn nhất trên pixel hợp lệ. | max(R_i), i thuộc V. | U |
| `std_rad` | Độ lệch chuẩn bức xạ | Processed | Độ lệch chuẩn tổng thể, ddof=0. | σ = sqrt(max(tổng R_i² / N − μ², 0)). | U |
| `spatial_cv` | Hệ số biến thiên bức xạ | Processed | Hệ số biến thiên; dictionary giữ quy ước Task 3 bằng 0 khi μ ≤ 0, trống nếu N=0. App ánh xạ rad_cv nên có thể hiển thị trống khi μ ≤ 0. | σ / μ nếu μ > 0; trường hợp khác theo mô tả. | không thứ nguyên |
| `sol_change_pct` | Tốc độ thay đổi quy mô kinh tế đêm theo năm | Processed | Tốc độ thay đổi chỉ báo quy mô kinh tế đêm theo ánh sáng so với năm liền trước. Chỉ so sánh khi cùng nguồn ảnh; không tính qua mốc đổi DMSP F16/F18 năm 2010 hoặc DMSP–VIIRS năm 2014. | 100 × (SOL_y / SOL_y−1 − 1); thiếu hoặc mẫu số không dương thì trống. | % |
| `gdp_change_pct` | Tốc độ tăng trưởng GRDP | Processed | Tăng trưởng GRDP năm liền trước, tính riêng từng cơ sở giá; không phụ thuộc có ảnh. Thiếu/không dương giá trị năm trước thì trống. | 100 × (gdp_y / gdp_y−1 − 1). | % |
| `light_gdp_elasticity` | Tỷ số tăng trưởng ánh sáng–GRDP | Processed | Tỷ số tăng trưởng quy mô kinh tế đêm theo ánh sáng và tăng trưởng GRDP trong cùng hai năm liên tiếp. Không đồng nhất với hệ số beta của hồi quy log–log. | (phần trăm thay đổi SOL) / (phần trăm thay đổi GRDP); tăng trưởng GRDP bằng 0 hoặc thiếu tham chiếu thì trống. | không thứ nguyên |
| `sol_gdp_ratio` | Cường độ ánh sáng trên GRDP | Processed | Cường độ ánh sáng trên một tỷ đồng GRDP; so sánh trong cùng nguồn ảnh và cùng cơ sở giá. | SOL / GRDP, chỉ khi GRDP dương. | U/tỷ đồng |
| `predicted_gdp` | GRDP ước lượng từ ánh sáng | Processed | GRDP ước lượng từ mô hình log–log trên mẫu VIIRS có SOL và đủ hai loại GRDP dương trong phạm vi đang chọn. Cần ít nhất 10 quan sát và phương sai ln(SOL) dương. Đây là ước lượng từ ánh sáng, không phải giá trị kinh tế đêm đo trực tiếp hoặc dự báo cho tương lai. | exp(alpha + beta × ln(SOL)); mô hình theo từng cơ sở giá. | tỷ đồng |
| `sol_change_mom_pct` | Tốc độ thay đổi quy mô kinh tế đêm theo tháng | Processed | So đúng tháng lịch trước, thiếu tháng trước thì trống. | 100 × (S_t / S_(t−1 tháng) − 1). | % |
| `sol_change_yoy_pct` | Tốc độ thay đổi quy mô kinh tế đêm so với cùng kỳ | Processed | So đúng tháng cùng kỳ năm trước. | 100 × (S_t / S_(t−12 tháng) − 1). | % |
| `sol_ma3` | Quy mô kinh tế đêm trung bình ba tháng lịch | Processed | Trung bình quy mô theo ánh sáng trên phần dữ liệu có sẵn trong ba tháng lịch gồm tháng hiện tại và hai tháng trước. Giữ quy tắc hiện hành của bộ tính; không diễn giải là đủ ba quan sát nếu có tháng thiếu. | mean(SOL) trên dữ liệu hiện có của các tháng t, t−1, t−2. | U |

## Tính toán và dữ liệu thiếu

Ảnh tháng và ảnh năm đọc từ kết quả đã nạp. Không xử lý lại raster khi mở app. SOL = Σ Rᵢ × 1[Rᵢ ≥ b] trên tập pixel hợp lệ; đây là lọc theo ngưỡng, không trừ b khỏi từng pixel. Ngưỡng nền VIIRS 0,5 nW/cm²/sr; DMSP 0 DN. Ngưỡng sáng VIIRS 1,5 nW/cm²/sr; DMSP 5 DN. Diện tích sáng dùng diện tích phần giao pixel–tỉnh trong EPSG:6933. Số liệu thập phân làm tròn khi hiển thị, không thay đổi ngưỡng dùng tính toán.

GRDP chính thức dùng **giá so sánh năm gốc 2010**, đơn vị tỷ đồng; giá hiện hành chỉ dùng đối chiếu. Hai cột GRDP cùng hiển thị; các đại lượng ghép và hồi quy theo cơ sở giá đang chọn. Khi chọn đối chiếu hai cơ sở giá, bảng chỉ số ghép dùng giá so sánh, còn biểu đồ có hai mô hình trên cùng mẫu.

GRDP chỉ có theo năm; bảng tháng để null cả GRDP, tăng trưởng GRDP, tỷ số tăng trưởng ánh sáng–GRDP, cường độ ánh sáng trên GRDP và GRDP ước lượng. Không chia GRDP cho 12 hoặc lặp số năm xuống tháng. Hồi quy vẫn dùng quan sát năm ngay cả khi bảng đang xem theo tháng.

Tăng trưởng dùng đúng năm/tháng lịch tham chiếu, kể cả mốc trước nằm ngoài khoảng đang hiển thị. Thiếu mốc hoặc mẫu số không dương thì null; tăng trưởng GRDP bằng 0 thì tỷ số tăng trưởng ánh sáng–GRDP null. Không so SOL chưa hiệu chỉnh qua năm 2010 hoặc 2014. Tổng ảnh năm được tính từ ảnh tổng hợp cấp pixel, không thay bằng trung vị tổng SOL tháng.

## Hồi quy và GRDP ước lượng

Hai mô hình dùng chung các cặp tỉnh–năm có SOL dương, đủ hai loại GRDP dương cùng đơn vị tỷ đồng, nguồn VIIRS và nguồn gốc dữ liệu nhất quán. Mẫu phụ thuộc khoảng năm/phạm vi tỉnh đang chọn, không cố định ở 2020–2024. Giao diện mặc định chọn 2020–2024; có thể chọn từ 2015 khi số liệu đủ điều kiện.

Với mỗi cơ sở giá: `ln(GRDP) = α + β × ln(SOL) + ε`; α, β ước lượng OLS có hệ số chặn. `predicted_gdp = exp(α + β × ln(SOL))`, tính bằng hệ số chưa làm tròn của chính mẫu trên biểu đồ. Giữ quy tắc của dự án: cần ít nhất 10 quan sát và phương sai ln(SOL) dương; không đủ thì để trống, không lấy hệ số đã lưu từ một mẫu khác. Ngưỡng 10 quan sát là điều kiện tối thiểu của phần mềm, không bảo đảm tự động độ tin cậy thống kê.

Phép chuyển ngược exp không hiệu chỉnh sai lệch do log; vì vậy chưa phải ước lượng không chệch của trung bình GRDP trên thang gốc. R² được tính trên thang log. Kết quả mô tả quan hệ đồng biến, không chứng minh tác động nhân quả và chưa được đánh giá như mô hình dự báo ngoài mẫu.

## Trường loại khỏi màn kinh tế

Theo phạm vi hiện tại, không hiển thị `chenh_lech_gdp_anh`, `cuong_do_vung_sang`, `ty_trong_sol_quoc_gia`, `sol_bq_dau_nguoi`, `sol_cal`, `light_basis`, `valid_pixels`, `area_km2`, `source`, `note`, `calibration`, `status` trong bảng/bộ lọc/CSV kinh tế. Diện tích và số pixel cần cho công thức vẫn được dùng nội bộ; không bổ sung cột hiệu chỉnh hoặc dữ liệu dân số.

Ba tên trường tiếng Việt cũ được chuẩn hoá: `do_co_gian_sol_gdp` → `light_gdp_elasticity`; `gdp_du_bao_tu_anh` → `predicted_gdp`; `sol_tren_gdp` → `sol_gdp_ratio`.

Moran I nằm trong mục mở rộng của tab kinh tế, dùng mật độ SOL năm và trọng số tiếp giáp Queen chuẩn hoá hàng. Đây là tự tương quan không gian, không trực tiếp đo lan toả kinh tế. Tài liệu: [Định nghĩa biến và công thức](DINH_NGHIA_BIEN_VA_CONG_THUC_DEMO.md).

## Nguồn triển khai và tham khảo

- [Night Data Dictionary](NIGHT_DATA_DICTIONARY.md): trường tiếng Anh, định nghĩa tiếng Việt.
- `backend/core/indicator_catalog.py`: tên chuẩn, nhóm, định nghĩa và công thức cho bộ lọc, bảng và nút ⓘ.
- `backend/core/economic_metrics.py`: tăng trưởng, tỷ số và ước lượng theo mẫu hiện tại; API đọc dữ liệu đã nạp và gọi hàm core, không xử lý raster hoặc ghi đè snapshot.
- Henderson, Storeygard & Weil (2012), *Measuring Economic Growth from Outer Space*, American Economic Review, 102(2), 994–1028. Nghiên cứu là cơ sở cho cách tiếp cận dùng ánh sáng làm biến đại diện; tỷ số tăng trưởng đơn giản trong app không phải bản sao mô hình ước lượng của bài báo.
- Chen & Nordhaus (2011), *Using Luminosity Data as a Proxy for Economic Statistics*, PNAS, 108(21), 8589–8594.
- Gibson, Olivia & Boe-Gibson (2020), *Night Lights in Economics: Sources and Uses*, Journal of Economic Surveys, 34(5), 955–980.
