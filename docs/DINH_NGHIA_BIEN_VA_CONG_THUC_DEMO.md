# Định nghĩa biến và công thức — demo kinh tế đêm

Ngày cập nhật: 22/11/2026. Phạm vi: 63 tỉnh trước sáp nhập; dữ liệu demo chính VIIRS 2020–2024, GRDP theo năm. Đây là bản làm việc phần C; chưa nhận form của giảng viên để xác nhận đúng biểu mẫu. Tài liệu Word cùng tên được sinh từ tài liệu này và `NIGHT_DATA_DICTIONARY.md`, không nhập lại danh mục bằng tay.

## 1. Danh mục và cách đếm

Danh mục chuẩn là bảng duy nhất trong [NIGHT_DATA_DICTIONARY.md](NIGHT_DATA_DICTIONARY.md). `table` chỉ có **Night Data** hoặc **Night Economy**. Tên trường chữ thường tiếng Anh, diễn giải tiếng Việt; định danh ở đầu, tiếp theo Raw, sau đó Processed, nhóm dùng chuỗi hiệu chỉnh ở cuối.

Số lượng được chương trình sinh Word đếm trực tiếp từ bảng. Đếm mỗi dòng định nghĩa một lần; không cộng lại các khóa xuất ở cả hai CSV. Đây là số mục từ điển gồm chỉ số, metadata và tham số, không đồng nghĩa số biến độc lập của mô hình. `tnl` và `sol_raw` vẫn được giữ để truy nguồn nhưng bằng nhau trên cùng đầu vào, không tính như hai nguồn thông tin độc lập.

Phần D đã triển khai `valid_area_km2`, `valid_area_pct`, `class_area_pct`, xuất CSV và hiển thị trên app sau khi chạy kiểm chứng. Sau phần P1, danh mục có 121 mục: 19 Raw (6 định danh) và 102 Processed; gồm cả metadata/tham số, không phải 121 biến độc lập. Không còn ba công thức chỉ ở mức đề xuất như bản đầu phần C. `light_class.area_km2` là tên có tiền tố bảng để phân biệt diện tích lớp với diện tích tự nhiên tỉnh, không phải tên một cột SQLite có dấu chấm.

## 2. Ký hiệu, nguồn và quy tắc đầu vào

- V: tập pixel bức xạ hợp lệ trong ảnh tỉnh, có mask hợp lệ, hữu hạn và khác -9999. Giá trị 0 thuộc V. N = số pixel trong V.
- R_i: bức xạ pixel i của ảnh đầu vào đang tính; U là nW/cm²/sr với VIIRS, DN với DMSP. Tổng bức xạ là tổng giá trị pixel, không phải tổng công suất phát sáng vật lý; không nhân diện tích trong công thức SOL.
- C_i: số lượt quan sát sạch mây của băng cf_cvg. Tập pixel lấy trung bình C_i phải đồng thời hợp lệ ở băng bức xạ và băng cf_cvg, với C_i ≥ 0.
- A: diện tích tự nhiên tỉnh GADM 4.1, chiếu EPSG:6933 rồi chia 10⁶ để được km². Không đổi ranh giới giữa các năm so sánh.
- a_i: từ v9 fractional là diện tích phần giao pixel với tỉnh, đo trong EPSG:6933 chia 10⁶. Bản cũ trước sửa dùng diện tích cả pixel, km². Với lưới chiếu đơn vị mét: abs(dx × dy)/10⁶. Với EPSG:4326: abs(dlon × dlat) × 111,320² × cos(latitude_center_i). Đây là xấp xỉ theo vĩ độ của code, không phải phép đo diện tích ellipsoid chính xác. Không hỗ trợ lưới xoay.
- b: ngưỡng nền, VIIRS 0,5; DMSP 0. h: ngưỡng sáng, VIIRS 1,5; DMSP 5. Pixel bằng ngưỡng được giữ trong nhóm đạt ngưỡng.
- G_y: GRDP tỉnh năm y của cơ sở giá được chỉ định; P_y: dân số tỉnh năm y. Giá so sánh năm gốc 2010 là cơ sở chính; giá hiện hành để đối chiếu. Cả hai dùng tỷ đồng.
- Ảnh năm VIIRS được tổng hợp median ở từng pixel từ ảnh tháng đã lọc, sau đó mới tính tổng/thống kê. Không thay bằng median của các tổng SOL tháng. Ảnh năm tổng hợp là Processed.
- Raw là đầu vào của dự án: sản phẩm VIIRS tháng đã qua xử lý của nhà cung cấp và số liệu thống kê nguồn. Một đường dẫn #band=1 trong CSV tính lại có thể trỏ ảnh đã lọc; không vì tên avg_rad mà gọi ảnh đó là Raw. App phần B chỉ đăng ký Raw hai băng từ raw_data.

