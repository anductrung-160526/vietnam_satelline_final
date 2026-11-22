# KẾ HOẠCH DEMO APP KINH TẾ ĐÊM

- Ngày lập: thứ Bảy, **21/11/2026**.
- Hạn demo: thứ Hai, **23/11/2026**, theo giờ Việt Nam. Chưa xác định giờ demo cụ thể.
- Nhánh thực hiện: `night-app`.
- Phạm vi: **63 tỉnh trước sáp nhập**, không mở rộng xuống huyện/xã trong đợt demo.
- Tài liệu này là danh sách công việc cần làm; các ô chưa đánh dấu chưa được coi là hoàn thành.

## 1. Mục tiêu phải trình bày được vào thứ Hai

Đi hết một luồng: **chọn tỉnh/năm → xem dữ liệu đầu vào → xem các mức sáng và diện tích → xem chỉ số, biến động → đối chiếu hai loại GRDP → tải kết quả**.

| Ưu tiên | Ý nghĩa | Hạng mục |
|---|---|---|
| P0 | Phải hoàn thành để demo app bằng dữ liệu thật | Kiểm kê dữ liệu; giao diện Raw trước Processed; phân lớp sáng; diện tích; SOL/mật độ/biến động; hai loại GRDP; tài liệu công thức; xuất dữ liệu; kiểm chứng |
| P1 | Yêu cầu phân tích không gian cần có phiên bản đầu và báo cáo đúng tình trạng | Global Moran's I; bản đồ thay đổi vùng sáng; mô tả hướng dịch chuyển có bằng chứng |
| Sau demo | Không mở rộng trong hai ngày chuẩn bị | Học máy/KNN phân lớp; Local Moran đầy đủ; mô hình dự báo nâng cao; cấp huyện/xã; viết bài báo |

**P1 không phải yêu cầu được bỏ qua.** Nếu dữ liệu hoặc kiểm chứng chưa đủ trước giờ demo, phải ghi rõ phần chưa hoàn thành, không trình bày kết quả chưa kiểm tra như kết quả chính thức.

## 2. Hiện trạng đã xác nhận và các đầu vào còn thiếu

| Nội dung | Hiện trạng | Việc tiếp theo |
|---|---|---|
| App | Có ba màn: Ảnh đêm, Chỉ số đêm, Chỉ số kinh tế đêm | Chạy thử trên chính máy dùng demo; bổ sung các điều khiển còn thiếu |
| Code tính chỉ số | Có `backend/data/calculate_ntl.py`, xuất CSV theo dictionary và bảng tương thích app | Bổ sung phân lớp nhiều mức; kiểm chứng trên ảnh thật |
| Kiểm tra code | Lần kiểm tra gần nhất có 108 test đạt trên ảnh/dữ liệu mẫu | Không coi đây là bằng chứng bộ ảnh thật đã chính xác |
| Data Dictionary | Có `docs/NIGHT_DATA_DICTIONARY.md` | Cập nhật biến lớp sáng, cơ sở giá, công thức và số lượng Raw/Processed |
| Dữ liệu ảnh | Chưa xác nhận độ phủ và đường dẫn trên máy demo trong đợt chuẩn bị này | Kiểm kê ảnh theo tỉnh/năm, CRS, NoData, băng, scale và chất lượng |
| GRDP | Đã nhận Excel `GRDP Cấp Tỉnh_So sánh vs Hiện hành.xlsx` | Chuyển về bảng dài và nạp cả hai loại giá |
| Phạm vi GRDP | 63 tỉnh, 2015–2024, tỷ đồng; giá so sánh năm gốc 2010; 2024 sơ bộ | Giữ đơn vị, cơ sở giá, nguồn và nhãn sơ bộ đi cùng dữ liệu |
| Dân số | Không có trong file GRDP đã nhận | Tìm bộ dân số theo tỉnh–năm; chưa có thì để trống chỉ số trên đầu người |
| Ngưỡng năm mức sáng | Chưa có bộ mốc số được xác nhận | Kiểm tra ảnh thật, đề xuất và xác nhận bộ ngưỡng dùng cho demo |
| NEI | Chưa chốt công thức tổng hợp riêng | Xác nhận NEI là SOL, mật độ hay công thức khác; không tự thêm trọng số |
| Form tài liệu | Chưa nhận mẫu form cụ thể trong phiên này | Lấy mẫu cô yêu cầu để trình bày Word đúng form |

### Những điểm GRDP phải đánh dấu để đối chiếu

