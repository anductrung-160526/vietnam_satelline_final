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
-- Tên cột phải TRÙNG KHỚP tên mà task_pipeline/derive.py:ntl_annual_rows sinh ra.
-- Đặt tên khác đi thì build_indices vẫn nạp được dòng nhưng cột để rỗng, không báo lỗi.
CREATE TABLE IF NOT EXISTS ntl_annual(
  ma_tinh TEXT NOT NULL, ten_tinh TEXT, nam INTEGER NOT NULL, nguon_anh TEXT,
  sol_ntl REAL,              -- quy mô: tổng độ sáng, SAU khi trừ nền
  sol_ntl_tho REAL,          -- tổng trước khi trừ nền, để đo tác động bước lọc
  nguong_nen REAL,           -- ngưỡng nền: VIIRS 0,5; DMSP 0 (stable_lights đã loại nền)
  so_pixel_nen INTEGER,      -- số điểm dưới ngưỡng nền
  mat_do_ntl REAL,           -- mật độ: sol_ntl / diện tích
  thay_doi_ntl REAL,         -- % so năm trước, CHỈ trong cùng một nguồn
  -- Sau hiệu chỉnh liên kết DMSP->VIIRS: so sánh được xuyên mốc 2013.
  sol_ntl_hc REAL, mat_do_ntl_hc REAL, thay_doi_ntl_hc REAL,
  mean_ntl REAL,             -- trung bình mỗi điểm ảnh
  std_ntl REAL,              -- độ lệch chuẩn
  min_ntl REAL, max_ntl REAL,
  cv_ntl REAL,               -- std/mean: chênh lệch sáng-tối trong tỉnh
  so_pixel_hop_le INTEGER,   -- số điểm ảnh có dữ liệu
  so_pixel_sang INTEGER,     -- số điểm vượt ngưỡng sáng
  dt_sang_km2 REAL,          -- diện tích được chiếu sáng
  ty_le_sang_pct REAL,       -- dt_sang_km2 / diện tích tỉnh
  sol_vung_sang REAL,        -- tổng bức xạ chỉ trên vùng sáng
  nguong_sang REAL,          -- ngưỡng đã dùng: VIIRS 1,5 nW/cm²/sr, DMSP DN 5
  dt_tu_nhien_km2 REAL,
  ghi_chu TEXT, hieu_chinh TEXT, trang_thai TEXT,
  PRIMARY KEY(ma_tinh,nam)
);

-- Chỉ số ảnh ngày theo năm: Landsat 2004-2014, Sentinel-2 2015-2025.
-- Cảnh báo: Sentinel-2 2015-2018 là TOA (L1C), 2019-2025 là phản xạ bề mặt (L2A).
-- Tên cột theo task_pipeline/derive.py:day_rows + day_stats (hậu tố _std, KHÔNG phải _stdDev).
-- derive sinh bảng này theo THÁNG; build_indices gộp lên năm bằng trung bình các tháng.
CREATE TABLE IF NOT EXISTS day_annual(
  ma_tinh TEXT NOT NULL, ten_tinh TEXT, nam INTEGER NOT NULL, nguon_anh TEXT,
  loai_phan_xa TEXT,         -- TOA (Sentinel-2 trước 2019) hoặc SR
  NDVI_mean REAL, NDVI_std REAL, NDBI_mean REAL, NDBI_std REAL,
  MNDWI_mean REAL, MNDWI_std REAL, BSI_mean REAL, BSI_std REAL,
  BLUE_mean REAL, GREEN_mean REAL, RED_mean REAL,
  NIR_mean REAL, SWIR1_mean REAL, SWIR2_mean REAL,
  ty_le_hop_le_pct REAL, dt_hop_le_km2 REAL, dt_tu_nhien_km2 REAL,
  so_thang INTEGER,          -- số tháng đã gộp lên năm này
  trang_thai TEXT,
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
  -- Phạm vi ảnh (WGS84). Thiếu nó thì bản đồ xin ô khắp thế giới và TiTiler trả 500
  -- cho mọi ô nằm ngoài ảnh.
  tay REAL, nam_do REAL, dong REAL, bac REAL,
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
