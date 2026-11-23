# P1 — Moran và thay đổi vùng sáng

> Giao diện hiện hành: **Chỉ số kinh tế đêm → Phân tích định lượng → Moran’s I**. Moran được tính trước theo từng năm và đọc từ kết quả đã kiểm chứng. Khi chọn khoảng rộng hơn lượt đã lưu (ví dụ chọn 2015–2024 trong khi chỉ có kết quả 2020–2024), app hiển thị các năm đã có và liệt kê năm còn thiếu. CSV chỉ xuất các kết quả có thật. Không tự tính thêm, nội suy hoặc thay ô thiếu bằng 0; không ghép các snapshot. Nếu nhiều lượt cùng snapshot, chọn lượt có nhiều năm nằm trong khoảng yêu cầu nhất, ưu tiên lượt mới hơn khi bằng nhau. Các hướng dẫn giao diện tab riêng bên dưới là lịch sử triển khai.

Đã có code, API, màn **Phân tích không gian**, CSV/GeoTIFF/GeoJSON và kiểm thử bằng dữ liệu biết trước. Cần chạy trên kho Windows và gửi spatial_report.json trước khi xác nhận kết quả 63 tỉnh thật. P1 là phân tích cấp tỉnh/ảnh tỉnh, không phải công thức NEI tổng hợp.

## Chạy trên máy demo

Dừng uvicorn bằng Ctrl+C, cập nhật code rồi chạy:

```powershell
git pull origin night-app
python -m backend.data.build_spatial --root "E:\SatelliteData" --integration-report "E:\SatelliteData\_demo_verify\20261122_202206_706008\integration_report.json" --year-start 2020 --year-end 2024 --publish
```

Dùng đúng báo cáo F đã gửi: snapshot 8f7799734c1d6b7df0a75882326db855b9a011a2f83437dbe0fd7067e7e6d43b, stats v9. Lệnh tính Moran cho từng năm 2020–2024 và so sánh ảnh 2020 với 2024 tại từng tỉnh. Không chạy lại A–F. Không tải ảnh mới; không sửa ảnh, CSV chỉ số hoặc mô hình GRDP. Có thể đổi hai năm để tạo một lượt P1 khác khi đủ VIIRS và phân lớp trong snapshot F.

Mặc định yêu cầu đủ danh mục 63 ranh giới GADM gốc; không dùng GeoJSON web rút gọn. Nếu F đã dùng --db, --boundaries hoặc --boundary-metadata khác mặc định, truyền cùng các đường dẫn đó. Script từ chối ranh giới khác SHA đã kiểm F. Không dùng --publish thì chỉ chuẩn bị candidate.db/file kết quả; database app giữ nguyên. Khi --publish, có backup và kiểm database chưa bị chương trình khác sửa trong lúc tính.

Chạy xong:

```powershell
python -m uvicorn backend.api.main:app --reload --port 8000
```

Ctrl+F5, mở **Phân tích không gian**, chọn 2020 và 2024, bấm **Xem phân tích**. Dùng tỉnh ở thanh chung để xem bản đồ chi tiết; chọn Toàn quốc để xem bản đồ thay đổi ròng. P1 dùng hai năm riêng trong màn phân tích, không lấy tháng đang chọn làm kỳ so sánh. Thiếu TiTiler vẫn đọc được bảng/CSV và tải GeoTIFF; bản đồ raster cần các phụ thuộc backend/requirements.txt.

## 1. Global Moran's I

Biến x là sol_density chưa hiệu chỉnh của ntl_annual: SOL sau loại nền / diện tích tự nhiên tỉnh. Chỉ dùng VIIRS, cùng năm, cùng snapshot F. Số 0 hợp lệ được giữ; ô thiếu hoặc không hữu hạn bị loại. Nguồn đã kiểm F bị mất/đổi làm dừng, không dùng số lưu cũ mà coi như còn hợp lệ.

