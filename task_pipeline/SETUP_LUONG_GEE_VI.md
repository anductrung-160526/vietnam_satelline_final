# Hướng dẫn: thiết lập và chạy một luồng tải ảnh năm toàn quốc (Earth Engine → PowerShell)

Tài liệu này ghi lại toàn bộ các bước để thêm một luồng (tài khoản Google + project Earth
Engine) mới, hoặc để tự chạy lại từ đầu khi không còn nhớ các lệnh. Viết cho `task_pipeline/national.py`
trên nhánh `vngis-tinh-001-011`. Đọc kèm `CLAUDE.md` ở gốc repo — đó là nơi ghi các **quy tắc dự án
bắt buộc** (giai đoạn Landsat/Sentinel-2/VIIRS/DMSP, các quyết định đã chốt, bảng 6 tài khoản).

---

## 0. Tổng quan luồng dữ liệu

```
Google Cloud project (đăng ký Earth Engine)
        │
        ▼
task_pipeline/national.py  --product ... --years ... --project ...
        │   (Earth Engine tính ảnh năm toàn quốc, mỗi mảnh tải thẳng về)
        ▼
ổ E, thư mục tiles/  (mỗi mảnh một file .tif)
        │   --merge
        ▼
VN_<NGUON>_<NĂM>.tif   (một file GeoTIFF toàn quốc)
        │   --clip
        ▼
data_intermediate/annual_province/<NGUON>/<ma_tinh>_<slug>/   (63 file theo tỉnh)
```

Ba chế độ của cùng một lệnh `national.py`:
| Chế độ | Cần Earth Engine? | Việc làm |
|---|---|---|
| (mặc định) | Có, tốn quota | Tải ảnh năm toàn quốc, mỗi mảnh một file, tự tiếp tục khi bị dừng |
| `--merge` | Không | Ghép các mảnh một năm thành 1 file `.tif` |
| `--clip` | Không | Cắt ảnh toàn quốc (hoặc đã ghép) thành 63 file theo tỉnh |

---

## 1. Thiết lập trên Google Earth Engine / Google Cloud

Làm **một lần cho mỗi tài khoản/project** mới.

### 1.1. Tạo project Google Cloud
1. Đăng nhập đúng tài khoản Google muốn dùng cho luồng này.
2. Vào `console.cloud.google.com` → **New Project**. Đặt tên dễ nhớ (ví dụ `vngis-ee-<vùng>`),
   ghi lại **Project ID** chính xác (chữ thường, có gạch ngang) — đây là giá trị dùng ở `--project`.

### 1.2. Đăng ký Earth Engine cho project đó
1. Vào `code.earthengine.google.com`, hoặc trực tiếp
   `console.cloud.google.com/earth-engine?project=<project-id>`.
2. Đăng ký ở dạng **Noncommercial / Academic & Research** (phi thương mại, miễn phí).
3. Bật **Earth Engine API** cho project (Console → APIs & Services → Library → tìm "Earth Engine API" → Enable).

### 1.3. Kiểm tra quota
`console.cloud.google.com/apis/api/earthengine.googleapis.com/quotas?project=<project-id>`
- Dòng **"Noncommercial EECU-seconds per month"**: giới hạn phi thương mại theo tháng (ví dụ
  1.000 EECU-giờ = 3.600.000 EECU-giây). Hiện tại đây là cái quyết định tốc độ chạy.
- Nếu **"Current usage percentage"** vượt 100%, project đang ở **chế độ hạn chế** (restricted
  mode): vẫn chạy được nhưng chậm, hay gặp lỗi 429. Không có cách "mua thêm" quota phi thương
  mại; chỉ chờ đặt lại đầu tháng, hoặc xin tier cao hơn qua kênh chính thức của Earth Engine
  (cần giảng viên/đơn vị nghiên cứu đứng tên), hoặc chuyển sang Earth Engine thương mại (cần
  tài khoản billing, không nằm trong phạm vi tài liệu này).

