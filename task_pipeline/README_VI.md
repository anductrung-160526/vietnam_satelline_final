> **Muốn bỏ Drive và ghi trực tiếp vào E:** dùng [DIRECT_TO_E_VI.md](DIRECT_TO_E_VI.md). Đây là chế độ chạy trên laptop bằng PowerShell; workflow GitHub bên dưới vẫn là phương án qua Drive.

> **Cập nhật:** đầu ra ảnh mới là **một TIFF toàn tỉnh/thời kỳ, không xuất PNG**, không xuất các tile tạm lên Drive. DMSP theo năm; VIIRS và ảnh ngày theo tháng. File mới có `_province_` trong tên. File tile cũ giữ nguyên, không tự xóa.

# Sáu nhánh cố định — Task 1, 2, 3 theo tỉnh, 2004–2025

Đầu ra **cấp tỉnh**, không chạy từng xã/huyện. Giữ project `vngis-ee-2`; không dùng project `angelic-digit-434804-r9` ghi trong notebook, không đổi sang project của các nhánh tỉnh cũ. Sáu nhánh dùng chung project và quota, không tạo ra sáu quota độc lập.

| Nhánh | STT cố định | Pilot: toàn tỉnh đầu nhóm | Full |
|---|---|---|---|
| vngis-tinh-001-011 | 1–11 | Hà Nội | 11 tỉnh |
| vngis-tinh-012-022 | 12–22 | Thái Nguyên | 11 tỉnh |
| vngis-tinh-023-033 | 23–33 | Hà Nam | 11 tỉnh |
| vngis-tinh-034-043 | 34–43 | Quảng Ngãi | 10 tỉnh |
| vngis-tinh-044-053 | 44–53 | Lâm Đồng | 10 tỉnh |
| vngis-tinh-054-063 | 54–63 | Trà Vinh | 10 tỉnh |

STT 1–63 **không phải mã thống kê**. Danh sách cố định trong `provinces.json`, theo mã thống kê tăng dần của bộ 63 tỉnh trước sáp nhập. Huế giữ tên lịch sử Thừa Thiên Huế. Sáu nhánh có cùng code/notebook/workflow/docs; chỉ `task_pipeline/branch_range.json` khác hai số start/end. Workflow không cho nhập tỉnh ngoài khoảng. Pilot là **toàn giai đoạn 2004–2025 của tỉnh đầu**, không phải chỉ 12 tháng 2025 hoặc vài xã.

## Chạy trên GitHub

1. Hủy các chuỗi cũ đang chạy/chờ trên các nhánh cũ. Không xóa dữ liệu Drive, config local hoặc marker E. Giữ `pause:true` trong biến cũ để workflow province trên main không tiếp tục xuất; workflow Task123 không dùng cờ pause này để quyết định mode.
2. Dùng sẵn `PROVINCE_CONFIG_JSON` cho project/Drive/budget, `EE_SERVICE_ACCOUNT_JSON` và `RCLONE_CONF`. Không cần thêm secret cho sáu nhánh. Giá trị project trong config phải là `vngis-ee-2`; sai thì báo lỗi, không âm thầm đổi project. Ranh giới tỉnh dùng GADM 4.1 đã pin/crosswalk; không cần asset communes_l3 hoặc quyền truy cập asset cũ trong notebook.
3. Actions → **Task 1-2-3 · 6 nhóm tỉnh cố định** (file `vngis-2024.yml`) → Run workflow. Nếu giao diện đang hiện tên workflow main cũ, chọn theo **file `vngis-2024.yml`**, sau đó chọn nhánh `vngis-tinh-...`.
4. Chọn `mode=pilot` để chạy tỉnh đầu của đúng nhánh. Chọn `full` để chạy cả khoảng của đúng nhánh. Cả hai cùng 2004–2025. Có thể chạy sáu nhánh song song, nhưng tổng EE concurrency dự kiến ít nhất sáu luồng, phụ thuộc quota chung.
5. Mỗi runner xử lý **liên tục**, tối đa khoảng 5 giờ 15 phút/lượt. Thứ tự trong toàn nhóm: TIFF đêm của tất cả tỉnh → CSV đêm/ngày của tất cả tỉnh → TIFF ngày của tất cả tỉnh. Sáu nhóm độc lập, không chờ nhau. Không khởi động runner/workflow mới sau mỗi 10 việc. Khi hết thời lượng, tự gọi lượt kế tiếp cùng nhánh/mode; nếu Drive đầy thì dừng, sau khi nhận về E cần Run workflow lại.
6. Full tái sử dụng các output pilot đã xác minh trong cùng nhánh (cùng scientific job ID và root Drive). Không chạy pilot/full cùng lúc trên cùng nhánh; concurrency của workflow bảo vệ một writer/nhánh.

