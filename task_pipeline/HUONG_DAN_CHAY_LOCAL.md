# Hướng dẫn chạy local: dữ liệu chảy thẳng vào ổ E

Chạy trên laptop Windows. Earth Engine tải ảnh thô thẳng về `E:\SatelliteData`, không qua Google Drive, không cần GitHub Actions. Một thư mục mã chạy được cả 6 luồng, mỗi luồng một cửa sổ PowerShell.

## 0. Pipeline làm gì

Mỗi luồng (một dải tỉnh) chạy theo thứ tự:

| Bước | Việc | Chạy ở đâu | Kết quả |
|---|---|---|---|
| 1 | Ảnh thô ban đêm: DMSP năm 2004–2013, VIIRS tháng và năm 2013–2025 | Earth Engine (tốn quota) | `VN_NTL_Panel_2004_2025\raw_data\NTL\` |
| 2 | Ảnh thô ban ngày: Landsat tháng 2004–2014 (30 m), Sentinel-2 tháng 2015–2025 (20 m) | Earth Engine (tốn quota) | `VN_LandCover_Panel_2004_2025\raw_data\DAY\` |
| 3 | Ảnh trung gian: lọc nhiễu ảnh đêm, ảnh năm mùa khô từ ảnh tháng | Laptop | `...\data_intermediate\` |
| 4 | Bảng chỉ số tháng và năm (.csv, .xlsx, .dta) | Laptop | `...\data_processed\` |

- Ảnh ngày lưu int16 = phản xạ × 10000, 6 kênh (BLUE, GREEN, RED, NIR, SWIR1, SWIR2), nén ZSTD không mất dữ liệu. Ngoài ranh giới tỉnh là NoData, nên mọi phần mềm hiển thị đúng hình tỉnh.
- File đã có thì giữ, chỉ tải phần còn thiếu. Dừng giữa chừng rồi chạy lại là an toàn.

Cấu trúc trên ổ E sau khi chạy:

```
E:\SatelliteData\
  VN_NTL_Panel_2004_2025\
    README.md
    raw_data\NTL\DMSP\<mã_tỉnh>\   raw_data\NTL\VIIRS\<mã_tỉnh>\
    data_intermediate\DMSP\  VIIRS_MONTHLY\  VIIRS_ANNUAL\
    data_processed\ntl_annual.*  ntl_monthly.*  ntl_overlap_2013.*
    metadata\codebook.csv   logs\nhat_ky_cap_nhat.txt   code\ dashboard\ docs\
  VN_LandCover_Panel_2004_2025\
    README.md
    raw_data\DAY\LANDSAT\<mã_tỉnh>\   raw_data\DAY\SENTINEL2\<mã_tỉnh>\
    data_intermediate\annual_composite\LANDSAT\  SENTINEL2\
    data_processed\day_indices_monthly.*
    metadata\  samples\  logs\  code\  dashboard\  docs\
  _control\001_011\ ... _control\054_063\   (trạng thái riêng của từng luồng, không sửa tay)
  _legacy\                                   (dữ liệu định dạng cũ, bạn tự quyết định xóa)
```

Mỗi tỉnh thuộc đúng một luồng, nên 6 luồng không ghi đè ảnh của nhau. Bảng chung trong `data_processed` được ghép từ phần riêng của từng luồng, có khóa file.

## 1. Chuẩn bị (làm một lần)

1. Tải mã: trên GitHub chọn nhánh `vngis-tinh-054-063` (nhánh nào cũng được, 6 nhánh cùng mã), bấm **Code ▸ Download ZIP**, giải nén, ví dụ vào `C:\satellite\vietnam_satelline_final`.
2. Mở PowerShell tại thư mục đó, tạo môi trường Python 3.11:

```powershell
cd C:\satellite\vietnam_satelline_final
py -3.11 -m venv .venv
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $python -m pip install -r .\province_pipeline\requirements.txt
Test-Path "E:\"
```

`Test-Path "E:\"` phải ra `True`.

3. Nếu PowerShell chặn chạy script, chạy một lần: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
4. Tắt chế độ ngủ khi cắm sạc, để máy chạy qua đêm: `powercfg /change standby-timeout-ac 0`.

