# Dùng ngay EE_SERVICE_ACCOUNT_JSON và RCLONE_CONF hiện có

Không cần tạo OAuth client mới hoặc tải Desktop client JSON để chạy workflow này.
Hai secret cũ vẫn nằm trong GitHub; chương trình không đọc lại chúng từ giao diện Settings,
không xuất giá trị ra log/artifact và không chuyển khóa service account về máy Windows.

## 1. Hai cách đăng nhập tách riêng

- Earth Engine: key của secret `EE_SERVICE_ACCOUNT_JSON`, project `vngis-ee-2`.
- Drive: remote trong secret `RCLONE_CONF`, mặc định tên `gdrive`, giống workflow cũ.
- Rclone tự dùng client OAuth cũ hoặc client mặc định để refresh token. Adapter gọi rclone
  cục bộ, giữ stdout riêng, đưa access token vào Drive API trong bộ nhớ; không yêu cầu
  thêm client_id/client_secret vào cấu hình hoặc ghi chúng trong code.
- Secret tồn tại chưa chứng minh còn hoạt động. `check_only` kiểm tra quyền thực tế;
  token hết hạn/bị thu hồi hoặc service account thiếu quyền phải được xử lý theo lỗi.

Service account Earth Engine không phải chủ tài khoản Drive cá nhân. Vì vậy mặc định
`export_backend=direct`: EE xử lý tile → worker tải TIFF → upload bằng tài khoản Drive của
rclone. Không gửi batch Export.toDrive của service account vào folder tài khoản người dùng.
Mỗi tile phải dưới giới hạn download 32 MB không nén và 10000 pixel mỗi chiều. Giữ
`tile_pixels=512` cho pilot. Tỉnh được chia nhiều tile, thống kê tỉnh tính từ cùng composite.

Trong chế độ direct, worker GitHub phải còn hoạt động để tải/upload lô đó. Nếu runner
bị ngắt, không có task export batch chạy nền thay worker; controller thử lại tối đa bốn
lượt khi chưa có file remote. Nếu đã có upload nhưng kết quả chưa được xác nhận, nó
chặn để kiểm tra thay vì ghi đè hoặc upload trùng.

## 2. Cấu hình GitHub — không cần secret mới

Giữ nguyên hai secret cũ trong Settings → Secrets and variables → Actions → Secrets.
Tại tab Variables, thêm `PROVINCE_CONFIG_JSON` bằng nội dung
`province_pipeline/config/example.json` rồi sửa:

- `project`: `vngis-ee-2`.
- `drive_root_id`: ID của thư mục `SatelliteStaging` trên Drive tài khoản rclone.
- `drive_staging_budget_gib`: ngân sách thực tế đã dành, phải nhỏ hơn dung lượng trống.
- `drive_safety_margin_gib`: dự phòng cho lô đang chạy và dữ liệu ngoài staging.
- `boundary_provider`: `gadm41`; `boundary_policy`: `gadm41_research`.
- `export_backend`: `direct`; `tile_pixels`: 512.
- Giữ `pause=true`, `allow_remote_delete=false` trong lần kiểm tra đầu.

Không cần `PROVINCE_GOOGLE_CREDENTIALS_JSON`, không cần upload GADM lên Drive.
Nếu remote không tên `gdrive`, thêm Variable `PROVINCE_RCLONE_REMOTE` bằng tên remote
thực tế (ví dụ `mydrive`), không có dấu hai chấm. Không đăng giá trị RCLONE_CONF vào chat.

## 3. Chạy kiểm tra trước, chưa xuất hoặc xóa ảnh

Actions → **Province satellite staging** → **Run workflow** → chọn nhánh
`inspriring-newton`, mode **check_only**. Workflow phải khả dụng trên nhánh mặc định
để nút dispatch/lịch hoạt động theo quy tắc GitHub; nếu chưa thấy workflow, tạo PR đưa
workflow/code vào nhánh mặc định, không chạy workflow cấp xã cũ thay thế.

Chế độ này:

1. Tạo file key/rclone tạm trong runner, chmod 600, xóa ở bước always cuối job.
2. Chuẩn bị GADM tự động.
3. Thực hiện probe EE Number(1), kiểm tra thư mục Drive và quota còn trống.
4. Kiểm kê nguồn ảnh, tạo artifact **province-source-inventory** chứa CSV, không credentials.
5. Không submit batch export, không upload TIFF, không xóa dữ liệu Drive.

Khi kiểm tra đạt, xem inventory rồi đặt `pause=false`, chạy mode **run**. Cấu hình
mẫu chỉ có Hà Nội năm 2024. Lượt kế tiếp hòa giải output và tạo manifest READY cho receiver.
Lịch mỗi 30 phút chạy mode run nhưng vẫn tôn trọng pause/quota. Có thể pause lại bất cứ lúc nào.
CI luôn ép backend direct khi dùng cặp secret cũ để tránh service-account Drive export.

