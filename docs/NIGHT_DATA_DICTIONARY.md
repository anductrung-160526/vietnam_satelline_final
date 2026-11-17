# Night Data Dictionary

## 1. Night Data — Task 3 áp dụng cấp tỉnh

| Nhóm | Trường dữ liệu | Tên trong Task 3 (viết thường) | Ý nghĩa | Note |
|---|---|---|---|---|
| Băng ảnh đầu vào | `avg_rad` | `avg_rad` | Bức xạ ánh sáng đêm tại từng pixel của sản phẩm VIIRS tháng, đơn vị nW/cm²/sr. Đây là đầu vào của Task 3, đã được nhà cung cấp tổng hợp tháng. | Raw |
| Băng ảnh đầu vào | `cf_cvg` | `cf_cvg` | Số lượt quan sát sạch mây tại từng pixel của sản phẩm VIIRS tháng, đơn vị lượt. | Raw |
| Định danh | `gid_1` | `gid_1` | Mã tỉnh theo GADM. | Raw |
| Định danh | `name_1` | `name_1` | Tên tỉnh, thành phố. | Raw |
| Thời gian | `year` | `year` | Năm của quan sát. | Raw |
| Thời gian | `month` | `month` | Tháng của quan sát, từ 1 đến 12. | Raw |
| Tính từ ranh giới | `area_km2` | — | Diện tích tự nhiên tỉnh trước sáp nhập, tính từ ranh giới GADM 4.1 trong EPSG:6933, đơn vị km²; dùng làm mẫu số tính mật độ và tỷ lệ diện tích sáng. | Processed |
| Thống kê từ ảnh | `total_pixels` | Biến `total_pixels`, từ `avg_rad_count` | Số pixel có dữ liệu trong tỉnh; biến trung gian dùng tính tỷ lệ pixel sáng, không xuất thành cột CSV. | Processed |
| Thống kê từ ảnh | `tnl` | `tnl` | Tổng bức xạ `avg_rad` trong tỉnh; Task 3 không áp dụng ngưỡng loại nền riêng cho tổng này. | Processed |
| Thống kê từ ảnh | `mean_rad` | `mean_rad` | Bức xạ trung bình trên các pixel có dữ liệu trong tỉnh, đơn vị nW/cm²/sr. | Processed |
| Thống kê từ ảnh | `std_rad` | `std_rad` | Độ lệch chuẩn bức xạ trong tỉnh, đơn vị nW/cm²/sr. | Processed |
| Thống kê từ ảnh | `min_rad` | `min_rad` | Bức xạ nhỏ nhất trong tỉnh, đơn vị nW/cm²/sr. | Processed |
| Thống kê từ ảnh | `max_rad` | `max_rad` | Bức xạ lớn nhất trong tỉnh, đơn vị nW/cm²/sr. | Processed |
| Thống kê từ ảnh | `cloud_free_obs` | `cloud_free_obs` | Trung bình băng `cf_cvg` trên tỉnh, đơn vị lượt quan sát sạch mây. | Processed |
| Xử lý theo ngưỡng | `lit_pixels` | `lit_pixels` | Số pixel đạt ngưỡng sáng 1,5 nW/cm²/sr. | Processed |
| Xử lý theo ngưỡng | `lit_pop_proxy` | `lit_pop_proxy` | Tổng bức xạ trên các pixel đạt ngưỡng sáng; là biến đại diện, không phải số dân đo trực tiếp. | Processed |
| Tính toán từ thống kê | `spatial_cv` | `spatial_cv` | Hệ số biến thiên không gian bằng `std_rad / mean_rad`, không thứ nguyên; Task 3 đặt 0 nếu bức xạ trung bình không dương. | Processed |
| Tính toán từ thống kê | `electrification_ratio_pct` | `electrification_ratio_pct` | Tỷ lệ pixel sáng bằng `lit_pixels / total_pixels × 100`, đơn vị %; không phải tỷ lệ hộ dân tiếp cận điện đo trực tiếp. | Processed |
| Tính toán theo thời gian | `tnl_ma3` | `tnl_ma3` | Trung bình trượt tối đa ba dòng tnl gần nhất, tối thiểu một dòng; có thể vượt ba tháng lịch khi thiếu tháng. | Processed |
| Tính toán theo thời gian | `tnl_mom_growth_pct` | `tnl_mom_growth_pct` | Phần trăm thay đổi tnl so với dòng quan sát trước, tính bằng `pct_change() × 100`; có thể so qua tháng bị thiếu. | Processed |

