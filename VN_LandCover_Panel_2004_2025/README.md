# VN_LandCover_Panel_2004_2025: Lớp phủ bề mặt cấp huyện Việt Nam (2004–2025)

Bộ dữ liệu ảnh vệ tinh ban ngày, bản đồ lớp phủ 5 lớp và bảng diện tích theo **~705 quận/huyện/thị xã** (địa giới trước sáp nhập), giai đoạn 2004–2025. Khóa chính là `ma_huyen + nam`, và mỗi dòng ghi rõ nguồn ảnh (`nguon_anh`: Landsat hoặc Sentinel-2).

## Nguồn ảnh (qua Google Earth Engine)

Mặc định mỗi năm dùng một nguồn: **Landsat cho 2004–2014, Sentinel-2 cho 2015–2025**.

| Nguồn | Giai đoạn | GEE collection | Độ phân giải |
|---|---|---|---|
| Landsat 5 TM | 2004–2011 | `LANDSAT/LT05/C02/T1_L2` | 30 m |
| Landsat 7 ETM+ | 2012, và lấp chỗ trống các năm khác | `LANDSAT/LE07/C02/T1_L2` | 30 m |
| Landsat 8 / 9 | 2013–2025 / 2022–2025 | `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2` | 30 m |
| Sentinel-2 | 2015–2025 | `COPERNICUS/S2_SR_HARMONIZED` (từ 04/2017), `COPERNICUS/S2_HARMONIZED` | 10 m |
| Độ dốc | — | `USGS/SRTMGL1_003` | 30 m |

## Xử lý (không dùng machine learning)

1. Ghép ảnh năm: lấy ảnh **mùa khô** (01/11 năm trước → 30/04), bỏ cảnh có > 60% mây, che mây và bóng mây theo pixel (`QA_PIXEL` / `SCL` / `QA60`), rồi lấy trung vị.
2. Phân lớp theo **ngưỡng chỉ số phổ**, áp theo thứ tự ưu tiên: mặt nước (MNDWI), đô thị (NDBI), rừng (NDVI cao, hoặc NDVI khá trên đất dốc), nông nghiệp (NDVI trung bình, đất dốc < 15°), còn lại là đất khác. Ngưỡng nằm trong `pipeline_core/config.py` và được ghi trong codebook.
3. Diện tích từng lớp theo huyện (ha). Diện tích chuyển đổi đất nông nghiệp tính bằng **chồng xếp pixel**: pixel là nông nghiệp ở năm t−1 và thuộc lớp khác ở năm t.
4. **Dữ liệu 12 tháng** (khi bật `--monthly`): ghép các cảnh trong từng tháng, rồi tính diện tích 5 lớp, tỷ lệ diện tích có ảnh sạch mây (`ty_le_quan_sat`) và NDVI/MNDWI/NDBI trung bình. Tháng không có cảnh nào vẫn có một dòng với `so_canh_anh = 0`, không điền số.
5. Đánh giá độ chính xác bằng bộ điểm `samples/`. Bộ điểm chỉ dùng để kiểm chứng, không dùng để huấn luyện. Chỉ các điểm nằm trong vùng đang chạy mới được đánh giá. Báo cáo lưu tại `docs/BAO_CAO_DO_CHINH_XAC_<NGUON>_<NAM>.md`.

Phân lớp theo ngưỡng minh bạch và dễ giải thích, nhưng thường kém chính xác hơn phương pháp học máy khi phải tách nông nghiệp với rừng thưa hoặc đất trống. Vì vậy cần đọc kèm báo cáo độ chính xác.

## Cấu trúc thư mục

```
VN_LandCover_Panel_2004_2025/
├── README.md
├── raw_data/DAY/LANDSAT/     LANDSAT_<ma_huyen>_<nam>[_<thang>].tif  (ảnh tổng hợp đã che mây, 6 kênh, ×10000)
├── raw_data/DAY/SENTINEL2/   SENTINEL2_<ma_huyen>_<nam>[_<thang>].tif
├── data_intermediate/        LC_<LANDSAT|SENTINEL2>_<ma_huyen>_<nam>[_<thang>].tif (bản đồ phân lớp)
├── data_processed/           vietnam_district_day_indices_2004_2025.{csv,xlsx,dta}      (gộp năm + tháng, cột ky)
│                             vietnam_district_landcover_panel_2004_2025.{csv,xlsx,dta}  (năm)
│                             vietnam_district_landcover_monthly.{csv,xlsx,dta}         (12 tháng)
├── metadata/                 codebook_landcover.{md,xlsx}
├── samples/                  ground_truth_samples.{csv,geojson}
├── code/                     landcover_pipeline.py, accuracy_assessment.py
├── dashboard/                (không thuộc phạm vi pipeline)
├── docs/                     HUONG_DAN_CAP_NHAT.md, báo cáo độ chính xác
└── logs/
```

## Môi trường chạy

Xem `HUONG_DAN_CHAY_TU_DONG.md` ở thư mục gốc repo. Ví dụ: `python run_pipeline.py --pipeline landcover --province "Hà Nội" --years 2024 --monthly --monthly-tif`.
