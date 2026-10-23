# Hướng dẫn chạy pipeline dữ liệu viễn thám cấp huyện (tự động)

Tài liệu này hướng dẫn từng bước chạy pipeline trên máy Windows. Pipeline lấy dữ liệu **cấp huyện**, giai đoạn **2004–2025**, và ghi kết quả vào ổ C:

```
C:\VNGIS_Data\
├── VN_NTL_Panel_2004_2025\        ánh sáng ban đêm (DMSP, VIIRS)
│   ├── README.md
│   ├── raw_data\NTL\DMSP\  raw_data\NTL\VIIRS\    ảnh .tif gốc theo huyện
│   ├── data_intermediate\                         ảnh .tif đã lọc nhiễu, hiệu chỉnh
│   ├── data_processed\                            bảng .csv .xlsx .dta
│   ├── metadata\  code\  docs\  logs\  dashboard\
├── VN_LandCover_Panel_2004_2025\  ảnh ban ngày (Landsat, Sentinel-2)
│   ├── raw_data\DAY\LANDSAT\  raw_data\DAY\SENTINEL2\
│   ├── data_intermediate\  data_processed\  metadata\  samples\  code\  docs\  logs\  dashboard\
├── _cache\     ranh giới GADM tải về (dùng lại)
└── timing\     thời gian chạy từng bước
```

Pipeline **không dùng machine learning**. Ảnh ban ngày được phân 5 lớp bằng ngưỡng chỉ số phổ (NDVI, MNDWI, NDBI) kết hợp độ dốc địa hình. Ngưỡng nằm trong `pipeline_core/config.py` (`LANDCOVER_THRESHOLDS`).

---

## 1. Cài đặt (làm một lần)

1. Cài **Python 3.10 trở lên** từ https://www.python.org/downloads/. Khi cài, tích ô **Add python.exe to PATH**.
2. Tải repo về máy, ví dụ vào `C:\Users\<tên bạn>\Documents\vietnam_satelline_final`.
3. Mở **Command Prompt** (gõ `cmd` vào Start), rồi chạy:

```bat
cd /d "C:\Users\<tên bạn>\Documents\vietnam_satelline_final"
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Nếu cài `rasterio` bị lỗi, chạy `pip install --only-binary=:all: rasterio`. Thư viện này chỉ cần khi ảnh quá lớn và phải chia ô rồi ghép lại.

**Lưu ý khi gõ lệnh:** mỗi lệnh chạy **riêng một dòng**. Dán một dòng, bấm Enter, đợi chạy xong rồi mới dán dòng tiếp theo. Nếu dán nhiều lệnh dính liền thành một dòng, Windows sẽ báo lỗi `unrecognized arguments`.

**Repo nằm trong OneDrive:** thư mục `.venv` có hàng nghìn tệp nhỏ, nên OneDrive có thể khóa tệp khi đang cài. Nếu `pip install` báo *Access is denied* hoặc *file in use*, hãy tạm dừng OneDrive (biểu tượng đám mây, chọn Pause syncing) rồi chạy lại. Dữ liệu đầu ra ghi vào `C:\VNGIS_Data`, nằm ngoài OneDrive.

### Chạy trong terminal của Antigravity / VS Code (PowerShell)

Terminal của Antigravity trên Windows mặc định là **PowerShell**, còn các lệnh trong tài liệu này viết cho **Command Prompt (cmd)**. Có hai cách:

- **Cách 1 (dễ nhất):** trong panel Terminal, bấm mũi tên **˅** cạnh dấu **+**, chọn **Command Prompt**. Khi đó mọi lệnh trong tài liệu chạy y nguyên.
- **Cách 2:** giữ PowerShell và đổi các lệnh sau:

| Command Prompt | PowerShell |
|---|---|
| `cd /d "C:\...\vietnam_satelline_final"` | `cd "C:\...\vietnam_satelline_final"` |
| `.venv\Scripts\activate` | `.\.venv\Scripts\Activate.ps1` |
| `run_hanoi_pilot.bat` | `.\run_hanoi_pilot.bat` |
| ghi chú `:: ...` | ghi chú `# ...` |
| xuống dòng bằng `^` | xuống dòng bằng `` ` `` (hoặc viết trên một dòng) |

Nếu PowerShell báo *running scripts is disabled* khi kích hoạt `.venv`, chạy một lần lệnh `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Biến đặt bằng `setx` chỉ có tác dụng ở terminal **mở sau đó**. Muốn dùng ngay trong phiên hiện tại thì chạy `$env:VNGIS_EE_PROJECT = "vngis-ee-2"`. Nếu `earthengine authenticate` không mở được trình duyệt, chạy `earthengine authenticate --auth_mode=notebook`, mở link được in ra rồi dán mã xác thực vào terminal.