### 1.4. Không cần viết code trên GEE Code Editor
Toàn bộ logic (lọc mây, composite theo năm, band, chỉ số) đã viết sẵn trong
`task_pipeline/national.py`, `task_pipeline/methods.py`, `task_pipeline/stats.py`. Không cần mở
Code Editor hay JavaScript của Earth Engine. Mọi thao tác chạy từ PowerShell qua thư viện Python
`earthengine-api`, xác thực bằng tài khoản Google đã đăng ký Earth Engine ở bước 1.2.

---

## 2. Cấu hình trong code (nơi khai báo luồng mới)

Mỗi luồng = một **project Earth Engine** + một **tài khoản Google đã đăng nhập (profile riêng)**.
Không có "danh sách luồng" trung tâm trong code — mỗi lần chạy, `--project` quyết định project
nào được dùng. Nhưng có 2 chỗ cần biết:

### 2.1. `task_pipeline/national.py` — các sản phẩm và giai đoạn hợp lệ
```python
PRODUCTS = {
    'LANDSAT':   dict(years=range(2004, 2015), scale=30, ...),
    'SENTINEL2': dict(years=range(2015, 2026), scale=10, ...),
    'VIIRS':     dict(years=range(2014, 2026), scale=500, ...),
    'DMSP':      dict(years=range(2004, 2014), scale=1000, ...),
}
```
Lệnh sẽ **từ chối chạy** nếu `--years` nằm ngoài khoảng cho phép của `--product` (đúng quy tắc
dự án: Landsat chỉ 2004–2014, Sentinel-2 chỉ 2015–2025, VIIRS chỉ 2014–2025, DMSP chỉ
2004–2013). Không sửa bảng này trừ khi quy tắc dự án trong `CLAUDE.md` thay đổi.

### 2.2. `CLAUDE.md` — bảng tài khoản/project hiện có
`CLAUDE.md` ở gốc repo giữ bảng **10 luồng** (tài khoản Google ↔ project Earth Engine ↔ thư mục
profile trên Windows). Khi thêm tài khoản/project mới: **thêm một dòng vào bảng đó**, và nếu chạy
trên máy ảo thì thêm một mục vào mảng `ACCOUNTS` trong `scripts/cloud_vm/run.sh`.

**Không cần tạo nhánh git riêng cho mỗi luồng.** Mọi luồng chạy từ cùng checkout nhánh
`vngis-tinh-001-011`; việc chia công việc do `--shard i/n` quyết định (10 tài khoản →
`--shard 1/10` … `10/10`). Các nhánh `vngis-tinh-XXX-XXX` là di sản của luồng tải ảnh theo
tỉnh/tháng trước đây, không dùng cho ảnh năm toàn quốc.

---

## 3. Đưa code mới lên nhánh GitHub (khi có thay đổi) và kiểm thử

Chỉ cần làm khi **sửa code** (ví dụ thêm tuỳ chọn mới). Nếu chỉ chạy lệnh sẵn có, bỏ qua mục này,
sang thẳng mục 4.

### 3.1. Vị trí code
Nhánh làm việc: **`vngis-tinh-001-011`** trên repo
`https://github.com/anductrung-160526/vietnam_satelline_final`. Các file chính:
- `task_pipeline/national.py` — lệnh tải/ghép/cắt ảnh năm toàn quốc.
- `task_pipeline/stats.py` — lệnh tính chỉ số theo tháng trên Earth Engine (không tải ảnh).
- `tests/test_national.py`, `tests/test_stats.py` — test offline (giả lập Earth Engine, không
  tốn quota, không cần mạng tới Earth Engine thật).

### 3.2. Chạy test trước khi tin tưởng code mới
```bash
cd <thư mục checkout nhánh vngis-tinh-001-011>
pip install -q rasterio numpy shapely affine pandas requests pytest earthengine-api
PYTHONPATH=.:tests python -m pytest -q -p no:warnings tests
```
Kết quả mong đợi: toàn bộ test `passed`, không `failed`. Test chạy **offline**, giả lập phản hồi
Earth Engine bằng dữ liệu giả, nên **không phát hiện được lỗi chỉ xảy ra khi gọi Earth Engine
thật** (ví dụ lỗi kiểu dữ liệu không khớp khi gộp ảnh — từng gặp với VIIRS). Vì vậy sau khi push,
luôn theo dõi vài phút đầu của lần chạy thật trên PowerShell.