## 4. Máy Windows chỉ cần rclone, không cần key EE

GitHub Secrets không tự có trên máy Windows và không thể xem lại giá trị đã lưu.
Nếu đã dùng rclone trên máy:

```powershell
rclone version
rclone listremotes
rclone config file
```

Các lệnh trên không in token. Ghi lại đường dẫn config và tên remote. Nếu chưa cài,
cài từ https://rclone.org/downloads/ hoặc `winget install Rclone.Rclone`, rồi mở PowerShell mới.
Nếu chưa cấu hình remote, chạy `rclone config`: tạo remote tên `gdrive`, chọn Google Drive,
để client_id/client_secret trống để dùng client mặc định của rclone, chọn quyền đủ cho
thư mục dự án và đăng nhập bằng tài khoản Drive chứa SatelliteStaging. Không cần tải OAuth JSON.

Đặt đường dẫn file local (ví dụ, dùng đúng kết quả `rclone config file`):

```powershell
$env:PROVINCE_RCLONE_CONFIG = "$env:APPDATA\rclone\rclone.conf"
$env:PROVINCE_RCLONE_REMOTE = "gdrive"
```

Dùng cấu hình local có Drive root/budget đúng như cloud, marker ổ đã đăng ký, xóa tắt.
Ví dụ nếu `$python` là đường dẫn Python bạn đã tạo ở thư mục ngoài:

```powershell
& $python -m province_pipeline --config province_pipeline/config/local.json enroll-disk
# Điền token marker được in ra vào volume_marker của local.json.
& $python -m province_pipeline --config province_pipeline/config/local.json receive --dry-run
& $python -m province_pipeline --config province_pipeline/config/local.json receive
& $python -m province_pipeline --config province_pipeline/config/local.json aggregate
```

Receiver không gọi Earth Engine, không cần EE_SERVICE_ACCOUNT_JSON. Nếu chỉ muốn chạy
inventory EE trên Windows, cần một key được cấp riêng và lưu an toàn local qua
`PROVINCE_EE_CREDENTIALS`; không trích xuất khóa GitHub Secret để làm việc đó.

Đăng ký task tự chạy sau khi pilot đạt:

```powershell
.\scripts\windows\Register-SatelliteTask.ps1 `
  -Repo (Get-Location).Path `
  -Config (Resolve-Path province_pipeline/config/local.json).Path `
  -RcloneConfig $env:PROVINCE_RCLONE_CONFIG `
  -Remote "gdrive" `
  -Python $python
