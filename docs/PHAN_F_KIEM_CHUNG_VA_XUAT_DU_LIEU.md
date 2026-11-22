# Phần F — kiểm chứng ảnh, CSV, SQLite, API và file xuất

Phần F bổ sung truy nguồn và kiểm chứng cho bộ v9 đã chạy thành công trên Windows. Không chạy lại bước sửa raw/filtered hay thay CSV kết quả D/E. Chương trình có đọc ảnh và tính lại thống kê, phân lớp/diện tích và mô hình để đối chiếu; vì vậy vẫn cần thời gian quét file.

## 1. Những thay đổi đã thực hiện

| Nội dung | Cách thực hiện |
|---|---|
| Tên trường | Kiểm tra trường CSV chuẩn và ánh xạ API đều có trong Dictionary; xuất field_contract.csv |
| CSV → SQLite | Đối chiếu từng dòng/từng cột nhập, cả hai giá; kiểm lớp, tỷ lệ và báo cáo diện tích |
| Ảnh → CSV | Tính lại SOL, sol_raw, số pixel, thống kê bức xạ, diện tích sáng và diện tích hợp lệ từ ảnh nguồn để đối chiếu |
| COG lớp → nguồn | Kiểm tra mã lớp, mask, ngưỡng và diện tích từ ảnh bức xạ hiện tại, không chỉ tin tag TIFF |
| Mô hình | Đối chiếu số cặp chung, α/β/R²/n, thời kỳ và GRDP ước lượng với các CSV đã xuất |
| Phiên bản | dataset_manifest.json có SHA-256/số dòng từng CSV, STATS_VERSION và dataset_id theo nội dung |
| Schema | DEMO_SCHEMA_VERSION=2, migration cộng thêm; base schema.sql vẫn v8, không reset bảng chỉ số hoặc sổ COG |
| GeoTIFF xuất | Kiểm từng băng theo phần giao pixel–tỉnh; tạo bản crop/mask riêng nếu có dữ liệu hoàn toàn ngoài tỉnh |
| Nguồn mất/đổi | API kiểm file thực tế và chữ ký size/mtime; không báo ảnh sẵn có khi nguồn/bản xuất đã mất hoặc đổi |
| Đồng bộ khi cập nhật | API đọc một snapshot; có header X-Snapshot-ID, frontend yêu cầu tải lại nếu bộ dữ liệu đổi giữa các lần đọc |
| Tải đúng phiên bản | Link CSV/TIFF mang expected_snapshot; backend trả 409 nếu khác snapshot đang hiển thị |

Các ảnh nguồn, CSV khoa học và bảng dữ liệu nền được giữ nguyên. Metadata mới, bản xuất mask và database candidate được ghi riêng. Chỉ --publish mới sao lưu và cập nhật database app sau khi kiểm chứng hoàn tất.

## 2. Lệnh chạy trên máy demo

Dừng uvicorn đang chạy trước khi xuất bản, rồi:

```powershell
git pull origin night-app
python -m backend.data.verify_demo --root "E:\SatelliteData" --fix-report "E:\SatelliteData\_demo_fix\20261122_180611_662323\fix_report.json" --publish
```

Lệnh dùng đúng thư mục kết quả v9 đã xác nhận, không cần chạy lại fix_demo_data. Nếu đã chuyển kho dữ liệu, chỉnh đường dẫn theo vị trí thật. Nếu ranh giới không ở vị trí mặc định của phần A, thêm --boundaries và --boundary-metadata đúng bản gốc đã kiểm SHA, không dùng GeoJSON web rút gọn.

Chương trình thực hiện:

1. Kiểm phiên bản trong CSV so với fix_report, tạo metadata snapshot nếu bộ v9 cũ chưa có.
2. Clone database app, áp migration cộng thêm trên candidate.db; không gọi cơ chế reset schema.
3. Đối chiếu CSV/SQLite và hợp đồng tên trường; kiểm mô hình/ước lượng.
4. Kiểm tất cả ảnh đã đăng ký tại các mốc trong manifest: raw, processed, classes, support. Báo tiến độ mỗi 100 ảnh; nguồn cùng chữ ký/geometry đã kiểm ở lượt F trước có thể dùng cache.
5. Đọc lại và kiểm bản xuất sau mask; bảo đảm ngoài tỉnh không còn pixel hợp lệ theo quy tắc bên dưới.
6. Kiểm SQLite, kiểm file/CSV không thay đổi giữa lượt chạy; backup và xuất bản candidate khi tất cả đều đạt.

