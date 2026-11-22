# Phần D — phân lớp sáng, diện tích và kiểm chứng

**Cập nhật v9:** để sửa diện tích vượt 100% và kiểm tra/phục hồi tháng thiếu, dùng [SUA_DIEN_TICH_VA_THANG_THIEU.md](SUA_DIEN_TICH_VA_THANG_THIEU.md). Các lệnh/giới hạn v2/v8 dưới đây mô tả phiên bản trước sửa.

Phạm vi: VIIRS 2020–2024, cấp 63 tỉnh trước sáp nhập. Bộ phân lớp không dùng học máy. Code, CSV, API và tài liệu đã được kiểm tra trên ảnh biết trước; chưa coi là đã nghiệm thu toàn bộ ảnh thật trên máy Windows.

## 1. Đầu ra đã bổ sung

Trong thư mục của lượt phân lớp `<root>/cog/light_classes/<lượt chạy>/`:

| File | Nội dung |
|---|---|
| `*_classes.tif` | COG một băng uint8: mã lớp 0–4, NoData=255; không sửa raster bức xạ nguồn |
| `method.json` | Bốn ngưỡng thực tế, năm tham chiếu và căn cứ phương pháp; giữ nguyên khi tiếp tục lượt cũ |
| `light_class_areas.csv` | Năm dòng mỗi tỉnh–năm–tháng, diện tích và % diện tích tự nhiên, cận ngưỡng, đơn vị, phiên bản |
| `light_class_validation.csv` | Một dòng mỗi ảnh: diện tích tỉnh, nguồn mẫu số, số pixel hợp lệ/NoData, diện tích có dữ liệu, độ phủ, diện tích sáng, sai lệch tổng lớp, trạng thái, đường dẫn ảnh |
| `validation_report.json` | Tổng số ảnh kiểm tra, ảnh dùng lại, ảnh rỗng, ảnh thiếu mẫu số, ảnh có độ phủ trên 100%, sai lệch lớn nhất và danh sách phép kiểm tra |

CSV dùng UTF-8 BOM để Excel Windows đọc tiếng Việt. Các file báo cáo được ghi sau khi tất cả ảnh đã qua kiểm tra; SQLite chỉ cập nhật dữ liệu lớp/summary trong một transaction sau đó, có backup trước cập nhật. Nếu lỗi ghi file hoặc database, đọc thông báo cuối; có file báo cáo không đồng nghĩa đã nạp SQLite thành công. Lượt chạy lại có thể thay các CSV/JSON kiểm chứng trong cùng thư mục, không sửa method.json cũ hoặc raster phân lớp đã dùng lại.

SQLite giữ bảng `light_class` cũ và thêm `light_class_summary`; tỷ lệ năm lớp lưu JSON tại `class_area_pcts`. API chỉ đọc kết quả đã lưu, không xử lý raster theo yêu cầu HTTP.

## 2. Ngưỡng và quy tắc phân lớp

| Mã | Tên | Khoảng nW/cm²/sr |
|---|---|---|
| 0 | Tối / dưới ngưỡng nền | 0 ≤ r < 0,5 |
| 1 | Sáng yếu | 0,5 ≤ r < 1,5 |
| 2 | Sáng vừa | 1,5 ≤ r < q50 |
| 3 | Sáng mạnh | q50 ≤ r < q90 |
| 4 | Rất sáng | r ≥ q90 |

0,5 là ngưỡng nền hiện có của dự án; 1,5 theo Task 3. q50/q90 tính một lần bằng phân vị tuyến tính trên toàn bộ pixel sáng hợp lệ r≥1,5 của 63 ảnh năm VIIRS 2020. Lấy theo số pixel, chưa có trọng số diện tích; pixel giao biên có thể lặp giữa tỉnh. Dùng cố định qua các năm/tháng, không chia theo max từng ảnh. Đây là phân loại bức xạ thực nghiệm; không khẳng định năm lớp tương ứng trực tiếp với mức kinh tế, loại đất hoặc mức sống.

