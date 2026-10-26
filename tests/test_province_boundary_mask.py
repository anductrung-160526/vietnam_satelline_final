"""Day TIFFs keep only the province shape; neighbouring land becomes NoData."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import rasterio
from affine import Affine
from task_pipeline.province_image import download,mask_outside
from province_pipeline.receiver import validate,hashes


def fixture(product='SENTINEL2',width=6,height=6):
    res=.01
    return dict(kind='image',job_id='day',product=product,period='2025-01',image_layout='province',
        scale=res*111319.49079327358,grid_resolution=res,dtype='float64',bands=['RED','NIR'],chunk_pixels=4,
        crs='EPSG:4326',quality=dict(processing_mode='notebook_tasks'),reserved_bytes=8*1024**2,
        tile=dict(width=width,height=height,bounds=[105,20,105+width*res,20+height*res],
                  transform=[res,0,105,0,-res,20+height*res]))


def triangle(job):
    # Lower-left triangle of the bounding box: the upper-right corner is another province.
    x0,y0,x1,y1=job['tile']['bounds']
    return dict(geometry=dict(type='Polygon',coordinates=[[[x0,y0],[x1,y0],[x0,y1],[x0,y0]]]))


def fetch_full(image,part,path):
    t=part['tile'];h,w=t['height'],t['width']
    with rasterio.open(path,'w',driver='GTiff',width=w,height=h,count=2,dtype='float64',
                       crs=part['crs'],transform=Affine(*t['transform']),nodata=-9999) as ds:
        ds.write(np.full((2,h,w),.25))


class BoundaryMaskTests(unittest.TestCase):
    def test_day_tiff_outside_province_is_nodata_and_masked(self):
        j=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'day.tif'
            result=download(None,j,path,triangle(j),{},fetch_full)
            self.assertTrue(result['boundary_mask']);self.assertGreater(result['outside_pixels_cleared'],0)
            with rasterio.open(path) as ds:
                data=ds.read();mask=ds.dataset_mask()
                self.assertEqual(data[0,-1,0],.25)        # inside (lower-left)
                self.assertEqual(data[0,0,-1],-9999)      # outside (upper-right)
                self.assertEqual(mask[-1,0],255);self.assertEqual(mask[0,-1],0)
                self.assertEqual(ds.tags()['BOUNDARY_MASK'],'province_polygon_all_touched')
            f=dict(size=str(path.stat().st_size),md5Checksum=hashes(path)[0])
            self.assertEqual(validate(path,f,j),hashes(path)[1])
            self.assertEqual([p.name for p in Path(tmp).iterdir()],['day.tif'])

    def test_stitched_day_tiff_is_masked_too(self):
        j=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'day.tif'
            from unittest.mock import patch
            with patch('task_pipeline.province_image.small',return_value=False):
                result=download(None,j,path,triangle(j),{},fetch_full)
            self.assertEqual(result['strategy'],'internal_chunks');self.assertTrue(result['boundary_mask'])
            with rasterio.open(path) as ds:
                self.assertEqual(ds.read(1)[0,-1],-9999)

    def test_night_tiff_unchanged(self):
        j=fixture('VIIRS_MONTHLY')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'night.tif'
            result=download(None,j,path,triangle(j),{},fetch_full)
            self.assertNotIn('boundary_mask',result)
            with rasterio.open(path) as ds:
                self.assertEqual(ds.read(1)[0,-1],.25)

    def test_band_descriptions_and_grid_preserved(self):
        j=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'day.tif';fetch_full(None,j,path)
            with rasterio.open(path,'r+') as ds:
                ds.set_band_description(1,'RED');ds.set_band_description(2,'NIR');ds.update_tags(SOURCE='S2')
            mask_outside(path,j,triangle(j))
            with rasterio.open(path) as ds:
                self.assertEqual(ds.descriptions,('RED','NIR'));self.assertEqual(ds.tags()['SOURCE'],'S2')
                self.assertEqual(ds.transform,Affine(*j['tile']['transform']));self.assertEqual(ds.nodata,-9999)


if __name__=='__main__':
    unittest.main()


class Int16DayTests(unittest.TestCase):
    def test_int16_day_tiff_is_scaled_masked_and_valid(self):
        j=dict(fixture(),dtype='int16')
        def fetch_int(image,part,path):
            t=part['tile'];h,w=t['height'],t['width']
            with rasterio.open(path,'w',driver='GTiff',width=w,height=h,count=2,dtype='int16',
                               crs=part['crs'],transform=Affine(*t['transform']),nodata=-9999) as ds:
                ds.write(np.full((2,h,w),2500,dtype='int16'))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'day.tif'
            from unittest.mock import patch
            for chunked in (False,True):
                with patch('task_pipeline.province_image.small',return_value=not chunked):
                    download(None,j,path,triangle(j),{},fetch_int)
                with rasterio.open(path) as ds:
                    self.assertEqual(ds.dtypes,('int16','int16'));self.assertEqual(ds.scales,(1e-4,1e-4))
                    self.assertEqual(ds.read(1)[-1,0],2500);self.assertEqual(ds.read(1)[0,-1],-9999)
                    self.assertEqual(ds.tags()['SCALE_FACTOR'],'0.0001')
                f=dict(size=str(path.stat().st_size),md5Checksum=hashes(path)[0])
                self.assertEqual(validate(path,f,j),hashes(path)[1])
                from province_pipeline.quality import inspect_raster
                qa=inspect_raster(path,dict(j,variant='composite'))
                self.assertGreater(qa['valid_pixel_pct'],0);self.assertNotIn('VALUE_RANGE_REVIEW',qa['flags'])
                path.unlink()