### 3.3. Commit và push
```bash
git add <file đã sửa>
git commit -m "Mô tả ngắn gọn thay đổi"
git push origin vngis-tinh-001-011
```

### 3.4. Lấy code mới nhất trên máy Windows (laptop)
Không dùng `git clone`/`git pull` trên checkout cũ nếu đang dùng bản ZIP tải tay; cách đơn giản
và chắc chắn nhất là tải thẳng từng file cần thiết bằng `Invoke-WebRequest`:
```powershell
cd "C:\Users\AD\Downloads\vietnam_satelline_final-vngis-tinh-001-011\vietnam_satelline_final-vngis-tinh-001-011"
$base = "https://raw.githubusercontent.com/anductrung-160526/vietnam_satelline_final/vngis-tinh-001-011"
Invoke-WebRequest "$base/task_pipeline/national.py" -OutFile .\task_pipeline\national.py
Select-String -Path .\task_pipeline\national.py -Pattern "def merge_year"   # xác nhận đã tải đúng bản mới
```
Luôn kiểm tra bằng `Select-String` tìm một đoạn code chắc chắn có trong bản mới nhất, để biết
tải có thành công không (tránh lỗi mạng âm thầm giữ bản cũ).

---

## 4. Thiết lập máy Windows cho một luồng mới

Làm **một lần cho mỗi tài khoản/project** mới trên laptop.

### 4.1. Cài Python và thư viện (chỉ cần một lần cho cả máy, dùng chung mọi luồng)
```powershell
cd "C:\Users\AD\Downloads\vietnam_satelline_final-vngis-tinh-001-011\vietnam_satelline_final-vngis-tinh-001-011"
py -3.12 -m venv .venv
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $python -m pip install -r .\province_pipeline\requirements.txt
```

### 4.2. Tạo profile đăng nhập riêng cho tài khoản Google mới
Mỗi tài khoản Google cần một thư mục riêng để lưu token đăng nhập Earth Engine, nếu không các
luồng sẽ **ghi đè đăng nhập của nhau** trên cùng một máy.
```powershell
$env:USERPROFILE = "C:\ee-profiles\acc-<ten-ngan>"      # ví dụ acc-ftu, acc-quynhmai...
New-Item -ItemType Directory -Force $env:USERPROFILE | Out-Null
```

### 4.3. Đăng nhập Earth Engine cho tài khoản đó (một lần, hoặc khi token hết hạn)
```powershell
cd "C:\Users\AD\Downloads\vietnam_satelline_final-vngis-tinh-001-011\vietnam_satelline_final-vngis-tinh-001-011"
& $python -m task_pipeline.national --product LANDSAT --years 2004 --project <project-id> --workers 0 2>&1 | Select-Object -First 1
```
Cách đơn giản và đáng tin cậy hơn: dùng lệnh `authenticate` có sẵn trong `local.py` (được
`national.py` dùng chung):
```powershell
& $python -c "import ee; ee.Authenticate(auth_mode='localhost', scopes=['https://www.googleapis.com/auth/earthengine','https://www.googleapis.com/auth/cloud-platform']); ee.Initialize(project='<project-id>'); print('Earth Engine:', '<project-id>', 'PASS' if ee.Number(1).getInfo()==1 else 'FAIL')"
```
Trình duyệt mở ra → đăng nhập **đúng tài khoản Google** của project đó → cấp quyền. Cửa sổ
PowerShell phải in ra `... PASS`. Token được lưu vào `$env:USERPROFILE\.config\earthengine\`,
nên lần sau mở cửa sổ mới chỉ cần đặt lại `$env:USERPROFILE` (mục 4.2), **không cần đăng nhập lại**.

### 4.4. Cách khác: dùng service-account key thay cho đăng nhập trình duyệt
Nếu project đã có **service account** và file **key JSON**, không cần đăng nhập trình duyệt —
tiện hơn nhiều khi có 10 luồng, và bắt buộc khi chạy trên máy ảo không có màn hình.
1. Trên Google Cloud Console → **IAM & Admin → Service Accounts** → tạo service account cho project.
2. Cấp quyền: **Earth Engine Resource Writer** (hoặc Viewer nếu chỉ đọc) và **Service Usage Consumer**.
3. **Đăng ký service account đó với Earth Engine** (bắt buộc, nếu không sẽ bị từ chối khi gọi API):
   `signup.earthengine.google.com/#!/service_accounts`, hoặc thêm email service account vào project
   Earth Engine đã đăng ký.
