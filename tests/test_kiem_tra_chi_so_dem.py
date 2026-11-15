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
COLS = ['ma_tinh', 'ten_tinh', 'nam', 'nguon_anh', 'sol_ntl', 'sol_ntl_tho', 'sol_ntl_hc',
        'mat_do_ntl', 'ty_le_sang_pct', 'thay_doi_ntl', 'thay_doi_ntl_hc', 'cv_ntl']
TEN = {1: 'Hà Nội', 2: 'Hồ Chí Minh'}


def bang(sua=None):
    """Bảng 63 tỉnh x 22 năm hợp lệ; sua(row) được gọi để bẻ gãy một thứ."""
    rows = []
    for i in range(1, 64):
        quy = (3 if i <= 2 else 1) * (1 + (i % 7) / 10)
        truoc = truoc_hc = None
        for nam in range(2004, 2026):
            src = 'DMSP' if nam <= 2013 else 'VIIRS'
            that = quy * (1 + 0.06 * (nam - 2004)) * 5000
            sol = that if src == 'VIIRS' else (that / A) ** (1 / B)
            row = dict(
                ma_tinh=f'{i:02}', ten_tinh=TEN.get(i, f'Tỉnh {i}'), nam=nam, nguon_anh=src,
                sol_ntl=round(sol, 2), sol_ntl_hc=round(that, 2),
                sol_ntl_tho=round(sol if src == 'DMSP' else sol / 0.85, 2),
                mat_do_ntl=round(sol / 3000, 4), ty_le_sang_pct=round(min(99, quy * 12), 2),
                thay_doi_ntl=(None if truoc is None or nam == 2014
                              else round(100 * (sol / truoc - 1), 2)),
                thay_doi_ntl_hc=(None if truoc_hc is None
                                 else round(100 * (that / truoc_hc - 1), 2)),
                cv_ntl=1.8)
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
            if row['ma_tinh'] == '05' and row['nam'] == 2019:
                row['sol_ntl'] = ''
        self._hong(sua, 'dòng có sol_ntl')

    def test_a_landsat_era_row_marked_viirs_is_reported(self):
        def sua(row):
            if row['nam'] == 2009:
                row['nguon_anh'] = 'VIIRS'
        self._hong(sua, 'đúng nguồn')

    def test_background_never_subtracted_is_reported(self):
        """sol_ntl == sol_ntl_tho ở mọi dòng VIIRS nghĩa là bước trừ nền không chạy."""
        def sua(row):
            row['sol_ntl_tho'] = row['sol_ntl']
        self._hong(sua, 'nền chiếm')

    def test_comparing_across_the_satellite_change_is_reported(self):
        """Cột gốc có số ở 2014 là so hai thang đo khác nhau."""
        def sua(row):
            if row['nam'] == 2014:
                row['thay_doi_ntl'] = -76.4
        self._hong(sua, 'cột gốc bỏ trống')

    def test_a_harmonisation_that_leaves_a_jump_is_reported(self):
        def sua(row):
            if row['nam'] >= 2014:
                row['thay_doi_ntl_hc'] = 900.0 if row['nam'] == 2014 else row['thay_doi_ntl_hc']
        self._hong(sua, 'cột _hc')

    def test_provinces_shifted_so_the_big_cities_are_not_brightest(self):
        def sua(row):
            if row['ten_tinh'] in TEN.values():
                row['sol_ntl'] = round(float(row['sol_ntl']) / 100, 2)
        self._hong(sua, 'tốp 5')

    def test_one_year_where_most_provinces_jump_at_once_is_reported(self):
        """Lỗi xử lý của riêng một năm, thứ dễ bị bỏ sót nhất."""
        def sua(row):
            if row['nam'] == 2021:
                row['thay_doi_ntl'] = 180.0
        self._hong(sua, 'cùng biến động mạnh')


class TheKnown2010SatelliteBreakIsNotReportedAsANewFault(unittest.TestCase):
    """Mốc 2010 đã chốt giữ nguyên. Báo nó như lỗi mới mỗi lần chạy thì script mất tác dụng:
    người dùng quen với màu đỏ và sẽ bỏ qua cả những lỗi thật."""

    def test_the_2010_break_is_labelled_known_and_does_not_fail_the_run(self):
        def sua(row):
            if row['nam'] == 2010:
                row['thay_doi_ntl'] = 420.0
        code, out = chay(bang(sua))
        self.assertIn('ĐÃ BIẾT', out)
        self.assertIn('F16', out)
        self.assertEqual(code, 0, f'mốc 2010 đã chốt giữ nguyên, không được coi là lỗi:\n{out}')

    def test_the_same_break_in_another_year_still_fails(self):
        def sua(row):
            if row['nam'] == 2011:
                row['thay_doi_ntl'] = 420.0
        code, out = chay(bang(sua))
        self.assertEqual(code, 1, f'năm khác 2010 vẫn phải báo lỗi:\n{out}')
        self.assertIn('2011', out)


if __name__ == '__main__':
    unittest.main()
