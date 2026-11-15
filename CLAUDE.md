# Quy tắc dự án (bắt buộc, áp dụng cho mọi phiên làm việc)

## Nguồn ảnh và giai đoạn
- **Ảnh ngày: Landsat CHỈ 2004–2014; Sentinel-2 từ 2015–2025.** Không lấy Landsat sau 2014,
  không lấy Sentinel-2 trước 2015. Mỗi năm chỉ có một nguồn ảnh ngày.
- Landsat tính ở 30 m, Sentinel-2 ở 10 m (theo kế hoạch quản lý dữ liệu).
- **Ảnh đêm: DMSP 2004–2013 (theo năm, 1 km); VIIRS 2014–2025 (theo tháng, 500 m).**
- **VIIRS 2013 CÓ tải, nhưng KHÔNG vào chuỗi chỉ số năm.** Năm 2013 trong `ntl_annual` luôn
  lấy từ DMSP (`derive.ntl_annual_rows`: VIIRS chỉ dùng từ `year>=2014`). VIIRS 2013 tồn tại
  duy nhất để làm **năm chồng lấn** cho bước hiệu chỉnh DMSP→VIIRS: `harmonize.py` khớp mô
  hình trên các tỉnh có cả hai nguồn ở 2013, và từ chối chạy nếu dưới 30 tỉnh.
  Thiếu VIIRS 2013 thì chuỗi 2004–2025 không bao giờ so sánh được xuyên mốc đổi vệ tinh.
- Chỉ số tính theo tháng (DMSP theo năm), cấp tỉnh, 63 tỉnh trước sáp nhập.

## Quyết định đã chốt
- **CÓ hiệu chỉnh liên kết DMSP–VIIRS** (chốt 09/11/2026, đảo lại quyết định trước đó).
  Tự khớp mô hình trên năm chồng lấn 2013 của chính bộ dữ liệu này; **không** dùng bộ dữ liệu
  harmonized bên ngoài (Li et al.) và không lấy thêm VIIRS 2013 từ nguồn khác.
  `task_pipeline/harmonize.py`: hồi quy log–log trên 63 tỉnh năm 2013, quy DMSP về thang VIIRS
  (`sol_viirs = a * sol_dmsp^b`), số liệu VIIRS giữ nguyên. Ghi thêm cột `sol_ntl_hc`,
  `mat_do_ntl_hc`, `thay_doi_ntl_hc`; **không ghi đè** cột gốc. `hieu_chinh` mang tên phương pháp.
  Tham số mô hình lưu ở `metadata/hieu_chinh_dmsp_viirs.json`.
  - So sánh xuyên mốc 2013 thì dùng cột `_hc`; cột gốc là giá trị theo thang riêng từng vệ tinh.
  - `thay_doi_ntl` (gốc) vẫn chỉ so trong cùng một nguồn, bỏ trống ở mốc đổi vệ tinh.
- **KHÔNG hiệu chỉnh mốc đổi vệ tinh DMSP F16→F18 năm 2010** (chốt 15/11/2026).
  Ảnh DMSP 2004–2009 là vệ tinh F16, 2010–2013 là F18; NOAA không hiệu chuẩn các vệ tinh
  DMSP với nhau. F16 dừng ở 2009 còn F18 bắt đầu 2010 nên **không có năm chồng lấn**:
  không thể đo độ lệch bằng chính bộ dữ liệu này như đã làm ở mốc 2013.
  Hệ quả: `thay_doi_ntl` năm 2010 của nhiều tỉnh vọt lên hàng trăm phần trăm — đó là
  đổi cảm biến, không phải kinh tế. **`sol_ntl_hc` KHÔNG sửa mốc này**, nó chỉ xử lý
  mốc DMSP→VIIRS năm 2013.
  Mọi so sánh bắc qua 2010 là không hợp lệ, kể cả trên cột `_hc`. Giai đoạn VIIRS
  2014–2025 không có mốc nối nào nên sạch. `app/api/store.py: MOC_2010` cảnh báo trên API;
  `scripts/kiem_tra_chi_so_dem.py` nhắc lại khi soi bảng.
- **CÓ trừ ánh sáng nền theo ngưỡng** (chốt 09/11/2026). Pixel dưới ngưỡng vẫn hợp lệ nhưng đóng
  góp 0 vào `sol_ntl`. Ngưỡng nền: VIIRS 0,5 nW/cm²/sr (bằng mặc định `lit_threshold_viirs` của
  `province_pipeline/profiles.py`); DMSP 0 vì `stable_lights` của NOAA đã loại nền sẵn, trừ nữa
  là trừ hai lần. `sol_ntl_tho` giữ tổng chưa trừ nền để đo được tác động.