- [ ] Bắc Giang, giá hiện hành 2015: `N/a`; để trống, không thay bằng 0 hoặc tự nội suy.
- [ ] Thừa Thiên Huế, giá so sánh 2021: tổng 33.446,7 tỷ đồng, tổng bốn thành phần 33.346,7; chênh 100 tỷ đồng.
- [ ] Hà Nội, giá so sánh: tăng khoảng 48,14% năm 2017, giảm khoảng 13,46% năm 2018; đối chiếu nguồn và tính nhất quán chuỗi.
- [ ] Giữ nguyên giá trị gốc, ghi cờ rà soát; chỉ sửa khi có căn cứ và lưu lại lý do.

## 3. Phạm vi dữ liệu dùng cho demo

- Ưu tiên **2020–2024** cho phần ghép ánh sáng–GRDP, sau khi xác nhận có đủ ảnh thật. Đây là khoảng dự kiến, chưa phải xác nhận độ phủ ảnh.
- Dùng VIIRS cho phần so sánh chính để tránh mốc đổi cảm biến DMSP–VIIRS.
- Có thể xem ảnh 2025 nếu đã có; chưa có GRDP 2025 trong Excel nên không dựng kết quả ghép kinh tế năm đó.
- Giữ chức năng tra cứu các năm khác nếu đã chạy ổn; không để xử lý toàn chuỗi lịch sử làm chậm bộ demo chính.
- Hai loại GRDP phải đối chiếu trên **cùng tập tỉnh–năm có đủ cả hai loại và ánh sáng**, không dùng hai mẫu khác nhau.
- Mọi số liệu trên màn hình phải lấy từ kết quả thật. Dữ liệu giả chỉ dùng kiểm thử và phải có nhãn riêng.

## 4. Lịch từ bây giờ đến thứ Hai

Các mốc dưới đây là thứ tự các phiên làm việc, không phải giờ cố định. Nếu bắt đầu muộn, giảm phạm vi năm/tính năng phụ theo mục 10; vẫn giữ kiểm chứng và chạy thử demo.

| Thời điểm | Công việc | Phụ thuộc | Đầu ra / điểm kiểm tra |
|---|---|---|---|
| Thứ Bảy — phiên 1 | Kiểm kê ảnh, GRDP, dân số và máy demo; chốt phạm vi năm | Truy cập được ổ dữ liệu | Danh sách ảnh thật; bảng GRDP chuẩn hóa; danh sách dữ liệu còn thiếu |
| Thứ Bảy — phiên 2 | Hoàn thiện bố cục giao diện và luồng demo, Raw trước Processed | Biết các nhóm dữ liệu | Ba màn có điều khiển phù hợp và trạng thái thiếu dữ liệu rõ ràng |
| Thứ Bảy — phiên 3 | Chốt ngưỡng/công thức; cập nhật dictionary và khung Word | Phân bố giá trị ảnh, form cô yêu cầu | Bảng ngưỡng có phiên bản; tài liệu định nghĩa biến |
| Thứ Bảy — phiên 4 | Sửa cấu trúc hai loại GRDP; viết tính lớp sáng và diện tích | Ngưỡng và cấu trúc dữ liệu đã chốt | Bộ tính chạy được trên một tỉnh và ít nhất hai năm |
| Chủ nhật — phiên 1 | Kiểm chứng trên các tỉnh khác nhau, rồi chạy bộ dữ liệu demo | Bộ tính vượt kiểm tra ảnh mẫu và ảnh thật | CSV, raster lớp sáng, nhật ký tính và bảng đối chiếu |
| Chủ nhật — phiên 2 | Nạp SQLite, nối API, hoàn thiện bản đồ/bảng/biểu đồ/xuất file | Kết quả tính đã kiểm tra | Luồng chọn tỉnh/năm chạy xuyên suốt |
| Chủ nhật — phiên 3 | Tính Global Moran, dựng bản đồ thay đổi; hoàn thiện Word | Đủ dữ liệu không gian và chuỗi so sánh | Kết quả P1 có phương pháp, kiểm định và giới hạn rõ ràng |
| Tối Chủ nhật | Chạy thử kịch bản, sửa lỗi chặn demo, chốt phiên bản và sao lưu | Luồng chính hoạt động | Bộ demo có thể mở lại từ đầu trên máy trình bày |
| Thứ Hai — trước giờ demo | Kiểm tra khởi động, đường dẫn ảnh, tải CSV/TIF và mở Word | Phiên bản đã chốt | Sẵn sàng trình bày; không thêm tính năng lớn |

## 5. Danh sách công việc P0 chi tiết

### A. Chuẩn bị dữ liệu và môi trường

