"""Laptop stages (raw -> intermediate -> processed), table merge and the E layout migration."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from task_pipeline import derive
from task_pipeline.migrate import migrate

P=dict(number=1,ma_tinh='01',ten_tinh='Hà Nội',slug='ha_noi')
T=Affine(.01,0,105,0,-.01,21.04)


def tif(path,data,dtype,names=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with rasterio.open(path,'w',driver='GTiff',width=data.shape[2],height=data.shape[1],count=data.shape[0],
                       dtype=dtype,crs='EPSG:4326',transform=T,nodata=-9999) as ds:
        ds.write(data.astype(dtype))
        for i,n in enumerate(names or [],1):ds.set_band_description(i,n)
    return path


def day_month(root,month,value,year=2024):
    data=np.full((6,4,4),value,dtype='int16');data[:,0,0]=-9999
    return tif(Path(root)/f'raw/{year}-{month:02}.tif',data,'int16',derive.DAY_BANDS)


class DayTests(unittest.TestCase):
    def test_dry_season_median_with_observation_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw={('LANDSAT',f'2014-{m:02}'):day_month(tmp,m,m*100,2014) for m in range(1,13)}
            [out]=derive.day_annual(raw,P,tmp)
            self.assertIn('annual_composite/LANDSAT/01_ha_noi',out.as_posix())
            with rasterio.open(out) as ds:
                self.assertEqual(ds.read(1)[1,1],350)           # median of months 1,2,3,4,11,12
                self.assertEqual(ds.read(7)[1,1],6);self.assertEqual(ds.read(1)[0,0],-9999)
                self.assertEqual(ds.tags()['SEASON_RULE'],'DRY_SEASON');self.assertEqual(ds.compression.name.upper(),'ZSTD')
                self.assertEqual(ds.scales[0],1e-4);self.assertEqual(ds.dataset_mask()[0,0],0)
            mtime=out.stat().st_mtime_ns
            derive.day_annual(raw,P,tmp);self.assertEqual(out.stat().st_mtime_ns,mtime)   # unchanged inputs

    def test_fallback_to_all_months_and_regional_seasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            [out]=derive.day_annual({('SENTINEL2','2020-06'):day_month(tmp,6,600,2020)},P,tmp)
            with rasterio.open(out) as ds:
                self.assertEqual(ds.read(1)[1,1],600);self.assertEqual(ds.tags()['SEASON_RULE'],'ALL_MONTHS_FALLBACK')
        self.assertEqual(derive.dry_season('48'),[1,2,3,4,5,6,7,8]);self.assertEqual(derive.dry_season('79'),[1,2,3,4,12])
        self.assertEqual(derive.dry_season('79',{'79':[2,3]}),[2,3])

    def test_monthly_spectral_statistics(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=np.stack([np.full((4,4),v,dtype='int16') for v in (1000,2000,3000,5000,2500,1500)])
            path=tif(Path(tmp)/'m.tif',data,'int16')
            row=derive.day_stats(path)
        self.assertAlmostEqual(row['RED_mean'],.3);self.assertAlmostEqual(row['NDVI_mean'],.25)
        self.assertEqual(row['NDVI_std'],0);self.assertEqual(row['valid_pixels'],16)
        status={('SENTINEL2','2016-01'):'DONE_LOCAL',('SENTINEL2','2016-02'):'MISSING_SOURCE'}
        with tempfile.TemporaryDirectory() as tmp:
            cache=derive.Cache(Path(tmp)/'c.json')
            rows=derive.day_rows(P,status,{('SENTINEL2','2016-01'):tif(Path(tmp)/'m.tif',data,'int16')},100,cache)
        self.assertEqual([r['status'] for r in rows],['OK_TOA','MISSING_SOURCE'])
        self.assertEqual(rows[0]['month'],1);self.assertEqual(rows[0]['source'],'Sentinel-2')


class NightTests(unittest.TestCase):
    def test_filter_spike_negative_and_coverage_then_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw={}
            for m in range(1,13):
                rad=np.full((1,3,3),2.0);cov=np.full((1,3,3),5.0)
                if m==7:rad[:]=50.0
                if m==3:rad[:]=-1.0
                if m==5:cov[:]=0
                raw[('VIIRS_MONTHLY',f'2014-{m:02}')]=tif(Path(tmp)/f'v{m}.tif',np.concatenate([rad,cov]),'float64',['avg_rad','cf_cvg'])
            raw[('DMSP','2013')]=tif(Path(tmp)/'d.tif',np.full((1,3,3),10.0),'float64',['stable_lights'])
            filtered=derive.viirs_filtered(raw,P,tmp)
            with rasterio.open(filtered['2014-07']) as ds:self.assertEqual(ds.read(1)[0,0],2.0)
            with rasterio.open(filtered['2014-03']) as ds:self.assertEqual(ds.read(1)[0,0],0.0)
            with rasterio.open(filtered['2014-05']) as ds:self.assertEqual(ds.read(1)[0,0],-9999)
            annual=derive.viirs_annual(raw,filtered,P,tmp)
            with rasterio.open(annual['2014']) as ds:
                self.assertEqual(ds.read(1)[0,0],2.0);self.assertEqual(ds.tags()['SOURCE'],'MEDIAN_OF_FILTERED_VIIRS_MONTHS')
            dmsp=derive.dmsp_annual(raw,P,tmp)
            cache=derive.Cache(Path(tmp)/'c.json')
            monthly=derive.ntl_monthly_rows(P,filtered,10.0,cache)
            self.assertEqual(monthly[0]['sol'],18.0);self.assertEqual(monthly[0]['sol_density'],1.8)
            rows,_=derive.ntl_annual_rows(P,dmsp,annual,10.0,cache)
            by={r['year']:r for r in rows}
            self.assertEqual(by[2013]['source'],'DMSP');self.assertEqual(by[2014]['sol'],18.0)
            self.assertIsNone(by[2014]['sol_change_pct']);self.assertEqual(by[2014]['note'],'DOI_NGUON_ANH_CHUA_HIEU_CHINH')
            self.assertEqual(by[2014]['calibration'],'PENDING')
            # Mỗi nguồn một ngưỡng riêng: VIIRS theo bức xạ, DMSP theo DN.
            self.assertEqual(by[2014]['lit_threshold'],derive.LIT_THRESHOLD['VIIRS'])
            self.assertEqual(by[2013]['lit_threshold'],derive.LIT_THRESHOLD['DMSP'])
            self.assertIsNotNone(by[2014]['lit_pixels'])
            self.assertIsNotNone(by[2013]['lit_pixels'])
            # Thống kê phân tán phải có ở cả hai nguồn.
            for year in (2013,2014):
                for field in ('rad_mean','rad_std','rad_min','rad_max','rad_cv','valid_pixels'):
                    self.assertIsNotNone(by[year][field],f'{field} thiếu ở {year}')


class MergeTests(unittest.TestCase):
    def test_parts_from_two_branches_merge_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            derive.write_part(root/'_control/001_011','ntl_annual',[dict(province_code='01',province_name='Hà Nội',year=2014,source='VIIRS',sol=1.0)])
            derive.write_part(root/'_control/054_063','ntl_annual',[dict(province_code='84',province_name='Trà Vinh',year=2014,source='VIIRS',sol=2.0)])
            written=derive.merge(root)
            frame=pd.read_csv(root/'VN_NTL_Panel_2004_2025/data_processed/ntl_annual.csv',dtype={'province_code':str})
            self.assertEqual(list(frame['province_code']),['01','84'])
            self.assertTrue((root/'VN_NTL_Panel_2004_2025/data_processed/ntl_annual.dta').exists())
            self.assertIn('.xlsx',{p.suffix for p in written})
            derive.write_docs(root)
            self.assertTrue((root/'VN_LandCover_Panel_2004_2025/README.md').exists())
            self.assertTrue((root/'VN_NTL_Panel_2004_2025/metadata/codebook.csv').exists())


class MigrationTests(unittest.TestCase):
    def test_moves_into_shared_layout_keeps_legacy_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'Task123_branches/001_011'
            night='VN_NTL_Panel_2004_2025/raw_data/NTL/VIIRS/01_ha_noi/a.tif'
            day_old='VN_LandCover_Panel_2004_2025/raw_data/DAY/SENTINEL2/01_ha_noi/x_province_v004tasks_1234abcd.tif'
            day_new='VN_LandCover_Panel_2004_2025/raw_data/DAY/SENTINEL2/01_ha_noi/y_sr6.tif'
            table='VN_LandCover_Panel_2004_2025/data_processed/day_indices.csv'
            for rel,content in ((night,b'n'),(day_old,b'o'),(day_new,b'd'),(table,b't'),('.local_state/receipts/j.json',b'{}'),('.work/tmp',b'w')):
                (old/rel).parent.mkdir(parents=True,exist_ok=True);(old/rel).write_bytes(content)
            (root/'VN_NTL_Panel_2004_2025/raw_data/NTL/VIIRS/01_ha_noi').mkdir(parents=True)
            conflict=old.parent/'012_022'/night;conflict.parent.mkdir(parents=True);conflict.write_bytes(b'different')
            report=migrate(root)
            self.assertEqual((root/night).read_bytes(),b'n');self.assertEqual((root/day_new).read_bytes(),b'd')
            self.assertEqual((root/'_legacy/001_011'/day_old).read_bytes(),b'o')
            self.assertEqual((root/'_legacy/001_011'/table).read_bytes(),b't')
            self.assertTrue((root/'_control/001_011/.local_state/receipts/j.json').exists())
            self.assertEqual(conflict.read_bytes(),b'different');self.assertEqual(len(report['conflicts']),1)
            self.assertTrue((old/'.work/tmp').exists())
            self.assertIn('Chuyển cấu trúc',(root/'VN_NTL_Panel_2004_2025/logs/nhat_ky_cap_nhat.txt').read_text(encoding='utf-8'))
            again=migrate(root);self.assertEqual(again['moved'],0)


if __name__=='__main__':
    unittest.main()


class NtlFieldCoverageTest(unittest.TestCase):
    """Bảng chỉ số đêm phải đủ các biến kế hoạch quản lý dữ liệu yêu cầu.

    Kế hoạch (metadata/codebook_ntl.md) bắt buộc: province_code, province_name, year, source,
    sol (quy mô), sol_density (mật độ), sol_change_pct (mức độ thay đổi).
    Luồng chạy cũ (Task3 notebook, cấp huyện theo tháng) còn có thêm các chỉ số phân tán
    và vùng sáng; phần này giữ chúng ở cấp tỉnh theo năm.
    """

    BAT_BUOC = ('province_code','province_name','year','source','sol','sol_density','sol_change_pct')
    BO_SUNG = ('rad_mean','rad_std','rad_min','rad_max','rad_cv','valid_pixels',
               'lit_pixels','lit_area_km2','lit_area_pct','lit_sol','lit_threshold')

    def _rows(self):
        import numpy as np, rasterio
        from affine import Affine
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def anh(path, value):
                path.parent.mkdir(parents=True, exist_ok=True)
                data = np.full((4, 4), value, dtype='float32')
                data[0, 0] = 9.0                       # một điểm sáng vượt ngưỡng
                with rasterio.open(path, 'w', driver='GTiff', height=4, width=4, count=1,
                                   dtype='float32', crs='EPSG:4326', nodata=derive.NODATA,
                                   transform=Affine(0.01, 0, 105.0, 0, -0.01, 21.0)) as ds:
                    ds.write(data, 1)
                return path
            # Nền 0,5 nằm dưới ngưỡng 1,5 nên chỉ điểm 9,0 được tính là sáng;
            # diện tích tỉnh 20 km² lớn hơn tổng 16 điểm ảnh (~18,5 km²) của ảnh giả.
            dmsp = {str(y): anh(root / f'd{y}.tif', 1.0) for y in range(2004, 2014)}
            viirs = {str(y): anh(root / f'v{y}.tif', 0.5) for y in range(2014, 2026)}
            cache = derive.Cache(root / 'c.json')
            rows, _ = derive.ntl_annual_rows(
                dict(ma_tinh='01', ten_tinh='Hà Nội'), dmsp, viirs, 20.0, cache)
            return {r['year']: r for r in rows}

    def test_the_plan_mandated_variables_are_all_present(self):
        row = self._rows()[2020]
        for field in self.BAT_BUOC:
            with self.subTest(bien=field):
                self.assertIn(field, row)
                self.assertIsNotNone(row[field], f'{field} rỗng')

    def test_the_extra_indicators_from_the_old_pipeline_are_present_for_viirs(self):
        row = self._rows()[2020]
        for field in self.BO_SUNG:
            with self.subTest(bien=field):
                self.assertIsNotNone(row.get(field), f'{field} rỗng ở năm VIIRS')

    def test_each_source_uses_its_own_lit_threshold(self):
        """DMSP là DN 0-63, VIIRS là bức xạ: hai thang đo, hai ngưỡng, không dùng chung."""
        rows = self._rows()
        self.assertEqual(rows[2010]['source'], 'DMSP')
        self.assertEqual(rows[2010]['lit_threshold'], 5)
        self.assertEqual(rows[2020]['source'], 'VIIRS')
        self.assertEqual(rows[2020]['lit_threshold'], 1.5)
        # Nền DMSP là 1.0 (< 5) và nền VIIRS 0.5 (< 1,5): chỉ điểm 9,0 vượt ngưỡng ở cả hai.
        self.assertEqual(rows[2010]['lit_pixels'], 1)
        self.assertEqual(rows[2020]['lit_pixels'], 1)

    def test_the_thresholds_match_the_project_configuration(self):
        """Ngưỡng phải lấy đúng giá trị dự án đã chốt, không tự đặt lại trong derive."""
        import json
        from pathlib import Path as _P
        goc = _P(__file__).resolve().parent.parent
        cau_hinh = json.loads((goc / 'province_pipeline' / 'config'
                               / 'full_2004_2025.json').read_text(encoding='utf-8'))
        self.assertEqual(derive.LIT_THRESHOLD['DMSP'],
                         cau_hinh['quality']['lit_threshold_dmsp'])
        # VIIRS được task_pipeline/scope.py ghi đè lên 1,5.
        scope = (goc / 'task_pipeline' / 'scope.py').read_text(encoding='utf-8')
        self.assertIn("lit_threshold_viirs']=1.5", scope.replace(' ', ''))
        self.assertEqual(derive.LIT_THRESHOLD['VIIRS'], 1.5)

    def test_the_coefficient_of_variation_is_std_over_mean(self):
        row = self._rows()[2020]
        self.assertAlmostEqual(row['rad_cv'], row['rad_std'] / row['rad_mean'], places=3)

    def test_only_pixels_above_the_threshold_count_as_lit(self):
        row = self._rows()[2020]
        self.assertEqual(row['lit_pixels'], 1)       # chỉ điểm 9,0; nền 0,5 bị loại
        self.assertEqual(row['lit_sol'], 9.0)
        self.assertGreater(row['lit_area_pct'], 0)
        self.assertLessEqual(row['lit_area_km2'], row['area_km2'] + 1e-6)

    def test_changing_the_formula_invalidates_the_cache(self):
        """Cache khoá theo size+mtime+STATS_VERSION: đổi công thức là mục cũ hết hiệu lực."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'x.bin'
            path.write_bytes(b'x')
            cache = derive.Cache(Path(tmp) / 'c.json')
            self.assertEqual(cache.get(path, lambda p: {'v': 1}), {'v': 1})
            self.assertEqual(cache.get(path, lambda p: {'v': 2}), {'v': 1})   # còn hiệu lực
            goc = derive.STATS_VERSION
            try:
                derive.STATS_VERSION = goc + 1
                self.assertEqual(cache.get(path, lambda p: {'v': 2}), {'v': 2})
            finally:
                derive.STATS_VERSION = goc


