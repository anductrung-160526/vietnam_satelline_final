# PHẦN B — GIAO DIỆN RAW / PROCESSED VÀ ĐỐI CHIẾU GRDP

## 1. Chức năng đã thực hiện

- Thanh phạm vi dùng chung: tỉnh, năm, cả năm hoặc tháng. Mặc định Hà Nội, 2024, cả năm.
- Chọn tỉnh trên bản đồ hoặc cột bên trái cập nhật phạm vi chung và bảng so sánh.
- Màn Chỉ số đêm hiển thị định danh trước, Raw trước Processed; số 0 được giữ, thiếu số có lý do.
- Raw gồm băng VIIRS gốc `avg_rad`, `cf_cvg`, dân số, GRDP so sánh và hiện hành. Hai băng ảnh chỉ có khi đã đăng ký file gốc phù hợp; ảnh năm tổng hợp không bị gán nhãn Raw.
- Trường Processed hiển thị tên dictionary, có ánh xạ tên cột SQLite cũ; `sol_raw` và `tnl` luôn ở nhóm Processed.
- Bảng so sánh nhiều tỉnh/nhiều năm giữ bộ lọc riêng. Khi chọn đúng một tỉnh và một mốc, phạm vi chung được cập nhật; các giá trị hiển thị luôn ghi rõ tỉnh/năm/tháng.
- Màn Ảnh đêm có lựa chọn bức xạ đã xử lý, hai băng Raw và năm mức sáng; chú giải ghi đơn vị/ngưỡng và diện tích từng mức.
- Thẻ diện tích trên bản đồ được đặt tên **Diện tích sáng**, không dùng diện tích tự nhiên tỉnh thay cho vùng sáng.
- Màn Kinh tế đêm có giá so sánh (mặc định), hiện hành và đối chiếu. Hai hồi quy dùng chung các tỉnh–năm có đủ hai loại GRDP và SOL dương, cùng đơn vị tỷ đồng.
- Các kết quả thiếu dân số/ảnh/mô hình không được thay bằng 0. Một tỉnh trong một năm không đủ mẫu hồi quy sẽ có lời giải thích, không tạo β giả.
- Khi chọn tháng, GRDP vẫn là số theo năm, được ghi rõ; không nội suy thành GRDP tháng.
- CSV tải xuống theo cùng phạm vi, giữ riêng hai cơ sở giá và nhãn loại giá dùng cho cột dẫn xuất.
- Dữ liệu giả nếu dùng kiểm thử có nhãn rõ; bộ nạp dữ liệu thật không tự gọi demo_seed.

## 2. Cách nạp dữ liệu thật trên máy demo

Đóng tiến trình uvicorn đang chạy trước khi nạp; giữ các bản sao database mà chương trình tạo.

```powershell
git pull origin night-app
python -m backend.data.load_demo --root "E:\SatelliteData" --prepared "E:\SatelliteData\_demo_preparation\20261121_224811_221282"
python -m backend.data.build_light_classes --root "E:\SatelliteData"
python -m uvicorn backend.api.main:app --reload --port 8000
```

Mở `http://localhost:8000`, tải lại trang để lấy frontend mới.

### Khôi phục lượt phân lớp bị lỗi bảng mã Windows

Nếu đã xử lý hết ảnh nhưng dừng tại `SCHEMA.read_text()` với `UnicodeDecodeError` (cp1252), cập nhật code và chạy:

```powershell
git pull origin night-app
python -m backend.data.build_light_classes --root "E:\SatelliteData" --resume-latest
```

Lệnh chọn thư mục mới nhất có `method.json` trong `E:\SatelliteData\cog\light_classes`, giữ bộ ngưỡng đã tính, đọc COG cũ để lấy diện tích và hoàn tất nạp SQLite. Không phân lớp lại những ảnh đã có. Vẫn cần thời gian đọc và kiểm tra 4.095 ảnh. Dừng app trước khi chạy. Nếu một ảnh còn thiếu, chỉ ảnh đó được phân lớp; ảnh có metadata/mask không khớp sẽ báo lỗi thay vì tự bỏ qua. Có thể chỉ định lượt cụ thể bằng `--resume-dir "E:\SatelliteData\cog\light_classes\TEN_THU_MUC"`.

Lần `load_demo` đã báo thành công thì không cần nạp lại chỉ để khắc phục lỗi này. Nếu cần nạp lại mà thiếu `grdp_all_prices.csv`, kiểm tra đúng thư mục chuẩn bị:

