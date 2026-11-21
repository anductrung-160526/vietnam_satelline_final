# PHẦN A — CHUẨN BỊ DỮ LIỆU VÀ MÔI TRƯỜNG

Ngày kiểm tra: 21/11/2026. Nhánh: `night-app`.

## 1. Kết luận từ báo cáo Windows mới nhất

Đã nhận báo cáo toàn kho ban đầu và lần kiểm tra riêng 150 ảnh mẫu trên Windows (HEAD `69dd233`, Python 3.12.6). Ảnh nguồn không bị sửa trong quá trình kiểm tra.

| Hạng mục | Kết quả đã xác minh | Giới hạn |
|---|---|---|
| Môi trường | Đúng repo, nhánh night-app, HEAD khớp remote tại thời điểm chạy; đủ thư viện | Tab chưa lưu trong IDE không thể kiểm tra từ Git |
| Sao lưu | Git status chỉ có province_pipeline/ untracked; có thư mục backup | Untracked chỉ được liệt kê, chưa sao lưu; không xóa thư mục này |
| Ranh giới | Đủ 63 tỉnh, checksum và crosswalk khớp | Ranh giới GADM nghiên cứu, không chứng nhận pháp lý |
| Metadata mẫu | EPSG:4326, NoData=-9999, scale=1, offset=0; băng ảnh đúng các bước xử lý | Chỉ nhóm mẫu được kiểm tra sâu từng pixel |
| Mask của 150 ảnh mẫu | Không có pixel hợp lệ nằm ngoài mặt nạ all_touched; các pixel có tâm ngoài đều giao mép tỉnh | Không suy rộng kiểm tra sâu này thành toàn bộ tỉnh/năm |
| 72 ảnh tháng đã lọc trong mẫu | Có FILTER đúng chuỗi dự kiến, không còn số âm, không có NaN/Inf còn unmasked | Chưa tính lại toàn bộ thuật toán lọc từ ảnh thô để đối chiếu |
| 6 ảnh năm mẫu | Cả 6 đạt PASS_PIXEL_MEDIAN_FOR_DISCOVERED_MONTHS | Đối chiếu các tháng tìm được, đúng MONTHS_USED; không tự chứng minh nguồn có đủ mọi tháng quan sát |
| GRDP | 1.260 dòng, 1.259 số hợp lệ, 2024 sơ bộ, 15 cờ rà soát | Chưa tự sửa điểm nghi ngờ |
| Manifest và độ phủ | Lần toàn kho cũ có 4.017 ứng viên và 309/315 mốc năm | Cần xuất lại manifest toàn kho theo quy tắc giao pixel đã xác minh; báo cáo SAMPLES_ONLY không thay thế độ phủ toàn kho |

### Sáu mốc đã được giải thích

Các con số sau giống nhau ở 2020 và 2024 của từng tỉnh:

| Tỉnh | Pixel hợp lệ mỗi ảnh năm | Pixel có tâm ngoài nhưng giao biên | Pixel ngoài mặt nạ all_touched | Kiểm tra median từng pixel |
|---|---|---|---|---|
| Hà Nội | 14.967 | 514 | 0 | Đạt cả 2 năm |
| Lào Cai | 28.271 | 637 | 0 | Đạt cả 2 năm |
| Bắc Ninh | 3.737 | 199 | 0 | Đạt cả 2 năm |

Đây là khác biệt giữa quy tắc lấy **tâm pixel trong tỉnh** và quy tắc **pixel giao với tỉnh**, không phải bằng chứng thiếu file hoặc hỏng ảnh.

### Quy tắc biên được ghi rõ trong bản công cụ cập nhật

- Giữ mask và giá trị ảnh gốc, nhận pixel giao biên theo quy tắc `intersecting_pixel`.
- Pixel có tâm ngoài nhưng thuộc mặt nạ all_touched: ghi `BOUNDARY_INTERSECTION_PIXELS_INCLUDED` trong cột warnings, không loại ảnh chỉ vì lý do này.
- Pixel hợp lệ nằm ngoài mặt nạ all_touched: vẫn bị chặn bởi `VALID_PIXELS_OUTSIDE_PROVINCE`.
- Không nới sai số theo một tỷ lệ tùy ý; vẫn xuất số lượng pixel của cả hai nhóm.
- Diện tích sáng đang cộng toàn bộ diện tích pixel giao biên, nên là một xấp xỉ có thể cao hơn diện tích phần giao thực. Một pixel có thể giao hai tỉnh; không khẳng định phép cộng tỉnh là diện tích hợp nhất toàn quốc chính xác.
- Chưa thay đổi công thức SOL, mật độ hoặc tự phân bổ pixel theo phần diện tích giao. Nếu đổi quy tắc tính chính thức, phải tính lại nhất quán các năm và cập nhật công thức.

Với hai báo cáo đã nhận, 78 ảnh đã xử lý của nhóm mẫu (72 tháng + 6 năm) đủ cơ sở gỡ chặn do tiêu chí tâm pixel cũ. Đây chưa phải số lượng manifest toàn kho đã được xuất mới.

### Phân loại các file ngoài phạm vi

15.973 dòng trong image_errors.csv ban đầu gồm: 15.742 ảnh ngày, 167 COG/preview, 34 tile toàn quốc, 22 mosaic toàn quốc và 8 file tạm/control. Bản mới chuyển chúng sang `excluded_images.csv`, không coi là lỗi ảnh tỉnh đêm. File ảnh đêm chưa nhận dạng hoặc không mở được vẫn vào `image_errors.csv`.

### Bước tiếp theo

Cập nhật code và chạy lại kiểm kê toàn kho theo mục 2 để xuất manifest/coverage mới. Không cần tải lại hoặc tính lại ảnh do vấn đề giao biên này. Có thể dự kiến thêm lại các ứng viên bị chặn cũ, nhưng chỉ báo đủ 315/315 sau khi kết quả toàn kho mới xác nhận.

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
- [x] 150 ảnh mẫu không có pixel hợp lệ ngoài mặt nạ all_touched; pixel giao biên được ghi cảnh báo, không tự xóa. Zero hợp lệ trong tỉnh vẫn được giữ.
- [ ] Bộ lọc tháng có metadata và 72 ảnh lọc mẫu không còn số âm; 6 ảnh năm đã đạt median từng pixel. Chưa kiểm chứng lại toàn bộ bước lọc từ ảnh thô.
- [ ] Manifest ứng viên đã được rà soát trước khi dùng làm manifest chính thức.
- [ ] Bảng độ phủ ảnh thật đủ cho khoảng năm demo đã chọn; đã xác nhận nhóm tỉnh kiểm chứng.
- [ ] Hai loại GRDP và nhãn sơ bộ/cờ rà soát được giữ nguyên.

Để đối chiếu lần chạy trên máy demo, gửi lại `preparation_report.json`, `image_errors.csv` và `coverage_province_year.csv`. Không cần gửi toàn bộ ảnh lớn ở bước đầu.
