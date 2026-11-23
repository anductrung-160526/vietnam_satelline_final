# Khôi phục dữ liệu GRDP, sổ ảnh và P1

Ảnh/bảng sáng vẫn có số nhưng GRDP trống, sổ ảnh không có và P1 báo chưa nạp thường xảy ra khi app mở một database khác hoặc database từng bị dựng lại từ CSV chỉ số. Báo cáo F/P1 đã published trước đó không chứng minh app hiện tại vẫn đang mở chính file đó.

Đã sửa hai vấn đề:

- build_indices.mo trước đây unlink database khi PRAGMA user_version đổi. Nay backup rồi chỉ thêm bảng/cột thiếu; không xóa bảng mở rộng F/P1 hoặc sổ ảnh. build_indices từ chối nạp đè CSV cũ lên database đang có snapshot F/P1.
- Thanh thời gian ảnh đọc được demo_asset của tỉnh đã nạp; không yêu cầu tạo COG toàn quốc khi ảnh tỉnh đã có.
- GRDP có thể nằm trong economy_prices, economy.grdp theo nhãn giá, hoặc hai cột grdp_so_sanh/grdp_hien_hanh cũ. Bộ đọc nay dùng chung ở bảng/CSV/màn kinh tế và hỗ trợ cả các vị trí đó. Không lấy một giá gán thành giá còn lại. Dân số/GRDP dòng tháng vẫn null.

## Lệnh trên máy demo

Dừng uvicorn bằng Ctrl+C. Chạy từ thư mục repo:

```powershell
git pull origin night-app
python -m backend.data.recover_demo --root "E:\SatelliteData" --publish
python -m uvicorn backend.api.main:app --reload --port 8000
```

Ctrl+F5. Lệnh recover tìm lượt P1 published mới nhất trong _demo_spatial; kiểm candidate.db khớp snapshot/report, CSV còn hợp lệ, ảnh nguồn và file kết quả không bị mất/đổi; sau đó clone và migration trên file riêng, dọn dòng giả có nhãn, kiểm các thành phần rồi mới backup/cập nhật database app. Không chạy tính lại ảnh, phân lớp hoặc mô hình.

Có thể chỉ định chính xác lượt đã gửi:

```powershell
python -m backend.data.recover_demo --root "E:\SatelliteData" --spatial-report "E:\SatelliteData\_demo_spatial\20261123_001247_214509\spatial_report.json" --publish
```

Không có --publish thì chỉ tạo candidate và báo cáo để xem. Nếu dùng VNGIS_DB, lệnh dùng biến đó; có thể truyền --db. Không tự đổi database khác với đường dẫn app đang dùng. Source candidate được giữ nguyên. Nếu file/nguồn không khớp, lệnh dừng trước khi cập nhật app; không sửa hash hoặc tạo ảnh/số liệu thay thế. Bản backup giữ database đang dùng trước phục hồi.

Kết quả: E:\SatelliteData\_demo_recovery\<lượt chạy>\recovery_report.json. Gửi file này để đối chiếu đường dẫn thật, số dòng trước/sau, nguồn phục hồi và trạng thái published.

## Kiểm tra đúng database

Mở http://127.0.0.1:8000/api/demo/status hoặc /api/health (data_status). Nội dung có đường dẫn database, schema, số dòng bảng, số giá trị GRDP/dân số thật và thành phần chưa nạp. Đây là chẩn đoán kỹ thuật, không thêm lại các cột đã bỏ khỏi bảng dữ liệu.

Với bộ đã xác nhận F/P1 trước đó, cần có economy_prices, demo_asset, light_class và spatial_run cùng snapshot. Chỉ số NTL có số chưa đủ để kết luận các màn đã nạp đủ. Sau phục hồi, chọn Hà Nội/năm 2024 kiểm hai loại GRDP; xem ảnh và lớp sáng; mở Moran 2020–2024. Không chạy build_cogs/build_indices chỉ vì UI báo thiếu sổ ảnh nếu các ảnh đã có trước đó.

## Dân số

File Excel GRDP đã nhận trước đây không có dân số. Báo cáo E trước đó cũng xác nhận population_missing. Việc phục hồi không sinh dân số. Nếu chưa nạp nguồn dân số thật, dân số năm tiếp tục null và app ghi rõ lý do; không khôi phục dân số giả cũ để lấp ô trống. Dòng tháng luôn null cho cả ba trường kinh tế.
