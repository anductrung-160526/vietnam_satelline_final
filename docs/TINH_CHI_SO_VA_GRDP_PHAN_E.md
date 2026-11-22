# Phần E — SOL, mật độ, biến động và hai cơ sở giá GRDP

Đã hoàn thiện code và kiểm tra trên ảnh/số liệu biết trước. Cần chạy trên bộ ảnh thật ở E: để có hệ số và bộ kết quả thực tế; không suy SOL từ diện tích lớp hoặc dùng dữ liệu giả thay thế. Vấn đề diện tích và tháng thiếu dữ liệu phần D vẫn giữ nguyên trạng thái chưa nghiệm thu.

## 1. Phần tính đã thực hiện

| Chỉ số/đầu ra | Quy tắc |
|---|---|
| sol_raw | Tổng bức xạ hợp lệ trước loại nền trên ảnh đầu vào đã lọc; không phải băng Raw |
| sol | Tổng pixel đạt ngưỡng nền; pixel dưới nền đóng góp 0; kiểm tra 0 ≤ sol ≤ sol_raw |
| sol_density | Tổng sáng đã chọn / diện tích tự nhiên tỉnh; light_basis ghi sol hay sol_cal |
| lit_area_km2 / lit_area_pct | Diện tích pixel sáng và tỷ lệ trên diện tích tự nhiên, hiện vẫn xấp xỉ theo toàn pixel giao biên; giữ cờ giới hạn |
| electrification_ratio_pct | Số pixel sáng / pixel hợp lệ ×100; mẫu số khác lit_area_pct |
| tnl_ma3 / tnl_mom_growth_pct | Ba dòng quan sát tháng và tăng trưởng so dòng tháng trước; có thể qua tháng lịch thiếu |
| sol_ma3 / sol_change_mom_pct / sol_change_yoy_pct | Ba tháng lịch / tháng lịch trước / cùng tháng năm trước; không dùng dòng kế cận thay tháng thiếu |
| sol_change_pct | Năm liền trước, đúng chuỗi ánh sáng; chặn năm 2010, chưa hiệu chỉnh thì không so qua đổi nguồn 2013–2014 |
| gdp_change_pct | Tăng trưởng GRDP năm liền trước, tính riêng từng cơ sở giá; có thể có ngay cả khi thiếu ảnh |
| sol_per_capita | sol_cal / dân số năm; thiếu dân số hoặc không dương thì trống; chỉ tính ở dòng năm |
| light_gdp_elasticity | %Δsol_cal / %ΔGRDP giữa năm liền nhau, từng cơ sở giá; mẫu số tăng trưởng bằng 0/thiếu thì trống; chặn 2010 |
| predicted_gdp | exp(α + β ln ánh sáng) từ mô hình riêng từng giá trên cùng mẫu; không điền vào ô GRDP gốc, không khẳng định là dự báo tương lai đã kiểm định |

Nguồn code: `calculate_ntl.py` đọc raster một lần, tính thống kê/thời gian, gọi `economy_indices.py` ghép hai giá. Ghi chú cạnh từng khối chỉ rõ chỉ số đang tính. STATS_VERSION tăng từ 7 lên 8; không dùng kết quả phiên bản trước như thể đã tính lại.

## 2. Hai giá và mẫu mô hình

