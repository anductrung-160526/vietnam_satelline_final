# -*- coding: utf-8 -*-
"""
Pipeline lớp phủ bề mặt (ảnh ban ngày) cấp huyện, Việt Nam 2004–2025.

KHÔNG dùng machine learning: phân 5 lớp bằng luật ngưỡng chỉ số phổ (NDVI, MNDWI, NDBI) kết hợp
độ dốc SRTM. Ngưỡng nằm trong pipeline_core/config.py (LANDCOVER_THRESHOLDS).

Nguồn ảnh (Google Earth Engine):
Mặc định (auto): Landsat cho 2004–2014, Sentinel-2 cho 2015–2025 (mỗi năm một nguồn).
- Landsat 5/7/8/9 Collection 2 Level 2 (30 m). Landsat 7 (lỗi SLC-off sau 2003) chỉ dùng để
  lấp chỗ trống của cảm biến chính, trừ năm 2012 (năm chỉ có Landsat 7).
- Sentinel-2 (10 m) từ 2015: S2_SR_HARMONIZED (từ 04/2017), trước đó S2_HARMONIZED (TOA).

Xử lý: lọc cảnh nhiều mây, che mây và bóng mây theo pixel (QA_PIXEL / SCL / QA60), ghép ảnh trung vị
mùa khô (11 năm trước -> 4 năm hiện tại), phân lớp, cắt theo huyện, tính diện tích và diện tích đất
nông nghiệp chuyển đổi bằng chồng xếp pixel giữa năm t-1 và năm t.
"""
import sys
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from pipeline_core.config import (YEARS, START_YEAR, LANDCOVER_PACKAGE, LANDCOVER_CLASSES, LANDCOVER_THRESHOLDS,
                                  DRY_SEASON, MAX_SCENE_CLOUD, SCALE, SENTINEL2_DOWNLOAD_SCALE)
from pipeline_core.base_pipeline import BasePipeline, ID_COLS
from pipeline_core.utils import export_multiformat_table, combine_annual_monthly
from pipeline_core import ee_utils