class OverlapTableMatchesTheColumnTheModelIsAppliedTo(unittest.TestCase):
    """Bảng chồng lấn 2013 phải đo cùng một đại lượng với cột sol.

    Lỗi đã xảy ra: bảng chồng lấn gọi ntl_stats trần (background=0) nên sol_viirs gồm cả
    nhiễu nền dưới 0,5 — một lượng tỷ lệ với diện tích tỉnh. Mô hình hiệu chỉnh khớp trên
    đại lượng đó rồi được áp cho sol đã trừ nền: R² 0,57 và b < 1 (sai chiều vật lý,
    DMSP bão hòa thì b phải > 1).
    """

    def _overlap(self, gia_tri_nen):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def anh(path, nen):
                # 15 điểm ảnh ở mức nền + 1 điểm đô thị thật.
                data = np.full((1, 4, 4), nen, dtype='float32')
                data[0, 0, 0] = 40.0
                return tif(path, data, 'float32')

            dmsp = {'2013': anh(root / 'd2013.tif', 1.0)}
            viirs = {'2013': anh(root / 'v2013.tif', gia_tri_nen)}
            cache = derive.Cache(root / 'c.json')
            rows, overlap = derive.ntl_annual_rows(P, dmsp, viirs, 20.0, cache)
            return overlap, {r['year']: r for r in rows}

    def test_viirs_background_is_subtracted_in_the_overlap_pair(self):
        """15 điểm ở 0,2 nW nằm dưới ngưỡng nền 0,5: chúng không được vào sol_viirs."""
        overlap, _ = self._overlap(0.2)
        self.assertEqual(overlap['sol_viirs'], 40.0,
                         'sol_viirs còn cộng cả nhiễu nền -> mô hình khớp sai đại lượng')

    def test_the_dmsp_side_matches_the_annual_column_exactly(self):
        overlap, rows = self._overlap(0.2)
        self.assertEqual(overlap['sol_dmsp'], rows[2013]['sol'])

    def test_the_cache_does_not_mix_two_threshold_sets_for_one_file(self):
        """Cùng một file gọi với hai bộ ngưỡng phải là hai mục cache riêng."""
        with tempfile.TemporaryDirectory() as tmp:
            path = tif(Path(tmp) / 'a.tif',
                       np.full((1, 4, 4), 0.2, dtype='float32'), 'float32')
            cache = derive.Cache(Path(tmp) / 'c.json')
            co_nen = cache.get(path, lambda x: derive.ntl_stats(x, 1.5, 0.5), nhan=('VIIRS',))
            khong = cache.get(path, lambda x: derive.ntl_stats(x, None, 0.0), nhan=('tho',))
            self.assertEqual(co_nen['sol'], 0.0)
            self.assertAlmostEqual(khong['sol'], 0.2 * 16, places=4)