Tiến độ và lệnh chạy trên máy demo: [CHUAN_BI_DEMO_PHAN_A.md](CHUAN_BI_DEMO_PHAN_A.md). Báo cáo GLOBAL_SCAN trên Windows lúc 22:48 ngày 21/11 xác nhận không còn blocker: 4.095 ứng viên (315 ảnh năm + 3.780 ảnh tháng), đủ 315/315 tỉnh–năm 2020–2024. Đã có thể chuyển sang phần B và các bước tích hợp; kết quả này là mức sẵn sàng đầu vào demo, chưa thay thế kiểm chứng số liệu toàn bộ.

- [x] Xác nhận repo, nhánh `night-app`, phiên bản code và Python trên máy demo. Báo cáo Windows xác nhận HEAD d303ff0 khớp remote tại thời điểm chạy, Python 3.12.6 và đủ thư viện; lần pull sau cần đối chiếu lại phiên bản.
- [ ] Sao lưu chỉnh sửa cục bộ trước khi cập nhật; đóng tab có nội dung cũ để tránh lưu đè bản vừa kéo về. Báo cáo đã tạo git_backup, không có tracked changes; province_pipeline/ untracked chưa sao lưu và trạng thái tab IDE còn cần người dùng xác nhận.
- [x] Lập manifest ảnh: mã tỉnh, năm, tháng, nguồn, đường dẫn, diện tích tự nhiên tỉnh. Lần chạy toàn kho mới đã xuất 4.095 ứng viên trong manifest_candidates.csv; dùng đúng bộ kết quả 20261121_224811_221282, giữ nhãn ứng viên trước kiểm chứng chỉ số chính thức.
- [x] Kiểm tra mẫu ảnh: tên băng, số băng, hệ tọa độ, kích thước pixel, NoData và hệ số scale/offset. Đã nhận báo cáo 150 mẫu trên Windows; băng phù hợp, EPSG:4326, NoData=-9999, scale=1, offset=0.
- [x] Kiểm tra ngoài ranh giới là NoData/mask, không bị điền 0 như pixel tối hợp lệ. Đã xác minh 150 mẫu theo mặt nạ all_touched: không có pixel hợp lệ hoàn toàn ngoài tỉnh; giữ cảnh báo và giới hạn diện tích ở pixel giao biên.
- [x] Xác nhận ở mức kiểm tra chuẩn bị: 72 ảnh tháng lọc mẫu có FILTER đúng quy trình, không còn số âm; 6 ảnh năm mẫu khớp median từng pixel. Chưa tái tính toàn bộ bộ lọc từ ảnh thô hoặc kiểm tra từng pixel của toàn kho.
- [x] Chuẩn hóa tên/mã 63 tỉnh, gồm cách viết TP.Hồ Chí Minh; không tự áp mã sau sáp nhập. Đã đối chiếu danh mục, hai sheet GRDP và độ phủ đủ 63 mã tỉnh trên Windows.
- [x] Lập bảng độ phủ tỉnh–năm; chọn bộ chính 2020–2024: 63 tỉnh × 5 năm, mỗi mốc có 1 ứng viên ảnh năm và 12 ứng viên ảnh tháng. Nhóm kiểm chứng sâu: Hà Nội, Bắc Ninh, Lào Cai tại 2020 và 2024.
- [x] Đánh dấu năm 2024 sơ bộ và các điểm GRDP cần rà soát. Đã kiểm tra file gốc; các điểm nghi ngờ được giữ số gốc và gắn cờ.

**Đạt khi:** biết chính xác ảnh nào có thể tính và GRDP nào có thể ghép; không còn đường dẫn dựa trên suy đoán.

### B. Giao diện hiển thị Raw trước Processed

Đã triển khai và thử trên trình duyệt bằng ảnh kiểm thử. Lệnh nạp ảnh thật/GRDP và căn cứ ngưỡng: [GIAO_DIEN_DEMO_PHAN_B.md](GIAO_DIEN_DEMO_PHAN_B.md). Các dấu hoàn thành dưới đây xác nhận chức năng đã làm, chưa thay thế bước nghiệm thu trên máy Windows với dữ liệu thật.