```powershell
Test-Path "E:\SatelliteData\_demo_preparation\20261121_224811_221282\grdp_all_prices.csv"
Get-ChildItem "E:\SatelliteData\_demo_preparation" -Filter grdp_all_prices.csv -Recurse
```

Đường dẫn dùng `_demo_preparation`, không có dấu gạch chéo giữa `_` và `demo_preparation`. Dùng thư mục cha của CSV tìm thấy cho `--prepared`; không cần chạy lại toàn bộ phần A chỉ vì nhập sai đường dẫn.

`load_demo`:

- Đọc `grdp_all_prices.csv`, `manifest_candidates.csv`, `image_inventory.csv` từ phần A.
- Lưu GRDP vào bảng `economy_prices` với khóa **tỉnh + năm + cơ sở giá**. Không ghi đè bảng `economy` cũ.
- Đăng ký đường dẫn ảnh tỉnh; Raw lấy đúng file hai băng avg_rad/cf_cvg trong raw_data.
- Nạp `ntl_annual.csv`, `ntl_monthly.csv`, và các CSV dictionary nếu có ở `<root>/VN_NTL_Panel_2004_2025/data_processed/`.
- Có thể dùng `--indices-dir "DUONG_DAN_KET_QUA_CHI_SO"` nếu kết quả tính nằm ở thư mục khác.
- Báo số dòng đã nạp từng bảng. Nếu indices là 0, màn hình sẽ ghi thiếu kết quả; kiểm tra CSV đầu vào hoặc chạy bước tính chỉ số trước.
- Sao lưu SQLite trước khi nạp, bổ sung bảng mới, giữ sổ COG và dữ liệu đang có. File backup được bỏ qua bởi Git.
- Kết quả dictionary ghép kinh tế phải có `grdp_price_basis` để được dùng ở đúng cơ sở giá; không tự gán kết quả thiếu nhãn thành giá so sánh.

`build_light_classes`:

- Cần đủ 63 ảnh năm VIIRS 2020 đã đăng ký; thiếu ảnh tham chiếu thì dừng, không khớp ngưỡng trên một mẫu thiếu.
- Chọn ngưỡng một lần từ năm tham chiếu, phân lớp các ảnh VIIRS 2020–2024 đã đăng ký, bao gồm ảnh tháng có mặt.
- In bốn mốc số thực tế, đường dẫn `method.json` và số ảnh đã phân lớp.
- Xuất COG lớp sáng vào `<root>/cog/light_classes/<thời điểm>/`; không sửa ảnh bức xạ gốc.
- Nạp diện tích từng lớp và đường dẫn COG vào database. Chỉ cập nhật sau khi cả lượt tạo ảnh thành công.
- Nếu phân bố tham chiếu không tạo được các mốc tăng nghiêm ngặt, dừng để rà soát, không tự tạo số cho đủ năm lớp.

## 3. Căn cứ của năm mức sáng

> Bộ ngưỡng hiện hành đã chuyển sang **0,50 / 2,00 / 10,00 / 20,00** theo Ozturk & Ozturk (2025), Bảng 3. Phần P50/P90 bên dưới là lịch sử của bản demo trước. Cập nhật diện tích và bản đồ bằng lệnh tại [Phân lớp sáng phần D](PHAN_LOP_SANG_PHAN_D.md); không đổi nhãn dữ liệu cũ thành ngưỡng mới.

Đây là **phân loại bức xạ thực nghiệm cho demo**, không phải chuẩn phân loại hoạt động kinh tế, đất đô thị hoặc mức sống. Không khẳng định các tài liệu tham khảo quy định chính xác năm khoảng này cho Việt Nam.

Đơn vị: nW/cm²/sr, chỉ áp dụng VIIRS. Không dùng chung ngưỡng với DN của DMSP.

Gọi `q50`, `q90` là phân vị 50% và 90% của **các pixel sáng r ≥ 1,5** trong toàn bộ 63 ảnh VIIRS năm 2020:

| Mức | Khoảng bức xạ | Căn cứ |
|---|---|---|
| Tối / dưới ngưỡng nền | 0 ≤ r < 0,5 | Ngưỡng nền đang được chốt trong dự án; không khẳng định pixel này tối tuyệt đối |
| Sáng yếu | 0,5 ≤ r < 1,5 | Khoảng từ ngưỡng nền dự án đến ngưỡng sáng của Task 3 |
| Sáng vừa | 1,5 ≤ r < q50 | Nửa dưới của phân bố pixel sáng năm tham chiếu |
| Sáng mạnh | q50 ≤ r < q90 | Từ trung vị đến phân vị 90 của phân bố sáng tham chiếu |
| Rất sáng | r ≥ q90 | Nhóm 10% sáng nhất trong phân bố pixel sáng tham chiếu, không phải 10% diện tích tỉnh |

