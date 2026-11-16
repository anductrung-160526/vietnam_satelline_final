> **Luồng mới theo yêu cầu CSV gộp và 2 chế độ thử/toàn bộ:** xem [RUN_PROFILES_VI.md](RUN_PROFILES_VI.md). Các bước pilot/source-panel bên dưới là hướng dẫn cũ; không dùng để cấu hình mẫu v2.

# Thiết lập và chạy pilot

Cây thư mục chuẩn và chuyển dữ liệu cũ: [DIRECTORY_LAYOUT.md](DIRECTORY_LAYOUT.md). Thư mục tỉnh nằm bên trong nhóm dữ liệu của từng package, không bọc bên ngoài package.

## 1. Những gì cần chuẩn bị

- Project được đăng ký Earth Engine, có quyền/quota cho công việc dự kiến; xem điều kiện sử dụng và chi phí hiện hành.
- Một tài khoản Google có Drive trống và khả năng truy cập project Earth Engine.
- Bộ ranh giới 63 tỉnh tại năm 2024 và crosswalk sang mã thống kê. Repo chỉ cung cấp danh mục mã/nhóm, không giả định đã có bộ ranh giới được xác nhận.
- Laptop Windows, ổ cứng ngoài có dung lượng trống, Python 3.11+; cài `python -m pip install -r province_pipeline/requirements.txt` trong virtualenv.

Không gửi khóa/refresh token vào chat. File cấu hình local và ranh giới riêng đã được gitignore; credentials nên đặt ngoài repo và hạn chế quyền đọc.

## 2. Chuẩn bị địa giới tự động (GADM cấp tỉnh)

Không cần QGIS với cấu hình mẫu mới. Tại thư mục repo, chạy:

```powershell
Copy-Item province_pipeline/config/example.json province_pipeline/config/local.json
python -m province_pipeline --config province_pipeline/config/local.json prepare-gadm
python -m province_pipeline --config province_pipeline/config/local.json validate
```

Nếu đã có `local.json`, **không chép đè**. Giữ nguyên project/Drive/budget và thêm:

```json
"boundary_provider": "gadm41",
"boundary_policy": "gadm41_research"
```

Lệnh tải GADM 4.1 Việt Nam cấp 1 từ UC Davis qua HTTPS, xác nhận checksum ZIP và JSON đã pin, đối chiếu 63 tỉnh bằng bảng GID+tên chính xác trong `province_pipeline/data/gadm41_province_crosswalk.csv`, gắn `ma_tinh` chuỗi và tạo tự động:

```text
province_pipeline/config/boundaries.geojson
province_pipeline/config/boundaries.metadata.json
```

Các file sinh ra nằm trong checkout nhưng gitignored; repo chứa công cụ tái tạo và crosswalk, không phát hành lại toàn bộ geometry GADM. Xem điều kiện sử dụng nguồn tại https://gadm.org/license.html. GitHub Actions gọi `sync-boundaries`, tự tải và chuẩn hóa cùng bộ GADM theo checksum; **không cần upload hai file lên Drive hoặc điền hai boundary file ID** khi dùng `boundary_provider=gadm41`. Chạy lại xác minh file hiện có, không ghi đè dữ liệu người dùng. Nếu chỉ có một file hoặc checksum sai, lệnh dừng để bạn xử lý, không xóa tự động.

Metadata ghi ngày thành viên archive `2022-07-18`, không gán ngày pháp lý 2024. Đây là footprint GADM cho nghiên cứu với danh mục 63 tỉnh trước sáp nhập; đối chiếu mã đã kiểm tra không đồng nghĩa xác nhận địa giới chính thức năm 2024. Bộ nguồn được giữ nguyên hình học, không tự thêm đảo/vùng tranh chấp hoặc chứng nhận đủ toàn bộ lãnh thổ; kiểm tra footprint phù hợp mục tiêu trước khi tính các tỉnh ven biển. Bounds thực tế được kiểm tra khi chuẩn bị dữ liệu; xem `province_pipeline/data/README.md`.

Nếu có bộ chính thức 2024 riêng, đặt `boundary_provider=drive`, `boundary_policy=official_2024`, cung cấp GeoJSON đủ 63 tỉnh WGS84 với `properties.ma_tinh`, nguồn/version/date/code_reference/crosswalk_verified/SHA256 trong metadata. Upload hai file lên Drive và điền `boundaries_drive_id`, `boundary_metadata_drive_id`. SHA256 có thể tính bằng `Get-FileHash -Algorithm SHA256 <file>`. Chỉ đặt crosswalk_verified=true sau khi đối chiếu thật. Không thay GADM bằng nguồn khác nhưng giữ metadata GADM; loader phân biệt hai chế độ.

