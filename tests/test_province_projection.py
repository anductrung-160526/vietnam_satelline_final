"""CRS request representation and fail-fast projection probe, no live credentials."""
import unittest
from unittest.mock import Mock, patch
from rasterio.crs import CRS
from province_pipeline.projection import ee_crs,same_crs,probe_download_projection


class ProjectionTests(unittest.TestCase):
    def test_wkt_roundtrip_preserves_original_equal_area_crs(self):
        wkt=ee_crs('EPSG:6933')
        self.assertTrue(wkt.startswith('PROJCS['))
        self.assertIn('Cylindrical_Equal_Area',wkt)
        self.assertEqual(CRS.from_wkt(wkt),CRS.from_epsg(6933))
        self.assertEqual(CRS.from_wkt(wkt).to_epsg(),6933)

    def test_crs_comparison_accepts_equivalent_wkt_and_epsg(self):
        self.assertTrue(same_crs(ee_crs('EPSG:6933'),'EPSG:6933'))
        self.assertFalse(same_crs('EPSG:4326','EPSG:6933'))
        self.assertFalse(same_crs(None,'EPSG:6933'))

    def test_probe_sends_wkt_transform_and_dimensions_without_region(self):
        projection=Mock();projection.nominalScale.return_value.getInfo.return_value=1
        image=Mock();image.toFloat.return_value=image
        image.getDownloadURL.return_value='https://example.invalid/not-a-real-signed-url'
        with patch('ee.Projection',return_value=projection) as ctor,patch('ee.Image.constant',return_value=image):
            self.assertIsNone(probe_download_projection({'crs':'EPSG:6933'}))
        self.assertEqual(ctor.call_args.args[0],ee_crs('EPSG:6933'))
        params=image.getDownloadURL.call_args.args[0]
        self.assertEqual(CRS.from_wkt(params['crs']),CRS.from_epsg(6933))
        self.assertNotIn('region',params)
        self.assertEqual(params['dimensions'],[4,4])

    def test_probe_rejects_bad_scale_before_getting_download_url(self):
        projection=Mock();projection.nominalScale.return_value.getInfo.return_value=0
        with patch('ee.Projection',return_value=projection),patch('ee.Image.constant') as image:
            with self.assertRaisesRegex(RuntimeError,'invalid scale'):
                probe_download_projection({'crs':'EPSG:6933'})
        image.assert_not_called()

    def test_probe_surfaces_server_projection_rejection(self):
        import ee
        projection=Mock();projection.nominalScale.return_value.getInfo.side_effect=ee.EEException('Projection could not be parsed')
        with patch('ee.Projection',return_value=projection):
            with self.assertRaisesRegex(ee.EEException,'could not be parsed'):
                probe_download_projection({'crs':'EPSG:6933'})


if __name__=='__main__':unittest.main()
