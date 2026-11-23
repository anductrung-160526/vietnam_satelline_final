# Bảng dữ liệu theo tháng — danh mục đã thu gọn

Mỗi dòng là tỉnh–năm hoặc tỉnh–tháng. Cột từ trái sang phải: định danh → Raw → Processed. Chọn năm VIIRS để xem dòng năm và 12 tháng, hoặc tick độc lập trong bộ lọc. Tải CSV xuất toàn bộ các dòng đã lọc; bảng phân trang 100 dòng.

Bộ lọc có grdp_so_sanh, grdp_hien_hanh, min_rad, background_threshold, background_pixels, lit_threshold. GRDP chỉ có ở dòng năm; dòng tháng null. Các băng avg_rad/cf_cvg là tham chiếu file Raw. Dữ liệu thiếu giữ trống; số 0 hợp lệ giữ nguyên.

Từ điển hiện tại có 43 mục. Các trường và nhóm đã bỏ không còn trong bảng/CSV người dùng. Màn Moran chỉ hiển thị và tải year, moran_i. Danh mục này tách khỏi metadata kỹ thuật kiểm tra dữ liệu nội bộ.

Cập nhật và xóa dòng giả trên máy demo (dừng server trước):

```powershell
git pull origin night-app
python -m backend.data.purge_simulated
python -m uvicorn backend.api.main:app --reload --port 8000
```

Lệnh purge sao lưu database, chỉ xóa dòng có nhãn giả lập xác định được và in số dòng theo bảng. Nếu dùng VNGIS_DB, lệnh dùng đúng biến môi trường đó; cũng có thể chỉ định --db. Không xóa theo tỉnh/năm hay giá trị số. App cũng chặn các dòng giả trong các kết nối đọc trước khi xóa vật lý. Không cần chạy lại A–P1. Ctrl+F5 sau cập nhật.
