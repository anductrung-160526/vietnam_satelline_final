"""Province boundary and resume checks without Earth Engine/Drive credentials."""
import os
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import pandas as pd

with patch.dict(os.environ, {"VNGIS_SKIP_MAIN": "1"}):
    import vngis_2024 as v


def admin_table():
    return pd.DataFrame([
        {"GID_1": province, "NAME_1": name, "GID_3": gid, "NAME_3": gid, "TYPE_3": kind}
        for province, name, gid, kind in [
            ("VNM.10_1", "Đà Nẵng", "VNM.10.1.1_1", "Phường"),
            ("VNM.2_1", "CầnThơ", "VNM.2.1.2_1", "Xã"),
            ("VNM.1_1", "An Giang", "VNM.1.1.2_1", "Xã"),
            ("VNM.2_1", "CầnThơ", "VNM.2.1.1_1", "Phường"),
            ("VNM.1_1", "An Giang", "VNM.1.1.1_1", "Phường"),
        ]
    ])


class ProvinceStopTests(unittest.TestCase):
    def setUp(self):
        self.admin = admin_table()
        for name, value in (("MODE", "full"), ("START_FROM_PROVINCE", ""), ("PROVINCE_ORDER", "gadm"),
                            ("STOP_AFTER_PROVINCE", "Cần Thơ"),
                            ("STOP_EVENT", threading.Event()), ("STOP_REASON", [None]),
                            ("MAX_ATTEMPTS", 3)):
            p = patch.object(v, name, value)
            p.start()
            self.addCleanup(p.stop)
        targets = v.load_targets(self.admin)
        self.rows = {r["GID_3"]: r for r in targets.to_dict("records")}
        self.gids = list(self.rows)

    def test_names_and_exact_gid_select_same_boundary(self):
        for name in ("Cần Thơ", "CầnThơ", "Can Tho", "cantho", "VNM.2_1"):
            with self.subTest(name=name), patch.object(v, "STOP_AFTER_PROVINCE", name):
                selected = v.load_targets(self.admin)
                self.assertEqual(set(selected["GID_1"]), {"VNM.1_1", "VNM.2_1"})
                self.assertEqual(len(selected), 4)

    def test_unknown_province_fails_instead_of_running_nationwide(self):
        with patch.object(v, "STOP_AFTER_PROVINCE", "not-a-province"):
            with self.assertRaises(ValueError):
                v.load_targets(self.admin)

    def test_ambiguous_province_name_fails(self):
        duplicate = self.admin.copy()
        duplicate.loc[duplicate["GID_1"] == "VNM.10_1", "NAME_1"] = "Can Tho"
        with self.assertRaises(ValueError):
            v.load_targets(duplicate)

    def test_blank_boundary_keeps_nationwide_behavior(self):
        with patch.object(v, "STOP_AFTER_PROVINCE", ""):
            selected = v.load_targets(self.admin)
            rows = {r["GID_3"]: r for r in selected.to_dict("records")}
            self.assertEqual(len(v.next_round_jobs(list(rows), rows, {})), 5)

    def test_pilot_ignores_full_mode_boundary(self):
        with patch.object(v, "MODE", "pilot"), patch.object(v, "PILOT_N", 2), \
             patch.object(v, "STOP_AFTER_PROVINCE", "unknown"):
            selected = v.load_targets(self.admin)
        self.assertEqual(len(selected), 2)
        self.assertEqual(set(selected["TYPE_3"]), {"Phường", "Xã"})

    def test_only_first_unfinished_province_is_scheduled(self):
        jobs = v.next_round_jobs(self.gids, self.rows, {})
        self.assertEqual({row["GID_1"] for _, row, _ in jobs}, {"VNM.1_1"})
        self.assertEqual(len(jobs), 2)

    def test_resume_skips_completed_provinces_and_communes(self):
        statuses = {g: {"status": "done"} for g in self.gids if self.rows[g]["GID_1"] == "VNM.1_1"}
        statuses["VNM.2.1.1_1"] = {"status": "done"}
        statuses["VNM.2.1.2_1"] = {"status": "partial", "attempts": 1}
        jobs = v.next_round_jobs(self.gids, self.rows, statuses)
        self.assertEqual([g for g, _, _ in jobs], ["VNM.2.1.2_1"])

    def test_exhausted_or_missing_asset_commune_blocks_next_province(self):
        for state in ({"status": "partial", "attempts": 3}, {"status": "not_in_asset"}):
            with self.subTest(state=state):
                with self.assertRaises(v.ProvinceIncompleteError):
                    v.next_round_jobs(self.gids, self.rows, {"VNM.1.1.1_1": state})

    def test_all_selected_communes_done_produces_no_jobs(self):
        statuses = {g: {"status": "done"} for g in self.gids}
        self.assertEqual(v.next_round_jobs(self.gids, self.rows, statuses), [])


