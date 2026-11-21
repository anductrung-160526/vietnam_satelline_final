# VNGISDash — ứng dụng kinh tế đêm

Nguyên mẫu web đọc chỉ số ánh sáng ban đêm của **63 tỉnh Việt Nam trước sáp nhập,
2004–2025**, và ước lượng hệ số co giãn ánh sáng–GRDP.

Nhánh `night-app` chứa ứng dụng và bước tính lại chỉ số từ ảnh tỉnh đã lọc.
Xem `docs/NIGHT_DATA_DICTIONARY.md` và `backend/data/calculate_ntl.py`.
Luồng tải ảnh từ Earth Engine, bộ xử lý đầy đủ và công cụ chẩn đoán dữ liệu
vẫn nằm ở nhánh `inspriring-newton`. Xem mục "Nhánh này đã bỏ gì" ở cuối.

## Cấu trúc

```
backend/                  Python — không có tệp nào phục vụ trình duyệt ngoài frontend/
├── api/                  FastAPI + TiTiler: lớp CHỈ ĐỌC, không tính chỉ số
│   ├── main.py           các đầu mối /api/*, phục vụ frontend/ ở '/'
│   ├── store.py          truy vấn SQLite, danh mục chỉ số, cảnh báo dữ liệu
│   └── export.py         gói .zip theo yêu cầu của cô: ảnh + chỉ số + kinh tế
├── core/                 công thức và dữ liệu nền, dùng chung
│   ├── chi_so.py         do_co_gian (β), hàm thời gian, CODEBOOK
│   ├── nguon.py          tên hai gói dữ liệu trên ổ dữ liệu
│   └── ranh_gioi/        dựng ranh giới 63 tỉnh từ GADM 4.1
└── data/                 các bước chuẩn bị dữ liệu, chạy tay rồi mới chạy app
    ├── calculate_ntl.py      ảnh tỉnh đã lọc -> CSV chỉ số đêm
    ├── build_indices.py      CSV  -> SQLite
    ├── build_boundaries.py   GADM -> provinces.geojson
    ├── build_cogs.py         ảnh năm  -> COG cho bản đồ
    ├── build_monthly_cogs.py ảnh tháng -> COG cho bản đồ
    ├── gia_lap_kinh_te.py    sinh số kinh tế GIẢ LẬP để chạy thử màn thứ ba
    ├── demo_seed.py          vài tỉnh mẫu khi chưa có dữ liệu thật
    ├── schema.sql            lược đồ SQLite
    └── economy_mau.csv       mẫu điền dân số và GRDP

frontend/                 HTML + CSS + JS thuần, không có bước build
├── index.html            khung ba màn
├── app.js                MapLibre, bộ lọc, bảng, biểu đồ ECharts
├── style.css
└── vendor/               maplibre-gl, echarts — để sẵn, không gọi CDN

tests/                    94 test
docs/                     đặc tả màn hình, ý nghĩa chỉ số, sơ đồ kiến trúc
Dockerfile.backend        một ảnh container cho cả API lẫn TiTiler
```

Ranh giới rạch ròi: **mọi thứ trình duyệt tải về nằm trong `frontend/`**, mọi thứ
chạy trên máy chủ nằm trong `backend/`. `backend/api/main.py` tự phục vụ `frontend/`
ở đường dẫn gốc, nên chạy một tiến trình là đủ, không cần máy chủ web riêng.

## Ba màn hình

| Màn | Nội dung |
|---|---|
| **Ảnh đêm** | Bản đồ nền ban đêm cắt theo ranh giới tỉnh, ba thẻ SOL / Diện tích / Mật độ, tải `.tif` toàn quốc hoặc theo tỉnh |
| **Chỉ số đêm** | Bộ lọc kiểu World Bank DataBank (tỉnh, chỉ số, cây thời gian năm→tháng), bảng tỉnh × chỉ số, biểu đồ chuỗi thời gian, tải CSV |
| **Chỉ số kinh tế đêm** | Ánh sáng bình quân đầu người, hệ số β trong `ln(GRDP) = α + β·ln(SOL)`, biểu đồ phân tán kèm đường hồi quy |

Chi tiết từng màn: `docs/DAC_TA_MAN_HINH.md`. Ý nghĩa từng chỉ số:
`docs/CHI_SO_KINH_TE_DEM.md`.

## Chạy tại chỗ