Toàn bộ các bước trong PowerShell:

```powershell
cd "C:\Users\<tên bạn>\Documents\vietnam_satelline_final"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
earthengine authenticate
$env:VNGIS_EE_PROJECT = "vngis-ee-2"
python run_hanoi_pilot.py
```

## 2. Đăng ký và xác thực Google Earth Engine (làm một lần)

1. Đăng ký Earth Engine tại https://earthengine.google.com/ rồi tạo (hoặc chọn) một **Google Cloud Project** đã bật Earth Engine API. Ghi lại **Project ID**.
2. Trong cửa sổ cmd đã kích hoạt `.venv`, chạy:

```bat
earthengine authenticate
```

   Trình duyệt sẽ mở ra. Bạn đăng nhập tài khoản Google đã đăng ký GEE và bấm cho phép.
3. Khai báo Project ID một lần cho máy (mở lại cmd sau lệnh này):

```bat
setx VNGIS_EE_PROJECT "ten-project-cua-ban"
setx VNGIS_USER "Ho Ten Nguoi Thuc Hien"
```

   `VNGIS_USER` là tên ghi vào cột "Người thực hiện" trong nhật ký cập nhật.

## Nguồn nào có dữ liệu tháng?

| Nguồn | Năm | Tháng | Ghi chú |
|---|---|---|---|
| DMSP-OLS (2004–2013) | có | **không** | NOAA chỉ phát hành ảnh năm |
| VIIRS DNB | có (2013–2025) | có (từ 04/2012) | ảnh tháng tổng hợp sẵn của EOG |
| Landsat 5/7/8/9 | **2004–2014** (ghép mùa khô) | có (ghép các cảnh trong tháng) | tháng mùa mưa nhiều mây, xem cột `ty_le_quan_sat` |
| Sentinel-2 | **2015–2025** (ghép mùa khô) | có (ghép các cảnh trong tháng) | như trên |

Ảnh ngày mặc định dùng **một nguồn cho mỗi năm**: Landsat cho 2004–2014, Sentinel-2 cho 2015–2025. Ví dụ năm 2024 chỉ chạy Sentinel-2. Diện tích chuyển đổi năm 2015 so với 2014 được tính giữa hai nguồn khác nhau, và điều này được ghi ở cột `ghi_chu`. Muốn chạy nguồn khác, dùng `--day-sensors landsat` hoặc `--day-sensors landsat,sentinel2`.

Nguồn chỉ có ảnh năm thì chỉ lấy theo năm. Nguồn có ảnh tháng thì lấy cả **năm** (theo đúng kế hoạch) **và 12 tháng**. Tháng không có cảnh nào vẫn có một dòng trong bảng, với `so_canh_anh = 0`; pipeline **không tự điền số**. Diện tích đất nông nghiệp chuyển đổi chỉ tính theo năm, vì ảnh tháng thay đổi theo mùa vụ.

## 3. Chạy thử Hà Nội (đo thời gian)

Cách đơn giản nhất là **bấm đúp `run_hanoi_pilot.bat`** trong thư mục repo. Cách khác là chạy lệnh:

```bat
python run_hanoi_pilot.py                      :: năm 2024: dữ liệu năm + 12 tháng, bảng + ảnh tháng
python run_hanoi_pilot.py --years 2004-2025    :: Hà Nội cả chuỗi, năm + 12 tháng mỗi năm
python run_hanoi_pilot.py --no-monthly-tif     :: có bảng tháng nhưng không tải ảnh tháng (nhẹ hơn nhiều)
python run_hanoi_pilot.py --no-monthly         :: chỉ dữ liệu năm
python run_hanoi_pilot.py --no-tif                :: chỉ bảng số liệu, không tải ảnh
```

Khi chạy xong, màn hình in ra:

- tổng thời gian, số tệp `.tif` và dung lượng đã tải;
- thời gian trung bình theo từng bước (xác thực GEE, đọc ranh giới, chuẩn bị ảnh, thống kê vùng, tải tif, xuất bảng);
- **ước tính thời gian và dung lượng cho toàn quốc** (~705 huyện × 22 năm).

Chi tiết từng bước được ghi vào `C:\VNGIS_Data\VN_NTL_Panel_2004_2025\logs\timing_hanoi_<thời điểm>.csv`. File `..._tom_tat.txt` cùng thư mục chứa bản tóm tắt. Bản sao của cả hai file cũng nằm trong thư mục `logs` của gói LandCover.

Ảnh tháng làm dung lượng tăng khoảng 12 lần so với chỉ lấy ảnh năm. Riêng Sentinel-2 10 m của Hà Nội có thể lên tới vài GB mỗi năm, nên cả chuỗi 2015–2025 cần hàng chục GB. Hãy chạy năm 2024 trước để xem dung lượng thực tế. Sentinel-2 ở độ phân giải 10 m có dung lượng lớn nhất. Hà Nội cần khoảng vài trăm MB mỗi năm. Muốn tải nhẹ hơn, bạn đặt `setx VNGIS_S2_SCALE 20`. Cách này chỉ đổi độ phân giải ảnh tải về; bảng diện tích vẫn tính ở 10 m.

## 4. Chạy theo tỉnh, theo năm hoặc toàn quốc

```bat
python run_pipeline.py --province "Hà Nội" --years 2024
python run_pipeline.py --province "Hà Nội,Bắc Ninh" --years 2015-2025
python run_pipeline.py --districts "Ba Vì,Sóc Sơn" --years 2004,2010,2024
python run_pipeline.py --years 2004-2025 --monthly           :: toàn quốc, thêm dữ liệu 12 tháng
python run_pipeline.py --pipeline ntl --years 2013-2025      :: chỉ ánh sáng đêm
python run_pipeline.py --pipeline landcover --day-sensors landsat
python run_pipeline.py --pipeline init-only                  :: chỉ tạo thư mục, codebook, điểm mẫu
```

| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `--output-dir` | Thư mục gốc lưu dữ liệu | `C:\VNGIS_Data` (hoặc biến `OUTPUT_ROOT`) |
| `--pipeline` | `all`, `ntl`, `landcover`, `init-only` | `all` |
| `--province` | Tên tỉnh, có thể nhiều tỉnh cách nhau dấu phẩy | toàn quốc |
| `--districts` | Tên hoặc mã huyện (Cục Thống kê / GADM), cách nhau dấu phẩy | tất cả |
| `--years` | `2024`, `2010-2015`, `2004,2024` | 2004–2025 |
| `--mode pilot --pilot-n 3` | Chỉ lấy n huyện đầu để thử nhanh | `full` |
| `--monthly` | Thêm bảng 12 tháng cho mọi nguồn có ảnh tháng: VIIRS (từ 04/2012), Landsat, Sentinel-2 | tắt (chạy Hà Nội: bật) |
| `--monthly-tif` | Tải thêm ảnh `.tif` từng tháng | tắt (chạy Hà Nội: bật) |
| `--day-sensors` | `auto` (Landsat 2004–2014, Sentinel-2 2015–2025), `landsat`, `sentinel2`, `landsat,sentinel2` | `auto` |
| `--no-tif` | Chỉ tính bảng, không tải ảnh `.tif` | tải ảnh |
| `--no-accuracy` | Bỏ qua đánh giá độ chính xác phân lớp | có đánh giá |
| `--ee-project` | Project ID GEE | biến `VNGIS_EE_PROJECT` |
| `--min-free-gb` | Cảnh báo khi ổ đĩa còn ít hơn số GB này | 5 |

## 5. Chạy tự động định kỳ (Windows Task Scheduler)

