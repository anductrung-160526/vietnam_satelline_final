# Hướng dẫn cập nhật ảnh vệ tinh ban ngày cho các năm sau

1. **Thời điểm:** ảnh năm N được ghép từ mùa khô 01/11/(N−1) đến 30/04/N, nên chỉ chạy năm N sau tháng 5/N. Lịch tự động hằng năm (`run_auto_update.py --scope annual`) đặt vào 15/06.
2. **Giữ nguyên kiến trúc:** không đổi thư mục, tên tệp, tên cột hay **ngưỡng phân lớp**. Nếu buộc phải đổi ngưỡng trong `pipeline_core/config.py`, phải xóa checkpoint `logs/landcover_pipeline_checkpoint.jsonl` và các bản đồ trong `data_intermediate/`, rồi chạy lại cả chuỗi để số liệu các năm nhất quán. Ghi lý do vào nhật ký.
3. **Dữ liệu tháng:** `python run_auto_update.py --scope monthly --monthly-tif` (chạy hằng tháng) bổ sung các tháng mới của năm nay và năm trước. Tháng chưa có cảnh nào được thử lại ở lần sau; chỉ khi tháng đã qua 45 ngày mà vẫn không có ảnh thì mới ghi `so_canh_anh = 0`.
4. **Diện tích chuyển đổi** của năm N cần ảnh năm N−1. Pipeline tự tính lại ảnh năm N−1 trên GEE nên không cần chạy lại năm cũ.
5. **Độ chính xác:** sau mỗi lần cập nhật, kiểm tra báo cáo `docs/BAO_CAO_DO_CHINH_XAC_<NGUON>_<NAM>.md` của năm mới. Nên bổ sung điểm mẫu có năm quan sát vào `samples/ground_truth_samples.csv` (cột `lon, lat, class`).
6. **Nhật ký:** tự ghi vào `logs/nhat_ky_cap_nhat.txt` theo mẫu `Ngày cập nhật | Người thực hiện | Loại ảnh (Landsat/Sentinel-2) | Nội dung`.