```bash
pip install -r backend/requirements.txt

# 1. Nạp chỉ số vào SQLite. Bảng nào chưa có dữ liệu thì để rỗng chứ không lỗi.
#    LÀM TRƯỚC build_cogs: đổi SCHEMA_VERSION thì build_indices dựng lại cơ sở dữ
#    liệu và xoá sổ ảnh COG, nên chạy sau sẽ mất hết ảnh đã vào sổ.
python3 -m backend.data.build_indices --root /data/SatelliteData

# 2. Ranh giới tỉnh cho bản đồ. Lần đầu thêm --tai-gadm để tải GADM 4.1 (~50 MB);
#    prepare_gadm đối chiếu SHA-256 của cả tệp nén lẫn nội dung trước khi dùng.
#    Máy nào đã tải ở nhánh pipeline thì chép hai tệp sang, khỏi tải lại:
#      province_pipeline/config/boundaries*.json -> backend/core/ranh_gioi/config/
python3 -m backend.data.build_boundaries --tai-gadm

# 3. Ảnh nền cho bản đồ (theo năm, rồi theo tháng).
python3 -m backend.data.build_cogs --root /data/SatelliteData --kinds VIIRS DMSP
python3 -m backend.data.build_monthly_cogs --root /data/SatelliteData --kiem-ke

# 4. Chạy
python3 -m uvicorn backend.api.main:app --reload --port 8000
```

Mở <http://localhost:8000>. Đầu mối `/api/health` cho biết máy chủ đang phục vụ đúng
tệp giao diện nào — hữu ích khi màn hình không giống bản vừa sửa.

## Số liệu kinh tế

Điền `backend/data/economy_mau.csv`, lưu thành `data_processed/economy.csv`, chạy lại
`build_indices`. Cột `grdp_price_basis` phải ghi `so_sanh` hoặc `hien_hanh` — **giá
hiện hành làm β sai lệch vì lạm phát**, và app sẽ hiện cảnh báo đỏ.

Chưa có số thật thì sinh số giả lập để chạy thử giao diện:

```bash
python3 -m backend.data.gia_lap_kinh_te --root /data/SatelliteData
```

Mọi dòng mang `source = GIA_LAP`, và API dò nhãn đó ngay trên dữ liệu để đẩy một cảnh
báo đỏ lên đầu màn. β hiện ra khi đó là con số đã cấy vào lúc sinh dữ liệu, **không
phải kết quả nghiên cứu**.

## Nguyên tắc: đây là lớp chỉ đọc

API **không tính chỉ số**. Số liệu do nhánh pipeline hoặc bước chạy tay
`backend.data.calculate_ntl` tính và ghi ra `data_processed/*.csv`. `backend/core/chi_so.py` chỉ giữ các công thức mà màn hình
gọi trực tiếp (β, hàm thời gian) và CODEBOOK.

Đổi công thức ở đây mà không đổi ở nhánh pipeline thì cột trong bảng và con số trên
màn hình nói hai chuyện khác nhau, **mà không có gì báo lỗi**.

## Nhánh này đã bỏ gì

So với `inspriring-newton`, nhánh `night-app` bỏ những thứ không dự phần vào việc
chạy app. Mọi thứ dưới đây vẫn còn nguyên ở nhánh kia:

| Đã bỏ | Vì sao |
|---|---|
| `task_pipeline/` (875 dòng riêng `derive.py`) | luồng tải và tính chỉ số; app chỉ cần 157 dòng, đã trích sang `backend/core/chi_so.py` |
| `province_pipeline/` (3.530 dòng) | hạ tầng Earth Engine; app chỉ cần phần dựng ranh giới, đã trích sang `backend/core/ranh_gioi/` |
| `pipeline_core/`, `run_pipeline.py`, hai gói `VN_*_Panel_*` | pipeline cấp huyện, đã bị thay thế |
| `vngis_2024.py`, `verify_pilot.py`, `vngis-github-repo-v6/` | bản một tệp đời đầu và một bản sao của nó |
| `scripts/` (chẩn đoán, PowerShell, máy ảo) | công cụ vận hành dữ liệu, không chạy app |
| `notebooks/`, `.github/` | notebook đối chiếu và CI của pipeline |
| 25 trong 27 tệp test | chúng kiểm pipeline; giữ lại `test_app_api.py` và `test_monthly_cogs.py` |

`backend/core/chi_so.py` và `backend/core/ranh_gioi/` là bản **chép nguyên văn**, đã
đối chiếu cho ra kết quả y hệt bản gốc. Sửa một bên thì phải sửa cả bên kia.
