# Setup nhánh vngis-ee-ha-tinh-lai-chau

Nhánh GitHub: `vngis-ee-ha-tinh-lai-chau`. Dùng file **`vngis_2024.py` ở thư mục gốc** và `.github/workflows/vngis-2024.yml`; thư mục `vngis-github-repo-v6` là bản lưu cũ.

| Thành phần | Cấu hình của nhánh |
|---|---|
| Project ID chịu quota Earth Engine | `vngis-ee-ha-tinh-lai-chau` |
| Tài khoản quản lý project | `k62.2313560049@ftu.edu.vn` |
| Tài khoản Google Drive nhận kết quả | `adt.wqiqc@gmail.com` |
| Thư mục kết quả full | `VNGISDash_2024_Ha Tinh_Lai Chau` |
| Thư mục chạy thử | `VNGISDash_2024_Ha Tinh_Lai Chau_PILOT` |
| Secret Earth Engine riêng | `EE_SERVICE_ACCOUNT_JSON_HA_TINH_LAI_CHAU` |
| Secret rclone riêng | `RCLONE_CONF_HA_TINH_LAI_CHAU` |

Project ID trong tài liệu là tên dự kiến **`vngis-ee-ha-tinh-lai-chau`**. Nếu chưa tạo, đăng nhập tài khoản quản lý ở trên, chọn **Select a project → New project**, chỉnh **Project ID** cho khớp tên này rồi tạo. Tên hiển thị project không thay thế Project ID. Branch GitHub đã có code; Google Cloud project, asset, IAM và secrets phải được cấu hình bằng tài khoản của bạn.

Earth Engine và Drive dùng hai thông tin xác thực độc lập. Không cần chuyển quyền sở hữu project sang tài khoản nhận kết quả. Khóa service account dùng để đọc/tính toán EE; token OAuth rclone đăng nhập `adt.wqiqc@gmail.com` dùng để ghi Drive.

## 1. Phạm vi dữ liệu

Sắp xếp theo tên tỉnh tiếng Việt **bỏ dấu khi so sánh, giữ khoảng trắng**, đúng bảng alphabet đã thống nhất. Phạm vi được chọn bằng tên tỉnh theo alphabet, không bằng khoảng số trong mã GADM.

| Thứ tự chạy | Tỉnh/thành | GID_1 | Đơn vị cấp xã |
|---:|---|---|---:|
| 1 | Hà Tĩnh | VNM.29_1 | 262 |
| 2 | Hải Dương | VNM.22_1 | 265 |
| 3 | Hải Phòng | VNM.23_1 | 224 |
| 4 | Hậu Giang | VNM.24_1 | 76 |
| 5 | Hồ Chí Minh | VNM.25_1 | 322 |
| 6 | Hoà Bình | VNM.30_1 | 210 |
| 7 | Hưng Yên | VNM.31_1 | 161 |
| 8 | Khánh Hòa | VNM.32_1 | 137 |
| 9 | Kiên Giang | VNM.33_1 | 145 |
| 10 | Kon Tum | VNM.34_1 | 102 |
| 11 | Lai Châu | VNM.36_1 | 108 |
| | **Tổng** | | **2.012** |

Đây là 11 tỉnh/thành trong GADM 4.1, trước sáp nhập. Cả `pilot` và `full` đều lọc phạm vi này trước khi chọn xã. Full hoàn tất từng tỉnh rồi mới chuyển tỉnh tiếp theo; chỉ dừng thành công khi hết Lai Châu. Khi hết thời gian 5 giờ 15 phút, workflow nối lượt trên **cùng nhánh** và giữ phạm vi. Xã đã `done` được bỏ qua. Xã hết số lần thử mà còn lỗi sẽ chặn chuyển tỉnh, báo lỗi để xử lý.

## 2. Chuẩn bị project và service account