Nếu thất bại, dừng để xem thông báo; database app không bị thay bằng candidate chưa đạt. CSV đã chỉnh sửa nhưng khác dataset_manifest sẽ bị từ chối; không sửa metadata/hash để che sai lệch. Nếu ảnh nguồn khác số trong CSV, cần tính lại đúng D/E từ nguồn đó, không chỉ nạp lại CSV cũ. Các bộ kết quả ngoài mốc manifest không được tự gán mã snapshot mới.

Kết thúc thành công, mở lại app và tải lại trang:

```powershell
python -m uvicorn backend.api.main:app --reload --port 8000
```

## 3. Quy tắc mask GeoTIFF

Dùng ranh giới GADM gốc cùng phần D v3. Pixel hoàn toàn không giao tỉnh phải là NoData ở mọi băng; pixel có phần giao diện tích dương được giữ. Pixel cắt biên vẫn là ô raster đầy đủ khi hiển thị, còn diện tích thống kê chỉ cộng phần giao EPSG:6933. Không kiểm bằng điều kiện “tâm pixel phải nằm trong tỉnh”, vì điều kiện đó sẽ bỏ pixel giao biên hợp lệ.

Ảnh tải được crop về cửa sổ bao các pixel giao tỉnh, giữ CRS, vị trí địa lý, tên băng, scale/offset, NoData và giá trị 0 hợp lệ. cf_cvg=0 trong tỉnh vẫn giữ 0 ở ảnh Raw, không biến thành NoData chỉ để làm đầy quan sát. Khi nguồn đã mask/crop phù hợp, dùng nguyên file; khi cần sửa mask xuất, tạo COG riêng, giữ file nguồn và SHA riêng.

Bản xuất nằm ở _demo_verify/<lượt chạy>/exports nếu cần. Demo_asset.path vẫn tham chiếu nguồn khoa học; demo_asset_check ghi source/export, hash và kết quả kiểm tra. API bản đồ và tải dùng export_path đã kiểm, không sửa nguồn đầu vào của phép tính D/E.

## 4. Metadata và xuất dữ liệu trên app

- Bảng chỉ số có dataset_id rút gọn, stats_version, thông báo nguồn chưa sẵn có/khác phiên bản và nút tải CSV chỉ số đúng tỉnh–năm–tháng.
- CSV chỉ số dạng dài: một field mỗi dòng, Raw trước Processed, giữ 0 và ô thiếu riêng; có đơn vị, light_basis, area_method, cơ sở giá, source_image_path/hash và cờ provenance_consistent.
- CSV kinh tế giữ cả GRDP so sánh/hiện hành, đơn vị tiền tệ, sol_unit, derived_price_basis, nguồn/sơ bộ/cờ chất lượng, mô hình offline/thời kỳ/n, dataset_id và stats_version.
- CSV lớp có cận ngưỡng, đơn vị, diện tích/tỷ lệ/mẫu số, phiên bản phân lớp và xuất xứ ảnh.
- GeoTIFF có header X-Snapshot-ID, X-Source-SHA256 và quy tắc mask; JSON asset có hash bản xuất riêng nếu bản mask khác file nguồn.
- /api/demo/dataset liệt kê snapshot, phiên bản schema và tình trạng file CSV; chưa có metadata được ghi là chưa xác minh, không tự nhận đã kiểm F.

