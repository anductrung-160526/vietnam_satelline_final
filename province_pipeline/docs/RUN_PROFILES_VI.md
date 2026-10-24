# Chạy thử Hà Nội 2025 và chạy toàn bộ mẫu

Chỉ dùng nhánh `inspriring-newton`. Không cần biến GitHub mới; giữ hai secrets hiện có và `PROVINCE_CONFIG_JSON` để cung cấp project, thư mục Drive và ngân sách. Không đưa credentials vào repo.

## Trước khi bắt đầu

1. Trong `PROVINCE_CONFIG_JSON`, đặt `"pause": true` để workflow cũ trên main không tiếp tục xuất theo cấu hình cũ. Workflow mới khi chọn `mode=run` sẽ chủ động mở chạy theo sample đã chọn, không cần sửa years/province_codes/products trong biến.
2. Đảm bảo không còn workflow cũ đang chạy. Không chạy đồng thời controller ở máy khác.
3. Cập nhật bản repo trên Windows trước khi nhận: mã mới bổ sung đồng bộ hai CSV cuối. Nếu dùng ZIP, giải nén **sang thư mục mới**, giữ bản cũ và sao chép `province_pipeline/config/local.json` từ bản cũ sang bản mới (không ghi đè marker hoặc cấu hình local bằng config mẫu). Cài requirements bằng Python venv đang dùng. Đăng ký lại Scheduled Task với đường dẫn repo mới bằng hướng dẫn `scripts/windows/Register-SatelliteTask.ps1`; kiểm tra tên script và tham số thực tế ở phần dưới. Nếu dùng Git, pull tại checkout trên nhánh tương ứng và giữ config local đã gitignore. Không copy secret vào thư mục tracked.
4. Giữ nguyên ổ E, marker đã đăng ký, rclone và local `allow_remote_delete=true` nếu đã xác minh chức năng xóa. Không đăng ký lại marker khi đổi sample.

## Hai chế độ

Vào Actions → **Province satellite staging** → **Run workflow**, chọn branch `inspriring-newton`:

| Input | Chạy thử (mặc định) | Toàn bộ |
|---|---|---|
| `sample` | `test_hanoi_2025` | `full_2004_2025` |
| `mode` | `run` | `run` |
| `cycles` | `20` | `20` |

- Thử: Hà Nội, đủ 12 tháng 2025, VIIRS đêm và Sentinel-2 SR ngày.
- Toàn bộ: 63 tỉnh, 2004–2025; không thay thế nguồn thiếu.
- `cycles` trong 1–20 là số lượt workflow tối đa trong một chuỗi, **không phải số năm hay số luồng**. Token GitHub của riêng job finalize được cấp `actions:write` để kích hoạt lượt kế tiếp cùng nhánh/sample; không cần PAT hoặc secret mới. Mỗi chuỗi tự dừng khi xong, đủ số lượt, Drive đầy hoặc cần kiểm tra submission không rõ kết quả. Lỗi dispatch được báo công khai bằng HTTP code, không lộ token; có thể chạy tiếp thủ công.
- Khi hết số lượt mà chưa xong, chọn lại đúng sample và `run` để tiếp tục. Mẫu toàn bộ có thể cần rất nhiều chuỗi; không có cam kết hoàn tất trước deadline hay 20 lượt là đủ.
- Đừng khởi động nhiều chuỗi cùng lúc hoặc đổi sample trong khi chuỗi cũ còn tiếp tục.
- Cron chỉ hoạt động trên default branch. Trên nhánh này, chuỗi bắt đầu bởi Run workflow; khi dừng vì Drive đầy, cần giải phóng staging bằng receiver rồi Run workflow lại. Không tuyên bố vận hành 24/24 không giới hạn.
- Nếu GitHub không cho dispatch workflow trên nhánh chưa có workflow tương ứng ở default branch, lượt đầu vẫn chạy; tiếp tục thủ công. Không merge main tự động.

## Kết quả để kiểm tra