1. Đăng nhập Google Cloud bằng **`k62.2313560049@ftu.edu.vn`**. Mở [project mới](https://console.cloud.google.com/home/dashboard?project=vngis-ee-ha-tinh-lai-chau), kiểm tra trường **Project ID** là `vngis-ee-ha-tinh-lai-chau`. Tên hiển thị có thể chứa khoảng trắng; code sử dụng ID không có khoảng trắng.
2. Mở [Earth Engine configuration](https://console.cloud.google.com/earth-engine/configuration?project=vngis-ee-ha-tinh-lai-chau), hoàn tất đăng ký phù hợp mục đích sử dụng. Trong **APIs & Services**, bật **Google Earth Engine API** cho project này.
3. **IAM & Admin → Service Accounts → Create service account**, ví dụ ID `vngis-runner`. Email khi đó là `vngis-runner@vngis-ee-ha-tinh-lai-chau.iam.gserviceaccount.com`.
4. Trong IAM của **project này**, cấp cho **email service account**, không chỉ email Gmail cá nhân:
   - **Service Usage Consumer** (`roles/serviceusage.serviceUsageConsumer`).
   - **Earth Engine Resource Writer** (`roles/earthengine.writer`).
5. Mở service account → **Keys → Add key → Create new key → JSON**. Tải file về máy, giữ kín. Workflow kiểm tra JSON thuộc đúng project trước khi chạy.

## 3. Chuẩn bị asset communes_l3

Project mới không tự có bảng ranh giới. Asset mặc định là:

```text
projects/vngis-ee-ha-tinh-lai-chau/assets/communes_l3
```

**Cách tạo mới:** đăng nhập [Earth Engine Code Editor](https://code.earthengine.google.com/) bằng tài khoản quản lý project, chọn project `vngis-ee-ha-tinh-lai-chau`. Tải [GADM 4.1 Việt Nam](https://geodata.ucdavis.edu/gadm/gadm4.1/shp/gadm41_VNM_shp.zip), giải nén, lấy các file cùng tên `gadm41_VNM_3` gồm `.shp`, `.shx`, `.dbf`, `.prj` và `.cpg`. Trong **Assets**, chọn cloud project này (thêm project vào danh sách nếu cần), **NEW → Table upload → Shape files**; tải bộ file cấp 3 và đặt tên asset `communes_l3`. Đợi tác vụ upload hoàn tất. Bảng phải giữ các trường `GID_1`, `NAME_1`, `GID_2`, `NAME_2`, `GID_3`, `NAME_3`, `TYPE_3` và geometry; GADM cấp 3 có 11.163 bản ghi.

**Nếu dùng lại bảng GADM đang có:** chủ asset cũ cấp quyền đọc asset cho email service account mới. Trong GitHub **Settings → Secrets and variables → Actions → Variables**, thêm repository variable `VNGIS_HA_TINH_LAI_CHAU_EE_ASSET` với đường dẫn đầy đủ tới asset đó. Đây là variable, không phải secret. Chỉ đổi nguồn ranh giới; mọi truy vấn vẫn dùng `ee.Initialize(project="vngis-ee-ha-tinh-lai-chau")` và quota project mới. Không cần cấp quyền ghi toàn project cũ chỉ để đọc bảng.

## 4. Cấu hình Drive bằng adt.wqiqc@gmail.com

Nếu remote `gdrive` đã xác thực đúng `adt.wqiqc@gmail.com` như nhánh Cao Bằng–Hà Nội, dùng lại toàn bộ cấu hình đó cho secret rclone của nhánh này, không cần đăng nhập bằng tài khoản quản lý EE. Các nhánh dùng cùng Drive nhưng lưu vào các thư mục và trạng thái riêng.

Nếu cần cấu hình remote mới, trên máy có rclone, mở terminal rồi chạy:

```text
rclone config
```

Tạo hoặc chỉnh remote tên **`gdrive`**, chọn storage **Google Drive**. Với tài khoản cá nhân: `client_id` và `client_secret` có thể để trống, scope chọn **1 (Full access)**, service account file để trống, advanced config chọn `n`, đăng nhập qua trình duyệt chọn `y`, Shared Drive chọn `n`.

**Client OAuth riêng:** rclone đã cảnh báo client Google Drive dùng chung sẽ ngừng hoạt động trong năm 2026. Để cấu hình lâu dài, tạo client theo [hướng dẫn chính thức của rclone](https://rclone.org/drive/#making-your-own-client-id): bật Google Drive API trong project bạn quản lý, cấu hình OAuth consent cho phép `adt.wqiqc@gmail.com` đăng nhập, tạo OAuth client loại **Desktop app**, điền Client ID và Client secret vào remote `gdrive`, rồi xác thực lại bằng `rclone config reconnect gdrive:`. Với OAuth External đang ở Testing và dùng quyền Drive, refresh token thường hết hạn sau 7 ngày; cấu hình trạng thái xuất bản phù hợp trước khi chạy lâu dài. Client Drive có thể thuộc project riêng và dùng chung cho các nhánh; project chịu quota EE vẫn là project ở mục 2.

Trong trình duyệt OAuth, **chọn đúng `adt.wqiqc@gmail.com`**, cấp quyền cho rclone. Nếu trình duyệt đang đăng nhập nhiều tài khoản, kiểm tra email ở trang cấp quyền trước khi xác nhận. Để `root_folder_id` trống để thư mục được tạo trong My Drive của tài khoản này. Không dùng JSON EE cho remote Drive.

Kiểm tra tại máy:

```text
rclone lsd gdrive:
rclone mkdir "gdrive:VNGISDash_2024_Ha Tinh_Lai Chau"
rclone config show gdrive
```

Mở Drive bằng `adt.wqiqc@gmail.com`, kiểm tra thư mục vừa tạo xuất hiện. Copy toàn bộ kết quả `rclone config show gdrive`, **bao gồm dòng `[gdrive]`**, vào secret riêng ở bước 5. Nội dung này có token: không gửi lên chat hoặc commit vào repo. Nếu remote cũ đã đăng nhập đúng `adt.wqiqc@gmail.com`, có thể dùng cùng nội dung cấu hình cho secret mới.

## 5. Tạo hai GitHub Secrets riêng

Trong repository → **Settings → Secrets and variables → Actions → New repository secret**:

| Tên chính xác | Nội dung |
|---|---|
| `EE_SERVICE_ACCOUNT_JSON_HA_TINH_LAI_CHAU` | Toàn bộ JSON tải ở bước 2, thuộc project mới |
| `RCLONE_CONF_HA_TINH_LAI_CHAU` | Cấu hình `[gdrive]` đã OAuth bằng `adt.wqiqc@gmail.com` |

Không thay thế `EE_SERVICE_ACCOUNT_JSON` và `RCLONE_CONF` mà nhánh `main` đang dùng. Secrets thuộc repository, tên riêng giúp hai workflow dùng đúng cấu hình.

Trong **Settings → Actions → General → Workflow permissions**, bảo đảm policy cho phép workflow tự dispatch lượt kế tiếp (`actions: write`). Workflow đã khai báo `contents: read` và `actions: write`.

## 6. Chạy trên nhánh mới

1. **Actions → chọn workflow `vngis-2024.yml` → Run workflow**. Tên hiển thị trên trang Actions có thể vẫn lấy từ main.
2. Trong **Use workflow from**, chọn **`vngis-ee-ha-tinh-lai-chau`**. Chạy thử `mode=pilot`, `pilot_n=2`, `workers=2`.
3. Ô `stop_after_province` được giữ để tương thích giao diện main; nhánh mới luôn cấu hình **Hà Tĩnh → Lai Châu**, không lấy giá trị ô này làm phạm vi. Chọn `Lai Châu` để dễ đọc lịch sử lượt chạy.
4. Kiểm tra log có `project=vngis-ee-ha-tinh-lai-chau`, preflight đạt, 2 xã thử đều trong phạm vi; kiểm tra thư mục `VNGISDash_2024_Ha Tinh_Lai Chau_PILOT` trên Drive `adt.wqiqc@gmail.com`.
5. Chạy lượt mới trên cùng nhánh với **`mode=full`, `workers=2`**. Log `Danh sách` phải ghi **2.012 xã, 11 tỉnh**, bắt đầu ở Hà Tĩnh. Kết quả full nằm trong **`VNGISDash_2024_Ha Tinh_Lai Chau`**.

Cấu hình khởi đầu giữ 1 yêu cầu EE đồng thời, 2 luồng tháng, 8 lần retry với backoff cho HTTP 429. Có thể tăng `VNGIS_EE_CONCURRENCY` trong workflow sau khi kiểm tra project thực tế chạy ổn; project mới vẫn có các quota riêng của Earth Engine. Nhánh này không làm tăng quota và không tự gỡ restricted mode.

## 7. Dừng, tiếp tục và theo dõi

- Dừng: tạo file **`STOP` trên nhánh `vngis-ee-ha-tinh-lai-chau`**, hoặc `_control/STOP` trong thư mục kết quả trên Drive. Workflow kiểm tra STOP theo đúng nhánh; file STOP trên main không chặn nhánh này.
- Tiếp tục: xóa STOP ở đúng nhánh/Drive rồi Run workflow từ `vngis-ee-ha-tinh-lai-chau`, cùng mode. Không xóa `_control/status`.
- Theo dõi: `_control/progress.csv`, `_control/logs/`, và Step summary. Full chỉ báo hoàn tất khi toàn bộ phạm vi đã `done`, sau đó đồng bộ cuối và không gọi lượt mới.
- Thư mục kết quả chứa `Day`, `Night`, `CSV`, `_control`. CSV tổng hợp vẫn giữ tên `day_indices.csv` và `night_indices.csv`; trong thư mục riêng này dữ liệu chỉ thuộc phạm vi đã chọn.
- Lỗi 403: kiểm tra project ID, **email service account** được gán IAM, đăng ký EE và quyền đọc asset.
- `not_in_asset`: kiểm tra bảng cấp 3 giữ đúng `GID_3`; không thay bằng bảng tỉnh/huyện hoặc bộ ranh giới sau sáp nhập.
- Dữ liệu xuất nhầm tài khoản: đăng nhập lại remote `gdrive` bằng `adt.wqiqc@gmail.com`, cập nhật secret riêng và chạy lại.

## 8. Kiểm thử code trong cloud environment

```bash
python -m venv /tmp/vngis-ha-tinh-lai-chau-venv
/tmp/vngis-ha-tinh-lai-chau-venv/bin/pip install -r requirements.txt
/tmp/vngis-ha-tinh-lai-chau-venv/bin/python -m unittest discover -s tests -v
```

Các kiểm thử chạy offline, không cần JSON hoặc token Drive. Chạy pipeline thật vẫn cần project/asset/IAM và hai secrets ở trên. Dùng checkout hiện có; không cần Git worktree.
