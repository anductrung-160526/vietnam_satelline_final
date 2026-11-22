# Đối chiếu kết quả thật phần D — 22/11/2026

**Kết luận: đạt kiểm tra số học/kỹ thuật trong bốn file xuất; chưa nghiệm thu độ chính xác diện tích tỉnh và tính đầy đủ của chuỗi tháng.** Báo cáo này đối chiếu CSV/JSON người dùng gửi sau lượt chạy Windows, không đọc lại TIFF trên ổ E: và không xác nhận trực tiếp nội dung SQLite trên máy demo. `passed` trong file là trạng thái kiểm chứng mã lớp/mask/tổng diện tích theo code, không phải chứng nhận chỉ số kinh tế hoặc tỷ lệ diện tích đã chính xác về địa lý.

## 1. Kết quả đã đối chiếu

| Hạng mục | Kết quả |
|---|---|
| Phạm vi | 63 tỉnh trước sáp nhập, 2020–2024 |
| Số ảnh | 4.095 = 315 ảnh năm + 3.780 ảnh tháng; không trùng khóa |
| Dùng lại ảnh cũ | 4.095 theo validation_report.json; không phải lượt phân lớp lại |
| Dòng lớp sáng | 20.475, đúng năm mã 0–4 cho mỗi khóa tỉnh–năm–tháng |
| Mẫu số diện tích tỉnh | Không thiếu; nhất quán theo tỉnh; area_source trỏ province_areas.csv phần A |
| Cận ngưỡng | Đồng nhất giữa method.json, validation_report.json và mọi dòng CSV lớp |
| Tổng diện tích năm lớp | Khớp diện tích pixel hợp lệ cho tất cả 4.095 mốc |
| Diện tích sáng | Khớp tổng lớp 2+3+4 cho mọi mốc |
| Tỷ lệ từng lớp | Khớp diện tích lớp / diện tích tỉnh × 100 và JSON class_area_pcts |
| Metadata | Khớp năm tham chiếu, phiên bản và trạng thái giữa hai CSV |
| Sai lệch tổng diện tích lớn nhất | 3,637978807091713 × 10⁻¹² km²; sai số số thực, không đáng kể |
| Trạng thái | 4.038 passed; 57 no_valid_pixels; khớp báo cáo tổng |

## 2. Ngưỡng thật của lượt chạy

| Lớp | Khoảng bức xạ, nW/cm²/sr |
|---|---|
| Tối / dưới ngưỡng nền | 0 ≤ r < 0,5 |
| Sáng yếu | 0,5 ≤ r < 1,5 |
| Sáng vừa | 1,5 ≤ r < 3,0850000381469727 |
| Sáng mạnh | 3,0850000381469727 ≤ r < 17,459999084472656 |
| Rất sáng | r ≥ 17,459999084472656 |

Khi trình bày có thể làm tròn hai ngưỡng cuối thành **3,085** và **17,46**, nhưng bộ tính vẫn dùng số đầy đủ trong method.json. Năm tham chiếu 2020; method.json ghi 147.598 pixel sáng (r≥1,5) được dùng chọn phân vị. Đây là giá trị metadata do bộ tính cung cấp; bốn file không chứa danh sách bức xạ tham chiếu để tự tính lại P50/P90 độc lập. Giữ nhãn phân loại bức xạ thực nghiệm, không gọi đây là các ngưỡng kinh tế phổ quát.

## 3. Ảnh tháng thiếu dữ liệu

Không có ảnh năm rỗng. Có **57 ảnh tháng hoàn toàn NoData**, không được coi là tỉnh tối hoặc thay bằng SOL=0.

| Tháng | Số tỉnh không có pixel hợp lệ |
|---|---:|
| 2021-08 | 1 |
| 2021-09 | 3 |
| 2022-07 | 49 |
| 2023-09 | 1 |
| 2024-06 | 1 |
| 2024-09 | 2 |

Tháng 7/2022 cả 63 tỉnh đều có dòng: 49 tỉnh rỗng, 14 tỉnh còn dữ liệu nhưng độ phủ từ 0,0039% đến 57,9790%. Kiên Giang chỉ còn 1 pixel, Lào Cai 4 pixel. Cần đối chiếu ảnh gốc, cf_cvg và điều kiện lọc tháng này; chưa đủ căn cứ để quy mọi trường hợp cho mây hay lỗi tải.

Ngoài 57 ảnh rỗng, có 22 ảnh tháng còn dữ liệu nhưng độ phủ dưới 1%, 270 ảnh tháng không rỗng có độ phủ dưới 50%. Đây là các mức mô tả để ưu tiên rà soát, chưa phải ngưỡng loại mẫu đã được chốt. Có đủ file tháng không đồng nghĩa đủ quan sát hợp lệ. Không dùng biến động SOL tháng của các mốc này như bằng chứng kinh tế nếu chưa xử lý chất lượng/độ phủ. Ảnh năm không rỗng cũng không chứng minh đủ 12 tháng tại mỗi pixel.

