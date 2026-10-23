# -*- coding: utf-8 -*-
"""
Pipeline lớp phủ bề mặt (ảnh ban ngày) cấp huyện, Việt Nam 2004–2025.

KHÔNG dùng machine learning: phân 5 lớp bằng luật ngưỡng chỉ số phổ (NDVI, MNDWI, NDBI) kết hợp
độ dốc SRTM. Ngưỡng nằm trong pipeline_core/config.py (LANDCOVER_THRESHOLDS).

Nguồn ảnh (Google Earth Engine):
- Landsat 5/7/8/9 Collection 2 Level 2 (30 m), 2004–2025. Landsat 7 (lỗi SLC-off sau 2003) chỉ dùng để
  lấp chỗ trống của cảm biến chính, trừ năm 2012 (năm chỉ có Landsat 7).
- Sentinel-2 (10 m) từ 2015: S2_SR_HARMONIZED (từ 04/2017), trước đó S2_HARMONIZED (TOA).

Xử lý: lọc cảnh nhiều mây, che mây và bóng mây theo pixel (QA_PIXEL / SCL / QA60), ghép ảnh trung vị
mùa khô (11 năm trước -> 4 năm hiện tại), phân lớp, cắt theo huyện, tính diện tích và diện tích đất
nông nghiệp chuyển đổi bằng chồng xếp pixel giữa năm t-1 và năm t.
"""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from pipeline_core.config import (YEARS, START_YEAR, LANDCOVER_PACKAGE, LANDCOVER_CLASSES, LANDCOVER_THRESHOLDS,
                                  DRY_SEASON, MAX_SCENE_CLOUD, SCALE, SENTINEL2_DOWNLOAD_SCALE)
from pipeline_core.base_pipeline import BasePipeline, ID_COLS
from pipeline_core.utils import export_multiformat_table
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
SRTM = "USGS/SRTMGL1_003"