- [x] Đặt định danh tỉnh và thời gian ở đầu vùng dữ liệu.
- [x] Nhóm Raw trước: băng ảnh đầu vào, dân số và hai loại GRDP; nhóm Processed ở sau.
- [x] Hiển thị `avg_rad`/`cf_cvg` qua bản đồ hoặc liên kết tải ảnh; không coi mảng pixel là một giá trị số của tỉnh.
- [x] Giữ `sol_raw`/`tnl` trong nhóm Processed vì đây là tổng tính từ pixel.
- [x] Bổ sung lựa chọn ảnh bức xạ hoặc bản đồ năm mức sáng.
- [x] Hiển thị chú giải màu, mốc ngưỡng, đơn vị và diện tích từng lớp.
- [x] Đồng bộ chọn tỉnh/năm giữa các thành phần; hiển thị rõ khi đổi từ tháng sang năm.
- [x] Bổ sung chọn cơ sở giá GRDP và chế độ đối chiếu; mặc định giá so sánh.
- [x] Thiếu dữ liệu hiện ô trống hoặc dấu gạch cùng lý do, không tự thay bằng 0.

**Đạt khi:** cô có thể chọn một tỉnh/năm và hiểu được đầu vào, kết quả, đơn vị mà không phải đọc code.

### C. Tài liệu định nghĩa biến và công thức

Đã tạo [bản Word](DINH_NGHIA_BIEN_VA_CONG_THUC_DEMO.docx) và [nguồn giải thích/công thức](DINH_NGHIA_BIEN_VA_CONG_THUC_DEMO.md). Sau phần P1, danh mục có 117 mục: 16 Raw (gồm 5 định danh) và 101 Processed. Ba công thức diện tích/độ phủ trước đây ở mức đề xuất đã triển khai ở phần D. Đây là số mục từ điển gồm metadata/tham số, không phải 117 biến độc lập hoặc 117 cột đã có trong một file.

- [x] Cập nhật Data Dictionary theo code tính, bộ nạp, SQLite và API; ghi rõ khác biệt CSV/app, trường thiếu dữ liệu và công thức chưa có đầu ra.
- [x] Định nghĩa diện tích từng lớp, tỷ lệ và metadata ngưỡng; đã cập nhật tỷ lệ lớp/độ phủ theo đầu ra phần D.
- [x] Phân biệt dữ liệu đầu vào với tham số cấu hình và chỉ số tính toán; không xếp ngưỡng vào băng ảnh thô.
- [x] Thống nhất tên trường tiếng Anh chữ thường; giải thích bằng tiếng Việt.
- [x] Viết công thức, đơn vị, nguồn, cấp tỉnh và tần suất của từng trường.
- [x] Định nghĩa rõ mẫu số: diện tích tự nhiên tỉnh, diện tích có dữ liệu và số pixel hợp lệ.
- [x] Nêu cách xử lý thiếu ảnh, thiếu tháng, mẫu số bằng 0 và ít quan sát sạch mây.
- [x] Phân biệt tỷ số tăng trưởng ánh sáng/GRDP với hệ số β của hồi quy GRDP theo ánh sáng.
- [x] Thống kê số mục Raw và Processed; tách định danh và mục đề xuất, không cộng trùng khóa ở hai CSV.
- [x] Tạo `.docx` bản làm việc, mở lại và render để kiểm tra bảng/công thức; đã cập nhật theo trường/công thức phần E. Có script sinh lại từ Markdown.
- [ ] Xác nhận/chỉnh Word theo form cô yêu cầu sau khi nhận được form; chưa coi bản làm việc là đã đúng biểu mẫu.
- [ ] Chốt công thức NEI tổng hợp với cô. Hiện tài liệu trình bày các chỉ số thành phần, không tự gán trọng số hay gọi SOL/β là NEI chính thức.

**Đạt khi:** mỗi biến trên app truy được đến công thức, đơn vị và nguồn tương ứng trong tài liệu.

### D. Phân lớp sáng và diện tích

Đã triển khai và kiểm tra code/API/giao diện bằng ảnh biết trước. Lệnh chạy và ý nghĩa báo cáo: [PHAN_LOP_SANG_PHAN_D.md](PHAN_LOP_SANG_PHAN_D.md). Các dấu dưới đây là tiến độ thực hiện chức năng, chưa phải nghiệm thu 4.095 ảnh thật trên Windows.