Mỗi lượt chạy có phần Summary báo stage, số dòng `OK`, `PENDING`, `MISSING_SOURCE`, `INSUFFICIENT_QUALITY`, `FAILED` và cảnh báo chưa hiệu chỉnh.

Trong job finalize, artifact `province-indices-test_hanoi_2025` gồm hai CSV và `quality_summary.json`. Artifact xuất theo tiến độ: đủ số dòng **không đồng nghĩa đã có đủ số liệu**. Đợi stage `complete` và kiểm tra DATA_STATUS / ERROR, không chỉ nhìn workflow xanh.

Hai CSV chính trên Drive và trên ổ E:

```text
VN_NTL_Panel_2004_2025/data_processed/night_indices.csv
VN_LandCover_Panel_2004_2025/data_processed/day_indices.csv
```

Mẫu thử có 12 dòng mỗi CSV. Toàn bộ có 9.702 dòng đêm và 16.632 dòng ngày. Số liệu thiếu là ô trống (=null), không phải 0. Không sinh CSV bảng năm/tháng phụ; phân mảnh kỹ thuật ở `_staging/statistics/`. Dữ liệu legacy giữ nguyên để tránh xóa kết quả của người dùng.

Receiver mới tải snapshot hai CSV có kiểm tra MD5/SHA256 và version trước/sau. CSV nhỏ được giữ trên Drive; chỉ các output nguồn nhận thành công mới thuộc cơ chế xóa có điều kiện. Hai bảng vẫn đủ dữ liệu khi TIFF/phân mảnh nguồn đã bị xóa. Không chỉnh sửa TIFF đã có receipt.

## Nguồn và thứ tự xử lý

1. Ảnh đêm DMSP 2004–2013 theo năm, VIIRS 2014–2025 theo tháng, gồm nguồn và lọc.
2. Chỉ số CSV đêm/ngày. Ngày dùng Landsat 2004–2017, Sentinel-2 SR 2018–2025, theo tháng. Không áp bộ lọc mùa khô vào CSV tháng.
3. TIFF ngày composite năm ưu tiên các tháng mùa khô được cấu hình; không xuất 12 TIFF tháng thay cho sản phẩm năm PDF.

Tối đa 10 công việc đang hoạt động, luân phiên 10 nhóm tỉnh. Mẫu Hà Nội chỉ có nhóm 0 nên không thể có 10 nhóm tỉnh cùng chạy. Công việc FAILED sau tối đa 4 lần, BLOCKED_OUTPUT, MISSING_SOURCE hoặc INSUFFICIENT_QUALITY không chặn vĩnh viễn stage sau; báo cáo vẫn giữ lỗi.

Kiểm tra offline bằng CLI (không truy cập EE/Drive):

```powershell
& $python -m province_pipeline --config province_pipeline/config/local.json profile --sample test_hanoi_2025 --output .province-local/test.json
& $python -m province_pipeline --config .province-local/test.json validate
```

Với GADM hiện tại / tile 512: 24 tile TIFF đêm, 24 công việc bảng, 52 tile TIFF ngày. Đây là kế hoạch, không chứng minh ảnh thực tế sẵn có hoặc chất lượng đạt.

## Phương pháp và giới hạn phải giữ trong báo cáo

