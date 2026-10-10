# Setup dữ liệu cấp huyện: tháng 07/2024–06/2025

Branch: **`vngis-ee-districts-202407-202506`**. Dùng `vngis_2024.py`, `verify_pilot.py` và `.github/workflows/vngis-2024.yml` ở thư mục gốc. Thư mục `vngis-github-repo-v6` là bản lưu cũ.

**Mặc định hiện tại khi chọn `mode=full`: `scope=repair_csv`, chỉ sửa CSV của 5 huyện ở mục 16.** Phần từ `55.8` đến cuối đã được người dùng xác nhận hoàn tất. Chỉ chọn `scope=range` khi muốn lấy TIFF/CSV theo phạm vi ở mục 14.

| Thành phần | Cấu hình |
|---|---|
| Phạm vi | GADM toàn quốc: **710 đơn vị cấp huyện, 63 tỉnh/thành**; nhánh mặc định chỉ sửa CSV của **5 mã** ở mục 16 |
| Ranh giới | GADM 4.1 Việt Nam, level 2; geometry huyện, mã `GID_2` |
| Tháng | 2024-07 đến 2025-06, **12 tháng**, bao gồm hai đầu |
| Project EE mặc định | `vngis-ee-2`, tái sử dụng project hiện có |
| Asset mặc định | `projects/vngis-ee-2/assets/districts_l2` |
| Drive nhận kết quả | **`adt.wqiqc@gmail.com`**, remote `gdrive` |
| TIFF ngày mặc định trên Actions | **50 m**, Int16, 10 kênh; có tùy chọn 20 m |
| Thư mục full 50 m | `VNGISDash_202407_202506_Districts_50m` |
| Thư mục pilot 50 m | `VNGISDash_202407_202506_Districts_50m_PILOT` |
| Secrets | `EE_SERVICE_ACCOUNT_JSON`, `RCLONE_CONF` |

710 đơn vị gồm 543 huyện, 49 quận, 50 thị xã và 68 thành phố. Đây là ranh giới GADM 4.1 cố định, không phải danh mục hành chính sau sáp nhập. Asset xã `communes_l3` không thể thay bảng huyện chỉ bằng đổi tên.

## 1. Bộ shapefile cấp 2 đã chuẩn bị

Bộ ZIP upload là **`gadm41_VNM_2.zip`**, chứa đúng năm file cùng tên:

```text
gadm41_VNM_2.shp
gadm41_VNM_2.shx
gadm41_VNM_2.dbf
gadm41_VNM_2.prj
gadm41_VNM_2.cpg
```

