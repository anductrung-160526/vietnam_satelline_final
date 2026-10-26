"""Catalog definitions. Coverage is queried live, never inferred from the filename."""
SOURCES = {
    'LANDSAT': {'collections': ['LANDSAT/LT05/C02/T1_L2', 'LANDSAT/LE07/C02/T1_L2',
                               'LANDSAT/LC08/C02/T1_L2', 'LANDSAT/LC09/C02/T1_L2'],
                'scale': 30, 'bands': ['BLUE','GREEN','RED','NIR','SWIR1','SWIR2','NDVI','NDBI','MNDWI','BSI'],
                'unit': 'surface_reflectance_and_dimensionless_indices',
                'reference': 'https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T1_L2'},
    'SENTINEL2': {'collections': ['COPERNICUS/S2_SR_HARMONIZED'], 'scale': 20,
                  'bands': ['BLUE','GREEN','RED','NIR','SWIR1','SWIR2','NDVI','NDBI','MNDWI','BSI'],
                  'unit': 'surface_reflectance_and_dimensionless_indices',
                  'reference': 'https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED'},
    'SENTINEL2_10M': {'collections': ['COPERNICUS/S2_SR_HARMONIZED'], 'scale': 10,
                      'bands': ['BLUE','GREEN','RED','NIR'], 'unit': 'surface_reflectance',
                      'reference': 'https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED'},
    'DMSP': {'collections': ['NOAA/DMSP-OLS/NIGHTTIME_LIGHTS'], 'scale': 1000,
             'bands': ['stable_lights'], 'unit': 'DN_unharmonized',
             'reference': 'https://developers.google.com/earth-engine/datasets/catalog/NOAA_DMSP-OLS_NIGHTTIME_LIGHTS'},
    'VIIRS_MONTHLY': {'collections': ['NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG'], 'scale': 500,
                      'bands': ['avg_rad','cf_cvg'], 'unit': 'nW_cm-2_sr-1',
                      'reference': 'https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_MONTHLY_V1_VCMSLCFG'},
    'VIIRS_ANNUAL': {'collections': ['NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG'], 'scale': 500,
                     'bands': ['avg_rad','cf_cvg'], 'unit': 'nW_cm-2_sr-1',
                     'reference': 'https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_MONTHLY_V1_VCMSLCFG'},
    # Official EOG annual VNL composites (V2.1 2013-2021, V2.2 later years); a year missing
    # from both is reported UNAVAILABLE and built locally from the monthly raw images.
    'VIIRS_ANNUAL_EOG': {'collections': ['NOAA/VIIRS/DNB/ANNUAL_V21','NOAA/VIIRS/DNB/ANNUAL_V22'], 'scale': 500,
                         'bands': ['average','average_masked','cf_cvg'], 'unit': 'nW_cm-2_sr-1',
                         'reference': 'https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_ANNUAL_V21'},
}
BANDS = ['BLUE','GREEN','RED','NIR','SWIR1','SWIR2']
NTL_PACKAGE = 'VN_NTL_Panel_2004_2025'
DAY_PACKAGE = 'VN_LandCover_Panel_2004_2025'
