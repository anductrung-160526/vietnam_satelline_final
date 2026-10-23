# VN_NTL_Panel_2004_2025: Kinh tế đêm cấp huyện Việt Nam (2004–2025)

Bộ dữ liệu ảnh vệ tinh ánh sáng ban đêm và chỉ số kinh tế đêm của **~705 quận/huyện/thị xã** (địa giới trước sáp nhập), giai đoạn 2004–2025. Khóa chính là `ma_huyen + nam`.

## Nguồn ảnh (truy xuất qua Google Earth Engine)

| Nguồn | Giai đoạn | GEE collection | Độ phân giải |
|---|---|---|---|
| DMSP-OLS tổng hợp năm | 2004–2013 | `NOAA/DMSP-OLS/NIGHTTIME_LIGHTS` (`stable_lights`) | ~1 km |
| VIIRS DNB tổng hợp năm (EOG VNL) | 2013–2025 | `NOAA/VIIRS/DNB/ANNUAL_V21`, `ANNUAL_V22` (`average_masked`) | ~500 m |
| VIIRS DNB hằng tháng | 2014–nay | `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG` (dự phòng `VCMCFG`) | ~500 m |
| Ranh giới huyện | — | GADM 4.1 Level 2 (tải về máy) | — |
| Điểm cháy | — | `FIRMS` | 1 km |

Nếu một năm VIIRS chưa có bản tổng hợp năm, pipeline tự ghép từ ảnh tháng (có trọng số theo `cf_cvg`).

## Xử lý

1. Lọc nhiễu: ánh sáng nền (VIIRS < 0,5 nW/cm²/sr; DMSP DN ≤ 6), mây (`cf_cvg`), cháy rừng (FIRMS, đệm 1 km), tàu thuyền và đốt khí ngoài khơi (cắt theo ranh giới đất liền).
2. Hiệu chỉnh liên kết DMSP → VIIRS: `ln(VIIRS) = a + b·ln(DN)` ước lượng trên các pixel năm chồng lấn 2013. Đây là hồi quy thống kê, không phải machine learning. Hệ số lưu tại `docs/hieu_chinh_dmsp_viirs.json`.
3. Cắt theo ranh giới huyện, tính `sol_ntl` (Σ bức xạ × diện tích pixel), `mat_do_ntl` và `thay_doi_ntl`.

## Cấu trúc thư mục

```
VN_NTL_Panel_2004_2025/
├── README.md
├── raw_data/NTL/DMSP/      DMSP_<ma_huyen>_<nam>.tif   (ảnh gốc, cắt theo huyện)
├── raw_data/NTL/VIIRS/     VIIRS_<ma_huyen>_<nam>[_<thang>].tif
├── data_intermediate/      NTL_<ma_huyen>_<nam>.tif    (đã lọc nhiễu, quy về thang VIIRS)
├── data_processed/         vietnam_district_ntl_panel_2004_2025.{csv,xlsx,dta}
│                           vietnam_district_ntl_viirs_monthly.{csv,xlsx,dta}
├── metadata/               codebook_ntl.{md,xlsx}
├── code/                   ntl_pipeline.py
├── dashboard/              (dành cho dashboard, không thuộc phạm vi pipeline)
├── docs/                   HUONG_DAN_CAP_NHAT.md, BIEN_BAN_KIEM_TRA.md, hieu_chinh_dmsp_viirs.json
└── logs/                   nhat_ky_cap_nhat.txt, log từng lượt chạy, lỗi, checkpoint, timing
```

`<ma_huyen>` là mã huyện của Cục Thống kê, hoặc mã GADM nếu huyện chưa có trong danh mục mã.

## Môi trường chạy

Xem `HUONG_DAN_CHAY_TU_DONG.md` ở thư mục gốc repo. Tóm tắt các bước: cài Python 3.10+, chạy `pip install -r requirements.txt`, chạy `earthengine authenticate`, rồi chạy `python run_pipeline.py --pipeline ntl --province "Hà Nội" --years 2024`.
