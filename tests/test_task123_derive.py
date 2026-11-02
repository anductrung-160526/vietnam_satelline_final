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
        self.assertEqual(row['NDVI_std'],0);self.assertEqual(row['so_pixel_hop_le'],16)
        status={('SENTINEL2','2016-01'):'DONE_LOCAL',('SENTINEL2','2016-02'):'MISSING_SOURCE'}
        with tempfile.TemporaryDirectory() as tmp:
            cache=derive.Cache(Path(tmp)/'c.json')
            rows=derive.day_rows(P,status,{('SENTINEL2','2016-01'):tif(Path(tmp)/'m.tif',data,'int16')},100,cache)
        self.assertEqual([r['trang_thai'] for r in rows],['OK_TOA','MISSING_SOURCE'])
        self.assertEqual(rows[0]['thang'],1);self.assertEqual(rows[0]['nguon_anh'],'Sentinel-2')


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
            self.assertEqual(monthly[0]['sol_ntl'],18.0);self.assertEqual(monthly[0]['mat_do_ntl'],1.8)
            rows,_=derive.ntl_annual_rows(P,dmsp,annual,10.0,cache)
            by={r['nam']:r for r in rows}
            self.assertEqual(by[2013]['nguon_anh'],'DMSP');self.assertEqual(by[2014]['sol_ntl'],18.0)
            self.assertIsNone(by[2014]['thay_doi_ntl_pct']);self.assertEqual(by[2014]['ghi_chu'],'DOI_NGUON_ANH_CHUA_HIEU_CHINH')
            self.assertEqual(by[2014]['hieu_chinh'],'PENDING')


class MergeTests(unittest.TestCase):
    def test_parts_from_two_branches_merge_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            derive.write_part(root/'_control/001_011','ntl_annual',[dict(ma_tinh='01',ten_tinh='Hà Nội',nam=2014,nguon_anh='VIIRS',sol_ntl=1.0)])
            derive.write_part(root/'_control/054_063','ntl_annual',[dict(ma_tinh='84',ten_tinh='Trà Vinh',nam=2014,nguon_anh='VIIRS',sol_ntl=2.0)])
            written=derive.merge(root)
            frame=pd.read_csv(root/'VN_NTL_Panel_2004_2025/data_processed/ntl_annual.csv',dtype={'ma_tinh':str})
            self.assertEqual(list(frame['ma_tinh']),['01','84'])
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
