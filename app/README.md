# VNGISDash — lớp web

Nguyên mẫu Web Dashboard: bản đồ nền ban đêm, tra cứu theo tỉnh, biểu đồ chuỗi thời gian,
nút trích xuất dữ liệu.

**Đây là lớp CHỈ ĐỌC.** Mọi con số đều do `task_pipeline/derive.py` tính ra và ghi vào
`data_processed/*.csv`. API không tính chỉ số. Nếu app cần một con số chưa có, bổ sung vào
`derive.py` kèm test, đừng tính trong API — nếu không thì sẽ có hai nguồn chân lý.

## Chạy thử tại chỗ

```bash
pip install -r app/requirements.txt

# 1. Nạp chỉ số thật vào SQLite (bảng nào chưa có dữ liệu thì để rỗng, không lỗi)
python3 -m app.data.build_indices --root /data/SatelliteData

# 2. (tuỳ chọn) Ranh giới tỉnh cho bản đồ — cần GADM 4.1 đã kiểm SHA-256
python3 -m app.data.build_boundaries --config .province-local/config.json

# 3. (tuỳ chọn) Ảnh COG nhẹ cho bản đồ — cần gdal-bin
python3 -m app.data.build_cogs --root /data/SatelliteData

# 4. Chạy
uvicorn app.api.main:app --reload      # http://localhost:8000
```

Chưa có chỉ số thật mà cần demo giao diện:

```bash
python3 -m app.data.demo_seed          # số GIẢ LẬP, giao diện treo biển báo đỏ
```

Số giả lập có `status='GIA_LAP'`; chạy lại `build_indices.py` là bị xoá sạch.
**Không bao giờ lấy số từ đó đưa vào báo cáo.**

## Các đầu mối API

| Đường dẫn | Trả về |
|---|---|
| `GET /api/health` | tình trạng, số tỉnh, đường dẫn cơ sở dữ liệu |
| `GET /api/provinces` | 63 tỉnh, kèm số năm đã có dữ liệu từng loại |
| `GET /api/indices?ma_tinh=01&nam_tu=2004&nam_den=2025` | chuỗi đêm, ngày, kinh tế + cảnh báo phương pháp |
| `GET /api/coverage` | năm nào đã có dữ liệu gì (dùng cho báo cáo tiến độ) |
| `GET /api/basemap` | các năm có ảnh nền đêm |
| `GET /api/originals` | ảnh gốc ở tầng lạnh (chỉ liệt kê) |
| `GET /api/export.zip?ma_tinh=01` | gói 4 phần: ảnh đêm + chỉ số ngày + chỉ số đêm + chỉ số kinh tế |
| `GET /api/indicators` | danh mục chỉ số, kèm số tỉnh và khoảng năm thực có |
| `GET /api/panel?chi_so=sol_ntl&nam_tu=2004&nam_den=2025` | bảng kiểu WDI: 63 tỉnh × các năm |
| `GET /api/panel.csv?chi_so=sol_ntl&dang=rong\|dai` | tải bảng về, dạng rộng hoặc dạng dài |
| `GET /api/choropleth?chi_so=sol_ntl&nam=2024` | một chỉ số một năm cho mọi tỉnh, để tô màu bản đồ |
| `GET /tiles/cog/...` | ô bản đồ (chỉ có khi đã cài `titiler.core`) |

## Giao diện

**Tab Bản đồ**
- Mở lên là **toàn Việt Nam**, 63 tỉnh tô màu theo chỉ số và năm đang chọn.
  Thang màu căn theo căn bậc hai vì độ sáng lệch rất mạnh — tuyến tính thì 60 tỉnh cùng một màu.
  Tỉnh chưa có số liệu để màu xám xanh, phân biệt rõ với bậc thấp nhất.
- **Chọn một tỉnh** (bằng danh sách hoặc bấm thẳng lên bản đồ) thì bản đồ phóng vào tỉnh đó
  và **che toàn bộ phần ngoài ranh giới**: một đa giác phủ cả thế giới, khoét lỗ đúng hình tỉnh.
  Nút “← Toàn quốc” quay lại.
- Thanh trượt năm đổi cả màu tô lẫn ảnh nền đêm.

**Tab Dữ liệu** — dựng theo World Development Indicators của World Bank
- Chọn chỉ số, khoảng năm, lọc tỉnh theo tên.
- Bảng: mỗi dòng một tỉnh, mỗi cột một năm. Cột tên tỉnh và hàng tiêu đề dính khi cuộn.
- Ô trống hiện `··`, nghĩa là **chưa có số liệu**, không phải bằng không.
- Tải về hai dạng: **bảng rộng** (dán vào Excel) và **bảng dài** (Stata, R, pandas).
  Cả hai đều có phần đầu ghi tên chỉ số, đơn vị, nguồn bảng và cảnh báo phương pháp.

## Nguyên tắc thiết kế

- **Thiếu dữ liệu thì nói ra.** Không bao giờ vẽ 0, không bao giờ để trang trắng.
  Tỉnh chưa có chỉ số trả về 200 với mảng rỗng, giao diện ghi "chưa có số liệu".
- **Cảnh báo phương pháp đi theo dữ liệu.** TOA 2015–2018 và việc chưa hiệu chỉnh
  DMSP–VIIRS xuất hiện cả trên màn hình lẫn trong file tải về.
- **Từng phần hỏng độc lập.** Bản đồ tải không được thì biểu đồ vẫn chạy, và ngược lại.
- **Ảnh gốc không lên đám mây.** 24 GB/năm ở tầng lạnh; đám mây chỉ giữ bản nén ~100 MB.
- **Thư viện trình duyệt nằm trong repo** (`app/web/vendor/`) — mạng chặn CDN vẫn chạy.

## Triển khai Cloud Run

```bash
gcloud builds submit --tag asia-southeast1-docker.pkg.dev/<PROJECT>/vngis/dash -f app/Dockerfile .
gcloud run deploy vngisdash \
  --image asia-southeast1-docker.pkg.dev/<PROJECT>/vngis/dash \
  --region asia-southeast1 --allow-unauthenticated --min-instances 0
```

Chỉ số nhỏ nên đóng luôn `vngis.db` vào ảnh container ở giai đoạn nguyên mẫu. Khi dữ liệu
lớn hơn hoặc cần cập nhật không phải dựng lại ảnh thì chuyển sang Cloud SQL —
chỉ phải sửa `app/api/store.py`, phần còn lại giữ nguyên.
