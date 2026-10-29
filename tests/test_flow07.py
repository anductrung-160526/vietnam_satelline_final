"""Province selection must keep flow 07 inside the requested province."""
import unittest
from unittest.mock import patch
from test_province_stop import admin_table, v

class Flow07Tests(unittest.TestCase):
    def test_full_and_pilot_stay_in_selected_province(self):
        for mode in ('pilot', 'full'):
            for province in ('Cần Thơ', 'Can Tho', 'VNM.2_1'):
                with self.subTest(mode=mode, province=province), patch.multiple(
                    v, MODE=mode, PROVINCE=province, STOP_AFTER_PROVINCE='', PILOT_N=10
                ):
                    selected = v.load_targets(admin_table())
                    self.assertEqual(len(selected), 2)
                    self.assertEqual(set(selected.GID_1), {'VNM.2_1'})

    def test_unknown_and_ambiguous_names_fail(self):
        data = admin_table()
        with patch.object(v, 'PROVINCE', 'unknown'), self.assertRaises(ValueError):
            v.load_targets(data)
        data.loc[data.GID_1 == 'VNM.10_1', 'NAME_1'] = 'Can Tho'
        with patch.object(v, 'PROVINCE', 'Cần Thơ'), self.assertRaises(ValueError):
            v.load_targets(data)

    def test_resume_only_schedules_selected_unfinished_commune(self):
        with patch.multiple(v, MODE='full', PROVINCE='VNM.2_1', STOP_AFTER_PROVINCE=''):
            rows = {r['GID_3']: r for r in v.load_targets(admin_table()).to_dict('records')}
            states = {'VNM.2.1.1_1': {'status': 'done'}}
            jobs = v.next_round_jobs(list(rows), rows, states)
            self.assertEqual([g for g, _, _ in jobs], ['VNM.2.1.2_1'])