## 3. Tổng sáng, vùng sáng và các mẫu số

TNL = SOL_raw = tổng R_i trên V, khi cùng ảnh, cùng mask và cùng thời gian. SOL = tổng R_i × 1[R_i ≥ b]. Pixel dưới nền đóng góp 0; không lấy R_i − b. Phần bị loại là SOL_raw − SOL trên cùng đầu vào.

L = tổng 1[R_i ≥ h]; T_lit = tổng R_i × 1[R_i ≥ h]; A_lit = tổng a_i × 1[R_i ≥ h]. Không suy dân số từ T_lit dù tên lịch sử là lit_pop_proxy.

Ba tỷ lệ khác nhau: lit_area_pct = 100 × A_lit/A; electrification_ratio_pct = 100 × L/N; valid_area_pct = 100 × tổng a_i/A. Tỷ lệ số pixel không mặc nhiên bằng tỷ lệ diện tích, nhất là lưới địa lý. valid_area_pct đã tính offline và lưu light_class_summary trong phần D.

sol_density = SOL_selected/A, không phải diện tích sáng. SOL_selected được ghi ở light_basis. CSV tính lại có thể chọn sol_cal bằng --calibrate; SQLite/API phần B dùng sol. VIIRS giữ sol_cal=sol nên bằng nhau trong demo 2020–2024; không suy rộng sự bằng nhau sang DMSP.

## 4. Năm lớp sáng và diện tích

Chỉ áp dụng phân lớp này cho VIIRS, đơn vị nW/cm²/sr. Các mốc là [0,5; 1,5; q50; q90]. q50/q90 lấy bằng phân vị tuyến tính trên tất cả pixel hợp lệ R≥1,5 của 63 ảnh năm 2020, theo số pixel, chưa có trọng số diện tích; các pixel giao biên có thể lặp giữa hai tỉnh. Bộ ngưỡng được giữ cố định cho các năm/tháng.

- Lớp 0: 0 ≤ R < 0,5; gọi là tối/dưới ngưỡng nền, không kết luận không phát sáng tuyệt đối.
- Lớp 1: 0,5 ≤ R < 1,5; sáng yếu.
- Lớp 2: 1,5 ≤ R < q50; sáng vừa.
- Lớp 3: q50 ≤ R < q90; sáng mạnh.
- Lớp 4: R ≥ q90; rất sáng. Đây là đuôi 10% pixel sáng của năm tham chiếu, không phải 10% diện tích mỗi tỉnh.

A_k = tổng a_i × 1[pixel thuộc lớp k]. Tổng A_k = A_valid. class_area_pct = 100 × A_k/A đã tính offline, lưu ở light_class_summary.class_area_pcts và xuất light_class_areas.csv; API đọc tỷ lệ đã lưu. NoData=255 không thuộc năm lớp. Code từ chối ảnh đã xử lý còn giá trị âm, ngưỡng suy biến hoặc thiếu 63 ảnh tham chiếu.

Diện tích từ v9 fractional lấy phần giao pixel–polygon trong EPSG:6933, cùng ranh giới/mẫu số; không được vượt polygon ngoài sai số số thực. V2 cũ lấy cả pixel giao ranh giới nên có thể cao hơn polygon và chỉ giữ để tham chiếu. Không ép sai lệch thực về 100%, không đổi NoData thành tối, không dùng cố định 0,25 km²/pixel.

