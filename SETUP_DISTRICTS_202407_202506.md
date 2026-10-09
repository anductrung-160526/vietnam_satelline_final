# Setup dữ liệu cấp huyện: tháng 07/2024–06/2025

Branch: **`vngis-ee-districts-202407-202506`**. Dùng `vngis_2024.py`, `verify_pilot.py` và `.github/workflows/vngis-2024.yml` ở thư mục gốc. Thư mục `vngis-github-repo-v6` là bản lưu cũ.

| Thành phần | Cấu hình |
|---|---|
| Phạm vi | Toàn quốc: **710 đơn vị cấp huyện, 63 tỉnh/thành** |
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
4. Kiểm tra **`VNGISDash_202407_202506_Districts_50m_PILOT`**. Khi pilot đạt, tạo lượt mới trên đúng branch với **`mode=full`, `workers=4`, `day_scale=50`**. Full lưu vào `VNGISDash_202407_202506_Districts_50m`. Pilot/full dùng thư mục riêng; full xử lý toàn quốc, không chỉ các huyện thí điểm.
5. Full phải ghi **710 huyện, 63 tỉnh**. Khi hoàn tất đầy đủ, mỗi CSV có **8.520 dòng huyện–tháng**, có 12 TIFF ngày và 12 TIFF đêm mỗi huyện (tổng 8.520 file mỗi loại).

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

- Mỗi lượt tối đa 5 giờ 15 phút rồi đồng bộ và tự nối trên **cùng branch**, cùng mode/pilot_n/workers. Khoảng tháng và project đọc từ workflow/variables của branch.
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
| `RCLONE_COMMON` trong `vngis_2024.py` | `--transfers 4`, `--checkers 8`, `--tpslimit 8` | Song song và giới hạn tốc độ API khi tải lên Drive; cấu hình trong code, độc lập với giới hạn EE |

`workers=4` × `MONTH_THREADS=2` có thể tạo 8 tác vụ tải ảnh, nhưng **tối đa 4 yêu cầu EE đang chạy** do giới hạn chung; nếu bị hạ về 1 thì tăng workers không vượt qua được giới hạn này. TIFF đêm giữ 500 m. Huyện lớn phải chia nhiều ô và project Restricted Mode vẫn có thể chậm dù có nghỉ chủ động. Xem `[speed]`, `[quota]`, `[rest]` để đo tốc độ và các khoảng nghỉ thực tế.

Bản sửa chỉ áp dụng cho lượt mới: chờ lượt cũ kết thúc, hoặc tạo STOP trên đúng branch rồi đợi đồng bộ xong, xóa STOP và Run workflow. Thư mục Drive, project, asset và Secrets giữ nguyên.
