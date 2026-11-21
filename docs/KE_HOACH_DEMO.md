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

Tiến độ và lệnh chạy trên máy demo: [CHUAN_BI_DEMO_PHAN_A.md](CHUAN_BI_DEMO_PHAN_A.md). Đã giải thích 6 mốc bị chặn cũ: pixel giao biên, không có pixel ngoài mặt nạ all_touched trong 150 ảnh mẫu; 6 ảnh năm đạt median từng pixel. Còn xuất lại manifest/độ phủ toàn kho theo quy tắc biên đã ghi rõ.

- [x] Xác nhận repo, nhánh `night-app`, phiên bản code và Python trên máy demo. Báo cáo Windows xác nhận HEAD f7e5b18 khớp remote tại thời điểm chạy, Python 3.12.6 và đủ thư viện; lần pull sau cần đối chiếu lại phiên bản.
- [ ] Sao lưu chỉnh sửa cục bộ trước khi cập nhật; đóng tab có nội dung cũ để tránh lưu đè bản vừa kéo về.
- [ ] Lập manifest ảnh: mã tỉnh, năm, tháng, nguồn, đường dẫn, diện tích tự nhiên tỉnh.
- [x] Kiểm tra mẫu ảnh: tên băng, số băng, hệ tọa độ, kích thước pixel, NoData và hệ số scale/offset. Đã nhận báo cáo 150 mẫu trên Windows; băng phù hợp, EPSG:4326, NoData=-9999, scale=1, offset=0.
- [x] Kiểm tra ngoài ranh giới là NoData/mask, không bị điền 0 như pixel tối hợp lệ. Đã xác minh 150 mẫu theo mặt nạ all_touched: không có pixel hợp lệ hoàn toàn ngoài tỉnh; giữ cảnh báo và giới hạn diện tích ở pixel giao biên.
- [ ] Xác nhận ảnh tháng đã lọc và ảnh năm được tổng hợp ở cấp pixel; không lấy trung vị SOL tháng thay cho SOL ảnh năm.
- [x] Chuẩn hóa tên/mã 63 tỉnh, gồm cách viết TP.Hồ Chí Minh; không tự áp mã sau sáp nhập. Đã đối chiếu danh mục và hai sheet GRDP; tên ảnh còn chờ kiểm kê trên Windows.
- [ ] Lập bảng độ phủ tỉnh–năm; chọn bộ dữ liệu chính và vài tỉnh để kiểm chứng chi tiết.
- [x] Đánh dấu năm 2024 sơ bộ và các điểm GRDP cần rà soát. Đã kiểm tra file gốc; các điểm nghi ngờ được giữ số gốc và gắn cờ.

**Đạt khi:** biết chính xác ảnh nào có thể tính và GRDP nào có thể ghép; không còn đường dẫn dựa trên suy đoán.

### B. Giao diện hiển thị Raw trước Processed

- [ ] Đặt định danh tỉnh và thời gian ở đầu vùng dữ liệu.
- [ ] Nhóm Raw trước: băng ảnh đầu vào, dân số và hai loại GRDP; nhóm Processed ở sau.
- [ ] Hiển thị `avg_rad`/`cf_cvg` qua bản đồ hoặc liên kết tải ảnh; không coi mảng pixel là một giá trị số của tỉnh.
- [ ] Giữ `sol_raw`/`tnl` trong nhóm Processed vì đây là tổng tính từ pixel.
- [ ] Bổ sung lựa chọn ảnh bức xạ hoặc bản đồ năm mức sáng.
- [ ] Hiển thị chú giải màu, mốc ngưỡng, đơn vị và diện tích từng lớp.
- [ ] Đồng bộ chọn tỉnh/năm giữa các thành phần; hiển thị rõ khi đổi từ tháng sang năm.
- [ ] Bổ sung chọn cơ sở giá GRDP và chế độ đối chiếu; mặc định giá so sánh.
- [ ] Thiếu dữ liệu hiện ô trống hoặc dấu gạch cùng lý do, không tự thay bằng 0.

**Đạt khi:** cô có thể chọn một tỉnh/năm và hiểu được đầu vào, kết quả, đơn vị mà không phải đọc code.