- Mask QA_PIXEL/QA_RADSAT và đệm mây Landsat; SCL + Cloud Score+ Sentinel; median các quan sát hợp lệ; tính chỉ số pixel trước median và thống kê diện tích toàn tỉnh trên lưới 30 m.
- Mặc định ít nhất 2 quan sát ngày/pixel, diện tích hợp lệ tối thiểu 80%, Cloud Score+ cs_cdf >=0.60. Đây là ngưỡng cấu hình ban đầu, chưa phải ngưỡng được xác nhận cho mọi tỉnh/mùa. Xem `quality` trong cấu hình materialize.
- TIFF Sentinel nhiều băng có SWIR ở 20 m; không gọi SWIR nội suy là quan sát gốc 10 m. Đợt này không xuất thêm bản quang học 4 băng 10 m.
- NTL dùng cf_cvg và MODIS MOD14A1 để mask pixel cháy confidence cao. DMSP nhiều vệ tinh: chọn system:index lớn nhất theo thứ tự từ điển, không trộn trung bình các vệ tinh chưa hiệu chỉnh. DN gốc có thể bão hòa/blooming.
- Không coi vùng biển tối là thiếu dữ liệu, không xóa mọi mặt nước để xử lý tàu thuyền. Chưa có mô hình loại toàn bộ ánh sáng tàu và transient đáng tin cậy: ghi cờ residual review.
- Tự kiểm tra TIFF sau tải (decode, lưới, NaN/Inf, tile hằng, NoData, miền giá trị) và gắn QA tags. Khi SR ngoài miền bảo thủ [-0.2,1.6], thử lại đúng nguồn/asset/kỳ bằng mask chặt hơn tối đa một lần; nếu bảng vẫn không đạt, để null. Cờ chuỗi thời gian robust chỉ đánh dấu để kiểm tra, không xóa biến động thực tế.
- TNL/SOL là tổng pixel nguồn; mật độ chia diện tích tự nhiên. DMSP DN khác VIIRS radiance và khác lưới. **CALIBRATION_STATUS=NOT_CALIBRATED; SOL_NTL_CALIBRATED=null**. Chưa có mô hình liên cảm biến đã kiểm định độc lập. Theo phương án deadline đã thống nhất, xuất chỉ số gốc kèm trạng thái, không tuyên bố đã tạo chuỗi hài hòa.
- VIIRS SOL_YEAR là trung bình thời gian của đủ 12 SOL tháng hợp lệ (không phải ảnh annual EOG và không cộng 12 tháng); lặp trên dòng tháng, không cộng lại. Thiếu tháng thì giá trị năm null. Năm 2014 không tính tăng trưởng sang DMSP 2013.
- Tỷ lệ diện tích sáng không phải tỷ lệ hộ có điện. LIT_POP_PROXY null vì chưa có mô hình dân số. Min/max, CV, lit counts, cf_cvg và các công thức nằm trong `metadata/indices_codebook.json`, `processing_policy.json`.
- Không phân loại 5 lớp, không tính chuyển đổi đất, không dashboard. Chưa hoàn tất toàn bộ yêu cầu khoa học PDF; các giới hạn trên phải giữ trong bàn giao.

## Cập nhật receiver Windows từ ZIP

Tại **thư mục repo mới**, kiểm tra script đăng ký và đọc ví dụ trước khi chạy:

```powershell
Get-ChildItem .\scripts\windows\
$repo = (Get-Location).Path
$python = "C:\Users\AD\Downloads\vietnam_satelline_final-inspriring-newton\.venv\Scripts\python.exe"
& $python -m pip install -r .\province_pipeline\requirements.txt
& .\scripts\windows\Register-SatelliteTask.ps1 `
    -Repo $repo `
    -Config (Join-Path $repo "province_pipeline\config\local.json") `
    -Python $python `
    -RcloneConfig "$env:APPDATA\rclone\rclone.conf" `
    -Remote "gdrive"
```

Nếu giữ checkout cũ và chỉ pull code, tác vụ đã đăng ký vẫn dùng đường dẫn cũ hợp lệ. Kiểm tra tác vụ:

```powershell
Start-ScheduledTask -TaskName "Satellite-Drive-To-ExternalDisk"
Get-ScheduledTaskInfo -TaskName "Satellite-Drive-To-ExternalDisk" |
    Format-List LastRunTime, LastTaskResult, NextRunTime
```

`LastTaskResult=0` là lượt receiver hoàn tất; xem thêm log `receiver_summary`, kết quả trên E và CSV DATA_STATUS. Laptop tắt/Sleep thì receiver dừng. Drive đầy thì chuỗi xuất dừng; sau khi bật máy giải phóng dung lượng, chạy lại sample để tiếp tục.