Một tỉnh 22 năm ở độ phân giải 20/30 m có thể rất nặng. Sáu nhánh giảm chờ do khởi động workflow nhiều lần, không bảo đảm xong trước deadline hoặc vượt được quota của một project.

## Phương pháp đối chiếu ba notebook

Notebook gốc được lưu tại `notebooks/task123/`, giữ nguyên source các cell, bỏ outputs và execution count. `provenance.json` ghi SHA256 upload và SHA256 source cell. Không chạy các cell hỏi nhập xã, đăng nhập Colab, gắn Drive hoặc phân tích đường sá/ảnh minh họa của notebook.

### Task 1 — bảng ngày

- Sentinel từ 2018: năm 2018 dùng `COPERNICUS/S2_HARMONIZED` (TOA), từ 2019 dùng `COPERNICUS/S2_SR_HARMONIZED` (SR), đúng điều kiện year>=2019 trong Task1/2. TOA/SR không được coi như chuỗi đã hài hòa.
- QA60 bit10/11, chia 10000, B2/B3/B4/B8/B11/B12 → BLUE/GREEN/RED/NIR/SWIR1/SWIR2.
- Trong đúng tháng, lọc CLOUDY_PIXEL_PERCENTAGE<85; nếu không còn cảnh, dùng các cảnh cùng tháng trước lọc cảnh. **Vẫn mask QA60**, không phải bỏ mask.
- Median các băng **trước khi** tính NDVI/NDBI/MNDWI/BSI. Sau đó reduceRegions(mean+stdDev), scale50, tileScale4, EPSG4326, một feature là một tỉnh. Không dùng trung bình/std diện tích của các tile thay cho reducer notebook.
- 2004–2017 mở rộng bằng Landsat 5/7/8/9 C02 T1 L2: QA_PIXEL/QA_RADSAT, scale/offset SR đúng nguồn, median rồi chỉ số/reducer như trên. Ba notebook không có đoạn Landsat; đây là phần mở rộng theo xác nhận của người dùng.

### Task 2 — TIFF ngày

- **Theo tháng**, không phải composite năm như pipeline trước. Lấy trong tháng; chỉ khi không có cảnh mới thử cửa sổ ±15, rồi ±30 ngày cùng nguồn như notebook. Không có cảnh cả ba cửa sổ thì null/missing, không đổi cảm biến.
- S2 dùng QA60, median, rồi bốn chỉ số; TIFF 10 băng, 20 m (SWIR không gọi là gốc 10 m). Landsat extension 30 m.
- Task1 CSV giữ đúng tháng, **không dùng ảnh mở rộng thời gian của Task2** để điền bảng tháng. Window, ngày bắt đầu/ngày kết thúc exclusive và asset IDs nằm trong job manifest. Tên file giữ tháng đích; cần đọc provenance nếu window>0.
- Thử tải nguyên tỉnh khi dưới giới hạn 32 MB/10.000 pixel mỗi chiều; nếu lớn hoặc EE báo giới hạn kích thước thì tải các ô tạm cùng lưới rồi ghép trên đĩa thành đúng một TIFF. Không resample/đổi pixel khi ghép. Chỉ upload sau khi mọi ô cần thiết đã hoàn tất và xác minh. Lưới EPSG4326, bước góc=scale/111319.49079327358, tương ứng nominal scale ở xích đạo; không gọi mỗi pixel địa lý đều đúng diện tích 20x20 m ở mọi vĩ độ. Float64 như bước toDouble của notebook + NoData -9999, có band descriptions, không thay số liệu khoa học bằng ảnh PNG.

### Task 3 — TIFF đêm và bảng đêm

