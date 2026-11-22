# Kết quả chạy sửa dữ liệu v9 trên Windows — 22/11/2026

Đã nhận fix_report.json từ người dùng. Báo cáo xác nhận published=true, đã backup và cập nhật database app. Đây là đối chiếu báo cáo tổng hợp, chưa mở trực tiếp database/TIFF trên máy Windows hoặc đọc lại từng dòng CSV sau sửa.

## Kết quả tổng hợp

| Hạng mục | Kết quả theo báo cáo |
|---|---:|
| Ảnh tính diện tích | 4.095 |
| COG phân lớp dùng lại | 4.095 |
| Diện tích độ phủ vượt 100% | 0, trước sửa 3.135 |
| Thiếu diện tích tự nhiên tỉnh | 0 |
| Sai lệch tổng diện tích lớn nhất | 7,275957614183426 × 10⁻¹² km² |
| Ảnh tháng đã đối chiếu raw/filtered | 3.780 |
| Khớp raw và quy tắc lọc | 3.723 |
| Raw không có quan sát sạch mây hợp lệ | 57 |
| Ảnh tháng/năm cần xuất bản sửa pixel | 0 / 0 |
| Dòng GRDP đầu vào | 1.260 |
| Dòng Night Economy | 8.820 = 1.260 năm + 7.560 tháng |
| Mẫu chung hai mô hình | 315 tỉnh–năm |
| Mô hình so_sanh / hien_hanh | Cả hai khớp thành công |
| Ảnh ghép được báo cáo chất lượng D v3 | 4.095; không có ảnh thiếu liên kết |
| Chỉ số năm / tháng nạp app | 315 / 3.780 |
| Dòng dictionary nạp app | 12.915 = 4.095 Night Data + 8.820 Night Economy |

Phép đo mới là pixel_polygon_intersection_epsg6933_v1, STATS_VERSION=9. Toàn bộ COG được dùng lại vì nguồn/ngưỡng vẫn phù hợp; diện tích được tính lại độc lập theo phần giao polygon. Không cần thay pixel bức xạ để sửa lỗi cộng cả ô giao biên.

## 57 tháng thiếu là giới hạn nguồn

monthly_repaired=0 không phải chương trình bỏ qua lỗi. 3.723 ảnh tháng khớp quy tắc FILTER; 57 ảnh còn lại có chẩn đoán NO_CLOUD_FREE_OBSERVATIONS trong ảnh raw, không có ca báo mất mask hoặc sai quy tắc lọc cần phục hồi. annual_repaired=0 cho biết ảnh median năm cũng không cần tái tạo pixel theo phép đối chiếu hiện tại.

Giữ 57 mốc này là thiếu dữ liệu, không thay SOL bằng 0 hoặc nội suy. Muốn lấp các mốc phải có nguồn quan sát hợp lệ bổ sung, không thể khôi phục tín hiệu chưa có trong file raw bằng sửa công thức. Báo cáo năm min/max/trung bình số tháng hợp lệ vẫn cần xem để diễn giải chất lượng ảnh median năm; không coi ảnh năm có dữ liệu là đủ 12 quan sát tại mỗi pixel.

## Các số không phải lỗi mới

- empty_image_result_rows=114 là 57 ảnh thiếu × hai cơ sở giá, không phải 114 ảnh bị mất.
- missing_image_result_rows=630 là hai giá của 315 tỉnh–năm 2015–2019 chưa có ảnh trong manifest demo 2020–2024; GRDP vẫn giữ dòng, không bị xóa.
- missing_grdp_input_values=1 phù hợp với điểm thiếu Bắc Giang giá hiện hành 2015 đã xác nhận từ nguồn; cần CSV để đối chiếu chính dòng, không tự điền.
- missing_population_rows=8.820: file kinh tế chưa có dân số, nên giữ trống chỉ số trên đầu người.
- recovery.database_changed=false chỉ nói riêng bước đối chiếu/sửa ảnh; published=true ở cấp workflow xác nhận snapshot cuối đã cập nhật database app.

## Mức nghiệm thu và việc còn lại

Đã có bằng chứng chạy thành công toàn workflow trên dữ liệu thật: sửa cách tính diện tích, xác định nguyên nhân tháng rỗng theo raw, tính lại D/E và xuất bản database. Chưa có hệ số alpha/beta/R² trong fix_report nên chưa đánh giá chất lượng thống kê hoặc kết luận quan hệ kinh tế.

Cần kiểm tra calculation_models.csv, annual_observation_support.csv và vài dòng CSV/ảnh sau sửa để xác nhận hệ số, độ đầy đủ quan sát, trường diện tích và hiển thị Windows. Không biến việc hết tỷ lệ vượt 100% thành khẳng định ranh giới GADM là ranh giới pháp lý hoặc mọi dữ liệu kinh tế đã chính xác. Phần F tiếp tục đối chiếu app → CSV → raster.

Thư mục kết quả: E:\SatelliteData\_demo_fix\20261122_180611_662323.

- Mô hình: indices/calculation_models.csv.
- Báo cáo nguồn tháng: repair/monthly_recovery_audit.csv.
- Độ đầy đủ quan sát năm: repair/annual_observation_support.csv.
- Báo cáo diện tích: E:\SatelliteData\cog\light_classes\20261122_181806_016650\validation_report.json.

SHA-256 của fix_report.json đã nhận: `d0115576b094a6a675715fae98d07b3d116fdf77943b31c05c1a7b42b13a571f`.