Bằng ngưỡng thuộc lớp cao hơn; NoData không thuộc lớp 0. Giá trị âm trong ảnh đã lọc làm dừng. Ảnh đầu vào cần băng bức xạ scale=1, offset=0; một băng hoặc hai băng có tên avg_rad/cf_cvg. Không áp dụng bộ ngưỡng VIIRS cho DN của DMSP.

Căn cứ chi tiết và tài liệu tham khảo: [GIAO_DIEN_DEMO_PHAN_B.md](GIAO_DIEN_DEMO_PHAN_B.md). Đã nhận method.json thật ngày 22/11: q50=3,0850000381469727 và q90=17,459999084472656, tham chiếu 2020 với 147.598 pixel sáng theo metadata. Kết quả này thay cho mọi mốc minh họa; xem [đối chiếu dữ liệu thật](DOI_CHIEU_KET_QUA_PHAN_D.md) trước khi nghiệm thu.

## 3. Diện tích và mẫu số

A_k = tổng diện tích các pixel hợp lệ thuộc lớp k. A_valid = tổng diện tích tất cả pixel hợp lệ. A_lit = A_2 + A_3 + A_4. Không nhân cố định mỗi pixel với 0,25 km².

- Với EPSG:4326: a_i = abs(dlon × dlat) × 111,320² × cos(vĩ độ tâm pixel). Đây là xấp xỉ đang dùng trong bộ tính; không gọi là diện tích ellipsoid chính xác.
- Với lưới chiếu mét: a_i = abs(dx × dy)/10⁶. Lưới xoay/CRS không hỗ trợ làm dừng.
- `class_area_pct = 100 × A_k / area_km2`.
- `valid_area_pct = 100 × A_valid / area_km2`.
- `lit_area_pct = 100 × A_lit / area_km2`.

Mẫu số `area_km2` là diện tích tự nhiên tỉnh, lấy từ CSV `province_areas.csv` phần A nếu có `--areas`; nếu không, lấy dòng tương ứng đúng tỉnh/năm/tháng trong `ntl_annual` hoặc `ntl_monthly`. Nguồn mẫu số lưu ở `area_source`; không thay bằng tổng diện tích pixel. Thiếu hoặc không có mẫu số dương thì tỷ lệ để trống, báo `missing_province_area`; không kết luận kiểm chứng tỷ lệ đã hoàn tất.

Theo quy tắc phần A, tính cả diện tích pixel giao biên tỉnh. Độ phủ có thể vượt 100%; giữ số và cờ `coverage_above_polygon`, không cắt về 100% hoặc tự sửa mask. Không tự kết luận mọi trường hợp vượt đều do pixel giao biên: cần đối chiếu mask và mẫu số, đặc biệt khi vượt nhiều. Muốn loại sai số giao biên phải làm bước diện tích phần giao polygon–pixel riêng, chưa triển khai ở đây.

Toàn NoData: diện tích hợp lệ bằng 0, các diện tích lớp bằng 0, nhưng tỷ lệ lớp và tỷ lệ diện tích sáng để trống, trạng thái `no_valid_pixels`; không kết luận tỉnh tối. `nodata_pixels` gồm ô ngoài tỉnh trong hình chữ nhật raster, không phải số pixel mây.

## 4. Phép kiểm chứng khi chạy