Lựa chọn P50/P90 là quy ước thống kê minh bạch của bản demo, không phải ngưỡng vật lý được một nghiên cứu xác nhận. Chúng tạo nhóm trung tâm và đuôi sáng mạnh, có thể tính lại từ chính bộ dữ liệu. Trước khi dùng cho nghiên cứu chính thức cần xem phân bố, bản đồ và độ nhạy với lựa chọn phân vị.

- Mốc 0,5: quy tắc loại nền đã có trong `CLAUDE.md` và `calculate_ntl.py` của dự án.
- Mốc 1,5: ngưỡng pixel sáng trong notebook Task 3 người dùng cung cấp.
- q50/q90 phải được tính trên máy chứa ảnh thật; không dùng số từ ảnh mẫu kiểm thử thay thế.
- Dùng mọi pixel sáng hợp lệ của năm tham chiếu, tính phân vị tuyến tính theo số pixel; chưa phải phân vị có trọng số diện tích. Pixel giao hai tỉnh có thể xuất hiện trong cả hai ảnh.
- Các mốc được giữ nguyên giữa các năm và các tháng để thay đổi màu phản ánh thay đổi bức xạ, không phải thay đổi bộ chia mỗi năm.
- NoData được gán 255, không xếp vào lớp tối; biên bằng ngưỡng thuộc lớp cao hơn.
- Diện tích lớp là tổng diện tích pixel hợp lệ, có điều chỉnh theo vĩ độ ở EPSG:4326; pixel giao biên được tính cả pixel theo quy tắc phần A.
- Tổng diện tích năm lớp bằng diện tích pixel có dữ liệu, không ép bằng diện tích tự nhiên tỉnh khi thiếu quan sát.

### Tài liệu đối chiếu phương pháp

- [EOG — VIIRS Nighttime Light](https://eogdata.mines.edu/products/vnl/index.html): đơn vị bức xạ, vai trò cf_cvg, ảnh hưởng chất lượng quan sát và nguyên tắc xử lý/ngưỡng nhất quán theo thời gian. EOG không quy định năm khoảng phân loại của bản demo này.
- [Elvidge và cộng sự, 2021 — Annual Time Series of Global VIIRS Nighttime Lights](https://doi.org/10.3390/rs13050922): xử lý nền và tính nhất quán chuỗi thời gian. Ngưỡng data-range trong sản phẩm EOG khác ngưỡng cường độ r đang chia ở đây; không đánh đồng hai loại ngưỡng.
- [Liu và cộng sự, 2019 — Automated Extraction of Built-Up Areas](https://doi.org/10.3390/rs11131571): ví dụ xác định ngưỡng theo dữ liệu và đối chiếu với thông tin khác khi suy ra đất xây dựng. Dự án này không triển khai bộ phân loại học máy của bài báo và không gán mức sáng thành loại đất.

## 4. Kiểm tra trước khi demo trên Windows

- [ ] Bộ nạp báo đủ dòng hai loại GRDP và đường dẫn ảnh, có bản sao database.
- [ ] Không nhầm CSV chứa cả hai cơ sở giá với bộ đọc cũ chỉ có khóa tỉnh–năm.
- [ ] Đổi tỉnh trên bản đồ và trên thanh chung, đối chiếu tên tỉnh/năm ở cả ba màn.
- [ ] Chọn ảnh tháng để xem/tải Raw hai băng; ảnh năm hiển thị đúng thông báo khi không có Raw năm.
- [ ] Raw nằm trước Processed; số 0 vẫn là 0, thiếu dữ liệu có lý do.
- [ ] Bốn mốc thật trong method.json khớp chú giải và TIFF phân lớp; không dùng ngưỡng test.
- [ ] Diện tích năm lớp khớp kết quả xuất; raster bức xạ nguồn không bị thay đổi.
- [ ] Đối chiếu hai cơ sở giá, xem cờ sơ bộ 2024 và cờ cần rà soát nguồn.
- [ ] File CSV/GeoTIFF tải đúng tỉnh/năm đang chọn.

Đã kiểm tra tự động API, bộ nạp, phép chia lớp và diện tích trên dữ liệu biết trước; đã thử luồng trình duyệt desktop/mobile với ảnh tổng hợp có nhãn kiểm thử. Việc nạp và kiểm tra trực tiếp bộ ảnh thật ở ổ E: vẫn cần chạy trên máy demo.
