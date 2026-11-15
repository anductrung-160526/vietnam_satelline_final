"""Script kiểm nghiệm chất lượng phải bắt được lỗi, và không kêu oan chỗ trống hợp lệ."""
import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / 'scripts' / 'kiem_dinh_chat_luong.py'
COLS = ['province_code', 'province_name', 'year', 'month', 'period', 'frequency', 'source',
        'area_km2', 'sol', 'sol_density', 'sol_change_pct', 'rad_cv', 'valid_pixels',
        'lit_pixels', 'lit_area_pct', 'cloud_free_obs', 'status', 'note']


def bang(sua=None):
    rows = []
    for i in range(1, 64):
        truoc = None
        for year in range(2004, 2014):
            sol = (1 + (i % 7) / 10) * (1 + 0.06 * (year - 2004)) * 1000
            row = dict(province_code=f'{i:02}', province_name=f'T{i}', year=year, month=0,
                       period=str(year), frequency='annual', source='DMSP', area_km2=3000,
                       sol=round(sol, 2), sol_density=round(sol / 3000, 4),
                       sol_change_pct=('' if truoc is None else round(100 * (sol / truoc - 1), 2)),
                       rad_cv=1.8, valid_pixels=3000, lit_pixels=500, lit_area_pct=16.7,
                       cloud_free_obs='', status='OK', note='')
            truoc = sol
            if sua:
                sua(row)
            rows.append(row)
    return rows


def chay(rows, bang_ten='ntl_panel'):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'VN_NTL_Panel_2004_2025' / 'data_processed'
        out.mkdir(parents=True)
        with (out / f'{bang_ten}.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=COLS)
            writer.writeheader()
            writer.writerows(rows)
        done = subprocess.run([sys.executable, '-I', str(SCRIPT), '--root', tmp,
                               '--bang', bang_ten], capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr


class ItDoesNotCryWolf(unittest.TestCase):
    def test_a_clean_table_reports_no_technical_problem(self):
        code, out = chay(bang())
        self.assertEqual(code, 0, out)
        self.assertIn('KHÔNG phát hiện vấn đề kỹ thuật', out)

    def test_the_legitimately_empty_columns_are_not_counted_as_faults(self):
        """sol_change_pct trống ở năm đầu và cloud_free_obs trống với DMSP là ĐÚNG."""
        code, out = chay(bang())
        self.assertIn('dự kiến: năm đầu chuỗi', out)
        self.assertIn('dự kiến: ảnh DMSP không có băng cf_cvg', out)
        self.assertEqual(code, 0)


class ItCatchesRealProblems(unittest.TestCase):
    def _hong(self, sua, dau_hieu, bang_ten='ntl_panel'):
        code, out = chay(bang(sua), bang_ten)
        self.assertEqual(code, 1, f'báo sạch cho bảng đã hỏng:\n{out}')
        self.assertIn(dau_hieu, out, out)

    def test_a_duplicate_key_is_reported(self):
        rows = bang()
        rows.append(dict(rows[0]))
        code, out = chay(rows)
        self.assertEqual(code, 1, out)
        self.assertIn('LẶP', out)

    def test_a_province_code_that_lost_its_leading_zero_is_reported(self):
        """Lỗi kinh điển khi mở CSV bằng Excel: '01' thành 1."""
        def sua(row):
            if row['province_code'] == '01':
                row['province_code'] = '1'
        self._hong(sua, 'MÃ SAI ĐỊNH DẠNG')

    def test_text_in_a_numeric_column_is_reported(self):
        def sua(row):
            if row['year'] == 2008:
                row['sol'] = 'khong co'
        self._hong(sua, 'ĐỊNH DẠNG')

    def test_an_unexpected_empty_cell_is_reported(self):
        def sua(row):
            if row['year'] == 2009:
                row['sol_density'] = ''
        self._hong(sua, 'KHÔNG dự kiến trống')

    def test_a_negative_sum_of_lights_is_reported(self):
        """sol âm là vô nghĩa vật lý: bức xạ không âm."""
        def sua(row):
            if row['year'] == 2011:
                row['sol'] = -5
        self._hong(sua, 'ngoài [0')

    def test_a_percentage_above_one_hundred_is_reported(self):
        def sua(row):
            if row['year'] == 2012:
                row['lit_area_pct'] = 140
        self._hong(sua, 'lit_area_pct')

    def test_a_missing_province_is_reported(self):
        rows = [r for r in bang() if r['province_code'] != '40']
        code, out = chay(rows)
        self.assertEqual(code, 1, out)
        self.assertIn('cần 63', out)

    def test_an_empty_table_is_reported_not_silently_passed(self):
        code, out = chay([])
        self.assertEqual(code, 1)
        self.assertIn('RỖNG', out)


if __name__ == '__main__':
    unittest.main()
