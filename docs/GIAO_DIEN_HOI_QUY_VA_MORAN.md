# Giao diện hồi quy và Moran

Màn Ảnh đêm hiển thị các cận ngưỡng với đúng hai chữ số thập phân theo định dạng Việt Nam: 0,50; 1,50; 3,09; 17,46. Chỉ định dạng hiển thị, giữ nguyên các ngưỡng đầy đủ để tính toán/phân lớp và trong dữ liệu nguồn/CSV.

Màn Chỉ số kinh tế đêm khôi phục bảng cùng biểu đồ phân tán và đường hồi quy log–log. Bộ lọc riêng gồm khoảng năm, tỉnh hoặc toàn bộ tỉnh, giá so sánh/hiện hành/đối chiếu hai giá. Mặc định toàn bộ tỉnh, 2020–2024, giá so sánh. Bảng và biểu đồ dùng chung bộ lọc; biểu đồ chỉ lấy mẫu đủ hai giá GRDP và SOL dương, cùng VIIRS và nguồn nhất quán như bộ tính backend. Mẫu dùng cho hai mô hình là giống nhau. Không vẽ đường hồi quy nếu thiếu mẫu/phương sai; không tạo số liệu để làm đầy biểu đồ.

Năm hiển thị dạng 2024, không phải 2.024,00. GRDP đơn vị tỷ đồng. Hồi quy dùng dữ liệu năm; thanh chọn tháng của màn ảnh/chỉ số không áp dụng tại màn phân tích kinh tế. Các giá trị năm vẫn được giữ null trên dòng tháng ở bảng chỉ số và CSV tháng theo yêu cầu trước. Dân số không được đưa trở lại.

Phương trình, beta, R² và n trở lại dưới dạng chú thích hồi quy, không thêm thành các cột dữ liệu hoặc tái lập nhóm Mẫu hồi quy trong Data Dictionary. Không diễn giải hệ số hồi quy là tác động nhân quả. Dữ liệu trống hoặc ít mẫu hiện lý do cụ thể.

Bỏ tab Phân tích không gian ở thanh điều hướng. Moran được gộp vào mục thu gọn Tự tương quan không gian · Moran’s I dưới bảng/biểu đồ kinh tế. Mục này chỉ giữ year và moran_i, theo các năm trong bộ lọc kinh tế; phạm vi Moran vẫn là toàn bộ các tỉnh đủ điều kiện, không phải hồi quy của tỉnh đang chọn. Chọn một năm hoặc khoảng con của bộ P1 đã có không cần tính lại Moran. Chưa có kết quả P1 bao phủ khoảng năm thì báo thiếu; không lấy kết quả năm khác thay thế.

Cập nhật bằng git pull origin night-app, mở lại server và Ctrl+F5. Không cần tính lại A–P1; không thay cấu trúc database hoặc snapshot dữ liệu.
