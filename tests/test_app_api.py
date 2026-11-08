"""API chỉ là lớp đọc: thiếu dữ liệu phải trả rỗng một cách lịch sự, không bao giờ 500."""
import ast
import io
import json
import os
import re
import sys
import tempfile
import unittest
import types
import zipfile
from pathlib import Path
from unittest import mock
from unittest.mock import Mock

REPO = Path(__file__).resolve().parent.parent


def fresh_database(case):
    """Một cơ sở dữ liệu riêng cho mỗi test cần ghi, trả về (đường dẫn, client)."""
    directory = tempfile.TemporaryDirectory()
    case.addCleanup(directory.cleanup)
    from app.data import build_indices
    db = Path(directory.name) / 'vngis.db'
    report = build_indices.build(directory.name, db)
    os.environ['VNGIS_DB'] = str(db)
    case.addCleanup(os.environ.pop, 'VNGIS_DB', None)
    from fastapi.testclient import TestClient
    from app.api.main import app
    return db, TestClient(app), report


class ApiTest(unittest.TestCase):
    """Đọc thôi; không test nào ở đây được ghi thêm dòng vào cơ sở dữ liệu."""

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
        response = self.client.get('/api/indices', params={'ma_tinh': '02'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['ten_tinh'], 'Hà Giang')
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
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = archive.namelist()
            for part in ('chi_so_dem.csv', 'chi_so_ngay.csv', 'chi_so_kinh_te.csv', 'DOC_TRUOC.txt'):
                self.assertIn(part, names)
            self.assertTrue(any(n.startswith('anh_dem/') for n in names))
            # Phần trống phải nói ra là trống, không được là file rỗng im lặng.
            self.assertIn('Chưa có dữ liệu kinh tế',
                          archive.read('chi_so_kinh_te.csv').decode('utf-8-sig'))
            # Cảnh báo phương pháp phải đi kèm mọi lần tải về.
            self.assertIn('DMSP', archive.read('DOC_TRUOC.txt').decode('utf-8'))

    def test_the_export_filename_survives_an_http_header(self):
        """Header HTTP chỉ nhận latin-1; tên tỉnh có dấu từng làm hỏng cả lượt tải."""
        response = self.client.get('/api/export.zip', params={'ma_tinh': '01'})
        disposition = response.headers['content-disposition']
        self.assertIn('ha_noi', disposition)
        disposition.encode('latin-1')

    def test_health_and_coverage_do_not_crash_on_an_empty_database(self):
        self.assertTrue(self.client.get('/api/health').json()['ok'])
        body = self.client.get('/api/coverage').json()
        self.assertEqual(set(body), {'dem', 'ngay', 'kinh_te', 'anh_cog'})

    def test_the_province_list_is_loaded_from_the_pipelines_own_file(self):
        """Không có danh sách tỉnh thứ hai trong app: nó phải đến từ task_pipeline."""
        self.assertEqual(self.report['tinh'], 63)
        self.assertTrue((REPO / 'task_pipeline' / 'provinces.json').exists())

    def test_the_indicator_catalogue_reports_real_coverage(self):
        """Giao diện phải biết chỉ số nào còn trống để nói ra, thay vì vẽ bảng rỗng."""
        body = self.client.get('/api/indicators').json()['chi_so']
        codes = [c['ma'] for c in body]
        self.assertIn('sol_ntl', codes)
        self.assertIn('gdp', codes)
        for entry in body:
            for field in ('ma', 'ten', 'don_vi', 'bang', 'chu_so', 'so_tinh', 'mo_ta'):
                self.assertIn(field, entry)
        # kinh_te rỗng khi giảng viên chưa gửi số liệu: phải báo 0, không báo None.
        self.assertEqual([c for c in body if c['ma'] == 'gdp'][0]['so_tinh'], 0)

    def test_the_panel_covers_all_63_provinces_even_the_empty_ones(self):
        """Bảng kiểu WDI liệt kê đủ 63 tỉnh; tỉnh chưa có số liệu là ô trống, không bị bỏ."""
        body = self.client.get('/api/panel', params={'chi_so': 'sol_ntl',
                                                     'nam_tu': 2020, 'nam_den': 2025}).json()
        self.assertEqual(len(body['dong']), 63)
        self.assertEqual(body['nam'], [2020, 2021, 2022, 2023, 2024, 2025])
        self.assertTrue(all(len(r['gia_tri']) == 6 for r in body['dong']))
        trong = [r for r in body['dong'] if all(v is None for v in r['gia_tri'])]
        self.assertEqual(len(trong) + body['so_tinh_co_du_lieu'], 63)
        self.assertIn('02', [r['ma_tinh'] for r in trong])

    def test_a_panel_spanning_2013_warns_about_the_satellite_change(self):
        body = self.client.get('/api/panel', params={'chi_so': 'sol_ntl',
                                                     'nam_tu': 2010, 'nam_den': 2016}).json()
        self.assertTrue(any('DMSP' in w and 'VIIRS' in w for w in body['canh_bao']))
        inside = self.client.get('/api/panel', params={'chi_so': 'sol_ntl',
                                                       'nam_tu': 2016, 'nam_den': 2020}).json()
        self.assertEqual(inside['canh_bao'], [])

    def test_an_indicator_code_can_never_reach_the_sql(self):
        """Mã chỉ số do người dùng gửi: chỉ nhận mã có trong danh mục, không ghép vào SQL."""
        for bad in ('sol_ntl; DROP TABLE tinh', '"', 'khong_co_that', '*'):
            self.assertEqual(self.client.get('/api/panel', params={'chi_so': bad}).status_code, 404)
            self.assertEqual(self.client.get('/api/choropleth',
                                             params={'chi_so': bad}).status_code, 404)
        self.assertEqual(len(self.client.get('/api/provinces').json()['tinh']), 63)

    def test_the_two_csv_shapes_carry_the_header_and_the_method_note(self):
        wide = self.client.get('/api/panel.csv', params={'chi_so': 'sol_ntl', 'nam_tu': 2004,
                                                         'nam_den': 2006}).content.decode('utf-8-sig')
        self.assertIn('ma_tinh,ten_tinh,chi_so,don_vi,nguon_anh,2004,2005,2006', wide)
        self.assertIn('# Tổng độ sáng ban đêm', wide)
        self.assertIn('01,Hà Nội', wide)
        long = self.client.get('/api/panel.csv', params={'chi_so': 'sol_ntl', 'dang': 'dai'}
                               ).content.decode('utf-8-sig')
        self.assertIn('ma_tinh,ten_tinh,nam,chi_so,don_vi,gia_tri,nguon_anh', long)
        self.assertEqual(self.client.get('/api/panel.csv',
                                         params={'chi_so': 'sol_ntl', 'dang': 'xxx'}).status_code, 400)


class WritableDatabaseTest(unittest.TestCase):
    """Test có ghi thêm dòng dùng cơ sở dữ liệu riêng.

    Dùng chung một cơ sở dữ liệu thì test ghi trước làm sai kỳ vọng của test chạy sau —
    đã xảy ra thật: thêm dòng cho biểu đồ bản đồ khiến test đếm độ phủ báo 3 thay vì 0.
    """

    def setUp(self):
        self.db, self.client, _ = fresh_database(self)

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
        panel = self.client.get('/api/panel', params={'chi_so': 'NDVI_mean',
                                                      'nam_tu': 2015, 'nam_den': 2018}).json()
        self.assertTrue(any('TOA' in w for w in panel['canh_bao']))

    def test_the_choropleth_gives_the_range_the_legend_needs(self):
        import sqlite3
        with sqlite3.connect(self.db) as connection:
            connection.executemany(
                'INSERT OR REPLACE INTO ntl_annual(ma_tinh,nam,sol_ntl) VALUES(?,?,?)',
                [('01', 2022, 10.0), ('27', 2022, 90.0), ('48', 2022, 50.0)])
        body = self.client.get('/api/choropleth', params={'chi_so': 'sol_ntl', 'nam': 2022}).json()
        self.assertEqual(body['nho_nhat'], 10.0)
        self.assertEqual(body['lon_nhat'], 90.0)
        self.assertEqual(body['gia_tri']['27'], 90.0)
        trong = self.client.get('/api/choropleth', params={'chi_so': 'sol_ntl', 'nam': 1999}).json()
        self.assertIsNone(trong['nho_nhat'])

    def test_a_province_with_data_reports_it_and_keeps_the_calibration_note(self):
        import sqlite3
        with sqlite3.connect(self.db) as connection:
            connection.executemany(
                'INSERT OR REPLACE INTO ntl_annual(ma_tinh,nam,sol_ntl,hieu_chinh) VALUES(?,?,?,?)',
                [('01', y, float(y - 2000), 'CHUA_HIEU_CHINH') for y in range(2004, 2026)])
        body = self.client.get('/api/indices', params={'ma_tinh': '01'}).json()
        self.assertEqual(len(body['dem']), 22)
        self.assertFalse(body['thieu_du_lieu']['dem'])
        self.assertTrue(any('CHUA_HIEU_CHINH' in w or 'chưa hiệu chỉnh' in w
                            for w in body['canh_bao']))


class DeclaredDependenciesTest(unittest.TestCase):
    """Mọi thư viện bên ngoài mà app/ import phải có trong app/requirements.txt.

    Đã sót thật một lần: build_boundaries.py import shapely nhưng requirements không
    khai báo, nên cài xong vẫn chạy không được. Test này bắt đúng lớp lỗi đó.
    """

    NOI_BO = {'app', 'province_pipeline', 'task_pipeline', 'pipeline_core', 'tests'}

    def _declared(self):
        names = set()
        for line in (REPO / 'app' / 'requirements.txt').read_text(encoding='utf-8').splitlines():
            line = line.split('#')[0].strip()
            if not line:
                continue
            name = re.split(r'[<>=!\[]', line)[0].strip()
            names.add(name.lower().replace('-', '_'))
            names.add(name.lower().split('.')[0])        # titiler.core -> titiler
        return names

    def _imported(self):
        found = set()
        for path in sorted((REPO / 'app').rglob('*.py')):
            tree = ast.parse(path.read_text(encoding='utf-8'), str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    found.update(a.name.split('.')[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    found.add(node.module.split('.')[0])
        return {f for f in found
                if f not in self.NOI_BO and f not in sys.stdlib_module_names}

    def test_every_third_party_import_is_declared(self):
        declared = self._declared()
        missing = sorted(f for f in self._imported()
                         if f.lower().replace('-', '_') not in declared)
        self.assertEqual(missing, [], f'Thiếu trong app/requirements.txt: {missing}')

    def test_shapely_is_declared_for_the_boundary_script(self):
        self.assertIn('shapely', self._declared())
        self.assertIn('shapely', self._imported())


class ColumnNamesMatchThePipelineTest(unittest.TestCase):
    """Tên cột trong app phải trùng tên mà task_pipeline/derive.py thật sự ghi ra.

    Lệch tên thì build_indices vẫn nạp đủ dòng, API vẫn trả 200, giao diện vẫn vẽ —
    chỉ là mọi ô của cột đó trống. Không có gì báo lỗi. Đã xảy ra thật: app đi tìm
    'thay_doi_ntl', 'rad_mean', 'lit_pixels', 'dien_tich_km2', 'status' trong khi derive
    ghi 'thay_doi_ntl_pct', 'mean_ntl', 'so_pixel_sang', 'dt_tu_nhien_km2', 'trang_thai'.
    Hậu quả nặng nhất: cảnh báo DMSP–VIIRS bị tắt vì derive ghi hieu_chinh='PENDING'
    còn app dò 'CHUA_HIEU_CHINH'.
    """

    def _derive_source(self):
        return (REPO / 'task_pipeline' / 'derive.py').read_text(encoding='utf-8')

    def test_every_night_field_appears_in_derive(self):
        from app.api import store
        nguon = self._derive_source()
        thieu = [f for f in store.NIGHT_FIELDS
                 if f not in ('nam',) and f"'{f}'" not in nguon and f'{f}=' not in nguon]
        self.assertEqual(thieu, [], f'Cột đêm không có trong derive.py: {thieu}')

    def test_every_day_field_appears_in_derive(self):
        from app.api import store
        nguon = self._derive_source()
        # so_thang do build_indices tạo khi gộp tháng lên năm, derive không có.
        thieu = [f for f in store.DAY_FIELDS
                 if f not in ('nam', 'so_thang')
                 and f"'{f}'" not in nguon and f'{f}=' not in nguon
                 and f"'{f.replace('_mean', '')}'" not in nguon
                 and f"'{f.replace('_std', '')}'" not in nguon]
        self.assertEqual(thieu, [], f'Cột ngày không có trong derive.py: {thieu}')

    def test_every_indicator_code_is_a_column_of_its_table(self):
        import sqlite3
        from app.api import store
        db, _, _ = fresh_database(self)
        with sqlite3.connect(db) as connection:
            for entry in store.INDICATORS:
                cot = {r[1] for r in connection.execute(
                    f"PRAGMA table_info({entry['bang']})")}
                with self.subTest(chi_so=entry['ma']):
                    self.assertIn(entry['ma'], cot)

    def test_the_calibration_flag_derive_actually_writes_is_accepted(self):
        """derive ghi hieu_chinh='PENDING'; CLAUDE.md nói 'CHUA_HIEU_CHINH'. Nhận cả hai."""
        nguon = self._derive_source()
        self.assertIn("'hieu_chinh']='PENDING'", nguon.replace(' ', ''))
        store_source = (REPO / 'app' / 'api' / 'store.py').read_text(encoding='utf-8')
        self.assertIn("'PENDING'", store_source)
        self.assertIn("'CHUA_HIEU_CHINH'", store_source)

    def test_a_dmsp_to_viirs_series_always_carries_the_warning(self):
        """Chuỗi có cả hai nguồn thì cảnh báo phải hiện, dù cột hieu_chinh ghi gì."""
        import sqlite3
        from app.api import store
        db, _, _ = fresh_database(self)
        with sqlite3.connect(db) as connection:
            connection.executemany(
                'INSERT OR REPLACE INTO ntl_annual(ma_tinh,nam,nguon_anh,sol_ntl,hieu_chinh) '
                'VALUES(?,?,?,?,?)',
                [('01', y, 'DMSP' if y <= 2013 else 'VIIRS', 1.0, None)
                 for y in range(2004, 2026)])
        data = store.indices('01', 2004, 2025)
        self.assertTrue(any('DMSP' in w and 'VIIRS' in w for w in data['canh_bao']))


class BuildBoundariesTest(unittest.TestCase):
    """Chỉ kiểm phần ghép nối. Việc tải GADM thật cần mạng, chạy trên máy người dùng."""

    def test_missing_boundaries_explain_the_one_command_that_fixes_it(self):
        from app.data import build_boundaries
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'c.json'
            config.write_text(json.dumps({
                'boundaries': str(Path(directory) / 'khong_co.geojson'),
                'boundary_metadata': str(Path(directory) / 'khong_co.json'),
                'boundary_policy': 'gadm41_research'}), encoding='utf-8')
            with self.assertRaises(SystemExit) as thoat:
                build_boundaries.build(config)
        self.assertIn('--tai-gadm', str(thoat.exception))

    def test_the_download_flag_reaches_prepare_gadm(self):
        """--tai-gadm phải gọi đúng prepare() của pipeline, không tự tải theo cách khác."""
        from app.data import build_boundaries
        goi = []
        module = types.ModuleType('province_pipeline.prepare_gadm')
        module.prepare = lambda config: goi.append(config) or 63
        with tempfile.TemporaryDirectory() as directory:
            config = {'boundaries': str(Path(directory) / 'x.geojson'),
                      'boundary_metadata': str(Path(directory) / 'x.json'),
                      'boundary_policy': 'gadm41_research'}
            path = Path(directory) / 'c.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            with mock.patch.dict(sys.modules, {'province_pipeline.prepare_gadm': module}), \
                 mock.patch('province_pipeline.boundaries.load_boundaries',
                            return_value=({}, {'source': 'GADM', 'version': 'GADM 4.1',
                                               'sha256': 'x'})):
                out, count, size = build_boundaries.build(path, Path(directory) / 'o.geojson',
                                                          download=True)
            # Kiểm tra trong lòng with: ra khỏi khối là thư mục tạm bị xoá.
            self.assertEqual(len(goi), 1)
            self.assertEqual(count, 0)
            self.assertTrue(out.exists())
            self.assertEqual(json.loads(out.read_text(encoding='utf-8'))['type'],
                             'FeatureCollection')

    def test_the_default_config_matches_what_the_pipeline_writes(self):
        """Chạy không --config phải trỏ đúng chỗ task_pipeline.local.prepare() đặt file."""
        from app.data.build_boundaries import DEFAULT_CONFIG
        self.assertEqual(DEFAULT_CONFIG['boundaries'],
                         'province_pipeline/config/boundaries.geojson')
        self.assertEqual(DEFAULT_CONFIG['boundary_policy'], 'gadm41_research')
        local = (REPO / 'task_pipeline' / 'local.py').read_text(encoding='utf-8')
        for value in DEFAULT_CONFIG.values():
            self.assertIn(value, local)


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
                self.assertEqual(connection.execute('SELECT loai FROM anh_cog').fetchone()[0], 'NTL')
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


if __name__ == '__main__':
    unittest.main()