- [x] Chốt quy tắc năm khoảng cho demo: 0,5; 1,5; P50/P90 pixel sáng năm 2020. Giá trị thật P50/P90 phải lấy từ method.json; không dùng mốc ảnh kiểm thử.
- [x] Phân biệt tối thực sự với dưới ngưỡng nền; ghi rõ chưa suy diễn lớp bức xạ thành mức kinh tế/loại đất.
- [x] Mỗi pixel hợp lệ thuộc đúng một khoảng; bằng ngưỡng thuộc lớp cao hơn; kiểm chứng lại từ bức xạ nguồn.
- [x] Giữ ngưỡng cố định qua các năm/tháng VIIRS; không fit lại theo max từng ảnh.
- [x] Không dùng 600/6.000 làm giới hạn mặc định; cận trên lớp rất sáng không hữu hạn.
- [x] Tính diện tích từng lớp theo lưới/vĩ độ; không dùng 0,25 km²/pixel cố định.
- [x] Tính và lưu tỷ lệ từng lớp trên diện tích tự nhiên, diện tích hợp lệ và độ phủ; thiếu mẫu số thì để trống tỷ lệ và báo cờ.
- [x] Giữ NoData=255, kiểm tra mask với ảnh nguồn; toàn NoData có trạng thái riêng, không coi là tối.
- [x] Xuất COG, CSV diện tích, CSV/JSON kiểm chứng, ngưỡng và phiên bản; API tải CSV đúng tỉnh/mốc đang chọn.
- [x] Kiểm tra tổng diện tích lớp với diện tích hợp lệ; giữ số/cờ khi độ phủ trên 100% do pixel giao biên.
- [x] Đã nhận đủ bốn file kết quả Windows ngày 22/11, đối chiếu đủ 4.095 khóa và 20.475 dòng lớp; tổng lớp, tỷ lệ và metadata khớp. Ngưỡng thật: 0,5; 1,5; 3,0850000381469727; 17,459999084472656. Báo cáo: [DOI_CHIEU_KET_QUA_PHAN_D.md](DOI_CHIEU_KET_QUA_PHAN_D.md).
- [x] Đã triển khai v9: diện tích phần giao EPSG:6933, đối chiếu/sửa tháng theo raw và FILTER, bản đồ số tháng hợp lệ, database tạm trước xuất bản; lệnh chạy: [SUA_DIEN_TICH_VA_THANG_THIEU.md](SUA_DIEN_TICH_VA_THANG_THIEU.md).
- [x] Đã chạy v9 trên Windows và nhận fix_report.json: 4.095 ảnh, coverage_above_100=0, không thiếu mẫu số, sai lệch tổng lớp tối đa 7,28×10⁻¹² km²; published=true. 3.723 tháng khớp FILTER và 57 tháng raw không có quan sát sạch mây hợp lệ, không có ảnh cần sửa pixel. [Kết quả sau sửa v9](KET_QUA_SAU_SUA_V9.md).
- [ ] Đối chiếu vài dòng CSV/ảnh/bản đồ Windows sau sửa và báo cáo số tháng hợp lệ theo pixel; giữ 57 tháng thiếu là thiếu dữ liệu nguồn, không tự lấp hoặc coi bằng 0.

**Đạt khi:** phân lớp có thể tái lập, tổng diện tích được kiểm tra và bản đồ sử dụng đúng bộ ngưỡng đã tính.

### E. SOL, mật độ, biến động và ghép GRDP

Đã hoàn thiện code, kiểm tra CSV→SQLite→API và nhận báo cáo chạy dữ liệu thật v9: hai mô hình khớp trên chung 315 cặp, diện tích dùng phần giao EPSG:6933, kết quả đã nạp app. Hướng dẫn: [TINH_CHI_SO_VA_GRDP_PHAN_E.md](TINH_CHI_SO_VA_GRDP_PHAN_E.md), [kết quả sau sửa](KET_QUA_SAU_SUA_V9.md). 57 tháng raw thiếu quan sát được giữ thiếu; cần kiểm tra hệ số thật và báo cáo độ đầy đủ năm.