## 2. Đăng nhập Earth Engine (một lần)

Mỗi luồng dùng một project riêng để có quota riêng:

| Luồng (`-Range`) | Tỉnh | Project |
|---|---|---|
| 1-11 | Hà Nội … Hòa Bình | vngis-ee-2 |
| 12-22 | Thái Nguyên … Thái Bình | vngis-ee-ha-tinh-lai-chau |
| 23-33 | Hà Nam … Quảng Nam | vngis-ee-soc-trang-yen-bai |
| 34-43 | Quảng Ngãi … Đắk Nông | vngis-ee-cao-bang-hanoi |
| 44-53 | Lâm Đồng … Bến Tre | vngis-ee-lam-dong-quang-tri |
| 54-63 | Trà Vinh … Cà Mau | vgis-ee-6 |

Tài khoản Google bạn đăng nhập phải có quyền dùng cả 6 project (Owner, hoặc Service Usage Consumer + Earth Engine Resource Writer). Đăng nhập:

```powershell
& $python -m task_pipeline.local authenticate --project vngis-ee-2
```

Trình duyệt mở ra, đăng nhập, cho phép. Dòng `Earth Engine: vngis-ee-2 PASS` là thành công. Chỉ cần làm một lần cho mọi project.

## 3. Dừng luồng cũ

- GitHub ▸ Actions: hủy (Cancel) mọi lượt chạy đang chạy hoặc đang chờ.
- Nếu đã cài tác vụ nhận dữ liệu từ Drive, tắt nó:

```powershell
$task = Get-ScheduledTask -TaskName "Satellite-Drive-To-ExternalDisk" -ErrorAction SilentlyContinue
if ($task) { Stop-ScheduledTask -TaskName $task.TaskName; Disable-ScheduledTask -TaskName $task.TaskName }
```

## 4. Chuyển dữ liệu cũ sang cấu trúc mới (một lần)

Đóng mọi cửa sổ đang chạy pipeline, rồi:

```powershell
.\scripts\windows\Run-Task123-Local.ps1 -Command migrate -Python $python
```