- 2014–2025: VIIRS `VCMSLCFG` trước; nếu không có cảnh dùng `VCMCFG` trong cùng tháng (cùng cảm biến, sản phẩm xử lý khác). Ghi collection thực tế. Nếu cả hai thiếu thì null.
- Mean composite, avg_rad + cf_cvg; không thêm mask cháy, Cloud Score+ hoặc ngưỡng 80% coverage của pipeline cũ. TIFF 500 m nominal, EPSG4326.
- Reducer sum/mean/stdDev/min/max/count ở scale500; ngưỡng sáng >=1.5; LIT_POP_PROXY=sum radiance vùng sáng, **không phải dân số thực**; LIT_AREA_HA=lit_count*25 (xấp xỉ notebook); ELECTRIFICATION_RATIO_PCT=100*lit_count/valid_pixel_count (**không phải tỷ lệ hộ có điện**). Các mức làm tròn như Task3.
- TNL_MA3 rolling ba quan sát, min_periods=1 như notebook; nếu bỏ qua kỳ thiếu sẽ ghi NONCONSECUTIVE_OBSERVATIONS. MoM để null khi không có ngay tháng trước, tránh gọi mức thay đổi nhiều tháng là tăng trưởng một tháng. Không xuất inf khi kỳ trước=0.
- 2004–2013 mở rộng bằng DMSP theo năm: chọn satellite system:index lớn nhất, stable_lights DN, ngưỡng DN5; diện tích pixel100ha xấp xỉ ở nominal1000m. Không tạo 12 bản sao tháng. Đây không phải công thức VIIRS được gắn nhãn DMSP và không có hiệu chỉnh liên vệ tinh/liên cảm biến đã kiểm định.

QA60 trong các catalog Sentinel có giai đoạn không sẵn có/masked. Khi mask QA60 làm ảnh toàn NoData, ghi lỗi/chỉ số null, không tự chuyển Cloud Score+ hay nguồn khác rồi tuyên bố vẫn đúng notebook. Cần xem quality report trước khi dùng chuỗi 2004–2025.

### Khác biệt phải giữ rõ

Notebook gọi EE filterDate với ngày cuối tháng là end **exclusive**, vì vậy bỏ ngày cuối tháng. Bản này giữ đúng giới hạn notebook và ghi rõ provenance, không sửa âm thầm. Dữ liệu thiếu/toàn NoData giữ null thay vì `or 0` của một số đoạn notebook. Không dùng zero giả hoặc điền dữ liệu từ cảm biến khác.

Landsat/DMSP, mức tỉnh, tiling, retry/checkpoint, null safety và bảo vệ Drive là mở rộng kỹ thuật; không tuyên bố ba notebook vốn đã hỗ trợ 2004–2025 cấp tỉnh. Không phân loại đất hoặc dashboard. DN DMSP, VIIRS radiance, TOA S2 và SR khác nhau; không coi dữ liệu nối trong CSV là đã harmonize.

## Drive, ổ E và xem kết quả

```text
<Drive root hiện có>/Task123_branches/001_011/
    VN_NTL_Panel_2004_2025/raw_data/NTL/{DMSP,VIIRS}/<mã_tên_tỉnh>/*.tif
    VN_LandCover_Panel_2004_2025/raw_data/DAY/{LANDSAT,SENTINEL2}/<mã_tên_tỉnh>/*.tif
    VN_NTL_Panel_2004_2025/data_processed/night_indices.csv
    VN_LandCover_Panel_2004_2025/data_processed/day_indices.csv
    _control/{state.json,branch_progress.json,manifests,receipts,...}
```

Các nhóm khác đổi 001_011 thành 012_022, 023_033, 034_043, 044_053, 054_063. Ảnh mới nằm trực tiếp trong thư mục tỉnh: đúng một TIFF/tháng (DMSP một TIFF/năm); không tạo PNG mới. Các tile cũ nếu có vẫn được giữ để tránh xóa dữ liệu; nhận diện file mới bằng `_province_`. Hai CSV gộp theo nhánh; mỗi dòng vẫn cấp tỉnh. Tổng full cả sáu nhánh: 9.702 dòng đêm và 16.632 dòng ngày, bao gồm kỳ thiếu.