Mốc 0,5 dựa trên quy tắc nền đã chốt của dự án; 1,5 theo Task 3. P50/P90 là lựa chọn thực nghiệm minh bạch cho demo, không phải chuẩn vật lý hay phân lớp kinh tế đã được nghiên cứu xác nhận. Giá trị số thực tế phải đọc từ method.json trên máy chứa ảnh; tài liệu này không điền số kiểm thử thay thế. Căn cứ và tài liệu đối chiếu: [GIAO_DIEN_DEMO_PHAN_B.md](GIAO_DIEN_DEMO_PHAN_B.md), EOG VIIRS Nighttime Light, Elvidge và cộng sự (2021), DOI 10.3390/rs13050922.

## 5. Thống kê và chuỗi thời gian

μ = tổng R_i/N; σ = sqrt(max(tổng R_i²/N − μ², 0)), độ lệch chuẩn tổng thể ddof=0. spatial_cv = σ/μ nếu μ>0. Khi N>0 và μ≤0, CSV dictionary ghi 0 theo Task 3, còn cột rad_cv cũ app đang ánh xạ có thể trống. N=0 thì thống kê để trống; total_pixels=0 là số đếm thực.

Tăng trưởng = 100 × (giá trị hiện tại/giá trị tham chiếu − 1); mẫu số thiếu hoặc ≤0 thì trống. SOL theo năm so đúng năm liền trước, theo tháng so đúng tháng lịch trước hoặc cùng kỳ năm trước. Chưa hiệu chỉnh chỉ so cùng nguồn; không diễn giải bước nhảy năm 2010 như tăng trưởng kinh tế, kể cả chuỗi đã nối DMSP–VIIRS.

tnl_ma3 dùng tối đa ba dòng quan sát tháng gần nhất; tnl_mom_growth_pct so dòng tháng trước trong chuỗi, có thể nhảy qua tháng thiếu. sol_ma3 dùng cửa sổ ba tháng lịch và trung bình phần có dữ liệu. Không thay hai định nghĩa này bằng nhau. Năm đầu chuỗi hoặc mốc thiếu tham chiếu thì không tạo tăng trưởng bằng 0.

Thiếu tháng làm số tháng hợp lệ khi tổng hợp ảnh năm khác nhau giữa pixel; báo cáo không mặc định đủ 12 tháng chỉ vì tên file là năm. Việc phát hiện cf_cvg <2 là cảnh báo chất lượng, không tự loại mọi pixel/tỉnh khỏi thống kê. CF_CVG_MEAN trên ảnh một băng là metadata từ bước trước, không tái tạo được băng cf_cvg hay số quan sát năm độc lập.

## 6. GRDP, hồi quy và hiệu chỉnh

Khóa bảng economy_prices: province_code + year + price_basis. Hai bộ giá được giữ đồng thời, ô thiếu không thay 0. Bắc Giang hiện hành 2015 N/a; GRDP 2024 sơ bộ. Giữ cờ các điểm cần rà soát ở Hà Nội và Thừa Thiên Huế; app chưa tự loại các điểm bị gắn cờ khỏi mô hình. GRDP theo năm; khi xem ảnh tháng, không nội suy thành GRDP tháng.

Mô hình app: ln(G) = α + β ln(SOL) + ε. Mỗi cơ sở giá có một mô hình riêng trên cùng mẫu tỉnh–năm có SOL và cả hai GRDP dương, cùng đơn vị tỷ đồng. β = cov_sum(ln SOL, ln G)/var_sum(ln SOL); α = mean(ln G) − β mean(ln SOL); R² tính trên thang log. Cần ít nhất 10 cặp và biến thiên ln SOL; hệ số riêng tỉnh của API cần ít nhất 8 năm. Một tỉnh × một năm không đủ ước lượng. Mẫu chính 2020–2024 chỉ có 5 năm nên không đủ β riêng tỉnh.

β là độ co giãn GRDP theo ánh sáng trong mô hình, không phải tỷ số %Δánh sáng/%ΔGRDP. Hồi quy gộp hiện tại không có hiệu ứng cố định hay kiểm định nhân quả. Dữ liệu giả có nhãn kiểm thử; không đưa vào kết luận nghiên cứu. Muốn báo cáo kết quả phải kiểm tra nguồn và mẫu thật, không chỉ xem số hệ số hiện trên app.

