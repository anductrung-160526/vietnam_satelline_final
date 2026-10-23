# Hướng dẫn cập nhật ảnh vệ tinh ban đêm cho các năm sau

1. **Giữ nguyên kiến trúc:** không đổi cấu trúc thư mục, quy cách đặt tên tệp, tên cột hay định dạng bảng. Dữ liệu năm mới được nối tiếp vào cùng bảng `data_processed/vietnam_district_ntl_panel_2004_2025.*`.
2. **Cập nhật hằng tháng (VIIRS):** `python run_auto_update.py --scope monthly`, hoặc để Task Scheduler tự chạy (xem `HUONG_DAN_CHAY_TU_DONG.md`, mục 5).
3. **Cập nhật hằng năm:** khi EOG phát hành bản VIIRS năm mới trên GEE, chạy `python run_auto_update.py --scope annual`. Nếu chưa có bản năm, pipeline tự ghép từ ảnh tháng và ghi nguồn vào cột `nguon_anh`. Khi bản năm chính thức có mặt, xóa checkpoint của năm đó rồi chạy lại để thay bằng bản chính thức.
4. **Hệ số hiệu chỉnh DMSP→VIIRS** lưu cố định tại `docs/hieu_chinh_dmsp_viirs.json`, nên các lần cập nhật sau không làm thay đổi chuỗi cũ. Chỉ xóa tệp này khi muốn ước lượng lại hệ số, và khi đó phải chạy lại toàn bộ 2004–2012.
5. **Nhật ký:** mọi lượt bổ sung được ghi tự động vào `logs/nhat_ky_cap_nhat.txt` theo mẫu `Ngày cập nhật | Người thực hiện | Loại ảnh (DMSP/VIIRS) | Nội dung`. Đặt tên người thực hiện bằng biến môi trường `VNGIS_USER`.
6. Sau khi cập nhật, điền biên bản `docs/BIEN_BAN_KIEM_TRA.md`.