class TheCombinedPanelIsOneDatasetWithTwoFrequencies(unittest.TestCase):
    """ntl_panel: DMSP theo NĂM đến 2013, VIIRS theo THÁNG từ 2014, trong cùng một bảng."""

    def _bo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def anh(path, value, cf=None):
                data = np.full((1, 4, 4), value, dtype='float32')
                data[0, 0, 0] = 40.0
                path = tif(path, data, 'float32')
                if cf is not None:
                    with rasterio.open(path, 'r+') as ds:
                        ds.update_tags(CF_CVG_MEAN=str(cf))
                return path

            dmsp = {str(y): anh(root / f'd{y}.tif', 1.0) for y in range(2004, 2014)}
            viirs = {str(y): anh(root / f'v{y}.tif', 0.2) for y in range(2014, 2026)}
            filtered = {f'{y}-{m:02}': anh(root / f'f{y}{m:02}.tif', 0.2, cf=12.5)
                        for y in (2014, 2015) for m in range(1, 13)}
            cache = derive.Cache(root / 'c.json')
            annual, _ = derive.ntl_annual_rows(P, dmsp, viirs, 20.0, cache)
            monthly = derive.ntl_monthly_rows(P, filtered, 20.0, cache)
            return derive.ntl_panel_rows(annual, monthly), annual, monthly

    def test_the_dmsp_half_is_annual_and_the_viirs_half_is_monthly(self):
        panel, _, _ = self._bo()
        dmsp = [r for r in panel if r['source'] == 'DMSP']
        viirs = [r for r in panel if r['source'] == 'VIIRS']
        self.assertTrue(all(r['frequency'] == 'annual' and r['month'] == 0 for r in dmsp))
        self.assertTrue(all(r['frequency'] == 'monthly' and 1 <= r['month'] <= 12
                            for r in viirs))
        self.assertEqual({r['year'] for r in dmsp}, set(range(2004, 2014)))
        self.assertEqual(len(viirs), 24)

    def test_no_year_is_covered_by_both_halves(self):
        """Trùng năm ở hai nửa là đếm hai lần cùng một hoạt động kinh tế."""
        panel, _, _ = self._bo()
        nam_dmsp = {r['year'] for r in panel if r['source'] == 'DMSP'}
        nam_viirs = {r['year'] for r in panel if r['source'] == 'VIIRS'}
        self.assertEqual(nam_dmsp & nam_viirs, set())

    def test_the_period_column_reads_the_same_way_in_both_halves(self):
        panel, _, _ = self._bo()
        theo = {r['period'] for r in panel}
        self.assertIn('2010', theo)
        self.assertIn('2014-01', theo)

    def test_editing_the_panel_never_touches_the_other_two_tables(self):
        panel, annual, monthly = self._bo()
        panel[0]['sol'] = -1
        self.assertNotEqual(annual[0]['sol'], -1)
        self.assertNotEqual(monthly[0]['sol'], -1)