Các ánh xạ giữ ý nghĩa: total_pixels ↔ valid_pixels, mean_rad ↔ rad_mean…; tnl chỉ bằng sol_raw cùng đầu vào. Không gộp tnl_ma3/tnl_mom_growth_pct với cửa sổ tháng lịch của SOL. sol_cal và chỉ số đầu người dùng thang VIIRS, không gán đơn vị DN cho kết quả đã hiệu chỉnh. Mật độ/tăng trưởng lấy đúng chuỗi ghi ở light_basis khi CSV có hiệu chỉnh.

avg_rad/cf_cvg trong CSV tính lại là tham chiếu băng đầu vào đã lọc; Raw trên app lấy ảnh raw hai băng đã đăng ký. Hai tham chiếu có giai đoạn xử lý khác nhau và được ghi rõ trong field_contract.csv; không tuyên bố hai đường dẫn là cùng một file. Các chỉ số số học được đối chiếu từ nguồn tính tương ứng.

Mô hình offline khớp 315 cặp 2020–2024; biểu đồ app có thể khớp lại theo bộ lọc năm/tỉnh hiện tại. Cùng snapshot dữ liệu không đồng nghĩa cùng phạm vi ước lượng; metadata thời kỳ/n và nhãn giá vẫn phải đi cùng hệ số. Phần F xác nhận tính nhất quán phần mềm/số học, không thay thế đánh giá kinh tế, nhân quả hoặc ranh giới pháp lý.

## 5. File kết quả cần gửi lại

Thư mục: E:\SatelliteData\_demo_verify\<lượt chạy>\.

| File | Ý nghĩa |
|---|---|
| integration_report.json | Mã snapshot, phiên bản, số dòng/bộ ảnh đã kiểm, số bản mask, ngoài tỉnh còn hợp lệ hay không, mô hình, published và backup |
| field_contract.csv | Tên trường chuẩn và ánh xạ CSV/SQLite/API cùng lưu ý ý nghĩa |
| candidate.db | Database đã chuẩn bị; chỉ cập nhật app khi --publish |
| exports/ | Bản crop/mask riêng khi cần, không thay file gốc |

Metadata dataset_manifest.json được bổ sung trong thư mục indices v9, không thay nội dung các CSV. Cache API dùng tồn tại/size/mtime để phát hiện file đổi nhanh; SHA được ghi khi kiểm chứng offline, không băm toàn bộ TIFF ở mỗi HTTP request. Không xóa/chuyển thư mục nguồn/CSV/exports sau khi xuất bản; nếu cần di chuyển, đăng ký và kiểm chứng lại vị trí mới.

Gửi **integration_report.json** sau khi chạy thành công. Kiểm các mục: published=true, stats_version=9, demo_schema_version=2, outside_valid_values_after=0. masked_export_copies là số ảnh dùng bản xuất riêng, không nhất thiết số file mới tạo trong lượt chạy nếu có cache.

## 6. Kiểm tra Windows trước demo

- Chọn Hà Nội/Bắc Ninh, đổi năm/tháng; đối chiếu cùng SOL và mốc trên bản đồ/thẻ số/bảng/CSV.
- Chọn 2022-07 ở tỉnh không có quan sát để thấy thiếu số, không phải SOL=0.
- Tải CSV chỉ số, CSV kinh tế hai giá, CSV lớp và TIFF; đối chiếu mã snapshot, đơn vị, source hash và mốc.
- Mở TIFF bằng QGIS: CRS/vị trí đúng, ngoài footprint giao tỉnh là NoData, pixel 0 hợp lệ vẫn còn.
- Với file nguồn thử nghiệm riêng, đổi tên rồi đổi mốc trên app: ảnh không báo sẵn có, nút tải tắt hoặc endpoint 410. Trả lại vị trí file để tiếp tục; không dùng thử nghiệm này trên file gốc đang phục vụ demo.
- Nếu cập nhật database giữa lúc trang đang mở, app yêu cầu tải lại và các link tải snapshot cũ trả 409; không ghép dữ liệu hai lượt vào một màn.

Đã kiểm tra bằng dữ liệu biết trước và trình duyệt; nghiệm thu kho Windows cần integration_report.json cùng kiểm tra màn hình thực tế. Không cần chạy lại bước sửa diện tích/tháng thiếu chỉ để kiểm phần F.