## 3. Dùng hai secret hiện có — không cần tải OAuth JSON

Workflow đã dùng lại `EE_SERVICE_ACCOUNT_JSON` cho Earth Engine và `RCLONE_CONF`
cho Drive. Không cần tạo Desktop OAuth client hoặc thêm secret đăng nhập chung.
Xem hướng dẫn từng bước tại [REUSE_EXISTING_SECRETS_VI.md](REUSE_EXISTING_SECRETS_VI.md).

GitHub chỉ cần thêm Variable `PROVINCE_CONFIG_JSON`; remote mặc định `gdrive`.
Chạy mode `check_only` trước để kiểm tra quyền và nguồn ảnh mà chưa xuất/xóa dữ liệu.
Windows receiver dùng rclone config riêng trên máy, không cần key Earth Engine.

## 4. Cấu hình pilot

Sao chép `province_pipeline/config/example.json` thành `local.json`, giữ một tỉnh/năm, 512 pixel/tile và 2 lượt transfer toàn cục. Điền project, Drive root ID (thư mục riêng `SatelliteStaging`), budget và safety margin thực tế. Hai boundary file ID chỉ cần khi dùng provider `drive`.

Ví dụ **chỉ khi đã đo còn đủ dung lượng**: dành 5 GiB staging, margin 0.5 GiB, ngưỡng cao 0.65/thấp 0.30. Các giá trị này không phải ước lượng dung lượng tài khoản của bạn. Reservation dựa vào pixel×band×4 byte×2 + overhead, không trông chờ nén. Tài khoản còn trống phải đủ cả reserved+margin. Khi thiếu chỗ → WAITING_FOR_SPACE; không xóa dữ liệu người dùng khác.

```powershell
python -m province_pipeline --config province_pipeline/config/local.json validate
python -m province_pipeline --config province_pipeline/config/local.json sync-boundaries
# Kiểm kê nguồn ở mode check_only trên GitHub nếu key EE chỉ có trong GitHub Secrets.
# Lệnh inventory local chỉ dùng khi bạn có credentials EE riêng được cấp cho máy này.
```

Review `.province-local/source_inventory.csv`: AVAILABLE mới được xuất; PARTIAL/UNAVAILABLE không biến thành số 0. Xem METHODS.md về VIIRS 2013/Sentinel-2 2015–2016 và việc VIIRS annual là tự tổng hợp từ tháng.

Sau khi kiểm tra, đặt `pause=false`. Đặt JSON cấu hình cloud (không credentials) vào Actions Variable `PROVINCE_CONFIG_JSON`. Giữ `allow_remote_delete=false` và không đưa marker ổ đĩa cá nhân lên cấu hình cloud nếu không cần. Pipeline tính config hash cho plan/worker; các job phải dùng cùng cấu hình.

Workflow trong nhánh phát triển cần được push để GitHub thấy. Chạy manual với đúng ref `inspriring-newton` khi workflow khả dụng; lịch schedule chỉ hoạt động từ nhánh mặc định của repository theo quy tắc GitHub, không tự chạy định kỳ chỉ vì tồn tại ở nhánh này. Chưa merge/push thì chỉ có mã local, không có job GitHub đang chạy.

## 5. Chạy Actions và theo dõi

Run workflow **Province satellite staging**, chọn **check_only** trước, sau khi đạt chọn **run**. Controller tạo folder tỉnh trước, cấp chỗ và lưu state; matrix 10 nhóm chỉ thực hiện phần được cấp. Backend direct tải tile từ EE rồi upload bằng tài khoản rclone ngay trong worker; không có batch export tiếp tục chạy nền sau khi runner kết thúc. Lượt schedule/manual sau (mỗi 30 phút theo UTC trong workflow) hòa giải và tạo manifest READY. Có thể gọi manual để giảm thời gian chờ; concurrency ngăn chồng lượt. Chưa có vòng polling liên tục nên không hứa phản hồi ngay khi có file.

`_control/state.json` là nguồn tiến độ chính; manifests/reports/receipts nằm ở các thư mục riêng. Controller single-writer nhờ concurrency của **một workflow trong một repo**. Không khởi chạy controller thứ hai từ máy khác hay workflow khác. Không sửa/xóa state khi workflow đang chạy.

Pause: đặt `pause=true` trong Actions Variable. Lượt mới không cấp thêm export; task cũ vẫn được hòa giải. Pause không hủy transfer đã bắt đầu trong worker; chúng đã có reservation. Quota/lỗi HTTP được xử lý hữu hạn; `BLOCKED_AMBIGUOUS` giữ chỗ để tránh submit trùng. Xem EE Task Manager theo description `province_<job_id>` và file ID trước khi sửa lỗi. Không xóa report/state để ép chạy lại khi task chưa rõ kết quả.