Artifact mỗi lượt: `task123-<branch>-<mode>`, gồm hai CSV, `branch_progress.json` và báo cáo tiến độ; QA của mọi TIFF nằm trong worker reports. Báo cáo `complete_with_gaps` vẫn có missing/failed; không coi dấu xanh hoặc số dòng đủ là dữ liệu đã đầy đủ/đã kiểm định. DATA_STATUS=`OK_NOTEBOOK` nghĩa là đã tính theo phương pháp, không phải đã kiểm định khoa học.

Ngân sách staging dùng lại từ biến cũ, trừ dữ liệu cũ hiện có rồi chia sáu phần. Mỗi nhánh có margin/share riêng để sáu controller không cùng chiếm toàn bộ 20GB. Khi phần riêng đầy, dừng và nhận về E; không hứa xuất hết lên Drive khi laptop ngủ.

Cập nhật **một** checkout Windows từ bất kỳ nhánh mới nào, giữ local.json/marker/rclone hiện có, cài requirements, đăng ký lại task nếu đổi đường dẫn repo. Script Receive-Satellite.ps1 mới gọi thêm `task_pipeline.receiver` để phát hiện cả sáu root và nhận vào:

```text
E:\SatelliteData\Task123_branches\001_011\...
...
E:\SatelliteData\Task123_branches\054_063\...
```

Giữ bản xác minh/hash/receipt và conditional delete hiện có; dữ liệu remote chỉ xóa sau xác nhận bản trên đúng ổ E. CSV nhỏ giữ trên Drive. Có thể nhận sáu nhóm bằng cùng một task Windows, không cần sáu máy hoặc sáu rclone configs. Lệnh nhận riêng (cần env rclone như receiver cũ):

```powershell
& $python -m task_pipeline.receiver --config province_pipeline/config/local.json
```

GitHub có thể vẫn có các run cũ đang chạy sau khi xóa nhánh; xóa nhánh không hủy run. API ở môi trường triển khai hiện bị Forbidden nên người dùng cần hủy các run cũ bằng giao diện. Không xóa project Google Cloud, secrets, dữ liệu Drive/E, main, inspriring-newton hoặc nhánh districts khi dọn bốn nhánh tên tỉnh cũ.


## TIFF-only và cập nhật runner/receiver

1. Hủy các lượt đang chạy/chờ trước khi khởi động lại bằng code mới. Không xóa dữ liệu, state, receipts hoặc marker E.
2. Chọn nhánh như cũ và mode pilot/full. Project vẫn vngis-ee-2, một TIFF/tỉnh/tháng cho VIIRS/ảnh ngày và một TIFF/tỉnh/năm cho DMSP. Tên mới có `_province_` và không có số ô.
3. Không tạo hoặc upload PNG tự động, không kèm PNG trong manifest mới. QA pixel vẫn chạy. TIFF toàn tỉnh đã hoàn thành giữ nguyên ID, không bị tải lại chỉ vì bỏ PNG. Reservation chưa chạy theo kiểu cặp sẽ được chuyển sang TIFF-only.
4. PNG và các manifest cặp đã tạo trước đây được giữ tương thích để tránh mất dữ liệu. Không tự xóa các PNG hoặc tile cũ.
5. Mở TIFF float64 nhiều băng/BigTIFF bằng QGIS. TIFF ngày chọn RED/GREEN/BLUE; NTL chọn stable_lights/avg_rad và stretch. Bỏ PNG không bảo đảm trình xem TIFF web hỗ trợ các kiểu dữ liệu khoa học này.
6. Cập nhật checkout Windows từ một nhánh mới, giữ config local/rclone/marker hiện có. Kết quả vẫn về thư mục tỉnh dưới E:\SatelliteData\Task123_branches\... và conditional-delete sau xác minh như trước.

Ảnh lớn vẫn ghép các ô tạm thành một TIFF trước khi upload; không đổi pixel, không âm thầm giảm độ phân giải. Nếu file nén vượt output cap hoặc runner thiếu ổ đĩa, báo OUTPUT_LIMIT, không xuất file thiếu/cắt cụt. Ảnh nguồn thực sự toàn NoData vẫn bị từ chối. Không điền dữ liệu từ nguồn/kỳ khác ngoài phương pháp Task2 đã công bố.
