# PHẦN A — CHUẨN BỊ DỮ LIỆU VÀ MÔI TRƯỜNG

Ngày kiểm tra: 21/11/2026. Nhánh: `night-app`.

## 1. Kết quả thực hiện đến hiện tại

| Mục trong kế hoạch A | Đã làm | Phần còn phải xác nhận trên máy demo |
|---|---|---|
| Repo, nhánh, Python | Đã kiểm tra workspace Codex: repo `anductrung-160526/vietnam_satelline_final`, nhánh `night-app`; bộ chuẩn bị tự ghi HEAD, remote SHA, Python và phiên bản thư viện | Máy Windows/Antigravity có thể khác workspace; cần chạy lệnh ở mục 2 |
| Sao lưu trước cập nhật, đóng tab cũ | Công cụ lưu patch nhị phân của tracked changes, staged changes và Git status, không reset/pull/đổi nhánh | Tab chưa lưu phải tự lưu thành bản sao hoặc đóng; không thể xác nhận từ Codex. File untracked chỉ được liệt kê, chưa được sao lưu |
| Manifest ảnh | Có bộ sinh `manifest_candidates.csv` đúng cột mà file tính chỉ số nhận | Workspace không truy cập được ổ E: nên chưa có manifest ảnh thật |
| Băng, CRS, kích thước pixel, NoData, scale/offset | Có công cụ đọc metadata tất cả raster và xuất `image_inventory.csv` | Chưa chạy trên ảnh thật ở máy demo |
| NoData/mask ngoài tỉnh | Có kiểm tra toàn bộ pixel của các ảnh mẫu, đếm riêng zero hợp lệ trong tỉnh và zero còn hợp lệ ngoài tỉnh | Chưa có kết quả ảnh thật; không coi pixel ngoài tỉnh điền 0 là đạt |
| Ảnh tháng đã lọc, ảnh năm tổng hợp pixel | Công cụ ghi bằng chứng FILTER; kiểm tra ảnh năm mẫu bằng trung vị từng pixel của các ảnh tháng tìm được, cùng lưới và đúng MONTHS_USED | FILTER chỉ là khai báo metadata, chưa thay thế việc kiểm chứng thuật toán lọc với ảnh thô. Ảnh thiếu bằng chứng không được mặc nhiên coi đã lọc |
| Chuẩn hóa 63 tỉnh | Đã xác minh đủ 63 mã thống kê trước sáp nhập, mã GADM và ánh xạ hai sheet GRDP; xử lý đúng `TP.Hồ Chí Minh` | Tên file ảnh không có mã tỉnh rõ ràng sẽ được đưa vào báo cáo lỗi, không fuzzy-match |
| Độ phủ tỉnh–năm, tỉnh kiểm chứng | Có bộ tạo 315 ô tỉnh–năm cho 2020–2024; nhóm mẫu đề xuất Hà Nội, Bắc Ninh, Lào Cai ở năm đầu/cuối | Chưa xác nhận độ phủ ảnh thật; nếu tỉnh mẫu thiếu ảnh phải chọn thay và ghi rõ |
| GRDP 2024 sơ bộ, điểm rà soát | Đã đọc Excel gốc và giữ nhãn sơ bộ 2024; tạo dữ liệu chuẩn hóa và bảng cờ kiểm tra | Các cờ rà soát chưa có căn cứ để tự sửa giá trị nguồn |

**Chưa đánh dấu toàn bộ A hoàn thành:** dữ liệu ảnh và IDE nằm trên máy Windows, không phải workspace Codex. Phần ảnh phải dựa vào báo cáo sau khi chạy trên `E:\SatelliteData`.

## 2. Chạy trên Antigravity / PowerShell

Trước khi cập nhật Git, lưu nội dung tab đang sửa thành bản sao nếu cần. Không lưu lại tab chứa nội dung cũ sau khi pull.

