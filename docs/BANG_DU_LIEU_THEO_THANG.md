# Bảng dữ liệu theo năm và từng tháng

Màn Chỉ số đêm trở lại bảng ngang phục vụ xem và xuất dữ liệu. Mỗi dòng là một tỉnh–năm hoặc tỉnh–tháng; thứ tự cột giống CSV tải từ bảng: định danh → Raw → Processed. Tiêu đề cột tiếng Anh, giải thích tiếng Việt khi xem bảng.

- Chọn tỉnh và năm VIIRS ở thanh trên: mặc định lấy một dòng năm (month=0) và 12 dòng tháng. Chọn tháng cụ thể để chỉ lấy một tháng.
- Bộ lọc bên trái vẫn chọn nhiều tỉnh, nhiều năm/tháng và chỉ số. Tick năm và tick tháng độc lập; “cả 12 tháng” không tự đổi dòng năm thành dòng tháng.
- Chế độ Bảng dùng dữ liệu theo quan sát, phân trang 100 dòng để trình duyệt không treo. Nút Tải CSV xuất toàn bộ dòng đã lọc, không chỉ trang hiện tại. Bộ lọc của CSV là đúng bộ lọc đã tạo bảng đang hiển thị.
- Chế độ So sánh thời gian giữ bảng cũ tỉnh × chỉ số, các mốc ở cột; Biểu đồ và các hàm thời gian vẫn dùng bộ tính cũ. CSV ở chế độ này giữ định dạng so sánh thời gian.
- avg_rad/cf_cvg ở bảng/CSV là tham chiếu băng Raw #band=1/#band=2, không phải trung bình pixel của tỉnh. Khi bấm tham chiếu, endpoint kiểm file và tải GeoTIFF gốc. Không gán ảnh năm median vào băng Raw.
- population, grdp_so_sanh, grdp_hien_hanh trên dòng tháng là số liệu năm tham chiếu. grdp_frequency=annual_reference ghi rõ điều đó; grdp_unit=ty_vnd là tỷ đồng. Không chia GRDP cho 12 hay suy diễn số liệu tháng.
- Ô thiếu để trống khi xuất, hiển thị dấu gạch trong bảng; giá trị 0 giữ là 0. Chọn mốc chưa có ảnh vẫn có dòng ghi MISSING_OBSERVATION, không dựng chỉ số thay thế.
- Dataset_id của từng dòng giữ xuất xứ đã lưu. Snapshot ở phản hồi dùng khóa CSV tải; không sửa nội dung/mã snapshot F hoặc P1 khi xem/xuất bảng. Đây là dữ liệu đã lưu, không phải phép quét lại tình trạng mọi ảnh nguồn trên mỗi lần xem bảng.

API bảng: /api/demo/data?province_code=01&moc=2024,2024-01,2024-02. API CSV: /api/demo/data.csv cùng tham số và expected_snapshot. Có thể thêm chi_so để lọc các trường số Processed; định danh, Raw và metadata xuất xứ vẫn đi cùng dữ liệu.

Các lần chạy calculate_ntl mới cũng xuất cột theo định danh → Raw → Processed. Chỉ đổi thứ tự cột, không đổi công thức hoặc STATS_VERSION. Không sửa tại chỗ các CSV khoa học đã kiểm F trên máy demo; tải bộ CSV đúng thứ tự từ bảng để sử dụng ngay, không cần chạy lại A–P1.

Sau git pull, mở lại uvicorn và Ctrl+F5. Không cần chạy bộ nạp hoặc tính lại ảnh.
