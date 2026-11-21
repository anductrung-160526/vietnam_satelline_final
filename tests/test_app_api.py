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
    from backend.data import build_indices
    db = Path(directory.name) / 'vngis.db'
    report = build_indices.build(directory.name, db, repo_fallback=False)
    os.environ['VNGIS_DB'] = str(db)
    case.addCleanup(os.environ.pop, 'VNGIS_DB', None)
    from fastapi.testclient import TestClient
    from backend.api.main import app
    return db, TestClient(app), report


class ApiTest(unittest.TestCase):
    """Đọc thôi; không test nào ở đây được ghi thêm dòng vào cơ sở dữ liệu."""

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        from backend.data import build_indices
        cls.db = Path(cls.directory.name) / 'vngis.db'
        cls.report = build_indices.build(cls.directory.name, cls.db, repo_fallback=False)
        os.environ['VNGIS_DB'] = str(cls.db)
        from fastapi.testclient import TestClient
        from backend.api.main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop('VNGIS_DB', None)
        cls.directory.cleanup()

    def test_sixty_three_provinces_with_the_official_codes(self):
        """63 tỉnh trước sáp nhập — con số này là quy tắc dự án, không phải tuỳ chọn."""
        body = self.client.get('/api/provinces').json()
        self.assertEqual(len(body['tinh']), 63)
        self.assertEqual(body['tinh'][0]['province_code'], '01')
        self.assertTrue(all(len(t['province_code']) == 2 for t in body['tinh']))

    def test_a_province_without_indices_answers_empty_not_an_error(self):
        """Tỉnh chưa tính chỉ số vẫn phải trả 200 + mảng rỗng: app không được trắng xoá."""
        response = self.client.get('/api/indices', params={'province_code': '02'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['province_name'], 'Hà Giang')
        self.assertEqual(body['dem'], [])
        self.assertTrue(body['thieu_du_lieu']['dem'])
        self.assertTrue(body['thieu_du_lieu']['economy'])

    def test_an_unknown_province_is_a_404_and_a_bad_year_range_a_400(self):
        self.assertEqual(self.client.get('/api/indices', params={'province_code': '99'}).status_code, 404)
        self.assertEqual(self.client.get(
            '/api/indices', params={'province_code': '01', 'nam_tu': 2020, 'nam_den': 2010}).status_code, 400)

    def test_export_always_holds_the_four_parts_the_supervisor_asked_for(self):
        """Ảnh đêm, chỉ số ngày, chỉ số đêm, chỉ số kinh tế — kể cả khi phần đó còn trống."""
        response = self.client.get('/api/export.zip', params={'province_code': '01'})
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
        response = self.client.get('/api/export.zip', params={'province_code': '01'})
        disposition = response.headers['content-disposition']
        self.assertIn('ha_noi', disposition)
        disposition.encode('latin-1')

    def test_health_and_coverage_do_not_crash_on_an_empty_database(self):
        self.assertTrue(self.client.get('/api/health').json()['ok'])
        body = self.client.get('/api/coverage').json()
        self.assertEqual(set(body), {'dem', 'ngay', 'economy', 'cog_image'})

    def test_the_province_list_is_loaded_from_the_pipelines_own_file(self):
        """Không có danh sách tỉnh thứ hai trong app: nó phải đến từ task_pipeline."""
        self.assertEqual(self.report['province'], 63)
        self.assertTrue((REPO / 'backend' / 'core' / 'ranh_gioi' / 'config'
                         / 'danh_muc_tinh.json').exists())

    def test_the_indicator_catalogue_reports_real_coverage(self):
        """Giao diện phải biết chỉ số nào còn trống để nói ra, thay vì vẽ bảng rỗng."""
        body = self.client.get('/api/indicators').json()['chi_so']
        codes = [c['ma'] for c in body]
        self.assertIn('sol', codes)
        self.assertIn('gdp', codes)
        for entry in body:
            for field in ('ma', 'ten', 'don_vi', 'bang', 'chu_so', 'so_tinh', 'mo_ta'):
                self.assertIn(field, entry)
        # economy rỗng khi giảng viên chưa gửi số liệu: phải báo 0, không báo None.
        self.assertEqual([c for c in body if c['ma'] == 'gdp'][0]['so_tinh'], 0)

    def test_the_panel_covers_all_63_provinces_even_the_empty_ones(self):
        """Bảng kiểu WDI liệt kê đủ 63 tỉnh; tỉnh chưa có số liệu là ô trống, không bị bỏ."""
        body = self.client.get('/api/panel', params={'chi_so': 'sol',
                                                     'nam_tu': 2020, 'nam_den': 2025}).json()
        self.assertEqual(len(body['dong']), 63)
        self.assertEqual(body['moc'], ['2020', '2021', '2022', '2023', '2024', '2025'])
        self.assertTrue(all(len(r['gia_tri']) == 6 for r in body['dong']))
        trong = [r for r in body['dong'] if all(v is None for v in r['gia_tri'])]
        self.assertEqual(len(trong) + body['so_tinh_co_du_lieu'], 63)
        self.assertIn('02', [r['province_code'] for r in trong])

    def test_a_panel_spanning_2013_warns_about_the_satellite_change(self):
        body = self.client.get('/api/panel', params={'chi_so': 'sol',
                                                     'nam_tu': 2010, 'nam_den': 2016}).json()
        self.assertTrue(any('DMSP' in w and 'VIIRS' in w for w in body['canh_bao']))
        inside = self.client.get('/api/panel', params={'chi_so': 'sol',
                                                       'nam_tu': 2016, 'nam_den': 2020}).json()
        self.assertEqual(inside['canh_bao'], [])

    def test_a_series_spanning_2010_warns_about_the_dmsp_satellite_change(self):
        """Mốc F16→F18 nằm GIỮA giai đoạn DMSP; cột _hc không sửa nó, nên app phải nói ra."""
        body = self.client.get('/api/panel', params={'chi_so': 'sol',
                                                     'nam_tu': 2008, 'nam_den': 2012}).json()
        self.assertTrue(any('2010' in w and 'F16' in w for w in body['canh_bao']),
                        body['canh_bao'])
        trong = self.client.get('/api/panel', params={'chi_so': 'sol',
                                                      'nam_tu': 2010, 'nam_den': 2013}).json()
        self.assertFalse(any('F16' in w for w in trong['canh_bao']),
                         'nằm gọn trong giai đoạn F18 thì không có mốc nào để cảnh báo')

    def test_the_2010_warning_says_the_harmonised_column_does_not_fix_it(self):
        """Hiểu nhầm nguy hiểm nhất: tưởng sol_cal đã sửa mọi mốc đổi vệ tinh."""
        body = self.client.get('/api/panel', params={'chi_so': 'sol',
                                                     'nam_tu': 2008, 'nam_den': 2012}).json()
        moc = [w for w in body['canh_bao'] if 'F16' in w]
        self.assertTrue(moc, body['canh_bao'])
        self.assertIn('hiệu chỉnh', moc[0])

    def test_an_indicator_code_can_never_reach_the_sql(self):
        """Mã chỉ số do người dùng gửi: chỉ nhận mã có trong danh mục, không ghép vào SQL."""
        for bad in ('sol; DROP TABLE tinh', '"', 'khong_co_that', '*'):
            self.assertEqual(self.client.get('/api/panel', params={'chi_so': bad}).status_code, 400)
            self.assertEqual(self.client.get('/api/choropleth',
                                             params={'chi_so': bad}).status_code, 404)
        self.assertEqual(len(self.client.get('/api/provinces').json()['tinh']), 63)

    def test_the_two_csv_shapes_carry_the_header_and_the_method_note(self):
        wide = self.client.get('/api/panel.csv', params={'chi_so': 'sol', 'nam_tu': 2004,
                                                         'nam_den': 2006}).content.decode('utf-8-sig')
        self.assertIn('province_code,province_name,chi_so,don_vi,source,2004,2005,2006', wide)
        self.assertIn('# Tổng độ sáng ban đêm', wide)
        self.assertIn('01,Hà Nội', wide)
        long = self.client.get('/api/panel.csv', params={'chi_so': 'sol', 'dang': 'dai'}
                               ).content.decode('utf-8-sig')
        self.assertIn('province_code,province_name,period,chi_so,don_vi,gia_tri,source', long)
        self.assertEqual(self.client.get('/api/panel.csv',
                                         params={'chi_so': 'sol', 'dang': 'xxx'}).status_code, 400)


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
        from backend.api import store
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                'INSERT OR REPLACE INTO day_annual(province_code,year,source,NDVI_mean) VALUES(?,?,?,?)',
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
                'INSERT OR REPLACE INTO ntl_annual(province_code,year,sol) VALUES(?,?,?)',
                [('01', 2022, 10.0), ('27', 2022, 90.0), ('48', 2022, 50.0)])
        body = self.client.get('/api/choropleth', params={'chi_so': 'sol', 'nam': 2022}).json()
        self.assertEqual(body['nho_nhat'], 10.0)
        self.assertEqual(body['lon_nhat'], 90.0)
        self.assertEqual(body['gia_tri']['27'], 90.0)
        trong = self.client.get('/api/choropleth', params={'chi_so': 'sol', 'nam': 1999}).json()
        self.assertIsNone(trong['nho_nhat'])

    def test_a_province_with_data_reports_it_and_keeps_the_calibration_note(self):
        import sqlite3
        with sqlite3.connect(self.db) as connection:
            connection.executemany(
                'INSERT OR REPLACE INTO ntl_annual(province_code,year,sol,calibration) VALUES(?,?,?,?)',
                [('01', y, float(y - 2000), 'CHUA_HIEU_CHINH') for y in range(2004, 2026)])
        body = self.client.get('/api/indices', params={'province_code': '01'}).json()
        self.assertEqual(len(body['dem']), 22)
        self.assertFalse(body['thieu_du_lieu']['dem'])
        self.assertTrue(any('CHƯA hiệu chỉnh' in w for w in body['canh_bao']),
                        body['canh_bao'])


