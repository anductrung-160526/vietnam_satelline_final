# Night Data Dictionary

## 1. Night Data — Task 3

| Nhóm | Trường dữ liệu | Tên trong Task 3 | Ý nghĩa | Note |
|---|---|---|---|---|
| Băng ảnh đầu vào | `avg_rad` | `avg_rad` | Bức xạ ánh sáng đêm tại từng pixel của sản phẩm VIIRS tháng, đơn vị nW/cm²/sr. Đây là đầu vào của Task 3, đã được nhà cung cấp tổng hợp tháng. | Raw |
| Băng ảnh đầu vào | `cf_cvg` | `cf_cvg` | Số lượt quan sát sạch mây tại từng pixel của sản phẩm VIIRS tháng, đơn vị lượt. | Raw |
| Định danh | `GID_1` | `GID_1` | Mã tỉnh theo GADM. | Raw |
| Định danh | `NAME_1` | `NAME_1` | Tên tỉnh, thành phố. | Raw |
| Định danh | `GID_3` | `GID_3` | Mã xã, phường theo GADM. | Raw |
| Định danh | `NAME_3` | `NAME_3` | Tên xã, phường được chọn để trích xuất dữ liệu. | Raw |
| Thời gian | `YEAR` | `YEAR` | Năm của quan sát. | Raw |
| Thời gian | `MONTH` | `MONTH` | Tháng của quan sát, từ 1 đến 12. | Raw |
| Thời gian | `TIME` | `TIME` | Mốc thời gian được ghép từ năm và tháng, dạng YYYY-MM. | Processed |
| Tính từ ranh giới | `COMMUNE_AREA_HA` | `COMMUNE_AREA_HA` | Diện tích tự nhiên xã tính từ hình học ranh giới trên GEE, đơn vị ha. | Processed |
| Thống kê từ ảnh | `total_pixels` | Biến `total_pixels`, từ `avg_rad_count` | Số pixel có dữ liệu trong địa bàn; biến trung gian dùng tính tỷ lệ pixel sáng, không xuất thành cột CSV. | Processed |
| Thống kê từ ảnh | `TNL` | `TNL` | Tổng bức xạ `avg_rad` trong địa bàn; Task 3 không áp dụng ngưỡng loại nền riêng cho tổng này. | Processed |
| Thống kê từ ảnh | `MEAN_RAD` | `MEAN_RAD` | Bức xạ trung bình trên các pixel có dữ liệu trong địa bàn, đơn vị nW/cm²/sr. | Processed |
| Thống kê từ ảnh | `STD_RAD` | `STD_RAD` | Độ lệch chuẩn bức xạ trong địa bàn, đơn vị nW/cm²/sr. | Processed |
| Thống kê từ ảnh | `MIN_RAD` | `MIN_RAD` | Bức xạ nhỏ nhất trong địa bàn, đơn vị nW/cm²/sr. | Processed |
| Thống kê từ ảnh | `MAX_RAD` | `MAX_RAD` | Bức xạ lớn nhất trong địa bàn, đơn vị nW/cm²/sr. | Processed |
| Thống kê từ ảnh | `CLOUD_FREE_OBS` | `CLOUD_FREE_OBS` | Trung bình băng `cf_cvg` trên địa bàn, đơn vị lượt quan sát sạch mây. | Processed |
| Xử lý theo ngưỡng | `is_lit` | Lớp trung gian `is_lit` | Mặt nạ pixel sáng khi `avg_rad ≥ 1,5 nW/cm²/sr`; không xuất thành cột CSV. | Processed |
| Xử lý theo ngưỡng | `lit_rad` | Lớp trung gian `lit_rad` | Bức xạ chỉ giữ ở pixel đạt ngưỡng sáng; không xuất thành cột CSV. | Processed |
| Xử lý theo ngưỡng | `LIT_PIXELS` | `LIT_PIXELS` | Số pixel đạt ngưỡng sáng 1,5 nW/cm²/sr. | Processed |
| Xử lý theo ngưỡng | `LIT_POP_PROXY` | `LIT_POP_PROXY` | Tổng bức xạ trên các pixel đạt ngưỡng sáng; là biến đại diện, không phải số dân đo trực tiếp. | Processed |
| Tính toán từ thống kê | `SPATIAL_CV` | `SPATIAL_CV` | Hệ số biến thiên không gian bằng `STD_RAD / MEAN_RAD`, không thứ nguyên; Task 3 đặt 0 nếu bức xạ trung bình không dương. | Processed |
| Tính toán từ thống kê | `LIT_AREA_HA` | `LIT_AREA_HA` | Diện tích sáng xấp xỉ bằng `LIT_PIXELS × 25 ha`, theo giả định pixel 500 m × 500 m. | Processed |
| Tính toán từ thống kê | `ELECTRIFICATION_RATIO_PCT` | `ELECTRIFICATION_RATIO_PCT` | Tỷ lệ pixel sáng bằng `LIT_PIXELS / total_pixels × 100`, đơn vị %; không phải tỷ lệ hộ dân tiếp cận điện đo trực tiếp. | Processed |
| Tính toán theo thời gian | `TNL_MA3` | `TNL_MA3` | Trung bình trượt tối đa ba dòng TNL gần nhất, tối thiểu một dòng; có thể vượt ba tháng lịch khi thiếu tháng. | Processed |
| Tính toán theo thời gian | `TNL_MOM_GROWTH_PCT` | `TNL_MOM_GROWTH_PCT` | Phần trăm thay đổi TNL so với dòng quan sát trước, tính bằng `pct_change() × 100`; có thể so qua tháng bị thiếu. | Processed |

