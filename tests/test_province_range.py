"""Branch range checks using province counts from the actual GADM 4.1 DBF."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import pandas as pd

with patch.dict(os.environ, {"VNGIS_SKIP_MAIN": "1"}):
    import vngis_2024 as v

EXPECTED = ['VNM.29_1', 'VNM.22_1', 'VNM.23_1', 'VNM.24_1', 'VNM.25_1', 'VNM.30_1', 'VNM.31_1', 'VNM.32_1', 'VNM.33_1', 'VNM.34_1', 'VNM.36_1']


def gadm_fixture():
    counts = pd.read_csv(Path(__file__).parent / "fixtures" / "gadm41_vnm_provinces.csv")
    return pd.DataFrame([
        {"GID_1": row.GID_1, "NAME_1": row.NAME_1,
         "GID_3": row.GID_1.replace("_1", f".1.{i + 1}_1"),
         "NAME_3": f"Commune {i + 1}", "TYPE_3": "Phường" if i % 2 else "Xã"}
        for row in counts.itertuples() for i in range(row.communes)
    ])


class ProvinceRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = gadm_fixture()

    def setUp(self):
        p = patch.multiple(v, MODE="full", START_FROM_PROVINCE='Hà Tĩnh',
                           STOP_AFTER_PROVINCE='Lai Châu', PROVINCE_ORDER="alphabet")
        p.start()
        self.addCleanup(p.stop)

    def test_real_gadm_counts_and_exact_inclusive_scope(self):
        targets = v.load_targets(self.admin)
        self.assertEqual(len(self.admin), 11163)
        self.assertEqual(self.admin.GID_1.nunique(), 63)
        self.assertEqual(len(targets), 2012)
        self.assertEqual(list(targets.GID_1.drop_duplicates()), EXPECTED)
        self.assertEqual((targets.GID_1 == 'VNM.34_1').sum(), 102)
        self.assertEqual((targets.GID_1 == 'VNM.36_1').sum(), 108)

    def test_pilot_stays_in_scope_even_when_requesting_more_than_scope(self):
        with patch.multiple(v, MODE="pilot", PILOT_N=3000):
            targets = v.load_targets(self.admin)
        self.assertEqual(len(targets), 2012)
        self.assertEqual(set(targets.GID_1), set(EXPECTED))

    def test_small_pilot_starts_at_range_beginning_and_samples_both_types(self):
        with patch.multiple(v, MODE="pilot", PILOT_N=2):
            targets = v.load_targets(self.admin)
        self.assertEqual(set(targets.GID_1), {'VNM.29_1'})
        self.assertEqual(set(targets.TYPE_3), {"Xã", "Phường"})

    def test_endpoint_names_without_accents_and_exact_ids(self):
        for start, end in (('ha tinh', 'lai chau'), ('VNM.29_1', 'VNM.36_1')):
            with self.subTest(start=start), patch.multiple(v, START_FROM_PROVINCE=start,
                                                         STOP_AFTER_PROVINCE=end):
                self.assertEqual(v.province_boundary(self.admin, end), set(EXPECTED))

    def test_reversed_range_fails(self):
        with patch.multiple(v, START_FROM_PROVINCE='Lai Châu', STOP_AFTER_PROVINCE='Hà Tĩnh'):
            with self.assertRaises(ValueError):
                v.load_targets(self.admin)

    def test_missing_start_fails_in_both_modes(self):
        for mode in ("full", "pilot"):
            with self.subTest(mode=mode), patch.multiple(v, MODE=mode, START_FROM_PROVINCE="Unknown"):
                with self.assertRaises(ValueError):
                    v.load_targets(self.admin)

    def test_resume_schedules_penultimate_province_before_final_province(self):
        targets = v.load_targets(self.admin)
        rows = {r["GID_3"]: r for r in targets.to_dict("records")}
        states = {g: {"status": "done"} for g, row in rows.items()
                  if row["GID_1"] in EXPECTED[:-2]}
        jobs = v.next_round_jobs(list(rows), rows, states)
        self.assertEqual({r["GID_1"] for _, r, _ in jobs}, {'VNM.34_1'})
        self.assertEqual(len(jobs), 102)

    def test_full_pipeline_resumes_same_scope_and_finishes_at_range_end(self):
        states, rounds = {}, []
        with tempfile.TemporaryDirectory() as root:
            with patch.multiple(v, LOCAL_ROOT=root, PREFLIGHT=False, MAX_RUNTIME_SEC=0,
                                STOP_EVENT=threading.Event(), STOP_REASON=[None],
                                ADMIN_DF=None, ADMIN_BY_GID={}, PARTS_STAMP=None, STATUS_FILE=None):
                def finish(jobs, statuses):
                    rounds.append({row["GID_1"] for _, row, _ in jobs})
                    for gid, _, _ in jobs:
                        states[gid] = {"status": "done"}
                    if len(rounds) == 1:
                        v.request_stop("deadline")
                        return "stop"
                    return "ok"

                mocks = dict(
                    setup_logging=Mock(), init_earth_engine=Mock(), init_storage=Mock(),
                    build_admin_table=Mock(return_value=self.admin),
                    load_all_status=Mock(side_effect=lambda: states.copy()),
                    install_signal_handlers=Mock(), drive_stop_exists=Mock(return_value=False),
                    Uploader=Mock(), run_round=Mock(side_effect=finish),
                    build_national_csv=Mock(), rclone_sync_once=Mock(),
                )
                with patch.multiple(v, **mocks):
                    self.assertEqual(v.main(), 3)
                    self.assertEqual(rounds, [{'VNM.29_1'}])
                    v.STOP_EVENT.clear()
                    v.STOP_REASON[0] = None
                    self.assertEqual(v.main(), 0)
                    self.assertEqual(rounds, [{gid} for gid in EXPECTED])
                    self.assertEqual(len(states), 2012)
                    report = pd.read_csv(Path(root) / "_control" / "progress.csv")
                    self.assertEqual(len(report), 2012)
                    self.assertTrue((report.status == "done").all())
                    self.assertEqual(set(report.GID_1), set(EXPECTED))
                    self.assertTrue(mocks["rclone_sync_once"].call_args.kwargs["final"])


if __name__ == "__main__":
    unittest.main()
