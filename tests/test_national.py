"""Annual national tiles: grid plan, split on heavy tiles, resume, and the VRT mosaic (no EE)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import rasterio
from affine import Affine
from task_pipeline import national

RES=national.PRODUCTS['LANDSAT']['scale']/national.DEG


def province(x0,y0,x1,y1):
    return dict(geometry=dict(type='Polygon',coordinates=[[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]]))


def fake_fetch(origin,calls,heavy_above=None):
    """Writes value = 1000*row + col (global pixel indices) like Earth Engine would, per window."""
    def fetch(image,job,path):
        t=job['tile'];a=Affine(*t['transform']);w,h=t['width'],t['height']
        if heavy_above and w*h>heavy_above:
            calls.append(('heavy',w,h));raise RuntimeError('Earth Engine HTTP 400: User memory limit exceeded.')
        col=round((a.c-origin[0])/RES);row=round((origin[1]-a.f)/RES)
        values=(1000*np.arange(row,row+h)[:,None]+np.arange(col,col+w)[None,:]).astype('int16')
        calls.append(('ok',w,h))
        with rasterio.open(path,'w',driver='GTiff',width=w,height=h,count=len(job['bands']),dtype='int16',
                           crs='EPSG:4326',transform=a,nodata=-9999) as ds:
            for b in range(len(job['bands'])):ds.write(values+b,b+1)
    return fetch


class NationalTests(unittest.TestCase):
    def test_project_rule_years(self):
        self.assertEqual(list(national.PRODUCTS['LANDSAT']['years']),list(range(2004,2015)))
        self.assertEqual(list(national.PRODUCTS['SENTINEL2']['years']),list(range(2015,2026)))
        self.assertEqual(list(national.PRODUCTS['VIIRS']['years'])[0],2014)
        self.assertEqual(list(national.PRODUCTS['DMSP']['years']),list(range(2004,2014)))
        with self.assertRaises(SystemExit):national.run_year('LANDSAT',2015,'.',{},1,image=object())
        with self.assertRaises(SystemExit):national.run_year('SENTINEL2',2014,'.',{},1,image=object())

    def test_tiles_stay_under_the_download_limit(self):
        for product,p in national.PRODUCTS.items():
            n=national.tile_pixels(product);per=len(p['bands'])*(2 if p['dtype']=='int16' else 4)
            self.assertLess(n*n*per,32_000_000,product);self.assertGreaterEqual(n,512,product)

    def _run(self,tmp,boundaries,fetch,tile=4):
        with patch.object(national,'tile_pixels',lambda product:tile),\
             patch.object(national,'compress',lambda path,dtype:None):
            return national.run_year('LANDSAT',2010,tmp,boundaries,1,fetch=fetch,image=object(),
                                     pause_seconds=0,max_idle_rounds=2)

    def test_mosaic_vrt_matches_global_pixels_skips_empty_tiles_and_resumes(self):
        # Two "provinces" with a gap: tiles fully in the gap are skipped.
        b={'01':province(105,20,105+10*RES,20+7*RES),'02':province(105+22*RES,20,105+30*RES,20+7*RES)}
        with tempfile.TemporaryDirectory() as tmp:
            calls=[];exact,_=national.national_geometry(b)
            g,_,_=national.plan('LANDSAT',exact.bounds);origin=(g['transform'][2],g['transform'][5])
            self.assertTrue(self._run(tmp,b,fake_fetch(origin,calls)))
            folder=Path(tmp)/'VN_LandCover_Panel_2004_2025'/'raw_data'/'DAY'/'LANDSAT'/'VN_LANDSAT_2010'
            vrt=folder/'VN_LANDSAT_2010.vrt'
            with rasterio.open(vrt) as ds:
                self.assertEqual((ds.width,ds.height,ds.count),(g['width'],g['height'],6))
                self.assertEqual(ds.descriptions[0],'BLUE');self.assertEqual(ds.crs.to_epsg(),4326)
                data=ds.read(1);bands=ds.read()
            expected=1000*np.arange(g['height'])[:,None]+np.arange(g['width'])[None,:]
            have=data!=-9999
            np.testing.assert_array_equal(data[have],expected[have])
            np.testing.assert_array_equal(bands[3][have],expected[have]+3)
            self.assertTrue(have[:, :10].all())             # province 01 fully present
            self.assertFalse(have[:, 12:20].any())          # tiles fully in the gap were never requested
            # Resume: nothing is downloaded again.
            again=[];self.assertTrue(self._run(tmp,b,fake_fetch(origin,again)));self.assertEqual(again,[])

    def test_heavy_tile_is_split_into_identical_pixels(self):
        b={'01':province(105,20,105+9*RES,20+9*RES)}
        with tempfile.TemporaryDirectory() as tmp:
            calls=[];exact,_=national.national_geometry(b)
            g,_,_=national.plan('LANDSAT',exact.bounds);origin=(g['transform'][2],g['transform'][5])
            with patch.object(national,'MIN_TILE',1):
                self.assertTrue(self._run(tmp,b,fake_fetch(origin,calls,heavy_above=9),tile=8))
            self.assertIn(('heavy',8,8),calls)
            vrt=Path(tmp)/'VN_LandCover_Panel_2004_2025'/'raw_data'/'DAY'/'LANDSAT'/'VN_LANDSAT_2010'/'VN_LANDSAT_2010.vrt'
            with rasterio.open(vrt) as ds:data=ds.read(1)
            expected=1000*np.arange(g['height'])[:,None]+np.arange(g['width'])[None,:]
            have=data!=-9999
            self.assertTrue(have[:9,:9].all());np.testing.assert_array_equal(data[have],expected[have])

    def test_failed_tile_leaves_year_incomplete_without_vrt(self):
        b={'01':province(105,20,105+6*RES,20+6*RES)}
        def broken(image,job,path):raise RuntimeError('Earth Engine HTTP 403: Permission denied')
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(self._run(tmp,b,broken))
            self.assertFalse(list(Path(tmp).rglob('*.vrt')))

    def test_compress_keeps_pixels(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'t.tif';data=np.arange(6*40*50,dtype='int16').reshape(6,40,50)
            with rasterio.open(p,'w',driver='GTiff',width=50,height=40,count=6,dtype='int16',crs='EPSG:4326',
                               transform=Affine(RES,0,105,0,-RES,21),nodata=-9999) as ds:
                ds.write(data)
                for i,n in enumerate(national.DAY_TIFF_BANDS,1):ds.set_band_description(i,n)
            national.compress(p,'int16')
            with rasterio.open(p) as ds:
                np.testing.assert_array_equal(ds.read(),data)
                self.assertEqual(ds.compression.name.upper(),'ZSTD');self.assertEqual(ds.descriptions[5],'SWIR2')

    def test_refused_tiles_are_retried_in_later_rounds(self):
        b={'01':province(105,20,105+8*RES,20+8*RES)}
        with tempfile.TemporaryDirectory() as tmp:
            calls=[];exact,_=national.national_geometry(b)
            g,_,_=national.plan('LANDSAT',exact.bounds);origin=(g['transform'][2],g['transform'][5])
            real=fake_fetch(origin,calls);refused=[]
            def flaky(image,job,path):
                if len(refused)<3:refused.append(1);raise RuntimeError('Too many concurrent aggregations (429)')
                real(image,job,path)
            self.assertTrue(self._run(tmp,b,flaky))
            self.assertEqual(len(refused),3)
            self.assertTrue(list(Path(tmp).rglob('VN_LANDSAT_2010.vrt')))

    def test_split_tile_counts_as_done_only_when_all_parts_arrived(self):
        b={'01':province(105,20,105+8*RES,20+8*RES)}
        with tempfile.TemporaryDirectory() as tmp,patch.object(national,'MIN_TILE',1):
            calls=[];exact,_=national.national_geometry(b)
            g,_,_=national.plan('LANDSAT',exact.bounds);origin=(g['transform'][2],g['transform'][5])
            real=fake_fetch(origin,calls,heavy_above=16)
            # First run: the third sub-tile keeps failing (permission-like error) -> incomplete.
            def partial(image,job,path):
                t=job['tile']
                if t['width']*t['height']<=16 and len([c for c in calls if c[0]=='ok'])>=2:
                    raise RuntimeError('Earth Engine HTTP 403: denied')
                real(image,job,path)
            self.assertFalse(self._run(tmp,b,partial,tile=8))
            self.assertFalse(list(Path(tmp).rglob('*.vrt')))
            first={p.name:p.stat().st_mtime_ns for p in Path(tmp).rglob('tiles/*.tif')}
            self.assertEqual(len(first),2)
            # Second run: the two sub-tiles already on disk are kept, the rest is fetched.
            self.assertTrue(self._run(tmp,b,real,tile=8))
            after={p.name:p.stat().st_mtime_ns for p in Path(tmp).rglob('tiles/*.tif')}
            for name,mtime in first.items():self.assertEqual(after[name],mtime)
            self.assertGreater(len(after),len(first))
            vrt=next(Path(tmp).rglob('VN_LANDSAT_2010.vrt'))
            with rasterio.open(vrt) as ds:data=ds.read(1)
            expected=1000*np.arange(g['height'])[:,None]+np.arange(g['width'])[None,:]
            np.testing.assert_array_equal(data,expected)

    def test_shards_share_one_year_and_the_last_writes_the_vrt(self):
        """Any number of shards (6 accounts, 10 accounts...) covers every tile exactly once."""
        for count in (6,10):
            with self.subTest(shards=count):
                b={'01':province(105,20,105+20*RES,20+12*RES)}
                with tempfile.TemporaryDirectory() as tmp:
                    calls=[];exact,_=national.national_geometry(b)
                    g,_,_=national.plan('LANDSAT',exact.bounds);origin=(g['transform'][2],g['transform'][5])
                    fetch=fake_fetch(origin,calls)
                    folder=Path(tmp)/'VN_LandCover_Panel_2004_2025'/'raw_data'/'DAY'/'LANDSAT'/'VN_LANDSAT_2010'
                    with patch.object(national,'tile_pixels',lambda product:4),patch.object(national,'compress',lambda path,dtype:None):
                        for i in range(count):
                            self.assertFalse((folder/'VN_LANDSAT_2010.vrt').exists())
                            self.assertTrue(national.run_year('LANDSAT',2010,tmp,b,1,fetch=fetch,image=object(),
                                                              pause_seconds=0,max_idle_rounds=2,shard=(i,count)))
                    files=list((folder/'tiles').glob('*.tif'))
                    self.assertEqual(len(files),len(calls))          # every tile fetched exactly once
                    with rasterio.open(folder/'VN_LANDSAT_2010.vrt') as ds:data=ds.read(1)
                    expected=1000*np.arange(g['height'])[:,None]+np.arange(g['width'])[None,:]
                    np.testing.assert_array_equal(data,expected)

    def test_tile_the_disk_reports_corrupted_is_downloaded_again(self):
        b={'01':province(105,20,105+8*RES,20+8*RES)}
        with tempfile.TemporaryDirectory() as tmp:
            calls=[];exact,_=national.national_geometry(b)
            g,_,_=national.plan('LANDSAT',exact.bounds);origin=(g['transform'][2],g['transform'][5])
            fetch=fake_fetch(origin,calls)
            self.assertTrue(self._run(tmp,b,fetch))
            first=len(calls)
            broken=next(Path(tmp).rglob('tiles/r000000_c000000.tif'))
            real_stat=Path.stat
            def stat(self,*a,**k):
                if self.name==broken.name:raise OSError(1392,'The file or directory is corrupted and unreadable')
                return real_stat(self,*a,**k)
            real_unlink=Path.unlink
            def unlink(self,*a,**k):
                if self.name==broken.name:raise OSError(1392,'corrupted')
                return real_unlink(self,*a,**k)
            # Forget the year so every tile is checked again on disk.
            for state in Path(tmp).rglob('tiles*.json'):state.unlink()
            with patch.object(Path,'stat',stat),patch.object(Path,'unlink',unlink):
                self.assertTrue(self._run(tmp,b,fetch))
            self.assertEqual(len(calls),first+1)            # only the corrupted tile again
            self.assertTrue((broken.parent/'r000000_c000000b.tif').exists())
            vrt=next(Path(tmp).rglob('VN_LANDSAT_2010.vrt'))
            self.assertIn('r000000_c000000b.tif',vrt.read_text())
            self.assertNotIn('r000000_c000000.tif<',vrt.read_text())

    def test_merge_writes_one_geotiff_identical_to_the_tiles(self):
        b={'01':province(105,20,105+20*RES,20+12*RES),'02':province(105+30*RES,20,105+40*RES,20+12*RES)}
        with tempfile.TemporaryDirectory() as tmp:
            calls=[];exact,_=national.national_geometry(b)
            g,_,_=national.plan('LANDSAT',exact.bounds);origin=(g['transform'][2],g['transform'][5])
            self.assertTrue(self._run(tmp,b,fake_fetch(origin,calls)))
            self.assertTrue(national.merge_year('LANDSAT',2010,tmp,strip_rows=5,strip_cols=7))
            folder=next(Path(tmp).rglob('VN_LANDSAT_2010'))
            with rasterio.open(folder/'VN_LANDSAT_2010.tif') as out,rasterio.open(folder/'VN_LANDSAT_2010.vrt') as src:
                self.assertEqual(out.driver,'GTiff');self.assertEqual(out.compression.name.upper(),'ZSTD')
                self.assertEqual((out.count,out.nodata,out.descriptions[5]),(6,-9999,'SWIR2'))
                self.assertEqual(out.transform,src.transform)
                np.testing.assert_array_equal(out.read(),src.read())
            self.assertFalse(list(folder.glob('*.merging.tif')))
            self.assertTrue(national.merge_year('LANDSAT',2010,tmp))          # already up to date
            self.assertFalse(national.merge_year('LANDSAT',2011,tmp))         # no VRT yet

    def test_clip_writes_one_masked_geotiff_per_province(self):
        tri=dict(geometry=dict(type='Polygon',coordinates=[[[105,20],[105+20*RES,20],[105,20+12*RES],[105,20]]]))
        b={'01':tri,'02':province(105+30*RES,20,105+40*RES,20+12*RES)}
        provinces=[dict(ma_tinh='01',slug='ha_noi',ten_tinh='Hà Nội'),dict(ma_tinh='02',slug='ha_giang',ten_tinh='Hà Giang')]
        with tempfile.TemporaryDirectory() as tmp:
            calls=[];exact,_=national.national_geometry(b)
            g,_,_=national.plan('LANDSAT',exact.bounds);origin=(g['transform'][2],g['transform'][5])
            self.assertTrue(self._run(tmp,b,fake_fetch(origin,calls)))
            # Tiny blocks so each province is written in many pieces, as a big one would be.
            self.assertTrue(national.clip_year('LANDSAT',2010,tmp,b,provinces,block_rows=3,block_cols=5))
            out=Path(tmp)/'VN_LandCover_Panel_2004_2025'/'data_intermediate'/'annual_province'/'LANDSAT'
            hn=out/'01_ha_noi'/'01_ha_noi_LANDSAT_2010.tif';hg=out/'02_ha_giang'/'02_ha_giang_LANDSAT_2010.tif'
            vrt=next(Path(tmp).rglob('VN_LANDSAT_2010.vrt'))
            with rasterio.open(hn) as a,rasterio.open(vrt) as src:
                data=a.read(1);self.assertEqual(a.count,6);self.assertEqual(a.tags()['MA_TINH'],'01')
                self.assertTrue((data==-9999).any())           # triangle: corner outside masked
                self.assertTrue((data!=-9999).any())
                col=round((a.transform.c-src.transform.c)/RES);row=round((src.transform.f-a.transform.f)/RES)
                full=src.read(1)[row:row+a.height,col:col+a.width]
                np.testing.assert_array_equal(data[data!=-9999],full[data!=-9999])
            with rasterio.open(hg) as a:
                self.assertTrue((a.read(1)!=-9999).all())      # rectangle fully inside
            before=hn.stat().st_mtime_ns
            self.assertTrue(national.clip_year('LANDSAT',2010,tmp,b,provinces))
            self.assertEqual(hn.stat().st_mtime_ns,before)      # up to date: not rewritten
