-- Bổ sung cho phần B, không dựng lại database hoặc xóa sổ COG đang dùng.
CREATE TABLE IF NOT EXISTS economy_prices(
 province_code TEXT NOT NULL, year INTEGER NOT NULL, price_basis TEXT NOT NULL,
 grdp REAL, population REAL, price_base_year INTEGER, unit TEXT NOT NULL DEFAULT 'ty_vnd',
 is_provisional INTEGER DEFAULT 0, source TEXT, quality_flags TEXT,
 PRIMARY KEY(province_code,year,price_basis),
 CHECK(price_basis IN ('so_sanh','hien_hanh'))
);
CREATE TABLE IF NOT EXISTS demo_asset(
 province_code TEXT NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL,
 kind TEXT NOT NULL, path TEXT NOT NULL, source TEXT, band_names TEXT,
 PRIMARY KEY(province_code,year,month,kind)
);
CREATE TABLE IF NOT EXISTS light_class(
 province_code TEXT NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL,
 class_index INTEGER NOT NULL, lower_bound REAL NOT NULL, upper_bound REAL,
 area_km2 REAL, status TEXT NOT NULL, unit TEXT NOT NULL, source TEXT NOT NULL,
 PRIMARY KEY(province_code,year,month,class_index)
);
-- Kết quả dictionary tùy chọn, giữ tách theo table và cơ sở giá, không ép công thức TNL=SOL.
CREATE TABLE IF NOT EXISTS demo_result(
 province_code TEXT NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL,
 table_name TEXT NOT NULL, price_basis TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(province_code,year,month,table_name,price_basis)
);
-- Phần D: kiểm chứng và mẫu số lưu cùng kết quả, không tính raster trong API.
CREATE TABLE IF NOT EXISTS light_class_summary(
 province_code TEXT NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL,
 area_km2 REAL, area_source TEXT NOT NULL,
 valid_pixels INTEGER NOT NULL, nodata_pixels INTEGER NOT NULL,
 valid_area_km2 REAL NOT NULL, valid_area_pct REAL,
 lit_area_km2 REAL NOT NULL, lit_area_pct REAL,
 area_balance_error_km2 REAL NOT NULL, validation_status TEXT NOT NULL,
 reference_year INTEGER NOT NULL, method_version TEXT NOT NULL,
 class_area_pcts TEXT NOT NULL,
 PRIMARY KEY(province_code,year,month)
);
CREATE TABLE IF NOT EXISTS annual_observation_support(
 province_code TEXT NOT NULL, year INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(province_code,year)
);
CREATE TABLE IF NOT EXISTS monthly_recovery_audit(
 province_code TEXT NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(province_code,year,month)
);
-- F: schema cộng thêm, không reset các bảng chỉ số/sổ COG cũ.
CREATE TABLE IF NOT EXISTS demo_schema_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS demo_dataset(
 dataset_id TEXT PRIMARY KEY, indices_dir TEXT NOT NULL, manifest_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS demo_provenance(
 province_code TEXT NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL,
 table_name TEXT NOT NULL, price_basis TEXT NOT NULL, dataset_id TEXT NOT NULL,
 source_path TEXT,
 PRIMARY KEY(province_code,year,month,table_name,price_basis)
);
CREATE TABLE IF NOT EXISTS demo_asset_check(
 province_code TEXT NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL, kind TEXT NOT NULL,
 payload TEXT NOT NULL,
 PRIMARY KEY(province_code,year,month,kind)
);