Lệnh này chuyển nội dung `E:\SatelliteData\Task123_branches\<nhánh>\`:
- ảnh trong `VN_*` sang `E:\SatelliteData\VN_*` (giữ nguyên đường dẫn bên trong gói);
- ảnh ngày định dạng cũ và bảng cũ trong `data_processed` sang `E:\SatelliteData\_legacy\<nhánh>\`;
- trạng thái và biên nhận sang `E:\SatelliteData\_control\<nhánh>\`.

Lệnh chỉ di chuyển (rất nhanh vì cùng ổ), không xóa, không ghi đè. Cuối lệnh in báo cáo:
- `moved`: số file đã chuyển.
- `conflicts`: file trùng tên nhưng khác nội dung, được để nguyên chỗ cũ. Nếu khác 0, gửi báo cáo cho người phụ trách mã trước khi chạy tiếp.
- Báo cáo đầy đủ lưu tại `E:\SatelliteData\_control\migration_<thời gian>.json`. Chạy lại lệnh này nhiều lần cũng an toàn.

## 5. Chạy 6 luồng song song

Mở **6 cửa sổ PowerShell**, mỗi cửa sổ `cd` vào thư mục mã, đặt `$python` như bước 1, rồi chạy một dòng:

```powershell
.\scripts\windows\Run-Task123-Local.ps1 -Range 1-11  -Python $python
.\scripts\windows\Run-Task123-Local.ps1 -Range 12-22 -Python $python
.\scripts\windows\Run-Task123-Local.ps1 -Range 23-33 -Python $python
.\scripts\windows\Run-Task123-Local.ps1 -Range 34-43 -Python $python
.\scripts\windows\Run-Task123-Local.ps1 -Range 44-53 -Python $python
.\scripts\windows\Run-Task123-Local.ps1 -Range 54-63 -Python $python
```

Mặc định `-Mode full` (cả dải tỉnh, 2004–2025). Muốn thử một tỉnh đầu dải trước, thêm `-Mode pilot`. Project của từng dải được chọn tự động theo bảng ở bước 2; muốn đổi, thêm `-Project <tên>`.

## 6. Theo dõi tiến độ

- Trạng thái từng luồng: `E:\SatelliteData\_control\<nhánh>\branch_progress.json` (bước đang chạy, số việc theo trạng thái).
- Nhật ký tải ảnh theo mẫu của kế hoạch (Ngày cập nhật | Người thực hiện | Loại ảnh | Nội dung):

```powershell
Get-Content "E:\SatelliteData\VN_LandCover_Panel_2004_2025\logs\nhat_ky_cap_nhat.txt" -Tail 20 -Wait
```

- Log đầy đủ mỗi lần chạy: `%LOCALAPPDATA%\SatellitePipeline\direct-logs\`.
- Tên người thực hiện ghi trong nhật ký lấy từ tên đăng nhập Windows. Muốn ghi tên khác: `$env:SATELLITE_OPERATOR = "An Duc Trung"` trước khi chạy.

## 7. Dừng và chạy tiếp

| Muốn | Làm |
|---|---|
| Dừng một luồng | Bấm `Ctrl+C` trong cửa sổ đó. File đang tải dở bị bỏ, không có file hỏng |
| Chạy tiếp | Chạy lại đúng dòng lệnh của luồng đó. File đã có được bỏ qua |
| Chỉ chạy bước 3–4 (không tốn quota) | Thêm `-Command derive`, ví dụ `.\scripts\windows\Run-Task123-Local.ps1 -Command derive -Range 54-63 -Python $python` |

Mã thoát in ở cuối cửa sổ:

| Mã | Ý nghĩa | Làm gì |
|---|---|---|
| 0 | Xong | Xem `branch_progress.json`; `complete_with_gaps` là có tháng không có ảnh |
| 2 | Lỗi mạng, quyền hoặc Earth Engine | Kiểm tra mạng và quyền project, rồi chạy lại |
| 4 | Ổ E còn dưới khoảng 2 GB trống | Giải phóng chỗ hoặc thay ổ, rồi chạy lại |
| 130 | Đã dừng bằng Ctrl+C | Chạy lại khi muốn |

Một việc lỗi 4 lần liên tiếp được đánh dấu `FAILED` và bỏ qua ở các lần sau; xem `state.json` trong `_control\<nhánh>\.local_state\`.

## 8. Lưu ý

- **Dung lượng:** ảnh ngày theo tháng ước tính khoảng 1,0–1,3 TB, cộng ảnh đêm và ảnh trung gian. Ổ 1 TB có thể không đủ. Khi ổ gần đầy, luồng tự dừng với mã 4, không ghi file dở.
- **Sentinel-2 2015–2018** chỉ có ảnh TOA (chưa hiệu chỉnh khí quyển) trên Earth Engine; bảng ghi `loai_phan_xa = TOA` và `trang_thai = OK_TOA`.
- **Sentinel-2 dùng 20 m** thay cho 10 m trong kế hoạch, để vừa dung lượng; kênh SWIR gốc chỉ có 20 m. Ghi chú này đã có trong README của gói.
- **Hiệu chỉnh liên kết DMSP–VIIRS chưa áp dụng** (`hieu_chinh = PENDING`). Năm 2013 có cả hai nguồn, số liệu đối chiếu nằm trong `ntl_overlap_2013`. Chuỗi năm không tính mức thay đổi qua năm đổi nguồn 2013→2014.
- **Bản đồ phân loại 5 lớp** cần bộ điểm mẫu trong `VN_LandCover_Panel_2004_2025\samples\`; trạng thái hiện tại `PENDING_SAMPLES`.
- **Mùa khô cho ảnh năm:** tháng 11–4 cho tỉnh mã 01–42, tháng 1–8 cho Quảng Bình đến Bình Thuận (mã 44–60), tháng 12–4 cho Tây Nguyên, Đông Nam Bộ, Đồng bằng sông Cửu Long (mã 62–96). Năm không có ảnh mùa khô thì dùng mọi tháng có ảnh và ghi `SEASON_RULE=ALL_MONTHS_FALLBACK` trong tag của file.
- Không sửa, đổi tên hay xóa file trong `_control\`; đó là biên nhận giúp chạy tiếp đúng chỗ.