Trong terminal repo, lưu thay đổi tracked vào stash rồi cập nhật (không pop stash ngay sau khi pull):

```powershell
git stash push -m "Backup truoc khi chuan bi demo phan A"
git pull origin night-app
```

Stash giữ thay đổi tracked; các file untracked vẫn ở máy, không bị xóa. Nếu đang ở nhánh khác, xác nhận nhánh trước khi áp dụng cập nhật.

Sau khi đã cập nhật được nhánh `night-app`, chạy trong thư mục repo:

```powershell
python -m pip install -r backend/requirements.txt
python -m backend.data.prepare_demo --root "E:\SatelliteData"
```

Công cụ tự tìm đúng tên file Excel `GRDP Cấp Tỉnh_So sánh vs Hiện hành.xlsx` trong ổ dữ liệu. Nếu có nhiều bản hoặc đã đổi tên, chỉ định:

```powershell
python -m backend.data.prepare_demo --root "E:\SatelliteData" --grdp "E:\SatelliteData\GRDP Cấp Tỉnh_So sánh vs Hiện hành.xlsx"
```

- Dùng Python của môi trường sẽ chạy app; `environment.json` ghi đường dẫn Python thực tế.
- Không sửa ảnh, không tự pull/reset Git, không ghi đè kết quả tính hoặc database app.
- Mỗi lần chạy tạo thư mục riêng: `E:\SatelliteData\_demo_preparation\<thời điểm>\`.
- Công cụ đọc metadata tất cả raster; kiểm tra toàn bộ pixel của các ảnh mẫu thuộc mã `01`, `27`, `10`, trong năm đầu và cuối. Quá trình này có thể lâu với ảnh lớn.
- Chọn nhóm mẫu khác bằng `--sample-codes 01 27 60`; chọn khoảng năm bằng `--years 2020 2021 2022 2023 2024`.
- Có `BLOCKERS` hoặc mã thoát 2 nghĩa là đã xuất báo cáo nhưng còn mục chưa đạt; không có nghĩa đã hoàn thành A.

Nếu chưa có ranh giới gốc trên máy, chạy bước tải có sẵn rồi chạy lại phần A:

```powershell
python -m backend.data.build_boundaries --tai-gadm
```

Hoặc chỉ rõ hai file ranh giới gốc đã có:

```powershell
python -m backend.data.prepare_demo --root "E:\SatelliteData" --boundaries "DUONG_DAN\boundaries.geojson" --boundary-metadata "DUONG_DAN\boundaries.metadata.json"
```

Không dùng `backend/data/provinces.geojson` rút gọn cho web để tính diện tích/kiểm tra mask. Công cụ chỉ nhận bộ ranh giới GADM gốc vượt kiểm tra checksum và crosswalk.

## 3. Các file kết quả cần mở

| File | Dùng để làm gì |
|---|---|
| `preparation_report.json` | Kết luận tổng hợp, blocker và giới hạn của lần chạy |
| `environment.json` | Repo, nhánh, commit local/remote, Python, thư viện và phạm vi máy được kiểm tra |
| `git_backup/working_changes.patch` | Snapshot phần thay đổi tracked so với HEAD; lưu ngoài repo trước khi dùng để phục hồi |
| `git_backup/staged_changes.patch` | Snapshot phần đã stage |
| `git_backup/status.txt` | Danh sách thay đổi và untracked; file untracked không nằm trong patch |
| `province_catalog.csv` | 63 mã thống kê, tên tỉnh, mã GADM và slug |
| `province_areas.csv` | Diện tích tự nhiên từ ranh giới gốc, EPSG:6933, km² |
| `image_inventory.csv` | Mỗi raster một dòng: metadata, bằng chứng xử lý, kiểm tra pixel mẫu, lỗi và điểm chờ xác nhận |
| `image_errors.csv` | Ảnh không mở được hoặc chưa xác định được tỉnh/năm/nguồn |
| `manifest_candidates.csv` | Ứng viên đầu vào tính chỉ số; chưa tự coi là bộ dữ liệu đã kiểm chứng hoàn toàn |
| `coverage_province_year.csv` | Từng tỉnh–năm: số file có mặt, số ảnh năm/tháng đủ điều kiện metadata và trạng thái sẵn sàng |
| `grdp_all_prices.csv` | Cả hai loại giá, khóa tỉnh–năm–cơ sở giá, đơn vị và nguồn |
| `economy_so_sanh.csv` | Dữ liệu giá so sánh, tách riêng để bộ đọc hiện tại không gặp trùng tỉnh–năm |
| `economy_hien_hanh.csv` | Dữ liệu giá hiện hành, giữ riêng để đối chiếu |
| `grdp_checks.csv` | Thiếu dữ liệu, lệch tổng thành phần và tăng trưởng cần rà soát |

Chưa nạp `grdp_all_prices.csv` vào bộ đọc kinh tế hiện tại: bộ đọc này dùng khóa tỉnh–năm và cần sửa ở bước E để nhận đồng thời hai cơ sở giá. Các file tách riêng giúp bảo toàn dữ liệu trong giai đoạn chuẩn bị.

## 4. Kết quả GRDP đã kiểm tra trên file cô gửi

- 63 tỉnh × 10 năm (2015–2024) × 2 loại giá = **1.260 dòng**, **1.259 giá trị hợp lệ**, một ô thiếu.
- Đơn vị tỷ đồng; giá so sánh năm gốc 2010; nhãn năm 2024 là sơ bộ.
- Bắc Giang, hiện hành 2015: `N/a`, giữ trống.
- Thừa Thiên Huế, so sánh 2021: lệch 100 tỷ đồng giữa tổng và tổng bốn thành phần; chưa sửa.
- Có 13 cờ tăng trưởng theo tiêu chí rà soát `< -10%` hoặc `> 30%`; cờ này không tự khẳng định số liệu sai.
- Tổng cộng **15 cờ rà soát**: 1 ô thiếu + 1 lệch thành phần + 13 biến động tăng trưởng.
- Hà Nội, so sánh 2017 tăng khoảng 48,14%, 2018 giảm khoảng 13,46%; cần đối chiếu nguồn.
- Giữ giá trị và địa chỉ ô Excel nguồn; không nội suy, không ghi đè file gốc.

## 5. Cách xác nhận hoàn tất A sau lần chạy Windows

- [ ] `environment.json` đúng máy demo, repo và nhánh `night-app`; HEAD đã cập nhật.
- [ ] Bản sao sửa đổi cục bộ còn giữ được; các tab chưa lưu đã được xử lý.
- [ ] Ranh giới gốc có đủ 63 mã, checksum đạt; diện tích không lấy từ polygon web rút gọn.
- [ ] Metadata ảnh, scale/offset và các ảnh trùng đã được rà soát; không bỏ qua lỗi nhận dạng.
- [ ] Ảnh mẫu không có pixel ngoài tỉnh còn hợp lệ; zero hợp lệ trong tỉnh vẫn được giữ.
- [ ] Có bằng chứng nguồn cho bộ lọc tháng; ảnh năm mẫu đạt kiểm tra median từng pixel hoặc có giải trình cách tổng hợp khác.
- [ ] Manifest ứng viên đã được rà soát trước khi dùng làm manifest chính thức.
- [ ] Bảng độ phủ ảnh thật đủ cho khoảng năm demo đã chọn; đã xác nhận nhóm tỉnh kiểm chứng.
- [ ] Hai loại GRDP và nhãn sơ bộ/cờ rà soát được giữ nguyên.

Để đối chiếu lần chạy trên máy demo, gửi lại `preparation_report.json`, `image_errors.csv` và `coverage_province_year.csv`. Không cần gửi toàn bộ ảnh lớn ở bước đầu.
