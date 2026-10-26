> **Đã thay thế:** hướng dẫn mới (cấu trúc thư mục chung, 6 luồng song song, thứ tự ảnh đêm → ảnh ngày → ảnh trung gian → bảng) nằm ở [HUONG_DAN_CHAY_LOCAL.md](HUONG_DAN_CHAY_LOCAL.md). Tài liệu dưới đây chỉ để tham khảo.

# Chạy trực tiếp vào ổ E, bỏ hoàn toàn Google Drive

Luồng mới chạy **trên laptop Windows**:

```text
Earth Engine → file tạm trên E → kiểm tra → TIFF/CSV chính thức trên E
```

Không dùng Drive API, rclone, upload, download từ Drive hoặc bước xóa dữ liệu Drive. Không cần cài self-hosted runner: chạy PowerShell trực tiếp là đủ. Máy phải bật, có mạng, không Sleep và ổ E được cắm. Giữ nguyên project `vngis-ee-2`, sáu phạm vi tỉnh, pilot/full, ưu tiên ảnh đêm, CSV rồi ảnh ngày, một TIFF tỉnh/thời kỳ và không xuất PNG.

**Workflow GitHub cũ vẫn chạy qua Drive.** Để bỏ Drive, dùng lệnh local dưới đây, không bấm Run workflow cũ. Nếu muốn điều khiển local bằng GitHub sau này thì cần tự cài self-hosted runner trên laptop; thay đổi hiện tại không tự cài runner hoặc sửa máy Windows từ xa.

## 1. Dừng luồng Drive cũ

- Trên GitHub Actions, hủy các run cũ đang chạy/chờ, tránh cùng lúc tiêu thụ quota và tiếp tục upload Drive.
- Trên PowerShell, dừng tác vụ nhận Drive nếu đã cài:

```powershell
$task = Get-ScheduledTask -TaskName "Satellite-Drive-To-ExternalDisk" -ErrorAction SilentlyContinue
if ($task) {
    Stop-ScheduledTask -TaskName $task.TaskName
    Disable-ScheduledTask -TaskName $task.TaskName
}
```

Không xóa dữ liệu Drive/E hoặc marker. Khi muốn dùng luồng Drive cũ trở lại, Enable-ScheduledTask và Start-ScheduledTask. Receiver mới cũng tự bỏ qua thư mục nhánh có state ownership local để tránh ghi đè kết quả trực tiếp.

## 2. Cập nhật mã đúng nhánh

Dùng checkout/ZIP mới của `vngis-tinh-001-011` để thử Hà Nội. Giữ `province_pipeline/config/local.json` cũ nếu đã có; không ghi đè volume_marker đã đăng ký. Mở PowerShell tại thư mục repo có `task_pipeline/local.py` và `scripts/windows/Run-Task123-Local.ps1`.

Python dưới đây là đường dẫn venv bạn từng dùng; nếu đã đổi thì sửa lại đúng file python.exe hiện tại:

```powershell
$python = "C:\Users\AD\Downloads\vietnam_satelline_final-inspriring-newton\.venv\Scripts\python.exe"
Test-Path $python
Test-Path "E:\"
Test-Path ".\task_pipeline\local.py"
& $python -m pip install -r .\province_pipeline\requirements.txt
```

Ba Test-Path phải True. Không cần đăng nhập/cấu hình rclone. Thiết lập GADM được thực hiện tự động nếu thiếu, có kiểm tra checksum và crosswalk như bản cloud.

## 3. Đăng nhập Earth Engine một lần trên máy Windows

```powershell
& $python -m task_pipeline.local authenticate
```

Đăng nhập tài khoản Google đã có quyền dùng project `vngis-ee-2` trong trình duyệt được mở. Command kiểm tra Earth Engine và in PASS, không truy cập Drive. OAuth chỉ yêu cầu Earth Engine/cloud-platform.

Nếu có service-account JSON hợp lệ lưu **ngoài repo**, có thể bỏ bước OAuth và truyền `-EeKey "C:\duong_dan_bao_mat\ee-key.json"` vào script chạy bên dưới. Không gửi key/token vào chat hoặc commit vào Git.

## 4. Chạy pilot trực tiếp

```powershell
& .\scripts\windows\Run-Task123-Local.ps1 `
    -Mode pilot `
    -Python $python `
    -Root "E:\SatelliteData"
```

Pilot = toàn giai đoạn 2004–2025 của tỉnh đầu trong file range của checkout đó. Nhánh 001–011 là Hà Nội. Không phải chỉ năm 2025. Để chạy đầy đủ nhóm:

```powershell
& .\scripts\windows\Run-Task123-Local.ps1 `
    -Mode full `
    -Python $python `
    -Root "E:\SatelliteData"
```

Lệnh CLI tương đương (cũng không dùng Drive):

```powershell
& $python -u -m task_pipeline.local run --mode pilot --root "E:\SatelliteData"
```

Giữ PowerShell đang chạy; Ctrl+C dừng có trật tự khi yêu cầu EE hiện tại kết thúc. Chạy lại đúng lệnh để tiếp tục các công việc chưa xong. Không có giới hạn runner GitHub 5 giờ 15 phút hoặc ngân sách Drive 20 GB trong chế độ local; giới hạn là dung lượng trống của E và quota EE. Không hứa sẽ lấy nhanh hơn khả năng xử lý của EE.