class DeclaredDependenciesTest(unittest.TestCase):
    """Mọi thư viện bên ngoài mà app/ import phải có trong app/requirements.txt.

    Đã sót thật một lần: build_boundaries.py import shapely nhưng requirements không
    khai báo, nên cài xong vẫn chạy không được. Test này bắt đúng lớp lỗi đó.
    """

    NOI_BO = {'backend', 'frontend', 'tests'}

    def _declared(self):
        names = set()
        for line in (REPO / 'backend' / 'requirements.txt').read_text(encoding='utf-8').splitlines():
            line = line.split('#')[0].strip()
            if not line:
                continue
            name = re.split(r'[<>=!\[]', line)[0].strip()
            names.add(name.lower().replace('-', '_'))
            names.add(name.lower().split('.')[0])        # titiler.core -> titiler
        return names

    def _imported(self):
        found = set()
        for path in sorted((REPO / 'backend').rglob('*.py')):
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


class StaticAndSchemaTest(unittest.TestCase):
    """Hai lỗi đã làm người dùng mất thời gian, giữ lại test để không lặp."""

    def setUp(self):
        self.db, self.client, _ = fresh_database(self)

    def test_health_reports_which_interface_files_are_being_served(self):
        """Khi màn hình không giống bản vừa sửa, phải biết ngay máy chủ dùng tệp nào."""
        from backend.api.main import dau_van_giao_dien, van_tay_tung_tep
        body = self.client.get('/api/health').json()
        self.assertEqual(body['dau_van_giao_dien'], dau_van_giao_dien())
        self.assertTrue(body['thu_muc_giao_dien'].endswith('frontend'))
        self.assertEqual(len(body['dau_van_giao_dien']), 12)
        self.assertEqual(set(body['van_tay_tung_tep']),
                         {'index.html', 'style.css', 'app.js'})

    def test_the_fingerprint_ignores_windows_line_endings(self):
        """Git trên Windows đổi LF thành CRLF; không chuẩn hoá thì phép so vô dụng."""
        from backend.api.main import _bam
        self.assertEqual(_bam(b'a\r\nb\r\n'), _bam(b'a\nb\n'))
        self.assertNotEqual(_bam(b'a\nb\n'), _bam(b'a\nc\n'))

    def test_the_sidebar_comes_before_the_map_in_the_markup_and_the_grid(self):
        """Cột lọc phải nằm BÊN TRÁI: ô lưới đầu tiên, và cũng là thẻ đầu tiên."""
        web = REPO / 'frontend'
        html = (web / 'index.html').read_text(encoding='utf-8')
        self.assertLess(html.index('id="cot-loc"'), html.index('id="khung-ban-do"'))
        css = (web / 'style.css').read_text(encoding='utf-8')
        self.assertIn('grid-template-columns:var(--rong-cot) 6px 1fr', css)
        # Không còn quy tắc nào đặt bản đồ vào cột đầu.
        self.assertNotIn('grid-template-areas', css)

    def test_static_files_are_served_with_no_cache(self):
        """Trình duyệt từng giữ style.css cũ rồi ghép với index.html mới -> giao diện lai."""
        for path in ('/', '/style.css', '/app.js'):
            with self.subTest(path=path):
                phan_hoi = self.client.get(path)
                self.assertEqual(phan_hoi.status_code, 200)
                self.assertIn('no-cache', phan_hoi.headers.get('cache-control', ''))

    def test_rebuilding_the_database_never_leaves_it_without_provinces(self):
        """build_cogs dựng lại DB khi schema đổi; thiếu bước nạp tỉnh là giao diện '0 tỉnh'."""
        import sqlite3
        from backend.data import build_indices
        with sqlite3.connect(self.db) as connection:
            connection.execute('PRAGMA user_version = 1')       # giả lập schema cũ
        connection = build_indices.mo(self.db)
        try:
            self.assertEqual(
                connection.execute('SELECT COUNT(*) FROM province').fetchone()[0], 63)
            self.assertEqual(
                connection.execute('PRAGMA user_version').fetchone()[0],
                build_indices.SCHEMA_VERSION)
        finally:
            connection.close()

    def test_build_cogs_alone_still_leaves_a_usable_database(self):
        import sqlite3
        from backend.data import build_cogs
        with sqlite3.connect(self.db) as connection:
            connection.execute('PRAGMA user_version = 1')
        build_cogs.record(self.db, 'cog_image',
                          [('NTL', 2024, '/cog/v.tif', 'VIIRS', 10, 102.0, 8.5, 110.0, 23.5)])
        self.assertEqual(len(self.client.get('/api/provinces').json()['tinh']), 63)