BANDS = ["BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2"]
LANDSAT = {
    "L5": ("LANDSAT/LT05/C02/T1_L2", ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"]),
    "L7": ("LANDSAT/LE07/C02/T1_L2", ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"]),
    "L8": ("LANDSAT/LC08/C02/T1_L2", ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"]),
    "L9": ("LANDSAT/LC09/C02/T1_L2", ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"]),
}
S2_BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
S2_SR = "COPERNICUS/S2_SR_HARMONIZED"
S2_TOA = "COPERNICUS/S2_HARMONIZED"
S2_FIRST_YEAR = 2015
S2_SR_START = "2017-03-28"
SRTM = "USGS/SRTMGL1_003"

SENSORS = ("auto",)  # auto: Landsat 2004–2014, Sentinel-2 2015–2025
S2_SWITCH_YEAR = 2015
TABLE = "vietnam_district_landcover_panel_2004_2025"
MONTHLY_TABLE = "vietnam_district_landcover_monthly"
COMBINED_TABLE = "vietnam_district_day_indices_2004_2025"  # bảng gộp năm + tháng
AREA_COLS = [c["code"] for c in LANDCOVER_CLASSES.values()]
TABLE_COLS = ID_COLS + ["nam", "nguon_anh"] + AREA_COLS + [
    "dt_khong_quan_sat", "tong_dien_tich_ha", "ty_le_nong_nghiep", "dt_nn_chuyen_doi",
    "so_canh_anh", "ky_ghep_anh", "ghi_chu"]
MONTHLY_COLS = ID_COLS + ["nam", "thang", "nguon_anh"] + AREA_COLS + [
    "dt_khong_quan_sat", "tong_dien_tich_ha", "ty_le_quan_sat", "ndvi_tb", "mndwi_tb", "ndbi_tb",
    "so_canh_anh", "ghi_chu"]
# Tháng chưa có cảnh nào: chỉ chốt "không có ảnh" khi tháng đã qua đủ lâu (ảnh mới có thể về muộn)
MONTH_SETTLE_DAYS = 45


def month_window(year, month):
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    return start, end


def sensor_for_year(year):
    """Nguồn ảnh ngày theo năm: Landsat đến hết 2014, Sentinel-2 từ 2015."""
    return "landsat" if year < S2_SWITCH_YEAR else "sentinel2"


def season_window(year):
    start = f"{year - 1}-{DRY_SEASON['start_month_prev_year']:02d}-01"
    end_m = DRY_SEASON["end_month"] + 1
    end = f"{year}-{end_m:02d}-01"
    return start, end


def landsat_sources(year):
    """(cảm biến chính, cảm biến lấp chỗ trống) theo năm."""
    if year <= 2011:
        return ["L5"], ["L7"]
    if year == 2012:
        return ["L7"], ["L5"]
    if year <= 2021:
        return ["L8"], ["L7"]
    return ["L8", "L9"], ["L7"]


class LandCoverPipeline(BasePipeline):
    PACKAGE = LANDCOVER_PACKAGE
    NAME = "landcover_pipeline"
    SUBDIRS = ("raw_data/DAY/LANDSAT", "raw_data/DAY/SENTINEL2", "data_intermediate", "data_processed",
               "metadata", "samples", "code", "docs", "logs", "dashboard")

    def __init__(self, *args, sensors=SENSORS, accuracy=True, monthly=False, monthly_tif=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_dir = {"landsat": self.pkg_dir / "raw_data" / "DAY" / "LANDSAT",
                        "sentinel2": self.pkg_dir / "raw_data" / "DAY" / "SENTINEL2"}
        self.sensors = tuple(sensors)
        self.auto = self.sensors == ("auto",)
        self.accuracy = accuracy
        self._cls_cache = {}
        self._aoi = None
        self.monthly = monthly
        self.monthly_tif = monthly_tif

    # ------------------------------------------------------------------ ảnh tổng hợp
    def landsat_collection(self, key, start, end):
        ee = self.ee
        cid, bands = LANDSAT[key]

        def prep(img):
            qa = img.select("QA_PIXEL")
            # bit 1 mây giãn nở, 2 mây ti, 3 mây, 4 bóng mây
            clear = qa.bitwiseAnd(0b11110).eq(0)
            sr = img.select(bands, BANDS).multiply(0.0000275).add(-0.2)
            return sr.updateMask(clear).copyProperties(img, ["system:time_start"])

        return (ee.ImageCollection(cid).filterDate(start, end).filterBounds(self.aoi())
                .filter(ee.Filter.lt("CLOUD_COVER", MAX_SCENE_CLOUD)).map(prep))

    def landsat_window(self, year, start, end):
        """Ảnh trung vị Landsat trong [start, end), cảm biến chọn theo năm; trả (ảnh, nhãn, số cảnh)."""
        ee = self.ee
        main_keys, fill_keys = landsat_sources(year)
        main = ee.ImageCollection([])
        for k in main_keys:
            main = main.merge(self.landsat_collection(k, start, end))
        fill = ee.ImageCollection([])
        for k in fill_keys:
            fill = fill.merge(self.landsat_collection(k, start, end))
        n_main, n_fill = ee_utils.get_info(ee.List([main.size(), fill.size()]))
        if n_main + n_fill == 0:
            return None, "Landsat", 0
        comp = main.median() if n_main else fill.median()
        if n_main and n_fill:
            comp = comp.unmask(fill.median())  # lấp chỗ trống bằng cảm biến phụ (vd Landsat 7)
        names = "+".join(LANDSAT_LABEL[k] for k in (main_keys if n_main else fill_keys))
        if n_main and n_fill:
            names += f" (lấp trống bằng {'+'.join(LANDSAT_LABEL[k] for k in fill_keys)})"
        return comp, f"Landsat {names}", int(n_main + n_fill)

    def sentinel2_window(self, start, end):
        """Ảnh trung vị Sentinel-2 trong [start, end): ưu tiên SR, chưa có SR thì dùng L1C (TOA)."""
        ee = self.ee
        for use_sr in ((True, False) if start >= S2_SR_START else (False,)):
            cid = S2_SR if use_sr else S2_TOA

            def prep(img, use_sr=use_sr):
                if use_sr:
                    scl = img.select("SCL")
                    clear = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
                else:
                    qa = img.select("QA60")
                    clear = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
                return img.select(S2_BANDS, BANDS).divide(10000).updateMask(clear) \
                    .copyProperties(img, ["system:time_start"])

            col = (ee.ImageCollection(cid).filterDate(start, end).filterBounds(self.aoi())
                   .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_SCENE_CLOUD)).map(prep))
            n = ee_utils.get_info(col.size())
            if n:
                return col.median(), f"Sentinel-2 ({'SR' if use_sr else 'TOA'})", int(n)
        return None, "Sentinel-2", 0

    def landsat_composite(self, year):
        start, end = season_window(year)
        comp, label, n = self.landsat_window(year, start, end)
        if comp is None:
            raise RuntimeError(f"Không có cảnh Landsat mùa khô năm {year}")
        return comp, label, n, f"{start}..{end}", ""

    def sentinel2_composite(self, year):
        if year < S2_FIRST_YEAR:
            raise RuntimeError("Sentinel-2 chỉ có từ năm 2015")
        start, end = season_window(year)
        note = ""
        if year == S2_FIRST_YEAR:  # chưa có mùa khô 2014–2015, dùng 6 tháng cuối 2015
            start, end, note = "2015-06-23", "2016-01-01", "Năm 2015 ghép ảnh 7–12/2015 (chưa có mùa khô)"
        comp, label, n = self.sentinel2_window(start, end)
        if comp is None:
            raise RuntimeError(f"Không có cảnh Sentinel-2 năm {year}")
        if "TOA" in label:
            note = (note + "; " if note else "") + "Sentinel-2 L1C (TOA), chưa có SR"
        return comp, label, n, f"{start}..{end}", note

    def composite(self, sensor, year):
        return self.landsat_composite(year) if sensor == "landsat" else self.sentinel2_composite(year)

    def aoi(self):
        """Vùng bao các huyện đang xử lý (lọc cảnh để giảm tải cho GEE)."""
        if self._aoi is None:
            boxes = [ee_utils.geojson_bbox(g) for g in self.geoms.values()]
            self._aoi = self.ee.Geometry.Rectangle([min(b[0] for b in boxes), min(b[1] for b in boxes),
                                                    max(b[2] for b in boxes), max(b[3] for b in boxes)])
        return self._aoi

    # ------------------------------------------------------------------ phân lớp theo ngưỡng
    def classify(self, comp):
        ee = self.ee
        t = LANDCOVER_THRESHOLDS
        ndvi = comp.normalizedDifference(["NIR", "RED"])
        mndwi = comp.normalizedDifference(["GREEN", "SWIR1"])
        ndbi = comp.normalizedDifference(["SWIR1", "NIR"])
        slope = ee.Terrain.slope(ee.Image(SRTM))
        cls = ee.Image.constant(5)
        cls = cls.where(ndvi.gte(t["agri_ndvi_min"]).And(slope.lt(t["agri_slope_max_deg"])), 1)
        cls = cls.where(ndvi.gte(t["forest_ndvi_min"]).Or(
            ndvi.gte(t["forest_slope_ndvi_min"]).And(slope.gte(t["forest_slope_deg"]))), 3)
        cls = cls.where(ndbi.gt(t["urban_ndbi_min"]).And(ndvi.lt(t["urban_ndvi_max"])), 2)
        cls = cls.where(mndwi.gt(t["water_mndwi_min"]).And(ndvi.lt(t["water_ndvi_max"])), 4)
        return cls.updateMask(ndvi.mask()).rename("classification").toUint8()

    def classified(self, sensor, year):
        key = (sensor, year)
        if key not in self._cls_cache:
            comp, label, n, window, note = self.composite(sensor, year)
            self._cls_cache[key] = (comp, self.classify(comp), label, n, window, note)
        return self._cls_cache[key]

    # ------------------------------------------------------------------ diện tích
    def class_areas(self, cls, prev_cls, geom, scale):
        ee = self.ee
        area = ee.Image.pixelArea().divide(1e4)
        grouped = area.addBands(cls.unmask(0)).reduceRegion(
            ee.Reducer.sum().group(groupField=1, groupName="lop"), geom, scale, maxPixels=1e10, tileScale=4)
        out = {c: 0.0 for c in range(0, 6)}
        conv = None
        info = ee_utils.get_info(grouped if prev_cls is None else ee.Dictionary({
            "g": grouped,
            "conv": area.updateMask(prev_cls.eq(1).And(cls.neq(1))).reduceRegion(
                ee.Reducer.sum(), geom, scale, maxPixels=1e10, tileScale=4).get("area"),
        }))
        groups = info["groups"] if prev_cls is None else info["g"]["groups"]
        for g in groups:
            out[int(g["lop"])] = float(g["sum"])
        if prev_cls is not None:
            conv = float(info.get("conv") or 0.0)
        return out, conv

    # ------------------------------------------------------------------ chạy
    def process(self, sensor, year, districts):
        scale = SCALE["LANDSAT"] if sensor == "landsat" else SCALE["SENTINEL2"]
        dl_scale = scale if sensor == "landsat" else SENTINEL2_DOWNLOAD_SCALE
        sensor_label = "Landsat" if sensor == "landsat" else "Sentinel-2"
        prefix = "LANDSAT" if sensor == "landsat" else "SENTINEL2"
        with self.timer.step(self.NAME, f"chuan_bi_anh_{sensor}", nam=year):
            comp, cls, label, n_scenes, window, note = self.classified(sensor, year)
            prev = None
            prev_sensor = sensor_for_year(year - 1) if self.auto else sensor
            first_year = START_YEAR if prev_sensor == "landsat" else S2_FIRST_YEAR
            if year - 1 >= first_year:
                try:
                    prev = self.classified(prev_sensor, year - 1)[1]
                except Exception as e:
                    self.log(sensor_label, f"Không có ảnh năm {year - 1} để tính chuyển đổi: {e}")
            if prev is not None and prev_sensor != sensor:
                note = (note + "; " if note else "") + \
                    "dt_nn_chuyen_doi so với năm trước dùng Landsat (khác nguồn ảnh, độ phân giải 30 m vs 10 m)"
        self.log(sensor_label, f"Năm {year}: {n_scenes} cảnh, kỳ {window}, {label}")

        for _, row in districts.iterrows():
            gid = row["ma_huyen_gadm"]
            if gid not in self.geoms:
                continue
            fid = self.file_id(row)
            task = f"lc_{sensor}"
            try:
                if not self.checkpoint.is_completed(gid, year, task):
                    geom = self.ee.Geometry(self.geoms[gid])
                    with self.timer.step(self.NAME, f"thong_ke_dien_tich_{sensor}", gid, year):
                        areas, conv = self.class_areas(cls, prev, geom, scale)
                    total = sum(areas.values())
                    rec = {**self.id_fields(row), "nam": year, "nguon_anh": label}
                    for cid, meta in LANDCOVER_CLASSES.items():
                        rec[meta["code"]] = round(areas[cid], 2)
                    rec.update({
                        "dt_khong_quan_sat": round(areas[0], 2),
                        "tong_dien_tich_ha": round(total, 2),
                        "ty_le_nong_nghiep": round(areas[1] / total * 100, 2) if total else None,
                        "dt_nn_chuyen_doi": round(conv, 2) if conv is not None else None,
                        "so_canh_anh": n_scenes, "ky_ghep_anh": window, "ghi_chu": note,
                    })
                    self.checkpoint.mark_completed(gid, year, task, rec)
                    self.log(sensor_label, f"{row['ten_huyen']} {year}: NN={areas[1]:.0f} ha, "
                                           f"chuyển đổi={rec['dt_nn_chuyen_doi']}")
                self.save_tif(comp.multiply(10000).toInt16(), row,
                              self.raw_dir[sensor] / f"{prefix}_{fid}_{year}.tif", dl_scale, 6, "int16",
                              sensor_label, year)
                self.save_tif(cls, row, self.intermediate_dir / f"LC_{prefix}_{fid}_{year}.tif", dl_scale, 1,
                              "uint8", sensor_label, year)
            except Exception as e:
                self.log(sensor_label, f"Lỗi huyện {row['ten_huyen']} ({gid}) năm {year}: {e}", error=True)

    # ------------------------------------------------------------------ theo tháng
    def month_stats(self, comp, cls, geom, scale):
        """Diện tích 5 lớp + không quan sát (ha) và chỉ số phổ trung bình của 1 tháng, trong 1 lần gọi GEE."""
        ee = self.ee
        area = ee.Image.pixelArea().divide(1e4)
        grouped = area.addBands(cls.unmask(0)).reduceRegion(
            ee.Reducer.sum().group(groupField=1, groupName="lop"), geom, scale, maxPixels=1e10, tileScale=4)
        idx = ee.Image.cat([comp.normalizedDifference(["NIR", "RED"]).rename("ndvi"),
                            comp.normalizedDifference(["GREEN", "SWIR1"]).rename("mndwi"),
                            comp.normalizedDifference(["SWIR1", "NIR"]).rename("ndbi")])
        means = idx.reduceRegion(ee.Reducer.mean(), geom, scale, maxPixels=1e10, tileScale=4)
        info = ee_utils.get_info(ee.Dictionary({"g": grouped, "m": means}))
        out = {c: 0.0 for c in range(0, 6)}
        for g in info["g"]["groups"]:
            out[int(g["lop"])] = float(g["sum"])
        return out, info["m"]

    def process_monthly(self, sensor, year, districts):
        scale = SCALE["LANDSAT"] if sensor == "landsat" else SCALE["SENTINEL2"]
        dl_scale = scale if sensor == "landsat" else SENTINEL2_DOWNLOAD_SCALE
        sensor_label = "Landsat" if sensor == "landsat" else "Sentinel-2"
        prefix = "LANDSAT" if sensor == "landsat" else "SENTINEL2"
        today = date.today()
        for month in range(1, 13):
            start, end = month_window(year, month)
            if start > today or (sensor == "sentinel2" and end <= date(2015, 6, 23)):
                continue
            task = f"lcm_{sensor}_{month:02d}"
            rows = [r for _, r in districts.iterrows() if r["ma_huyen_gadm"] in self.geoms]
            todo = [r for r in rows if not self.checkpoint.is_completed(r["ma_huyen_gadm"], year, task)]
            if not todo and not self.monthly_tif:
                continue
            with self.timer.step(self.NAME, f"chuan_bi_anh_thang_{sensor}", nam=year, thang=month):
                if sensor == "landsat":
                    comp, label, n = self.landsat_window(year, start.isoformat(), end.isoformat())
                else:
                    comp, label, n = self.sentinel2_window(start.isoformat(), end.isoformat())
            if comp is None:
                settled = today - end > timedelta(days=MONTH_SETTLE_DAYS)
                self.log(sensor_label, f"{month:02d}/{year}: không có cảnh ảnh"
                                       f"{'' if settled else ' (sẽ thử lại lần cập nhật sau)'}")
                if settled:
                    for row in todo:
                        rec = {**self.id_fields(row), "nam": year, "thang": month, "nguon_anh": label,
                               "so_canh_anh": 0, "ty_le_quan_sat": 0.0, "ghi_chu": "Không có cảnh ảnh trong tháng"}
                        self.checkpoint.mark_completed(row["ma_huyen_gadm"], year, task, rec)
                continue
            cls = self.classify(comp)
            self.log(sensor_label, f"{month:02d}/{year}: {n} cảnh, {label}")
            for row in rows:
                gid = row["ma_huyen_gadm"]
                fid = self.file_id(row)
                try:
                    if not self.checkpoint.is_completed(gid, year, task):
                        geom = self.ee.Geometry(self.geoms[gid])
                        with self.timer.step(self.NAME, f"thong_ke_thang_{sensor}", gid, year, thang=month):
                            areas, means = self.month_stats(comp, cls, geom, scale)
                        total = sum(areas.values())
                        observed = total - areas[0]
                        rec = {**self.id_fields(row), "nam": year, "thang": month, "nguon_anh": label}
                        for cid, meta in LANDCOVER_CLASSES.items():
                            rec[meta["code"]] = round(areas[cid], 2)
                        rec.update({
                            "dt_khong_quan_sat": round(areas[0], 2),
                            "tong_dien_tich_ha": round(total, 2),
                            "ty_le_quan_sat": round(observed / total * 100, 2) if total else None,
                            "ndvi_tb": _r(means.get("ndvi")), "mndwi_tb": _r(means.get("mndwi")),
                            "ndbi_tb": _r(means.get("ndbi")), "so_canh_anh": n,
                            "ghi_chu": "Mây che phần lớn huyện" if total and observed / total < 0.5 else "",
                        })
                        self.checkpoint.mark_completed(gid, year, task, rec)
                    if self.monthly_tif:
                        self.save_tif(comp.multiply(10000).toInt16(), row,
                                      self.raw_dir[sensor] / f"{prefix}_{fid}_{year}_{month:02d}.tif",
                                      dl_scale, 6, "int16", sensor_label, year)
                        self.save_tif(cls, row,
                                      self.intermediate_dir / f"LC_{prefix}_{fid}_{year}_{month:02d}.tif",
                                      dl_scale, 1, "uint8", sensor_label, year)
                except Exception as e:
                    self.log(sensor_label, f"Lỗi huyện {row['ten_huyen']} ({gid}) {month:02d}/{year}: {e}",
                             error=True)

    def _keep_auto_source(self, df):
        """Chế độ auto: chỉ giữ bản ghi đúng nguồn của năm (bỏ bản ghi cũ từ lần chạy khác nguồn)."""
        if df.empty or not self.auto:
            return df
        want = df["nam"].astype(int).map(lambda y: "Landsat" if sensor_for_year(y) == "landsat" else "Sentinel-2")
        return df[[str(n).startswith(w) for n, w in zip(df["nguon_anh"], want)]]

    def export_tables(self):
        monthly = self._keep_auto_source(pd.DataFrame(self.checkpoint.results("lcm_")))
        if not monthly.empty:
            monthly = monthly.sort_values(["ma_huyen_gadm", "nam", "thang"]).reindex(columns=MONTHLY_COLS)
            for f in self.export(monthly, MONTHLY_TABLE):
                self.log("LandCover", f"Xuất bảng {f}")
        df = self._keep_auto_source(pd.DataFrame(self.checkpoint.results("lc_")))
        if not df.empty:
            df = df.sort_values(["ma_huyen_gadm", "nam"]).reindex(columns=TABLE_COLS)
        with self.timer.step(self.NAME, "xuat_bang"):
            if not df.empty:
                for f in self.export(df, TABLE):
                    self.log("LandCover", f"Xuất bảng {f}")
            combined = combine_annual_monthly(df, monthly)
            if not combined.empty:
                for f in self.export(combined, COMBINED_TABLE):
                    self.log("LandCover", f"Xuất bảng chỉ số ảnh ngày (năm + tháng) {f}")
        return df

    def run(self, districts_df, years=None):
        years = sorted(years or YEARS)
        districts = self.prepare_districts(districts_df)
        self.log("LandCover", f"Bắt đầu: {len(districts)} huyện, năm {years[0]}–{years[-1]}, "
                              f"ảnh: {'Landsat 2004–2014, Sentinel-2 2015–2025' if self.auto else ', '.join(self.sensors)}{', có dữ liệu tháng' if self.monthly else ''} "
                              f"(phân lớp theo ngưỡng chỉ số, không ML)")
        self.connect()
        self.load_geometries(districts)
        for sensor, sensor_years in self.plan(years):
            for year in sensor_years:
                try:
                    self.process(sensor, year, districts)
                except Exception as e:
                    self.log(sensor, f"Lỗi năm {year}: {e}", error=True)
                if self.monthly:
                    try:
                        self.process_monthly(sensor, year, districts)
                    except Exception as e:
                        self.log(sensor, f"Lỗi dữ liệu tháng năm {year}: {e}", error=True)
            if self.accuracy:
                self.run_accuracy(sensor, sensor_years)
        self._cls_cache.clear()
        return self.export_tables()

    def plan(self, years):
        """[(nguồn, [năm...])]: auto -> Landsat 2004–2014, Sentinel-2 2015–2025."""
        if self.auto:
            out = [(s, [y for y in years if sensor_for_year(y) == s]) for s in ("landsat", "sentinel2")]
        else:
            out = [(s, [y for y in years if s == "landsat" or y >= S2_FIRST_YEAR]) for s in self.sensors]
        return [(s, ys) for s, ys in out if ys]

    def run_accuracy(self, sensor, years):
        if not years:
            return
        from VN_LandCover_Panel_2004_2025.code.accuracy_assessment import evaluate_classification_accuracy
        year = max(years)
        try:
            with self.timer.step(self.NAME, f"danh_gia_do_chinh_xac_{sensor}", nam=year):
                cls = self.classified(sensor, year)[1]
                evaluate_classification_accuracy(self.ee, cls, self.pkg_dir, sensor, year, logger=self.logger)
        except Exception as e:
            self.log(sensor, f"Lỗi đánh giá độ chính xác năm {year}: {e}", error=True)


LANDSAT_LABEL = {"L5": "5", "L7": "7", "L8": "8", "L9": "9"}


def _r(v, nd=4):
    return round(float(v), nd) if v is not None else None