4. Tạo **key JSON**, lưu **ngoài repo** (ví dụ `C:\keys\vgis-ee-07.json`). Không commit lên Git.
5. Chạy với `--ee-key`:
```powershell
& $python -m task_pipeline.national --product SENTINEL2 --years 2024 --project vgis-ee-07 --ee-key "C:\keys\vgis-ee-07.json" --shard 7/10
```
Khi dùng `--ee-key`, **không cần** đặt `$env:USERPROFILE` cho luồng đó.

---

## 5. Chạy luồng trên PowerShell

### 5.1. Khuôn mẫu một cửa sổ (một luồng)
```powershell
$env:USERPROFILE = "C:\ee-profiles\acc-<ten-ngan>"     # bỏ dòng này nếu dùng tài khoản mặc định của máy
cd "C:\Users\AD\Downloads\vietnam_satelline_final-vngis-tinh-001-011\vietnam_satelline_final-vngis-tinh-001-011"
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
New-Item -ItemType Directory -Force "E:\SatelliteData\_control\national" | Out-Null
$log = "E:\SatelliteData\_control\national\log_<ten-luong>.txt"
& $python -m task_pipeline.national --product <LANDSAT|SENTINEL2|VIIRS|DMSP> --years <năm hoặc khoảng> --project <project-id> 2>&1 | Tee-Object -FilePath $log -Append
```

### 5.2. Các tuỳ chọn chính
| Tuỳ chọn | Ý nghĩa |
|---|---|
| `--product` | `LANDSAT`, `SENTINEL2`, `VIIRS`, hoặc `DMSP`. Bắt buộc |
| `--years` | `2015-2025` (khoảng) hoặc `2020,2022` (danh sách). Phải nằm trong giai đoạn cho phép |
| `--project` | Project ID Earth Engine. Bắt buộc trừ khi dùng `--merge`/`--clip` |
| `--root` | Thư mục gốc lưu dữ liệu. Mặc định `E:\SatelliteData` trên Windows |
| `--workers` | Số request gửi song song tới Earth Engine. Mặc định `1` (nhẹ nhất cho quota). Thử `2`–`3` nếu muốn nhanh hơn và quota còn nhiều |
| `--shard i/n` | Chia **mỗi năm** thành `n` phần, luồng này lấy phần `i`. Dùng khi muốn **nhiều project cùng làm chung một năm** cho xong nhanh. Mọi luồng của cùng năm đó phải dùng cùng `n` |
| `--merge` | Không tải, chỉ ghép các mảnh một năm **đã tải xong** (có `.vrt`) thành 1 file `.tif`. Không cần `--project` |
| `--clip` | Không tải, cắt ảnh năm (ưu tiên `.tif` đã ghép, nếu chưa có thì dùng `.vrt`) thành 63 file theo tỉnh. Cần `--project` (để lấy ranh giới tỉnh), không tốn quota |
| `--overviews` | Dùng với `--merge`: build thêm pyramid để QGIS zoom nhanh hơn, tốn thêm ~30% dung lượng |