- [x] Đối chiếu `sol_raw` và `sol` trên cùng đầu vào, kiểm tra không âm và sol không vượt sol_raw trong luồng hai giá.
- [x] Tính `sol_density` theo diện tích tự nhiên; ghi light_basis và model_light_basis rõ.
- [x] Giữ công thức/mẫu số riêng cho diện tích sáng, tỷ lệ diện tích và tỷ lệ pixel; mang cờ xấp xỉ/tỷ lệ vượt 100% sang CSV/app, chưa nghiệm thu địa lý.
- [x] Tính chuỗi thời gian riêng cho ba dòng tháng và ba tháng lịch; không tạo tăng trưởng từ tháng/giá trị tham chiếu thiếu. Bộ tính v8 chặn tăng trưởng năm 2010.
- [x] Khóa economy_prices và demo_result giữ đồng thời hai giá; CSV trùng khóa bị từ chối.
- [x] Giữ đơn vị tỷ đồng, năm gốc 2010, nguồn, sơ bộ và cờ rà soát; thiếu GRDP vẫn giữ ô trống.
- [x] Bổ sung --economy-prices cho bộ tính CSV hai giá, API và CSV tải theo cơ sở giá; luồng --economy một giá cũ vẫn dùng được.
- [x] Khớp hai mô hình VIIRS năm trên chung mẫu dương ≥10 điểm, loại GIA_LAP; xuất thời kỳ/n/β theo từng mô hình.
- [x] Mặc định giá so sánh, hiện hành dùng đối chiếu; tăng trưởng GRDP/tỷ số tăng trưởng/ước lượng được tính riêng từng giá.
- [x] Chỉ tính `sol_per_capita` năm khi có dân số dương; không tạo dân số. GRDP tháng chỉ là tham chiếu năm.
- [x] Giữ điều kiện hiệu chỉnh ≥30 cặp dương DMSP/VIIRS 2013 và lưu mô hình; không bật cho demo chỉ VIIRS và không sửa mốc F16/F18 2010.
- [x] Đã nhận tóm tắt E trong fix_report.json: 1.260 dòng giá, 8.820 dòng kết quả, hai mô hình trên cùng 315 cặp, 4.095 ảnh có liên kết báo cáo chất lượng, STATS_VERSION=9; đã nạp 315 dòng năm và 3.780 dòng tháng.
- [ ] Nhận calculation_models.csv và vài dòng night_economy.csv để đối chiếu α/β/R², số liệu/đơn vị/cơ sở giá thực tế; báo cáo tổng không chứa các hệ số này. Dân số vẫn thiếu, chỉ số đầu người giữ trống.

**Đạt khi:** hai loại giá không bị trộn, không mất dòng và kết quả có nhãn cơ sở giá rõ ràng.

### F. Nạp và xuất dữ liệu xuyên suốt app

Đã triển khai bộ kiểm chứng và metadata snapshot; hướng dẫn: [PHAN_F_KIEM_CHUNG_VA_XUAT_DU_LIEU.md](PHAN_F_KIEM_CHUNG_VA_XUAT_DU_LIEU.md). Các dấu dưới đây xác nhận code/kiểm thử, còn nghiệm thu kho Windows mở ở mục cuối.

- [x] Kiểm trường Dictionary/CSV/API; xuất field_contract.csv, giữ đúng alias SQL/JSON, phân biệt tham chiếu Raw và filtered.
- [x] Thêm schema demo v2 bằng migration cộng thêm, backup trước xuất bản; base schema v8 không bị reset, số liệu và COG giữ nguyên.
- [x] Nạp chỉ số và xuất xứ vào cùng transaction; không dựng lại schema rồi làm mất sổ ảnh. Từ chối CSV khác dataset_manifest/trùng khóa hoặc schema mới hơn code.
- [x] Kiểm từng dòng CSV/SQLite, thống kê từ ảnh và mô hình; các màn nhận X-Snapshot-ID và yêu cầu tải lại nếu bộ dữ liệu đổi giữa lần đọc.
- [x] CSV chỉ số/kinh tế/lớp có đơn vị, mốc, cơ sở giá, chuỗi ánh sáng, dataset_id/stats_version và hash nguồn; link tải gắn expected_snapshot để chặn nhầm lượt.
- [x] Quét GeoTIFF theo mốc manifest, tạo bản crop/mask riêng khi cần; kiểm lại ngoài tỉnh là NoData, giữ 0 hợp lệ và pixel giao biên dương; nguồn không đổi.
- [x] Kiểm tồn tại/chữ ký nguồn và bản xuất; API báo không sẵn có/410 khi đổi hoặc mất, không dùng số không nhất quán vào mẫu mô hình.
- [x] Đã nhận integration_report.json Windows: published=true, 12.285 ảnh, 0 pixel hợp lệ hoàn toàn ngoài tỉnh, 0 bản cần sửa mask; đối chiếu 315 dòng năm, 3.780 tháng, 4.095 Night Data và 8.820 Night Economy. Snapshot 8f7799734c1d…; stats v9/schema v2.
- [ ] Nghiệm thu màn hình sau bản sửa cache/snapshot 63868bc; đối chiếu vài tỉnh/năm app/CSV/TIFF và xem mask trong QGIS trước demo.

**Đạt khi:** một giá trị được chọn có thể đối chiếu từ ảnh → CSV → SQLite → API → màn hình → file tải xuống.

## 6. Công việc P1: Moran và thay đổi không gian

