# Đối chiếu dữ liệu người dùng gửi ngày 10/10/2026

Nguồn: `day_indices.csv`, `night_indices.csv`, `progress (1).csv`, `run_20261010_0233_38017392268.log`. Đây là kết quả đối chiếu các file được gửi, không phải kiểm kê Drive trực tiếp ở thời điểm hiện tại. Không có TIFF hoặc inventory đường dẫn TIFF trong các file đính kèm.

## Tỉnh GADM 34–54

- 21 tỉnh, **238 huyện**.
- Log có đủ **12 tháng ảnh ngày + 12 tháng ảnh đêm `OK` cho từng huyện**, tổng 5.712 TIFF được xử lý trên runner.
- Kết quả xử lý cuối tìm thấy trong log: **236 huyện done**, **2 huyện partial**.
- `VNM.46.2_1` Ba Đồn / Quảng Bình: CSV ngày thiếu 2025-02.
- `VNM.48.4_1` Lý Sơn / Quảng Ngãi: CSV ngày thiếu 2024-12.
- Hai CSV được gửi có **0 dòng** của tỉnh 34–54. Người dùng xác nhận TIFF ngày/đêm của nhóm này chưa có trên Drive.
- Progress được gửi ghi cả **238 huyện pending**. Đây không phải kết quả cuối của log; không dùng nó để kết luận chưa từng xử lý ảnh hoặc đã upload đủ.

## Toàn quốc

- Mỗi CSV có **5.460 dòng = 455 huyện × 12 tháng**, thuộc 42 tỉnh.
- Thiếu hoàn toàn CSV của **255 huyện**: 238 huyện nhóm 34–54, thêm **10 huyện Kiên Giang** (`VNM.33.6_1` đến `VNM.33.15_1`) và **7 huyện Thái Bình** (`VNM.55.1_1` đến `VNM.55.7_1`).
- CSV đêm: cả 5.460 dòng `ok`. CSV ngày: 5.450 dòng `ok`, **10 dòng no_data**.
- Chỉ **445/710 huyện** có đủ 12 tháng hợp lệ ở cả hai CSV được gửi. Chưa có bằng chứng TIFF tương ứng từ hai CSV.

10 dòng CSV ngày no_data:

| GID_2 | Đơn vị / tỉnh | Tháng |
|---|---|---|
| VNM.2.3_1 | Giá Rai / Bạc Liêu | 2024-12 |
| VNM.2.4_1 | Hồng Dân / Bạc Liêu | 2024-12 |
| VNM.2.6_1 | Phước Long / Bạc Liêu | 2024-12 |
| VNM.4.4_1 | Chợ Mới / Bắc Kạn | 2025-02 |
| VNM.14.8_1 | Phục Hoà / Cao Bằng | 2025-02 |
| VNM.23.5_1 | Đồ Sơn / Hải Phòng | 2024-07 |
| VNM.23.11_1 | Lê Chân / Hải Phòng | 2024-07 |
| VNM.56.2_1 | Định Hóa / Thái Nguyên | 2025-02 |
| VNM.62.6_1 | Tam Dương / Vĩnh Phúc | 2025-02 |
| VNM.62.8_1 | Vĩnh Yên / Vĩnh Phúc | 2025-02 |

Chi tiết từng huyện: [drive_recovery_20261010.csv](drive_recovery_20261010.csv). Các cột log chỉ chứng minh xử lý trên runner. `tiff_on_drive_confirmation=user_reports_absent` ghi lại xác nhận của người dùng đối với nhóm 34–54; các tỉnh khác ghi chưa được kiểm chứng từ CSV/progress.

## Cách thực hiện phục hồi

Scope `recover_drive` đối soát toàn quốc, ưu tiên tỉnh 34–54. Giữ parts/CSV hợp lệ và TIFF có bằng chứng thực trên Drive; chỉ tải/tính lại phần thiếu. TIFF đêm có file nhưng mất checkpoint được đọc lại để kiểm tra trước khi tái sử dụng, không tự nhận done từ log. CSV ngày no_data tiếp tục tính đúng tháng, không thay bằng 0 hoặc tháng khác. CSV đêm được truy vấn từng tháng để giảm lỗi aggregation.

Request trong `.github/recovery/drive-recovery-request.txt` kích hoạt workflow khi được push lên nhánh huyện. Dùng secrets hiện có, project `vngis-ee-2`, thư mục `VNGISDash_202407_202506_Districts_50m`, 2 yêu cầu EE đồng thời. Giữ khóa concurrency cùng lượt xử lý/upload cũ để không chạy hai tiến trình ghi cùng dữ liệu. Nếu lượt cũ đang đồng bộ, lượt phục hồi sẽ chờ.

Không thể upload ảnh chỉ từ log hoặc từ CSV chỉ số. Nếu runner cũ đã bị hủy trước khi upload, ảnh cục bộ chưa lưu sẽ không có trên runner mới và phải tải bù. Nếu chạy phục hồi trên máy vẫn còn TIFF cục bộ, chúng được đồng bộ trước khi tính phần thiếu.

Progress phục hồi: `_control/progress_recovery.csv`. CSV tổng hợp được dựng lại trước mỗi đợt đồng bộ, từ mọi parts thuộc profile/kỳ chạy. Sau lượt phục hồi có báo cáo kiểm kê thực tế trong Summary và artifact `drive-recovery-audit-<run_id>`; việc workflow được kích hoạt chưa chứng minh upload hoàn tất.

## Sửa lỗi khởi tạo ở lượt #26

Log lượt `38035466846` xác nhận Earth Engine khởi tạo thành công, đã đọc 2 file trạng thái, 8 file parts và thấy 7.435 TIFF có dung lượng trên Drive. Lượt dừng trước khi import CSV vì không có manifest được xác nhận khớp. Trong đường chạy này, manifest không được đọc thành công; cấu hình khác đã bị chặn ở `init_storage`, nên nguyên nhân là thiếu manifest, không phải lỗi quota EE. Các lần Drive API giới hạn lệnh `cat` đã được backoff và vượt qua.

Bản sửa dùng metadata checkpoint cùng remote để khôi phục manifest bị thiếu khi toàn bộ checkpoint đọc được khớp kỳ/profile/cấp huyện. Không dùng log hay progress để xác nhận đã upload. CSV vẫn kiểm tra schema/metadata/tháng/chỉ số, TIFF vẫn kiểm tra bằng chứng thực có. Nếu thiếu bằng chứng hoặc manifest có cấu hình khác thì dừng.

Đồng bộ phục hồi chỉ được phép sau khi đã đọc xong cả hai CSV. Bước đồng bộ cuối của lượt lỗi khởi tạo không được dựng/ghi đè CSV từ phần parts đọc được. Workflow lưu log độc lập với audit để lỗi khởi tạo vẫn có artifact và Summary.