## 2. Night Economy — CHI_SO_KINH_TE_DEM

| Nhóm | Trường dữ liệu | Tên trong Task 3 (viết thường) | Ý nghĩa | Note |
|---|---|---|---|---|
| Đầu vào kinh tế | `population` | — | Dân số của tỉnh trong năm, đơn vị người; lấy từ số liệu thống kê cung cấp riêng. | Raw |
| Đầu vào kinh tế | `gdp` | — | GDP theo tên trường trong tài liệu nguồn; ở cấp tỉnh dùng GRDP, thống nhất đơn vị tiền tệ và giá so sánh khi phân tích tăng trưởng. | Raw |
| Chỉ số ánh sáng | `sol` | — | Quy mô ánh sáng sau loại nền: tổng bức xạ pixel hợp lệ, pixel dưới ngưỡng nền đóng góp 0. Khác tnl của Task 3 vì có bước loại nền; ngưỡng VIIRS 0,5 nW/cm²/sr, DMSP 0 DN. | Processed |
| Chỉ số ánh sáng | `sol_density` | — | Mật độ ánh sáng bằng tổng ánh sáng chia `area_km2`, đơn vị bức xạ/km². Dùng `sol` với chuỗi chưa hiệu chỉnh hoặc `sol_cal` với chuỗi đã hiệu chỉnh; ghi rõ phiên bản đầu vào khi sử dụng. | Processed |
| Chỉ số ánh sáng | `sol_change_pct` | — | Phần trăm thay đổi tổng ánh sáng so với năm liền trước: `(giá trị năm này / giá trị năm trước − 1) × 100`. Dùng `sol` cho chuỗi chưa hiệu chỉnh và chỉ so cùng nguồn ảnh; dùng `sol_cal` cho chuỗi đã hiệu chỉnh để so qua mốc 2013–2014. Không khắc phục đứt gãy DMSP năm 2010. | Processed |
| Chỉ số vùng sáng | `lit_area_km2` | `lit_area_ha` (đổi đơn vị) | Diện tích được chiếu sáng, đơn vị km². Với cách ước tính trong Task 3: `lit_pixels × 0,25 km²`; khi tính theo lưới ảnh thực tế, cộng diện tích các pixel đạt ngưỡng sáng. | Processed |
| Chỉ số vùng sáng | `lit_area_pct` | — | Tỷ lệ diện tích được chiếu sáng bằng `lit_area_km2 / area_km2 × 100`, đơn vị %. Khác `electrification_ratio_pct` ở bảng 1 vì mẫu số là diện tích tự nhiên, không phải số pixel có dữ liệu. | Processed |
| Hiệu chỉnh liên vệ tinh | `sol_cal` | — | SOL sau khi quy DMSP sang thang VIIRS bằng mô hình khớp trên năm chồng lấn 2013; VIIRS giữ nguyên. Không sửa mốc đổi DMSP F16–F18 năm 2010. | Processed |
| Chỉ số cốt lõi — đề xuất | `sol_per_capita` | — | Ánh sáng bình quân đầu người bằng `sol_cal / population`, đơn vị bức xạ/người; biến đại diện mức sống. | Processed |
| Chỉ số cốt lõi — đề xuất | `light_gdp_elasticity` | — | Tỷ số phần trăm thay đổi ánh sáng trên phần trăm thay đổi GDP/GRDP: `%Δ sol_cal / %Δ gdp`, không thứ nguyên; không xác định khi tăng trưởng GDP bằng 0. | Processed |
| Chỉ số cốt lõi — đề xuất | `predicted_gdp` | — | GDP/GRDP dự báo từ hồi quy `ln(gdp) ~ ln(sol_cal)` trên dữ liệu tỉnh; cùng đơn vị tiền tệ và cơ sở giá với dữ liệu dùng khớp mô hình. | Processed |
