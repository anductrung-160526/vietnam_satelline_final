# Cấu trúc repo: hiện trạng và đề xuất

Viết ngày 16/11/2026, trên nhánh `inspriring-newton`.

## Tóm tắt

Repo không chỉ lộn xộn về thư mục. Nó đang chứa **ba đời pipeline chồng lên nhau**,
trong đó hai đời đã chết nhưng vẫn nằm nguyên và vẫn được test tham chiếu tới. Thêm
vào đó là 14 tệp `.pyc` bị commit nhầm, một thư mục sao chép nguyên si của bản phát
hành cũ, và một vụ **trùng tên** giữa thư mục trong repo với thư mục dữ liệu trên ổ E
— chỗ này là nguy hiểm thật sự chứ không phải chuyện thẩm mỹ.

---

## 1. Hiện trạng

```
vietnam_satelline_final/
│
├── CLAUDE.md                      ĐỜI 3 · quy tắc dự án
├── requirements.txt               ĐỜI 3
├── .github/                       ĐỜI 3 · CI
│
├── province_pipeline/     (43)    ĐỜI 3 · hạ tầng: ranh giới GADM, Earth Engine,
│                                           xuất ảnh, kiểm chất lượng raster
├── task_pipeline/         (25)    ĐỜI 3 · luồng tải + tính chỉ số, CẤP TỈNH
│                                           derive.py là trái tim của dự án
├── app/                   (23)    ĐỜI 3 · FastAPI + TiTiler + web tĩnh
├── scripts/               (19)    ĐỜI 3 · công cụ chẩn đoán + ps1 Windows + sh máy ảo
├── tests/                 (27)    ĐỜI 3 · 492 test
├── docs/                   (7)    ĐỜI 3
├── notebooks/task123/      (4)    ĐỜI 3 · notebook gốc của cô, để đối chiếu
│
├── run_pipeline.py                ĐỜI 2 ╮
├── pipeline_core/         (12)    ĐỜI 2 │ pipeline CẤP HUYỆN
├── VN_NTL_Panel_2004_2025/ (16)   ĐỜI 2 │ đã bị task_pipeline thay thế hoàn toàn
├── VN_LandCover_Panel_2004_2025/  ĐỜI 2 ╯
│                          (20)
│
├── vngis_2024.py   (1.639 dòng)   ĐỜI 1 ╮
├── verify_pilot.py                ĐỜI 1 │ bản một tệp đầu tiên
├── GHI_CHU.md                     ĐỜI 1 │ CÒN SỐNG: 2 test vẫn import vngis_2024
├── HUONG_DAN.md                   ĐỜI 1 │
├── DOI_CHIEU_NOTEBOOK.md          ĐỜI 1 ╯
│
└── vngis-github-repo-v6/   (6)    BẢN SAO của đời 1, cũ hơn bản ở gốc
```

### Bốn vấn đề cụ thể

**V1 — `vngis-github-repo-v6/` là bản sao thừa.**
`GHI_CHU.md` và `DOI_CHIEU_NOTEBOOK.md` giống hệt bản ở gốc; `vngis_2024.py` và
`requirements.txt` là phiên bản **cũ hơn**. Không một tệp nào trong repo import tới
nó. Đây là ảnh chụp của một bản phát hành cũ bị kéo nhầm vào.

**V2 — 14 tệp `.pyc` bị commit.**
`.gitignore` có `__pycache__/` nhưng chúng được thêm vào git **trước khi** dòng đó
tồn tại, nên git vẫn theo dõi tiếp. Nằm rải ở `pipeline_core/`, hai gói `VN_*` và gốc.