- CSV hai giá dùng khóa **province_code + year + grdp_price_basis**; giữ so_sanh/hien_hanh riêng. Đơn vị ty_vnd; giá so sánh năm gốc 2010, giá hiện hành không có năm gốc.
- Giữ nguồn, quality_flags, is_provisional, price_base_year và ô GRDP thiếu. Có GRDP mà chưa có ảnh vẫn có dòng năm với chỉ số ánh sáng để trống. Có ảnh mà thiếu một giá vẫn giữ dòng với cờ thiếu giá.
- Night Data giữ một dòng cho mỗi ảnh; Night Economy có một dòng cho mỗi tỉnh/năm/tháng/giá. Khi chọn tháng, GRDP chỉ là tham chiếu năm, không phải nội suy GRDP tháng. Ba chỉ số ghép kinh tế trên đầu người/tỷ số tăng trưởng/ước lượng không tự tạo thành kết quả tháng.
- Hai mô hình log–log dùng chung mẫu VIIRS năm từ 2014, ánh sáng và cả hai GRDP dương; loại nguồn GIA_LAP. Cần ít nhất 10 điểm và biến thiên log ánh sáng. Dùng cùng light_basis và cùng đơn vị tỷ đồng. Không tự loại cờ rà soát GRDP khỏi mẫu, nên vẫn phải đối chiếu nguồn trước báo cáo khoa học.
- Giá so sánh là cơ sở chính thức của bộ cô cung cấp; giá hiện hành dùng đối chiếu. Chế độ hai giá mới tính cả hai mô hình/tỷ số; luồng `--economy` một giá cũ vẫn giữ hợp đồng trước đó, chỉ ước lượng mô hình giá so sánh.
- β là độ co giãn GRDP theo ánh sáng trong mô hình, không phải %Δánh sáng/%ΔGRDP. Không diễn giải quan hệ gộp này là nhân quả.
- Mỗi kết quả ước lượng giữ model_training_period, model_n, model_beta và model_light_basis. Mô hình CSV offline khớp theo toàn bộ đầu vào; biểu đồ/mô hình API khớp lại theo phạm vi đang chọn, nên hệ số có thể khác nhau. App ghi rõ sự khác biệt này.

Chưa bật hiệu chỉnh DMSP–VIIRS cho luồng demo chỉ VIIRS 2020–2024. Nếu muốn dùng --calibrate, manifest phải có đủ ≥30 cặp tỉnh DMSP/VIIRS 2013 dương và mô hình mũ hợp lệ, lưu calculation_models.csv. Không dùng hiệu chỉnh này để sửa mốc F16/F18 năm 2010. Thiếu cặp thì dừng, không tạo hệ số giả.

## 3. Cờ chất lượng phần D được mang sang

`--class-validation` nhận light_class_validation.csv thật của phần D. Đối chiếu số pixel hợp lệ từng khóa với lần tính lại; khác thì dừng để tránh ghép báo cáo khác phiên bản. Chưa chứng minh hai raster giống nhau chỉ bằng phép đếm này; vẫn cần giữ đúng manifest/nguồn.

Các cờ gồm WHOLE_PIXEL_AREA_APPROXIMATION, COVERAGE_ABOVE_100, LIT_AREA_ABOVE_100, NO_VALID_PIXELS, LOW_CLOUD_FREE_OBSERVATIONS, VALID_PIXEL_COUNT_CHANGED; thiếu báo cáo D thì PART_D_NOT_LINKED. MISSING_IMAGE chỉ dòng có kinh tế mà không có ảnh trong manifest. comparison_note ghi giới hạn GRDP năm khi xem tháng và thay đổi số pixel hợp lệ giữa năm.

Không tự đặt ngưỡng loại mẫu 50%/90% để loại tháng; quy tắc chất lượng chưa được chốt. Trường độ phủ và cờ đi cùng kết quả để rà soát. Tháng hoàn toàn NoData không trở thành SOL=0; tăng trưởng thiếu giá trị tham chiếu để trống. Độ phủ thay đổi có thể làm tăng trưởng ánh sáng khác biến động kinh tế.

**Chưa sửa sai lệch diện tích trong phần E.** Theo [đối chiếu phần D](DOI_CHIEU_KET_QUA_PHAN_D.md), 57 tháng rỗng, 315 ảnh năm có độ phủ trên 100%, 20 mốc tỷ lệ sáng trên 100%. Giữ các số/cờ và nhãn xấp xỉ; không cắt tỷ lệ về 100% hoặc tự đổi mẫu số. Bộ E hoàn thiện công thức/ghép giá không đồng nghĩa đã nghiệm thu địa lý hoặc kinh tế.

