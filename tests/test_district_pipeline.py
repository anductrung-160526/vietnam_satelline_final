"""Kiểm tra pipeline cấp huyện mà không cần tài khoản GEE (giả lập Earth Engine)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd

from pipeline_core import ee_utils
from pipeline_core.admin_boundaries import attach_gso_codes, filter_districts, match_key
from pipeline_core.utils import CheckpointManager, pct_change_consecutive, StepTimer
from run_pipeline import parse_years, build_parser
from VN_LandCover_Panel_2004_2025.code.accuracy_assessment import metrics_from_matrix
from VN_LandCover_Panel_2004_2025.code.landcover_pipeline import season_window, landsat_sources, month_window


def districts():
    return pd.DataFrame([
        {"ma_tinh": "VNM.27_1", "ten_tinh": "HàNội", "ma_huyen": "VNM.27.1_1", "ten_huyen": "BaĐình", "loai_huyen": "Quận"},
        {"ma_tinh": "VNM.27_1", "ten_tinh": "HàNội", "ma_huyen": "VNM.27.2_1", "ten_huyen": "Ba Vì", "loai_huyen": "Huyện"},
        {"ma_tinh": "VNM.27_1", "ten_tinh": "HàNội", "ma_huyen": "VNM.27.3_1", "ten_huyen": "Từ Liêm", "loai_huyen": "Huyện"},
        {"ma_tinh": "VNM.1_1", "ten_tinh": "An Giang", "ma_huyen": "VNM.1.1_1", "ten_huyen": "An Phú", "loai_huyen": "Huyện"},
    ])


class BoundaryTests(unittest.TestCase):
    def test_match_key_ignores_accents_and_spaces(self):
        self.assertEqual(match_key("HàNội"), match_key("Hà Nội"))
        self.assertEqual(match_key("Ứng Hòa"), match_key("Ứng Hoà"))

    def test_gso_codes_attached_and_unknown_left_blank(self):
        df = attach_gso_codes(districts())
        codes = dict(zip(df["ten_huyen"], df["ma_huyen_tk"]))
        self.assertEqual(codes["BaĐình"], "001")
        self.assertEqual(codes["Ba Vì"], "271")
        self.assertEqual(codes["Từ Liêm"], "")  # tên cũ, không tự sinh mã
        self.assertEqual(df.loc[0, "ma_tinh_tk"], "01")

    def test_filter_by_province(self):
        df = attach_gso_codes(districts())
        self.assertEqual(len(filter_districts(df, province="Hà Nội")), 3)
        self.assertEqual(list(filter_districts(df, districts="Ba Vì")["ma_huyen"]), ["VNM.27.2_1"])


class ProvinceLevelTests(unittest.TestCase):
    def test_province_codes_cover_63(self):
        from pipeline_core.admin_boundaries import load_province_codes
        codes = load_province_codes()
        self.assertEqual(len(codes), 63)
        self.assertEqual(codes[match_key("HồChíMinh")], "79")
        self.assertEqual(codes[match_key("BàRịa-VũngTàu")], "77")

    def test_image_folder_is_province_name(self):
        from pipeline_core.admin_boundaries import province_folder_name
        self.assertEqual(province_folder_name({"ma_tinh_tk": "01", "ten_tinh": "HàNội"}), "Hà Nội")
        self.assertEqual(province_folder_name({"ma_tinh_tk": "79", "ten_tinh": "HồChíMinh"}), "Hồ Chí Minh")

    def test_tif_selector(self):
        from run_pipeline import build_parser
        a = build_parser().parse_args(["--tif", "night", "--tif-dir", "E:/VNGIS_Data"])
        self.assertEqual((a.tif, a.tif_dir), ("night", "E:/VNGIS_Data"))

    def test_province_export_renames_columns(self):
        from pipeline_core.base_pipeline import BasePipeline
        p = BasePipeline.__new__(BasePipeline)
        p.level = "tinh"
        df = pd.DataFrame([{"ma_tinh": "01", "ten_tinh": "Hà Nội", "ma_huyen": "01", "ten_huyen": "Hà Nội",
                            "ma_huyen_gadm": "VNM.27_1", "nam": 2024}])
        out = p.finalize(df)
        self.assertEqual(list(out.columns), ["ma_tinh", "ten_tinh", "ma_tinh_gadm", "nam"])
        self.assertEqual(p.table_name("vietnam_district_day_indices_2004_2025"),
                         "vietnam_province_day_indices_2004_2025")
        p.level = "huyen"
        self.assertIs(p.finalize(df), df)


class UtilTests(unittest.TestCase):
    def test_parse_years(self):
        self.assertEqual(parse_years("2024"), [2024])
        self.assertEqual(parse_years("2010-2012,2024"), [2010, 2011, 2012, 2024])
        self.assertEqual(len(parse_years("")), 22)

    def test_pct_change_only_consecutive_years(self):
        df = pd.DataFrame({"g": ["a"] * 3 + ["b"], "nam": [2010, 2011, 2013, 2011], "v": [100.0, 110.0, 121.0, 5.0]})
        out = pct_change_consecutive(df, "g", "v").tolist()
        self.assertTrue(pd.isna(out[0]))
        self.assertEqual(out[1], 10.0)
        self.assertTrue(pd.isna(out[2]))  # thiếu năm 2012 -> không tính
        self.assertTrue(pd.isna(out[3]))

    def test_checkpoint_resume_keeps_records(self):
        with tempfile.TemporaryDirectory() as d:
            cp = CheckpointManager(Path(d) / "cp.jsonl")
            cp.mark_completed("H1", 2024, "ntl_annual", {"sol_ntl": 1.5})
            cp.mark_completed("H1", 2024, "ntl_month_01", {"sol_ntl": 0.2})
            cp2 = CheckpointManager(Path(d) / "cp.jsonl")
            self.assertTrue(cp2.is_completed("H1", 2024, "ntl_annual"))
            self.assertEqual(cp2.results("ntl_annual"), [{"sol_ntl": 1.5}])

    def test_timer_records_failures(self):
        t = StepTimer()
        with self.assertRaises(ValueError):
            with t.step("p", "b"):
                raise ValueError
        self.assertEqual(t.rows[0]["trang_thai"], "loi")

    def test_hanoi_parser_defaults(self):
        p = build_parser()
        p.set_defaults(province="Hà Nội", years="2024")
        a = p.parse_args([])
        self.assertEqual((a.province, a.years, a.day_sensors), ("Hà Nội", "2024", "auto"))


class EarthEngineHelperTests(unittest.TestCase):
    def test_retry_then_success(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("429 Too Many Requests")
            return "ok"
        self.assertEqual(ee_utils.with_retry(flaky, sleep=lambda s: None), "ok")
        self.assertEqual(len(calls), 3)

    def test_non_retryable_raises_immediately(self):
        calls = []

        def bad():
            calls.append(1)
            raise RuntimeError("Image.select: band not found")
        with self.assertRaises(RuntimeError):
            ee_utils.with_retry(bad, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)

    def test_tile_plan_scales_with_size(self):
        small = ee_utils.plan_tiles((105.8, 21.0, 105.9, 21.1), 30, 6, "int16")
        big = ee_utils.plan_tiles((105.3, 20.5, 106.0, 21.4), 10, 6, "int16")
        self.assertEqual(len(small), 1)
        self.assertGreater(len(big), 4)

    def test_download_splits_when_too_large(self):
        geom = {"type": "Polygon", "coordinates": [[[105.8, 21.0], [105.9, 21.0], [105.9, 21.1], [105.8, 21.0]]]}
        attempts = []

        def fake_tile(ee, image, bbox, scale, dest, crs):
            attempts.append(bbox)
            if len(attempts) == 1:
                raise RuntimeError("Total request size (60000000 bytes) must be less than or equal to 50331648 bytes.")
            Path(dest).write_bytes(b"x")

        def fake_merge(parts, dest):
            Path(dest).write_bytes(b"merged" * len(parts))

        with tempfile.TemporaryDirectory() as d, \
                patch.object(ee_utils, "_download_tile", fake_tile), patch.object(ee_utils, "merge_tifs", fake_merge):
            size = ee_utils.download_image(MagicMock(), MagicMock(), geom, 30, Path(d) / "a.tif")
        self.assertEqual(len(attempts), 5)  # 1 lần lỗi + 4 ô
        self.assertEqual(size, len(b"merged") * 4)


class CompressionTests(unittest.TestCase):
    def test_lossless_compression_keeps_pixels(self):
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin
        y, x = np.mgrid[0:300, 0:300]
        arr = np.stack([(1500 + 500 * np.sin(x / 30) + i).astype(np.int16) for i in range(6)])
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.tif"
            with rasterio.open(f, "w", driver="GTiff", height=300, width=300, count=6, dtype="int16",
                               crs="EPSG:4326", transform=from_origin(105, 21, 1e-4, 1e-4)) as o:
                o.write(arr)
            before = f.stat().st_size
            ee_utils.compress_tif(f)
            with rasterio.open(f) as r:
                self.assertTrue(np.array_equal(r.read(), arr))
                self.assertEqual(r.compression.value.lower(), "deflate")
            self.assertLess(f.stat().st_size, before)

    def test_compress_ignores_unreadable_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "bad.tif"
            f.write_bytes(b"x")
            ee_utils.compress_tif(f)
            self.assertEqual(f.read_bytes(), b"x")


class LandCoverRuleTests(unittest.TestCase):
    def test_dry_season_window(self):
        self.assertEqual(season_window(2024), ("2023-11-01", "2024-05-01"))

    def test_auto_sensor_by_year(self):
        from VN_LandCover_Panel_2004_2025.code.landcover_pipeline import LandCoverPipeline, sensor_for_year
        self.assertEqual((sensor_for_year(2014), sensor_for_year(2015), sensor_for_year(2024)),
                         ("landsat", "sentinel2", "sentinel2"))
        p = LandCoverPipeline.__new__(LandCoverPipeline)
        p.auto, p.sensors = True, ("auto",)
        self.assertEqual(p.plan([2024]), [("sentinel2", [2024])])
        self.assertEqual(p.plan([2004, 2014, 2015]), [("landsat", [2004, 2014]), ("sentinel2", [2015])])
        old = pd.DataFrame({"nam": [2024, 2024, 2010], "nguon_anh": ["Landsat 8+9", "Sentinel-2 (SR)", "Landsat 5"]})
        self.assertEqual(list(p._keep_auto_source(old)["nguon_anh"]), ["Sentinel-2 (SR)", "Landsat 5"])

    def test_combined_annual_monthly(self):
        from pipeline_core.utils import combine_annual_monthly
        a = pd.DataFrame({"ma_huyen_gadm": ["A"], "nam": [2024], "sol_ntl": [1.0]})
        m = pd.DataFrame({"ma_huyen_gadm": ["A", "A"], "nam": [2024, 2024], "thang": [2, 1], "sol_ntl": [.1, .2]})
        df = combine_annual_monthly(a, m)
        self.assertEqual(list(df["ky"]), ["Năm", "Tháng", "Tháng"])
        self.assertEqual(list(df["thang"].fillna(0)), [0, 1, 2])

    def test_month_window(self):
        from datetime import date
        self.assertEqual(month_window(2024, 12), (date(2024, 12, 1), date(2025, 1, 1)))
        self.assertEqual(month_window(2024, 2), (date(2024, 2, 1), date(2024, 3, 1)))

    def test_hanoi_defaults_monthly(self):
        import run_hanoi_pilot
        with patch.object(run_hanoi_pilot, "run", side_effect=SystemExit) as r:
            with self.assertRaises(SystemExit):
                run_hanoi_pilot.main([])
        args = r.call_args[0][0]
        self.assertTrue(args.monthly and args.monthly_tif)

    def test_landsat_sources(self):
        self.assertEqual(landsat_sources(2005), (["L5"], ["L7"]))
        self.assertEqual(landsat_sources(2012), (["L7"], ["L5"]))
        self.assertEqual(landsat_sources(2024), (["L8", "L9"], ["L7"]))

    def test_accuracy_metrics(self):
        m = metrics_from_matrix([[8, 2], [1, 9]])
        self.assertAlmostEqual(m["oa"], 0.85)
        self.assertAlmostEqual(m["kappa"], 0.7)
        self.assertAlmostEqual(m["pa"][0], 0.8)

    def test_no_machine_learning_or_random_in_pipelines(self):
        root = Path(__file__).resolve().parent.parent
        for f in ["VN_LandCover_Panel_2004_2025/code/landcover_pipeline.py",
                  "VN_LandCover_Panel_2004_2025/code/accuracy_assessment.py",
                  "VN_NTL_Panel_2004_2025/code/ntl_pipeline.py"]:
            text = (root / f).read_text(encoding="utf-8")
            for banned in ("Classifier", "smileRandomForest", "np.random", "hash("):
                self.assertNotIn(banned, text, f"{banned} trong {f}")


if __name__ == "__main__":
    unittest.main()
