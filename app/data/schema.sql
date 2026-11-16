-- VNGISDash: lớp đọc cho web. Mọi con số ở đây do task_pipeline/derive.py tính ra;
-- build_indices.py chỉ nạp CSV của data_processed vào đây, không tính thêm gì.
--
-- Tên cột của các bảng SỐ LIỆU bằng tiếng Anh và phải TRÙNG KHỚP tên cột trong
-- data_processed/*.csv (xem bảng mô tả trường trong CLAUDE.md). Lệch tên thì dòng vẫn
-- vào bảng nhưng cột để rỗng và không có gì báo lỗi — đã xảy ra thật.
-- Hai bảng cog_image và source_image là sổ tay nội bộ của app chứ không phải cột dữ
-- liệu, nhưng vẫn đặt tên tiếng Anh để cả cơ sở dữ liệu nhất quán một thứ tiếng.

CREATE TABLE IF NOT EXISTS province(
  province_code TEXT PRIMARY KEY,
  number        INTEGER NOT NULL,
  province_name TEXT NOT NULL,
  slug          TEXT NOT NULL,
  gid_1         TEXT
);

-- Chỉ số ảnh đêm theo năm: DMSP 2004-2013, VIIRS 2014-2025.
CREATE TABLE IF NOT EXISTS ntl_annual(
  province_code TEXT NOT NULL, province_name TEXT, year INTEGER NOT NULL, source TEXT,
  sol REAL,                  -- quy mô: tổng độ sáng, SAU khi trừ nền
  sol_raw REAL,              -- tổng trước khi trừ nền, để đo tác động bước lọc
  background_threshold REAL, -- ngưỡng nền: VIIRS 0,5; DMSP 0 (stable_lights đã loại nền)
  background_pixels INTEGER, -- số điểm dưới ngưỡng nền
  sol_density REAL,          -- mật độ: sol / area_km2
  sol_change_pct REAL,       -- % so năm trước, CHỈ trong cùng một nguồn
  -- Sau hiệu chỉnh liên kết DMSP->VIIRS: so sánh được xuyên mốc 2013.
  sol_cal REAL, sol_density_cal REAL, sol_change_cal_pct REAL,
  rad_mean REAL,             -- trung bình mỗi điểm ảnh
  rad_std REAL,              -- độ lệch chuẩn
  rad_min REAL, rad_max REAL,
  rad_cv REAL,               -- std/mean: chênh lệch sáng-tối trong tỉnh
  valid_pixels INTEGER,      -- số điểm ảnh có dữ liệu
  lit_pixels INTEGER,        -- số điểm vượt ngưỡng sáng
  lit_area_km2 REAL,         -- diện tích được chiếu sáng
  lit_area_pct REAL,         -- lit_area_km2 / area_km2
  lit_pixel_pct REAL,        -- lit_pixels / valid_pixels
  lit_sol REAL,              -- tổng bức xạ chỉ trên vùng sáng
  lit_threshold REAL,        -- ngưỡng đã dùng: VIIRS 1,5 nW/cm²/sr, DMSP DN 5
  cloud_free_obs REAL,       -- số lượt quan sát sạch mây trung bình (trống với DMSP)
  area_km2 REAL,
  note TEXT, calibration TEXT, status TEXT,
  PRIMARY KEY(province_code,year)
);

-- Chỉ số ảnh đêm theo THÁNG: VIIRS 2013-2025. DMSP không có vì NOAA chỉ phát hành
-- sản phẩm tổng hợp năm. Tháng 2013 có mặt ở đây nhưng không vào chuỗi chỉ số năm.
CREATE TABLE IF NOT EXISTS ntl_monthly(
  province_code TEXT NOT NULL, province_name TEXT,
  year INTEGER NOT NULL, month INTEGER NOT NULL,
  period TEXT, source TEXT,
  sol REAL, sol_raw REAL,
  background_threshold REAL, background_pixels INTEGER,
  sol_density REAL,
  sol_change_yoy_pct REAL,   -- so với cùng tháng năm trước
  sol_change_mom_pct REAL,   -- so với tháng liền trước; trống nếu tháng trước thiếu
  sol_ma3 REAL,              -- trung bình trượt 3 tháng, làm mượt dao động mùa
  rad_mean REAL, rad_std REAL, rad_min REAL, rad_max REAL, rad_cv REAL,
  valid_pixels INTEGER, lit_pixels INTEGER,
  lit_area_km2 REAL, lit_area_pct REAL, lit_pixel_pct REAL, lit_sol REAL,
  lit_threshold REAL,
  cloud_free_obs REAL,       -- ít lượt quan sát sạch mây thì con số tháng đó kém tin cậy
  area_km2 REAL,
  calibration TEXT, status TEXT,
  PRIMARY KEY(province_code,year,month)
);

-- Chỉ số ảnh ngày theo năm: Landsat 2004-2014, Sentinel-2 2015-2025.
-- Cảnh báo: Sentinel-2 2015-2018 là TOA (L1C), 2019-2025 là phản xạ bề mặt (L2A).
-- Hậu tố _std, KHÔNG phải _stdDev. derive sinh bảng này theo THÁNG; build_indices gộp
-- lên năm bằng trung bình các tháng.
CREATE TABLE IF NOT EXISTS day_annual(
  province_code TEXT NOT NULL, province_name TEXT, year INTEGER NOT NULL, source TEXT,
  reflectance_type TEXT,     -- TOA (Sentinel-2 trước 2019) hoặc SR
  NDVI_mean REAL, NDVI_std REAL, NDBI_mean REAL, NDBI_std REAL,
  MNDWI_mean REAL, MNDWI_std REAL, BSI_mean REAL, BSI_std REAL,
  BLUE_mean REAL, GREEN_mean REAL, RED_mean REAL,
  NIR_mean REAL, SWIR1_mean REAL, SWIR2_mean REAL,
  valid_area_pct REAL, valid_area_km2 REAL, area_km2 REAL,
  months_used INTEGER,       -- số tháng đã gộp lên năm này
  status TEXT,
  PRIMARY KEY(province_code,year)
);

-- Chỉ số kinh tế do giảng viên cung cấp. Bảng rỗng là trạng thái hợp lệ: app vẫn chạy.
CREATE TABLE IF NOT EXISTS economy(
  province_code TEXT NOT NULL, year INTEGER NOT NULL,
  population REAL, gdp REAL, gdp_per_capita REAL, source TEXT,
  PRIMARY KEY(province_code,year)
);

-- Ảnh COG phục vụ bản đồ: mỗi (loại, năm, tháng) một ảnh. Sổ tay nội bộ của app.
CREATE TABLE IF NOT EXISTS cog_image(
  kind TEXT NOT NULL,          -- 'NTL' hoặc 'DAY'
  year INTEGER NOT NULL,
  -- 0 = ảnh tổng hợp cả năm; 1..12 = ảnh của tháng đó. Dùng 0 chứ không phải NULL vì
  -- NULL trong khoá chính của SQLite không coi là trùng nhau, sẽ sinh ra dòng lặp.
  month INTEGER NOT NULL DEFAULT 0,
  path TEXT NOT NULL,          -- đường dẫn cục bộ hoặc gs:// cho TiTiler
  source TEXT,
  size_bytes INTEGER,
  -- Phạm vi ảnh (WGS84). Thiếu nó thì bản đồ xin ô khắp thế giới và TiTiler trả 500
  -- cho mọi ô nằm ngoài ảnh.
  west REAL, south REAL, east REAL, north REAL,
  PRIMARY KEY(kind,year,month)
);

-- Ảnh gốc ở tầng lạnh (ổ E / NAS). Chỉ ghi nhận, không phục vụ qua đám mây.
CREATE TABLE IF NOT EXISTS source_image(
  kind TEXT NOT NULL, year INTEGER NOT NULL,
  path TEXT NOT NULL, size_bytes INTEGER, note TEXT,
  PRIMARY KEY(kind,year)
);

CREATE INDEX IF NOT EXISTS ix_ntl_year ON ntl_annual(year);
CREATE INDEX IF NOT EXISTS ix_ntl_thang ON ntl_monthly(year,month);
CREATE INDEX IF NOT EXISTS ix_day_year ON day_annual(year);