Offline calculate_ntl: light_gdp_elasticity = %Δsol_cal/%Δgdp, chỉ trên năm liền nhau, mẫu số tăng trưởng khác 0, không qua 2010. Luồng --economy cũ chỉ giá so sánh; --economy-prices mới tính riêng cả hai giá và giữ giá so sánh làm cơ sở chính. predicted_gdp = exp(α_g + β_g ln(sol_cal)), luồng một giá khớp ≥10 cặp dương từ 2014 giá so sánh; luồng hai giá v8 khớp hai mô hình VIIRS năm riêng trên cùng mẫu có đủ hai GRDP dương, loại nguồn GIA_LAP; không hiệu chỉnh sai lệch khi đổi log về mức. Đây là ước lượng trong mô hình, chưa phải dự báo tương lai đã kiểm định. API chỉ đọc các cột này khi CSV dictionary đã nạp đúng cơ sở giá, không lấy mô hình đối chiếu trên app điền vào cột còn thiếu.

sol_cal: VIIRS giữ nguyên; DMSP quy thang bằng exp(α_c) × SOL^β_c, khớp ≥30 tỉnh có cả DMSP và VIIRS 2013 dương, β_c>0. Không sửa mốc DMSP F16→F18 năm 2010. Tham số lưu calculation_models.csv; thiếu mô hình hợp lệ thì DMSP sol_cal trống. VIIRS bằng sol không phải bằng chứng đã chạy hiệu chỉnh DMSP.

sol_per_capita: offline dùng sol_cal/population; API kinh tế phần B dùng sol/population. Hai cách bằng nhau trong VIIRS demo. Chưa có dân số nên để trống, không gán dân số giả.

Lưu ý luồng nhập: --economy/read_economy vẫn nhận một giá mỗi tỉnh–năm. Từ v8 dùng --economy-prices với grdp_all_prices.csv để tính/xuất đồng thời hai giá, khóa tỉnh–năm–tháng–giá. Giữ dòng có GRDP mà chưa có ảnh; chỉ số ánh sáng để trống. load_demo nạp economy_prices và demo_result riêng từng giá, từ chối CSV trùng khóa. Hướng dẫn và nghiệm thu số liệu thật ở TINH_CHI_SO_VA_GRDP_PHAN_E.md.

## 7. NEI và tiêu chí còn mở

Chưa có công thức tổng hợp NEI được giảng viên xác nhận. Bản demo trình bày các chỉ số thành phần: quy mô ánh sáng (SOL), mật độ (SOL/A), diện tích sáng, phân bố lớp sáng, biến động và quan hệ với GRDP. Chưa coi các đại lượng này là giá trị tiền tệ kinh tế đêm, không tự tạo trọng số, không gọi β hay tỷ lệ diện tích là NEI chính thức.

Chờ chốt: NEI là chỉ số thành phần nào hay chỉ số tổng hợp; đơn vị và chuẩn hóa; trọng số nếu có; năm gốc; cách dùng GRDP; tiêu chí kiểm chứng. Dân số và form tài liệu của cô còn cần bổ sung. Đã nhận method.json thật ngày 22/11: bốn mốc 0,5; 1,5; 3,0850000381469727; 17,459999084472656 nW/cm²/sr. Báo cáo DOI_CHIEU_KET_QUA_PHAN_D.md mô tả bản v2 trước sửa: 57 ảnh tháng rỗng và 20 mốc tỷ lệ sáng vượt 100%. Bản v9 sau sửa xem KET_QUA_SAU_SUA_V9.md; độ phủ vượt 100% đã về 0, 57 tháng còn thiếu do raw không có quan sát sạch mây hợp lệ. Chấp nhận giao diện phần B không thay thế kiểm chứng từng con số trên máy demo.

## 8. Ví dụ đối chiếu có thể tính tay

Ví dụ kiểm thử, không phải số tỉnh thật: V có R=[0; 0,4; 0,5; 1,5; 10], thêm một pixel NoData; mỗi pixel hợp lệ có diện tích 1 km²; diện tích tự nhiên giả định A=6 km². Khi b=0,5 và h=1,5: N=5; TNL=SOL_raw=12,4; SOL=12; lit_pixels=2; lit_pop_proxy=11,5; lit_area_km2=2; lit_area_pct=33,3333%; electrification_ratio_pct=40%; sol_density=2 U/km²; A_valid=5 km². Các số khác nhau vì mẫu số khác nhau. Năm lớp vẫn cần bộ ngưỡng tham chiếu thật để xác định ranh giới.