class ColumnNamesMatchThePipelineTest(unittest.TestCase):
    """Tên cột trong app phải trùng tên mà backend/core/chi_so.py thật sự ghi ra.

    Lệch tên thì build_indices vẫn nạp đủ dòng, API vẫn trả 200, giao diện vẫn vẽ —
    chỉ là mọi ô của cột đó trống. Không có gì báo lỗi. Đã xảy ra thật: app đi tìm
    'sol_change_pct', 'rad_mean', 'lit_pixels', 'dien_tich_km2', 'status' trong khi derive
    ghi 'thay_doi_ntl_pct', 'rad_mean', 'lit_pixels', 'area_km2', 'status'.
    Hậu quả nặng nhất: cảnh báo DMSP–VIIRS bị tắt vì derive ghi calibration='PENDING'
    còn app dò 'CHUA_HIEU_CHINH'.
    """

    def _ten_cot_hop_le(self):
        """Tập tên cột mà bảng số liệu cam kết có, lấy từ CODEBOOK.

        Trên nhánh pipeline, hai phép kiểm dưới đây dò thẳng trong mã derive.py và
        harmonize.py. Nhánh night-app không có hai tệp đó, nên đối chiếu với CODEBOOK —
        chính là hợp đồng in ra bảng mô tả trường trong CLAUDE.md, và cũng là thứ nhánh
        pipeline phải tuân theo. Dòng `<KÊNH>_mean / _std` là một mục gộp cho sáu kênh
        phổ và bốn chỉ số, nên phải trải ra.
        """
        from backend.core.chi_so import CODEBOOK
        ten = {c[0] for c in CODEBOOK}
        kenh = ('BLUE', 'GREEN', 'RED', 'NIR', 'SWIR1', 'SWIR2',
                'NDVI', 'NDBI', 'MNDWI', 'BSI')
        return ten | {f'{k}_{h}' for k in kenh for h in ('mean', 'std')}

    def test_every_night_field_appears_in_the_pipeline(self):
        from backend.api import store
        hop_le = self._ten_cot_hop_le()
        thieu = [f for f in store.NIGHT_FIELDS if f not in hop_le]
        self.assertEqual(thieu, [], f'Cột đêm không có trong CODEBOOK: {thieu}')

    def test_every_day_field_appears_in_derive(self):
        from backend.api import store
        # months_used do build_indices tạo khi gộp tháng lên năm.
        hop_le = self._ten_cot_hop_le() | {'months_used'}
        thieu = [f for f in store.DAY_FIELDS if f not in hop_le]
        self.assertEqual(thieu, [], f'Cột ngày không có trong CODEBOOK: {thieu}')

    def test_every_indicator_code_is_a_column_of_its_table(self):
        import sqlite3
        from backend.api import store
        db, _, _ = fresh_database(self)
        with sqlite3.connect(db) as connection:
            for entry in store.INDICATORS:
                cot = {r[1] for r in connection.execute(
                    f"PRAGMA table_info({entry['bang']})")}
                with self.subTest(chi_so=entry['ma']):
                    self.assertIn(entry['ma'], cot)

    def test_the_calibration_flag_derive_actually_writes_is_accepted(self):
        """Pipeline ghi calibration='PENDING'; CLAUDE.md nói 'CHUA_HIEU_CHINH'. Nhận cả hai.

        Nhánh này không có mã pipeline để đối chiếu, nên chỉ kiểm được nửa phía app:
        store phải chấp nhận CẢ HAI giá trị. Nếu không, cảnh báo DMSP-VIIRS sẽ tắt
        lặng lẽ đúng như đã xảy ra một lần.
        """
        store_source = (REPO / 'backend' / 'api' / 'store.py').read_text(encoding='utf-8')
        self.assertIn("'PENDING'", store_source)
        self.assertIn("'CHUA_HIEU_CHINH'", store_source)

    def test_a_dmsp_to_viirs_series_always_carries_the_warning(self):
        """Chuỗi có cả hai nguồn thì cảnh báo phải hiện, dù cột calibration ghi gì."""
        import sqlite3
        from backend.api import store
        db, _, _ = fresh_database(self)
        with sqlite3.connect(db) as connection:
            connection.executemany(
                'INSERT OR REPLACE INTO ntl_annual(province_code,year,source,sol,calibration) '
                'VALUES(?,?,?,?,?)',
                [('01', y, 'DMSP' if y <= 2013 else 'VIIRS', 1.0, None)
                 for y in range(2004, 2026)])
        data = store.indices('01', 2004, 2025)
        self.assertTrue(any('DMSP' in w and 'VIIRS' in w for w in data['canh_bao']))
        self.assertTrue(any('F16' in w for w in data['canh_bao']),
                        'chuỗi 2004-2025 cũng bắc qua mốc F16->F18 năm 2010')

    def test_a_series_entirely_inside_the_f18_years_carries_no_2010_warning(self):
        import sqlite3
        from backend.api import store
        db, _, _ = fresh_database(self)
        with sqlite3.connect(db) as connection:
            connection.executemany(
                'INSERT OR REPLACE INTO ntl_annual(province_code,year,source,sol) '
                'VALUES(?,?,?,?)', [('01', y, 'DMSP', 1.0) for y in range(2010, 2014)])
        data = store.indices('01', 2010, 2013)
        self.assertFalse(any('F16' in w for w in data['canh_bao']), data['canh_bao'])


class BuildBoundariesTest(unittest.TestCase):
    """Chỉ kiểm phần ghép nối. Việc tải GADM thật cần mạng, chạy trên máy người dùng."""

    def test_missing_boundaries_explain_the_one_command_that_fixes_it(self):
        from backend.data import build_boundaries
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
        from backend.data import build_boundaries
        goi = []
        module = types.ModuleType('backend.core.ranh_gioi.prepare_gadm')
        module.prepare = lambda config: goi.append(config) or 63
        with tempfile.TemporaryDirectory() as directory:
            config = {'boundaries': str(Path(directory) / 'x.geojson'),
                      'boundary_metadata': str(Path(directory) / 'x.json'),
                      'boundary_policy': 'gadm41_research'}
            path = Path(directory) / 'c.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            with mock.patch.dict(sys.modules, {'backend.core.ranh_gioi.prepare_gadm': module}), \
                 mock.patch('backend.core.ranh_gioi.boundaries.load_boundaries',
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

    def test_the_default_config_points_inside_this_branch(self):
        """Nhánh này không có gói pipeline, nên ranh giới phải nằm cạnh mã dựng ra nó.

        Trước đây DEFAULT_CONFIG trỏ vào province_pipeline/config/ và được đối chiếu với
        task_pipeline/local.py. Cả hai đã bị xoá khỏi nhánh night-app, nên phép đối chiếu
        đó không còn nghĩa; thay bằng việc buộc đường dẫn nằm trong backend/.
        """
        from backend.data.build_boundaries import DEFAULT_CONFIG
        self.assertEqual(DEFAULT_CONFIG['boundary_policy'], 'gadm41_research')
        for key in ('boundaries', 'boundary_metadata'):
            self.assertTrue(DEFAULT_CONFIG[key].startswith('backend/core/ranh_gioi/'),
                            DEFAULT_CONFIG[key])


