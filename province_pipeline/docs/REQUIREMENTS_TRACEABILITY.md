# Đối chiếu kế hoạch quản lý dữ liệu và phạm vi được chốt

IMPLEMENTED dưới đây nghĩa là đã có mã và kiểm tra offline tương ứng; **không đồng nghĩa đã nghiệm thu Earth Engine/Drive/Windows thật**. Xem VALIDATION.md.

| Yêu cầu | Trạng thái | Triển khai / phần còn thiếu |
|---|---|---|
| 63 tỉnh trước sáp nhập, mã thống kê | IMPLEMENTED với GADM research | Tự tải GADM 4.1, pin hash, crosswalk GID+tên sang 63 mã, giữ nguồn/date đúng năm 2022. Bộ chính thức 2024 vẫn cần nguồn riêng |
| Tải ảnh tự động, nhật ký | IMPLEMENTED; live BLOCKED | Direct EE tile downloads + rclone-authenticated Drive upload, log và state/reports; dùng hai secret cũ. Live quyền/project/root/quota cần check_only trên GitHub |
| DMSP 2004–2013, VIIRS 2013–2025, Landsat 2004–2025, S2 từ 2015 | PARTIAL / BLOCKED coverage | Có adapters và live inventory snapshot IDs. Không xuất kỳ thiếu/partial; VCMSLCFG và S2 SR không đủ các năm đầu mục tiêu. Chưa bổ sung sản phẩm thay thế |
| Ảnh TIFF ngày, che mây, composite, ưu tiên mùa khô | IMPLEMENTED; live BLOCKED | Landsat QA/scale/offset; S2 SCL; tháng cấu hình theo tỉnh; tile equal-area có CRS/transform và noData |
| Ảnh TIFF đêm nguồn và lọc thêm | IMPLEMENTED một phần | DMSP stable product, VIIRS coverage và mask âm; chưa kiểm định loại hết cháy/tàu thuyền/ánh sáng tạm thời |
| Hiệu chuẩn liên cảm biến DMSP–VIIRS | BLOCKED scientific | Không dùng hệ số không được kiểm định; xuất chuỗi nguồn riêng, đơn vị khác nhau |
| SOL, mật độ, tăng trưởng | IMPLEMENTED theo từng nguồn | Định nghĩa lưới/đơn vị riêng, coverage và chỉ số tích phân riêng. Growth chỉ kỳ liền trước, không gán thiếu thành 0 |
| Chỉ số ảnh ngày | IMPLEMENTED theo yêu cầu hiện tại | Bands, NDVI/NDBI/MNDWI/BSI, area-weighted mean/std. Không thay thế chỉ số diện tích trong PDF |
| Phân loại 5 lớp, bản đồ phân loại, diện tích/đất chuyển đổi | DEFERRED | Người dùng hoãn, không sinh mẫu/accuracy hoặc diện tích mô phỏng |
| Cấu trúc hai package, TIFF/CSV/XLSX/DTA | IMPLEMENTED | Drive trước tiên theo tỉnh; manifest mapping về hai gốc package trên E; bảng tách nguồn/recipe |
| README/codebook, metadata nguồn | IMPLEMENTED một phần | Docs phương pháp, metadata nguồn/công thức, provenance manifest. Chưa có codebook cấp bộ dữ liệu live đã nghiệm thu và nguồn geometry thật |
| Đồng bộ về ổ E, cập nhật và ghi log | IMPLEMENTED; Windows live BLOCKED | Windows agent, volume serial+marker, task scheduler, block validation, checksum, receipt, conditional delete |
| Drive ít dung lượng / laptop tắt | IMPLEMENTED | Reservations toàn cục, hysteresis, quota tài khoản; WAITING_FOR_SPACE và resume; không hứa ghi E khi tắt |
| Sao lưu độc lập | CHƯA CÓ | Xóa Drive sau verify khiến E có thể là bản duy nhất. Không coi chuyển tệp là sao lưu thứ hai |
| Dashboard ngày/đêm | DEFERRED | Không tạo theo phạm vi hiện tại |
| 10 nhóm chạy định kỳ | IMPLEMENTED; GitHub activation BLOCKED | Matrix, global concurrency, pause, serialized controller; cần push workflow và cấu hình GitHub. Cron chỉ chạy nhánh mặc định |