- Ngưỡng "có ánh sáng" (khác ngưỡng nền): VIIRS 1,5 nW/cm²/sr (`task_pipeline/scope.py`),
  DMSP DN 5 (`province_pipeline/profiles.py`). Hai thang đo khác nhau, không dùng chung một số.
- Đổi công thức trong `derive.ntl_stats`/`day_stats` thì **phải tăng `STATS_VERSION`**, nếu không
  `Cache` trả lại kết quả cũ và cột mới sẽ rỗng mà không báo lỗi.
- DMSP: năm có nhiều vệ tinh thì dùng vệ tinh mới nhất.
- Cột lớp phủ (`dt_nong_nghiep`, `dt_do_thi`, `dt_rung`, `dt_mat_nuoc`, `dt_dat_khac`,
  `ty_le_nong_nghiep`, `dt_nn_chuyen_doi`) để trống cho đến khi có bộ điểm mẫu.

## Bảng mô tả trường dữ liệu (một bảng duy nhất cho mọi bảng số liệu)

Tên cột trong `data_processed/*.csv` và trong `app/data/schema.sql` **bằng tiếng Anh**.
Khoá chung: `province_code` + `year` + `month` (`month` = 0 với dòng ghi theo năm).
Bảng này sinh ra từ `task_pipeline/derive.py: CODEBOOK` — sửa ở đó rồi chạy lại,
đừng sửa tay ở đây; `tests/test_app_api.py` kiểm hai nơi khớp nhau.

