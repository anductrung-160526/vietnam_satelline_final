# PHẦN A — CHUẨN BỊ DỮ LIỆU VÀ MÔI TRƯỜNG

Ngày kiểm tra: 21/11/2026. Nhánh: `night-app`.

## 1. Kết quả từ lần chạy Windows đã nhận

Đã nhận `preparation_report.json`, `coverage_province_year.csv`, `image_errors.csv` của lần chạy 21/11/2026. Đã nhận tiếp `image_inventory.csv` và xác định vấn đề mask ở các mốc mẫu; còn chờ kiểm tra hai quy tắc biên pixel.

| Mục trong kế hoạch A | Bằng chứng hiện có | Kết luận |
|---|---|---|
| Repo, nhánh, Python | Windows 10, Python 3.12.6, nhánh night-app; HEAD f7e5b18 khớp remote tại thời điểm chạy; đủ thư viện | Đã xác minh môi trường máy demo cho phiên bản đó; cần pull bản sửa công cụ mới |
| Sao lưu, tab cũ | Có đường dẫn git_backup; Git status không có tracked changes, còn province_pipeline/ untracked | Không có tracked changes cần sao lưu tại thời điểm chạy; không xác nhận được tab chưa lưu, thư mục untracked chưa sao lưu |
| Ranh giới/mã tỉnh | Đủ 63 tỉnh, SHA-256 khớp bộ GADM gốc | Đã xác minh checksum và ánh xạ mã; không phải chứng nhận pháp lý ranh giới |
| Manifest | 4.017 ứng viên trong 2020–2024 | Chưa đủ điều kiện chốt manifest chính thức |
| Metadata và pixel ảnh | 37.715 raster đã được quét trong bản cũ; 150 raster được kiểm tra pixel mẫu | Bản quét gồm cả ảnh ngày/file ngoài phạm vi; cần đọc chi tiết mẫu chưa đạt |
| Ảnh tháng đã lọc | Có các ứng viên vượt kiểm tra khai báo metadata | Chưa kiểm chứng lại toàn bộ thuật toán lọc từ ảnh thô |
| Ảnh năm tổng hợp pixel | annual_pixel_checks rỗng | Chưa có bằng chứng kiểm tra median ảnh năm trong lần chạy này |
| Độ phủ | 309/315 tỉnh–năm có ứng viên ảnh năm | Thiếu điều kiện chấp nhận ở 6 mốc; đây không phải xác nhận thiếu file vật lý |
| GRDP | 1.260 dòng, 1.259 số hợp lệ, 2024 sơ bộ, 15 cờ rà soát | Đã chuẩn hóa và đánh dấu, chưa tự sửa số nguồn |

### Sáu mốc cần xem thêm chi tiết

| Mã tỉnh | Tỉnh | Năm | Số file được ghi nhận | Ứng viên ảnh năm | Ứng viên ảnh tháng |
|---|---|---|---|---|---|
| 01 | Hà Nội | 2020 | 25 | 0 | 0 |
| 01 | Hà Nội | 2024 | 25 | 0 | 0 |
| 10 | Lào Cai | 2020 | 25 | 0 | 0 |
| 10 | Lào Cai | 2024 | 25 | 0 | 0 |
| 27 | Bắc Ninh | 2020 | 25 | 0 | 0 |
| 27 | Bắc Ninh | 2024 | 25 | 0 | 0 |

Các mốc trên trùng đúng nhóm tỉnh/năm được kiểm tra pixel sâu. Cần xem cột `issues`, `pixel_audit` và `annual_pixel_check` trước khi kết luận ảnh hỏng, thiếu ảnh hoặc cần tính lại. Không bỏ kiểm tra để làm đẹp độ phủ.

### Chẩn đoán từ image_inventory.csv đã nhận

Đã xác định 6 ảnh năm đều là float32, EPSG:4326, NoData=-9999, scale=1, offset=0 và khai báo `MEDIAN_OF_FILTERED_VIIRS_MONTHS`. Cả 6 bị chặn bởi `VALID_PIXELS_OUTSIDE_PROVINCE` theo quy tắc tâm pixel.