## 2. Night Economy — CHI_SO_KINH_TE_DEM

| Nhóm | Trường dữ liệu | Tên trong Task 3 | Ý nghĩa | Note |
|---|---|---|---|---|
| Đầu vào kinh tế | `population` | — | Dân số của địa bàn trong năm, đơn vị người; lấy từ số liệu thống kê cung cấp riêng. | Raw |
| Đầu vào kinh tế | `gdp` | — | GDP theo tên trường trong tài liệu nguồn; ở cấp tỉnh dùng GRDP, thống nhất đơn vị tiền tệ và giá so sánh khi phân tích tăng trưởng. | Raw |
| Chỉ số ánh sáng | `sol` | — | Quy mô ánh sáng sau loại nền: tổng bức xạ pixel hợp lệ, pixel dưới ngưỡng nền đóng góp 0. Khác TNL của Task 3 vì có bước loại nền; ngưỡng VIIRS 0,5 nW/cm²/sr, DMSP 0 DN. | Processed |
| Chỉ số ánh sáng | `sol_density` | — | Mật độ ánh sáng bằng `sol / diện tích tự nhiên địa bàn (km²)`, đơn vị bức xạ/km². | Processed |
| Chỉ số ánh sáng | `sol_change_pct` | — | Phần trăm thay đổi SOL so với năm liền trước, chỉ so trong cùng nguồn ảnh; khác biến động tháng `TNL_MOM_GROWTH_PCT` ở bảng 1. | Processed |
| Hiệu chỉnh liên vệ tinh | `sol_cal` | — | SOL sau khi quy DMSP sang thang VIIRS bằng mô hình khớp trên năm chồng lấn 2013; VIIRS giữ nguyên. Không sửa mốc đổi DMSP F16–F18 năm 2010. | Processed |
| Hiệu chỉnh liên vệ tinh | `sol_density_cal` | — | Mật độ ánh sáng sau hiệu chỉnh bằng `sol_cal / diện tích tự nhiên địa bàn (km²)`. | Processed |
| Hiệu chỉnh liên vệ tinh | `sol_change_cal_pct` | — | Phần trăm thay đổi SOL năm trên chuỗi đã hiệu chỉnh DMSP–VIIRS, bao gồm mốc 2013–2014; không khắc phục đứt gãy năm 2010. | Processed |
| Chỉ số vùng sáng | `lit_area_pct` | — | Tỷ lệ diện tích sáng trên diện tích tự nhiên địa bàn, đơn vị %. Khác `ELECTRIFICATION_RATIO_PCT` ở bảng 1 vì mẫu số là diện tích tự nhiên, không phải số pixel có dữ liệu. | Processed |
| Chỉ số cốt lõi — đề xuất | `sol_bq_dau_nguoi` | — | Ánh sáng bình quân đầu người bằng `sol_cal / population`, đơn vị bức xạ/người; biến đại diện mức sống. | Processed |
| Chỉ số cốt lõi — đề xuất | `do_co_gian_sol_gdp` | — | Tỷ số phần trăm thay đổi ánh sáng trên phần trăm thay đổi GDP/GRDP: `%Δ sol_cal / %Δ gdp`, không thứ nguyên; không xác định khi tăng trưởng GDP bằng 0. | Processed |
| Chỉ số cốt lõi — đề xuất | `gdp_du_bao_tu_anh` | — | GDP/GRDP dự báo từ hồi quy `ln(gdp) ~ ln(sol_cal)` trên dữ liệu tỉnh; cùng đơn vị tiền tệ và cơ sở giá với dữ liệu dùng khớp mô hình. | Processed |
| Chỉ số bổ sung — đề xuất | `chenh_lech_gdp_anh` | — | Chênh lệch tương đối giữa GDP/GRDP thống kê và dự báo: `(gdp − gdp_du_bao_tu_anh) / gdp_du_bao_tu_anh × 100`, đơn vị %. | Processed |
| Chỉ số bổ sung — đề xuất | `sol_tren_gdp` | — | Cường độ ánh sáng trên một đơn vị GDP/GRDP bằng `sol_cal / gdp`, đơn vị bức xạ trên đơn vị tiền tệ của dữ liệu kinh tế. | Processed |
| Chỉ số bổ sung — đề xuất | `cuong_do_vung_sang` | — | Tổng bức xạ vùng sáng chia diện tích vùng sáng theo km²; tài liệu dùng `lit_sol / lit_area_km2`. Task 3 cung cấp đại lượng tương ứng qua `LIT_POP_PROXY` và `LIT_AREA_HA` (đổi ha sang km² trước khi chia). | Processed |
| Chỉ số bổ sung — đề xuất | `ty_trong_sol_quoc_gia` | — | Tỷ trọng ánh sáng tỉnh bằng `sol tỉnh / tổng sol cả nước × 100`, đơn vị %; các giá trị phải cùng mốc thời gian, cùng thang đo và đủ phạm vi tỉnh. | Processed |