### C. Tài liệu định nghĩa biến và công thức

- [ ] Cập nhật Data Dictionary để phản ánh đúng các trường thực sự tính/xuất/hiển thị.
- [ ] Thêm trường diện tích các mức sáng, tỷ lệ từng mức và metadata phương pháp cần thiết.
- [ ] Phân biệt dữ liệu đầu vào với tham số cấu hình và chỉ số tính toán; không xếp ngưỡng vào băng ảnh thô.
- [ ] Thống nhất tên trường tiếng Anh chữ thường; giải thích bằng tiếng Việt.
- [ ] Viết công thức, đơn vị, nguồn, cấp tỉnh và tần suất của từng trường.
- [ ] Định nghĩa rõ mẫu số: diện tích tự nhiên tỉnh, diện tích có dữ liệu hay số pixel hợp lệ.
- [ ] Nêu cách xử lý thiếu ảnh, thiếu tháng, mẫu số bằng 0 và ít quan sát sạch mây.
- [ ] Phân biệt tỷ số tăng trưởng ánh sáng/GDP với hệ số β của hồi quy GDP theo ánh sáng.
- [ ] Thống kê số biến Raw và Processed sau khi chốt danh mục; ghi rõ số này có gồm định danh hay không.
- [ ] Hoàn thiện `.docx` theo form cô yêu cầu và mở lại để kiểm tra công thức/bảng không lỗi định dạng.
- [ ] Chốt công thức NEI; nếu chưa chốt, trình bày các chỉ số thành phần, chưa gọi một công thức tự xây dựng là NEI chính thức.

**Đạt khi:** mỗi biến trên app truy được đến công thức, đơn vị và nguồn tương ứng trong tài liệu.

### D. Phân lớp sáng và diện tích

- [ ] Chốt năm khoảng: tối/không phát sáng, yếu, vừa, mạnh, rất mạnh.
- [ ] Phân biệt tối thực sự với ánh sáng bị coi là nền; ghi rõ định nghĩa được chọn.
- [ ] Mỗi pixel hợp lệ thuộc đúng một khoảng, với quy tắc biên không chồng lặp.
- [ ] Giữ ngưỡng cố định qua các năm cùng cảm biến; không chia lại theo max riêng từng năm.
- [ ] Không lấy 600/6.000 làm giới hạn mặc định khi chưa kiểm tra đơn vị ảnh thật.
- [ ] Tính diện tích từng lớp bằng tổng diện tích pixel trong lớp.
- [ ] Tính tỷ lệ từng lớp trên diện tích tự nhiên tỉnh; bổ sung độ phủ dữ liệu để giải thích phần còn thiếu.
- [ ] Giữ nguyên NoData; không gán pixel mây/thiếu ảnh vào lớp tối.
- [ ] Xuất raster phân lớp và bảng diện tích, kèm ngưỡng và phiên bản phương pháp.
- [ ] Kiểm tra tổng diện tích các lớp khớp diện tích pixel có dữ liệu, không ép bằng diện tích tự nhiên nếu ảnh thiếu.

**Đạt khi:** phân lớp có thể tái lập, tổng diện tích được kiểm tra và bản đồ sử dụng đúng bộ ngưỡng đã tính.

### E. SOL, mật độ, biến động và ghép GRDP