### 5.3. Ví dụ: 6 luồng cùng chia nhau một năm Sentinel-2
Mỗi cửa sổ PowerShell một luồng, `--shard` khác nhau từ `1/6` đến `6/6`:
```powershell
# Cửa sổ 1 — vngis-ee-2
cd "C:\Users\AD\Downloads\vietnam_satelline_final-vngis-tinh-001-011\vietnam_satelline_final-vngis-tinh-001-011"
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $python -m task_pipeline.national --product SENTINEL2 --years 2024 --project vngis-ee-2 --shard 1/6 2>&1 | Tee-Object -FilePath "E:\SatelliteData\_control\national\log_s2_2024_p1.txt" -Append

# Cửa sổ 2 — vngis-ee-ha-tinh-lai-chau
$env:USERPROFILE = "C:\ee-profiles\acc-ftu"
cd "C:\Users\AD\Downloads\vietnam_satelline_final-vngis-tinh-001-011\vietnam_satelline_final-vngis-tinh-001-011"
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $python -m task_pipeline.national --product SENTINEL2 --years 2024 --project vngis-ee-ha-tinh-lai-chau --shard 2/6 2>&1 | Tee-Object -FilePath "E:\SatelliteData\_control\national\log_s2_2024_p2.txt" -Append

# ... tương tự cho 4 project còn lại (acc-quynhmai/3, acc-work/4, acc-qec/5, acc-4usd/6)
```
Project nào xong phần mình sẽ báo `this shard is done; N tiles of other shards still missing`.
**Phải chạy đủ cả 6 cửa sổ**, thiếu một phần thì năm đó không bao giờ hoàn chỉnh.

### 5.4. Ghép và cắt sau khi tải xong
```powershell
# Ghép 1 năm thành file .tif duy nhất (không cần --project)
& $python -m task_pipeline.national --merge --product SENTINEL2 --years 2024

# Cắt theo 63 tỉnh (cần --project để lấy ranh giới)
& $python -m task_pipeline.national --clip --product SENTINEL2 --years 2024 --project vngis-ee-2
```

---

## 6. Theo dõi tiến độ, đọc output

### 6.1. Dòng tiến độ trên màn hình / trong log
```
Earth Engine project: vngis-ee-2 | workers 1
SENTINEL2 2024: grid 81000 x 167000 px at 10 m, 2490 tiles over Vietnam (625 empty skipped), tile 1280 px; shard 1/6 takes 415
  round 1: 0 tiles done, 415 to download
  SENTINEL2 2024: 20/415 tiles, 0 failed, 69 tiles/h, ~5.7 h left
```
- `tiles/h`, `h left`: tốc độ và thời gian còn lại **thật**, đọc trực tiếp dòng này để biết tiến độ.
- `N tiles failed this round; retrying in X min`: bình thường, nhất là khi project đang ở chế độ
  hạn chế (429). Code tự thử lại theo vòng, không cần can thiệp.
- `this shard is done; ...`: phần của luồng này xong, đang chờ các luồng khác.
- `COMPLETE -> ...vrt`: năm đó đã đủ mọi mảnh.
- Các dòng đỏ `CPLE_AppDefined ...`: cảnh báo của GDAL, không phải lỗi, bỏ qua được.
- `UserWarning: Your project has exceeded its noncommercial compute quota...`: project đang ở
  chế độ hạn chế, vẫn chạy tiếp nhưng chậm.

### 6.2. Lệnh kiểm tra tiến độ từ ngoài (không cần đọc hết log)
```powershell
Get-ChildItem "E:\SatelliteData\VN_LandCover_Panel_2004_2025\raw_data\DAY\SENTINEL2\VN_SENTINEL2_*" -Directory | ForEach-Object {
    $tiles = Get-ChildItem (Join-Path $_.FullName "tiles") -Filter *.tif -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike "*.part.tif" }
    $vrt = Test-Path (Join-Path $_.FullName "$($_.Name).vrt")
    "{0}: {1} manh, {2:N1} GB, xong: {3}" -f $_.Name, $tiles.Count, (($tiles | Measure-Object Length -Sum).Sum/1GB), $vrt
}
```

### 6.3. Dừng và chạy lại (an toàn, không mất dữ liệu)
- **Ctrl+C**: dừng có trật tự. Mảnh đang tải dở bị bỏ, mảnh đã xong được giữ.
- Chạy lại **đúng lệnh cũ** (nhấn ↑ rồi Enter): tự động tiếp tục, bỏ qua phần đã có.
- Gập máy / tắt màn hình: cần tắt chế độ Sleep trước (`powercfg /change standby-timeout-ac 0`,
  đổi "khi gập máy" thành "Do nothing" trong Power Options), nếu không mọi luồng sẽ bị treo.