## 4. Sai lệch diện tích cần xử lý

Có **3.135/4.095 ảnh** có diện tích pixel hợp lệ lớn hơn diện tích tự nhiên. Riêng **315/315 ảnh năm** đều vượt 100%: thấp nhất 101,9185%, trung vị 103,3124%, cao nhất 111,3756%.

| Tỉnh | Độ phủ ảnh năm, % |
|---|---:|
| Hải Phòng | 111,3756 |
| Quảng Ninh | 109,3837 |
| Đà Nẵng | 107,5646 |
| Hà Nam | 106,4451 |
| Bắc Ninh | 106,1380 |

Tổng diện tích lớp khớp diện tích pixel hợp lệ chỉ xác nhận tính nhất quán nội bộ. Cách cộng toàn bộ pixel giao biên hiện tại và công thức diện tích xấp xỉ là các yếu tố cần đối chiếu; không tự khẳng định toàn bộ sai lệch đều do biên nếu chưa kiểm tra raster/polygon thực tế.

Có **20 mốc lit_area_pct >100%** (1 mốc năm, 19 mốc tháng), thuộc Bắc Ninh/Hưng Yên. Bắc Ninh năm 2024 là 102,5576%; Bắc Ninh tháng 1/2023 là 105,9676%, lớn nhất. Vì diện tích sáng nằm trong tỉnh phải không vượt diện tích tỉnh khi đo cùng ranh giới và cùng phương pháp, các giá trị này chưa phù hợp để công bố là tỷ lệ diện tích địa lý chính xác. Không cắt về 100% hoặc đổi mẫu số sang diện tích hợp lệ để che sai lệch.

Danh sách chi tiết 57 ảnh rỗng và 20 mốc tỷ lệ sáng trên 100%: [PHAN_D_DIEM_CAN_RA_SOAT.csv](PHAN_D_DIEM_CAN_RA_SOAT.csv), tổng 77 dòng, không bao gồm toàn bộ 3.135 mốc độ phủ vượt 100% hoặc mọi ảnh độ phủ thấp.

## 5. Công việc tiếp theo trước nghiệm thu

1. Đối chiếu trực tiếp ảnh tỉnh/ranh giới ở Bắc Ninh, Hưng Yên và Hải Phòng; kiểm tra mask, lưới pixel, CRS và diện tích mẫu số.
2. Hoàn thiện diện tích theo phần giao polygon–pixel trên hệ chiếu diện tích phù hợp, hoặc phương pháp đã được kiểm chứng tương đương; giữ bản toàn pixel để tham chiếu và mô tả rõ phiên bản. Tính lại A_k, A_valid, A_lit và các tỷ lệ cùng định nghĩa. Chưa thay đổi phương pháp hoặc kết quả hiện tại chỉ dựa vào báo cáo này.
3. Rà soát tháng 7/2022 trước, sau đó các tháng rỗng/độ phủ thấp còn lại; xác định nguyên nhân và quy tắc chất lượng. Giữ thiếu dữ liệu là thiếu, không tự nội suy/tạo số.
4. Chạy lại kiểm chứng và xem bản đồ vài tỉnh/năm, xác nhận kết quả SQLite/app; sau đó mới đánh dấu phần D nghiệm thu xong.

Có thể trình diễn giao diện bằng kết quả hiện tại với nhãn phương pháp xấp xỉ và trạng thái chất lượng; chưa diễn giải các tỷ lệ vượt 100% như tỷ lệ diện tích thực. Ưu tiên chuỗi năm cho luồng demo chính, kèm giới hạn thiếu quan sát tháng; không coi việc chọn năm là đã giải quyết sai lệch diện tích.

## 6. Dấu vết đầu vào

SHA-256 của bốn file được gửi, để nhận biết đúng lượt kết quả đã kiểm tra:

| File | SHA-256 |
|---|---|
| method.json | `53ba41e60634601fdc24a8c5999f638fe85ab0c89b0bcdc8e36015f2334fb506` |
| validation_report.json | `7cf624e8cd40caa0db71a492a69f5c2260b188823040a834fd8c8bfa93d209cb` |
| light_class_validation.csv | `2fd2314dc9fd79da27326795847b6ca1a17304cd5150a4c1d2cdc9060108ba85` |
| light_class_areas.csv | `dda683e8aab7026f4583d7be4d3645263f5c5d8a52608ae14e33a3e58aa4a366` |
