"""Hiệu chỉnh liên kết DMSP–VIIRS: kế hoạch quản lý dữ liệu yêu cầu chuỗi thống nhất 2004–2025.

DMSP là DN 0–63 và bão hòa ở lõi đô thị; VIIRS là bức xạ và không bão hòa. Nối thẳng hai
đoạn vào một chuỗi tạo ra một bước nhảy giả ở năm 2013–2014, dễ bị đọc nhầm thành biến
động kinh tế. Mô-đun này khớp hàm lũy thừa trên năm chồng lấn 2013 rồi quy DMSP về thang
VIIRS; số liệu VIIRS không bị chạm tới.
"""
import csv
import json
import math
import random
import tempfile
import unittest
from pathlib import Path

from task_pipeline import harmonize


class FitTest(unittest.TestCase):

    def _pairs(self, a=2.5, b=1.3, n=63, noise=0.0, seed=7):
        random.seed(seed)
        out = []
        for _ in range(n):
            d = random.uniform(5, 800)
            v = a * d ** b
            if noise:
                v *= random.uniform(1 - noise, 1 + noise)
            out.append((d, v))
        return out

    def test_it_recovers_a_known_power_law(self):
        model = harmonize.fit(self._pairs())
        self.assertAlmostEqual(model['a'], 2.5, places=4)
        self.assertAlmostEqual(model['b'], 1.3, places=4)
        self.assertAlmostEqual(model['r2'], 1.0, places=6)
        self.assertEqual(model['so_tinh'], 63)
        self.assertEqual(model['nam_chong_lan'], 2013)

    def test_it_still_recovers_the_shape_with_noise(self):
        model = harmonize.fit(self._pairs(noise=0.10))
        self.assertAlmostEqual(model['b'], 1.3, delta=0.05)
        self.assertGreater(model['r2'], 0.99)

    def test_too_few_provinces_means_no_model_rather_than_a_bad_one(self):
        """Thà không hiệu chỉnh còn hơn hiệu chỉnh bằng một mô hình không đáng tin."""
        self.assertIsNone(harmonize.fit(self._pairs(n=10)))
        self.assertIsNone(harmonize.fit([]))

    def test_non_positive_pairs_are_dropped_not_crashed_on(self):
        """log(0) không tồn tại; tỉnh tối om cũng không nói gì về quan hệ hai thang đo."""
        pairs = self._pairs(n=40) + [(0, 5.0), (5.0, 0), (-1, 2), (None, 3), (4, None)]
        model = harmonize.fit(pairs)
        self.assertEqual(model['so_tinh'], 40)


class ApplyTest(unittest.TestCase):

    MODEL = {'phuong_phap': harmonize.METHOD, 'a': 2.5, 'b': 1.3, 'r2': 1.0,
             'so_tinh': 63, 'nam_chong_lan': 2013, 'huong': 'DMSP -> thang VIIRS'}

    def _rows(self, dmsp=100.0, viirs=1000.0):
        return [dict(ma_tinh='01', nam=y, nguon_anh='DMSP' if y <= 2013 else 'VIIRS',
                     sol_ntl=dmsp if y <= 2013 else viirs, dt_tu_nhien_km2=10.0)
                for y in range(2011, 2017)]

    def test_viirs_values_are_never_altered(self):
        """VIIRS là thang đích: một phép biến đổi chạm vào nó là sai."""
        rows = harmonize.apply(self._rows(), self.MODEL)
        for row in rows:
            if row['nguon_anh'] == 'VIIRS':
                self.assertEqual(row['sol_ntl_hc'], row['sol_ntl'])

    def test_dmsp_values_move_onto_the_viirs_scale(self):
        rows = harmonize.apply(self._rows(), self.MODEL)
        dmsp = [r for r in rows if r['nguon_anh'] == 'DMSP'][0]
        self.assertAlmostEqual(dmsp['sol_ntl_hc'], 2.5 * 100.0 ** 1.3, places=2)
        self.assertNotEqual(dmsp['sol_ntl_hc'], dmsp['sol_ntl'])

    def test_the_original_columns_survive_for_comparison(self):
        rows = harmonize.apply(self._rows(), self.MODEL)
        self.assertTrue(all(r['sol_ntl'] in (100.0, 1000.0) for r in rows))

    def test_the_fake_jump_at_the_satellite_change_disappears(self):
        """Đây chính là lý do phải hiệu chỉnh: +900% giả phải biến mất."""
        rows = harmonize.apply(self._rows(), self.MODEL)
        theo_nam = {r['nam']: r for r in rows}
        tho = 100 * (1000.0 / 100.0 - 1)
        self.assertEqual(tho, 900.0)
        self.assertLess(abs(theo_nam[2014]['thay_doi_ntl_hc']), 50.0)

    def test_density_is_recomputed_from_the_harmonised_value(self):
        rows = harmonize.apply(self._rows(), self.MODEL)
        for row in rows:
            self.assertAlmostEqual(row['mat_do_ntl_hc'], row['sol_ntl_hc'] / 10.0, places=5)

    def test_without_a_model_the_rows_say_so_instead_of_pretending(self):
        rows = harmonize.apply(self._rows(), None)
        for row in rows:
            self.assertIsNone(row['sol_ntl_hc'])
            self.assertEqual(row['hieu_chinh'], 'KHONG_DU_DU_LIEU_CHONG_LAN')

    def test_provinces_are_harmonised_independently(self):
        rows = self._rows() + [dict(r, ma_tinh='27') for r in self._rows(dmsp=50.0)]
        harmonize.apply(rows, self.MODEL)
        mot = [r for r in rows if r['ma_tinh'] == '01' and r['nam'] == 2012][0]
        hai = [r for r in rows if r['ma_tinh'] == '27' and r['nam'] == 2012][0]
        self.assertNotEqual(mot['sol_ntl_hc'], hai['sol_ntl_hc'])
        self.assertIsNone([r for r in rows if r['ma_tinh'] == '27'][0]['thay_doi_ntl_hc'])