- Trọng số gốc: hai polygon EPSG:6933 có khoảng cách ≤ 1 m là láng giềng Queen có dung sai. Chạm cạnh hoặc đỉnh đều tính; 1 m nhằm xử lý khe số hóa rất nhỏ, không phải khoảng cách lan tỏa kinh tế. Không nối láng giềng gần nhất để lấp đảo cô lập. --tolerance-m 0 chọn quan hệ tiếp xúc chính xác; ghi lại dung sai khi so sánh các lượt.
- Sau loại thiếu, tỉnh không có láng giềng quan sát được bị loại và ghi lý do. W_ij = 1/k_i với k_i là số láng giềng còn trong mẫu, W_ii = 0. S0 = tổng W_ij. neighbors.csv là trọng số thực dùng theo từng năm; neighbors trong JSON là đồ thị hình học ban đầu.
- z_i = x_i − trung bình x. I = (n/S0) × tổng_i tổng_j(W_ij z_i z_j) / tổng_i(z_i²). E[I] = −1/(n−1).
- 9.999 hoán vị nhãn x trên đồ thị cố định; seed thực tế mỗi năm = 20261123 + năm. P hai phía = (1 + số hoán vị có abs(I_perm − E[I]) ≥ abs(I_obs − E[I])) / (B + 1). Tối thiểu p = 0,0001 ở B=9.999. Lưu seed/B/cách kiểm định để tái lập; không gọi đây là kiểm định một phía của thư viện khác.
- n < 3 hoặc phương sai bằng 0: I và p để trống, có trạng thái. Nếu loại tỉnh: kết quả partial và công bố n/63, không gọi là kết quả đầy đủ 63 tỉnh.

Đã thử dựng đồ thị trên bản GADM có sẵn trong môi trường phát triển: 63 tỉnh, 135 cặp láng giềng không hướng, không có tỉnh cô lập ở dung sai 1 m. Đây là kiểm tra hình học, chưa phải kết quả Moran trên bộ ảnh Windows.

I dương/âm cho biết kiểu tự tương quan của biến trên trọng số đã chọn. P nhỏ phản ánh lệch khỏi giả thuyết hoán vị ngẫu nhiên, không chứng minh tác động nhân quả hoặc lan tỏa kinh tế. Chưa hiệu chỉnh đa kiểm định khi xem năm năm; độ nhạy theo trọng số và dung sai cần phân tích sau demo. Tham chiếu phương pháp: Moran (1950), “Notes on Continuous Stochastic Phenomena”, Biometrika 37(1/2), 17–23, DOI 10.2307/2332142; Cliff & Ord (1981), Spatial Processes: Models & Applications.

## 2. Miền so sánh và lớp thay đổi

Hai năm phải cùng VIIRS, ngưỡng, năm tham chiếu và phiên bản phân lớp. Các tỉnh cũng phải cùng bộ ngưỡng. Không fit lại P50/P90. Dùng bộ thật đã lưu trong SQLite sau D/F: 0,5; 1,5; 3,0850000381469727; 17,459999084472656 nW/cm²/sr.

Lưới đích là CRS, affine transform, kích thước pixel và extent ảnh năm cuối. Ảnh năm đầu được reproject nearest về đúng lưới đó nếu khác; mask/NaN được truyền như thiếu dữ liệu, không điền 0. Không lấy tổng hay so pixel hai lưới chưa khớp. Nearest giữ giá trị nguồn nhưng có sai số tái lấy mẫu và không tăng độ phân giải thực. File report lưu grid_reprojected và toàn bộ lưới đích.

Miền chung C = pixel có diện tích giao tỉnh dương, có bức xạ hợp lệ ở cả hai năm trên lưới chung. Diện tích ô a_i = phần giao EPSG:6933 như D/F. Báo riêng: common_area_km2, chỉ năm đầu, chỉ năm cuối, thiếu cả hai và diện tích tỉnh ngoài extent lưới đích. Những phần không quan sát chung không được diễn giải là mất sáng hoặc không thay đổi.

Raster change có sáu mã; NoData = 255:

| Mã | Ý nghĩa | Điều kiện trên miền chung |
|---|---|---|
| 0 | Không sáng ở cả hai năm | Cả hai < 1,5; vẫn có thể thay đổi trong hai lớp dưới ngưỡng sáng |
| 1 | Giữ lớp sáng | Cả hai ≥ 1,5 và cùng lớp |
| 2 | Mới sáng | Năm đầu < 1,5, năm cuối ≥ 1,5 |
| 3 | Mất sáng | Năm đầu ≥ 1,5, năm cuối < 1,5 |
| 4 | Tăng lớp trong vùng sáng | Cả hai sáng, lớp cuối > lớp đầu |
| 5 | Giảm lớp trong vùng sáng | Cả hai sáng, lớp cuối < lớp đầu |