## Thứ tự chạy trong mỗi nhóm

Code chạy theo từng bước trên **toàn nhóm**: ảnh đêm tất cả tỉnh → CSV ngày/đêm tất cả tỉnh → ảnh ngày tất cả tỉnh. Trong một bước, xử lý lần lượt từng tỉnh. Sáu nhóm chạy độc lập; nhóm nhanh không chờ nhóm chậm. Pilot chỉ có tỉnh đầu nên thứ tự vẫn là ảnh đêm → CSV → ảnh ngày của tỉnh đó.

Nếu đang chạy bản cũ, nhấn Ctrl+C và chờ lệnh thoát trước khi cập nhật code. Giữ nguyên thư mục kết quả, `.local_state`, receipts, local.json và marker ổ E. Sau khi cập nhật đúng nhánh, chạy lại lệnh cũ (`--mode full` cho toàn nhóm). Code mới xác minh và tái sử dụng file đã hoàn thành; ảnh ngày/CSV đã làm trước đó vẫn giữ nguyên. Không cập nhật code giữa lúc Python còn chạy.

## 5. Xem kết quả và tiến độ

```text
E:\SatelliteData\Task123_branches\001_011\
    VN_NTL_Panel_2004_2025\raw_data\NTL\DMSP\01_ha_noi\*.tif
    VN_NTL_Panel_2004_2025\raw_data\NTL\VIIRS\01_ha_noi\*.tif
    VN_NTL_Panel_2004_2025\data_processed\night_indices.csv
    VN_LandCover_Panel_2004_2025\raw_data\DAY\LANDSAT\01_ha_noi\*.tif
    VN_LandCover_Panel_2004_2025\raw_data\DAY\SENTINEL2\01_ha_noi\*.tif
    VN_LandCover_Panel_2004_2025\data_processed\day_indices.csv
    branch_progress.json
    .local_state\state.json
```

Log `saved_local` có đường dẫn E thực tế. Log transcript nằm ở `%LOCALAPPDATA%\SatellitePipeline\direct-logs\`. Không tìm kết quả local trong GitHub artifact hoặc Drive. TIFF mở bằng QGIS; không có PNG tự động.

Hai CSV vẫn chứa đúng dòng tỉnh/thời kỳ, null cho kỳ thiếu. Trong lúc đang lấy ảnh đêm, CSV có thể chưa cập nhật hoặc còn PENDING; xem stage `night_images` / `indices_csv` / `day_images` và cuối cùng `complete`. `complete_with_gaps` vẫn cần kiểm tra các dòng thiếu/lỗi.

## Khôi phục, bảo vệ ổ đĩa và chạy sáu nhóm

- Marker/serial ổ đĩa và khóa writer được kiểm tra. File được tạo trong scratch cùng ổ E, kiểm tra checksum/grid/schema rồi rename nguyên tử, lưu receipt/checkpoint để chạy lại không tải lại file hoàn thành.
- File nhận từ Drive trước đây chỉ được tái sử dụng nếu có manifest + receipt + checksum hợp lệ, đúng job và đúng volume_marker. File có sẵn không có provenance hợp lệ sẽ không bị ghi đè.
- Thống kê đã nhận hợp lệ được nạp trước khi viết CSV gộp. Khi đổi pilot/full hoặc chuyển từ snapshot Drive, giữ bản CSV cũ trong `.panel_history`; không tạo bản sao sau mọi dòng cập nhật.
- Mỗi TIFF có reservation dựa trên dung lượng E còn trống, để lại margin 2 GiB. Nếu ổ gần đầy, code dừng, không tự giảm độ phân giải hoặc ghi file cắt cụt. Exit 4 = cần giải phóng dung lượng; exit 2 = kiểm tra lỗi/quyền/mạng rồi chạy lại; 130 = người dùng dừng. Sau bốn lần lỗi một công việc sẽ ghi FAILED, cần xem state thay vì coi là có dữ liệu.
- Để chạy sáu nhóm, dùng sáu checkout/ZIP đúng các nhánh, mỗi thư mục có range file riêng. Có thể dùng chung Python venv và ổ E, mở một PowerShell cho mỗi nhóm; không chạy hai bản cùng nhóm. Sáu nhóm vẫn chia sẻ quota project `vngis-ee-2`; nên thử một nhóm trước.
- Chưa có xác minh trực tiếp trên laptop/ổ E của người dùng từ cloud. Các test local dùng TIFF fixture và mock marker/EE; không mô tả chúng là đã chạy thu dữ liệu thật trên Windows.

## Lỗi checkpoint trên Windows

Nếu traceback dừng ở `os.fsync(stream.fileno())` với `OSError: [Errno 9] Bad file descriptor`, cập nhật `province_pipeline/common.py` của đúng checkout sau khi tiến trình dừng. Bản mới dùng `FlushFileBuffers` của Windows và vẫn dừng nếu Windows báo không ghi được. Không bỏ qua flush hoặc xóa state/receipts. Lỗi này tự nó không chứng minh ổ đầy hay hết EECU; cần xem WinError thực tế nếu bản mới tiếp tục lỗi. File TIFF đã có receipt hợp lệ được kiểm tra và tái sử dụng khi chạy lại; checkpoint cũ vẫn giữ nếu lần ghi mới chưa hoàn tất.