## 4. Chạy trên Windows

Dừng app đang chạy. Lấy code mới:

```powershell
git pull origin night-app
```

Tạo thư mục kết quả mới để giữ bản đang dùng:

```powershell
$eOutput = Join-Path "E:\SatelliteData\_demo_economy" (Get-Date -Format "yyyyMMdd_HHmmss")
python -m backend.data.calculate_ntl --root "E:\SatelliteData" --manifest "E:\SatelliteData\_demo_preparation\20261121_224811_221282\manifest_candidates.csv" --economy-prices "E:\SatelliteData\_demo_preparation\20261121_224811_221282\grdp_all_prices.csv" --class-validation "E:\SatelliteData\cog\light_classes\20261121_235905_739916\light_class_validation.csv" --output "$eOutput"
```

Các đường dẫn trên lấy từ lượt chuẩn bị và file phần D bạn đã gửi. Nếu đã chuyển kho/thư mục, sửa theo vị trí thật. Chương trình báo tiến độ mỗi 100 ảnh; tính 4.095 ảnh cần thời gian, không tải lại hoặc sửa ảnh nguồn. Không dùng --overwrite để ghi lên thư mục đang trình diễn.

Các file chính: night_data.csv, night_economy.csv, ntl_annual.csv, ntl_monthly.csv, calculation_models.csv và economy_validation.csv. Với đúng 4.095 ảnh 2020–2024 và 1.260 dòng GRDP 2015–2024, dự kiến Night Data=4.095, Night Economy=8.820 (1.260 dòng năm + 7.560 dòng tháng). 630 dòng năm không có ảnh trong lần tính 2020–2024 tương ứng hai giá của 315 tỉnh–năm 2015–2019; không phải mất dữ liệu GRDP. Các số mô hình thực tế phải xem kết quả, không giả định đủ 315 cặp trước khi chạy.

Nạp kết quả mới sau khi lệnh tính thành công:

```powershell
python -m backend.data.load_demo --root "E:\SatelliteData" --prepared "E:\SatelliteData\_demo_preparation\20261121_224811_221282" --indices-dir "$eOutput"
python -m uvicorn backend.api.main:app --reload --port 8000
```

load_demo sao lưu và upsert, giữ sổ COG/lớp sáng và dữ liệu cũ ở các mốc khác; không gọi cơ chế reset schema. CSV dictionary trùng khóa bị từ chối trước cập nhật. SQLite economy_prices vẫn lưu cả hai giá, demo_result giữ kết quả riêng từng giá. Việc nạp lại không xóa vấn đề chất lượng phần D.

## 5. Kiểm tra sau khi chạy

1. Gửi economy_validation.csv và calculation_models.csv để kiểm tra số dòng, mẫu chung và hai mô hình. empty_images đếm ảnh thật; empty_image_result_rows đếm dòng kết quả theo hai giá, nên có thể gấp đôi.
2. Đối chiếu vài dòng night_economy.csv: sol_raw/sol/mật độ, năm tham chiếu tăng trưởng, hai giá/đơn vị/nguồn/sơ bộ, ô thiếu, image_quality_flags. Chưa có dân số thì sol_per_capita phải trống.
3. Chọn 2024 trên app, đổi so_sanh/hien_hanh/compare, đối chiếu GRDP và kết quả ước lượng với cùng dòng CSV; tải CSV kiểm tra derived_price_basis, model_training_period/n và cờ chất lượng.
4. Dữ liệu năm 2015–2019 còn sẵn trong SQLite từ lần cũ không đồng nghĩa đã được tính lại bởi manifest 2020–2024. Dùng đúng phạm vi demo và phiên bản khi đối chiếu; phần F tiếp tục kiểm tra tính xuyên suốt.
5. Giữ mục nghiệm thu thực tế mở cho tới khi nhận kết quả Windows; không dùng hệ số từ ảnh kiểm thử làm kết quả nghiên cứu.
