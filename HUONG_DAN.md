# VNGIS dữ liệu cấp huyện 07/2024–06/2025

Branch `vngis-ee-districts-202407-202506` chạy GADM cấp 2: **710 huyện, 63 tỉnh/thành**, 12 tháng từ 07/2024 đến 06/2025, gồm TIFF ngày/đêm và CSV. Actions mặc định TIFF ngày 50 m, 10 kênh Int16; CSV giữ phép tính gốc, ảnh đêm 500 m. Có tùy chọn 20 m dùng lại thư mục cũ.

Đọc [SETUP_DISTRICTS_202407_202506.md](SETUP_DISTRICTS_202407_202506.md) để upload asset `districts_l2`, cấu hình project/Drive/secrets, chạy pilot rồi full và theo dõi trạng thái.

Pipeline mặc định nghỉ chủ động 30 giây cho toàn bộ luồng EE sau mỗi 10 huyện mới hoàn tất hoặc khi hoàn tất một tỉnh; mốc trùng nhau chỉ nghỉ một lần. Xem mục 11 trong setup để chỉnh thời gian nghỉ và các tham số tốc độ. Log `[rest]` báo lúc nghỉ/tiếp tục; STOP ngắt được khoảng nghỉ.

Chuẩn bị lại shapefile đã kiểm tra từ nguồn chính thức bằng `python tools/prepare_district_gadm.py`. Dùng file Python/YAML ở thư mục gốc; thư mục `vngis-github-repo-v6` là bản lưu cũ.
