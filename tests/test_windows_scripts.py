"""Script PowerShell phải là ASCII thuần.

Windows PowerShell 5.1 (bản mặc định trên Windows 10) đọc file .ps1 UTF-8 **không BOM**
theo bảng mã ANSI của máy. Dấu tiếng Việt biến thành ký tự rác, và nếu rác rơi vào trong
một chuỗi thì cả file vỡ cú pháp:

    Write-Host "  rá»"i má»Ÿ http://localhost:8000"
    The string is missing the terminator: ".

Đã xảy ra thật. Giữ script ở ASCII là cách chắc chắn nhất, không phụ thuộc BOM hay bảng mã
của từng máy. Chú thích và thông báo viết tiếng Việt không dấu.
"""
import re
import unittest
from pathlib import Path

SCRIPTS = sorted((Path(__file__).resolve().parent.parent / 'scripts' / 'windows').glob('*.ps1'))


class PowerShellScriptTest(unittest.TestCase):

    def test_there_are_scripts_to_check(self):
        self.assertTrue(SCRIPTS, 'Không tìm thấy script PowerShell nào')

    def test_every_script_is_pure_ascii(self):
        for path in SCRIPTS:
            with self.subTest(script=path.name):
                raw = path.read_bytes()
                xau = [(i, b) for i, b in enumerate(raw) if b > 127]
                self.assertEqual(
                    xau[:5], [],
                    f'{path.name} có ký tự ngoài ASCII ở byte {[i for i, _ in xau[:5]]} — '
                    f'PowerShell 5.1 sẽ đọc sai và có thể vỡ cú pháp')

    @staticmethod
    def _dem_nhay_kep(line):
        """Số dấu nháy kép thật sự mở/đóng chuỗi trên một dòng.

        Bỏ qua: chuỗi nháy đơn (PowerShell cho phép " bên trong, ví dụ Contains('"')),
        dấu thoát `" và "" bên trong chuỗi nháy kép.
        """
        line = re.sub(r"`.", '', line)          # ký tự thoát của PowerShell
        line = re.sub(r"'[^']*'", '', line)     # chuỗi nháy đơn
        line = line.replace('""', '')           # nháy kép thoát bằng cách nhân đôi
        return line.count('"')

    def test_quotes_are_balanced_on_every_line(self):
        """Bắt sớm lỗi 'The string is missing the terminator' mà không cần chạy PowerShell."""
        for path in SCRIPTS:
            for number, line in enumerate(path.read_text(encoding='ascii').splitlines(), 1):
                if line.lstrip().startswith('#'):
                    continue
                with self.subTest(script=path.name, line=number):
                    self.assertEqual(
                        self._dem_nhay_kep(line) % 2, 0,
                        f'{path.name}:{number} lẻ dấu nháy kép: {line.strip()[:70]}')

    def test_the_quote_counter_itself_is_right(self):
        """Phép đếm từng báo nhầm dòng hợp lệ Contains('"'); giữ lại ca đó làm mốc."""
        dem = self._dem_nhay_kep
        self.assertEqual(dem("""if ($p.Contains('"')) { throw "Invalid path" }"""), 2)
        self.assertEqual(dem('Write-Host "xong"'), 2)
        self.assertEqual(dem('Write-Host "thieu terminator'), 1)
        self.assertEqual(dem('Write-Host "a `" b"'), 2)

    def test_the_night_index_script_runs_the_derive_step_for_all_six_ranges(self):
        text = (Path(__file__).resolve().parent.parent
                / 'scripts' / 'windows' / 'chi_so_dem.ps1').read_text(encoding='ascii')
        self.assertIn('task_pipeline.local derive', text)
        self.assertIn('--only', text)
        for group in ('1-11', '12-22', '23-33', '34-43', '44-53', '54-63'):
            self.assertIn(group, text)


if __name__ == '__main__':
    unittest.main()
