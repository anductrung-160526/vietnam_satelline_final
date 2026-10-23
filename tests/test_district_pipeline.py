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
        self.assertEqual((a.province, a.years, a.day_sensors), ("Hà Nội", "2024", "landsat,sentinel2"))


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


class LandCoverRuleTests(unittest.TestCase):
    def test_dry_season_window(self):
        self.assertEqual(season_window(2024), ("2023-11-01", "2024-05-01"))

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
