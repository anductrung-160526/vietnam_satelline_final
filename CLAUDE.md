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

## Sáu nhóm tỉnh, tài khoản và project Earth Engine
| Nhóm | Nhánh | Tài khoản | Project |
|---|---|---|---|
| 1-11 | vngis-tinh-001-011 | adt.wqiqc@gmail.com | vngis-ee-2 |
| 12-22 | vngis-tinh-012-022 | k62.2313560049@ftu.edu.vn | vngis-ee-ha-tinh-lai-chau |
| 23-33 | vngis-tinh-023-033 | trunganduclionel9equynhmai@gmail.com | vngis-ee-soc-trang-yen-bai |
| 34-43 | vngis-tinh-034-043 | antrungatwork0711@gmail.com | vngis-ee-cao-bang-hanoi |
| 44-53 | vngis-tinh-044-053 | trungad.qec@gmail.com | vngis-ee-lam-dong-quang-tri |
| 54-63 | vngis-tinh-054-063 | 4usdperchatgpt@gmail.com | vgis-ee-6 |

Cả sáu nhóm chạy từ checkout của nhánh `vngis-tinh-001-011` trên laptop Windows
(`--range` + `--project`, mỗi tài khoản một `$env:USERPROFILE`), dữ liệu ghi thẳng vào `E:\SatelliteData`.