class BuildCogsTest(unittest.TestCase):
    """Phần tìm ảnh và ghi sổ phải đúng; việc gọi gdal chỉ chạy trên máy có gdal-bin."""

    def test_sources_are_found_by_year_for_both_naming_shapes(self):
        from backend.data import build_cogs
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
        """Ảnh gốc 24 GB chỉ được ghi sổ ở tầng lạnh, không bao giờ vào bảng cog_image."""
        import sqlite3
        from backend.data import build_cogs
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'x.db'
            build_cogs.record(db, 'cog_image',
                              [('NTL', 2024, '/cog/v.tif', 'VIIRS', 10,
                                102.0, 8.5, 110.0, 23.5)])
            build_cogs.record(db, 'source_image', [('SENTINEL2', 2024, '/data/vn.vrt', 2 << 34, 'lạnh')])
            with sqlite3.connect(db) as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM cog_image').fetchone()[0], 1)
                self.assertEqual(connection.execute('SELECT kind FROM cog_image').fetchone()[0], 'NTL')
                self.assertEqual(connection.execute(
                    'SELECT path FROM source_image').fetchone()[0], '/data/vn.vrt')
                # Phạm vi ảnh phải được ghi: thiếu nó thì bản đồ xin ô khắp thế giới.
                self.assertEqual(connection.execute(
                    'SELECT west,south,east,north FROM cog_image').fetchone(),
                    (102.0, 8.5, 110.0, 23.5))

    def test_the_illustrative_day_image_is_rgb_eight_bit_and_downsampled(self):
        """Lời cô dặn: ảnh ngày phải nén lại, mỗi năm một ảnh. Lệnh phải phản ánh đúng thế."""
        from backend.data import build_cogs
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


class TheProvincePickerIsSortedAndSearchable(unittest.TestCase):
    """Cô dặn: danh sách tỉnh xếp A-Z và gõ tìm được tên tỉnh."""

    def setUp(self):
        self.js = (REPO / 'frontend' / 'app.js').read_text(encoding='utf-8')
        self.html = (REPO / 'frontend' / 'index.html').read_text(encoding='utf-8')

    def test_the_list_is_sorted_with_vietnamese_collation(self):
        """localeCompare('vi') mới xếp đúng a < ă < â; sort() trần thì Bắc đứng trước Bạc."""
        self.assertIn("localeCompare", self.js)
        self.assertIn("'vi'", self.js)

    def test_there_is_a_search_box_wired_to_the_list(self):
        self.assertIn('id="tim-tinh"', self.html)
        self.assertIn("$('tim-tinh').oninput", self.js)

    def test_typing_without_diacritics_still_matches(self):
        """Người dùng hiếm khi gõ đủ dấu: 'ba ria' phải ra 'Bà Rịa - Vũng Tàu'."""
        self.assertIn('normalize', self.js)
        self.assertIn('u0300-\\u036f', self.js)
        self.assertIn("replace(/đ/g, 'd')", self.js)

    def test_the_api_keeps_the_official_order(self):
        """Sắp xếp là việc của giao diện. API giữ thứ tự mã thống kê vì nơi khác dựa vào."""
        store_src = (REPO / 'backend' / 'api' / 'store.py').read_text(encoding='utf-8')
        self.assertIn('ORDER BY t.number', store_src)


