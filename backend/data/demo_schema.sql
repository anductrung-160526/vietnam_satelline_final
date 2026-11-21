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
