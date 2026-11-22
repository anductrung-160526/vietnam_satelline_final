# Sửa diện tích giao biên và kiểm tra/phục hồi ảnh tháng

**Đã nhận kết quả Windows ngày 22/11:** published=true, độ phủ vượt 100% đã về 0; 57 tháng thiếu thuộc loại raw không có quan sát sạch mây hợp lệ, không có ảnh bị lỗi FILTER cần sửa. Chi tiết: [KET_QUA_SAU_SUA_V9.md](KET_QUA_SAU_SUA_V9.md). Không cần chạy lại toàn workflow chỉ để tạo lại báo cáo này.

Bản cập nhật STATS_VERSION=9; phân lớp `viirs_brightness_classes_v3_fractional`. Đây là cách chạy mới sau khi đã nhận kết quả D v2 có tỷ lệ vượt 100% và 57 ảnh tháng rỗng. Các báo cáo cũ được giữ làm bằng chứng trước sửa, không sửa tay số liệu hoặc cắt tỷ lệ về 100%.

## 1. Diện tích đã sửa như thế nào

Với pixel i và tỉnh P: **a_i = area(pixel_i ∩ P trong EPSG:6933) / 10⁶**. Dùng đúng ranh giới GADM gốc đã kiểm SHA-256 và crosswalk như phần A; mẫu số cũng là area(P) trong EPSG:6933. Xử lý được pixel giao biên, lỗ polygon, đảo và phần raster nằm ngoài tỉnh.

Lưới đầu vào phải north-up EPSG:4326 hoặc EPSG:6933. Với EPSG:4326, hai trục được chiếu sang EPSG:6933; pixel thành hình chữ nhật trên lưới diện tích. Không tự dùng cách này cho CRS khác hoặc raster xoay. Tính tổng phần giao từng lớp trên pixel có dữ liệu; NoData không có diện tích quan sát. Tổng diện tích lớp phải khớp diện tích có dữ liệu trong tỉnh và không vượt polygon. Tỷ lệ làm tròn 8 chữ số thập phân để xử lý sai số số thực rất nhỏ; sai lệch thực vượt polygon làm dừng.

Trọng số diện tích được cache theo geometry, CRS, transform, kích thước và phiên bản, không theo mask ảnh; dùng lại khi các tháng/năm cùng lưới. COG phân lớp cũ được dùng lại nếu đúng nguồn, ngưỡng và năm tham chiếu; diện tích được tính lại từ phần giao, không tin diện tích cũ. Raster hiển thị vẫn gồm ô pixel đầy đủ; không được diễn giải diện tích màu trên màn hình như phép đo polygon chính xác.

**SOL vẫn là tổng giá trị bức xạ pixel**, không nhân trọng số diện tích. Đây là hợp đồng chỉ số ánh sáng hiện tại, không phải công suất vật lý. Pixel chỉ chạm đường biên nhưng phần giao có diện tích 0 bị loại khỏi tập quan sát. Mật độ vẫn SOL/diện tích tự nhiên. Không nhầm sửa diện tích với thay công thức tổng sáng thành tích phân bức xạ.

## 2. Các tháng thiếu được xử lý thế nào

Kiểm tra ảnh raw hai băng avg_rad/cf_cvg đã đăng ký trong SQLite. Chỉ tự sửa khi lưới/scale/băng và tag FILTER phù hợp quy tắc đã thấy trong ảnh thật:

`cf_cvg=0->NoData; negative->0; value>max(3*annual median, median+5)->annual median`

Cho từng pixel, tháng có quan sát khi bức xạ và cf_cvg hợp lệ, cf_cvg>0. Đưa bức xạ âm về 0. Tính trung vị năm từ 12 tháng raw sau quy tắc quan sát này; giá trị tháng vượt max(3×trung vị, trung vị+5) đưa về trung vị. Đối chiếu mask và giá trị với ảnh filtered đang có.