| Cột | Ý nghĩa | Kiểu | Đơn vị |
|---|---|---|---|
| `province_code` | Mã tỉnh, thành phố theo Cục Thống kê (63 tỉnh trước sáp nhập) | String | — |
| `province_name` | Tên tỉnh, thành phố | String | — |
| `year` | Năm | Numeric | — |
| `month` | Tháng; 0 với dòng ghi theo năm | Numeric | — |
| `period` | "2010" (theo năm) hoặc "2016-03" (theo tháng) | String | — |
| `frequency` | annual hoặc monthly — tần suất của chính dòng đó | String | — |
| `source` | DMSP, VIIRS, Landsat hoặc Sentinel-2 | String | — |
| `area_km2` | Diện tích tự nhiên của tỉnh (polygon GADM 4.1, EPSG:6933) | Numeric | km² |
| `sol` | Quy mô kinh tế đêm: tổng giá trị pixel hợp lệ SAU khi trừ nền | Numeric | DN (DMSP) / nW/cm²/sr (VIIRS) |
| `sol_density` | Mật độ kinh tế đêm: sol / area_km2 | Numeric | đơn vị bức xạ/km² |
| `sol_change_pct` | Thay đổi so với NĂM trước, chỉ khi cùng nguồn ảnh. Chỉ có ở dòng theo năm, nên trống ở toàn bộ nửa VIIRS theo tháng của ntl_panel | Numeric | % |
| `sol_change_yoy_pct` | Thay đổi so với CÙNG THÁNG năm trước. Chỉ có ở dòng theo tháng. Dòng 2014 lấy mốc so sánh từ VIIRS 2013 — cùng cảm biến nên hợp lệ, nhưng các tháng 2013 nằm ở ntl_monthly chứ không ở ntl_panel | Numeric | % |
| `sol_change_mom_pct` | Thay đổi so với THÁNG LIỀN TRƯỚC; trống nếu tháng trước thiếu. Chỉ có ở dòng theo tháng; tháng 01/2014 so với 12/2013 | Numeric | % |
| `sol_ma3` | Trung bình trượt 3 tháng của sol, làm mượt dao động mùa. Chỉ có ở dòng theo tháng; cửa sổ của đầu 2014 với tới các tháng 2013 | Numeric | nW/cm²/sr |
| `sol_raw` | Tổng giá trị TRƯỚC khi trừ nền, để đo tác động của bước lọc nền | Numeric | DN / nW/cm²/sr |
| `background_threshold` | Ngưỡng nền đã dùng (VIIRS 0,5; DMSP 0 vì stable_lights đã loại nền) | Numeric | nW/cm²/sr hoặc DN |
| `background_pixels` | Số pixel dưới ngưỡng nền, đóng góp 0 vào sol | Numeric | pixel |
| `rad_mean` | Bức xạ trung bình trên pixel hợp lệ | Numeric | DN / nW/cm²/sr |
| `rad_std` | Độ lệch chuẩn bức xạ trong tỉnh | Numeric | DN / nW/cm²/sr |
| `rad_min` | Giá trị nhỏ nhất trong tỉnh | Numeric | DN / nW/cm²/sr |
| `rad_max` | Giá trị lớn nhất trong tỉnh | Numeric | DN / nW/cm²/sr |
| `rad_cv` | Hệ số biến thiên rad_std/rad_mean: chênh lệch sáng–tối trong tỉnh | Numeric | không thứ nguyên |
| `lit_pixels` | Số pixel vượt ngưỡng sáng | Numeric | pixel |
| `lit_area_km2` | Diện tích các pixel vượt ngưỡng sáng | Numeric | km² |
| `lit_area_pct` | lit_area_km2 / area_km2: tỷ lệ diện tích tỉnh được chiếu sáng | Numeric | % |
| `lit_pixel_pct` | lit_pixels / valid_pixels: tỷ lệ số pixel sáng trên số pixel có dữ liệu | Numeric | % |
| `lit_sol` | Tổng bức xạ CHỈ trên các pixel vượt ngưỡng | Numeric | DN / nW/cm²/sr |
| `lit_threshold` | Ngưỡng xác định pixel sáng (VIIRS 1,5 nW/cm²/sr; DMSP DN 5) | Numeric | nW/cm²/sr hoặc DN |
| `valid_pixels` | Số pixel có dữ liệu trong ranh giới tỉnh | Numeric | pixel |
| `cloud_free_obs` | Số lượt quan sát sạch mây trung bình (cf_cvg). Trống với DMSP vì sản phẩm stable_lights của NOAA không có băng này | Numeric | lượt |
| `status` | OK, OK_TOA, CHUA_CO_ANH, MISSING_SOURCE, INSUFFICIENT_QUALITY | String | — |
| `note` | DOI_NGUON_ANH_CHUA_HIEU_CHINH tại năm chuyển từ DMSP sang VIIRS; rỗng ở mọi dòng khác, nên trong ntl_panel (hai nửa không giáp nhau) luôn rỗng | String | — |
| `sol_cal` | sol sau khi quy DMSP về thang VIIRS; dòng VIIRS giữ nguyên | Numeric | nW/cm²/sr |
| `sol_density_cal` | sol_cal / area_km2 | Numeric | nW/cm²/sr trên km² |
| `sol_change_cal_pct` | Thay đổi trên chuỗi đã hiệu chỉnh; CÓ giá trị tại mốc 2013→2014 | Numeric | % |
| `calibration` | Tên phương pháp hiệu chỉnh, hoặc PENDING | String | — |
| `sol_dmsp` | sol của ảnh DMSP 2013, dùng để khớp mô hình hiệu chỉnh | Numeric | DN |
| `sol_viirs` | sol của ảnh VIIRS 2013, cùng ngưỡng nền với cột sol | Numeric | nW/cm²/sr |
| `reflectance_type` | SR (phản xạ bề mặt) hoặc TOA (Sentinel-2 2015–2018) | String | — |
| `<KÊNH>_mean / _std` | Trung bình / độ lệch chuẩn phản xạ kênh (BLUE..SWIR2) và chỉ số NDVI, NDBI, MNDWI, BSI | Numeric | phản xạ (0–1) / không thứ nguyên |
| `valid_area_km2` | Diện tích pixel hợp lệ ở mọi kênh | Numeric | km² |
| `valid_area_pct` | valid_area_km2 / area_km2 | Numeric | % |
| `window_days` | Cửa sổ ngày của ảnh tổng hợp | String | — |
| `collections` | Bộ sưu tập ảnh đã dùng | String | — |
| `months_used` | Số tháng đã gộp lên dòng năm | Numeric | tháng |

Bảng nào có cột nào:

| Bảng | Nội dung | Cột riêng |
|---|---|---|
| `ntl_panel` | **Bộ chính**: DMSP theo năm 2004–2013 + VIIRS theo tháng 2014–2025 | cả hai nhóm, phân biệt bằng `frequency` |
| `ntl_annual` | Chuỗi theo năm 2004–2025 (VIIRS năm = trung vị các tháng) | `sol_change_pct`, nhóm `_cal` |
| `ntl_monthly` | Mọi tháng VIIRS có ảnh, kể cả 2013 | `sol_change_mom_pct`, `sol_change_yoy_pct`, `sol_ma3` |
| `ntl_overlap_2013` | Cặp DMSP–VIIRS năm 2013 để khớp mô hình hiệu chỉnh | `sol_dmsp`, `sol_viirs` |
| `day_indices_monthly` | Chỉ số ảnh ngày theo tháng | `reflectance_type`, `<KÊNH>_mean/_std` |

## Mười tài khoản và project Earth Engine

