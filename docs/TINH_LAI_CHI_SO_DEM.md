# Tính lại chỉ số đêm từ ảnh đã lọc theo tỉnh

Điểm chạy: `backend/data/calculate_ntl.py`. Chạy tay trước khi nạp SQLite;
API vẫn chỉ đọc dữ liệu, không xử lý ảnh trong request.

## Đầu vào

GeoTIFF một băng bức xạ VIIRS hoặc stable_lights DMSP, đã lọc và mask đúng
ranh giới từng tỉnh. Ngoài tỉnh phải là NoData/mask, **không được điền 0**:
0 trong tỉnh là quan sát hợp lệ. Chương trình đọc băng 1, bỏ NoData, mask,
NaN và Inf; không tự lọc mây, giá trị âm hoặc đột biến của ảnh thô.
Không dùng ảnh RGB/ảnh đã đổi sang byte, thay thang đo hoặc giảm mẫu để minh họa.

Ảnh cần CRS EPSG:4326 hoặc hệ chiếu mét và lưới north-up không xoay.
Diện tích pixel WGS84 dùng xấp xỉ theo vĩ độ như pipeline cũ;
`area_km2` phải là diện tích tự nhiên tỉnh GADM 4.1 tính trong EPSG:6933.
Không lấy diện tích pixel có dữ liệu thay cho diện tích tự nhiên tỉnh.

Sao chép `backend/data/ntl_images_mau.csv` thành manifest của bạn.
**Diện tích và đường dẫn trong mẫu chỉ minh họa**, thay bằng số từ ranh giới dự án.
Mỗi dòng gồm:

| Cột | Ý nghĩa |
|---|---|
| `province_code`, `province_name` | Mã và tên tỉnh trước sáp nhập |
| `year`, `month` | Năm; tháng 0 = ảnh năm, 1–12 = ảnh tháng |
| `source` | DMSP hoặc VIIRS |
| `path` | Đường dẫn tuyệt đối hoặc tương đối với thư mục chứa manifest |
| `area_km2` | Diện tích tự nhiên tỉnh, km² |

DMSP nhận ảnh năm 2004–2013. VIIRS nhận 2013–2025; ảnh năm 2013
chỉ dùng lập cặp chồng lấn, không đưa vào `ntl_annual`.
Ảnh VIIRS năm phải được tổng hợp ở **cấp pixel** từ các ảnh tháng đã lọc;
module không lấy trung bình/trung vị SOL tháng để giả làm SOL ảnh năm.
Muốn có chỉ số năm hãy liệt kê ảnh năm với `month=0`.

## Chạy

```bash
python -m backend.data.calculate_ntl --manifest /data/danh_sach_anh.csv --root /data/SatelliteData
python -m backend.data.build_indices --root /data/SatelliteData
```

CSV mặc định ghi vào `<root>/VN_NTL_Panel_2004_2025/data_processed/`:
`ntl_annual.csv`, `ntl_monthly.csv`, `ntl_panel.csv`, `ntl_overlap_2013.csv`.
Manifest là toàn bộ tập ảnh cần tính trong lần chạy: chương trình không trộn với
bảng cũ. Có thể chọn `--output /data/ket_qua_tinh_lai` để kiểm tra trước khi thay.
Mặc định từ chối ghi đè; thêm `--overwrite` khi chủ động thay cả tập bảng.
Không sửa ảnh nguồn hoặc SQLite trong bước tính này.

## Công thức và giới hạn

`ntl_stats()` được trích từ `task_pipeline/derive.py` commit `25bf350`.
`STATS_VERSION=6` bổ sung loại NoData/mask/NaN/Inf và kiểm tra CRS;
không đọc cache thống kê của pipeline. Khi thay công thức, tăng phiên bản này
và cập nhật công thức tương ứng ở nhánh pipeline nếu còn dùng cả hai.

- Ngưỡng nền: VIIRS 0,5; DMSP 0. Pixel dưới ngưỡng đóng góp 0 vào SOL,
  vẫn tham gia `rad_mean`, `rad_std` và số pixel hợp lệ; không trừ ngưỡng khỏi từng pixel.
- Ngưỡng sáng: VIIRS 1,5; DMSP DN 5 (pixel bằng ngưỡng được tính sáng).
- Xuất SOL, SOL thô, mật độ, thống kê bức xạ, diện tích/tỷ lệ vùng sáng,
  số pixel, ngưỡng và chất lượng (`CF_CVG_MEAN` nếu có trên thẻ ảnh).
- Biến động năm chỉ so hai năm liền nhau cùng nguồn; không so DMSP với VIIRS.
- Biến động tháng gồm MoM, YoY; MA3 dùng các giá trị có số trong cửa sổ
  **ba tháng lịch**, không kéo quan sát cũ qua khoảng thiếu tháng.
- Cờ: L không pixel hợp lệ; B ảnh năm 2010/2014; U cf_cvg < 2; A bình thường.
  Manifest không liệt kê ảnh thì không tạo dòng giả với giá trị 0.
- **Chưa thực hiện hiệu chỉnh DMSP–VIIRS**: `calibration=PENDING`, không sinh số `_cal`.
  Cặp năm 2013 được xuất để có thể chạy bước hiệu chỉnh riêng sau đó.
- Không tính GRDP hoặc dân số từ ảnh; hồi quy β và SOL/người vẫn dùng dữ liệu kinh tế
  cung cấp riêng và công thức trong `backend/core/chi_so.py`.