class AnOldTableIsNotReportedAsMissingData(unittest.TestCase):
    """Bảng cũ còn tên cột tiếng Việt thì phải nói là ĐỌC KHÔNG ĐƯỢC, không phải 'chưa có'.

    Hai câu đó dẫn người dùng đi hai hướng khác hẳn nhau: một bên đi tìm tệp, một bên
    chạy lại bước tính chỉ số. Nói sai ở đây làm mất cả buổi.
    """

    def _nap(self, header, dong):
        import csv
        from backend.data import build_indices
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'VN_NTL_Panel_2004_2025' / 'data_processed'
            out.mkdir(parents=True)
            with (out / 'ntl_annual.csv').open('w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()
                writer.writerows(dong)
            return build_indices.build(tmp, Path(tmp) / 'x.db')['ntl_annual']

    def test_vietnamese_column_names_are_reported_as_unreadable(self):
        info = self._nap(['ma_tinh', 'nam', 'sol_ntl'],
                         [{'ma_tinh': '01', 'nam': 2014, 'sol_ntl': 1.0}])
        self.assertEqual(info['rows'], 0)
        self.assertIn('province_code', info['khong_doc_duoc'])
        self.assertIn('1 dòng', info['khong_doc_duoc'])

    def test_a_genuinely_absent_file_is_still_reported_as_absent(self):
        from backend.data import build_indices
        with tempfile.TemporaryDirectory() as tmp:
            info = build_indices.build(tmp, Path(tmp) / 'x.db')['ntl_annual']
        self.assertEqual(info['rows'], 0)
        self.assertIsNone(info['khong_doc_duoc'])

    def test_a_current_table_still_loads(self):
        info = self._nap(['province_code', 'year', 'sol'],
                         [{'province_code': '01', 'year': 2014, 'sol': 1.0}])
        self.assertEqual(info['rows'], 1)
        self.assertIsNone(info.get('khong_doc_duoc'))


class TheFieldTableInClaudeMdMatchesTheCodebook(unittest.TestCase):
    """CLAUDE.md là nơi người ta tra tên cột. Lệch với mã nguồn là tra ra số sai."""

    def _bang(self):
        return (REPO / 'CLAUDE.md').read_text(encoding='utf-8')

    def test_every_documented_column_exists_in_the_codebook(self):
        from backend.core.chi_so import CODEBOOK
        ten = {c[0] for c in CODEBOOK}
        for name in ten:
            with self.subTest(cot=name):
                self.assertIn(f'| `{name}` |', self._bang(),
                              f'{name} có trong CODEBOOK nhưng thiếu ở CLAUDE.md')

    def test_the_night_table_columns_are_all_documented(self):
        """Mọi cột app đọc từ ntl_annual phải tra được trong CLAUDE.md."""
        from backend.api import store
        bang = self._bang()
        for name in store.NIGHT_FIELDS:
            with self.subTest(cot=name):
                self.assertIn(f'| `{name}` |', bang)

    def test_the_column_names_are_english(self):
        """Dấu hiệu sót lại của đợt đổi tên: cột vẫn mang tên tiếng Việt."""
        from backend.core.chi_so import CODEBOOK
        viet = ('ma_tinh', 'ten_tinh', 'nam', 'thang', 'sol_ntl', 'mat_do_ntl',
                'thay_doi_ntl', 'cv_ntl', 'dt_sang_km2', 'nguon_anh', 'trang_thai',
                'hieu_chinh', 'ghi_chu', 'dt_tu_nhien_km2')
        for name, *_ in CODEBOOK:
            self.assertNotIn(name, viet, f'cột {name} chưa đổi sang tiếng Anh')


class EconomyIndicatorDocTest(unittest.TestCase):
    """Tài liệu chỉ số kinh tế đêm phải khớp với danh mục thật trong app.

    Tài liệu này được dùng cho báo cáo, nên một tên cột sai ở đây sẽ đi thẳng vào bài viết.
    """

    DOC = REPO / 'docs' / 'CHI_SO_KINH_TE_DEM.md'

    # Tên nhóm B là ĐỀ XUẤT, chưa tồn tại trong app; liệt kê để test không báo nhầm.
    DE_XUAT = {'sol_bq_dau_nguoi', 'do_co_gian_sol_gdp', 'gdp_du_bao_tu_anh',
               'chenh_lech_gdp_anh', 'sol_tren_gdp', 'cuong_do_vung_sang',
               'ty_trong_sol_quoc_gia', 'gdp_du_bao'}

    def test_the_three_mandated_indicators_are_documented_and_real(self):
        from backend.api import store
        text = self.DOC.read_text(encoding='utf-8')
        for ma in ('sol', 'sol_density', 'sol_change_pct'):
            with self.subTest(chi_so=ma):
                self.assertIn(f'`{ma}`', text)
                self.assertIn(ma, store.NIGHT_FIELDS)

    def test_every_group_a_column_named_in_the_doc_exists_in_the_app(self):
        import re
        from backend.api import store
        text = self.DOC.read_text(encoding='utf-8')
        thuc = set(store.NIGHT_FIELDS) | {i['ma'] for i in store.INDICATORS}
        bo_qua = self.DE_XUAT | {
            'province_code', 'year', 'economy', 'population', 'gdp', 'sol_t', 'sol_viirs', 'sol_dmsp',
            'stable_lights', 'data_processed', 'metadata', 'backend', 'derive',
            'ntl_annual', '_hc'}
        ten = {t for t in re.findall(r'`([a-z0-9_]+)`', text)
               if '.' not in t and '/' not in t}
        thieu = sorted(t for t in ten - thuc - bo_qua)
        self.assertEqual(thieu, [], f'Tài liệu nhắc cột không có thật: {thieu}')

    def test_it_states_the_three_method_constraints(self):
        """Ba ràng buộc này là chỗ dễ làm hỏng toàn bộ phân tích nếu bỏ qua."""
        text = self.DOC.read_text(encoding='utf-8')
        self.assertIn('giá so sánh', text)        # khử lạm phát trước khi tính độ co giãn
        self.assertIn('_hc', text)                # bắc qua 2013 phải dùng chuỗi đã hiệu chỉnh
        self.assertIn('Gibson', text)             # DMSP kém tin cậy ở tỉnh nhỏ


class MonthlyIndicesLoadIntoTheDatabase(unittest.TestCase):
    """Chỉ số tháng phải vào bảng riêng, giữ nguyên từng tháng chứ không gộp lên năm."""

    def _nap(self, dong, header=None):
        import csv
        from backend.data import build_indices
        header = header or list(dong[0])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'VN_NTL_Panel_2004_2025' / 'data_processed'
            out.mkdir(parents=True)
            with (out / 'ntl_monthly.csv').open('w', encoding='utf-8-sig', newline='') as f:
                w = csv.DictWriter(f, fieldnames=header)
                w.writeheader()
                w.writerows(dong)
            db = Path(tmp) / 'x.db'
            bao = build_indices.build(tmp, db)['ntl_monthly']
            import sqlite3
            with sqlite3.connect(db) as con:
                hang = con.execute(
                    'SELECT province_code,year,month,sol FROM ntl_monthly '
                    'ORDER BY province_code,year,month').fetchall()
            return bao, hang

    def _dong(self, ma, year, month, sol):
        return dict(province_code=ma, province_name='T', year=year, month=month,
                    period=f'{year}-{month:02}', source='VIIRS', sol=sol,
                    sol_ma3=sol, cloud_free_obs=9.5, status='OK')

    def test_each_month_stays_its_own_row(self):
        """Gộp 12 tháng thành một dòng năm là mất đúng thứ biểu đồ tháng cần."""
        dong = [self._dong('01', 2024, m, 100.0 + m) for m in range(1, 13)]
        bao, hang = self._nap(dong)
        self.assertEqual(bao['rows'], 12)
        self.assertEqual(len(hang), 12)
        self.assertEqual([h[2] for h in hang], list(range(1, 13)))
        self.assertEqual(hang[0][3], 101.0)

    def test_the_key_is_province_year_month(self):
        """Hai tỉnh cùng tháng, một tỉnh hai năm — không dòng nào đè dòng nào."""
        dong = [self._dong('01', 2024, 7, 10.0), self._dong('27', 2024, 7, 20.0),
                self._dong('01', 2025, 7, 30.0)]
        _, hang = self._nap(dong)
        self.assertEqual(len(hang), 3)
        self.assertEqual({(h[0], h[1]) for h in hang}, {('01', 2024), ('27', 2024), ('01', 2025)})

    def test_a_row_without_a_real_month_is_skipped(self):
        """Dòng theo năm lọt vào tệp tháng thì bỏ, không nhét month = 0."""
        dong = [self._dong('01', 2024, 7, 10.0)]
        dong.append(dict(dong[0], month=0, sol=99.0))
        dong.append(dict(dong[0], month=13, sol=98.0))
        bao, hang = self._nap(dong)
        self.assertEqual(bao['rows'], 1)
        self.assertEqual(hang[0][2], 7)

    def test_the_province_code_keeps_its_leading_zero(self):
        _, hang = self._nap([self._dong('01', 2024, 7, 10.0)])
        self.assertEqual(hang[0][0], '01')

    def test_the_monthly_columns_the_charts_need_are_in_the_schema(self):
        """Ba cột này là lý do bảng tháng tồn tại; thiếu là biểu đồ tháng vô dụng."""
        import sqlite3
        from backend.data import build_indices
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'x.db'
            build_indices.build(tmp, db)
            with sqlite3.connect(db) as con:
                cot = {r[1] for r in con.execute('PRAGMA table_info(ntl_monthly)')}
        for ten in ('sol_ma3', 'sol_change_mom_pct', 'sol_change_yoy_pct', 'cloud_free_obs'):
            with self.subTest(cot=ten):
                self.assertIn(ten, cot)


class ThePanelTakesManyIndicatorsAndMonthlyPeriods(unittest.TestCase):
    """Màn 2 cần tick nhiều tỉnh, nhiều chỉ số, nhiều mốc — kể cả mốc tháng."""

    def setUp(self):
        import sqlite3
        self.db, self.client, _ = fresh_database(self)
        with sqlite3.connect(self.db) as con:
            con.executemany(
                'INSERT OR REPLACE INTO ntl_annual(province_code,year,source,sol,rad_cv) '
                'VALUES(?,?,?,?,?)',
                [('01', y, 'VIIRS', 100.0 + y, 1.5) for y in (2023, 2024)])
            con.executemany(
                'INSERT OR REPLACE INTO ntl_monthly'
                '(province_code,year,month,source,sol,sol_ma3,cloud_free_obs) '
                'VALUES(?,?,?,?,?,?,?)',
                [('01', 2024, m, 'VIIRS', 10.0 + m, 9.0 + m, 7.5) for m in (1, 2, 3)])

    def test_two_indicators_give_two_rows_per_province(self):
        body = self.client.get('/api/panel', params={
            'chi_so': 'sol,rad_cv', 'moc': '2024', 'province_code': '01'}).json()
        self.assertEqual([d['chi_so'] for d in body['dong']], ['sol', 'rad_cv'])
        self.assertEqual(body['dong'][0]['gia_tri'], [2124.0])
        self.assertEqual(body['dong'][1]['gia_tri'], [1.5])

    def test_a_monthly_period_reads_the_monthly_table(self):
        body = self.client.get('/api/panel', params={
            'chi_so': 'sol', 'moc': '2024-01,2024-02,2024-03',
            'province_code': '01'}).json()
        self.assertEqual(body['moc'], ['2024-01', '2024-02', '2024-03'])
        self.assertEqual(body['dong'][0]['gia_tri'], [11.0, 12.0, 13.0])
        self.assertTrue(body['co_thang'])

    def test_years_and_months_can_be_mixed_and_come_out_in_order(self):
        body = self.client.get('/api/panel', params={
            'chi_so': 'sol', 'moc': '2024-02,2023,2024-01', 'province_code': '01'}).json()
        self.assertEqual(body['moc'], ['2023', '2024-01', '2024-02'])
        self.assertEqual(body['dong'][0]['gia_tri'], [2123.0, 11.0, 12.0])

    def test_a_monthly_only_indicator_is_empty_on_a_yearly_period(self):
        """sol_ma3 chỉ có theo tháng; hỏi theo năm thì trống chứ không nổ."""
        body = self.client.get('/api/panel', params={
            'chi_so': 'sol_ma3', 'moc': '2024,2024-02', 'province_code': '01'}).json()
        self.assertEqual(body['dong'][0]['gia_tri'], [None, 11.0])

    def test_an_indicator_without_a_monthly_table_is_empty_on_a_monthly_period(self):
        body = self.client.get('/api/panel', params={
            'chi_so': 'sol_cal', 'moc': '2024-02', 'province_code': '01'}).json()
        self.assertEqual(body['dong'][0]['gia_tri'], [None])

    def test_a_malformed_period_is_rejected_not_guessed(self):
        for xau in ('2024-13', '24-01', 'abc', "2024'; DROP TABLE province;--"):
            with self.subTest(moc=xau):
                self.assertEqual(self.client.get('/api/panel', params={
                    'chi_so': 'sol', 'moc': xau}).status_code, 400)
        self.assertEqual(len(self.client.get('/api/provinces').json()['tinh']), 63)

    def test_the_csv_column_headers_are_the_periods(self):
        csv_text = self.client.get('/api/panel.csv', params={
            'chi_so': 'sol', 'moc': '2024-01,2024-02',
            'province_code': '01'}).content.decode('utf-8-sig')
        self.assertIn('province_code,province_name,chi_so,don_vi,source,2024-01,2024-02', csv_text)

    def test_every_monthly_indicator_is_a_real_column_of_the_monthly_table(self):
        import sqlite3
        from backend.api import store
        with sqlite3.connect(self.db) as con:
            cot = {r[1] for r in con.execute('PRAGMA table_info(ntl_monthly)')}
        for entry in store.INDICATORS:
            if entry.get('bang_thang'):
                with self.subTest(chi_so=entry['ma']):
                    self.assertIn(entry['ma'], cot)


class DownloadingOneProvincesImage(unittest.TestCase):
    """Chọn một tỉnh rồi bấm tải thì phải ra ảnh của riêng tỉnh đó, không phải cả nước."""

    def _dung(self, co_ranh_gioi=True):
        import json
        import sqlite3
        import numpy as np
        import rasterio
        from affine import Affine
        from backend.data.build_cogs import record
        thu_muc = tempfile.TemporaryDirectory()
        self.addCleanup(thu_muc.cleanup)
        goc = Path(thu_muc.name)
        # ảnh 20x20 phủ 105–107°Đ, 20–22°B
        anh = goc / 'ntl.tif'
        with rasterio.open(anh, 'w', driver='GTiff', width=20, height=20, count=1,
                           dtype='float32', crs='EPSG:4326', nodata=-9999,
                           transform=Affine(.1, 0, 105, 0, -.1, 22)) as ds:
            ds.write(np.full((1, 20, 20), 5.0, dtype='float32'))
        db = goc / 'x.db'
        from backend.data import build_indices
        build_indices.build(thu_muc.name, db)
        record(db, 'cog_image', [('NTL', 2024, 7, str(anh), 'VIIRS', 10,
                                  105.0, 20.0, 107.0, 22.0)], theo_thang=True)
        if co_ranh_gioi:
            # một ô vuông nhỏ ở góc, nhỏ hơn hẳn ảnh gốc
            gj = {'type': 'FeatureCollection', 'features': [
                {'type': 'Feature', 'properties': {'province_code': '01'},
                 'geometry': {'type': 'Polygon', 'coordinates': [
                     [[105.1, 21.9], [105.5, 21.9], [105.5, 21.5], [105.1, 21.5],
                      [105.1, 21.9]]]}}]}
            rg = goc / 'rg.geojson'
            rg.write_text(json.dumps(gj), encoding='utf-8')
            os.environ['VNGIS_BOUNDARIES'] = str(rg)
            self.addCleanup(os.environ.pop, 'VNGIS_BOUNDARIES', None)
        os.environ['VNGIS_DB'] = str(db)
        self.addCleanup(os.environ.pop, 'VNGIS_DB', None)
        from fastapi.testclient import TestClient
        from backend.api.main import app
        return TestClient(app)

    def test_the_clipped_image_is_smaller_than_the_national_one(self):
        import rasterio
        client = self._dung()
        ca_nuoc = client.get('/api/anh-dem.tif', params={'nam': 2024, 'thang': 7})
        mot_tinh = client.get('/api/anh-dem.tif',
                              params={'nam': 2024, 'thang': 7, 'province_code': '01'})
        self.assertEqual(mot_tinh.status_code, 200, mot_tinh.text[:300])
        with rasterio.io.MemoryFile(mot_tinh.content) as m, m.open() as ds:
            self.assertLess(ds.width, 20)
            self.assertLess(ds.height, 20)
            # Cắt bám lưới pixel nên biên nở ra ngoài tối đa một ô (0,1 độ).
            self.assertGreaterEqual(ds.bounds.left, 105.0 - 1e-9)
            self.assertLessEqual(ds.bounds.left, 105.1 + 1e-9)
            self.assertLessEqual(ds.bounds.right, 105.6 + 1e-9)
        self.assertEqual(ca_nuoc.status_code, 200)

    def test_outside_the_boundary_is_nodata_not_zero(self):
        """0 là một giá trị bức xạ hợp lệ; dùng nó cho vùng ngoài tỉnh là bịa số liệu."""
        import numpy as np
        import rasterio
        client = self._dung()
        r = client.get('/api/anh-dem.tif',
                       params={'nam': 2024, 'thang': 7, 'province_code': '01'})
        with rasterio.io.MemoryFile(r.content) as m, m.open() as ds:
            self.assertIsNotNone(ds.nodata)
            self.assertNotEqual(ds.nodata, 0)
            self.assertFalse(np.any(ds.read(1) == 0))

    def test_the_filename_is_ascii_so_the_http_header_survives(self):
        client = self._dung()
        r = client.get('/api/anh-dem.tif',
                       params={'nam': 2024, 'thang': 7, 'province_code': '01'})
        ten = r.headers['content-disposition']
        ten.encode('latin-1')
        self.assertIn('VN_NTL_01_', ten)

    def test_without_boundaries_it_says_which_command_to_run(self):
        client = self._dung(co_ranh_gioi=False)
        r = client.get('/api/anh-dem.tif',
                       params={'nam': 2024, 'thang': 7, 'province_code': '01'})
        self.assertEqual(r.status_code, 404)
        self.assertIn('build_boundaries', r.json()['detail'])

    def test_an_unknown_province_is_a_404(self):
        client = self._dung()
        r = client.get('/api/anh-dem.tif',
                       params={'nam': 2024, 'thang': 7, 'province_code': '99'})
        self.assertEqual(r.status_code, 404)


class TimeFunctionsOnThePanel(unittest.TestCase):
    """Hàm thời gian thành một cột phụ; từ chối chạy khi khoảng bắc qua mốc đổi vệ tinh."""

    def setUp(self):
        import sqlite3
        self.db, self.client, _ = fresh_database(self)
        with sqlite3.connect(self.db) as con:
            con.executemany(
                'INSERT OR REPLACE INTO ntl_annual'
                '(province_code,year,source,sol,sol_cal,obs_status) VALUES(?,?,?,?,?,?)',
                [('01', 2014 + i, 'VIIRS', 100.0 * 1.1 ** i, 100.0 * 1.1 ** i,
                  'B' if 2014 + i == 2014 else 'A') for i in range(4)])
            con.executemany(
                'INSERT OR REPLACE INTO ntl_annual'
                '(province_code,year,source,sol,sol_cal) VALUES(?,?,?,?,?)',
                [('27', y, 'DMSP' if y <= 2013 else 'VIIRS', 100.0, 100.0)
                 for y in (2012, 2013, 2014, 2015)])

    def _goi(self, **kw):
        kw.setdefault('province_code', '01')
        return self.client.get('/api/panel', params=kw).json()

    def test_the_growth_rate_comes_back_as_an_extra_column(self):
        body = self._goi(chi_so='sol', moc='2014,2015,2016,2017', ham='cagr')
        self.assertEqual([h['ma'] for h in body['ham']], ['cagr'])
        self.assertAlmostEqual(body['dong'][0]['ham']['cagr'], 10.0, places=4)

    def test_several_functions_at_once(self):
        body = self._goi(chi_so='sol', moc='2014,2015,2016,2017', ham='tong,trung_binh')
        self.assertEqual(set(body['dong'][0]['ham']), {'tong', 'trung_binh'})

    def test_growth_across_a_satellite_break_is_refused_not_guessed(self):
        """Một con số trông như thật còn tệ hơn một ô trống."""
        body = self._goi(chi_so='sol', moc='2012,2013,2014,2015',
                         province_code='27', ham='cagr,tong')
        dong = body['dong'][0]
        self.assertIsNone(dong['ham']['cagr'])
        self.assertIsNotNone(dong['ham']['tong'], 'tổng không phụ thuộc mốc, vẫn phải tính')
        self.assertTrue(dong['ham_tu_choi'])

    def test_the_calibrated_column_may_cross_the_2013_break(self):
        """sol_cal đã quy về cùng thang VIIRS nên đi qua mốc 2013 được."""
        body = self._goi(chi_so='sol_cal', moc='2012,2013,2014,2015',
                         province_code='27', ham='cagr')
        self.assertIsNone(body['dong'][0]['ham_tu_choi'])

    def test_2010_still_blocks_even_the_calibrated_column(self):
        """Mốc 2010 chưa hiệu chỉnh ở BẤT KỲ cột nào, kể cả cột _cal."""
        body = self._goi(chi_so='sol_cal', moc='2009,2010,2011',
                         province_code='27', ham='cagr')
        self.assertTrue(body['dong'][0]['ham_tu_choi'])

    def test_an_unknown_function_is_ignored_not_crashed(self):
        body = self._goi(chi_so='sol', moc='2014,2015', ham='khong_co_that')
        self.assertEqual(body['ham'], [])


class TheFlagsTravelWithTheValues(unittest.TestCase):

    def setUp(self):
        import sqlite3
        self.db, self.client, _ = fresh_database(self)
        with sqlite3.connect(self.db) as con:
            con.executemany(
                'INSERT OR REPLACE INTO ntl_annual'
                '(province_code,year,source,sol,obs_status) VALUES(?,?,?,?,?)',
                [('01', 2009, 'DMSP', 10.0, 'A'), ('01', 2010, 'DMSP', 31.0, 'B'),
                 ('01', 2011, 'DMSP', 32.0, 'U')])

    def test_each_value_has_a_matching_flag_slot(self):
        body = self.client.get('/api/panel', params={
            'chi_so': 'sol', 'moc': '2009,2010,2011', 'province_code': '01'}).json()
        dong = body['dong'][0]
        self.assertEqual(len(dong['co']), len(dong['gia_tri']))
        self.assertEqual(dong['co'], [None, 'B', 'U'])

    def test_a_normal_flag_is_not_sent(self):
        """'A' là bình thường: gửi về chỉ làm nặng tải và nặng mắt."""
        body = self.client.get('/api/panel', params={
            'chi_so': 'sol', 'moc': '2009', 'province_code': '01'}).json()
        self.assertEqual(body['dong'][0]['co'], [None])

    def test_the_legend_comes_with_the_table(self):
        body = self.client.get('/api/panel', params={'chi_so': 'sol', 'moc': '2010'}).json()
        self.assertIn('B', body['chu_giai_co'])
        self.assertIn('vệ tinh', body['chu_giai_co']['B'])


class TheNightEconomyScreen(unittest.TestCase):
    """Màn 3: ánh sáng bình quân đầu người và hệ số co giãn β."""

    def _nap(self, co_so_gia='so_sanh', so_nam=12):
        import math
        import sqlite3
        db, client, _ = fresh_database(self)
        with sqlite3.connect(db) as con:
            # Mã tỉnh của Cục Thống kê KHÔNG liên tục (không có 03, 05): phải lấy mã thật,
            # nếu không phép nối với bảng province sẽ loại bớt dòng.
            ma_that = [r[0] for r in con.execute(
                'SELECT province_code FROM province ORDER BY number LIMIT 6')]
            for i, ma in enumerate(ma_that):
                for t in range(so_nam):
                    nam = 2014 + t
                    sol = 1000 * (1 + 0.2 * i) * (1.07 ** t)
                    grdp = math.exp(2.0 + 0.8 * math.log(sol))
                    con.execute('INSERT OR REPLACE INTO ntl_annual'
                                '(province_code,year,source,sol) VALUES(?,?,?,?)',
                                (ma, nam, 'VIIRS', sol))
                    con.execute('INSERT OR REPLACE INTO economy'
                                '(province_code,year,population,grdp,grdp_price_basis) '
                                'VALUES(?,?,?,?,?)', (ma, nam, 1_000_000 * (i + 1),
                                                      grdp, co_so_gia))
        return client

    def test_an_empty_economy_table_is_not_an_error(self):
        """App phải chạy được khi cô chưa gửi số liệu."""
        _, client, _ = fresh_database(self)
        r = client.get('/api/kinh-te-dem')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body['dong'], [])
        self.assertIsNone(body['hoi_quy'])
        self.assertTrue(body['canh_bao'])

    def test_beta_comes_back_from_real_rows(self):
        body = self._nap().get('/api/kinh-te-dem').json()
        self.assertAlmostEqual(body['hoi_quy']['beta'], 0.8, places=5)
        self.assertEqual(body['hoi_quy']['n'], 72, '6 tỉnh × 12 năm')

    def test_light_per_capita_is_on_every_row(self):
        body = self._nap().get('/api/kinh-te-dem').json()
        r = body['dong'][0]
        self.assertAlmostEqual(r['sol_per_capita'], r['sol'] / r['population'], places=9)

    def test_current_prices_warn_loudly(self):
        body = self._nap(co_so_gia='hien_hanh').get('/api/kinh-te-dem').json()
        self.assertTrue(any('GIÁ HIỆN HÀNH' in c for c in body['canh_bao']))

    def test_a_missing_price_basis_also_warns(self):
        body = self._nap(co_so_gia=None).get('/api/kinh-te-dem').json()
        self.assertTrue(any('Chưa biết' in c for c in body['canh_bao']))

    def test_each_province_gets_its_own_beta_when_long_enough(self):
        body = self._nap(so_nam=12).get('/api/kinh-te-dem').json()
        self.assertTrue(all(r['beta_tinh'] is not None for r in body['dong']))
        ngan = self._nap(so_nam=4).get('/api/kinh-te-dem').json()
        self.assertTrue(all(r['beta_tinh'] is None for r in ngan['dong']))

    def test_the_sample_csv_has_the_columns_the_loader_expects(self):
        import csv
        from backend.data import build_indices
        mau = REPO / 'backend' / 'data' / 'economy_mau.csv'
        self.assertTrue(mau.is_file(), 'tệp mẫu để cô điền số liệu')
        with mau.open(encoding='utf-8-sig') as f:
            cot = set(next(csv.reader(f)))
        _, _, _ = fresh_database(self)
        import sqlite3
        from backend.api import store
        with sqlite3.connect(store.database_path()) as con:
            that = {r[1] for r in con.execute('PRAGMA table_info(economy)')}
        self.assertTrue(cot <= that, f'cột thừa trong tệp mẫu: {cot - that}')
        for bat_buoc in ('province_code', 'year', 'population', 'grdp', 'grdp_price_basis'):
            self.assertIn(bat_buoc, cot)


