# Luồng 07 — dữ liệu cấp xã năm 2024

Nhánh `vngis-ee-07` dựa trên pipeline `vngis_2024.py` của main. Đây là luồng cấp xã cho năm 2024, không phải pipeline Task123 cấp tỉnh 2004–2025 của sáu nhánh `vngis-tinh-*`.

- Project thực thi: `vgis-ee-07` (đúng chính tả trong ảnh Code Editor).
- Asset dùng chung: `projects/vngis-ee-2/assets/communes_l3`. Không cần sao chép asset sang project 07.
- Mỗi lần khởi động chọn một tỉnh qua NAME_1 hoặc GID_1 của GADM 4.1. Ví dụ `Ha Noi`; tên có dấu/không dấu được hỗ trợ. Đây là địa giới bộ dữ liệu GADM, không tự chuyển theo tỉnh sau sáp nhập.
- `pilot`: mặc định 2 xã trong tỉnh được chọn. `full`: mọi xã trong tỉnh đó. Không tự phân công tỉnh giữa luồng 07 và sáu nhánh cũ: hãy chọn phạm vi chưa giao cho luồng khác nếu cần tránh tải trùng.
- Drive: `VNGISDash_2024_FLOW07_PILOT` hoặc `VNGISDash_2024_FLOW07`, gồm Day/, Night/, CSV/ và _control/. Dùng cấu hình Drive của `RCLONE_CONF` hiện có. Không ghi vào thư mục/state các luồng trước.
- Concurrency riêng cho luồng 07; pilot/full cùng luồng xếp hàng, không ghi đồng thời.

## Thiết lập quyền và secret

1. Project `vgis-ee-07` cần được đăng ký sử dụng Earth Engine, bật Earth Engine API và còn quota hợp lệ.
2. Tại repository Settings → Secrets and variables → Actions → New repository secret, thêm `EE_SERVICE_ACCOUNT_JSON_07`: toàn bộ JSON khóa service account chạy luồng 07. Không đưa khóa vào code, issue hoặc chat. Nếu dùng service account ở ảnh, kiểm tra `client_email` là `vgis-ee-07@vgis-ee-07.iam.gserviceaccount.com`.
3. Service account cần quyền Earth Engine phù hợp trên project đích (pipeline hiện dùng Earth Engine Resource Writer), cùng Service Usage Consumer, và Reader trên asset nguồn. Share cho service account hoặc quyền public Reader hiện có đều cho phép đọc; không cần Writer trên asset nguồn.
4. Giữ secret `RCLONE_CONF` hiện có với remote `gdrive` có quyền ghi Drive. Không thay secret `EE_SERVICE_ACCOUNT_JSON` của các luồng khác.

## Chạy và tiếp tục tự động

Actions → chọn workflow có file **vngis-2024.yml** → Run workflow → chọn nhánh **vngis-ee-07**. Tên workflow hiển thị có thể vẫn là tên trên main.

Nhập `province`, chọn `mode=pilot`, giữ `pilot_n=2`, `workers=2`. Kiểm tra preflight, ảnh và CSV sau lượt thử. Sau đó chọn cùng tỉnh và `mode=full`.

Mỗi lượt tối đa khoảng 5 giờ 15 phút; khi hết giờ hoặc sự cố tạm thời theo logic pipeline có sẵn, workflow gọi lượt tiếp cùng nhánh và giữ province/mode/pilot_n/workers. Trạng thái được lưu trên Drive. Không xóa _control để chạy tiếp. Pilot và full có thư mục riêng nên full không tái sử dụng đầu ra pilot.

Chọn tỉnh khác sau khi lượt trước hoàn tất; các tỉnh dùng chung root FLOW07 nhưng có thư mục cấp tỉnh và checkpoint cấp xã riêng. Không chạy thủ công một writer khác vào cùng root.

## Dừng

Tạo file `STOP` ở gốc **nhánh vngis-ee-07**, hoặc `_control/STOP` trong root Drive tương ứng. Workflow kiểm tra STOP trên đúng nhánh và không tự nối khi STOP tồn tại. Xóa STOP rồi Run workflow lại cùng tỉnh/mode để tiếp tục.

## Kiểm tra đã thực hiện

15 kiểm thử chọn tỉnh/dừng/tiếp tục và kiểm tra cú pháp Python, YAML, shell workflow đã đạt. Chưa thực hiện tải Earth Engine/Drive thực tế: cần người quản lý thêm secret 07 và kiểm tra quyền/quota trước.