- Tắt hẳn máy: luồng dừng hẳn, không có cách tiếp tục khi máy tắt trừ khi chạy trên máy ảo cloud.

---

## 6b. Chạy 10 luồng trên máy ảo Google Cloud (tắt/gập laptop vẫn chạy)

Laptop tắt thì mọi luồng trên laptop dừng. Muốn chạy liên tục, đặt chúng trên một **máy ảo Linux**
(Compute Engine), trả bằng tín dụng dùng thử 300 USD. Ba script có sẵn trong `scripts/cloud_vm/`.

### Tạo máy ảo
Console → **Compute Engine → VM instances → Create instance**:
- Name `vngis-vm`, Region **asia-southeast1 (Singapore)**, Machine type **e2-standard-4**
  (4 CPU — 10 luồng chủ yếu là chờ Earth Engine, nhưng 4 CPU an toàn hơn 2).
- Boot disk: **Ubuntu 24.04 LTS**, 30 GB.
- Advanced → Disks → **Add new disk**: tên `data`, **Standard persistent disk**, **500 GB**.

### Cài đặt (bấm nút SSH cạnh tên máy ảo, dán vào cửa sổ terminal)
```bash
curl -sL https://raw.githubusercontent.com/anductrung-160526/vietnam_satelline_final/vngis-tinh-001-011/scripts/cloud_vm/setup.sh -o setup.sh && bash setup.sh
```

### Nạp xác thực cho 10 tài khoản
**Cách A — service-account key (khuyên dùng, không cần trình duyệt):** trong cửa sổ SSH bấm nút
**⚙ → Upload file** để đưa 10 file key JSON lên máy ảo, rồi đặt đúng tên:
```bash
mkdir -p ~/ee-keys
mv ~/<ten-file-key-1>.json ~/ee-keys/acc-wqiqc.json      # luồng 1  → vngis-ee-2
mv ~/<ten-file-key-2>.json ~/ee-keys/acc-ftu.json        # luồng 2
# ... acc-quynhmai, acc-work, acc-qec, acc-4usd,
#     acc-miendao (vgis-ee-07), acc-ducanchu (vgis-ee-08),
#     acc-linhbe (vgis-ee-09), acc-mpnguyen (vgis-ee-10)
chmod 600 ~/ee-keys/*.json
```
Tên file **phải khớp** cột "Profile" trong `CLAUDE.md` (phần sau `acc-`), vì `run.sh` tìm theo tên đó.

**Cách B — đăng nhập OAuth từng tài khoản** (nếu không có key):
```bash
cd ~/vietnam_satelline_final
bash scripts/cloud_vm/login.sh acc-miendao  vgis-ee-07
bash scripts/cloud_vm/login.sh acc-ducanchu vgis-ee-08
bash scripts/cloud_vm/login.sh acc-linhbe   vgis-ee-09
bash scripts/cloud_vm/login.sh acc-mpnguyen vgis-ee-10
# ... và 6 tài khoản cũ
```
Mỗi lệnh in ra một link → mở trên trình duyệt laptop → đăng nhập **đúng tài khoản** → dán mã về.

### Chạy 10 luồng nền
```bash
cd ~/vietnam_satelline_final
bash scripts/cloud_vm/run.sh SENTINEL2 2024          # một năm
bash scripts/cloud_vm/run.sh SENTINEL2 2015-2025     # hoặc cả giai đoạn, lần lượt từng năm
```
`run.sh` tự chia `--shard 1/10` … `10/10` theo bảng tài khoản, mỗi luồng một phiên `tmux` riêng.
**Sau bước này đóng cửa sổ SSH và tắt laptop được** — các luồng vẫn chạy trên máy ảo.

### Theo dõi (mở SSH lại bất cứ lúc nào)
```bash
tail -n 3 /data/SatelliteData/_control/national/log_SENTINEL2_p*.txt   # tiến độ 10 luồng
tmux ls                                                                # phiên nào đang chạy
tmux attach -t p7                                                      # xem luồng 7; thoát: Ctrl+B rồi D
df -h /data                                                            # dung lượng còn lại
```
Máy ảo khởi động lại hoặc luồng nào dừng: chạy lại đúng lệnh `run.sh`, nó bỏ qua phiên đang chạy
và chỉ khởi động lại phiên đã tắt.