def test_ranh_gioi_doc_duoc_ca_khoa_cu(tmp_path, monkeypatch):
    """GeoJSON dựng trước đợt đổi tên cột mang khoá ma_tinh — vẫn phải cắt được.

    Lỗi đã gặp: build_boundaries ghi 'ma_tinh' còn giao diện đọc 'province_code',
    nên chọn Hà Nội thì bản đồ không cắt theo ranh giới mà không báo lỗi gì rõ ràng.
    """
    from backend.api import main as api
    o = {'type': 'Polygon', 'coordinates': [[[105., 20.], [106., 20.], [106., 21.], [105., 20.]]]}
    cu = tmp_path / 'cu.geojson'
    cu.write_text(json.dumps({'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'ma_tinh': '01', 'ten_tinh': 'Hà Nội'},
         'geometry': o}]}), encoding='utf-8')
    monkeypatch.setenv('VNGIS_BOUNDARIES', str(cu))
    assert api._hinh_tinh('01') is not None, 'không đọc được khoá ma_tinh cũ'

    moi = tmp_path / 'moi.geojson'
    moi.write_text(json.dumps({'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'province_code': '01', 'province_name': 'Hà Nội'},
         'geometry': o}]}), encoding='utf-8')
    monkeypatch.setenv('VNGIS_BOUNDARIES', str(moi))
    assert api._hinh_tinh('01') is not None


