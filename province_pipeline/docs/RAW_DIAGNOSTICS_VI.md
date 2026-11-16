# Chạy lại Hà Nội 2025 không qua bộ lọc bổ sung

Ảnh chụp CSV có `DATA_STATUS=PENDING`: đây là dòng **chưa được tính**, không phải bằng chứng số liệu đã bị xóa hoặc nguồn không tồn tại. Hàng đợi trước đó ưu tiên xong TIFF đêm rồi mới tính CSV. Bộ lọc cũ còn để null chỉ số khi tỷ lệ pixel hợp lệ dưới 80%. Không thể khẳng định TIFF xám trong trình xem web là toàn NoData nếu chưa đọc pixel.

## Chạy thử lại

1. Hủy các chuỗi workflow cũ đang chạy/đang chờ để chúng không tiếp tục cập nhật bảng bằng chế độ cũ. Không xóa dữ liệu Drive hoặc marker ổ E.
2. Giữ `"pause": true` trong `PROVINCE_CONFIG_JSON` để workflow cũ trên main không xuất thêm. Không cần biến/secret mới.
3. Actions → Province satellite staging → Run workflow → branch `inspriring-newton`:
   - sample: `test_hanoi_2025`
   - processing: **`raw_source`** (mặc định mới)
   - mode: `run`
   - cycles: `20`
4. Chờ các lượt trong chuỗi; xem Summary stage. `PENDING / NOT_CALCULATED_YET` nghĩa là chưa tới/xong công việc tính chỉ số. `OK_RAW` nghĩa là đã tính từ sản phẩm chưa lọc bổ sung, **không phải đã kiểm định chất lượng**.
5. CSV trong artifact `province-indices-test_hanoi_2025`: 12 dòng mỗi file. Xem METHOD_VERSION=`v003raw`, PROCESSING_MODE=`raw_source`; không nhầm với artifact/lượt v002 cũ. Chưa chạy toàn bộ trước khi xem kết quả thử.

## Bỏ những bước nào?

`raw_source` không dùng thêm QA_PIXEL/QA_RADSAT, SCL, Cloud Score+, đệm mây, MODIS fire mask, ngưỡng số quan sát hoặc cắt nền âm VIIRS; không loại toàn bộ dòng vì độ phủ dưới 80%. Giữ các cảnh báo miền giá trị và độ phủ để người dùng kiểm tra, không tự lọc lại. Không sinh TIFF `filtered` trùng lặp trong chế độ này.

Vẫn giữ mask/NoData do chính catalog cung cấp, chọn đúng nguồn và thời kỳ, scale/offset phản xạ, phép tính chỉ số khi mẫu số hợp lệ, clipping và lưới xuất đã công bố. Ảnh ngày là median **không lọc bổ sung** của các ảnh trong năm (không lọc tháng mùa khô trong chế độ raw); CSV ngày tính từ median của riêng từng tháng. VIIRS là sản phẩm tổng hợp tháng do nhà cung cấp phát hành, không phải dữ liệu cảm biến từng đêm. Vì vậy không gọi đây là raw sensor scenes chưa xử lý.

Thống kê raw tính diện tích hợp lệ riêng từng băng. Một chỉ số không có mẫu số hợp lệ không được làm mất trung bình các băng quang học vẫn có dữ liệu. Không tạo dữ liệu cho nguồn/kỳ không có ảnh, không thay thế bằng cảm biến khác. Pixel hợp lệ bằng 0 vẫn là 0; NoData vẫn là null.

Nếu muốn so sánh, lựa chọn `quality_filtered` giữ phương pháp trước đây. Các bản có recipe hash khác nhau, không dùng lại TIFF/kết quả cũ cho phương pháp mới. Hai CSV chính khi đổi method/scope được lưu bản cũ tại Drive `_control/panel_history/`; receiver mới giữ bản local cũ tại `E:\SatelliteData\.panel_history\`. Cập nhật code receiver Windows để áp dụng cơ chế backup này. Các TIFF cũ không bị ghi đè/xóa bởi việc đổi chế độ.

## Xem TIFF đúng cách

GeoTIFF float32 nhiều băng không phải ảnh JPEG/RGB dùng cho Windows Photos hoặc trình xem TIFF web thông thường. Không chuyển giá trị khoa học về uint8 để làm cho file TIFF nhìn đẹp.

Mỗi job export có artifact **`province-previews-<group>`** trong lượt chạy chứa các file PNG và JSON của những tile đã xử lý trong lượt đó:

- PNG được stretch percentile 2–98 chỉ để hiển thị; TIFF không bị sửa số liệu.
- JSON ghi từng băng: valid_pixels, valid_pct, min/max, CRS, kích thước, NoData.
- `valid_pixels > 0` chứng minh băng đó có dữ liệu; chưa chứng minh chất lượng khoa học.
- TIFF không có pixel hợp lệ chung ở các băng cần thiết sẽ không được upload như kết quả thành công; báo `NO_VALID_PIXELS`, giữ báo cáo preview để chẩn đoán, không tự bù dữ liệu khác.

Trong QGIS: TIFF ngày chọn multiband RED/GREEN/BLUE và stretch; VIIRS chọn băng `avg_rad`, singleband gray, stretch min/max hoặc percentile. Nền ngoài ranh giới tỉnh là NoData bình thường.

Kiểm tra TIFF đã tải về ngay trên máy, **không cần EE/Drive credentials** và không sửa file gốc:

```powershell
& $python -m province_pipeline inspect-tiff `
    --path "E:\SatelliteData\duong_dan_den_file.tif" `
    --output ".province-local\inspection"
```

Thay `--path` bằng đường dẫn TIFF thực tế. Mở PNG trong `.province-local\inspection`; đọc JSON đi kèm. Nếu nguồn vẫn trống hoặc CSV FAILED, gửi TIFF thực tế, JSON chẩn đoán hoặc log job export; chỉ ảnh chụp trình xem chưa đủ để xác định nguyên nhân ảnh trống.

Giới hạn: sửa này được kiểm thử offline bằng SDK EE và TIFF fixture; chưa có truy cập trực tiếp các TIFF người dùng đang xem hoặc quyền chạy EE/Drive thật trong môi trường cloud này. Không khẳng định đã khắc phục một lỗi server/catalog cụ thể khi chưa có kết quả chạy lại.