Đã triển khai code/API/màn phân tích và kiểm thử ảnh biết trước. Hướng dẫn và căn cứ phương pháp: [PHAN_P1_PHAN_TICH_KHONG_GIAN.md](PHAN_P1_PHAN_TICH_KHONG_GIAN.md). Các dấu hoàn thành xác nhận chức năng; kết quả 63 tỉnh thật cần lượt chạy Windows.

### Global Moran's I cấp tỉnh

- [x] Chọn một biến phân tích, dùng `sol_density` chưa hiệu chỉnh của ntl_annual, cùng một năm trên toàn bộ 63 tỉnh.
- [x] Chốt trọng số không gian, Queen trên polygon EPSG:6933 với dung sai 1 m và chuẩn hóa hàng sau loại thiếu/cô lập; ghi rõ cách chuẩn hóa trọng số.
- [x] Xử lý tỉnh không có láng giềng và tỉnh thiếu số liệu; không tự gán Moran bằng 0.
- [x] Tính chỉ số, kiểm định hoán vị và lưu seed để tái lập; ghi số tỉnh thực tế tham gia.
- [x] Kiểm tra trường hợp biến không có phương sai hoặc số địa bàn không đủ.
- [x] Hiển thị kết quả theo năm, biến được dùng, phương pháp và giới hạn diễn giải.

**Giới hạn:** Moran đo tự tương quan không gian, không tự chứng minh lan tỏa kinh tế, hướng dịch chuyển hoặc quan hệ nhân quả.

### Thay đổi vùng sáng và hướng dịch chuyển

- [x] Chọn hai năm cùng cảm biến, cùng bộ ngưỡng và quy trình tổng hợp.
- [x] Đưa ảnh về cùng CRS, độ phân giải, lưới pixel và ranh giới.
- [x] So sánh trên vùng có dữ liệu hợp lệ ở cả hai năm; tách riêng phần thiếu quan sát.
- [x] Dựng bản đồ tăng/giảm sáng hoặc chuyển lớp và tính diện tích thay đổi.
- [x] Nếu tính trọng tâm ánh sáng, ghi rõ trọng số và tính khoảng cách/hướng trong hệ tọa độ phù hợp.
- [x] Chỉ kết luận liên hệ với đường, biển, cảng hoặc khu công nghiệp khi có lớp địa lý đối chiếu; nếu chưa có, chỉ mô tả thay đổi quan sát được.

- [ ] Chạy build_spatial trên Windows, gửi spatial_report.json; kiểm n/63, diện tích miền chung/thiếu, raster và hướng trọng tâm ở vài tỉnh trước demo.

## 7. Kiểm chứng số liệu trước khi chốt demo

Chọn vài tỉnh có đặc điểm khác nhau, ví dụ tỉnh đô thị lớn, tỉnh công nghiệp và tỉnh miền núi/nông nghiệp. Không chỉ kiểm trên một tỉnh thuận lợi.

- [ ] Tự tính trên một raster nhỏ biết trước giá trị để kiểm tra biên ngưỡng, tổng, diện tích và tỷ lệ.
- [ ] Kiểm tra ảnh thật của ít nhất ba tỉnh và hai năm trong phạm vi demo, nếu đầu vào đủ.
- [ ] Đối chiếu số pixel có dữ liệu, vùng ngoài tỉnh và NoData trên bản đồ.
- [ ] Tính lại độc lập một số tổng và diện tích để so với CSV, ghi sai số cho phép theo đơn vị/độ chính xác.
- [ ] Kiểm tra `tnl = sol_raw` khi cùng ảnh và cùng tập pixel; giải thích phần chênh `sol_raw − sol`.
- [ ] Kiểm tra tổng diện tích lớp, tỷ lệ và diện tích tự nhiên tỉnh.
- [ ] Kiểm tra cả hai cơ sở giá, dòng Bắc Giang thiếu số và năm 2024 sơ bộ.
- [ ] Kiểm tra công thức tăng trưởng và hồi quy trên dữ liệu có kết quả biết trước.
- [ ] Lập bảng kiểm chứng gồm: tỉnh, năm, chỉ số, kết quả độc lập, kết quả code, sai lệch, kết luận.
- [ ] Chạy các test liên quan sau thay đổi và kiểm tra giao diện bằng trình duyệt thật.

## 8. Đóng gói và chạy thử demo