class EndToEndTest(unittest.TestCase):

    def _write(self, directory):
        from province_pipeline.sources import NTL_PACKAGE
        processed = Path(directory) / NTL_PACKAGE / 'data_processed'
        processed.mkdir(parents=True, exist_ok=True)
        random.seed(11)
        overlap = []
        for i in range(63):
            d = random.uniform(10, 900)
            overlap.append({'ma_tinh': f'{i + 1:02}', 'nam': 2013,
                            'sol_dmsp': round(d, 4), 'sol_viirs': round(2.5 * d ** 1.3, 4)})
        with (processed / 'ntl_overlap_2013.csv').open('w', encoding='utf-8-sig',
                                                       newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(overlap[0]))
            writer.writeheader(); writer.writerows(overlap)

        annual = []
        for i in range(63):
            for year in range(2004, 2026):
                annual.append({'ma_tinh': f'{i + 1:02}', 'ten_tinh': f'T{i}', 'nam': year,
                               'nguon_anh': 'DMSP' if year <= 2013 else 'VIIRS',
                               'sol_ntl': 100.0 + i, 'dt_tu_nhien_km2': 10.0,
                               'hieu_chinh': 'PENDING'})
        with (processed / 'ntl_annual.csv').open('w', encoding='utf-8-sig',
                                                 newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(annual[0]))
            writer.writeheader(); writer.writerows(annual)
        return processed

    def test_the_run_adds_columns_and_records_the_model(self):
        from province_pipeline.sources import NTL_PACKAGE
        with tempfile.TemporaryDirectory() as directory:
            processed = self._write(directory)
            model, count = harmonize.run(directory)
            self.assertAlmostEqual(model['b'], 1.3, places=4)
            self.assertEqual(count, 63 * 22)

            with (processed / 'ntl_annual.csv').open(encoding='utf-8-sig') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 63 * 22)
            for field in ('sol_ntl_hc', 'mat_do_ntl_hc', 'thay_doi_ntl_hc'):
                self.assertIn(field, rows[0])
            self.assertTrue(all(r['hieu_chinh'] == harmonize.METHOD for r in rows))
            # Cột gốc không bị ghi đè.
            self.assertTrue(all(float(r['sol_ntl']) >= 100.0 for r in rows))

            meta = json.loads((Path(directory) / NTL_PACKAGE / 'metadata'
                               / 'hieu_chinh_dmsp_viirs.json').read_text(encoding='utf-8'))
            self.assertEqual(meta['phuong_phap'], harmonize.METHOD)
            self.assertEqual(meta['so_tinh'], 63)

    def test_running_twice_does_not_duplicate_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            processed = self._write(directory)
            harmonize.run(directory)
            harmonize.run(directory)
            with (processed / 'ntl_annual.csv').open(encoding='utf-8-sig') as stream:
                header = next(csv.reader(stream))
            self.assertEqual(len(header), len(set(header)))

    def test_a_missing_overlap_table_stops_with_an_explanation(self):
        with tempfile.TemporaryDirectory() as directory:
            processed = self._write(directory)
            (processed / 'ntl_overlap_2013.csv').unlink()
            with self.assertRaises(SystemExit) as thoat:
                harmonize.run(directory)
            self.assertIn('ntl_overlap_2013', str(thoat.exception))


if __name__ == '__main__':
    unittest.main()
