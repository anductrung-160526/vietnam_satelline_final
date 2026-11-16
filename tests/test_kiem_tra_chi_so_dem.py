"""Script soi bảng chỉ số đêm phải THẬT SỰ bắt được lỗi, không chỉ in ĐẠT.

Một script kiểm tra luôn báo đạt còn tệ hơn không có: nó tạo cảm giác an toàn giả.
Vì vậy mỗi phép kiểm ở đây được thử trên cả bảng đúng lẫn bảng hỏng.
"""
import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / 'scripts' / 'kiem_tra_chi_so_dem.py'
A, B = 0.00682, 1.3558          # mô hình hiệu chỉnh thật của bộ dữ liệu
COLS = ['province_code', 'province_name', 'year', 'source', 'sol', 'sol_raw', 'sol_cal',
        'sol_density', 'lit_area_pct', 'sol_change_pct', 'sol_change_cal_pct', 'rad_cv']
TEN = {1: 'Hà Nội', 2: 'Hồ Chí Minh'}


def bang(sua=None):
    """Bảng 63 tỉnh x 22 năm hợp lệ; sua(row) được gọi để bẻ gãy một thứ."""
    rows = []
    for i in range(1, 64):
        quy = (3 if i <= 2 else 1) * (1 + (i % 7) / 10)
        truoc = truoc_hc = None
        for year in range(2004, 2026):
            src = 'DMSP' if year <= 2013 else 'VIIRS'
            that = quy * (1 + 0.06 * (year - 2004)) * 5000
            sol = that if src == 'VIIRS' else (that / A) ** (1 / B)
            row = dict(
                province_code=f'{i:02}', province_name=TEN.get(i, f'Tỉnh {i}'), year=year, source=src,
                sol=round(sol, 2), sol_cal=round(that, 2),
                sol_raw=round(sol if src == 'DMSP' else sol / 0.85, 2),
                sol_density=round(sol / 3000, 4), lit_area_pct=round(min(99, quy * 12), 2),
                sol_change_pct=(None if truoc is None or year == 2014
                              else round(100 * (sol / truoc - 1), 2)),
                sol_change_cal_pct=(None if truoc_hc is None
                                 else round(100 * (that / truoc_hc - 1), 2)),
                rad_cv=1.8)
            truoc, truoc_hc = sol, that
            if sua:
                sua(row)
            rows.append(row)
    return rows


def chay(rows):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'VN_NTL_Panel_2004_2025' / 'data_processed'
        out.mkdir(parents=True)
        with (out / 'ntl_annual.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=COLS)
            writer.writeheader()
            writer.writerows(rows)
        done = subprocess.run([sys.executable, '-I', str(SCRIPT), '--root', tmp],
                              capture_output=True, text=True)
        return done.returncode, done.stdout


class ItPassesCleanData(unittest.TestCase):
    def test_a_correct_table_reports_every_check_as_passing(self):
        code, out = chay(bang())
        self.assertEqual(code, 0, out)
        self.assertNotIn('XEM LẠI', out)

    def test_it_prints_one_province_series_with_both_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'VN_NTL_Panel_2004_2025' / 'data_processed'
            out.mkdir(parents=True)
            with (out / 'ntl_annual.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=COLS)
                writer.writeheader()
                writer.writerows(bang())
            done = subprocess.run([sys.executable, '-I', str(SCRIPT), '--root', tmp,
                                   '--tinh', '01'], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('Hà Nội', done.stdout)
        self.assertEqual(done.stdout.count('DMSP'), 10)
        self.assertEqual(done.stdout.count('VIIRS'), 12)


class ItCatchesEachKindOfBreakage(unittest.TestCase):
    """Mỗi test bẻ gãy đúng một thứ và đòi script phải kêu."""

    def _hong(self, sua, dau_hieu):
        code, out = chay(bang(sua))
        self.assertEqual(code, 1, f'script báo ĐẠT cho bảng đã hỏng:\n{out}')
        self.assertIn(dau_hieu, out, out)

    def test_a_missing_sol_ntl_is_reported(self):
        def sua(row):
            if row['province_code'] == '05' and row['year'] == 2019:
                row['sol'] = ''
        self._hong(sua, 'dòng có sol')

    def test_a_landsat_era_row_marked_viirs_is_reported(self):
        def sua(row):
            if row['year'] == 2009:
                row['source'] = 'VIIRS'
        self._hong(sua, 'đúng nguồn')

    def test_background_never_subtracted_is_reported(self):
        """sol == sol_raw ở mọi dòng VIIRS nghĩa là bước trừ nền không chạy."""
        def sua(row):
            row['sol_raw'] = row['sol']
        self._hong(sua, 'nền chiếm')

    def test_comparing_across_the_satellite_change_is_reported(self):
        """Cột gốc có số ở 2014 là so hai thang đo khác nhau."""
        def sua(row):
            if row['year'] == 2014:
                row['sol_change_pct'] = -76.4
        self._hong(sua, 'cột gốc bỏ trống')

    def test_a_harmonisation_that_leaves_a_jump_is_reported(self):
        def sua(row):
            if row['year'] >= 2014:
                row['sol_change_cal_pct'] = 900.0 if row['year'] == 2014 else row['sol_change_cal_pct']
        self._hong(sua, 'cột _hc')

    def test_provinces_shifted_so_the_big_cities_are_not_brightest(self):
        def sua(row):
            if row['province_name'] in TEN.values():
                row['sol'] = round(float(row['sol']) / 100, 2)
        self._hong(sua, 'tốp 5')

    def test_one_year_where_most_provinces_jump_at_once_is_reported(self):
        """Lỗi xử lý của riêng một năm, thứ dễ bị bỏ sót nhất."""
        def sua(row):
            if row['year'] == 2021:
                row['sol_change_pct'] = 180.0
        self._hong(sua, 'cùng biến động mạnh')


class TheKnown2010SatelliteBreakIsNotReportedAsANewFault(unittest.TestCase):
    """Mốc 2010 đã chốt giữ nguyên. Báo nó như lỗi mới mỗi lần chạy thì script mất tác dụng:
    người dùng quen với màu đỏ và sẽ bỏ qua cả những lỗi thật."""

    def test_the_2010_break_is_labelled_known_and_does_not_fail_the_run(self):
        def sua(row):
            if row['year'] == 2010:
                row['sol_change_pct'] = 420.0
        code, out = chay(bang(sua))
        self.assertIn('ĐÃ BIẾT', out)
        self.assertIn('F16', out)
        self.assertEqual(code, 0, f'mốc 2010 đã chốt giữ nguyên, không được coi là lỗi:\n{out}')

    def test_the_same_break_in_another_year_still_fails(self):
        def sua(row):
            if row['year'] == 2011:
                row['sol_change_pct'] = 420.0
        code, out = chay(bang(sua))
        self.assertEqual(code, 1, f'năm khác 2010 vẫn phải báo lỗi:\n{out}')
        self.assertIn('2011', out)


if __name__ == '__main__':
    unittest.main()