- Đối chiếu kích thước, CRS, transform, nguồn ảnh, ngưỡng và năm tham chiếu giữa COG và raster nguồn.
- Đối chiếu mask với tập pixel bức xạ nguồn hợp lệ, kể cả giá trị 0.
- Tính lại mã lớp từ bức xạ từng pixel, so với COG đã tạo; không chỉ tin tag THRESHOLDS.
- Kiểm tra vùng không hợp lệ được ghi 255, mã hợp lệ thuộc 0–4.
- Cộng diện tích từng lớp; đối chiếu với diện tích hợp lệ từ mask nguồn bằng rtol=1e−10, atol=1e−8 km². Sai lệch số thực rất nhỏ vẫn ghi lại đầy đủ trong CSV.
- Chỉ ghi kết quả SQLite khi toàn bộ ảnh vượt các kiểm tra trên. `passed` xác nhận các kiểm tra kỹ thuật, không có nghĩa đã xác nhận ý nghĩa kinh tế hay độ chính xác diện tích phần giao biên.

## 5. Lệnh chạy trên máy demo

Dừng uvicorn trước khi cập nhật dữ liệu. Không cần chạy lại `load_demo` nếu lần nạp trước đã thành công.

```powershell
git pull origin night-app
Test-Path "E:\SatelliteData\_demo_preparation\20261121_224811_221282\province_areas.csv"
Get-ChildItem "E:\SatelliteData\cog\light_classes" -Directory
```

Nếu thư mục lượt cũ có method.json và ảnh phân lớp, tiếp tục để kiểm chứng/xuất CSV, không tạo lại COG đã có:

```powershell
python -m backend.data.build_light_classes --root "E:\SatelliteData" --resume-latest --areas "E:\SatelliteData\_demo_preparation\20261121_224811_221282\province_areas.csv"
```

Chỉ dùng đường dẫn `--areas` khi Test-Path=True; nếu dữ liệu chuẩn bị được chuyển thư mục, sửa theo vị trí thật. Có thể bỏ `--areas` để dùng diện tích trong SQLite, nhưng cần kiểm tra `missing_province_area` và `area_source`.

Nếu `--resume-latest` không tìm thấy method.json như lỗi đã gặp, chưa chạy lại phân lớp ngay. Tìm đường dẫn thật:

```powershell
Get-ChildItem "E:\" -Filter method.json -File -Recurse -ErrorAction SilentlyContinue | Select-Object FullName
```

Dùng `--resume-dir "THU_MUC_CHA_CUA_METHOD_JSON"` thay cho `--resume-latest`, đồng thời sửa `--root` về đúng kho dữ liệu. Nếu thật sự không còn kết quả cũ, bỏ hai tùy chọn resume để tạo lượt mới; bước này sẽ phân lớp lại các ảnh.

Chương trình vẫn đọc và đối chiếu từng pixel khi dùng lại ảnh nên cần thời gian. Kết thúc thành công sẽ in đường dẫn báo cáo và các số đếm. Chỉ sau đó khởi động app:

```powershell
python -m uvicorn backend.api.main:app --reload --port 8000
```

## 6. Kiểm tra trên app và đầu ra cần gửi lại

Chọn tỉnh, năm/tháng ở thanh chung, mở màn Ảnh đêm và lớp “năm mức sáng”. Bảng cột trái có km² và % tỉnh từng lớp, diện tích có dữ liệu/độ phủ, số pixel hợp lệ/NoData và trạng thái kiểm chứng. Có nút tải CSV đúng tỉnh/mốc đang chọn; API tương ứng `/api/demo/classes.csv?province_code=01&nam=2024&thang=0`. GeoTIFF tải qua nút ảnh hiện có. Số liệu vắng chưa được thay bằng 0.

Đã nhận đủ `validation_report.json`, `light_class_validation.csv`, `light_class_areas.csv` và `method.json` ngày 22/11. Đối chiếu số học đạt, nhưng chưa nghiệm thu độ chính xác diện tích và chuỗi tháng: 57 ảnh tháng rỗng, mọi ảnh năm có độ phủ vượt 100%, 20 mốc tỷ lệ sáng vượt 100%. Xem [báo cáo và việc cần xử lý](DOI_CHIEU_KET_QUA_PHAN_D.md). Sau khi xử lý cần xuất lại báo cáo và đối chiếu vài tỉnh/năm với raster/bản đồ thực tế.