## 9. Truy nguồn và cách cập nhật

- backend/data/calculate_ntl.py: ntl_stats, calculate, add_dictionary_tables, fit_log_model; CSV dictionary và mô hình offline.
- backend/data/build_light_classes.py: choose_thresholds, classify_image, saved_areas; method.json, COG lớp sáng và diện tích SQLite.
- backend/data/prepare_grdp.py: đọc GRDP nguồn, chuẩn hóa cơ sở giá, đơn vị và cờ rà soát.
- backend/data/load_demo.py và demo_schema.sql: nạp hai giá, đăng ký ảnh, kết quả dictionary tùy chọn.
- backend/api/demo_view.py: ánh xạ trường cũ, mẫu hồi quy chung, trạng thái thiếu và trường hiển thị.
- backend/core/chi_so.py: OLS và điều kiện số quan sát của app. CLAUDE.md là hợp đồng phương pháp đã chốt.

Sửa danh mục trong NIGHT_DATA_DICTIONARY.md và phần giải thích tại đây, rồi chạy `python scripts/build_demo_dictionary_doc.py` để sinh lại Word. Phụ thuộc tạo tài liệu nằm trong docs/requirements.txt, không làm tăng phụ thuộc runtime của app.

Phần D đối chiếu từng giá trị lớp với np.digitize trên ảnh nguồn, kiểm tra mask/NoData và tổng diện tích bằng rtol=1e−10, atol=1e−8; không chỉ tin metadata TIFF. Bảng kiểm chứng lưu diện tích tự nhiên và area_source. Có thể chỉ định --areas tới province_areas.csv của phần A; nếu không, lấy area_km2 đúng tỉnh/năm/tháng từ bảng ntl đã nạp. Thiếu mẫu số thì giữ diện tích lớp nhưng tỷ lệ để trống; toàn NoData ghi no_valid_pixels, không kết luận tỉnh tối. nodata_pixels đếm cả ô ngoài tỉnh trong khung raster nên không được diễn giải là số pixel mây.

Phần E xuất gdp_change_pct, mô hình hai giá và metadata model_training_period/model_n/model_beta/model_light_basis; app đọc kết quả đúng giá và phân biệt mô hình offline với hồi quy theo phạm vi xem. Cờ image_quality_flags/area_method giữ giới hạn phần D. Đã nhận báo cáo tổng hợp E chạy trên Windows với 315 cặp chung; F đã đối chiếu hệ số với ảnh/CSV/SQLite trên Windows.

## 10. Sửa diện tích và tháng thiếu v9

Workflow fix_demo_data tính diện tích giao pixel–tỉnh, đối chiếu raw hai băng với quy tắc FILTER xác minh được, xuất ảnh sửa riêng và bản đồ 0–12 tháng hợp lệ. Không tạo quan sát khi cf_cvg=0/NoData; các ca thiếu nguồn/lưới/quy tắc chưa xác minh có chẩn đoán cần rà soát. App đọc diagnosis và số tháng min/max/mean; không tự xem có đủ 12 file là đủ 12 quan sát. Đã nhận fix_report.json Windows: published=true, 4.095 ảnh tính lại diện tích, 0 mốc độ phủ trên 100%, 57 tháng raw thiếu quan sát sạch mây hợp lệ, không có lỗi FILTER cần sửa ảnh. Hai mô hình khớp trên 315 cặp chung; F đã nhận và đối chiếu hai mô hình: so sánh α=4,9099364858, β=0,6280771016, R²=0,6106039126; hiện hành α=5,5999525942, β=0,6158915247, R²=0,6305660368; cùng n=315. Tham chiếu KET_QUA_SAU_SUA_V9.md và SUA_DIEN_TICH_VA_THANG_THIEU.md. Không báo đã lấp 57 tháng, không biến thiếu nguồn thành 0.

## 11. Hợp đồng dữ liệu và xuất xứ phần F