class ProvinceMainTests(unittest.TestCase):
    def setUp(self):
        self.admin = admin_table()
        self.states = {}
        self.rounds = []
        self.events = []
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)

        values = {
            "MODE": "full", "START_FROM_PROVINCE": "", "PROVINCE_ORDER": "gadm",
            "STOP_AFTER_PROVINCE": "Cần Thơ", "MAX_ATTEMPTS": 3,
            "LOCAL_ROOT": self.root.name, "PREFLIGHT": False, "MAX_RUNTIME_SEC": 0,
            "STOP_EVENT": threading.Event(), "STOP_REASON": [None],
            "ADMIN_DF": None, "ADMIN_BY_GID": {}, "PARTS_STAMP": None, "STATUS_FILE": None,
        }
        for name, value in values.items():
            p = patch.object(v, name, value)
            p.start()
            self.addCleanup(p.stop)
        mocks = {
            "setup_logging": Mock(), "init_earth_engine": Mock(), "init_storage": Mock(),
            "build_admin_table": Mock(return_value=self.admin),
            "load_all_status": Mock(side_effect=lambda: self.states.copy()),
            "install_signal_handlers": Mock(), "drive_stop_exists": Mock(return_value=False),
            "Uploader": Mock(), "run_round": Mock(side_effect=self.finish_round),
            "build_national_csv": Mock(side_effect=lambda: self.events.append("csv")),
            "rclone_sync_once": Mock(side_effect=lambda **kwargs: self.events.append("sync")),
        }
        for name, value in mocks.items():
            p = patch.object(v, name, value)
            p.start()
            self.addCleanup(p.stop)

    def finish_round(self, jobs, statuses):
        self.rounds.append([row["GID_1"] for _, row, _ in jobs])
        for gid, _, _ in jobs:
            self.states[gid] = {"status": "done"}
        return "ok"

    def test_main_finishes_can_tho_syncs_and_returns_zero(self):
        with self.assertLogs(v.log, level="INFO") as logs:
            self.assertEqual(v.main(), 0)
        self.assertEqual(self.rounds, [["VNM.1_1"] * 2, ["VNM.2_1"] * 2])
        self.assertNotIn("VNM.10.1.1_1", self.states)
        self.assertEqual(self.events[-2:], ["csv", "sync"])
        self.assertTrue(any("đã đồng bộ Drive và dừng" in line for line in logs.output))
        report = pd.read_csv(os.path.join(self.root.name, "_control", "progress.csv"))
        self.assertEqual(len(report), 4)
        self.assertTrue((report["status"] == "done").all())

    def test_deadline_resumes_same_boundary_and_never_schedules_later_province(self):
        original = self.finish_round

        def deadline(jobs, statuses):
            original(jobs, statuses)
            v.request_stop("deadline")
            return "stop"

        with patch.object(v, "run_round", side_effect=deadline):
            self.assertEqual(v.main(), 3)
        v.STOP_EVENT.clear()
        v.STOP_REASON[0] = None
        self.assertEqual(v.main(), 0)
        self.assertEqual(self.rounds, [["VNM.1_1"] * 2, ["VNM.2_1"] * 2])
        self.assertNotIn("VNM.10.1.1_1", self.states)

    def test_main_reports_failed_province_instead_of_success(self):
        self.states = {
            r["GID_3"]: {"status": "done"}
            for r in self.admin.to_dict("records") if r["GID_1"] != "VNM.10_1"
        }
        self.states["VNM.2.1.1_1"] = {"status": "partial", "attempts": 3}
        with self.assertLogs(v.log, level="ERROR"):
            self.assertEqual(v.main(), 1)
        self.assertEqual(self.rounds, [])
        self.assertEqual(self.events[-1], "sync")


if __name__ == "__main__":
    unittest.main()