Đối với task thất bại đã xác nhận: giữ log, kiểm tra và xử lý chính xác file dở còn lại, sửa nguyên nhân; dùng algorithm version mới để tạo job mới có truy vết. Không có nút retry hàng loạt xóa dấu vết. Không hứa GitHub miễn phí: xem hạn mức runner và điều kiện sử dụng hiện hành.

## 6. Đăng ký ổ E trên Windows

Chỉ chạy bước này trên máy có ổ ngoài, không chạy trong Linux cloud:

```powershell
python -m province_pipeline --config province_pipeline/config/local.json enroll-disk
```

Lệnh tạo marker UUID ở gốc volume, đọc volume serial và in token marker (không phải credential). Điền token vào `volume_marker` của **cấu hình local**. Agent yêu cầu cả marker và serial khớp, root tồn tại; nếu đổi chữ ổ đĩa cần sửa `local_root`. Nếu ổ bị tháo/đầy, nguồn Drive được giữ lại.

```powershell
python -m province_pipeline --config province_pipeline/config/local.json receive --dry-run
python -m province_pipeline --config province_pipeline/config/local.json receive
python -m province_pipeline --config province_pipeline/config/local.json aggregate
```

Kiểm tra TIFF, bảng, receipts dưới E. `aggregate` xuất CSV/XLSX/DTA theo nguồn và recipe, giữ mã tỉnh chuỗi `01`; chưa ghép DN và radiance. Metadata chứa công thức, citations và đơn vị. Manifest local giữ đầy đủ provenance ngay cả khi xóa ảnh trên Drive.

**Chỉ sau khi kiểm tra pilot**, đặt local `allow_remote_delete=true`, chạy lại `receive`. Agent xác nhận receipt trên Drive và kiểm tra lại dữ liệu local, rồi xóa vĩnh viễn từng file ID đã verify bằng điều kiện ETag. Nếu API không cung cấp/hỗ trợ ETag, xóa sẽ bị chặn; không bỏ kiểm tra để cho qua. Không empty-trash toàn tài khoản. File nhỏ control/manifest được giữ, folder export rỗng chưa tự dọn. Không xóa tệp local.

## 7. Tự động khi bật máy

Ví dụ dùng PowerShell trên Windows (đổi đường dẫn cho đúng):

```powershell
.\scripts\windows\Register-SatelliteTask.ps1 `
  -Repo "C:\Projects\vietnam_satelline_final" `
  -Config "C:\Projects\vietnam_satelline_final\province_pipeline\config\local.json" `
  -RcloneConfig "$env:APPDATA\rclone\rclone.conf" `
  -Remote "gdrive" `
  -Python "C:\Projects\vietnam_satelline_final\.venv\Scripts\python.exe"
```

Task chạy khi đăng nhập và lặp mỗi 5 phút, IgnoreNew khi lần cũ còn chạy; không chứa secret trong command line, chỉ có đường dẫn file. Theo chính sách tài khoản Windows, có thể cần chọn lại người dùng/quyền trong Task Scheduler. Xem Last Run Result và chạy `Receive-Satellite.ps1` trực tiếp để xem lỗi. Phần Windows chưa được kiểm tra trên ổ E thật từ môi trường cloud.

Khi laptop tắt/Sleep không tải được. Lúc bật và đăng nhập lại, task nhận các lô READY; Drive giảm dung lượng rồi controller cấp tiếp trong lượt sau. GitHub worker có thể tải/upload khi laptop tắt; khi Drive gần đầy pipeline sẽ chờ đúng phương án đã chọn.

## 8. Mở rộng sau pilot

Đầu tiên dùng 1 tỉnh/1 kỳ ngày và đêm, kiểm tra từ submit đến receipt và xóa một lô. Sau đó 2–3 nhóm, thử ngắt mạng/tháo ổ an toàn/restart giữa chừng, rồi mới mở đủ 63 tỉnh và 2004–2025. Đặt `province_codes` bằng danh sách mã từ manifest, years = 2004..2025, products theo nhu cầu. `max_active_exports` tăng chỉ sau khi đo quota, Drive và tốc độ tải.

Không đổi source/mask/season/ranh giới nhưng giữ nguyên phiên bản khoa học: algorithm version và recipe hash dùng phân biệt kết quả. Inventory source IDs được snapshot và worker dùng chính IDs ấy; không tự chọn lại cảnh mới sau khi đã cấp job. Các bảng tổng hợp tách recipe để tránh trộn kết quả khác phương pháp.