**V3 — trùng tên giữa repo và ổ dữ liệu.** Đây là vấn đề nguy hiểm nhất.
Trong repo có thư mục `VN_NTL_Panel_2004_2025/` (đời 2, cấp huyện, chỉ còn vài tệp
mẫu 433 byte). Trên ổ E cũng có `E:\SatelliteData\VN_NTL_Panel_2004_2025\` (dữ liệu
thật, hàng trăm GB). Hai thứ **hoàn toàn khác nhau nhưng trùng tên**.

`app/data/build_indices.py` và 6 script chẩn đoán đều ghép đường dẫn bằng chuỗi
`'VN_NTL_Panel_2004_2025'`. Chạy đúng chỗ thì trỏ ra ổ E; chạy nhầm thư mục gốc một
cái là đọc phải bộ mẫu 4 dòng trong repo mà **không báo lỗi gì** — chỉ ra bảng rỗng.
Đúng kiểu hỏng âm thầm đã làm mất mấy ngày tuần trước.

**V4 — đời 1 và đời 2 chưa chết hẳn.**
- `tests/test_province_stop.py` và `tests/test_ee_requests.py` vẫn `import vngis_2024`.
- `tests/test_app_api.py` liệt `pipeline_core` vào danh sách gói nội bộ.
- `VN_*/code/*.py` vẫn import `pipeline_core`.

Nên **không thể xoá thẳng** — phải gỡ theo thứ tự.

---

## 2. Cấu trúc đề xuất

```
vietnam_satelline_final/
│
├── README.md                  ← MỚI: điểm vào duy nhất, chỉ đường cho người mới
├── CLAUDE.md                     quy tắc dự án
├── requirements.txt
│
├── province_pipeline/            giữ nguyên — hạ tầng
├── task_pipeline/                giữ nguyên — luồng tải + tính chỉ số
├── app/                          giữ nguyên — web
├── tests/                        giữ nguyên
├── notebooks/                    giữ nguyên — notebook gốc của cô
│
├── scripts/
│   ├── chan_doan/             ← gom 6 script điều tra dữ liệu
│   │     kiem_tra_chi_so_dem.py      soi bảng chỉ số đêm
│   │     kiem_dinh_chat_luong.py     kiểm định kỹ thuật toàn bộ bảng
│   │     kiem_tra_thang_thieu.py     tháng trống + dao động sol
│   │     kiem_tra_nguon_viirs.py     hỏi Earth Engine có ảnh không
│   │     kiem_tra_khau_roi.py        ảnh rơi ở chặng nào
│   │     soi_mot_anh.py              mở thẳng một ảnh ra đếm cf_cvg
│   ├── du_lieu/               ← script thao tác dữ liệu
│   │     gia_lap_kinh_te.py          sinh số kinh tế giả lập
│   │     sap_xep_du_lieu.py          kiểm kê và dọn gói dữ liệu
│   ├── windows/                  giữ nguyên — 7 tệp .ps1
│   └── cloud_vm/                 giữ nguyên — 4 tệp .sh
│
├── docs/
│   ├── CAU_TRUC_REPO.md          tệp này
│   ├── CHI_SO_KINH_TE_DEM.md
│   ├── DAC_TA_MAN_HINH.md
│   ├── KIEM_KE_DU_LIEU.md
│   ├── THAM_KHAO_FAS_IMF.md
│   ├── TIEN_DO_DEMO_23_11.md
│   └── kien_truc/
│
└── legacy/                    ← MỚI: đời cũ, chỉ để tra cứu, không chạy
    ├── README.md                 giải thích mỗi thư mục là đời nào, chết khi nào
    ├── doi_1_mot_tep/
    │     vngis_2024.py  verify_pilot.py  GHI_CHU.md
    │     HUONG_DAN.md   DOI_CHIEU_NOTEBOOK.md
    └── doi_2_cap_huyen/
          run_pipeline.py  pipeline_core/
          VN_NTL_Panel_2004_2025/  VN_LandCover_Panel_2004_2025/
```

Nguyên tắc: **ba gói đang sống nằm ở gốc, mọi thứ đã chết vào `legacy/`.** Nhìn vào
gốc repo là biết ngay cái gì đang chạy.

### Vì sao không gom hết vào `src/`

Có thể làm, nhưng đổi mọi đường import của 95 tệp và mọi lệnh `python -m` trong tài
liệu lẫn script PowerShell. Lợi ích là thẩm mỹ, rủi ro là gãy thật. Không đáng.

---

## 3. Kế hoạch gỡ, chia theo rủi ro

### Bước 0 — làm được ngay, an toàn tuyệt đối (khoảng 2 phút)

Không tệp nào đang chạy bị động tới:

```bash
git rm -r --cached $(git ls-files | grep __pycache__)   # bỏ 14 tệp .pyc khỏi git
echo ".pytest_cache/" >> .gitignore
git rm -r vngis-github-repo-v6                          # bản sao thừa, không ai import
git commit -m "Dọn tệp biên dịch bị commit nhầm và bản sao repo cũ"
python -m pytest tests/ -q                              # phải vẫn 492 pass
```

### Bước 1 — sau demo: chống hỏng âm thầm (V3)

Việc **quan trọng nhất** trong cả danh sách, vì nó là lỗi chực chờ chứ không phải
chuyện gọn gàng. Hai cách, nên làm cả hai:

1. Đưa `'VN_NTL_Panel_2004_2025'` ra một hằng số duy nhất (đã có
   `province_pipeline/sources.py: NTL_PACKAGE`) và bắt mọi script dùng nó, thay vì
   mỗi tệp tự viết lại chuỗi.
2. Thêm phép kiểm: nếu `--root` trỏ vào chính thư mục repo thì **dừng và báo lỗi**,
   chứ không im lặng đọc bộ mẫu 4 dòng.

Sau khi `VN_*` trong repo chuyển vào `legacy/` thì nguy cơ này cũng tự giảm.

### Bước 2 — sau demo: dời đời 2 vào `legacy/`

```bash
mkdir -p legacy/doi_2_cap_huyen
git mv run_pipeline.py pipeline_core VN_NTL_Panel_2004_2025 \
       VN_LandCover_Panel_2004_2025 legacy/doi_2_cap_huyen/
```
Phải sửa: `tests/test_app_api.py` (danh sách `NOI_BO`), và import `pipeline_core`
trong `legacy/doi_2_cap_huyen/VN_*/code/*.py`.

### Bước 3 — sau demo: dời đời 1 vào `legacy/`

```bash
mkdir -p legacy/doi_1_mot_tep
git mv vngis_2024.py verify_pilot.py GHI_CHU.md HUONG_DAN.md \
       DOI_CHIEU_NOTEBOOK.md legacy/doi_1_mot_tep/
```
Phải sửa đường import trong `tests/test_province_stop.py` và `tests/test_ee_requests.py`.

**Cân nhắc trước khi làm:** hai test đó đang kiểm `vngis_2024.py`, mà tệp này không
còn được dùng để chạy gì cả. Có hai lựa chọn, nên hỏi ý cô vì nó liên quan tới phần
đối chiếu với notebook gốc:
- Giữ test (bảo toàn lịch sử đối chiếu, đổi lấy việc phải nuôi đường import tới
  `legacy/`).
- Bỏ cả test lẫn tệp (gọn hơn, nhưng mất bằng chứng đã đối chiếu với notebook).

### Bước 4 — sau demo: chia nhỏ `scripts/`

```bash
mkdir -p scripts/chan_doan scripts/du_lieu
git mv scripts/kiem_tra_*.py scripts/soi_mot_anh.py \
       scripts/kiem_dinh_chat_luong.py scripts/chan_doan/
git mv scripts/gia_lap_kinh_te.py scripts/sap_xep_du_lieu.py scripts/du_lieu/
```
Phải sửa: đường dẫn trong `tests/test_app_api.py` (2 chỗ nạp script bằng
`importlib`), và mọi lệnh ví dụ trong `docs/`.

### Bước 5 — viết `README.md` ở gốc

Hiện chưa có. Người mới mở repo ra không biết bắt đầu từ đâu, mà `CLAUDE.md` là quy
tắc chứ không phải hướng dẫn. Cần: dự án làm gì, chạy app thế nào, chạy pipeline thế
nào, dữ liệu nằm ở đâu, `legacy/` là gì.

---

## 4. Khuyến nghị về thời điểm

**Trước demo 23/11: chỉ làm Bước 0.** Nó không động tới tệp nào đang chạy.

Bước 1–5 đụng vào đường import và đường dẫn, mà tuần này là tuần nước rút. Một lần
`git mv` nhầm chỗ là mất buổi tối sửa import thay vì dựng COG. Dọn repo không ghi
điểm trong buổi demo; bản đồ đêm trống thì mất điểm thật.

Sau demo thì làm lần lượt 1 → 5, mỗi bước một commit, chạy `pytest` sau mỗi bước.
