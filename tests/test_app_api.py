"""API chỉ là lớp đọc: thiếu dữ liệu phải trả rỗng một cách lịch sự, không bao giờ 500."""
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        from app.data import build_indices
        cls.db = Path(cls.directory.name) / 'vngis.db'
        cls.report = build_indices.build(cls.directory.name, cls.db)
        os.environ['VNGIS_DB'] = str(cls.db)
        from fastapi.testclient import TestClient
        from app.api.main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop('VNGIS_DB', None)
        cls.directory.cleanup()

    def test_sixty_three_provinces_with_the_official_codes(self):
        """63 tỉnh trước sáp nhập — con số này là quy tắc dự án, không phải tuỳ chọn."""
        body = self.client.get('/api/provinces').json()
        self.assertEqual(len(body['tinh']), 63)
        self.assertEqual(body['tinh'][0]['ma_tinh'], '01')
        self.assertTrue(all(len(t['ma_tinh']) == 2 for t in body['tinh']))

    def test_a_province_without_indices_answers_empty_not_an_error(self):
        """Tỉnh chưa tính chỉ số vẫn phải trả 200 + mảng rỗng: app không được trắng xoá."""
        response = self.client.get('/api/indices', params={'ma_tinh': '01'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['ten_tinh'], 'Hà Nội')
        self.assertEqual(body['dem'], [])
        self.assertTrue(body['thieu_du_lieu']['dem'])
        self.assertTrue(body['thieu_du_lieu']['kinh_te'])

    def test_an_unknown_province_is_a_404_and_a_bad_year_range_a_400(self):
        self.assertEqual(self.client.get('/api/indices', params={'ma_tinh': '99'}).status_code, 404)
        self.assertEqual(self.client.get(
            '/api/indices', params={'ma_tinh': '01', 'nam_tu': 2020, 'nam_den': 2010}).status_code, 400)

    def test_export_always_holds_the_four_parts_the_supervisor_asked_for(self):
        """Ảnh đêm, chỉ số ngày, chỉ số đêm, chỉ số kinh tế — kể cả khi phần đó còn trống."""
        response = self.client.get('/api/export.zip', params={'ma_tinh': '01'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'application/zip')
        with zipfile.ZipFile(__import__('io').BytesIO(response.content)) as archive:
            names = archive.namelist()
            for part in ('chi_so_dem.csv', 'chi_so_ngay.csv', 'chi_so_kinh_te.csv', 'DOC_TRUOC.txt'):
                self.assertIn(part, names)
            self.assertTrue(any(n.startswith('anh_dem/') for n in names))
            # Phần trống phải nói ra là trống, không được là file rỗng im lặng.
            self.assertIn('Chưa có dữ liệu kinh tế',
                          archive.read('chi_so_kinh_te.csv').decode('utf-8-sig'))
            # Cảnh báo phương pháp phải đi kèm mọi lần tải về.
            self.assertIn('DMSP', archive.read('DOC_TRUOC.txt').decode('utf-8'))

    def test_the_toa_warning_rides_along_with_any_2015_2018_day_row(self):
        """Sentinel-2 2015–2018 là TOA; ai tải dữ liệu cũng phải đọc được cảnh báo đó."""
        import sqlite3
        from app.api import store
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                'INSERT OR REPLACE INTO day_annual(ma_tinh,nam,nguon_anh,NDVI_mean) VALUES(?,?,?,?)',
                ('01', 2017, 'SENTINEL2', 0.42))
        data = store.indices('01', 2004, 2025)
        self.assertEqual(len(data['ngay']), 1)
        self.assertTrue(any('TOA' in w for w in data['canh_bao']))

    def test_health_and_coverage_do_not_crash_on_an_empty_database(self):
        self.assertTrue(self.client.get('/api/health').json()['ok'])
        body = self.client.get('/api/coverage').json()
        self.assertEqual(set(body), {'dem', 'ngay', 'kinh_te', 'anh_cog'})

    def test_the_province_list_is_loaded_from_the_pipelines_own_file(self):
        """Không có danh sách tỉnh thứ hai trong app: nó phải đến từ task_pipeline."""
        self.assertEqual(self.report['tinh'], 63)
        self.assertTrue((REPO / 'task_pipeline' / 'provinces.json').exists())


if __name__ == '__main__':
    unittest.main()


class BuildCogsTest(unittest.TestCase):
    """Phần tìm ảnh và ghi sổ phải đúng; việc gọi gdal chỉ chạy trên máy có gdal-bin."""

    def test_sources_are_found_by_year_for_both_naming_shapes(self):
        from app.data import build_cogs
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a').mkdir()
            for name in ('VN_SENTINEL2_2024.vrt', 'a/VN_SENTINEL2_2016.vrt',
                         'VN_VIIRS_2020.tif', 'khong_lien_quan.txt'):
                (root / name).write_bytes(b'x')
            day = build_cogs.find_sources(root, 'SENTINEL2')
            self.assertEqual(sorted(day), [2016, 2024])
            self.assertEqual(sorted(build_cogs.find_sources(root, 'VIIRS')), [2020])
            self.assertEqual(build_cogs.find_sources(root, 'DMSP'), {})

    def test_originals_are_recorded_but_never_treated_as_servable(self):
        """Ảnh gốc 24 GB chỉ được ghi sổ ở tầng lạnh, không bao giờ vào bảng anh_cog."""
        import sqlite3
        from app.data import build_cogs
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'x.db'
            build_cogs.record(db, 'anh_cog', [('NTL', 2024, '/cog/v.tif', 'VIIRS', 10)])
            build_cogs.record(db, 'anh_goc', [('SENTINEL2', 2024, '/data/vn.vrt', 2 << 34, 'lạnh')])
            with sqlite3.connect(db) as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM anh_cog').fetchone()[0], 1)
                self.assertEqual(connection.execute(
                    "SELECT loai FROM anh_cog").fetchone()[0], 'NTL')
                self.assertEqual(connection.execute(
                    'SELECT duong_dan FROM anh_goc').fetchone()[0], '/data/vn.vrt')

    def test_the_illustrative_day_image_is_rgb_eight_bit_and_downsampled(self):
        """Lời cô dặn: ảnh ngày phải nén lại, mỗi năm một ảnh. Lệnh phải phản ánh đúng thế."""
        from app.data import build_cogs
        seen = []
        original = build_cogs.run
        build_cogs.run = lambda command: seen.append([str(c) for c in command])
        try:
            build_cogs.day_cog('in.vrt', 'out.tif', '0.001')
        finally:
            build_cogs.run = original
        command = seen[0]
        self.assertEqual(command[:2], ['gdal_translate', '-b'])
        self.assertEqual([command[i + 1] for i, c in enumerate(command) if c == '-b'],
                         ['3', '2', '1'])         # RED, GREEN, BLUE theo thứ tự băng pipeline
        self.assertIn('Byte', command)
        self.assertIn('0.001', command)
        self.assertIn('COG', command)
