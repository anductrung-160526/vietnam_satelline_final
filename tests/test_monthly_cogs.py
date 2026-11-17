"""Ghép ảnh đêm 63 tỉnh của một tháng thành một ảnh toàn quốc.

Ảnh VIIRS tải theo tỉnh theo tháng; bản đồ của app đọc một ảnh cho mỗi mốc thời gian.
Phần dễ sai nhất: mỗi file tỉnh phủ hình chữ nhật bao quanh tỉnh, phần ngoài ranh giới là
-9999. Ghép sai thì vùng -9999 của tỉnh này đè lên dữ liệu thật của tỉnh bên cạnh.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine

from backend.data import build_monthly_cogs as ghep_thang

RES = 0.02
NODATA = -9999.0


def anh_tinh(path, chi_so, nam, thang, gia_tri):
    """Một 'tỉnh' hình vuông nằm giữa hộp bao; phần còn lại là nodata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cao, rong = 60, 70
    data = np.full((cao, rong), NODATA, dtype='float32')
    data[10:50, 10:55] = gia_tri
    with rasterio.open(path, 'w', driver='GTiff', height=cao, width=rong, count=1,
                       dtype='float32', crs='EPSG:4326', nodata=NODATA,
                       transform=Affine(RES, 0, 103.0 + chi_so * 1.0, 0, -RES, 22.0)) as ds:
        ds.write(data, 1)


class FindMonthlyTest(unittest.TestCase):

    def _dung(self, directory, thu_muc, so_tinh=4):
        goc = Path(directory) / 'VN_NTL_Panel_2004_2025' / thu_muc
        for i in range(so_tinh):
            ten = f'{i + 1:02}_tinh{i}'
            for nam, thang in ((2016, 7), (2016, 8), (2017, 1)):
                hau_to = '_filtered' if 'intermediate' in thu_muc else '_province_v1_abc'
                anh_tinh(goc / ten / f'{ten}_VIIRS_{nam}-{thang:02}{hau_to}.tif',
                         i, nam, thang, 5.0 + i + thang)
        return goc

    def test_months_are_grouped_across_provinces(self):
        with tempfile.TemporaryDirectory() as directory:
            self._dung(directory, 'data_intermediate/VIIRS_MONTHLY')
            theo_ky, nhan, _ = ghep_thang.tim_anh_thang(directory)
            self.assertEqual(sorted(theo_ky), [(2016, 7), (2016, 8), (2017, 1)])
            self.assertEqual(len(theo_ky[(2016, 7)]), 4)
            self.assertIn('lọc nhiễu', nhan)

    def test_filtered_images_win_over_raw_ones(self):
        """Ảnh trên bản đồ phải khớp với chính con số trong bảng chỉ số."""
        with tempfile.TemporaryDirectory() as directory:
            self._dung(directory, 'raw_data/NTL/VIIRS')
            _, nhan, thu_muc = ghep_thang.tim_anh_thang(directory)
            self.assertIn('THÔ', nhan)
            self._dung(directory, 'data_intermediate/VIIRS_MONTHLY')
            _, nhan, thu_muc = ghep_thang.tim_anh_thang(directory)
            self.assertIn('lọc nhiễu', nhan)
            self.assertIn('data_intermediate', str(thu_muc))

    def test_a_month_with_no_images_is_simply_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            self._dung(directory, 'data_intermediate/VIIRS_MONTHLY')
            theo_ky, _, _ = ghep_thang.tim_anh_thang(directory)
            self.assertNotIn((2016, 9), theo_ky)


class MergeTest(unittest.TestCase):

    def test_nodata_of_one_province_never_covers_its_neighbour(self):
        with tempfile.TemporaryDirectory() as directory:
            goc = Path(directory)
            manh = []
            for i in range(4):
                p = goc / f't{i}.tif'
                anh_tinh(p, i, 2016, 7, 10.0 + i)
                manh.append(p)
            target = goc / 'ghep.tif'
            ghep_thang.ghep(manh, target)
            with rasterio.open(target) as ds:
                data = ds.read(1)
                self.assertEqual(ds.nodata, NODATA)
                self.assertEqual(ds.count, 1)
                self.assertTrue(ds.overviews(1))
            hop_le = data[data != NODATA]
            # Mỗi tỉnh đóng góp đúng 40x45 pixel, không bị tỉnh bên cạnh xoá.
            self.assertEqual(hop_le.size, 4 * 40 * 45)
            self.assertEqual(sorted(set(np.round(hop_le, 1).tolist())),
                             [10.0, 11.0, 12.0, 13.0])

    def test_the_mosaic_spans_every_province(self):
        with tempfile.TemporaryDirectory() as directory:
            goc = Path(directory)
            manh = []
            for i in range(4):
                p = goc / f't{i}.tif'
                anh_tinh(p, i, 2016, 7, 1.0)
                manh.append(p)
            target = goc / 'ghep.tif'
            ghep_thang.ghep(manh, target)
            with rasterio.open(target) as ds:
                west, south, east, north = ds.bounds
            self.assertAlmostEqual(west, 103.0, places=4)
            self.assertAlmostEqual(east, 103.0 + 3 * 1.0 + 70 * RES, places=4)


class CatalogueTest(unittest.TestCase):

    def test_annual_and_monthly_live_side_by_side(self):
        """Khoá chính là (kind, year, month): ảnh năm 2016 và ảnh 07/2016 không đè nhau."""
        from backend.data.build_cogs import record
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'x.db'
            record(db, 'cog_image',
                   [('NTL', 2016, '/a/nam.tif', 'VIIRS', 10, 102.0, 8.5, 110.0, 23.5)])
            record(db, 'cog_image',
                   [('NTL', 2016, 7, '/a/thang.tif', 'VIIRS', 10, 102.0, 8.5, 110.0, 23.5)],
                   theo_thang=True)
            with sqlite3.connect(db) as connection:
                hang = connection.execute(
                    'SELECT month,path FROM cog_image WHERE year=2016 ORDER BY month').fetchall()
            self.assertEqual(hang, [(0, '/a/nam.tif'), (7, '/a/thang.tif')])

    def test_the_store_separates_the_two_time_steps(self):
        import os
        from backend.data.build_cogs import record
        from backend.api import store
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'x.db'
            record(db, 'cog_image',
                   [('NTL', 2016, '/a/nam.tif', 'VIIRS', 10, 102.0, 8.5, 110.0, 23.5)])
            record(db, 'cog_image',
                   [('NTL', 2016, m, f'/a/{m}.tif', 'VIIRS', 10, 102.0, 8.5, 110.0, 23.5)
                    for m in (7, 8)], theo_thang=True)
            os.environ['VNGIS_DB'] = str(db)
            self.addCleanup(os.environ.pop, 'VNGIS_DB', None)
            self.assertEqual(len(store.cog_years('NTL', 'nam')), 1)
            self.assertEqual(len(store.cog_years('NTL', 'thang')), 2)
            self.assertEqual(store.cac_buoc_thoi_gian('NTL'), {'nam': 1, 'thang': 2})
            self.assertEqual(store.cog_path('NTL', 2016), '/a/nam.tif')
            self.assertEqual(store.cog_path('NTL', 2016, 7), '/a/7.tif')


if __name__ == '__main__':
    unittest.main()
