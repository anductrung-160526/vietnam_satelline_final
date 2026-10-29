"""National scope, bounded grids, remote resume and VRT pixel checks."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np
import rasterio
from rasterio.transform import Affine
from shapely.geometry import box
import flow07_national as n

class NationalTests(unittest.TestCase):
    def test_one_union_feature_passed_to_reducers(self):
        source=Mock()
        with patch.object(n.v.ee,'Feature') as feature, patch.object(n.v.ee,'FeatureCollection') as collection:
            n.national_collection(source)
        source.geometry.assert_called_once_with(maxError=1)
        feature.assert_called_once_with(source.geometry.return_value,n.COUNTRY)
        collection.assert_called_once_with([feature.return_value])

    def test_grid_covers_entire_country_bbox(self):
        bounds=[102.01,8.12,116.94,23.39]
        for scale in (20,500):
            g=n.grid(bounds,scale);a,_,x,_,e,y=g['transform']
            self.assertLessEqual(x,bounds[0]);self.assertGreaterEqual(y,bounds[3])
            self.assertGreaterEqual(x+g['width']*a,bounds[2])
            self.assertLessEqual(y+g['height']*e,bounds[1])
        self.assertLess(n.TILE*n.TILE*10*8,24_000_000)

    def test_windows_skip_sea(self):
        g=dict(width=1024,height=1024,transform=[1,0,0,0,-1,1024])
        self.assertEqual(list(n.windows(g,box(1,513,511,1023))),[(0,0,512,512)])

    def test_remote_uploaded_tile_is_not_downloaded_again(self):
        window=(0,0,512,512);base='National/DAY/2024/01'
        known={f'{base}/tiles/{n.tile_name(window)}'};download=Mock()
        self.assertEqual(n.fetch_window(None,{},window,base,known,['BLUE'],download),[window])
        download.assert_not_called()

    def test_recursive_split_keeps_all_children_and_resumes(self):
        parent=(0,0,512,512);base='National/DAY/2024/01';known=set();download=Mock()
        def fetch(image,g,window,path,bands):
            if window==parent:raise n.v.TooLargeError('too large')
        download.side_effect=fetch
        def publish(path,relative,known):known.add(relative)
        with patch.object(n,'publish',side_effect=publish):
            children=n.fetch_window(None,{},parent,base,known,['BLUE'],download)
            self.assertEqual(sum(w*h for _,_,w,h in children),512*512)
            self.assertEqual(len(children),4)
            download.reset_mock()
            n.fetch_window(None,{},parent,base,known,['BLUE'],download)
            self.assertEqual(download.call_count,1)

    def test_vrt_preserves_pixels_and_sea_nodata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'tiles').mkdir()
            g=dict(width=4,height=2,transform=[1,0,100,0,-1,20]);window=(0,0,2,2)
            with rasterio.open(root/'tiles'/n.tile_name(window),'w',driver='GTiff',width=2,height=2,
                count=1,dtype='float64',crs='EPSG:4326',transform=Affine(*n.tile_transform(g,window)),nodata=-9999) as ds:
                ds.write(np.array([[[1,2],[3,4]]],dtype='float64'))
            n.write_vrt(root/'national.vrt',g,[window],['BLUE'])
            with rasterio.open(root/'national.vrt') as ds:
                np.testing.assert_array_equal(ds.read(1),[[1,2,-9999,-9999],[3,4,-9999,-9999]])
                self.assertEqual(ds.descriptions,('BLUE',));self.assertEqual(ds.tags()['LEVEL'],'national')

    def test_upload_failure_is_not_marked_complete(self):
        with patch.object(n.v,'check_stop'),patch.object(n.v,'_rclone',return_value=False):
            known=set()
            with self.assertRaises(RuntimeError):n.publish(Path('tile.tif'),'tile.tif',known)
            self.assertFalse(known)

    def test_main_processes_all_months_on_one_country_geometry(self):
        import json
        from shapely.geometry import mapping
        with tempfile.TemporaryDirectory() as tmp, patch.multiple(n.v,
            LOCAL_ROOT=tmp, MODE='full', MONTHS=list(range(1,13)),
            setup_logging=Mock(), init_storage=Mock(), install_signal_handlers=Mock(),
            init_earth_engine=Mock(), rclone_sync_once=Mock(), drive_stop_exists=Mock(return_value=False),
            ee_getinfo=Mock(return_value=mapping(box(102,8,110,24))),
            fetch_plan=Mock(return_value=(1,{m:dict(s2_window=0,viirs='VIIRS') for m in range(1,13)})),
            day_image=Mock(), night_image=Mock(), check_stop=Mock()
        ), patch.object(n,'national_collection') as country, \
           patch.object(n,'publish_stats') as stats, \
           patch.object(n,'remote_files',return_value=set()), \
           patch.object(n,'publish_image') as images:
            Path(tmp,'_control').mkdir()
            self.assertEqual(n.main(),0)
            self.assertEqual(images.call_count,24)
            self.assertEqual({call.args[4] for call in images.call_args_list},set(range(1,13)))
            stats.assert_called_once_with(country.return_value,country.return_value.geometry.return_value)
            report=json.loads(Path(tmp,'_control/national_progress.json').read_text())
            self.assertEqual(report['level'],'national')
            self.assertEqual(report['status'],'complete')