Bộ file đã được tạo từ [nguồn GADM 4.1 chính thức](https://geodata.ucdavis.edu/gadm/gadm4.1/shp/gadm41_VNM_shp.zip), giữ nguyên geometry và thuộc tính. CSV `districts_l2_admin.csv` đi kèm để kiểm tra tên và mã; **CSV không thay thế shapefile vì không có geometry**. `SOURCE.md` ghi nguồn, số bản ghi và SHA-256. File dữ liệu được chuẩn bị cục bộ, không đưa khóa hay token vào repository; xem [điều kiện sử dụng GADM](https://gadm.org/license.html).

Trong workspace đã chuẩn bị: `/workspace/artifacts/gadm41_VNM_2/gadm41_VNM_2.zip`.

Để tạo lại ngay từ repo, không cần geopandas hoặc tìm dữ liệu thủ công, mở terminal ở thư mục chứa repo rồi chạy (Python 3):

```bash
python tools/prepare_district_gadm.py
```

Script tự tải nguồn qua HTTPS, kiểm tra ZIP, đọc DBF và xác nhận 710 `GID_2` duy nhất / 63 tỉnh. Kết quả tại **`artifacts/gadm41_VNM_2/gadm41_VNM_2.zip`**, cùng các file rời, bảng tên và nguồn. Có thể chạy lại lệnh để tái tạo. Nếu đã có ZIP gốc:

```bash
python tools/prepare_district_gadm.py --archive /duong/dan/gadm41_VNM_shp.zip
```

## 2. Project, Earth Engine API và service account

1. Đăng nhập tài khoản đang quản lý [project `vngis-ee-2`](https://console.cloud.google.com/home/dashboard?project=vngis-ee-2). Kiểm tra **Project ID**, không chỉ tên hiển thị.
2. Trong [Earth Engine configuration](https://console.cloud.google.com/earth-engine/configuration?project=vngis-ee-2), kiểm tra project đã đăng ký đúng mục đích sử dụng. Trong **APIs & Services**, bật **Google Earth Engine API**.
3. Có thể dùng service account/JSON mà nhánh main đang dùng. Trong **IAM & Admin → IAM**, cấp hai role trên project cho **email service account trong trường `client_email` của JSON**:
   - **Service Usage Consumer** (`roles/serviceusage.serviceUsageConsumer`).
   - **Earth Engine Resource Writer** (`roles/earthengine.writer`).
4. Nếu cần khóa mới: **IAM & Admin → Service Accounts → chọn account → Keys → Add key → JSON**. Lưu file kín và đưa vào GitHub Secret, không upload vào mục Code của repo.

Project quyết định quota thông qua `ee.Initialize(project=...)`; domain trong email service account không tự quyết định project chịu quota. Actions thử tối đa **4 yêu cầu đồng thời**, chung cho truy vấn, tạo URL và tải ảnh. Khi gặp 429, số slot giảm 4 → 2 → 1; nếu thông báo Restricted Mode thì giảm ngay về 1, vẫn chờ Retry-After/backoff. Không tự tăng lại trong lượt. Các workflow khác dùng cùng project vẫn chia sẻ quota; branch mới không tăng quota. Khi project còn bị giới hạn, có thể đặt variable về 1 ngay từ đầu.

## 3. Upload asset districts_l2

1. Mở [Earth Engine Code Editor](https://code.earthengine.google.com/) bằng tài khoản có quyền trên project.
2. Chọn project `vngis-ee-2`. Trong **Assets**, thêm cloud project nếu chưa hiện.
3. Chọn **NEW → Table upload → Shape files**, tải **`gadm41_VNM_2.zip`** đã chuẩn bị hoặc chọn cùng lúc năm file rời ở mục 1.
4. Asset ID phải là **`projects/vngis-ee-2/assets/districts_l2`**. Đặt Asset Name `districts_l2`, bắt đầu upload và đợi tác vụ trong **Tasks** hoàn tất.
5. Bảng phải có geometry và các cột `GID_1`, `NAME_1`, `GID_2`, `NAME_2`, `TYPE_2`.

Kiểm tra bằng đoạn JavaScript sau trong Code Editor:

```javascript
var districts = ee.FeatureCollection('projects/vngis-ee-2/assets/districts_l2');
print('Số huyện, phải là 710:', districts.size());
print('GID_2 duy nhất, phải là 710:', districts.aggregate_count_distinct('GID_2'));
print('Số tỉnh, phải là 63:', districts.aggregate_count_distinct('GID_1'));
print('Metadata và geometry:', districts.first());
Map.addLayer(districts, {}, 'GADM 4.1 cấp huyện');
```

Nếu **asset ID đã tồn tại**, đóng upload và kiểm tra asset hiện có. Nếu đúng bảng cấp 2, dùng lại. Nếu sai hoặc cần bản mới, upload dưới tên `districts_l2_v2`, rồi đặt repository variable `VNGIS_DISTRICTS_EE_ASSET` thành đường dẫn đầy đủ mới. Không cần xóa asset cũ. Nếu dùng bảng huyện ở project khác, chủ asset cấp quyền đọc cho service account chạy pipeline và cấu hình variable đường dẫn; project chịu quota vẫn là project EE đã chọn.

## 4. Drive adt.wqiqc@gmail.com

Remote `gdrive` và token Drive độc lập với service account EE. Nếu remote đã đăng nhập đúng **`adt.wqiqc@gmail.com`**, dùng lại cấu hình hiện có.

Trên Windows, mở CMD ở thư mục có `rclone.exe` (hoặc nơi bất kỳ nếu rclone đã có trong PATH):

```text
rclone config
```

Tạo/chỉnh remote `gdrive`, storage Google Drive, scope **1 (Full access)**, service account file trống, `root_folder_id` trống. Dùng trình duyệt để OAuth bằng **`adt.wqiqc@gmail.com`**. Khi hỏi **Configure this as a Shared Drive (Team Drive)?**, chọn **`n`**. Nếu cần xác thực lại:

```text
rclone config reconnect gdrive:
```

Chọn thay token `y`, xác thực qua trình duyệt `y`, đúng email, rồi Shared Drive `n`.

**OAuth Client ID riêng:** client Google Drive dùng chung của rclone đang được ngừng hỗ trợ trong năm 2026. Làm theo [hướng dẫn chính thức](https://rclone.org/drive/#making-your-own-client-id): bật Google Drive API trong project bạn quản lý, cấu hình OAuth consent cho phép tài khoản nhận Drive, tạo OAuth client **Desktop app**, điền `client_id` và `client_secret` vào remote, rồi reconnect. Với OAuth External ở trạng thái Testing và quyền Drive, refresh token thường hết hạn sau 7 ngày; cấu hình trạng thái xuất bản phù hợp trước khi chạy lâu dài. Project OAuth Drive có thể khác project EE.

Kiểm tra:

```text
rclone lsd gdrive:
rclone mkdir "gdrive:VNGISDash_202407_202506_Districts_50m"
rclone config show gdrive
```

Mở Drive bằng `adt.wqiqc@gmail.com`, kiểm tra thư mục vừa tạo. Copy toàn bộ cấu hình gồm `[gdrive]` vào GitHub Secret ở mục 5. Không gửi token lên chat. Kiểm tra dung lượng Drive đủ cho TIFF trước khi chạy full; ít file hơn cấp xã không có nghĩa tổng dung lượng ảnh giảm tương ứng.

## 5. GitHub Secrets và Variables

Repo → **Settings → Secrets and variables → Actions → Secrets**:

| Secret | Nội dung |
|---|---|
| `EE_SERVICE_ACCOUNT_JSON` | Toàn bộ JSON service account có quyền trên project và asset huyện |
| `RCLONE_CONF` | Toàn bộ cấu hình `[gdrive]` đã OAuth bằng `adt.wqiqc@gmail.com` |

Nếu hai secrets main đang dùng đã đúng thì không cần tạo thêm hay thay đổi. Repository secrets không thuộc riêng một branch; thay giá trị này cũng ảnh hưởng workflow khác sử dụng cùng tên.

Trong tab **Variables**, tùy chọn:

| Variable | Mặc định / ý nghĩa |
|---|---|
| `VNGIS_DISTRICTS_EE_PROJECT` | `vngis-ee-2`; project truyền vào `ee.Initialize` |
| `VNGIS_DISTRICTS_EE_ASSET` | Trống → `projects/<project>/assets/districts_l2` |
| `VNGIS_DISTRICTS_EE_CONCURRENCY` | Mặc định `4`, tự giảm khi 429; đặt `1` nếu project đang Restricted Mode |
| `VNGIS_DISTRICTS_REST_EVERY_N` | `10`; nghỉ sau mỗi 10 huyện mới hoàn tất trong một lượt; `0` tắt mốc này |
| `VNGIS_DISTRICTS_REST_AFTER_PROVINCE` | `true`; nghỉ khi toàn bộ huyện của một tỉnh đã hoàn tất; `false` tắt mốc này |
| `VNGIS_DISTRICTS_REST_SEC` | `30`; số giây nghỉ chủ động; `0` tắt toàn bộ nghỉ chủ động |

Nếu đã tạo variable concurrency=`1` theo bản hướng dẫn cũ, nó vẫn được ưu tiên. Để thử chế độ nhanh, đặt `4`; theo dõi log `[quota]` tự hạ mức khi cần, không tiếp tục tăng khi lỗi quota.

Khi chạy Python trực tiếp, tên tương ứng là `VNGIS_EE_PROJECT`, `VNGIS_EE_ASSET`, `VNGIS_EE_CONCURRENCY`; thêm `VNGIS_DAY_IMAGE_SCALE=50` cho TIFF 50 m. Python trực tiếp giữ mặc định 20 m/1 yêu cầu để tương thích bản cũ; Actions mặc định 50 m/4 yêu cầu. Khoảng tháng trên workflow cố định `2024-07`/`2025-06`. Manifest/profile chứa scale để không dùng nhầm trạng thái 20 m cho 50 m.

Trong **Settings → Actions → General**, policy phải cho phép workflow tự dispatch (`actions: write`). YAML khai báo `contents: read` và `actions: write`.

## 6. Pilot rồi full

1. **Actions → workflow `vngis-2024.yml` → Run workflow → Use workflow from `vngis-ee-districts-202407-202506`**. Tên trên trang Actions có thể vẫn lấy từ main.
2. Chọn **`mode=pilot`, `pilot_n=6`, `workers=4`, `day_scale=50`** để đo tốc độ. Pilot từ 6 huyện trở lên lấy cả huyện đầu tiên/đô thị và các huyện phân bố trên cả nước; mọi huyện chạy đủ 12 tháng. Pilot 2 vẫn lấy huyện/đô thị đầu tiên như trước. Ô `stop_after_province` chỉ giữ tương thích giao diện main và bị bỏ qua.
3. Log phải ghi đúng project, asset, khoảng tháng và huyện thử; preflight kiểm tra Drive, ảnh ngày/đêm và ghép ô giữ pixel. `verify_pilot.py` kiểm tra file TIFF, độ phân giải, kiểu dữ liệu, năm/tháng và CSV. Thiếu dữ liệu sẽ báo FAIL, không coi là đủ.
4. Full lưu vào `VNGISDash_202407_202506_Districts_50m`. Pilot/full dùng thư mục riêng. Mặc định **`mode=full`, `scope=repair_csv`, `day_scale=50`** chỉ sửa 5 huyện theo mục 16.
5. Để lấy TIFF/CSV toàn quốc, chọn **`mode=full`, `scope=range`, `start_gid=VNM.1.1_1`**. Full toàn quốc phải ghi **710 huyện, 63 tỉnh**. Khi hoàn tất đầy đủ, mỗi CSV có **8.520 dòng huyện–tháng**, có 12 TIFF ngày và 12 TIFF đêm mỗi huyện (tổng 8.520 file mỗi loại).

Sentinel-2 ngày: median, 10 kênh BLUE/GREEN/RED/NIR/SWIR1/SWIR2/NDVI/NDBI/MNDWI/BSI; TIFF **Int16, 50 m mặc định trên Actions, scale 0.0001, offset 0, NoData -32768**. Đọc giá trị thực bằng **DN × 0.0001**. Trong miền biểu diễn, sai số lượng tử hóa tối đa 0.00005; giá trị vượt miền ±3.2767 gây lỗi rõ ràng, không tự cắt. TIFF đêm vẫn avg_rad/cf_cvg float64, 500 m.

TIFF 50 m có số pixel xấp xỉ **1/6,25** so với 20 m cho cùng vùng, giảm dữ liệu cần tải và số ô cần ghép; đây là giảm độ phân giải không gian theo lựa chọn của người dùng. Dùng scale của API Earth Engine, giữ CRS/công thức/band. CSV giữ phép tính gốc, không tính từ TIFF 50 m. Nén DEFLATE mức 6 vẫn không mất dữ liệu. Kích thước chia ô được dùng lại cho các tháng sau, tránh thử cả ảnh vượt giới hạn nhiều lần.

Nếu chọn **`day_scale=20`**, dùng lại thư mục `VNGISDash_202407_202506_Districts` / `_PILOT` cũ và trạng thái 20 m. Không đổi manifest hay trộn hai độ phân giải trong cùng thư mục.

CSV được tính **trên ảnh float gốc ở Earth Engine**, trước và độc lập với lượng tử hóa TIFF; Task 1 giữ mean/stdDev ở scale **50 m**. Trước tiên dùng cảnh có CLOUDY_PIXEL_PERCENTAGE < 85; nếu có kênh thiếu mean sau mask, thử toàn bộ cảnh **của đúng tháng đó**, vẫn giữ mask QA60, median và công thức chỉ số. Log ghi kênh thiếu, số cảnh và số pixel mỗi kênh. Nếu vẫn không có pixel hợp lệ, giữ null/no_data; không mở rộng tháng để lấp CSV. TIFF ngày giữ lựa chọn cửa sổ tháng, rồi ±15/±30 ngày khi không có cảnh. Ngày cuối tháng được bao gồm bằng end-exclusive là ngày đầu tháng tiếp theo.

Int16 giảm dung lượng TIFF lưu trên máy/Drive; bước chuyển đổi thực hiện theo block sau khi tải, nên giới hạn 32 MB mỗi yêu cầu Earth Engine vẫn có thể cần chia ô. Không tính lại CSV từ TIFF Int16. Công thức chỉ số đêm không thay đổi.

CSV metadata dùng `GID_2`, `NAME_2`, `TYPE_2` và `YEAR`, `MONTH`. `DISTRICT_AREA_HA` là diện tích huyện. Rolling TNL qua tháng 12 sang tháng 1 liên tục; tháng thiếu giữ null, tăng trưởng không lấy tháng xa hơn để lấp khoảng trống. `DATA_STATUS=no_data`/`ERROR` thể hiện không có cảnh hoặc pixel hợp lệ; không điền 0 để giả lập đo đạc.

## 7. Trạng thái, dừng và chạy tiếp

```text
Day/<GID_1>_<tỉnh>/<GID_2>_<huyện>/<GID_2>_day_YYYYMM.tif
Night/<GID_1>_<tỉnh>/<GID_2>_<huyện>/<GID_2>_night_YYYYMM.tif
CSV/day_indices.csv
CSV/night_indices.csv
_control/pipeline.json
_control/status/
_control/parts/
_control/progress.csv
_control/logs/
```

- Mỗi lượt tối đa 5 giờ 15 phút rồi đồng bộ và tự nối trên **cùng branch**, cùng mode/pilot_n/workers/day_scale/start_gid. Khoảng tháng và project đọc từ workflow/variables của branch.
- Trạng thái chứa `gid_2`, `period=202407-202506`, profile và khóa tháng `YYYY-MM`; không dùng trạng thái xã hoặc của khoảng khác.
- Checkpoint sau từng tháng tải xong giúp tiếp tục phần còn lại. TIFF/CSV đã báo xong nhưng thiếu trên Drive và máy hiện tại sẽ được tính/tải lại.
- Chỉ `done` khi cả TIFF ngày/đêm và CSV ngày/đêm đủ dữ liệu hợp lệ cho mọi tháng. `no_data` không coi là hoàn thành. Hết ba lần thử mà còn thiếu thì workflow báo lỗi, không nối vô hạn hoặc báo thành công.
- Dừng trật tự: tạo **`STOP` trên branch này**, hoặc `_control/STOP` trong thư mục Drive đang chạy. Chờ lượt đồng bộ cuối và thoát. STOP trên main không chặn branch huyện.
- Tiếp tục: xóa STOP đúng chỗ, chọn **Run workflow** trên branch này, cùng mode. Không xóa `_control/status` hoặc `_control/parts`.
- Dữ liệu thiếu đã hết lần thử: xác định nguyên nhân trong progress/log, khắc phục rồi tăng `VNGIS_MAX_ATTEMPTS` trong workflow cho lượt mới nếu cần. Không đặt status=done bằng tay.
- Final sync thất bại trả mã 1. Lượt chạy lại đối chiếu file hiện có để phục hồi TIFF/CSV chưa đồng bộ. Ảnh lớn được chia ô cùng scale và ghép theo block trên đĩa, không giảm độ phân giải hoặc resample. File `.part` chưa hoàn tất không được upload.

### Nâng cấp lượt float đã chạy trước bản sửa

Tạo STOP trên branch, chờ lượt cũ đồng bộ và kết thúc, rồi xóa STOP và **Run workflow tạo lượt mới**. Lượt đang chạy dùng code cũ. Để nâng cấp dữ liệu cũ giữ 20 m, chọn `day_scale=20`; không cần xóa kết quả. Chọn `50` sẽ dùng thư mục 50 m riêng và không lấy trạng thái 20 m để báo hoàn tất.

Pipeline tự nhận manifest float cũ của đúng kỳ/cấp: giữ TIFF đêm và CSV đêm, tính lại CSV ngày theo chính sách bổ sung ở trên. TIFF ngày đã có được lấy từ Drive và chuyển Int16 cục bộ, không tải lại ảnh đó từ Earth Engine. Nếu file thực sự mất, pipeline tải lại tháng tương ứng. `_control/int16_uploaded.json` chỉ đánh dấu TIFF Int16 đã upload; file float còn trên Drive không được nhầm là đã hoàn tất nâng cấp.

Nếu trước đây gặp `rclone copyto ... directory not found`, bản sửa đối chiếu file với danh sách Drive trước khi chuyển đổi. File có tên GID cũ/thư mục cũ được nhận diện khi chỉ có một nguồn phù hợp. Nếu không tìm thấy file, hoặc file mất sau lúc liệt kê, tải lại đúng tháng từ EE thay vì lặp copyto. Lỗi quyền/token/kết nối vẫn được báo riêng. Các trạng thái đã hết lần thử do nguồn chuyển đổi bị thiếu được mở lại một lần; lỗi dữ liệu thật sau đó vẫn bị giới hạn số lần thử. Không cần xóa `_control` để phục hồi.

Uploader và đối chiếu trạng thái dùng cùng khóa; chuyển file lên Drive không làm reset số lần thử. Kể cả một lượt rclone chỉ chuyển được một phần, những file chuyển thành công vẫn được ghi nhận. Dữ liệu thực sự thiếu chỉ thử đến giới hạn `VNGIS_MAX_ATTEMPTS`, rồi báo lỗi. Nếu log vẫn ghi CSV ngày 07/2024 no_data, xem chẩn đoán số cảnh/pixel thay vì chạy lặp vô hạn.

## 8. Xử lý lỗi

| Lỗi | Kiểm tra |
|---|---|
| 403/permission | Project ID, đăng ký EE, hai role cho đúng email service account, quyền đọc asset |
| Asset không có GID_2 / nhiều bản ghi | Đúng bảng level 2, GID_2 duy nhất, 710 bản ghi; không dùng communes_l3 |
| 429 / Restricted Mode | Xem log tự hạ concurrency; đặt variable 1 nếu còn bị giới hạn, hạn chế workflow khác cùng project |
| TIFF quá lớn | Giữ scale; pipeline chia ô tối đa 32×32; kiểm tra RAM/disk/timeout nếu vẫn lỗi |
| Lệch lưới/chồng lấn | Dừng báo lỗi; không ghép bằng nội suy để che lỗi |
| Drive đầy/token hết hạn | Dung lượng tài khoản nhận; reconnect remote đúng email, cập nhật secret nếu cần |
| copyto directory not found khi nâng cấp | Dùng bản sửa mới; đối chiếu nguồn thật, file mất được tải lại từ EE; không đổi secret chỉ vì thiếu file |
| files-from overrides all other filters | Dùng bản sửa chọn file đủ 2 phút trong Python; lệnh move chỉ dùng files-from, không kết hợp min-age/filter; final sync lấy mọi TIFF hoàn chỉnh |
| Manifest khác khoảng/cấp | Chọn thư mục kết quả khác cho cấu hình mới |
| Skipped vì STOP | Xóa STOP trên đúng branch, Run workflow tạo lượt mới |

## 9. Kiểm thử local/cloud

Trong checkout hiện có, không cần Git worktree:

```bash
python -m venv /tmp/vngis-districts-venv
/tmp/vngis-districts-venv/bin/pip install -r requirements.txt
/tmp/vngis-districts-venv/bin/python -m unittest discover -s tests -v
```

Kiểm thử offline dùng EE giả lập và TIFF thật nhỏ để xác minh date graph, schema, pixel, resume và lỗi. Không chứng minh quyền/quota hoặc tốc độ xử lý EE thực tế. Pilot thật cần project/asset và hai secrets; workspace hiện chưa có cấu hình rclone để chạy Drive trực tiếp.

## 10. Chạy nhanh để ưu tiên mốc trưa 10/10/2026

Đã thống nhất giảm TIFF ngày từ 20 m xuống **50 m**, giữ 10 kênh và CSV gốc. Dùng project/asset/Secrets hiện có; dừng lượt code cũ bằng STOP, chờ đồng bộ, xóa STOP rồi tạo lượt mới.

1. Kiểm tra variable `VNGIS_DISTRICTS_EE_CONCURRENCY`: đặt `4` để thử mức nhanh; giá trị `1` cũ sẽ ghi đè mặc định. Tạm dừng các workflow khác đang dùng cùng project `vngis-ee-2` để tránh tranh quota.
2. Chạy `pilot`, `pilot_n=6`, `workers=4`, `day_scale=50`. Log đầu phải ghi **50 m**, tối đa 4 yêu cầu. Preflight đọc dung lượng Drive còn trống, kiểm tra chia ô; sau đó xem file/report trong folder `_50m_PILOT`.
3. Khi pilot PASS, chạy `full`, `workers=4`, `day_scale=50`. Đích là `VNGISDash_202407_202506_Districts_50m` trên tài khoản nhận cũ.
4. Theo dõi log **`[speed]`**: chỉ đếm huyện `done`, báo huyện/giờ và ETA tham khảo theo giờ Việt Nam. Log `[quota]` cho biết nếu số yêu cầu đã bị hạ. `partial` không được cộng vào tốc độ hoàn tất.

710 huyện × 12 tháng tương ứng 8.520 TIFF ngày + 8.520 TIFF đêm và 8.520 dòng cho mỗi CSV khi đủ dữ liệu. Nếu chưa có huyện full nào xong, 60 huyện/giờ cần khoảng **11 giờ 50 phút**, 90 huyện/giờ cần khoảng **7 giờ 53 phút**, 30 huyện/giờ cần khoảng **23 giờ 40 phút**. Cộng thêm thời gian pilot, khởi động các lượt và đồng bộ cuối. Tốc độ không nhất thiết tăng 6,25 lần khi số pixel giảm 6,25 lần: truy vấn CSV, tính composite, hạn mức compute, network và Drive vẫn ảnh hưởng.

Sau 30–60 phút full, so sánh `(710 - số huyện done) / tốc độ thực tế` với thời gian còn lại tới **12:00 10/10/2026, UTC+7**. ETA ban đầu có thể lạc quan vì huyện lớn/mây nhiều xử lý lâu hơn. Nếu project tiếp tục Restricted Mode và tự giảm về 1, hoặc tốc độ thấp hơn mức cần đạt, không có căn cứ cam kết kịp mốc này chỉ bằng chỉnh code. Không tăng số project/tài khoản để né quota; không đổi CSV thiếu thành số 0/done.

## 11. Nghỉ chủ động và các tham số tốc độ

Mặc định **nghỉ 30 giây sau mỗi 10 huyện mới hoàn tất, hoặc khi hoàn tất toàn bộ huyện của một tỉnh**. Nếu huyện thứ 10 cũng là huyện cuối tỉnh thì chỉ nghỉ một lần 30 giây. Mốc tỉnh dựa trên toàn bộ bảng GADM cấp 2 và tính cả huyện đã hoàn tất ở lượt trước; pilot chỉ lấy một phần tỉnh không được coi là hoàn tất cả tỉnh. Huyện `partial`, thiếu dữ liệu, lỗi hoặc thử lại cùng huyện đã xong không được cộng vào bộ đếm.

Khoảng nghỉ áp dụng cho tất cả luồng Earth Engine: chặn yêu cầu mới, đợi yêu cầu đang chạy kết thúc, rồi bắt đầu tính đủ 30 giây. Uploader vẫn đồng bộ các file đã tải lên Drive. STOP hoặc hết giờ của lượt ngắt được cả lúc đợi lẫn lúc nghỉ; trạng thái huyện đã xong vẫn được giữ để nối lượt. Bộ đếm huyện mới được giữ qua các vòng thử lại trong cùng lượt Actions, và bắt đầu lại ở lượt Actions tiếp theo.

Log có dạng:

```text
[rest] đã hoàn tất 10 huyện mới trong lượt (mỗi 10 huyện): chờ các yêu cầu EE đang chạy kết thúc.
[rest] Nghỉ chủ động 30s cho tất cả luồng EE; đồng bộ Drive vẫn chạy.
[rest] Hết thời gian nghỉ, tiếp tục lấy dữ liệu.
```

Không cần tạo Variables để bật cơ chế này. Để chỉnh, dùng ba repository Variables ở mục 5. Khi chạy Python trực tiếp, tên tương ứng là **`VNGIS_REST_EVERY_N`**, **`VNGIS_REST_AFTER_PROVINCE`**, **`VNGIS_REST_SEC`**. Nghỉ cố định giúp giảm tải từng đợt; backoff khi lỗi 429 vẫn hoạt động riêng và quota Google không thay đổi. Với 710 huyện chạy mới trong một lượt, 70 mốc 10 huyện và 63 mốc tỉnh thêm tối đa khoảng **66,5 phút nghỉ**, ít hơn khi các mốc trùng nhau; chưa tính thời gian đợi yêu cầu đang chạy kết thúc.

Các tham số dưới đây là giá trị mặc định trên **workflow của nhánh huyện**; Python trực tiếp và Variables đang tồn tại có thể khác:

| Tham số trong Python / YAML | Mặc định Actions | Tác động và nơi chỉnh |
|---|---|---|
| `VNGIS_WORKERS` | `4` | Số huyện xử lý song song; chỉnh ô `workers` khi Run workflow |
| `VNGIS_MONTH_THREADS` | `2` | Số tác vụ tải ảnh song song trong mỗi huyện; chỉnh YAML |
| `VNGIS_EE_CONCURRENCY` | `4`, tự giảm khi 429 | Giới hạn chung số yêu cầu EE đang chạy, gồm CSV/tạo URL/tải TIFF; chỉnh variable `VNGIS_DISTRICTS_EE_CONCURRENCY` |
| `VNGIS_DAY_IMAGE_SCALE` | `50` m | Quyết định số pixel TIFF ngày; chỉnh ô `day_scale` (20 hoặc 50). Không đổi phép tính CSV |
| `VNGIS_DAY_BANDS` | `10` | Số kênh TIFF ngày, ảnh hưởng dung lượng; giữ 10 để đủ bộ kênh đã thống nhất |
| `VNGIS_DAY_FORMAT` / `VNGIS_DAY_SCALE` | `int16` / `10000` | Định dạng lưu và hệ số lượng tử hóa; `10000` là hệ số giá trị, không phải độ phân giải mét. Chuyển Int16 ở máy chạy sau tải, chủ yếu giảm dung lượng lưu/upload |
| `VNGIS_TIFF_ZLEVEL` | `6` | Mức nén DEFLATE 1–9; mức cao thường tốn CPU hơn, nén không mất dữ liệu |
| `VNGIS_UPLOAD_EVERY_SEC` | `300` s | Chu kỳ đồng bộ Drive; giảm chu kỳ làm file xuất hiện sớm hơn, không tăng tốc EE |
| `VNGIS_REST_EVERY_N` / `VNGIS_REST_AFTER_PROVINCE` / `VNGIS_REST_SEC` | `10` / `true` / `30` s | Mốc và thời gian nghỉ chủ động; chỉnh ba Variables ở mục 5 |
| `VNGIS_EE_MAX_RETRIES` | `8` | Số lần thử mỗi thao tác EE; thời gian backoff gốc tăng 5 → 10 → 20 → 40 → 60 giây, cộng jitter và tuân theo Retry-After |
| `VNGIS_MAX_RUNTIME_SEC` | `18900` s | Thời lượng một lượt 5 giờ 15 phút; hết giờ thì đồng bộ và nối lượt, không phải tốc độ mỗi huyện |
| `RCLONE_COMMON` trong `vngis_2024.py` | `--transfers 2`, `--checkers 4`, `--tpslimit 2` | Song song và giới hạn tốc độ API khi tải lên Drive; cấu hình trong code, độc lập với giới hạn EE |

`workers=4` × `MONTH_THREADS=2` có thể tạo 8 tác vụ tải ảnh, nhưng **tối đa 4 yêu cầu EE đang chạy** do giới hạn chung; nếu bị hạ về 1 thì tăng workers không vượt qua được giới hạn này. TIFF đêm giữ 500 m. Huyện lớn phải chia nhiều ô và project Restricted Mode vẫn có thể chậm dù có nghỉ chủ động. Xem `[speed]`, `[quota]`, `[rest]` để đo tốc độ và các khoảng nghỉ thực tế.

Bản sửa chỉ áp dụng cho lượt mới: chờ lượt cũ kết thúc, hoặc tạo STOP trên đúng branch rồi đợi đồng bộ xong, xóa STOP và Run workflow. Thư mục Drive, project, asset và Secrets giữ nguyên.

## 12. Lượt trước đã xong nhiều huyện nhưng lượt mới lại xếp 710 huyện

`Danh sách: 710 huyện` là tổng phạm vi, còn **`Vòng mới: ... huyện cần xử lý`** là số huyện thực sự chưa hoàn tất. Nếu lượt trước xong 610 thì khi checkpoint/file/CSV đã đồng bộ đủ, lượt sau chỉ cần xử lý khoảng 100 huyện còn lại.

Bản cũ có lỗi ở `--sync-only`: Python mới bắt đầu với danh sách TIFF Int16 trong RAM rỗng, rồi ghi đè `_control/int16_uploaded.json` thành rỗng. Do đó ảnh ngày đã tải có thể bị đưa lại vào hàng đợi nâng cấp và huyện mất trạng thái hoàn tất. Bản sửa nạp marker đã lưu trước khi ghi, và nếu không có bản local thì đọc marker từ Drive; lỗi đọc/quyền không được coi là marker rỗng để ghi đè.

Để phục hồi marker bị xóa hoặc thiếu một phần bởi lỗi cũ, chỉ với **thư mục 50 m có manifest khớp**, code dùng checkpoint cùng profile Int16, các tháng ảnh ngày đã xác nhận `ok` và TIFF đúng đường dẫn thực có trên Drive. Không dùng trạng thái khác kỳ/profile hoặc dữ liệu float 20 m để đánh dấu xong. CSV vẫn phải có các bản ghi parts hợp lệ; ảnh thiếu vẫn bị đưa vào hàng đợi. Không suy ra `done` chỉ từ số lượng hoặc tên TIFF.

Log `[resume]` ghi đích/profile, số file checkpoint được kéo về, số huyện có trạng thái/đã hoàn tất, số TIFF/marker và số bản ghi CSV parts ngày/đêm. Nếu đã có TIFF mà không có trạng thái hợp lệ, hoặc tất cả huyện từng có checkpoint hoàn tất đều bị mất bằng chứng, pipeline dừng trước preflight để tránh chạy lại toàn bộ âm thầm. Kiểm tra đúng tài khoản OAuth Drive, đúng folder full/pilot/20m/50m, `_control/status`, `_control/parts`, marker và lỗi đồng bộ của lượt cũ. **Không xóa `_control` hoặc đổi folder khi muốn nối lượt.**

Chỉ khi chủ động muốn tải lại toàn bộ mới đặt repository variable **`VNGIS_DISTRICTS_ALLOW_FULL_RESTART=true`** (Python trực tiếp: `VNGIS_ALLOW_FULL_RESTART=true`). Không bật để che lỗi checkpoint. Kiểm thử offline mô phỏng 610 huyện hoàn tất với marker rỗng chứng minh chỉ còn 100 huyện trong hàng đợi sau phục hồi; quyền và dữ liệu Drive thật cần kiểm tra qua log của lượt mới.


## 13. Google Drive API rateLimitExceeded

Log chứa `drive.googleapis.com`, `RATE_LIMIT_EXCEEDED`, `rateLimitExceeded` là hạn mức **Drive API**. Preflight ghi Drive OK và còn dung lượng không có nghĩa là đủ quota API cho cả lượt. Hạn mức EE và giới hạn số file/byte của Drive là các cơ chế khác nhau.

Bản sửa cho mọi lệnh rclone (đọc, liệt kê, kéo checkpoint, copyto và upload) dùng một tiến trình mỗi lúc trong lượt, mặc định **2 yêu cầu API/giây**, burst 1, 2 transfers và 4 checkers. Thêm fast-list để giảm lượt liệt kê thư mục. Khi Drive báo quota, chờ tăng dần 5 → 10 → 20 → 40 → 60 giây cộng jitter, tối đa 6 lần. Nghỉ áp dụng cả đồng bộ cuối khi STOP đã đặt. Hết lần thử thì báo lỗi và giữ file/checkpoint; quota hoặc lỗi quyền không được coi là file mất để tải lại ảnh từ EE. Những workflow khác vẫn có thể dùng chung quota OAuth project/tài khoản Drive.

Repository Variables tùy chọn: `VNGIS_DISTRICTS_DRIVE_TPS_LIMIT=2`, `VNGIS_DISTRICTS_DRIVE_TRANSFERS=2`, `VNGIS_DISTRICTS_DRIVE_MAX_RETRIES=6`. Python trực tiếp dùng `VNGIS_DRIVE_TPS_LIMIT`, `VNGIS_DRIVE_TRANSFERS`, `VNGIS_DRIVE_MAX_RETRIES`. Nếu vẫn gặp quota thì giảm TPS về 1 và tạm dừng các workflow khác cùng dùng Drive này; không tăng khi còn lỗi. Nếu quota theo ngày hoặc theo file đã hết, backoff không tạo thêm quota.

Để kiểm tra client ID trên Windows CMD **chỉ in dòng client_id**, không in token/client_secret:

```text
rclone config show gdrive | findstr /B /C:"client_id"
```

Nếu không có dòng này hoặc giá trị trống, remote thường đang dùng client chung của rclone (trừ khi đã ghi đè qua biến môi trường/cờ dòng lệnh). Nếu đã có ID thì kiểm tra trong project OAuth tương ứng. Làm theo [hướng dẫn tạo Client ID riêng chính thức](https://rclone.org/drive/#making-your-own-client-id): bật Google Drive API, cấu hình OAuth consent, tạo OAuth client Desktop app, điền client_id/client_secret và reconnect bằng đúng `adt.wqiqc@gmail.com`. Giữ tên remote `gdrive` và thư mục dữ liệu; cập nhật `RCLONE_CONF` sau khi xác thực. Không gửi config/token lên chat. Client riêng tách quota project khỏi client dùng chung, nhưng không loại bỏ hạn mức tài khoản/file.

Ví dụ log có **5.275 TIFF** thì đó là số file workflow thực sự nhìn thấy trong thư mục Drive. **610 huyện đủ 12 TIFF ngày và 12 TIFF đêm cần 14.640 TIFF**. Huyện done trên runner chưa chứng minh tất cả file đã upload; Cancel khi uploader còn lỗi có thể làm mất phần chưa đồng bộ trên runner. Không thể khôi phục phần này chỉ bằng sửa marker; code cần xử lý các tháng thật sự thiếu. Giữ nguyên thư mục và `_control`, dùng STOP và đợi đồng bộ thay vì Cancel nếu muốn giữ tiến độ tốt nhất.

## 14. `scope=range`: chạy từ huyện Vũ Thư (`VNM.55.8_1`)

Khi chọn **`scope=range`**, full bắt đầu từ **`VNM.55.8_1`** theo `start_gid`, bao gồm huyện này và mọi mã huyện sau nó theo thứ tự số của GADM. Đây là huyện Vũ Thư, Thái Bình, cấp 2; không phải xã cấp 3. Đối chiếu GADM 4.1 có **90 huyện trong phạm vi**, bỏ qua **620 mã trước đó**. Mã trước `55.8` được bỏ qua trong lượt này, không được gán `done` hay xác nhận đã upload đủ. Bộ đếm 610 done không xác định phạm vi; việc cắt danh sách dựa vào mã GADM chính xác.

1. **Run workflow** mới trên branch `vngis-ee-districts-202407-202506`, chọn **`mode=full`, `scope=range`, `day_scale=50`**, giữ workers phù hợp với quota.
2. Ô **`start_gid`** nhập `VNM.55.8_1` hoặc `55.8`. Nếu giao diện lấy inputs từ main và chưa có ô `scope`, tạo variable `VNGIS_DISTRICTS_SCOPE=range` để chọn phạm vi. `VNGIS_DISTRICTS_START_GID` dùng khi input trống/không có. Thứ tự ưu tiên: input → variable → mặc định nhánh.
3. Log phải có `[range] Bắt đầu từ VNM.55.8_1 (Vũ Thư, Thái Bình)` cùng số huyện trong phạm vi. Mã không tồn tại sẽ báo lỗi, không tự chọn huyện khác. Các huyện trong phạm vi có dữ liệu/checkpoint hợp lệ vẫn được bỏ qua; tháng thiếu được xử lý như cơ chế resume hiện tại.
4. Báo cáo lưu ở **`_control/progress_from_VNM.55.8_1.csv`**, để giữ nguyên `progress.csv` cũ. Khi tự nối lượt, workflow giữ nguyên `start_gid` và `repair_gids`. CSV gộp vẫn lấy mọi parts hợp lệ đã có, nhưng lượt này chỉ bảo đảm dữ liệu trong phạm vi đã chọn, không bảo đảm đủ toàn quốc. Mặc định mới thêm 5 mã cần sửa ở mục 15 vào cuối phạm vi: tổng **95 huyện được xét**, huyện đủ dữ liệu bền vững vẫn được bỏ qua.

Muốn kiểm tra/bổ sung lại toàn quốc, nhập **`start_gid=VNM.1.1_1`** (mã đầu GADM). Huyện có dữ liệu bền vững hợp lệ sẽ không bị tải lại. Với Python trực tiếp, dùng `VNGIS_START_GID=VNM.55.8_1`; mặc định Python để trống để xét toàn quốc. Pilot bỏ qua tham số này.

Giới hạn `concurrency` giữ nguyên: lượt mới vẫn chờ lượt cũ kết thúc, kể cả khi lượt cũ đang upload. Tùy chọn bắt đầu từ mã huyện không cho phép hai workflow chạy đồng thời. Cập nhật code không thay đổi lượt đang chạy, và Cancel có thể làm mất file chưa đồng bộ. Nếu bỏ qua các mã trước `55.8`, cần kiểm tra riêng phần đó sau khi upload hoàn tất, tránh bỏ sót huyện từng partial hoặc file mất.

## 15. Quyết định từ log người dùng cung cấp ngày 10/10/2026

File `run_20261010_0233_38017392268.log` có 11.595 dòng. Dòng 1–291 thuộc khoảng `2026-10-10 02:33–02:37`; dòng 292 chuyển về `2026-10-09 19:26` và phần cuối tới `23:11`. Vì vậy không dùng tên file hoặc bộ đếm để suy ra một danh sách đầy đủ của một lượt duy nhất. File có **437 mã với dòng `full -> done`** (10 mã ở đoạn 10/10, 427 mã ở đoạn 09/10), **5 mã partial**, cùng dòng bộ đếm 610 done. Không có thông báo đồng bộ cuối thành công. 437 dòng done này không phải danh sách đầy đủ của 610, và không chứng minh ảnh đã nằm trên Drive.

Có **5 mã partial tìm thấy trong log**. Phần từ `VNM.55.8_1` đến cuối đã được người dùng xác nhận hoàn tất; cấu hình hiện tại chỉ sửa CSV của 5 mã này (mục 16):

| Mã GADM | Đơn vị / tỉnh theo GADM 4.1 | Phần còn lỗi trong log |
|---|---|---|
| `VNM.23.5_1` | Đồ Sơn / Hải Phòng | CSV ngày 2024-07 |
| `VNM.23.11_1` | Lê Chân / Hải Phòng | CSV ngày 2024-07 |
| `VNM.33.11_1` | Phú Quốc / Kiên Giang | CSV đêm: Too many concurrent aggregations |
| `VNM.46.2_1` | Ba Đồn / Quảng Bình | CSV ngày 2025-02 |
| `VNM.48.4_1` | Lý Sơn / Quảng Ngãi | CSV ngày 2024-12 |

Workflow mặc định **`repair_gids=VNM.23.5_1,VNM.23.11_1,VNM.33.11_1,VNM.46.2_1,VNM.48.4_1`**. Trong `scope=range`, `repair_gids=none` tắt phần bổ sung; trong `scope=repair_csv`, danh sách trống/none báo lỗi để tránh chạy nhầm phạm vi. Variable tùy chọn `VNGIS_DISTRICTS_REPAIR_GIDS` áp dụng khi input không có/trống. Python trực tiếp dùng `VNGIS_REPAIR_GIDS` (mặc định trống). Pilot bỏ qua tham số sửa CSV.

Các mã sửa được chỉ định mà đã hết ngân sách retry sẽ được mở lại **một lần ở đầu lượt**, giữ mọi tháng có bằng chứng hợp lệ; huyện đã đủ dữ liệu hoặc không có trong asset không tự mở lại. Nếu vẫn không có pixel cho đúng tháng, CSV tiếp tục báo no_data/partial, không thay bằng tháng khác hay giá trị 0.

Hai lỗi được sửa theo bằng chứng log:

- `source file is being updated (size changed ...)`: trước khi upload CSV/trạng thái/log, tạo bản sao đã đóng trong thư mục tạm rồi để rclone đọc bản này. Khóa ghi status/parts chỉ giữ lúc copy cục bộ; worker vẫn làm việc trong thời gian upload. File `.part` không được copy. Checkpoint nhỏ được upload trước TIFF, rồi upload lại sau TIFF để cập nhật marker; resume vẫn kiểm tra file/parts thực có, không coi checkpoint done là bằng chứng upload ảnh.
- `Too many concurrent aggregations`: nhận diện như lỗi hạn mức, dùng cooldown/backoff chung và tự giảm số yêu cầu đồng thời như HTTP 429. Đây là giới hạn Earth Engine, không phải lỗi dung lượng Drive; giảm yêu cầu không tạo thêm quota và chưa chứng minh một query gộp nhiều phép tính luôn thành công.

Tùy chọn đối soát toàn quốc: **`scope=range`, `start_gid=VNM.1.1_1`**. Không dùng danh sách done trích từ log để ghi đè checkpoint trên Drive.

## 16. Chỉ sửa CSV của 5 huyện (mặc định hiện tại)

**Run workflow mới → branch `vngis-ee-districts-202407-202506` → `mode=full`, `scope=repair_csv`, `day_scale=50`.** Giữ `repair_gids` mặc định ở mục 15. Nếu giao diện cũ chưa có ô `scope`, nhánh vẫn mặc định `repair_csv` khi không có variable scope; không cần thêm variable. Nếu đã tạo `VNGIS_DISTRICTS_SCOPE=range`, đổi thành `repair_csv` hoặc chọn đúng input mới.

- Chỉ chọn **Đồ Sơn, Lê Chân, Phú Quốc, Ba Đồn, Lý Sơn**; bỏ qua `start_gid`. Log phải ghi `[csv-repair] Chỉ sửa CSV cho 5 huyện`.
- Chỉ tính phía CSV đang thiếu, giữ CSV phía đã hợp lệ. Không chạy kế hoạch tải ảnh, không tải TIFF ở preflight hay trong xử lý huyện, không move TIFF cũ khi đồng bộ. CSV gộp được dựng lại từ mọi parts hợp lệ đã lưu.
- Giữ **1 yêu cầu EE đồng thời** trong lượt full sửa CSV. CSV đêm được truy vấn **từng tháng**, sau đó ghép đủ 12 tháng mới tính rolling 3 tháng và tăng trưởng; giữ công thức, geometry và tháng gốc. Cách này giảm số phép aggregation trong một query Phú Quốc.
- Báo cáo riêng **`_control/progress_csv_repair.csv`**, cột **`csv_complete`**. Log kết thúc phải ghi **`[csv-repair] CSV đủ tháng: 5/5 huyện`** và đồng bộ cuối thành công. `status=partial` vẫn có thể xuất hiện nếu chưa xác nhận TIFF; lượt sửa CSV không gán ảnh là hoàn tất chỉ vì CSV đã đủ.
- Nếu một tháng vẫn không có pixel hợp lệ, giữ no_data/partial và báo lỗi; không bù số 0 hay lấy tháng khác. Tùy chọn scope/danh sách sửa được giữ khi nối lượt.

Python trực tiếp: đặt `VNGIS_MODE=full`, `VNGIS_CSV_REPAIR_ONLY=true`, `VNGIS_REPAIR_GIDS` theo danh sách 5 mã, `VNGIS_DAY_IMAGE_SCALE=50`, cùng thư mục Drive 50 m và project/credentials hiện có. Python mặc định vẫn giữ chế độ đầy đủ khi không đặt cờ sửa CSV.

## 17. Kiểm soát dữ liệu đã upload lên Drive

Thư mục tỉnh xuất hiện, hoặc log `full -> done`, **không chứng minh dữ liệu đã upload đủ**. Một huyện cần 12 TIFF ngày, 12 TIFF đêm và 12 dòng hợp lệ trong mỗi CSV ngày/đêm của kỳ 2024-07–2025-06. Toàn quốc cần **8.520 TIFF mỗi loại**, tổng 17.040 TIFF.

### Kiểm kê ngay khi lượt upload cũ vẫn chạy

1. **Actions → workflow VNGIS → Run workflow**. Chọn branch **`vngis-ee-districts-202407-202506`**.
2. Chọn **`mode=full`, `scope=audit_drive`, `day_scale=50`**. Nếu giao diện theo main chưa có ô `scope`, nhập **`AUDIT_DRIVE`** vào ô **`stop_after_province`**, chọn `mode=full`. Nhánh huyện nhận giá trị này là yêu cầu kiểm kê, không chạy pipeline. Khi không có `day_scale`, mặc định là 50 m.
3. Lượt này chỉ chạy job **“Kiểm kê file thực có trên Drive”**. Không yêu cầu khóa Earth Engine, không tải TIFF, không xóa/sửa file Drive, không tự nối lượt. STOP không chặn kiểm kê.
4. Mở **Summary** của lượt này để xem bảng 63 tỉnh. Ở cuối trang, mục **Artifacts**, tải **`drive-audit-<run_id>`**.

Job audit dùng nhóm concurrency riêng nên không phải đợi lượt upload cùng nhánh hoàn tất; vẫn có thể phải chờ runner GitHub nếu hết slot. Quét một lần dùng Drive TPS=1; không bấm chạy lặp liên tục khi Google Drive đang báo quota. Có thể kiểm kê lại sau 15–30 phút để so sánh số file tăng lên.

Trong artifact:

| File | Dùng để làm gì |
|---|---|
| `provinces_on_drive.csv` | Đủ cả 63 tỉnh, số huyện đủ theo kiểm kê, số TIFF ngày/đêm so với số cần có |
| `districts_on_drive.csv` | Đủ cả 710 huyện; `day_tiff_on_drive`/`night_tiff_on_drive` cần bằng 12; cột `*_missing_months` nêu tháng TIFF thiếu; `*_csv_missing_or_invalid_months` nêu tháng CSV chưa xác nhận |
| `files_on_drive.csv` | Đường dẫn từng TIFF thực thấy trên Drive, dung lượng byte, ID Drive, `observed_at_utc` và `drive_modtime` |
| `summary.md` | Bảng tổng hợp, đích Drive và thời điểm quét, gồm giờ Việt Nam |

`inventory_complete=true` chỉ khi thấy đúng một TIFF có dung lượng >0 cho từng tháng ở đúng đường dẫn, cùng các dòng CSV hợp lệ. File trùng đường dẫn, TIFF 0 byte, CSV trùng tháng/no_data/thiếu chỉ số không được tính là đủ. CSV dùng hai file tổng hợp `CSV/day_indices.csv` và `CSV/night_indices.csv`: nếu chỉ có parts mà CSV tổng hợp chưa cập nhật, báo cáo vẫn ghi chưa xác nhận. Lỗi API/quota/quyền đọc làm audit thất bại, không được biến thành kết luận “Drive trống”. Báo cáo này **chưa kiểm tra pixel, độ phân giải hay kiểu dữ liệu TIFF**; dùng `verify_pilot.py` khi cần kiểm tra sâu một nhóm huyện.

Lượt upload vẫn ghi file trong khi audit đọc nên số liệu là quan sát trong khoảng thời gian quét, không phải snapshot nguyên tử. `observed_at_utc` là lúc kiểm tra thấy file; **không phải giờ upload**. `drive_modtime` có thể là giờ file ở runner mà rclone giữ lại. Không thể suy ra chính xác giờ upload của các lượt cũ từ hai cột này.

Chạy bằng GitHub CLI nếu đã đăng nhập:

```bash
gh workflow run vngis-2024.yml --repo anductrung-160526/vietnam_satelline_final --ref vngis-ee-districts-202407-202506 -f mode=full -f scope=audit_drive -f day_scale=50
```

Trên máy có Python, đã cài `requirements.txt`, rclone remote `gdrive` hoạt động, mở terminal ở thư mục repo nhánh huyện:

```bash
python audit_drive.py --remote "gdrive:VNGISDash_202407_202506_Districts_50m" --output artifacts/drive_audit
```

Không cần EE JSON cho lệnh này. Script tự dùng danh sách GADM cấp 2; nếu đã có bảng huyện, thêm `--admin artifacts/gadm41_VNM_2/districts_l2_admin.csv`.

### Theo dõi upload ở lượt mới

Các lượt dùng mã mới ghi `[upload] Bắt đầu move -> .../Day` hoặc `.../Night`. Trong lúc chuyển, mỗi 30 giây sẽ có log số TIFF trong danh sách được rclone chuyển và xóa bản local. Cuối đợt có số đã chuyển, số còn chờ và kết quả OK/chưa hoàn tất. Log copy CSV/control ghi đang chạy bao nhiêu giây. Đây là tiến độ của **đợt/lượt hiện tại**, không thay thế kiểm kê toàn bộ Drive. Nhóm file tuổi <2 phút có thể được để lại tới đợt kế tiếp; đồng bộ cuối không áp dụng điều kiện tuổi này.

Mã mới không thay đổi tiến trình đang chạy. Để giữ file chưa upload, không Cancel lượt cũ chỉ vì thiếu log. Có thể kiểm tra nhanh số file thực có bằng rclone trên Windows CMD (số này chưa xác nhận đủ từng huyện hay tính hợp lệ):

```bat
rclone size "gdrive:VNGISDash_202407_202506_Districts_50m/Day" --include "*.tif" --fast-list --tpslimit 1
rclone size "gdrive:VNGISDash_202407_202506_Districts_50m/Night" --include "*.tif" --fast-list --tpslimit 1
```

Nếu số file không tăng và lượt upload đã kết thúc/lỗi, chờ không tự khôi phục file chưa upload của runner đã bị hủy. Khi đó dùng báo cáo tháng thiếu để chọn bước tải bù; không gán done theo log cũ.

## 18. Phục hồi phần chưa lưu trên Drive, ưu tiên tỉnh 34–54

Đối chiếu file người dùng gửi: [reports/DRIVE_RECOVERY_20261010.md](reports/DRIVE_RECOVERY_20261010.md). Log có đủ ảnh 238 huyện nhóm 34–54 nhưng CSV gửi lại thiếu toàn bộ nhóm này; không dùng progress cũ để đánh dấu ảnh đã upload.

Run workflow mới trên branch huyện, chọn **`mode=full`, `scope=recover_drive`, `day_scale=50`**. Nếu UI main chưa có scope, nhập **`RECOVER_DRIVE`** vào `stop_after_province`. Nhánh tự chọn full cho phục hồi. Bỏ qua start_gid và danh sách 5 huyện cũ: phục hồi đối chiếu cả 710 huyện, ưu tiên 238 huyện tỉnh 34–54 rồi phần còn lại.

File `.github/recovery/drive-recovery-request.txt` cũng kích hoạt lượt phục hồi khi được thay đổi và push vào đúng branch. Các push không thay đổi file này không tự chạy. Yêu cầu STOP vẫn được giữ; nếu đang có STOP, workflow sẽ báo skipped. Lượt phục hồi chờ lượt xử lý/upload cùng nhánh nếu lượt đó còn chạy; không Cancel để ép chạy song song và làm mất file cục bộ.

- Chỉ nhận CSV thực đọc từ Drive khi manifest/schema/metadata/tháng khớp; import các dòng hợp lệ còn thiếu vào parts, không ghi đè parts đã có. Dòng no_data hoặc trùng khóa không được nhận là hoàn tất.
- Đọc inventory TIFF dung lượng >0; thiếu file thì mở lại tháng cần xử lý. TIFF ngày đã có marker Int16 cùng đường dẫn được giữ; ảnh có file nhưng thiếu bằng chứng định dạng/checkpoint được đọc lại và kiểm tra trước khi dùng. Lỗi API/quota/quyền đọc không bị biến thành lý do tải lại.
- Nếu còn TIFF trên chính máy chạy phục hồi, đồng bộ ngay trước khi tính lại. Runner GitHub mới không lấy được file chưa upload từ runner cũ đã bị hủy; cần tải bù từ EE.
- CSV hợp lệ có trong parts được dùng ngay cả khi checkpoint status bị thiếu hoặc pending. Các huyện hết ngân sách thử nhưng còn thiếu dữ liệu được mở lại một ngân sách ở đầu lượt phục hồi; no_data thật vẫn có thể thất bại sau ngân sách này.
- Lượt phục hồi tự kích hoạt qua push dùng **2 huyện song song**, **2 yêu cầu EE đồng thời**, giữ backoff và nghỉ chủ động. Khi Run workflow thủ công, ô workers quyết định số huyện song song. CSV đêm tính từng tháng. CSV tổng hợp được dựng và upload trước đợt TIFF dài, rồi cập nhật lại sau ảnh, không chờ hết lượt.
- Đọc `_control/progress_recovery.csv` và log `[recovery]`, `[upload]`. Sau lượt có artifact `drive-recovery-audit-<run_id>` kiểm kê file thực có trên Drive. Chưa kiểm kê đủ 8.520 TIFF mỗi loại và CSV đủ 12 tháng/710 huyện thì chưa xác nhận hoàn tất toàn quốc.

Python trực tiếp: `VNGIS_MODE=full`, `VNGIS_RECOVER_DRIVE=true`, `VNGIS_DAY_IMAGE_SCALE=50`, cùng thư mục Drive 50 m, EE project/credentials hiện có. Cờ phục hồi ưu tiên hơn cờ sửa riêng CSV; không cần `VNGIS_ALLOW_FULL_RESTART=true` và không dùng log để tạo checkpoint done giả.

### Nếu phục hồi dừng vì thiếu manifest

Lượt #26 đọc được 7.435 TIFF và checkpoint, nhưng dừng ở `Phục hồi yêu cầu manifest Drive khớp kỳ/profile`. Bản sửa xác minh `_control/status` và `_control/parts` đã kéo từ cùng thư mục Drive khi `pipeline.json` bị thiếu: metadata phải đúng cấp huyện, kỳ 07/2024–06/2025 và profile 50 m hiện tại. Khi đủ bằng chứng, khôi phục manifest và tiếp tục nhập CSV. Manifest đã tồn tại nhưng khác cấu hình, lỗi quyền/quota hoặc checkpoint khác profile vẫn làm pipeline dừng; không sửa chúng thành dữ liệu hợp lệ.

Việc xác minh manifest không xác nhận đã đủ ảnh. Pipeline vẫn đối chiếu CSV từng tháng và TIFF thực có. Biên nhận `.recovery_csv_ready.json` chỉ lưu trên runner sau khi đã đọc xong cả hai CSV; không upload biên nhận này lên Drive. Nếu khởi tạo hoặc đọc CSV thất bại, bước `--sync-only` không dựng/ghi đè CSV tổng hợp từ parts chưa đủ.

Nếu lượt mới thất bại, **Summary** hiện 40 dòng cuối của pipeline và annotation lỗi gốc. Tải artifact **`vngis-logs-<run_id>`** để xem `pipeline.log`, `sync.log`, `audit.log`, kể cả khi chưa tạo được báo cáo kiểm kê. Artifact chỉ ghi đầu ra của các lệnh Python, không thu thập file cấu hình rclone hoặc JSON khóa EE.