### Ghép và đưa về ổ E
```bash
cd ~/vietnam_satelline_final && .venv/bin/python -m task_pipeline.national \
  --merge --product SENTINEL2 --years 2024 --root /data/SatelliteData
```
Trên laptop (cài Google Cloud CLI, `gcloud init` một lần):
```powershell
gcloud compute scp --zone <zone-cua-vm> vngis-vm:/data/SatelliteData/VN_LandCover_Panel_2004_2025/raw_data/DAY/SENTINEL2/VN_SENTINEL2_2024/VN_SENTINEL2_2024.tif "E:\SatelliteData\VN_LandCover_Panel_2004_2025\raw_data\DAY\SENTINEL2\"
```

### Chi phí và an toàn tín dụng
- Ước tính: máy ảo e2-standard-4 + ổ 500 GB + tải ~300 GB về ≈ **100–180 USD** cho khoảng 1 tháng.
- Đặt **Budget alert** trong **Billing → Budgets & alerts**.
- **Không bấm "Activate"/"Upgrade"** → tài khoản vẫn là Free Trial, không bao giờ bị trừ thẻ.
- Xong việc: **tải hết dữ liệu về ổ E trước**, rồi xoá máy ảo và ổ `data` để ngừng tiêu tín dụng.
- Quota Earth Engine **không đổi** khi chạy trên máy ảo; máy ảo chỉ giúp chạy 24/24.

---

## 7. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Could not find a part of the path '...\_control\national\log_...txt'` | Chưa tạo thư mục log | Chạy `New-Item -ItemType Directory -Force "E:\SatelliteData\_control\national"` trước |
| `Your project has exceeded its noncommercial compute quota` (cảnh báo đỏ) | Project đang ở chế độ hạn chế | Không phải lỗi dừng chương trình; cứ để chạy tiếp, sẽ chậm hơn. Chờ quota đặt lại đầu tháng |
| `429` / `Too many concurrent aggregations` | Earth Engine tạm thời từ chối | Code tự thử lại; nếu liên tục lặp lại, giảm `--workers` |
| `WinError 1392: The file or directory is corrupted and unreadable` | Ổ E bị ghi dở do rút ổ/mất điện/ngủ giữa chừng | Dừng mọi lệnh đang dùng ổ E, chạy `chkdsk E: /f /x` bằng PowerShell quyền Administrator, rồi chạy lại lệnh cũ |
| `out-file : The device is not ready` | Ổ E bị ngắt kết nối giữa lúc chạy | Kiểm tra cáp/cổng USB, tắt "USB selective suspend" trong Power Options, cắm trực tiếp không qua hub, rồi `chkdsk` như trên |
| Dòng tiến độ tăng vọt bất thường (hàng trăm/nghìn tiles/h) ngay sau khi chạy lại | Các mảnh đã tải xong trước đó được nhận lại ngay lập tức, không phải tốc độ thật | Đợi khoảng 30–60 phút để tốc độ ổn định rồi mới đọc `tiles/h` |
| `No usable source image for this period` (ở `try_one.py`, lệnh test 1 ảnh) | Tháng/khu vực đó không có cảnh đạt yêu cầu (quá nhiều mây) | Thử tháng khác hoặc khu vực khác |

---

## 8. Thêm một luồng thứ N (tóm tắt các bước)

1. Tạo project Google Cloud mới (mục 1.1), đăng ký Earth Engine (1.2), kiểm tra quota (1.3).
2. Thêm một dòng vào bảng tài khoản/project trong `CLAUDE.md`.
3. Trên máy Windows: tạo thư mục profile mới (4.2), đăng nhập Earth Engine cho tài khoản đó (4.3).
4. Chạy lệnh theo khuôn mẫu ở mục 5.1, thay `--project` và `$env:USERPROFILE` cho đúng luồng mới.
5. Nếu dùng `--shard` để nhiều luồng chia sẻ một năm: nhớ cập nhật số `n` ở **tất cả** các luồng
   đang chia sẻ năm đó, không chỉ luồng mới.