Dataset_manifest ghi hash/số dòng CSV, dataset_id và stats_version, tách schema demo v2 khỏi thuật toán v9. Kiểm F đối chiếu từng dòng CSV/SQLite, thống kê từ ảnh, lớp/diện tích và mô hình; bản xuất TIFF crop/mask riêng khi cần, nguồn giữ nguyên. API báo nguồn mất/đổi và snapshot không đồng bộ; CSV xuất có đơn vị/chuỗi sáng/cơ sở giá/mã snapshot/hash nguồn. Tham chiếu PHAN_F_KIEM_CHUNG_VA_XUAT_DU_LIEU.md. TNL và cửa sổ ba dòng vẫn khác SOL và ba tháng lịch; nguồn raw trên app khác tham chiếu băng filtered trong CSV tính lại. Đã nhận báo cáo F trên Windows: 12.285 ảnh đạt, outside_valid_values_after=0, published=true; nghiệm thu giao diện còn cần đối chiếu sau sửa cache.


## 12. Phân tích không gian P1

Phương pháp, công thức và lệnh chạy chi tiết trong PHAN_P1_PHAN_TICH_KHONG_GIAN.md. Moran dùng sol_density VIIRS chưa hiệu chỉnh, từng năm toàn bộ tỉnh đủ điều kiện. Queen có dung sai 1 m trên EPSG:6933, chuẩn hóa hàng sau loại thiếu/cô lập; I=(n/S0) × tổng(W_ij z_i z_j)/tổng(z_i²), E[I]=−1/(n−1). Kiểm định hoán vị 9.999 lượt, seed gốc 20261123 + năm; p=(1+đếm abs(I_perm−E)≥abs(I_obs−E))/(B+1). Thiếu mẫu/phương sai bằng 0 để trống; báo n và lý do loại. Moran không phải bằng chứng nhân quả hoặc chỉ số NEI tổng hợp.

Hai năm so sánh cùng VIIRS và cùng bộ ngưỡng cố định; đưa năm đầu về lưới năm cuối bằng nearest, giữ mask. Chỉ tính vùng hợp lệ cả hai năm C. Mỗi diện tích là tổng phần giao pixel–tỉnh EPSG:6933. Mới sáng: đầu<1,5, cuối≥1,5; mất sáng: đầu≥1,5, cuối<1,5; thay đổi ròng bằng mới−mất. Sáu nhóm thay đổi cộng bằng diện tích C, ma trận 5×5 giữ chuyển lớp chi tiết. Vùng chỉ một năm có dữ liệu, thiếu cả hai và ngoài lưới đích phải báo riêng. Chênh lệch bức xạ R_cuối−R_đầu khác tăng trưởng SOL.

Trọng tâm tính trên cùng C, trọng số m=R×diện tích giao khi R≥0,5. Tọa độ là trung bình tâm pixel trong EPSG:6933 theo m, có sai số ở pixel biên và độ phân giải. Khoảng cách haversine bán kính 6371,0088 km, góc từ Bắc theo chiều kim đồng hồ. Không có trọng số dương thì trống. Không gán hướng quan sát được cho biển/đường/cảng/khu công nghiệp khi chưa có lớp đối chiếu.

Kết quả lưu spatial_run riêng, P1 version=1, không đổi thống kê v9/schema F v2. Snapshot và run_id gắn với file tải, nguồn mất/đổi bị vô hiệu hóa. Đã kiểm chức năng bằng dữ liệu biết trước; chưa có spatial_report.json Windows để nghiệm thu 63 tỉnh thật.


## 13. Bảng dữ liệu theo quan sát

Màn Chỉ số đêm mặc định hiển thị bảng ngang tỉnh–năm/tháng, cùng thứ tự cột CSV: định danh → Raw → Processed. Chọn năm VIIRS mặc định có dòng năm và 12 dòng tháng, vẫn lọc độc lập. Băng Raw là tham chiếu ảnh, GRDP/dân số tháng là annual_reference của năm đó. Dữ liệu thiếu giữ trống, số 0 giữ nguyên. Chế độ So sánh thời gian và Biểu đồ giữ phương pháp cũ. Tham chiếu BANG_DU_LIEU_THEO_THANG.md. Việc đổi thứ tự cột không thay công thức, không thay STATS_VERSION, không cần chạy lại F/P1.