- [ ] Đối chiếu `sol_raw` trước loại nền và `sol` sau loại nền trên cùng ảnh/tập pixel.
- [ ] Tính `sol_density` từ tổng sáng chia diện tích tự nhiên tỉnh, ghi rõ chuỗi ánh sáng sử dụng.
- [ ] Tính `lit_area_km2`, `lit_area_pct` và tỷ lệ pixel sáng, giữ khác biệt giữa các mẫu số.
- [ ] Tính các chỉ số thời gian; phân biệt cửa sổ ba dòng quan sát của Task 3 với ba tháng lịch.
- [ ] Sửa khóa bảng kinh tế để lưu đồng thời tỉnh–năm–cơ sở giá; tránh hai bộ GRDP ghi đè nhau.
- [ ] Giữ giá hiện hành và giá so sánh năm gốc 2010, đơn vị tỷ đồng, nguồn và cờ sơ bộ.
- [ ] Sửa bộ đọc kinh tế, API và bộ xuất file để hỗ trợ hai loại giá; code hiện có chưa hỗ trợ đầy đủ yêu cầu này.
- [ ] Tính mô hình riêng theo từng cơ sở giá, dùng cùng tập tỉnh–năm khi đối chiếu.
- [ ] Dùng giá so sánh làm kết quả chính thức; giá hiện hành để đối chiếu theo yêu cầu của cô.
- [ ] Chỉ tính `sol_per_capita` khi đã có dân số hợp lệ; không suy dân số từ vùng sáng.
- [ ] Nếu dùng hiệu chỉnh DMSP–VIIRS: kiểm tra đủ cặp chồng lấn năm 2013, lưu mô hình; không tuyên bố đã sửa mốc F16–F18 năm 2010.

**Đạt khi:** hai loại giá không bị trộn, không mất dòng và kết quả có nhãn cơ sở giá rõ ràng.

### F. Nạp và xuất dữ liệu xuyên suốt app

- [ ] Rà tên trường giữa dictionary, code tính, CSV, schema SQLite và danh mục API.
- [ ] Sửa schema và tăng phiên bản schema khi đổi cấu trúc; sao lưu database trước khi dựng lại.
- [ ] Nạp chỉ số trước, sau đó cập nhật lại sổ ảnh COG nếu việc dựng lại schema đã xóa các bản ghi ảnh.
- [ ] Kiểm tra bản đồ, bảng, biểu đồ cùng lấy đúng tỉnh/năm và phiên bản kết quả.
- [ ] CSV xuất ra có tên trường, đơn vị/cơ sở giá và thông tin phương pháp đủ để đối chiếu.
- [ ] GeoTIFF tải theo tỉnh được cắt/mask đúng ranh giới; ngoài tỉnh là NoData.
- [ ] Không báo có dữ liệu trên màn hình khi file nguồn hoặc kết quả thực tế không còn.

**Đạt khi:** một giá trị được chọn có thể đối chiếu từ ảnh → CSV → SQLite → API → màn hình → file tải xuống.

## 6. Công việc P1: Moran và thay đổi không gian

### Global Moran's I cấp tỉnh

- [ ] Chọn một biến phân tích, đề xuất `sol_density`, cùng một năm trên toàn bộ 63 tỉnh.
- [ ] Chốt trọng số không gian, đề xuất quan hệ tiếp giáp ranh giới tỉnh; ghi rõ cách chuẩn hóa trọng số.
- [ ] Xử lý tỉnh không có láng giềng và tỉnh thiếu số liệu; không tự gán Moran bằng 0.
- [ ] Tính chỉ số, kiểm định hoán vị và lưu seed để tái lập; ghi số tỉnh thực tế tham gia.
- [ ] Kiểm tra trường hợp biến không có phương sai hoặc số địa bàn không đủ.
- [ ] Hiển thị kết quả theo năm, biến được dùng, phương pháp và giới hạn diễn giải.

**Giới hạn:** Moran đo tự tương quan không gian, không tự chứng minh lan tỏa kinh tế, hướng dịch chuyển hoặc quan hệ nhân quả.

### Thay đổi vùng sáng và hướng dịch chuyển

- [ ] Chọn hai năm cùng cảm biến, cùng bộ ngưỡng và quy trình tổng hợp.
- [ ] Đưa ảnh về cùng CRS, độ phân giải, lưới pixel và ranh giới.
- [ ] So sánh trên vùng có dữ liệu hợp lệ ở cả hai năm; tách riêng phần thiếu quan sát.
- [ ] Dựng bản đồ tăng/giảm sáng hoặc chuyển lớp và tính diện tích thay đổi.
- [ ] Nếu tính trọng tâm ánh sáng, ghi rõ trọng số và tính khoảng cách/hướng trong hệ tọa độ phù hợp.
- [ ] Chỉ kết luận liên hệ với đường, biển, cảng hoặc khu công nghiệp khi có lớp địa lý đối chiếu; nếu chưa có, chỉ mô tả thay đổi quan sát được.

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
