import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import audit_drive as audit
import vngis_2024 as v


ROWS = [dict(GID_1="VNM.1_1", NAME_1="An Giang", GID_2="VNM.1.1_1", NAME_2="An Phú", TYPE_2="Huyện"),
        dict(GID_1="VNM.2_1", NAME_1="Bạc Liêu", GID_2="VNM.2.1_1", NAME_2="Đông Hải", TYPE_2="Huyện")]


def csv_text(kind, periods=None):
    columns = v.DAY_COLUMNS if kind == "day" else v.NIGHT_COLUMNS
    rows = []
    for year, month in (v.PERIODS if periods is None else periods):
        row = {key: 0 for key in columns}
        row.update(ROWS[0], YEAR=year, MONTH=month, DATA_STATUS="ok", ERROR="")
        # Rolling/growth nulls are legitimate, unlike missing radiance/mean metrics.
        if kind == "night":
            row.update(TNL_MA3="", TNL_MOM_GROWTH_PCT="", SPATIAL_CV="")
        rows.append(row)
    return pd.DataFrame(rows, columns=columns).to_csv(index=False)


def full_inventory():
    ctx = v.build_ctx(ROWS[0])
    return [{"Path": f"{ctx[f'rel_{kind}_dir']}/{naming(ctx, period)}", "Size": 1500,
             "ModTime": "2026-10-09T18:00:00Z", "IsDir": False}
            for kind, naming in (("day", v.day_name), ("night", v.night_name)) for period in v.PERIODS]


class AuditTests(unittest.TestCase):
    def report(self, inventory=None, day=None, night=None):
        return audit.build_reports(pd.DataFrame(ROWS), full_inventory() if inventory is None else inventory,
                                   csv_text("day") if day is None else day,
                                   csv_text("night") if night is None else night,
                                   "2026-10-10T08:00:00Z", "gdrive:dataset")

    def test_reports_include_entirely_missing_province_and_true_complete_district(self):
        districts, provinces, files = self.report()
        self.assertTrue(districts.iloc[0].inventory_complete)
        self.assertFalse(districts.iloc[1].inventory_complete)
        self.assertEqual(provinces.iloc[1].night_tiff_on_drive, 0)
        self.assertEqual(provinces.iloc[1].tiff_expected_per_kind, 12)
        self.assertEqual(len(files), 24)
        self.assertNotEqual(files.iloc[0].drive_modtime, files.iloc[0].observed_at_utc)

    def test_directory_and_wrong_path_do_not_prove_month_uploaded(self):
        inv = full_inventory()
        inv[0]["IsDir"] = True
        inv[1]["Path"] = "wrong/" + inv[1]["Path"]
        districts, _, _ = self.report(inventory=inv)
        self.assertEqual(districts.iloc[0].day_tiff_on_drive, 10)
        self.assertIn("2024-07", districts.iloc[0].day_tiff_missing_months)
        self.assertFalse(districts.iloc[0].inventory_complete)

    def test_duplicate_and_zero_size_tiff_are_not_complete(self):
        inv = full_inventory()
        inv.append(dict(inv[0]))
        inv[1]["Size"] = 0
        districts, _, files = self.report(inventory=inv)
        self.assertEqual(districts.iloc[0].day_tiff_on_drive, 10)
        self.assertEqual(districts.iloc[0].day_tiff_duplicate_months, "2024-07")
        self.assertEqual(len(files), 25)

    def test_csv_duplicates_null_metrics_and_no_data_do_not_count(self):
        frame = pd.read_csv(io.StringIO(csv_text("day")), keep_default_na=False)
        frame.loc[1, "BLUE_mean"] = float("nan")
        frame.loc[2, "DATA_STATUS"] = "no_data"
        frame.loc[3, "RED_mean"] = float("inf")
        frame = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
        result = audit.csv_months(frame.to_csv(index=False), "day")
        self.assertEqual(len(result[ROWS[0]["GID_2"]]), 8)
        self.assertEqual(len(audit.csv_months(csv_text("night"), "night")[ROWS[0]["GID_2"]]), 12)

    def test_missing_csv_is_unconfirmed_and_invalid_schema_raises(self):
        self.assertEqual(audit.csv_months(None, "day"), {})
        with self.assertRaisesRegex(ValueError, "schema"):
            audit.csv_months("GID_2,YEAR,MONTH\nVNM.1.1_1,2024,7\n", "day")

    def test_read_errors_are_not_reported_as_missing_files(self):
        result = SimpleNamespace(returncode=1, stdout="", stderr="HTTP 403 RATE_LIMIT_EXCEEDED")
        with patch.object(v, "_run_rclone", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "inventory"):
                audit.read_inventory("gdrive:dataset")
            with self.assertRaisesRegex(RuntimeError, "Không đọc"):
                audit.read_remote_csv("gdrive:dataset", "day", [{"Path": "CSV/day_indices.csv"}])

    def test_all_audit_remote_commands_are_read_only(self):
        listing = [{"Path": "CSV/day_indices.csv", "Size": 500}]
        results = [SimpleNamespace(returncode=0, stdout=json.dumps(listing), stderr=""),
                   SimpleNamespace(returncode=0, stdout="\ufeff" + csv_text("day"), stderr="")]
        with patch.object(v, "_run_rclone", side_effect=results) as command, \
             patch.object(v, "init_earth_engine") as initialize:
            inventory = audit.read_inventory("gdrive:dataset")
            text = audit.read_remote_csv("gdrive:dataset", "day", inventory)
        self.assertEqual([call.args[0][0] for call in command.call_args_list], ["lsjson", "cat"])
        self.assertFalse(text.startswith("\ufeff"))
        initialize.assert_not_called()

    def test_upload_heartbeat_shuts_down_on_timeout(self):
        with self.assertLogs(v.log, level="INFO") as logs:
            with self.assertRaisesRegex(RuntimeError, "timeout"):
                with v.upload_heartbeat(["copy", "local", "gdrive:dataset"]):
                    raise RuntimeError("timeout")
        self.assertTrue(any("Bắt đầu" in line for line in logs.output))
        self.assertTrue(any("kết thúc" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