- [ ] Ghi commit dùng demo và đường dẫn dữ liệu; không phụ thuộc file còn nằm trên máy khác.
- [ ] Chuẩn bị database, COG, raster phân lớp và GeoJSON ranh giới trên máy demo.
- [ ] Khởi động lại app từ đầu theo đúng lệnh sẽ dùng thứ Hai.
- [ ] Thử khi không tải thêm dữ liệu từ Internet; xác định rõ chức năng nào còn phụ thuộc mạng.
- [ ] Chạy thử chọn tỉnh, đổi năm, bật lớp, xem bảng/biểu đồ và tải file.
- [ ] Chuẩn bị Word định nghĩa biến, bảng kiểm chứng và danh sách hạn chế còn lại.
- [ ] Sao lưu bộ demo riêng; lưu ảnh chụp/video luồng đã kiểm tra để trình bày dự phòng nếu lỗi máy.
- [ ] Tối Chủ nhật chốt phiên bản; sáng thứ Hai chỉ sửa lỗi chặn demo và kiểm tra lại phần bị ảnh hưởng.

## 9. Kịch bản trình bày

| Bước | Thao tác | Điều cần giải thích |
|---|---|---|
| 1 | Chọn một tỉnh và năm có đủ dữ liệu | Phạm vi 63 tỉnh trước sáp nhập, nguồn và chất lượng ảnh |
| 2 | Xem Raw rồi Processed | Phân biệt băng pixel đầu vào với số thống kê của cả tỉnh |
| 3 | Bật năm lớp sáng | Ngưỡng, màu và diện tích từng mức; NoData không phải vùng tối |
| 4 | Xem SOL, diện tích sáng và mật độ | Ba đại lượng khác nhau, công thức và đơn vị tương ứng |
| 5 | Chuyển năm hoặc xem bản đồ thay đổi | Thay đổi theo thời gian, giới hạn do chất lượng quan sát |
| 6 | Xem GRDP hiện hành và so sánh | Cùng mẫu đối chiếu, giá so sánh là kết quả chính thức, 2024 sơ bộ |
| 7 | Xem Moran nếu đã kiểm chứng | Tự tương quan không gian, không kết luận nhân quả/lan tỏa chỉ từ một con số |
| 8 | Tải CSV/GeoTIFF và mở tài liệu | Kết quả khớp màn hình, có công thức và có khả năng tái lập |

## 10. Xử lý khi thiếu thời gian hoặc thiếu đầu vào

| Vướng mắc | Cách xử lý |
|---|---|
| Chưa đủ ảnh 2020–2024 | Dùng khoảng năm thực sự có đủ; công bố độ phủ, không tạo số giả để đủ bảng |
| Ngưỡng chưa được cô xác nhận | Dùng cấu hình đề xuất có nhãn tạm thời để trình diễn, không gọi là phân lớp đã được xác nhận |
| Chưa có dân số | Để trống chỉ số trên đầu người, vẫn demo phần ánh sáng và GRDP |
| Điểm GRDP chưa đối chiếu xong | Giữ số gốc và cờ rà soát; công bố cách đưa vào/loại khỏi mẫu, không chọn lọc âm thầm |
| Chưa đủ dữ liệu toàn quốc cho Moran | Nêu chưa hoàn thành; không tính trên vài tỉnh rồi trình bày như kết quả 63 tỉnh |
| Thiếu lớp đường/biển/khu công nghiệp | Chỉ trình bày bản đồ thay đổi và hướng quan sát được; chưa khẳng định nguyên nhân |
| Công thức NEI chưa chốt | Trình bày chỉ số thành phần và mục cần thống nhất với cô |
| App lỗi sát giờ | Dùng bộ dữ liệu/phiên bản đã sao lưu và bản trình bày dự phòng; ghi đúng tình trạng phần chưa chạy được |

## 11. Điều kiện chốt sẵn sàng demo

- [ ] Máy demo mở được app từ đầu và đi hết luồng trình bày.
- [ ] Raw trước Processed; thông tin tỉnh, năm, nguồn và cơ sở giá rõ ràng.
- [ ] Lớp sáng và diện tích đã qua kiểm tra, ngưỡng có phiên bản và trạng thái xác nhận.
- [ ] Giá trị trên màn hình khớp dữ liệu tải xuống.
- [ ] Hai loại GRDP cùng tồn tại, cùng mẫu đối chiếu và không ghi đè nhau.
- [ ] Không còn số giả hoặc giá trị 0 thay cho dữ liệu thiếu trong kết quả demo thật.
- [ ] Tài liệu Word và bảng kiểm chứng mở được, khớp với code và dữ liệu.
- [ ] Moran/phân tích hướng có kết quả đã kiểm chứng hoặc có ghi rõ phần chưa hoàn thành.
- [ ] Có bản sao lưu và danh sách vấn đề cần cô xác nhận sau demo.
