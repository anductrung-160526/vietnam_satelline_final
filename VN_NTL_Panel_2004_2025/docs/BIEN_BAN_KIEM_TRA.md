# Biên bản kiểm tra dữ liệu kinh tế đêm (mẫu)

**Ngày kiểm tra:** ............  **Người kiểm tra:** ............  **Phạm vi (tỉnh/năm):** ............

| STT | Tiêu chí | Chuẩn chấp nhận | Cách kiểm tra | Kết quả (Đạt/Không đạt, ghi chú) |
|:---:|---|---|---|---|
| 1 | Đủ đơn vị hành chính | Đủ số huyện của phạm vi chạy | Số `ma_huyen` duy nhất so với danh mục | |
| 2 | Đủ chuỗi thời gian | Mỗi huyện đủ các năm đã chạy | Đếm `(ma_huyen, nam)` | |
| 3 | Không trùng khóa | Không có `(ma_huyen, nam)` trùng | `df.duplicated(["ma_huyen","nam"])` | |
| 4 | Huyện có mã Cục Thống kê | Không còn huyện dùng mã GADM | `logs/` mục "Chưa có mã Cục Thống kê" | |
| 5 | Liên tục DMSP/VIIRS | Không có bước nhảy bất thường 2012→2013 | So sánh `sol_ntl` 2012, 2013; xem `docs/hieu_chinh_dmsp_viirs.json` | |
| 6 | Hợp lý của mật độ | Quận nội thành cao hơn rõ huyện miền núi | Xếp hạng `mat_do_ntl` | |
| 7 | Lỗi khi chạy | Không có tệp `logs/*_errors_*.log` (hoặc đã xử lý) | Mở thư mục `logs/` | |
| 8 | Ảnh .tif | Đủ tệp theo huyện, năm; mở được bằng QGIS | Đếm tệp, mở thử | |
