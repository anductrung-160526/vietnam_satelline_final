# -*- coding: utf-8 -*-
"""
Pipeline ánh sáng ban đêm (NTL) cấp huyện, Việt Nam 2004–2025.

Nguồn ảnh (Google Earth Engine):
- DMSP-OLS tổng hợp năm (NOAA/DMSP-OLS/NIGHTTIME_LIGHTS, band stable_lights), 2004–2013
- VIIRS DNB tổng hợp năm của EOG (NOAA/VIIRS/DNB/ANNUAL_V21, ANNUAL_V22, band average_masked),
  dự phòng bằng tổng hợp từ ảnh tháng nếu năm đó chưa có bản năm
- VIIRS DNB hằng tháng (NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG, dự phòng VCMCFG), từ 04/2012
- DMSP-OLS chỉ có ảnh năm, không có dữ liệu tháng

Xử lý: lọc nhiễu (mây theo cf_cvg, ánh sáng nền, cháy rừng FIRMS, vùng biển/tàu thuyền bằng ranh giới
đất liền), hiệu chỉnh liên kết DMSP -> VIIRS bằng hồi quy log-log trên năm chồng lấn 2013 (thống kê,
không phải machine learning), cắt theo ranh giới huyện, tính chỉ số và xuất bảng + ảnh .tif.
"""
import sys
import json
from datetime import date
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from pipeline_core.config import (YEARS, NTL_PACKAGE, SCALE, DMSP_LAST_YEAR, VIIRS_FIRST_YEAR,
                                  VIIRS_BACKGROUND_THRESHOLD, DMSP_BACKGROUND_DN, VIIRS_MAX_RADIANCE)
from pipeline_core.base_pipeline import BasePipeline, ID_COLS
from pipeline_core.utils import export_multiformat_table, pct_change_consecutive
from pipeline_core import ee_utils

VIIRS_ANNUAL_COLLECTIONS = ["NOAA/VIIRS/DNB/ANNUAL_V21", "NOAA/VIIRS/DNB/ANNUAL_V22"]
VIIRS_MONTHLY_COLLECTIONS = ["NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG", "NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG"]
VIIRS_MONTHLY_FIRST_YEAR = 2012  # ảnh VIIRS tháng bắt đầu từ 04/2012 (VCMCFG)
DMSP_COLLECTION = "NOAA/DMSP-OLS/NIGHTTIME_LIGHTS"
FIRMS_COLLECTION = "FIRMS"
# Vùng lấy mẫu hiệu chỉnh: toàn lãnh thổ Việt Nam (bbox)
VN_BBOX = [102.1, 8.4, 109.5, 23.4]

ANNUAL_TABLE = "vietnam_district_ntl_panel_2004_2025"
MONTHLY_TABLE = "vietnam_district_ntl_viirs_monthly"
ANNUAL_COLS = ID_COLS + ["nam", "nguon_anh", "sol_ntl", "mat_do_ntl", "thay_doi_ntl",
                         "dien_tich_km2", "sol_ntl_goc", "don_vi_goc", "so_pixel", "ghi_chu"]
MONTHLY_COLS = ID_COLS + ["nam", "thang", "nguon_anh", "sol_ntl", "mat_do_ntl", "cf_cvg_tb",
                          "dien_tich_km2", "ghi_chu"]