Script `run_auto_update.bat` gọi `run_auto_update.py`. Script này tự tìm năm hoặc tháng **chưa có dữ liệu** (dựa vào checkpoint trong `logs\`) rồi chạy tiếp phần còn thiếu:

- `--scope monthly`: lấy dữ liệu tháng (VIIRS, Landsat, Sentinel-2) của năm nay và năm trước, bổ sung tháng mới vào các bảng tháng. Thêm `--monthly-tif` nếu muốn tải cả ảnh tháng.
- `--scope annual`: lấy NTL và lớp phủ cho mọi năm từ 2004 đến năm mới nhất đã đủ ảnh (từ tháng 6 thì tính cả năm hiện tại, vì ảnh mùa khô kết thúc vào tháng 4).
- `--scope all`: chạy cả hai.

Có thể thêm `--province "Hà Nội"` để chỉ cập nhật một tỉnh. Màn hình chạy được ghi nối tiếp vào `C:\VNGIS_Data\auto_update_console.log`.

### Tạo lịch bằng lệnh (mở cmd bằng *Run as administrator*)

Thay đường dẫn bằng thư mục repo của bạn:

```bat
:: Hằng tháng, ngày 10, lúc 02:00: cập nhật dữ liệu tháng
schtasks /Create /TN "VNGIS_CapNhat_Thang" /SC MONTHLY /D 10 /ST 02:00 ^
  /TR "\"C:\Users\<tên bạn>\Documents\vietnam_satelline_final\run_auto_update.bat\" --scope monthly --monthly-tif"

:: Hằng năm, ngày 15/06, lúc 01:00: cập nhật năm mới (NTL + lớp phủ)
:: (schtasks không có lịch YEARLY: dùng MONTHLY chỉ với tháng 6)
schtasks /Create /TN "VNGIS_CapNhat_Nam" /SC MONTHLY /M JUN /D 15 /ST 01:00 ^
  /TR "\"C:\Users\<tên bạn>\Documents\vietnam_satelline_final\run_auto_update.bat\" --scope annual"
```

### Tạo lịch bằng giao diện

1. Mở **Task Scheduler**, chọn **Create Basic Task...**
2. Đặt tên, ví dụ `VNGIS_CapNhat_Thang`. Trigger chọn **Monthly**, ngày 10, giờ 02:00.
3. Action chọn **Start a program**. Program/script trỏ tới `run_auto_update.bat`. *Add arguments* điền `--scope monthly --monthly-tif`. *Start in* điền thư mục repo.
4. Trong Properties, tích **Run whether user is logged on or not** và **Wake the computer to run this task** (tab Conditions).
5. Lặp lại các bước trên với `--scope annual` cho lịch hằng năm.

Kiểm tra lịch: `schtasks /Query /TN "VNGIS_CapNhat_Thang"`. Chạy thử ngay: `schtasks /Run /TN "VNGIS_CapNhat_Thang"`.

Tài khoản chạy task phải là tài khoản đã chạy `earthengine authenticate`, vì thông tin xác thực lưu trong `%USERPROFILE%\.config\earthengine`.

## 6. Chạy tiếp khi bị ngắt, xem log, xử lý lỗi

- **Chạy tiếp:** bạn chỉ cần chạy lại đúng lệnh cũ. Mỗi huyện-năm làm xong được ghi vào `logs\*_checkpoint.jsonl`, nên lần sau pipeline sẽ bỏ qua. Ảnh `.tif` đã có trên ổ đĩa cũng không tải lại. Bảng `data_processed` luôn được dựng lại từ toàn bộ checkpoint, nên không mất dữ liệu cũ.
- **Chạy lại từ đầu một phần:** xóa dòng tương ứng trong `*_checkpoint.jsonl` (hoặc xóa cả tệp) và xóa ảnh `.tif` tương ứng.
- **Nhật ký:**
  - `logs\nhat_ky_cap_nhat.txt`: nhật ký nối tiếp theo mẫu `Ngày cập nhật | Người thực hiện | Loại ảnh | Nội dung`.
  - `logs\<pipeline>_<thời điểm>.log`: nhật ký của từng lượt chạy.
  - `logs\<pipeline>_errors_<thời điểm>.log`: chỉ chứa lỗi; tệp này chỉ xuất hiện khi có lỗi.

| Lỗi thường gặp | Cách xử lý |
|---|---|
| `Không kết nối được Google Earth Engine` | Chạy lại `earthengine authenticate`; kiểm tra `VNGIS_EE_PROJECT` đúng Project ID đã đăng ký GEE |
| `429`, `quota`, `Too many requests` | Pipeline tự thử lại 5 lần (chờ 4, 8, 16, 32, 64 giây). Nếu vẫn lỗi, để đến hôm sau rồi chạy lại cùng lệnh |
| Mất mạng giữa chừng | Chạy lại cùng lệnh, pipeline sẽ chạy tiếp từ checkpoint |
| Ổ C đầy hoặc cảnh báo dung lượng | Dọn ổ, dùng `--output-dir D:\VNGIS_Data`, chạy `--no-tif`, hoặc đặt `VNGIS_S2_SCALE=20` |
| `Total request size ... must be less than` | Pipeline tự chia ảnh thành các ô nhỏ rồi ghép lại (cần `rasterio`) |
| `Không có ảnh ... năm X` | Năm đó nguồn ảnh chưa có (ví dụ VIIRS năm mới chưa phát hành). Lần cập nhật sau sẽ tự lấy |
| Huyện "Chưa có mã Cục Thống kê" | Bổ sung dòng vào `pipeline_core/data/gso_district_codes.csv` (tên không kèm "Quận/Huyện") |

## 7. Kiểm tra kết quả

| Kết quả | Đường dẫn |
|---|---|
| **CSV chỉ số ảnh đêm (năm + tháng)** | `VN_NTL_Panel_2004_2025\data_processed\vietnam_district_night_indices_2004_2025.csv` |
| **CSV chỉ số ảnh ngày (năm + tháng)** | `VN_LandCover_Panel_2004_2025\data_processed\vietnam_district_day_indices_2004_2025.csv` |
| Bảng ánh sáng đêm theo năm | `VN_NTL_Panel_2004_2025\data_processed\vietnam_district_ntl_panel_2004_2025.csv/.xlsx/.dta` |
| Bảng VIIRS theo tháng | `VN_NTL_Panel_2004_2025\data_processed\vietnam_district_ntl_viirs_monthly.*` |
| Bảng lớp phủ theo tháng | `VN_LandCover_Panel_2004_2025\data_processed\vietnam_district_landcover_monthly.*` |
| Ảnh đêm gốc / đã xử lý | `raw_data\NTL\DMSP\`, `raw_data\NTL\VIIRS\` / `data_intermediate\NTL_<ma_huyen>_<nam>.tif` |
| Hệ số hiệu chỉnh DMSP→VIIRS | `VN_NTL_Panel_2004_2025\docs\hieu_chinh_dmsp_viirs.json` |
| Bảng lớp phủ | `VN_LandCover_Panel_2004_2025\data_processed\vietnam_district_landcover_panel_2004_2025.*` |
| Ảnh ngày tổng hợp / bản đồ phân lớp | `raw_data\DAY\LANDSAT\`, `raw_data\DAY\SENTINEL2\` / `data_intermediate\LC_<nguồn>_<ma_huyen>_<nam>.tif` |
| Báo cáo độ chính xác | `VN_LandCover_Panel_2004_2025\docs\BAO_CAO_DO_CHINH_XAC_<NGUON>_<NAM>.md` |
| Codebook | `metadata\codebook_*.md` và `.xlsx` |
| Thời gian chạy | `logs\timing_hanoi_*.csv` (chạy thử), `C:\VNGIS_Data\timing\timing_*.csv` (chạy thường) |

**Đọc 2 file CSV chỉ số:** mỗi file chứa cả dòng năm và dòng tháng. Cột `ky` = `Năm` hoặc `Tháng`; cột `thang` để trống ở dòng năm. Lọc theo cột `ky` để lấy riêng từng loại. Trong file ảnh đêm, các năm 2004–2011 chỉ có dòng năm (DMSP), từ 04/2012 có thêm dòng tháng (VIIRS). Ở dòng tháng, `thay_doi_ntl` là % thay đổi so với **cùng tháng năm trước**.

**Đọc file timing:** mỗi dòng là một bước. `pipeline` là `ntl_pipeline` hoặc `landcover_pipeline`. `buoc` là tên bước. `ma_huyen` và `nam` cho biết bước đó chạy cho huyện và năm nào. `giay` là thời gian chạy. `mb` là dung lượng tệp vừa tải. `trang_thai` nhận giá trị `ok` hoặc `loi`. Mở bằng Excel rồi dùng PivotTable theo `buoc` để biết bước nào tốn thời gian nhất.

Mở ảnh `.tif` bằng QGIS (kéo thả tệp vào). Bản đồ phân lớp có giá trị 0 = không quan sát, 1 = nông nghiệp, 2 = đô thị, 3 = rừng, 4 = mặt nước, 5 = khác.