| Tỉnh | Năm | Pixel hợp lệ | Pixel có tâm ngoài tỉnh | Tỷ lệ |
|---|---|---|---|---|
| Hà Nội | 2020 và 2024 (mỗi năm) | 14.967 | 514 | 3,43% |
| Lào Cai | 2020 và 2024 (mỗi năm) | 28.271 | 637 | 2,25% |
| Bắc Ninh | 2020 và 2024 (mỗi năm) | 3.737 | 199 | 5,33% |

72 ảnh tháng đã lọc của nhóm mẫu có khai báo FILTER đúng chuỗi xử lý dự kiến; không còn giá trị âm trong các ảnh này. Ảnh thô hai băng chưa lọc không có tag FILTER là điều có thể xảy ra; không đồng nhất chúng với ảnh đã lọc bị hỏng.

Các con số lặp lại giữa hai năm gợi ý cần kiểm tra quy tắc raster hóa ranh giới. Chưa có tọa độ pixel trong CSV nên chưa thể khẳng định chúng chỉ là pixel giao mép hay thực sự nằm hoàn toàn ngoài tỉnh. Không nới điều kiện để tự đưa các ảnh đó vào manifest.

Bản công cụ mới kiểm tra riêng hai nhóm: `boundary_fringe_valid_pixels` (tâm ngoài nhưng pixel giao tỉnh) và `outside_touched_valid_pixels` (nằm ngoài mặt nạ all_touched). Đồng thời kiểm tra phép tổng hợp năm độc lập với lỗi mask, để không bỏ qua chẩn đoán ảnh năm.

Chạy lại riêng 150 ảnh mẫu từ inventory cũ, không quét lại toàn bộ ổ:

```powershell
python -m backend.data.prepare_demo --root "E:\SatelliteData" --review-inventory "E:\SatelliteData\_demo_preparation\20261121_184926_606622\image_inventory.csv"
```

Lần chạy này có scope `SAMPLES_ONLY`, không được dùng để kết luận độ phủ toàn quốc. Gửi lại `sample_image_checks.csv` và `preparation_report.json` trong thư mục kết quả mới. Công cụ chỉ đọc ảnh, không sửa mask hoặc giá trị nguồn.

### Sửa phân loại lỗi của công cụ

15.973 dòng trong image_errors.csv của bản cũ đều thuộc ngoài phạm vi ảnh tỉnh ban đêm:

| Loại | Số file |
|---|---|
| Ảnh ngày | 15.742 |
| COG hiển thị/preview | 167 |
| Tile ảnh toàn quốc | 34 |
| Mosaic toàn quốc | 22 |
| File tạm/control | 8 |

Bản sửa đưa các file này vào `excluded_images.csv`, không báo như lỗi ảnh tỉnh ban đêm. File ảnh đêm chưa nhận dạng hoặc không mở được vẫn vào `image_errors.csv`. Một số TIFF ảnh ngày có lỗi đọc thật trong báo cáo cũ, nhưng không thuộc dữ liệu demo kinh tế đêm cần xử lý ở bước này.

**Phần A chưa hoàn tất:** còn phân biệt pixel giao biên/ngoài tỉnh ở 6 mốc, xác nhận ảnh năm và chốt bộ ảnh chính thức. Trước mắt gửi `sample_image_checks.csv` từ bản mới hoặc lọc nhóm mẫu từ image_inventory.csv cũ, chưa cần gửi ảnh lớn.

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
| `image_errors.csv` | Ảnh tỉnh đêm không mở được hoặc chưa xác định được tỉnh/năm/nguồn |
| `excluded_images.csv` | Ảnh ngày, file tạm, COG, tile/mosaic toàn quốc nằm ngoài phạm vi; không xóa file nguồn |
| `sample_image_checks.csv` | Báo cáo gọn metadata và kiểm tra pixel ở các mốc mẫu |
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