class NTLPipeline(BasePipeline):
    PACKAGE = NTL_PACKAGE
    NAME = "ntl_pipeline"
    SUBDIRS = ("raw_data/NTL/DMSP", "raw_data/NTL/VIIRS", "data_intermediate", "data_processed",
               "metadata", "code", "docs", "logs", "dashboard")

    def __init__(self, *args, monthly=False, monthly_tif=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_dmsp_dir = self.pkg_dir / "raw_data" / "NTL" / "DMSP"
        self.raw_viirs_dir = self.pkg_dir / "raw_data" / "NTL" / "VIIRS"
        self.monthly = monthly
        self.monthly_tif = monthly_tif
        self.calibration = None

    # ------------------------------------------------------------------ ảnh nguồn
    def first_nonempty(self, collection_ids, start, end):
        ee = self.ee
        for cid in collection_ids:
            col = ee.ImageCollection(cid).filterDate(start, end)
            if ee_utils.get_info(col.size()) > 0:
                return cid, col
        return None, None

    def dmsp_raw(self, year):
        ee = self.ee
        col = ee.ImageCollection(DMSP_COLLECTION).filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        if ee_utils.get_info(col.size()) == 0:
            raise RuntimeError(f"Không có ảnh DMSP-OLS năm {year}")
        # Năm có 2 vệ tinh -> lấy trung bình các vệ tinh
        proj = col.first().select("stable_lights").projection()
        return col.select("stable_lights").mean().rename("dn").setDefaultProjection(proj)

    def dmsp_clean(self, raw):
        """DN <= ngưỡng nền -> 0 (stable_lights đã loại cháy rừng/ánh sáng tạm thời theo NOAA)."""
        return raw.where(raw.lte(DMSP_BACKGROUND_DN), 0).rename("dn")

    def fire_mask(self, start, end):
        """1 = không có điểm cháy FIRMS trong kỳ (đệm 1 km)."""
        ee = self.ee
        col = ee.ImageCollection(FIRMS_COLLECTION).filterDate(start, end).select("T21")
        fires = col.count().setDefaultProjection(col.first().projection())
        fire_px = fires.gt(0).focalMax(1000, "circle", "meters").unmask(0)
        return fire_px.Not()

    def viirs_from_monthly(self, start, end):
        """Tổng hợp từ ảnh tháng, trọng số theo số lượt quan sát không mây (cf_cvg)."""
        cid, col = self.first_nonempty(VIIRS_MONTHLY_COLLECTIONS, start, end)
        if col is None:
            raise RuntimeError(f"Không có ảnh VIIRS tháng trong {start}..{end}")
        rad_sum = col.map(lambda im: im.select("avg_rad").max(0).multiply(im.select("cf_cvg"))).sum()
        cf_sum = col.select("cf_cvg").sum()
        raw = rad_sum.divide(cf_sum.max(1)).updateMask(cf_sum.gt(0)).rename("rad") \
            .setDefaultProjection(col.first().projection())
        return raw, cid.split("/")[-1], col

    def viirs_clean(self, raw, start, end):
        clean = raw.where(raw.lt(VIIRS_BACKGROUND_THRESHOLD), 0).min(VIIRS_MAX_RADIANCE)
        return clean.multiply(self.fire_mask(start, end)).rename("rad")

    def viirs_annual(self, year):
        """Trả về (ảnh thô, ảnh sạch, nhãn nguồn)."""
        start, end = f"{year}-01-01", f"{year + 1}-01-01"
        cid, col = self.first_nonempty(VIIRS_ANNUAL_COLLECTIONS, start, end)
        if col is not None:
            img = col.first()
            raw = img.select("average").rename("rad")
            # average_masked: EOG đã loại ánh sáng nền, cháy rừng và điểm ngoại lai
            clean = img.select("average_masked").unmask(0).max(0).min(VIIRS_MAX_RADIANCE)
            clean = clean.multiply(self.fire_mask(start, end)).rename("rad")
            return raw, clean, f"SNPP-VIIRS ({cid.split('/')[-1]})"
        raw, label, _ = self.viirs_from_monthly(start, end)
        return raw, self.viirs_clean(raw, start, end), f"SNPP-VIIRS (tổng hợp tháng {label})"

    # ------------------------------------------------------------------ hiệu chỉnh liên kết
    def calibration_file(self):
        return self.docs_dir / "hieu_chinh_dmsp_viirs.json"

    def get_calibration(self):
        """ln(VIIRS) = a + b*ln(DN_DMSP) ước lượng trên các pixel sáng năm chồng lấn 2013."""
        if self.calibration:
            return self.calibration
        f = self.calibration_file()
        if f.is_file():
            self.calibration = json.loads(f.read_text(encoding="utf-8"))
            return self.calibration
        ee = self.ee
        with self.timer.step(self.NAME, "hieu_chinh_dmsp_viirs"):
            year = VIIRS_FIRST_YEAR
            dmsp = self.dmsp_clean(self.dmsp_raw(year))
            cid, col = self.first_nonempty(VIIRS_ANNUAL_COLLECTIONS, f"{year}-01-01", f"{year + 1}-01-01")
            if col is None:
                raise RuntimeError(f"Không có ảnh VIIRS năm {year} để hiệu chỉnh liên kết")
            viirs = col.first().select("average_masked").unmask(0).max(0)
            label = cid.split("/")[-1]
            viirs_1km = viirs.reduceResolution(ee.Reducer.mean(), maxPixels=64).reproject(dmsp.projection())
            pair = dmsp.log().rename("x").addBands(viirs_1km.max(0.01).log().rename("y")) \
                .updateMask(dmsp.gt(0).And(viirs_1km.gt(0)))
            pair = pair.addBands(ee.Image.constant(1).rename("c")).select(["c", "x", "y"])
            region = ee.Geometry.Rectangle(VN_BBOX)
            fit = pair.reduceRegion(ee.Reducer.linearRegression(numX=2, numY=1), region,
                                    scale=SCALE["DMSP"], maxPixels=1e9, bestEffort=True)
            coef = ee_utils.get_info(fit.get("coefficients"))
            n = ee_utils.get_info(pair.select("x").reduceRegion(ee.Reducer.count(), region,
                                                                 scale=SCALE["DMSP"], maxPixels=1e9,
                                                                 bestEffort=True).get("x"))
        self.calibration = {
            "mo_hinh": "ln(VIIRS) = a + b * ln(DN_DMSP), chỉ áp dụng cho pixel DN > 0",
            "nam_chong_lan": year, "nguon_viirs": label,
            "a": float(coef[0][0]), "b": float(coef[1][0]), "so_pixel": int(n or 0),
            "pham_vi": "Toàn lãnh thổ Việt Nam (bbox), độ phân giải 1 km",
        }
        f.write_text(json.dumps(self.calibration, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log("DMSP/VIIRS", f"Hệ số hiệu chỉnh liên kết: a={self.calibration['a']:.4f}, "
                               f"b={self.calibration['b']:.4f} (n={self.calibration['so_pixel']}) -> {f}")
        return self.calibration

    def dmsp_to_viirs(self, dmsp_clean):
        c = self.get_calibration()
        eq = dmsp_clean.max(1).log().multiply(c["b"]).add(c["a"]).exp()
        return eq.where(dmsp_clean.lte(0), 0).rename("rad")

    # ------------------------------------------------------------------ thống kê vùng
    def zonal(self, img, geom, scale):
        """SOL = Σ(bức xạ × diện tích pixel km²): không phụ thuộc độ phân giải -> so sánh được DMSP/VIIRS."""
        ee = self.ee
        area = ee.Image.pixelArea().divide(1e6)
        stack = img.multiply(area).rename("sol").addBands(ee.Image.constant(1).rename("n"))
        res = ee_utils.get_info(stack.reduceRegion(reducer=ee.Reducer.sum(), geometry=geom, scale=scale,
                                                   maxPixels=1e10))
        return res.get("sol") or 0.0, round(res.get("n") or 0)

    def district_area_km2(self, gid):
        ee = self.ee
        return ee_utils.get_info(ee.Geometry(self.geoms[gid]).area(maxError=1)) / 1e6

    # ------------------------------------------------------------------ chạy theo năm
    def process_year(self, year, districts):
        is_dmsp = year < VIIRS_FIRST_YEAR
        start, end = f"{year}-01-01", f"{year + 1}-01-01"
        with self.timer.step(self.NAME, "chuan_bi_anh_nam", nam=year):
            if is_dmsp:
                raw = self.dmsp_raw(year)
                clean_dn = self.dmsp_clean(raw)
                clean = self.dmsp_to_viirs(clean_dn)
                sensor, label, scale = "DMSP", "DMSP-OLS (hiệu chỉnh về VIIRS)", SCALE["DMSP"]
            else:
                raw, clean, label = self.viirs_annual(year)
                sensor, scale = "VIIRS", SCALE["VIIRS"]
            # Năm chồng lấn: lưu thêm ảnh DMSP thô để kiểm tra hiệu chỉnh
            dmsp_overlap = self.dmsp_raw(year) if (not is_dmsp and year <= DMSP_LAST_YEAR) else None

        for _, row in districts.iterrows():
            gid = row["ma_huyen_gadm"]
            if gid not in self.geoms:
                continue
            fid = self.file_id(row)
            try:
                task = "ntl_annual"
                if not self.checkpoint.is_completed(gid, year, task):
                    geom = self.ee.Geometry(self.geoms[gid])
                    with self.timer.step(self.NAME, "thong_ke_vung", gid, year):
                        area = self.district_area_km2(gid)
                        sol, n_px = self.zonal(clean, geom, scale)
                        sol_raw, _ = self.zonal(raw, geom, scale)
                    rec = {**self.id_fields(row), "nam": year, "nguon_anh": label,
                           "sol_ntl": round(sol, 4), "mat_do_ntl": round(sol / area, 4) if area else None,
                           "dien_tich_km2": round(area, 3), "sol_ntl_goc": round(sol_raw, 4),
                           "don_vi_goc": "DN·km²" if is_dmsp else "nW/cm²/sr·km²",
                           "so_pixel": int(n_px), "ghi_chu": ""}
                    self.checkpoint.mark_completed(gid, year, task, rec)
                    self.log(sensor, f"{row['ten_huyen']} {year}: SOL={sol:.2f}")

                raw_dir = self.raw_dmsp_dir if is_dmsp else self.raw_viirs_dir
                self.save_tif(raw.toFloat(), row, raw_dir / f"{sensor}_{fid}_{year}.tif", scale, 1, "float",
                              sensor, year)
                if dmsp_overlap is not None:
                    self.save_tif(dmsp_overlap.toFloat(), row, self.raw_dmsp_dir / f"DMSP_{fid}_{year}.tif",
                                  SCALE["DMSP"], 1, "float", "DMSP", year)
                self.save_tif(clean.toFloat(), row, self.intermediate_dir / f"NTL_{fid}_{year}.tif", scale, 1,
                              "float", sensor, year)
            except Exception as e:
                self.log(sensor, f"Lỗi huyện {row['ten_huyen']} ({gid}) năm {year}: {e}", error=True)

    def process_monthly(self, year, districts):
        ee = self.ee
        for month in range(1, 13):
            if date(year, month, 1) > date.today():
                break
            start = f"{year}-{month:02d}-01"
            end = f"{year + (month == 12)}-{(month % 12) + 1:02d}-01"
            todo = [r for _, r in districts.iterrows() if r["ma_huyen_gadm"] in self.geoms and (
                not self.checkpoint.is_completed(r["ma_huyen_gadm"], year, f"ntl_month_{month:02d}")
                or self.monthly_tif)]
            if not todo:
                continue
            cid, col = self.first_nonempty(VIIRS_MONTHLY_COLLECTIONS, start, end)
            if col is None:
                self.log("VIIRS", f"Chưa có ảnh VIIRS tháng {month:02d}/{year}")
                continue
            img = col.first()
            raw = img.select("avg_rad").rename("rad")
            clean = self.viirs_clean(raw.updateMask(img.select("cf_cvg").gt(0)), start, end)
            label = f"SNPP-VIIRS ({cid.split('/')[-1]})"
            for row in todo:
                gid = row["ma_huyen_gadm"]
                task = f"ntl_month_{month:02d}"
                try:
                    geom = ee.Geometry(self.geoms[gid])
                    if not self.checkpoint.is_completed(gid, year, task):
                        with self.timer.step(self.NAME, "thong_ke_vung_thang", gid, year, thang=month):
                            area = self.district_area_km2(gid)
                            sol, _ = self.zonal(clean, geom, SCALE["VIIRS"])
                            cf = ee_utils.get_info(img.select("cf_cvg").reduceRegion(
                                ee.Reducer.mean(), geom, SCALE["VIIRS"], maxPixels=1e9).get("cf_cvg"))
                        rec = {**self.id_fields(row), "nam": year, "thang": month, "nguon_anh": label,
                               "sol_ntl": round(sol, 4), "mat_do_ntl": round(sol / area, 4) if area else None,
                               "cf_cvg_tb": round(cf, 2) if cf is not None else None,
                               "dien_tich_km2": round(area, 3), "ghi_chu": ""}
                        self.checkpoint.mark_completed(gid, year, task, rec)
                    if self.monthly_tif:
                        self.save_tif(raw.toFloat(), row,
                                      self.raw_viirs_dir / f"VIIRS_{self.file_id(row)}_{year}_{month:02d}.tif",
                                      SCALE["VIIRS"], 1, "float", "VIIRS", year)
                except Exception as e:
                    self.log("VIIRS", f"Lỗi huyện {row['ten_huyen']} ({gid}) {month:02d}/{year}: {e}", error=True)

    # ------------------------------------------------------------------ xuất bảng
    def export_tables(self):
        written = []
        annual = pd.DataFrame(self.checkpoint.results("ntl_annual"))
        if not annual.empty:
            annual = annual.sort_values(["ma_huyen_gadm", "nam"]).reset_index(drop=True)
            annual["thay_doi_ntl"] = pct_change_consecutive(annual, "ma_huyen_gadm", "sol_ntl")
            annual = annual.reindex(columns=ANNUAL_COLS)
            with self.timer.step(self.NAME, "xuat_bang"):
                written += export_multiformat_table(annual, self.processed_dir / ANNUAL_TABLE, logger=self.logger)
        monthly = pd.DataFrame(self.checkpoint.results("ntl_month_"))
        if not monthly.empty:
            monthly = monthly.sort_values(["ma_huyen_gadm", "nam", "thang"]).reindex(columns=MONTHLY_COLS)
            written += export_multiformat_table(monthly, self.processed_dir / MONTHLY_TABLE, logger=self.logger)
        for f in written:
            self.log("NTL", f"Xuất bảng {f}")
        return annual

    def run(self, districts_df, years=None):
        years = sorted(years or YEARS)
        districts = self.prepare_districts(districts_df)
        self.log("NTL", f"Bắt đầu: {len(districts)} huyện, năm {years[0]}–{years[-1]}"
                        f"{', có dữ liệu tháng' if self.monthly else ''}")
        self.connect()
        self.load_geometries(districts)
        for year in years:
            try:
                self.process_year(year, districts)
                if self.monthly and year >= VIIRS_MONTHLY_FIRST_YEAR:
                    self.process_monthly(year, districts)
            except Exception as e:
                self.log("NTL", f"Lỗi năm {year}: {e}", error=True)
        return self.export_tables()
