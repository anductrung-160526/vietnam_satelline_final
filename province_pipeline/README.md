# Pipeline cấp tỉnh: GitHub → Drive tạm → ổ cứng ngoài

Cấu trúc dữ liệu layout 2: hai package ở gốc; tỉnh nằm ngay dưới các thư mục ảnh/ dữ liệu theo PDF. Xem [cây thư mục và cách sắp xếp lô cũ](docs/DIRECTORY_LAYOUT.md).

Luồng mới độc lập với `run_pipeline.py` và `vngis_2024.py`. Chỉ xuất ảnh thật và thống kê phổ/ánh sáng; chưa có dashboard, phân loại đất, diện tích chuyển đổi hay chuỗi DMSP–VIIRS đã hiệu chuẩn.

## Đường đi của dữ liệu

Xác thực: dùng lại hai secret cũ **EE_SERVICE_ACCOUNT_JSON** và **RCLONE_CONF**; không cần tạo OAuth client/tải JSON mới. Xem [hướng dẫn dùng cấu hình cũ](docs/REUSE_EXISTING_SECRETS_VI.md).

1. Controller duy nhất hòa giải task Earth Engine cũ và cấp chỗ trước khi xuất.
2. Matrix 10 nhóm cố định (7/7/7/6/6/6/6/6/6/6 tỉnh) chỉ gửi công việc đã được cấp. Tổng số task chịu `max_active_exports`, không phải mỗi nhóm có quota riêng.
3. Thư mục tỉnh, ví dụ `VN_LandCover_Panel_2004_2025/raw_data/DAY/LANDSAT/01_ha_noi/2024`, được tạo trước. Không có lớp tỉnh ở ngoài package hoặc folder riêng cho mỗi job. Worker dùng EE service account lấy tile TIFF dưới giới hạn 32 MB, rồi upload bằng tài khoản Drive của rclone. Không xuất batch từ service account vào My Drive của người dùng.
4. Transfer hoàn tất → manifest có file ID, MD5, size, phiên bản, đường dẫn E → `REMOTE_READY`.
5. Agent Windows kiểm tra đúng ổ đã đăng ký → tải `.part` → kiểm tra checksum và đọc dữ liệu → rename → receipt local và Drive → mới được xóa file nguồn khi đã bật tùy chọn.
6. Khi laptop tắt, GitHub worker có thể tiếp tục lấy/upload ảnh đã đặt chỗ. Hết ngân sách Drive thì controller chờ; khi mở máy và nhận đủ dữ liệu, lịch sau tiếp tục.

Ảnh TIFF bị xóa vĩnh viễn khỏi staging sau khi nhận nếu bật cleanup. Ổ E khi đó có thể là bản duy nhất: đây là chuyển dữ liệu, không phải hai bản sao lưu. Không có lệnh xóa toàn Trash.

## Bắt đầu

Đọc [hướng dẫn thiết lập](docs/SETUP_VI.md), [phương pháp và giới hạn](docs/METHODS.md), [đối chiếu kế hoạch](docs/REQUIREMENTS_TRACEABILITY.md).

```bash
python -m pip install -r province_pipeline/requirements.txt
python -m province_pipeline --help
python -m unittest discover -s tests -v
```

Sao chép `config/example.json` thành `config/local.json` (đã gitignore). Mặc định chỉ 1 tỉnh/1 năm, pause bật và xóa tắt. Cấu hình mẫu tự tải GADM 4.1 cấp tỉnh, đối chiếu mã bằng crosswalk đã lưu và tạo metadata; không giả định GADM là địa giới pháp lý 2024. Có thể chọn bộ chính thức 2024 riêng.

```bash
python -m province_pipeline --config province_pipeline/config/local.json prepare-gadm
python -m province_pipeline --config province_pipeline/config/local.json validate
python -m province_pipeline --config province_pipeline/config/local.json inventory
```

Chỉ chạy `plan` qua workflow `Province satellite staging` có concurrency toàn workflow. Không chạy controller thứ hai từ terminal/một repo khác với cùng Drive root. Drive JSON không phải distributed lock. State, manifest và receipt lưu ở `_control`, không phụ thuộc Actions cache/artifact.

Các trạng thái `BLOCKED_AMBIGUOUS`, `BLOCKED_OUTPUT`, `FAILED` yêu cầu người vận hành xem task/files trước khi quyết định thử lại. Không có auto-reset trạng thái vì có thể làm mất dấu task còn chạy. Kỳ thiếu/partial được lưu inventory, không tự xuất như dữ liệu hoàn chỉnh. Inventory được cache theo recipe; muốn cập nhật nguồn mới, hòa giải hết task trước rồi dùng Drive UI sửa/xóa đúng entry inventory với một controller đã pause, hoặc dùng staging root mới. Không xóa state đang có task.