class TheFieldsTheOriginalNotebookHadAreAllPresent(unittest.TestCase):
    """Notebook Task3 cũ có bốn trường mà bảng này từng thiếu."""

    def _thang(self, so_thang=24, cf=12.5):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            filtered = {}
            for i in range(so_thang):
                y, m = 2014 + i // 12, i % 12 + 1
                data = np.full((1, 4, 4), 0.2, dtype='float32')
                data[0, 0, 0] = 10.0 + i          # tăng dần để biến động khác 0
                path = tif(root / f'f{y}{m:02}.tif', data, 'float32')
                if cf is not None:
                    with rasterio.open(path, 'r+') as ds:
                        ds.update_tags(CF_CVG_MEAN=str(cf))
                filtered[f'{y}-{m:02}'] = path
            cache = derive.Cache(root / 'c.json')
            rows = derive.ntl_monthly_rows(P, filtered, 20.0, cache)
            return {r['period']: r for r in rows}

    def test_cloud_free_obs_comes_through_from_the_filter_step(self):
        """cf_cvg chỉ có ở ảnh thô và bị bỏ khi ghi ảnh đã lọc; phải được giữ lại."""
        rows = self._thang()
        self.assertEqual(rows['2014-05']['cloud_free_obs'], 12.5)

    def test_a_missing_cf_cvg_tag_is_empty_not_zero(self):
        """Không có thẻ nghĩa là KHÔNG BIẾT. Ghi 0 là nói sai: 0 lượt sạch mây."""
        rows = self._thang(so_thang=12, cf=None)
        self.assertIsNone(rows['2014-05']['cloud_free_obs'])

    def test_month_over_month_and_year_over_year_are_both_there(self):
        rows = self._thang()
        self.assertIsNotNone(rows['2015-06']['sol_change_mom_pct'])
        self.assertIsNotNone(rows['2015-06']['sol_change_yoy_pct'])
        self.assertIsNone(rows['2014-01']['sol_change_mom_pct'],
                          'tháng đầu chuỗi không có tháng trước để so')
        self.assertIsNone(rows['2014-06']['sol_change_yoy_pct'],
                          'năm đầu chuỗi không có cùng kỳ năm trước')

    def test_a_gap_in_the_series_is_not_compared_across(self):
        """Thiếu tháng 3 thì tháng 4 không được so với tháng 2 như thể liền nhau."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            filtered = {}
            for m in (1, 2, 4):
                data = np.full((1, 4, 4), 0.2, dtype='float32');data[0, 0, 0] = 10.0 * m
                filtered[f'2014-{m:02}'] = tif(root / f'f{m}.tif', data, 'float32')
            rows = {r['period']: r for r in derive.ntl_monthly_rows(
                P, filtered, 20.0, derive.Cache(root / 'c.json'))}
        self.assertIsNotNone(rows['2014-02']['sol_change_mom_pct'])
        self.assertIsNone(rows['2014-04']['sol_change_mom_pct'])

    def test_the_three_month_average_smooths_the_series(self):
        rows = self._thang()
        ba = [rows[f'2014-{m:02}']['sol'] for m in (1, 2, 3)]
        self.assertAlmostEqual(rows['2014-03']['sol_ma3'], round(sum(ba) / 3, 4), places=3)

    def test_the_lit_pixel_ratio_is_over_valid_pixels_not_province_area(self):
        """Notebook gọi là electrification ratio: số pixel sáng / số pixel CÓ DỮ LIỆU."""
        rows = self._thang()
        row = rows['2014-05']
        self.assertAlmostEqual(row['lit_pixel_pct'],
                               100 * row['lit_pixels'] / row['valid_pixels'], places=4)
        self.assertNotEqual(row['lit_pixel_pct'], row['lit_area_pct'])


class OldIntermediatesAreRebuiltWhenANewTagIsNeeded(unittest.TestCase):
    """Ảnh trung gian cũ thiếu thẻ mới thì phải dựng lại, không được coi là còn mới.

    Nếu không, thẻ không bao giờ được ghi và cột đọc từ thẻ đó rỗng vĩnh viễn mà
    không có gì báo lỗi — đúng kiểu hỏng âm thầm mà STATS_VERSION sinh ra để tránh.
    """

    def test_a_file_without_the_required_tag_counts_as_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nguon = tif(root / 'in.tif', np.ones((1, 4, 4), dtype='float32'), 'float32')
            dich = root / 'out.tif'
            derive.write(dich, dict(driver='GTiff', width=4, height=4, count=1,
                                    dtype='float32', crs='EPSG:4326', transform=T,
                                    nodata=-9999),
                         ['x'], [((slice(0, 4), slice(0, 4)),
                                  np.ones((1, 4, 4), dtype='float32'),
                                  np.ones((4, 4), dtype=bool))],
                         dict(SOURCE='TEST'), [nguon])
            self.assertTrue(derive.up_to_date(dich, [nguon]))
            self.assertFalse(derive.up_to_date(dich, [nguon], can_co=('CF_CVG_MEAN',)),
                             'thiếu thẻ mà vẫn báo còn mới')

    def test_a_file_with_the_tag_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nguon = tif(root / 'in.tif', np.ones((1, 4, 4), dtype='float32'), 'float32')
            dich = root / 'out.tif'
            derive.write(dich, dict(driver='GTiff', width=4, height=4, count=1,
                                    dtype='float32', crs='EPSG:4326', transform=T,
                                    nodata=-9999),
                         ['x'], [((slice(0, 4), slice(0, 4)),
                                  np.ones((1, 4, 4), dtype='float32'),
                                  np.ones((4, 4), dtype=bool))],
                         dict(CF_CVG_MEAN='12.5'), [nguon])
            self.assertTrue(derive.up_to_date(dich, [nguon], can_co=('CF_CVG_MEAN',)))


class StalePartsFromAnOlderSchemaNeverCollapseTheTable(unittest.TestCase):
    """Phần bảng của phiên bản cũ thiếu cột khoá hiện tại.

    Gộp thẳng vào thì mọi dòng cũ mang khoá rỗng, và drop_duplicates coi các ô rỗng là
    GIỐNG NHAU nên hàng nghìn dòng co lại còn một — mất dữ liệu mà không báo gì.
    Đã xảy ra thật trên ổ E: 1144 dòng cũ còn 1.
    """

    def _gop(self, moi, cu):
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            derive.write_part(root / '_control/001_011', 'ntl_annual', moi)
            derive.write_part(root / '_control/012_022', 'ntl_annual', cu)
            derive.merge(root)
            return pd.read_csv(root / 'VN_NTL_Panel_2004_2025/data_processed/ntl_annual.csv',
                               dtype={'province_code': str})

    def test_an_old_part_is_skipped_instead_of_collapsing_the_new_rows(self):
        moi = [dict(province_code='01', province_name='Hà Nội', year=y, month=0,
                    source='VIIRS', sol=float(y)) for y in range(2014, 2026)]
        cu = [dict(ma_tinh='12', ten_tinh='Lai Châu', nam=y, nguon_anh='VIIRS',
                   sol_ntl=float(y), ghi_chu=None) for y in range(2014, 2026)]
        frame = self._gop(moi, cu)
        self.assertEqual(len(frame), len(moi),
                         'dòng mới bị dòng cũ khoá-rỗng nuốt mất')
        self.assertEqual(set(frame['province_code']), {'01'})

    def test_a_column_that_is_empty_everywhere_does_not_kill_the_stata_export(self):
        """to_stata từ chối cả bảng vì một cột chữ toàn ô trống."""
        moi = [dict(province_code='01', province_name='Hà Nội', year=y, month=0,
                    source='VIIRS', sol=float(y), note=None) for y in range(2014, 2026)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            derive.write_part(root / '_control/001_011', 'ntl_annual', moi)
            viet = derive.merge(root)
        duoi = {p.suffix for p in viet}
        self.assertIn('.dta', duoi, 'mất tệp .dta vì một cột phụ toàn ô trống')
        self.assertIn('.csv', duoi)

    def test_the_skipped_group_is_named_so_it_can_be_recomputed(self):
        import io
        import contextlib
        cu = [dict(ma_tinh='12', nam=2014, sol_ntl=1.0)]
        moi = [dict(province_code='01', year=2014, month=0, source='VIIRS', sol=1.0)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            derive.write_part(root / '_control/001_011', 'ntl_annual', moi)
            derive.write_part(root / '_control/012_022', 'ntl_annual', cu)
            loi = io.StringIO()
            with contextlib.redirect_stderr(loi):
                derive.merge(root)
        self.assertIn('012_022', loi.getvalue())
        self.assertIn('province_code', loi.getvalue())