```

Sau khi kiểm tra dữ liệu tải về mới bật local `allow_remote_delete=true` nếu muốn.
Việc xóa vẫn cần checksum/receipt/ETag, không giảm kiểm tra do đổi phương thức đăng nhập.
Khi laptop tắt hoặc ổ E không có, Drive tích lũy đến ngưỡng rồi controller chờ.

## 5. Khả năng tương thích

- Luồng batch/user OAuth cũ vẫn có trong CLI cho cấu hình nâng cao, qua
  `PROVINCE_GOOGLE_CREDENTIALS` và backend batch. Không bắt buộc dùng ở workflow mới.
- Backend có trong job identity để không trộn report/task của batch và direct.
- PowerShell receiver/task vẫn nhận `-Credentials` kiểu cũ hoặc `-RcloneConfig` kiểu mới;
  phải chọn một, không cùng lúc.
- JSON cấu hình UTF-8 có BOM từ Windows PowerShell 5.1 được hỗ trợ.
- Live pilot vẫn cần chạy trên GitHub bằng hai secret thực tế; test offline không xác
  nhận token hoặc service account còn hoạt động. Không có dữ liệu vệ tinh thật được tải
  hay xóa chỉ từ việc sửa mã/push code.

## 6. Khi bước rclone preflight thất bại

Bản cũ chỉ báo chung “Rclone authentication failed”; thông báo đó không đủ để kết
luận token hết hạn. Bản mới ghi `rclone_config_check` (chỉ trạng thái cấu trúc) và
`rclone_command_failed` với mã lỗi cố định. Không in stderr/stdout/config/token gốc.

| Mã lỗi | Hành động |
|---|---|
| RCLONE_REMOTE_NOT_FOUND | Kiểm tra tên remote bằng `rclone listremotes` ở máy có cấu hình; đặt Variable PROVINCE_RCLONE_REMOTE đúng tên, không dấu hai chấm |
| RCLONE_CONFIG_FORMAT | Secret RCLONE_CONF phải là cấu hình INI đầy đủ có `[gdrive]` hoặc tên remote thật; không phải chỉ token JSON, Client ID, đường dẫn file hay chuỗi có newline bị escape |
| RCLONE_TOKEN_REVOKED | Google trả invalid_grant; reconnect remote trên máy tin cậy rồi cập nhật RCLONE_CONF qua GitHub Secrets, không gửi token qua chat |
| RCLONE_CLIENT_REJECTED | Kiểm tra client cũ bị xóa/sai thông tin; không mặc định tạo client mới trước khi xem cấu hình |
| RCLONE_TOKEN_MISSING | Remote thiếu OAuth token; đăng nhập remote bằng rclone cục bộ, không cần Desktop JSON mới nếu dùng client mặc định |
| RCLONE_SCOPE_DENIED | Token thiếu scope; xác thực lại với quyền Drive phù hợp |
| RCLONE_DRIVE_API_DISABLED | Kiểm tra Drive API trong project của OAuth client thực tế |
| RCLONE_RATE_LIMIT / RCLONE_NETWORK / RCLONE_TIMEOUT | Kiểm tra quota/kết nối, không đổi secret chỉ vì lỗi tạm thời |
| RCLONE_UNKNOWN | Chưa phân loại được; kiểm tra lỗi tại máy tin cậy, không dán cấu hình hoặc output chứa credentials |

Sau khi push bản sửa vào nhánh phát triển, mở Actions → Province satellite staging →
**Run workflow**, chọn **inspriring-newton**, mode **check_only**. Không chỉ bấm
Re-run jobs của lượt cũ vì lượt cũ vẫn dùng commit cũ. Merge PR vào main sau khi
kiểm tra bản sửa; lịch trên main chưa dùng bản nhánh phát triển khi chưa merge.

Nếu gặp `Projection: The CRS of a map projection could not be parsed`, dùng bản
mới có WKT đầy đủ và chạy một lượt mới trên nhánh `inspriring-newton`, mode
`check_only`. Tìm dòng `Earth Engine projection and exact-grid request probe: PASS`.
Không đổi `crs` trong cấu hình sang hệ khác để che lỗi; lưới tỉnh vẫn là EPSG:6933.
Nếu probe thất bại, gửi lỗi ở bước preflight trước khi tiếp tục chạy dữ liệu thật.

## 7. Bố trí đúng hai package và sắp xếp lô cũ

Xem [DIRECTORY_LAYOUT.md](DIRECTORY_LAYOUT.md). Tỉnh là con trực tiếp của các nhóm dữ liệu; Drive và E cùng layout. Mode organize_only yêu cầu pause=true, giữ nguyên file ID và dữ liệu, không xóa tệp. Merge code layout mới vào main trước khi bật lại lịch, tránh code cũ đối soát sai thư mục chứa nhiều TIFF.

Ảnh hiện dùng layout 3: TIFF nằm trực tiếp trong thư mục tỉnh. Năm/tháng nằm trong tên tệp; mode organize_only chuyển cả các ảnh đang nằm trong thư mục năm/tháng cũ mà không tải lại.

## 8. Chạy riêng inspriring-newton, chưa merge main

Sau khi organize_only đạt, vẫn giữ pause=true trong cấu hình hiện tại. Vào Settings
→ Secrets and variables → Actions → **Variables** (không phải Secrets):

1. Sao chép đầy đủ nội dung PROVINCE_CONFIG_JSON vào biến mới **PROVINCE_BRANCH_CONFIG_JSON**.
2. Kiểm tra biến mới đủ cấu hình rồi xóa biến cũ **PROVINCE_CONFIG_JSON**. Không xóa EE_SERVICE_ACCOUNT_JSON hoặc RCLONE_CONF.
3. Đợi các lượt workflow đang chạy kết thúc; lịch main về sau sẽ bỏ qua controller do không còn biến cấu hình cũ. Main không đọc PROVINCE_BRANCH_CONFIG_JSON.
4. Sửa pause=false trong **PROVINCE_BRANCH_CONFIG_JSON**, giữ allow_remote_delete=false cho pilot.
5. Actions → Province satellite staging → Run workflow → chọn branch **inspriring-newton**, mode **run**. Không Re-run lượt cũ vì nó dùng commit cũ.

Mã nhánh ưu tiên cấu hình branch khi chạy đúng inspriring-newton; mã main (cũ hoặc
mới) chỉ dùng PROVINCE_CONFIG_JSON. Cặp secrets Google/rclone và staging root giữ
nguyên. Không cần cập nhật config local trên Windows chỉ vì đổi tên Variable GitHub.

Giai đoạn này chạy nhánh qua workflow_dispatch thủ công; schedule GitHub chỉ xuất
phát từ default branch và main đang được bỏ qua. Không hứa nhánh tự chạy định kỳ
24/24 khi chưa có bộ lập lịch cho nhánh. Khi đã quyết định merge, đưa cấu hình về
PROVINCE_CONFIG_JSON để bật lịch main; xóa biến branch nếu không còn cần.