- Nếu ảnh lọc làm mất quan sát hợp lệ, giữ sai quan sát hoặc tính sai giá trị: xuất ảnh filtered sửa vào thư mục mới, ghi CF_CVG_MEAN và nguồn raw.
- Nếu cf_cvg có dữ liệu hợp lệ nhưng bằng 0: giữ NoData, ghi NO_CLOUD_FREE_OBSERVATIONS. Không nội suy hoặc biến thành vùng tối.
- Nếu băng cf_cvg không có dữ liệu hợp lệ: MISSING_CF_COVERAGE, không khẳng định có/không có quan sát chỉ từ số 0 đếm được.
- Nếu cf_cvg dương nhưng bức xạ không hợp lệ: NO_VALID_RADIANCE_DESPITE_CF; chưa thể khôi phục từ file này.
- Thiếu một trong 12 ảnh raw/filtered, khác lưới, scale khác hoặc FILTER chưa xác minh: ghi lý do cần rà soát, không tự resample/đoán quy tắc.

Khi có sửa tháng hoặc phát hiện ảnh năm không khớp, tạo ảnh năm mới bằng median tại từng pixel; không lấy trung vị các tổng SOL. Ảnh gốc/filtered cũ và raw không bị ghi đè. Luôn tạo bản đồ số tháng có quan sát **valid_month_count** (0–12 trong tỉnh, 255 ngoài tỉnh). Báo cáo năm có min/max/trung bình trên pixel có ít nhất một quan sát, diện tích không có quan sát và diện tích chỉ có một tháng; không tự chọn ngưỡng 6/9/12 tháng để loại số liệu.

Các chẩn đoán theo tháng và thông tin số tháng hợp lệ xuất hiện trên màn Chỉ số đêm sau khi nạp; có liên kết tải bản đồ đếm tháng. Quan sát thật sự thiếu cần nguồn dữ liệu hợp lệ bổ sung nếu muốn lấp; code không thể tạo lại tín hiệu không được đo.

## 3. Chạy một lệnh trên máy Windows

Dừng uvicorn đang chạy, cập nhật code:

```powershell
git pull origin night-app
```

Sau đó chạy:

```powershell
python -m backend.data.fix_demo_data --root "E:\SatelliteData" --prepared "E:\SatelliteData\_demo_preparation\20261121_224811_221282" --method-file "E:\SatelliteData\cog\light_classes\20261121_235905_739916\method.json" --publish
```

Các đường dẫn lấy từ báo cáo thật đã gửi. `--method-file` giữ bốn mốc 0,5; 1,5; 3,0850000381469727; 17,459999084472656 của snapshot tham chiếu 2020 đã chọn, để so sánh trước/sau sửa trên cùng bộ chia. Không khẳng định hai phân vị này đã được fit lại từ ảnh 2020 sau sửa; method mới ghi preserved_reference_snapshot. Nếu sau này chốt lại mẫu tham chiếu thì cần chạy một phiên bản ngưỡng mới riêng.

Lệnh thực hiện lần lượt:

1. Đối chiếu 12 tháng raw/filtered từng tỉnh–năm; tạo ảnh sửa và báo cáo.
2. Clone database app sang candidate.db; đăng ký manifest mới ở bản tạm.
3. Tính/kiểm chứng diện tích giao pixel–tỉnh, dùng lại COG phù hợp và xuất báo cáo D v3.
4. Tính lại D/E với STATS_VERSION=9, hai cơ sở giá GRDP và cờ chất lượng; nạp vào bản tạm, kiểm tra SQLite.
5. Chỉ sau khi toàn chuỗi hoàn tất: backup database gốc và xuất bản snapshot mới bằng SQLite backup. Thiếu --publish thì chỉ chuẩn bị kết quả, app chưa đổi.

