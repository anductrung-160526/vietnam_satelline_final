# Định nghĩa biến và công thức kinh tế đêm

Danh mục hiển thị hiện tại là NIGHT_DATA_DICTIONARY.md: 43 mục, 10 Raw (5 định danh) và 33 Processed. Bảng trên app và CSV giữ định danh → Raw → Processed. Tên trường tiếng Anh chữ thường, diễn giải tiếng Việt. Đây là danh mục hiển thị, không phải danh sách mọi tham số kiểm tra nội bộ của phần mềm.

## Dữ liệu năm và tháng

GRDP giá so sánh và GRDP hiện hành chỉ xuất giá trị ở dòng năm (month=0). Dòng tháng luôn null, xuất CSV là ô trống. Không lặp GRDP năm xuống tháng, không chia 12 hoặc nội suy. GRDP so sánh của bộ dữ liệu dùng giá gốc năm 2010, đơn vị tỷ đồng; 2024 sơ bộ theo nguồn.

Raw gồm nguồn và băng ảnh đầu vào, GRDP thật. avg_rad và cf_cvg trong bảng là tham chiếu băng ảnh Raw, không phải một số đại diện cho tỉnh. Ảnh năm median là đầu vào đã xử lý, không được gán thành băng Raw.

## Tổng và phân bố ánh sáng

Trên tập pixel hợp lệ trong tỉnh V: sol_raw = tổng R_i. sol = tổng R_i với R_i ≥ background_threshold; pixel dưới ngưỡng đóng góp 0, không lấy R_i trừ ngưỡng. Ngưỡng nền VIIRS 0,5 nW/cm²/sr, DMSP 0 DN. background_pixels đếm pixel dưới ngưỡng. mean_rad, std_rad, min_rad, max_rad là trung bình, độ lệch chuẩn, nhỏ nhất, lớn nhất của V; spatial_cv = std_rad / mean_rad, mẫu số bằng 0 thì trống.

sol_density = sol / area_km2, dùng ánh sáng chưa hiệu chỉnh. Không dùng phiên bản hiệu chỉnh khi hiển thị mật độ/tăng trưởng đã thu gọn. Không so sánh trực tiếp các thang DMSP và VIIRS hoặc bắc qua đổi vệ tinh DMSP 2010.

## Vùng sáng và diện tích

lit_threshold của VIIRS là 1,5 nW/cm²/sr, DMSP là 5 DN. lit_pixels đếm pixel R_i ≥ ngưỡng sáng; lit_sol tổng bức xạ trên các pixel này. lit_area_km2 là tổng diện tích phần giao pixel sáng–tỉnh trong EPSG:6933. lit_area_pct = lit_area_km2 / area_km2 × 100. electrification_ratio_pct = lit_pixels / total_pixels × 100, chỉ là tỷ lệ pixel sáng, không phải tỷ lệ hộ có điện.

Năm lớp sáng dùng các ngưỡng VIIRS cố định của bộ D: 0,5; 1,5; 3,0850000381469727; 17,459999084472656. Bằng ngưỡng thuộc lớp cao hơn; cận trên lớp cuối không hữu hạn. Tổng diện tích lớp dùng phần giao pixel–tỉnh. NoData không phải vùng tối.

## Biến động theo thời gian

sol_change_pct là thay đổi năm trước trong cùng nguồn. sol_change_mom_pct so tháng lịch liền trước, sol_change_yoy_pct so cùng tháng năm trước. Thiếu mốc tham chiếu hoặc mẫu số không dương thì trống. sol_ma3 dùng ba tháng lịch đủ dữ liệu. tnl_ma3 và tnl_mom_growth_pct là tên tương thích Task 3 cho cửa sổ theo quan sát, khác cửa sổ tháng lịch; không gộp hai công thức. gdp_change_pct chỉ có theo năm và theo cơ sở giá so sánh khi hiển thị chính.

## Moran

Chỉ giữ moran_i trong danh mục và app. I = (n/S0) × tổng_i tổng_j(W_ij z_i z_j) / tổng_i(z_i²), z_i = mật độ sáng tỉnh i trừ trung bình mẫu. Trọng số tiếp giáp Queen chuẩn hóa hàng, cùng năm; loại tỉnh thiếu/cô lập. Không đủ mẫu hoặc biến không có phương sai thì trống. Chỉ số đo tự tương quan không gian, không chứng minh nhân quả hoặc lan tỏa kinh tế. Các bước kiểm định và kiểm chứng tiếp tục được giữ nội bộ.

## Dữ liệu thật và trường trùng

App loại các dòng có nguồn/trạng thái GIA_LAP, SIMULATED hoặc SYNTHETIC. Lệnh backend.data.purge_simulated xóa vật lý các dòng đánh dấu này, có backup và transaction, không suy đoán dòng giả từ độ lớn số liệu. Các fixture kiểm thử tách khỏi database phục vụ app.

Bỏ tnl vì trùng sol_raw trên cùng đầu vào; bỏ gdp vì đã có hai trường GRDP riêng; bỏ frequency vì month đã xác định năm/tháng; bỏ các trường truy nguồn/độ phủ dư khỏi danh mục hiển thị. lit_pop_proxy dùng tên thống nhất lit_sol. Các nhóm người dùng yêu cầu bỏ không còn trong bộ lọc/bảng/CSV công khai. Các kiểm tra và dữ liệu kỹ thuật phục vụ toàn vẹn, mask, phiên bản tiếp tục chạy nội bộ, không sửa công thức hay buộc tính lại ảnh.

Trường population đã bỏ khỏi danh mục, bộ lọc, bảng, CSV và màn kinh tế; không còn yêu cầu nạp dân số để sử dụng app.
