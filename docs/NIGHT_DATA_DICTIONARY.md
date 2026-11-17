# Night Data Dictionary

| Nhóm | Trường dữ liệu | Tên trong Task 3 | Ý nghĩa | Note |
|---|---|---|---|---|
| Băng ảnh đầu vào | `avg_rad` | `avg_rad` | Bức xạ ánh sáng đêm tại từng pixel của sản phẩm VIIRS tháng, đơn vị nW/cm²/sr; sản phẩm đã được tổng hợp tháng, không phải tín hiệu thô của cảm biến. | Raw |
| Băng ảnh đầu vào | `cf_cvg` | `cf_cvg` | Số lượt quan sát sạch mây tại từng pixel của sản phẩm VIIRS tháng, đơn vị lượt. | Raw |
| Băng ảnh đầu vào | `stable_lights` | — | Giá trị ánh sáng đêm DMSP theo năm, thang DN 0–63; có trong dự án, không dùng trong Task 3. | Raw |
| Định danh | `province_code` | — | Mã thống kê của tỉnh trước sáp nhập trong app; khác hệ mã GADM `GID_1`. | Raw |
| Định danh | `province_name` | `NAME_1` | Tên tỉnh, thành phố. | Raw |
| Định danh | `GID_1` | `GID_1` | Mã tỉnh theo GADM; Task 3 xuất trường này, app dùng `province_code`. | Raw |
| Định danh | `GID_3` | `GID_3` | Mã xã theo GADM trong Task 3; bộ chỉ số hiện tại của app ở cấp tỉnh. | Raw |
| Định danh | `NAME_3` | `NAME_3` | Tên xã, phường được chọn trong Task 3. | Raw |
| Thời gian | `year` | `YEAR` | Năm của quan sát. | Raw |
| Thời gian | `month` | `MONTH` | Tháng của quan sát; app dùng 0 cho dòng theo năm. | Raw |
| Thời gian | `period` | `TIME` | Mốc thời gian dạng YYYY-MM với dòng tháng, YYYY với dòng năm. | Processed |
| Thời gian | `frequency` | — | Tần suất của dòng dữ liệu: `annual` hoặc `monthly`. | Processed |
| Nguồn | `source` | — | Nguồn ảnh DMSP hoặc VIIRS đối với bảng chỉ số đêm. | Raw |
| Đầu vào tính toán | `path` | — | Đường dẫn ảnh đã lọc theo tỉnh trong danh sách ảnh đầu vào; không phải chỉ số trích từ pixel. | Raw |
| Tham số xử lý | `background_threshold` | — | Ngưỡng loại nền khỏi tổng SOL: VIIRS 0,5 nW/cm²/sr, DMSP 0 DN. | Raw |
| Tham số xử lý | `lit_threshold` | Hằng số `1.5` | Ngưỡng xác định pixel sáng: VIIRS 1,5 nW/cm²/sr; DMSP 5 DN trong dự án. | Raw |
| Tính từ ranh giới | `area_km2` | — | Diện tích tự nhiên tỉnh tính từ ranh giới GADM 4.1 trong EPSG:6933, đơn vị km²; không phải diện tích pixel có dữ liệu. | Processed |
| Tính từ ranh giới | `COMMUNE_AREA_HA` | `COMMUNE_AREA_HA` | Diện tích tự nhiên xã trong Task 3, tính từ hình học GEE và đổi sang ha; không phải diện tích tỉnh `area_km2`. | Processed |
| Thống kê từ ảnh | `valid_pixels` | Biến `total_pixels`, từ `avg_rad_count` | Số pixel có dữ liệu hợp lệ trong địa bàn; Task 3 dùng làm mẫu số nhưng không xuất thành cột CSV. | Processed |
| Thống kê từ ảnh | `sol_raw` | `TNL`, từ `avg_rad_sum` | Tổng bức xạ pixel hợp lệ trước bước loại nền của module tính chỉ số. Task 3 cộng trực tiếp `avg_rad`; số có thể khác app nếu ảnh đầu vào đã qua các bước lọc khác nhau. | Processed |
| Thống kê từ ảnh | `sol` | — | Tổng bức xạ pixel hợp lệ sau loại nền: pixel dưới `background_threshold` đóng góp 0; không lấy bức xạ từng pixel trừ đi ngưỡng. Đơn vị nW/cm²/sr với VIIRS, DN với DMSP. | Processed |
| Thống kê từ ảnh | `background_pixels` | — | Số pixel hợp lệ dưới ngưỡng nền. | Processed |
| Thống kê từ ảnh | `rad_mean` | `MEAN_RAD`, từ `avg_rad_mean` | Bức xạ trung bình trên pixel hợp lệ; có tính pixel dưới ngưỡng nền. | Processed |
| Thống kê từ ảnh | `rad_std` | `STD_RAD`, từ `avg_rad_stdDev` | Độ lệch chuẩn bức xạ trên pixel hợp lệ, cùng đơn vị với bức xạ; module hiện tại tính độ lệch chuẩn tổng thể. | Processed |
| Thống kê từ ảnh | `rad_min` | `MIN_RAD`, từ `avg_rad_min` | Giá trị bức xạ nhỏ nhất trên pixel hợp lệ. | Processed |
| Thống kê từ ảnh | `rad_max` | `MAX_RAD`, từ `avg_rad_max` | Giá trị bức xạ lớn nhất trên pixel hợp lệ. | Processed |
| Thống kê từ ảnh | `cloud_free_obs` | `CLOUD_FREE_OBS` | Trung bình số lượt quan sát sạch mây trong địa bàn. Task 3 tính từ băng `cf_cvg`; module hiện tại đọc thẻ `CF_CVG_MEAN` trên ảnh đã lọc, thiếu thẻ thì để trống. | Processed |
| Xử lý theo ngưỡng | `is_lit` | Lớp trung gian `is_lit` | Mặt nạ pixel sáng khi `avg_rad ≥ 1,5` trong Task 3; không được xuất thành cột CSV. | Processed |
| Xử lý theo ngưỡng | `lit_rad` | Lớp trung gian `lit_rad` | Bức xạ chỉ giữ tại pixel đạt ngưỡng sáng trong Task 3; không được xuất thành cột CSV. | Processed |
| Xử lý theo ngưỡng | `lit_pixels` | `LIT_PIXELS` | Số pixel hợp lệ đạt ngưỡng sáng. | Processed |
| Xử lý theo ngưỡng | `lit_sol` | `LIT_POP_PROXY` | Tổng bức xạ trên các pixel đạt ngưỡng sáng; tên proxy trong Task 3 không có nghĩa là số dân được đo trực tiếp. | Processed |
| Tính toán từ thống kê | `rad_cv` | `SPATIAL_CV` | Hệ số biến thiên không gian bằng `rad_std / rad_mean`, không thứ nguyên; app để trống nếu trung bình không dương, Task 3 đặt 0. | Processed |
| Tính toán từ thống kê | `sol_density` | — | Mật độ ánh sáng bằng `sol / area_km2`, đơn vị bức xạ trên km². | Processed |
| Tính toán từ thống kê | `lit_area_km2` | — | Diện tích các pixel đạt ngưỡng sáng trong module hiện tại, tính theo lưới ảnh và hệ tọa độ, đơn vị km². | Processed |
| Tính toán từ thống kê | `LIT_AREA_HA` | `LIT_AREA_HA` | Diện tích sáng xấp xỉ trong Task 3 bằng `LIT_PIXELS × 25 ha`; không đồng nhất với cách tính theo lưới ảnh của `lit_area_km2`. | Processed |
| Tính toán từ thống kê | `lit_area_pct` | — | Tỷ lệ diện tích sáng bằng `lit_area_km2 / area_km2 × 100`, đơn vị %. | Processed |
| Tính toán từ thống kê | `lit_pixel_pct` | `ELECTRIFICATION_RATIO_PCT` | Tỷ lệ pixel sáng bằng `lit_pixels / valid_pixels × 100`, đơn vị %; không phải tỷ lệ hộ dân được tiếp cận điện được đo trực tiếp. | Processed |
| Tính toán theo thời gian | `sol_change_pct` | — | Biến động SOL so với năm liền trước, đơn vị %; chỉ tính khi hai năm có dữ liệu và cùng nguồn ảnh, để trống tại mốc DMSP–VIIRS 2014. | Processed |
| Tính toán theo thời gian | `sol_change_yoy_pct` | — | Biến động SOL tháng so với cùng tháng năm trước, đơn vị %. | Processed |
| Tính toán theo thời gian | `sol_change_mom_pct` | `TNL_MOM_GROWTH_PCT` | Biến động tháng so với tháng trước, đơn vị %. App yêu cầu hai tháng lịch liền nhau; Task 3 dùng `pct_change()` trên các dòng có dữ liệu nên có thể so qua tháng bị thiếu. | Processed |
| Tính toán theo thời gian | `sol_ma3` | `TNL_MA3` | Trung bình trượt SOL trong ba tháng lịch của module hiện tại, dùng các giá trị có số trong cửa sổ. Task 3 lấy trung bình tối đa ba dòng gần nhất của TNL, có thể vượt khoảng ba tháng lịch nếu thiếu tháng. | Processed |
| Xử lý chất lượng | `status` | — | Trạng thái xử lý dữ liệu; module tính lại trả `OK` khi có pixel hợp lệ, `INSUFFICIENT_QUALITY` khi ảnh không có pixel hợp lệ. | Processed |
| Xử lý chất lượng | `obs_status` | — | Cờ quan sát: A bình thường, B mốc đổi vệ tinh của chuỗi năm, L có ảnh nhưng không có pixel hợp lệ, U ít lượt sạch mây; bảng pipeline còn dùng O khi thiếu ảnh. | Processed |
| Xử lý chất lượng | `note` | — | Ghi chú về mốc đổi nguồn ảnh, như DMSP sang VIIRS. | Processed |
| Dữ liệu cho hiệu chỉnh | `sol_dmsp` | — | Tổng SOL DMSP năm 2013 của địa bàn, dùng lập cặp chồng lấn để khớp mô hình hiệu chỉnh. | Processed |
| Dữ liệu cho hiệu chỉnh | `sol_viirs` | — | Tổng SOL VIIRS năm 2013 của cùng địa bàn, dùng lập cặp với `sol_dmsp`. | Processed |
| Hiệu chỉnh từ thống kê | `sol_cal` | — | SOL sau khi quy DMSP sang thang VIIRS; VIIRS giữ nguyên. Module tính lại hiện chưa tính cột này. | Processed |
| Hiệu chỉnh từ thống kê | `sol_density_cal` | — | Mật độ sau hiệu chỉnh bằng `sol_cal / area_km2`; module tính lại hiện chưa tính cột này. | Processed |
| Hiệu chỉnh từ thống kê | `sol_change_cal_pct` | — | Biến động SOL năm trên chuỗi đã hiệu chỉnh DMSP–VIIRS; không khắc phục mốc đổi DMSP F16–F18 năm 2010. Module tính lại hiện chưa tính cột này. | Processed |
| Hiệu chỉnh từ thống kê | `calibration` | — | Tên hoặc trạng thái hiệu chỉnh; module tính lại hiện ghi `PENDING`. | Processed |