SENSORS = ("landsat", "sentinel2")
TABLE = "vietnam_district_landcover_panel_2004_2025"
AREA_COLS = [c["code"] for c in LANDCOVER_CLASSES.values()]
TABLE_COLS = ID_COLS + ["nam", "nguon_anh"] + AREA_COLS + [
    "dt_khong_quan_sat", "tong_dien_tich_ha", "ty_le_nong_nghiep", "dt_nn_chuyen_doi",
    "so_canh_anh", "ky_ghep_anh", "ghi_chu"]


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

    def __init__(self, *args, sensors=SENSORS, accuracy=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_dir = {"landsat": self.pkg_dir / "raw_data" / "DAY" / "LANDSAT",
                        "sentinel2": self.pkg_dir / "raw_data" / "DAY" / "SENTINEL2"}
        self.sensors = tuple(sensors)
        self.accuracy = accuracy
        self._cls_cache = {}

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

        return (ee.ImageCollection(cid).filterDate(start, end)
                .filter(ee.Filter.lt("CLOUD_COVER", MAX_SCENE_CLOUD)).map(prep))

    def landsat_composite(self, year):
        ee = self.ee
        start, end = season_window(year)
        main_keys, fill_keys = landsat_sources(year)
        main = ee.ImageCollection([])
        for k in main_keys:
            main = main.merge(self.landsat_collection(k, start, end))
        fill = ee.ImageCollection([])
        for k in fill_keys:
            fill = fill.merge(self.landsat_collection(k, start, end))
        n_main, n_fill = ee_utils.get_info(ee.List([main.size(), fill.size()]))
        if n_main + n_fill == 0:
            raise RuntimeError(f"Không có cảnh Landsat mùa khô năm {year}")
        comp = main.median() if n_main else fill.median()
        if n_main and n_fill:
            comp = comp.unmask(fill.median())  # lấp chỗ trống bằng cảm biến phụ (vd Landsat 7)
        names = "+".join(LANDSAT_LABEL[k] for k in (main_keys if n_main else fill_keys))
        if n_main and n_fill:
            names += f" (lấp trống bằng {'+'.join(LANDSAT_LABEL[k] for k in fill_keys)})"
        return comp, f"Landsat {names}", int(n_main + n_fill), f"{start}..{end}", ""

    def sentinel2_composite(self, year):
        ee = self.ee
        if year < S2_FIRST_YEAR:
            raise RuntimeError("Sentinel-2 chỉ có từ năm 2015")
        start, end = season_window(year)
        note = ""
        if year == S2_FIRST_YEAR:  # chưa có mùa khô 2014–2015, dùng 6 tháng cuối 2015
            start, end, note = "2015-06-23", "2016-01-01", "Năm 2015 ghép ảnh 7–12/2015 (chưa có mùa khô)"
        use_sr = start >= "2017-04-01"
        cid = S2_SR if use_sr else S2_TOA

        def prep(img):
            if use_sr:
                scl = img.select("SCL")
                clear = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
            else:
                qa = img.select("QA60")
                clear = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
            return img.select(S2_BANDS, BANDS).divide(10000).updateMask(clear) \
                .copyProperties(img, ["system:time_start"])

        col = (ee.ImageCollection(cid).filterDate(start, end)
               .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_SCENE_CLOUD)).map(prep))
        n = ee_utils.get_info(col.size())
        if n == 0:
            raise RuntimeError(f"Không có cảnh Sentinel-2 năm {year}")
        if not use_sr:
            note = (note + "; " if note else "") + "Sentinel-2 L1C (TOA), chưa có SR"
        return col.median(), f"Sentinel-2 ({'SR' if use_sr else 'TOA'})", int(n), f"{start}..{end}", note

    def composite(self, sensor, year):
        return self.landsat_composite(year) if sensor == "landsat" else self.sentinel2_composite(year)

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
            ee.Reducer.sum().group(groupField=1, groupName="lop"), geom, scale, maxPixels=1e10)
        out = {c: 0.0 for c in range(0, 6)}
        conv = None
        info = ee_utils.get_info(grouped if prev_cls is None else ee.Dictionary({
            "g": grouped,
            "conv": area.updateMask(prev_cls.eq(1).And(cls.neq(1))).reduceRegion(
                ee.Reducer.sum(), geom, scale, maxPixels=1e10).get("area"),
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
            first_year = START_YEAR if sensor == "landsat" else S2_FIRST_YEAR
            if year - 1 >= first_year:
                try:
                    prev = self.classified(sensor, year - 1)[1]
                except Exception as e:
                    self.log(sensor_label, f"Không có ảnh năm {year - 1} để tính chuyển đổi: {e}")
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

    def export_tables(self):
        df = pd.DataFrame(self.checkpoint.results("lc_"))
        if df.empty:
            return df
        df = df.sort_values(["ma_huyen_gadm", "nguon_anh", "nam"]).reindex(columns=TABLE_COLS)
        with self.timer.step(self.NAME, "xuat_bang"):
            for f in export_multiformat_table(df, self.processed_dir / TABLE, logger=self.logger):
                self.log("LandCover", f"Xuất bảng {f}")
        return df

    def run(self, districts_df, years=None):
        years = sorted(years or YEARS)
        districts = self.prepare_districts(districts_df)
        self.log("LandCover", f"Bắt đầu: {len(districts)} huyện, năm {years[0]}–{years[-1]}, "
                              f"ảnh: {', '.join(self.sensors)} (phân lớp theo ngưỡng chỉ số, không ML)")
        self.connect()
        self.load_geometries(districts)
        for sensor in self.sensors:
            for year in years:
                if sensor == "sentinel2" and year < S2_FIRST_YEAR:
                    continue
                try:
                    self.process(sensor, year, districts)
                except Exception as e:
                    self.log(sensor, f"Lỗi năm {year}: {e}", error=True)
            if self.accuracy:
                self.run_accuracy(sensor, [y for y in years if sensor == "landsat" or y >= S2_FIRST_YEAR])
            self._cls_cache.clear()
        return self.export_tables()

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
