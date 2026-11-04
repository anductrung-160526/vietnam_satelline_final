# Quy tắc dự án (bắt buộc, áp dụng cho mọi phiên làm việc)

## Nguồn ảnh và giai đoạn
- **Ảnh ngày: Landsat CHỈ 2004–2014; Sentinel-2 từ 2015–2025.** Không lấy Landsat sau 2014,
  không lấy Sentinel-2 trước 2015. Mỗi năm chỉ có một nguồn ảnh ngày.
- Landsat tính ở 30 m, Sentinel-2 ở 10 m (theo kế hoạch quản lý dữ liệu).
- **Ảnh đêm: DMSP 2004–2013 (theo năm, 1 km); VIIRS 2014–2025 (theo tháng, 500 m).**
  Không lấy VIIRS 2013.
- Chỉ số tính theo tháng (DMSP theo năm), cấp tỉnh, 63 tỉnh trước sáp nhập.

## Quyết định đã chốt
- Không hiệu chỉnh liên kết DMSP–VIIRS; không dùng bộ dữ liệu harmonized bên ngoài (Li et al.)
  và không lấy thêm VIIRS 2013. Cột `hieu_chinh = CHUA_HIEU_CHINH`; `thay_doi_ntl` chỉ so trong
  cùng một nguồn.
- DMSP: năm có nhiều vệ tinh thì dùng vệ tinh mới nhất.
- Cột lớp phủ (`dt_nong_nghiep`, `dt_do_thi`, `dt_rung`, `dt_mat_nuoc`, `dt_dat_khac`,
  `ty_le_nong_nghiep`, `dt_nn_chuyen_doi`) để trống cho đến khi có bộ điểm mẫu.

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