| Luồng | Tài khoản | Project | Profile trên Windows |
|---|---|---|---|
| 1 | adt.wqiqc@gmail.com | vngis-ee-2 | (mặc định) |
| 2 | k62.2313560049@ftu.edu.vn | vngis-ee-ha-tinh-lai-chau | `C:\ee-profiles\acc-ftu` |
| 3 | trunganduclionel9equynhmai@gmail.com | vngis-ee-soc-trang-yen-bai | `C:\ee-profiles\acc-quynhmai` |
| 4 | antrungatwork0711@gmail.com | vngis-ee-cao-bang-hanoi | `C:\ee-profiles\acc-work` |
| 5 | trungad.qec@gmail.com | vngis-ee-lam-dong-quang-tri | `C:\ee-profiles\acc-qec` |
| 6 | 4usdperchatgpt@gmail.com | vgis-ee-6 | `C:\ee-profiles\acc-4usd` |
| 7 | miendao752@gmail.com | vgis-ee-07 | `C:\ee-profiles\acc-miendao` |
| 8 | ducanchu0808@gmail.com | vgis-ee-08 | `C:\ee-profiles\acc-ducanchu` |
| 9 | linhbe200562@gmail.com | vgis-ee-09 | `C:\ee-profiles\acc-linhbe` |
| 10 | mpnguyenjib1030@gmail.com | vgis-ee-10 | `C:\ee-profiles\acc-mpnguyen` |

Mỗi luồng = một project Earth Engine (quota riêng) + một tài khoản Google đã đăng nhập.

**Không cần nhánh git riêng cho mỗi luồng.** Mọi luồng chạy từ cùng một checkout của nhánh
`vngis-tinh-001-011`; việc chia công việc do tham số quyết định:
- `national.py --shard i/n`: chia **mỗi năm** thành `n` phần, luồng này lấy phần `i`
  (10 tài khoản → `--shard 1/10` … `--shard 10/10`, mọi luồng của cùng một năm phải cùng `n`).
- `stats.py --range`: chia theo nhóm tỉnh (các nhánh `vngis-tinh-XXX-XXX` là di sản của luồng
  tải ảnh theo tỉnh/tháng trước đây, không dùng cho ảnh năm toàn quốc).

Dữ liệu ghi vào `E:\SatelliteData` (Windows) hoặc `/data/SatelliteData` (máy ảo Linux).
Xem `task_pipeline/SETUP_LUONG_GEE_VI.md` để biết các bước thiết lập và chạy chi tiết.

## Quyết định về ứng dụng VNGISDash (chốt 04/11/2026)
- **Prototype làm ở cấp tỉnh, 63 tỉnh toàn quốc.** Đề cương viết cấp xã (GADM 4.1,
  11.163 xã, thí điểm Bắc Ninh); cấp tỉnh được coi là **bước 1**. Nếu cô yêu cầu thêm
  thì mở rộng xuống cấp xã sau, không làm lại.
- **Kiến trúc bản gọn, nâng cấp dần**: một Cloud Run chạy FastAPI + TiTiler, chỉ số trong
  SQLite, ảnh COG trên Cloud Storage, frontend tĩnh. Nâng lên Cloud SQL (PostgreSQL) và
  Firebase Hosting sau khi demo chạy được. Ảnh gốc 24 GB/năm **không lên đám mây**
  (tầng lạnh: ổ E / NAS), API chỉ cấp liên kết tải.
- **Chuỗi Sentinel-2 không đồng nhất là có chủ ý và đã được cô chấp nhận**: 2015–2018 là
  `COPERNICUS/S2_HARMONIZED` (L1C, phản xạ đỉnh khí quyển TOA); 2019–2025 là
  `COPERNICUS/S2_SR_HARMONIZED` (L2A, phản xạ bề mặt). Không tự ý đổi nguồn hay thêm
  hiệu chỉnh. Mọi bảng/báo cáo so sánh giữa hai giai đoạn phải ghi rõ cảnh báo này.
- **Yêu cầu của cô về app** (kim chỉ nam khi thiết kế giao diện):
  bản đồ nền ban đêm làm chủ đạo, thiết kế nhẹ và dễ dùng; ảnh ngày **không** hiển thị
  toàn bộ, mỗi năm chỉ một ảnh nén để minh họa, phần còn lại chỉ dùng trích xuất ngầm;
  chọn xem theo từng tỉnh (độ sáng, diện tích sáng); một nút Export tải ra gồm ảnh đêm +
  chỉ số ngày + chỉ số đêm + chỉ số kinh tế; chỉ số kinh tế (dân số, GDP) do cô cung cấp.
- Lớp web nằm trong `app/`, **chỉ đọc** `data_processed/*.csv` và các COG. Không tính chỉ
  số trong API: mọi phép tính thuộc `task_pipeline/derive.py`.