Giữ cả thư mục kết quả và backup; không xóa ảnh nguồn. Nếu một bước tính/kiểm chứng thất bại trước bước xuất bản, database app giữ nguyên. Các năm không đủ nguyên liệu để sửa được ghi chẩn đoán và giữ ảnh hiện có; cần đọc báo cáo để biết còn thiếu quan sát nào. Không coi việc lệnh hoàn tất là mọi tháng đã có dữ liệu.

Thư viện cần thiết đã có trong backend/requirements.txt. Ranh giới phải là bản gốc đã xác minh, không dùng provinces.geojson rút gọn của web. Nếu hai file ranh giới không ở vị trí mặc định, thêm --boundaries và --boundary-metadata đúng như phần A. Cache diện tích và kết quả mới trên ổ E cần thêm dung lượng; chương trình in tiến độ theo tỉnh/năm và mỗi 100 ảnh tính chỉ số.

## 4. File kết quả và cách kiểm tra

Thư mục chính: `E:\SatelliteData\_demo_fix\<lượt chạy>\`.

| File/thư mục | Nội dung |
|---|---|
| fix_report.json | Tóm tắt chẩn đoán/sửa, diện tích, số dòng E, published, vị trí backup và báo cáo D v3 |
| repair/monthly_recovery_audit.csv | Raw/filtered từng tháng: số quan sát, pixel bị mất, mask/thống kê sai, chẩn đoán và đã sửa hay chưa |
| repair/annual_observation_support.csv | Mức đầy đủ quan sát tại từng tỉnh–năm, nguồn bản đồ đếm tháng |
| repair/*valid_month_count.tif | Bản đồ 0–12 tháng hợp lệ, NoData=255 ngoài tỉnh |
| repair/manifest_repaired.csv | Toàn bộ danh sách ảnh mới/cũ được chọn, không sửa manifest phần A |
| repair/*repaired.tif | Ảnh tháng/năm cần sửa, còn ảnh không đổi vẫn tham chiếu vị trí cũ |
| indices/ | CSV D/E, hai giá và mô hình được tính lại với diện tích giao biên |
| candidate.db | Snapshot đã chuẩn bị; --publish mới cập nhật database app |

Báo cáo D v3 nằm ở thư mục mới trong `cog/light_classes`; đường dẫn cụ thể có trong fix_report.json. Cần kiểm tra coverage_above_100=0, sai lệch tổng diện tích nhỏ và method_version=v3_fractional; đối chiếu bản đồ vài tỉnh với polygon. Cờ v2/whole_pixel không được coi là kết quả đã sửa.

Đã nhận **fix_report.json**: 0 ảnh tháng/năm cần sửa pixel, 57 tháng raw không có quan sát sạch mây hợp lệ; không coi đây là lỗi lọc còn chưa sửa. Cần đọc tiếp **repair/monthly_recovery_audit.csv**, **repair/annual_observation_support.csv**, **indices/calculation_models.csv** và vài dòng kết quả để kiểm tra chi tiết chất lượng năm/hệ số mô hình. Báo cáo tổng đã xác nhận workflow chạy và cập nhật app thành công.

## 5. Kiểm tra đã thực hiện ở môi trường phát triển

- Pixel giao biên nửa ô, polygon có lỗ, vùng hoàn toàn ngoài tỉnh và NoData.
- EPSG:4326 → EPSG:6933, cache thay đổi theo lưới/geometry, diện tích tỷ lệ ≤100%.
- Lưới 15 arc-second phủ kín 63 ranh giới GADM đã xác minh: tổng phần giao khớp polygon; sai số tương đối lớn nhất 3,66×10⁻¹⁵. Đây là kiểm chứng hình học, không phải chạy lại 4.095 ảnh thật.
- Raw còn quan sát nhưng filtered mất mask: phục hồi theo quy tắc cả spike; raw cf=0 và cả năm thiếu thật giữ thiếu.
- Đếm tháng hợp lệ, tái tạo ảnh năm, giữ byte file nguồn và xuất bản SQLite/API.
- Cố tình gây lỗi trước xuất bản: database gốc giữ nguyên.