Diện tích từng mã là tổng a_i. Sáu diện tích phải cộng bằng diện tích miền chung. lit_gain_km2 = diện tích mã 2; lit_loss_km2 = diện tích mã 3; lit_net_km2 = gain − loss. Tăng/giảm lớp trong vùng đã sáng không được cộng thành diện tích mới/mất sáng. transitions.csv lưu đủ 25 ô ma trận lớp gốc 0–4 → lớp cuối 0–4, kể cả diện tích bằng 0.

Raster delta = R_cuối − R_đầu trên miền chung, đơn vị nW/cm²/sr, NoData = −9999. Đây là chênh lệch bức xạ trước loại nền, không phải phần trăm tăng trưởng SOL. Nếu giá trị hợp lệ trùng mã NoData hoặc vượt khả năng biểu diễn, chương trình dừng thay vì xuất sai. mean_radiance_change là trung bình delta theo trọng số diện tích giao pixel, không phải trung bình của các tổng SOL.

## 3. Trọng tâm và hướng quan sát được

Tính riêng hai năm trên cùng miền C. Trọng số m_it = a_i × R_it × 1(R_it ≥ 0,5), khác SOL vốn là tổng bức xạ không nhân diện tích. Trọng tâm bằng tổng(m_it × tâm ô trong EPSG:6933) / tổng m_it. Diện tích giao ô biên được dùng làm trọng số, nhưng tọa độ vẫn là tâm ô đầy đủ; vị trí có sai số theo kích thước pixel, không phải trọng tâm hình học chính xác của từng phần giao. Thiếu tổng trọng số dương thì trọng tâm/hướng để trống.

Chuyển hai trọng tâm sang kinh/vĩ độ WGS84, khoảng cách haversine dùng bán kính Trái Đất trung bình 6371,0088 km. Góc phương vị ban đầu từ Bắc tăng theo chiều kim đồng hồ; chia tám hướng cách nhau 45°. Đây là xấp xỉ mặt cầu, không phải khoảng cách ellipsoid chính xác hay kiểm định ý nghĩa dịch chuyển. Khoảng dịch nhỏ hơn độ phân giải cần diễn giải thận trọng. Không gọi đường nối hai trọng tâm là quỹ đạo lan tỏa; không kết luận lan ra biển/đường/cảng/khu công nghiệp khi chưa có lớp đối chiếu.

## 4. Kết quả, phiên bản và nghiệm thu

Thư mục E:\SatelliteData\_demo_spatial\<lượt chạy>\:

| File | Nội dung |
|---|---|
| spatial_report.json | Snapshot F, P1 version=1, run_id, cấu hình, kết quả, nguồn/hash, số cặp, published và backup |
| moran.csv | Chỉ số, E[I], p, n/trạng thái theo năm |
| moran_values.csv | Giá trị từng tỉnh–năm, tham gia/lý do loại |
| neighbors.csv | W_ij thực tế, theo năm sau loại thiếu/cô lập |
| changes.csv | Diện tích miền chung/thiếu, sáu lớp, tọa độ trọng tâm, khoảng cách/hướng |
| transitions.csv | Ma trận chuyển lớp 5×5 theo tỉnh |
| province_changes.geojson | Ranh giới và thống kê thay đổi cấp tỉnh |
| rasters/<mã>_change.tif | Sáu mã thay đổi, NoData 255 |
| rasters/<mã>_delta.tif | Chênh lệch bức xạ có dấu |
| candidate.db | Database bổ sung spatial_run, không reset bảng nền |

P1 version=1 và bảng spatial_run riêng, không đổi STATS_VERSION=9 hay schema demo F v2 vì không thay phép tính A–F. Link file gắn snapshot và run_id; nguồn/file xuất mất hoặc đổi sẽ không báo sẵn có. Khi tính P1 lại với cùng snapshot nhưng cấu hình khác, tải lại màn phân tích để nhận đúng run_id. Giữ thư mục kết quả tại chỗ sau publish.

Kiểm trước demo: mở màn P1, xem n/63, lý do loại, p/seed; chọn Hà Nội/Bắc Ninh/Lào Cai, xem miền chung và các vùng thiếu; đối chiếu CSV với raster trong QGIS. Xem 0 là số thật và NoData là thiếu, không lẫn hai loại. Không khẳng định có dịch chuyển nếu khoảng cách nhỏ và chưa đánh giá sai số. Gửi spatial_report.json để kiểm tra kết quả thật; chưa có file này thì chỉ xác nhận chức năng đã triển khai.
