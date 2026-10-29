# Luồng 07 — dữ liệu Việt Nam cấp quốc gia năm 2024

Nhánh `vngis-ee-07` chạy **một vùng Việt Nam**, không lặp theo tỉnh/xã và không lấy trung bình các thống kê cấp tỉnh. `flow07_national.py` gộp hình học trong `projects/vngis-ee-2/assets/communes_l3` thành một feature quốc gia rồi tính chỉ số trực tiếp trên vùng đó. Phạm vi lãnh thổ theo đúng các đa giác có trong asset nguồn; không tự bổ sung vùng biển/đảo ngoài dữ liệu.

Project thực thi là `vgis-ee-07`. Mã phương pháp: `NATIONAL_MONTHLY_2024_v1`. Giữ năm **2024** của pipeline gốc; chưa mở rộng 2004–2025.

## Chạy tự động

1. Settings → Secrets and variables → Actions: thêm `EE_SERVICE_ACCOUNT_JSON_07` chứa JSON khóa service account chạy project 7. Giữ secret `RCLONE_CONF` hiện có, remote `gdrive` có quyền ghi Drive. Không đưa JSON khóa vào code/chat.
2. Project `vgis-ee-07` cần đăng ký Earth Engine, bật API, còn quota và cấp service account quyền Earth Engine phù hợp cùng Service Usage Consumer. Service account cần Reader trên asset nguồn (quyền public Reader hiện có cũng đáp ứng).
3. Actions → workflow file **vngis-2024.yml** → Run workflow → nhánh **vngis-ee-07**. Tên hiển thị có thể vẫn là tên workflow trên main.
4. `pilot`: **tháng 1/2024 trên toàn Việt Nam**, cùng độ phân giải full; không phải chỉ vài xã/tỉnh. `full`: **12 tháng 2024 trên toàn Việt Nam**. Không cần nhập tỉnh, số xã hay số worker. Luồng dùng một yêu cầu EE cùng lúc.
5. Khi hết thời lượng khoảng 5 giờ 15 phút, workflow tự nối cùng nhánh/mode. Các ô đã upload thành công được giữ trên Drive và bỏ qua ở lượt sau. Lỗi quyền, hết Drive hoặc lỗi khác báo thất bại, không đánh dấu hoàn tất giả; sửa nguyên nhân rồi Run workflow lại cùng mode.

## Kết quả

Drive root `VNGISDash_2024_FLOW07_NATIONAL` hoặc `VNGISDash_2024_FLOW07_NATIONAL_PILOT`:

```text
National/DAY/2024/01/tiles/*.tif
National/DAY/2024/01/VNM_DAY_202401.vrt
National/DAY/2024/01/complete.json
National/NIGHT/2024/01/tiles/*.tif
National/NIGHT/2024/01/VNM_NIGHT_202401.vrt
CSV/day_indices.csv
CSV/night_indices.csv
_control/national_progress.json
```

Full có thêm tháng 02–12. CSV có `LEVEL=national`, `COUNTRY_CODE=VNM`, `COUNTRY_NAME=Viet Nam`; mỗi tháng có dữ liệu là một quan sát quốc gia. Tên trường diện tích được đổi thành `NATIONAL_AREA_HA`. Các trường hành chính cũ chỉ dùng nội bộ khi gọi hàm dùng chung, không xuất ra CSV quốc gia.

Ảnh toàn quốc rất lớn nên **không ghép thành một TIFF khổng lồ trên GitHub runner**. Tải ô 512 pixel trên cùng lưới cố định, kiểm tra lưới/số băng, upload ngay từng ô để giữ dung lượng runner thấp. Ô quá lớn được chia nhỏ tiếp; không giảm độ phân giải. Chỉ tạo VRT và complete.json sau khi đủ mọi ô phủ vùng quốc gia. Các ô ngoài vùng đã clip là NoData -9999.

Tải **cả thư mục tháng gồm VRT và tiles**, giữ nguyên vị trí tương đối, rồi mở VRT trong QGIS để xem như một ảnh quốc gia. VRT không phải ảnh xem trước và không tự chứa pixel; chỉ tải riêng VRT sẽ không xem được. Thư mục đang tải dở có thể có tiles nhưng chưa có VRT/complete.json.

Pilot/full có root riêng, không tái sử dụng ô giữa hai mode. Root NATIONAL tách khỏi đầu ra FLOW07 cấp xã/tỉnh trước đó; không xóa hay sửa dữ liệu cũ.

## Phương pháp và giới hạn

Tái sử dụng các hàm khoa học trong `vngis_2024.py`: Sentinel-2 SR tháng, mask QA60, các chỉ số phổ và reducers mean/stdDev ở nominal 50 m; TIFF ngày 10 băng ở nominal 20 m; VIIRS tháng avg_rad/cf_cvg ở nominal 500 m và reducers ánh sáng như code gốc. TIFF Float64, không lượng tử hóa int16. EPSG:4326 với bước góc quy đổi từ nominal scale, không phải mọi pixel đều có diện tích chính xác 20x20 m.

Cửa sổ fallback ảnh ngày, lựa chọn nguồn VIIRS, ngưỡng sáng, proxy và cách tính tăng trưởng giữ nguyên code gốc. Đặc biệt, giới hạn ngày cuối tháng exclusive và hạn chế QA60 của code gốc vẫn còn; không gọi đây là dữ liệu đã được kiểm định hoặc hiệu chuẩn. CSV không có hàng ở tháng nguồn thực sự rỗng; báo cáo `complete_with_gaps` ghi các ảnh thiếu, không điền zero thay dữ liệu thiếu.

Dữ liệu toàn quốc 20 m × 10 băng × 12 tháng có thể rất lớn và vượt dung lượng Drive/quota. Tải ô giúp tiếp tục và giới hạn RAM/đĩa runner, không làm giảm tổng dữ liệu hay tăng quota. Kiểm tra đủ dung lượng Drive trước khi chạy full; luồng này chưa tự nhận vào ổ E hoặc xóa staging sau khi nhận.

## Dừng và tiếp tục

Tạo `STOP` ở gốc nhánh `vngis-ee-07`, hoặc `_control/STOP` trong root Drive tương ứng. Workflow kiểm tra STOP trên đúng nhánh, downloader kiểm tra STOP giữa các ô. Xóa STOP rồi Run workflow cùng mode để tiếp tục. Không đổi asset/method/root hoặc xóa tiles/complete.json giữa một chuỗi tải.

Đã kiểm tra bằng dữ liệu giả lập: một feature quốc gia, lưới/ô, chia nhỏ, tiếp tục từ Drive, lỗi upload và pixel/NoData của VRT, cùng các kiểm thử dừng/tiếp tục pipeline dùng chung. Chưa xác minh tải thực tế với credentials/quota của bạn.
