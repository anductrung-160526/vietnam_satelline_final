-- VNGISDash: lớp đọc cho web. Mọi con số ở đây do task_pipeline/derive.py tính ra;
-- build_indices.py chỉ nạp CSV của data_processed vào đây, không tính thêm gì.

CREATE TABLE IF NOT EXISTS tinh(
  ma_tinh  TEXT PRIMARY KEY,
  number   INTEGER NOT NULL,
  ten_tinh TEXT NOT NULL,
  slug     TEXT NOT NULL,
  gid_1    TEXT
);

-- Chỉ số ảnh đêm theo năm: DMSP 2004-2013, VIIRS 2014-2025 (không hiệu chỉnh liên vệ tinh).
CREATE TABLE IF NOT EXISTS ntl_annual(
  ma_tinh TEXT NOT NULL, nam INTEGER NOT NULL, nguon_anh TEXT,
  sol_ntl REAL, mat_do_ntl REAL, thay_doi_ntl REAL,
  rad_mean REAL, rad_stdDev REAL, rad_min REAL, rad_max REAL,
  lit_sol REAL, lit_pixels REAL, lit_threshold REAL,
  dien_tich_km2 REAL, phuong_phap TEXT, hieu_chinh TEXT, status TEXT,
  PRIMARY KEY(ma_tinh,nam)
);

-- Chỉ số ảnh ngày theo năm: Landsat 2004-2014, Sentinel-2 2015-2025.
-- Cảnh báo: Sentinel-2 2015-2018 là TOA (L1C), 2019-2025 là phản xạ bề mặt (L2A).
CREATE TABLE IF NOT EXISTS day_annual(
  ma_tinh TEXT NOT NULL, nam INTEGER NOT NULL, nguon_anh TEXT,
  NDVI_mean REAL, NDVI_stdDev REAL, NDBI_mean REAL, NDBI_stdDev REAL,
  MNDWI_mean REAL, MNDWI_stdDev REAL, BSI_mean REAL, BSI_stdDev REAL,
  ty_le_pixel_hop_le REAL, dien_tich_km2 REAL, scale_m REAL,
  phuong_phap TEXT, status TEXT,
  PRIMARY KEY(ma_tinh,nam)
);

-- Chỉ số kinh tế do giảng viên cung cấp. Bảng rỗng là trạng thái hợp lệ: app vẫn chạy.
CREATE TABLE IF NOT EXISTS kinh_te(
  ma_tinh TEXT NOT NULL, nam INTEGER NOT NULL,
  dan_so REAL, gdp REAL, grdp_bq_dau_nguoi REAL, nguon TEXT,
  PRIMARY KEY(ma_tinh,nam)
);

-- Ảnh COG phục vụ bản đồ: mỗi (loại, năm) một ảnh.
CREATE TABLE IF NOT EXISTS anh_cog(
  loai TEXT NOT NULL,          -- 'NTL' hoặc 'DAY'
  nam INTEGER NOT NULL,
  duong_dan TEXT NOT NULL,     -- đường dẫn cục bộ hoặc gs:// cho TiTiler
  nguon_anh TEXT,
  dung_luong_byte INTEGER,
  PRIMARY KEY(loai,nam)
);

-- Ảnh gốc ở tầng lạnh (ổ E / NAS). Chỉ ghi nhận, không phục vụ qua đám mây.
CREATE TABLE IF NOT EXISTS anh_goc(
  loai TEXT NOT NULL, nam INTEGER NOT NULL,
  duong_dan TEXT NOT NULL, dung_luong_byte INTEGER, ghi_chu TEXT,
  PRIMARY KEY(loai,nam)
);

CREATE INDEX IF NOT EXISTS ix_ntl_nam ON ntl_annual(nam);
CREATE INDEX IF NOT EXISTS ix_day_nam ON day_annual(nam);