def test_build_boundaries_ghi_khoa_tieng_anh():
    """Bản dựng mới phải ghi đúng tên khoá mà frontend/app.js đang đọc."""
    nguon = Path('backend/data/build_boundaries.py').read_text(encoding='utf-8')
    assert "'province_code': code" in nguon
    assert "'ma_tinh': code" not in nguon


def test_gia_lap_kinh_te_khoi_phuc_dung_beta(tmp_path):
    """Số giả lập phải (a) mang nhãn GIA_LAP, (b) để hồi quy tìm lại đúng beta đã cấy.

    Nếu ước lượng không trả lại con số đã cấy thì phép hồi quy sai, chứ không phải
    dữ liệu sai — đây là cách duy nhất kiểm được do_co_gian trên bộ số đã biết đáp án.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'gia_lap', Path(__file__).resolve().parent.parent / 'backend' / 'data' / 'gia_lap_kinh_te.py')
    gia_lap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gia_lap)
    from backend.core.chi_so import do_co_gian

    import math
    import random
    rng = random.Random(3)
    theo_tinh = {f'{i:02d}': {n: math.exp(rng.gauss(10, 1.2)) for n in range(2014, 2026)}
                 for i in range(1, 64)}
    dong = gia_lap.sinh(theo_tinh, beta=0.45, alpha=9.0, nhieu=0.2)
    assert len(dong) == 63 * 12
    assert all('GIA_LAP' in d['source'] for d in dong), 'thiếu nhãn giả lập'
    assert all(d['grdp'] > 0 and d['population'] > 0 for d in dong)

    for d in dong:
        d['sol'] = theo_tinh[d['province_code']][d['year']]
    ket = do_co_gian(dong, gia_so_sanh=True)
    assert abs(ket['beta'] - 0.45) < 0.06, f"beta lệch quá: {ket['beta']}"
    assert ket['n'] == 63 * 12
