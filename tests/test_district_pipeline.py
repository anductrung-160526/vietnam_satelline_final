"""Cross-year dates, level-2 queries, durable resume and real GeoTIFF checks."""
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

with patch.dict(os.environ, {'VNGIS_SKIP_MAIN': '1'}):
    import vngis_2024 as v
import verify_pilot as verify

ROW = {'GID_1': 'VNM.1_1', 'NAME_1': 'An Giang', 'GID_2': 'VNM.1.1_1',
       'NAME_2': 'An Phú', 'TYPE_2': 'Huyện'}
URBAN = {'GID_1': 'VNM.1_1', 'NAME_1': 'An Giang', 'GID_2': 'VNM.1.3_1',
         'NAME_2': 'Châu Đốc', 'TYPE_2': 'Thành phố'}


def complete_state(gid=ROW['GID_2']):
    return {'gid_2': gid, 'profile': v.OUTPUT_PROFILE, 'period': v.PERIOD_ID,
            'status': 'done', 't1': 'ok', 't3csv': 'ok',
            **{slot: dict.fromkeys(v.MONTH_KEYS, 'ok') for slot in
               ('t2', 't3img', 't1_by_month', 't3csv_by_month')}}


def day_props(row=ROW):
    return [{**row, 'YEAR': y, 'MONTH': m, **dict.fromkeys(v.T1_FEATURES, 0.2)} for y, m in v.PERIODS]


def night_records(row=ROW):
    return pd.DataFrame([{**row, 'YEAR': y, 'MONTH': m, 'TIME': v.month_key((y,m)),
                          'DATA_STATUS': 'ok', 'ERROR': '', 'TNL': float(i+1)}
                         for i,(y,m) in enumerate(v.PERIODS)]).reindex(columns=v.NIGHT_COLUMNS)


class LocalCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / '_control/status').mkdir(parents=True)
        p = patch.multiple(v, LOCAL_ROOT=str(self.root), STATUS_FILE=str(self.root / '_control/status/status_test.jsonl'),
                           PARTS_STAMP='test', ADMIN_BY_GID={ROW['GID_2']: ROW},
                           START_GID='', REPAIR_GIDS='', CSV_REPAIR_ONLY=False,
                           STOP_EVENT=threading.Event(), STOP_REASON=[None], REST_SEC=0, ALLOW_FULL_RESTART=False,
                           RESUME_DIAGNOSTICS={}, RESTORE_INT16_MARKER=False, DAY_IMAGE_SCALE=20,
                           REMOTE_TIFS=set(), REMOTE_INT16_TIFS=set(),
                           _dl_stats={'ok':0,'fail':0,'last_err':''})
        p.start()
        self.addCleanup(p.stop)


class DateTests(unittest.TestCase):
    def test_exact_twelve_months_across_year(self):
        self.assertEqual(v.PERIODS, [(2024,m) for m in range(7,13)] + [(2025,m) for m in range(1,7)])
        self.assertEqual(v.MONTH_KEYS[5:7], ['2024-12','2025-01'])

    def test_calendar_end_is_exclusive_next_month(self):
        self.assertEqual(v._month_dates(2024,12), ('2024-12-01','2025-01-01'))
        self.assertEqual(v._month_dates(2024,2), ('2024-02-01','2024-03-01'))
        self.assertEqual(v._month_dates(2025,6), ('2025-06-01','2025-07-01'))

    def test_invalid_or_reversed_month_range_fails(self):
        for a,b in [('2024-13','2025-06'),('2024-7','2025-06'),('2025-06','2024-07')]:
            with self.subTest(a=a), self.assertRaises(ValueError):
                v.month_pairs(a,b)

    def test_tiff_filenames_preserve_gid_and_year(self):
        ctx=v.build_ctx(ROW)
        self.assertEqual(v.day_name(ctx,(2024,12)), 'VNM.1.1_1_day_202412.tif')
        self.assertEqual(v.day_name(ctx,(2025,1)), 'VNM.1.1_1_day_202501.tif')
        self.assertNotEqual(v.night_name(ctx,(2024,7)),v.night_name(ctx,(2025,7)))
        self.assertNotIn('GID_3',v.ADM_COLS)

    def test_full_targets_ignore_commune_province_boundary(self):
        admin=pd.DataFrame([URBAN,ROW])
        with patch.object(v,'MODE','full'):
            selected=v.load_targets(admin)
        self.assertEqual(list(selected.GID_2),[ROW['GID_2'],URBAN['GID_2']])

    def test_fast_profile_uses_separate_50m_folder_and_does_not_upgrade_20m_state(self):
        script="""import json, vngis_2024 as v
old={'profile':v.LEGACY_FLOAT_PROFILE,'period':v.PERIOD_ID,'gid_2':'VNM.1.1_1'}
print(json.dumps({'scale':v.DAY_IMAGE_SCALE,'folder':v.DRIVE_FOLDER,'profile':v.OUTPUT_PROFILE,'migrated':v.current_status(v.migrate_float_status(old))}))"""
        env={**os.environ,'VNGIS_SKIP_MAIN':'1','VNGIS_DAY_IMAGE_SCALE':'50','VNGIS_MODE':'pilot'}
        env.pop('VNGIS_DRIVE_FOLDER',None)
        result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,check=True)
        data=json.loads(result.stdout)
        self.assertEqual(data['scale'],50)
        self.assertEqual(data['folder'],'VNGISDash_202407_202506_Districts_50m_PILOT')
        self.assertTrue(data['profile'].endswith(':day-scale-50'));self.assertFalse(data['migrated'])

    def test_large_pilot_samples_across_country(self):
        rows=[{**ROW,'GID_1':f'VNM.{i+1}_1','GID_2':f'VNM.{i+1}.1_1'} for i in range(30)]
        rows[1]['TYPE_2']='Thành phố'
        with patch.object(v,'MODE','pilot'),patch.object(v,'PILOT_N',6):
            selected=v.load_targets(pd.DataFrame(rows))
        self.assertEqual(len(selected),6)
        self.assertEqual(selected.iloc[-1].GID_1,'VNM.30_1')
        self.assertIn('Thành phố',set(selected.TYPE_2))

    def test_pilot_samples_rural_and_urban_districts(self):
        with patch.multiple(v,MODE='pilot',PILOT_N=2):
            selected=v.load_targets(pd.DataFrame([ROW,URBAN]))
        self.assertEqual(set(selected.TYPE_2), {'Huyện','Thành phố'})


class StartDistrictTests(LocalCase):
    def range_admin(self):
        gids = ['VNM.56.1_1', 'VNM.55.10_1', 'VNM.55.7_1', 'VNM.55.8_1', 'VNM.55.6_1']
        return pd.DataFrame([{**ROW, 'GID_2': gid} for gid in gids])

    def test_full_range_includes_start_and_sorts_numeric_ids(self):
        with patch.multiple(v, MODE='full', START_GID='VNM.55.8_1'):
            selected = v.load_targets(self.range_admin())
        self.assertEqual(list(selected.GID_2), ['VNM.55.8_1', 'VNM.55.10_1', 'VNM.56.1_1'])

    def test_short_start_code_and_empty_start(self):
        with patch.multiple(v, MODE='full', START_GID=' 55.8 '):
            selected = v.load_targets(self.range_admin())
        self.assertEqual(selected.iloc[0].GID_2, 'VNM.55.8_1')
        with patch.multiple(v, MODE='full', START_GID=''):
            self.assertEqual(len(v.load_targets(self.range_admin())), 5)

    def test_bad_or_missing_start_does_not_silently_select_another_district(self):
        for start in ['55.9', 'VNM.55.8_2', '../55.8', 'communes_l3']:
            with self.subTest(start=start), patch.multiple(v, MODE='full', START_GID=start):
                with self.assertRaises(ValueError):
                    v.load_targets(self.range_admin())

    def test_pilot_ignores_full_only_start_code(self):
        with patch.multiple(v, MODE='pilot', PILOT_N=2, START_GID='VNM.55.8_1'):
            selected = v.load_targets(pd.DataFrame([ROW, URBAN]))
        self.assertEqual(set(selected.GID_2), {ROW['GID_2'], URBAN['GID_2']})

    def test_range_keeps_original_progress_report_and_does_not_mark_skipped_done(self):
        original = self.root / '_control/progress.csv'
        original.write_text('old progress', encoding='utf-8')
        with patch.multiple(v, MODE='full', START_GID='55.8'):
            targets = v.load_targets(self.range_admin())
            progress = v.write_progress(targets, {})
        self.assertEqual(original.read_text(encoding='utf-8'), 'old progress')
        self.assertTrue((self.root / '_control/progress_from_VNM.55.8_1.csv').is_file())
        self.assertEqual(set(progress.status), {'pending'})
        self.assertNotIn('VNM.55.7_1', set(progress.GID_2))

    def test_previous_district_checkpoints_do_not_block_intentional_tail_run(self):
        admin = self.range_admin()
        rows = {row['GID_2']: row for row in admin.to_dict('records')}
        diag = {'claimed_done': 1, 'claimed_done_gids': ['VNM.55.7_1']}
        with patch.multiple(v, MODE='full', START_GID='55.8', ADMIN_BY_GID=rows,
                            REMOTE_TIFS={'Day/old/VNM.55.7_1_day_202407.tif'}, RESUME_DIAGNOSTICS=diag):
            targets = v.load_targets(admin)
            v.check_resume(targets, {})
            jobs = v.next_round_jobs(list(targets.GID_2), rows, {})
        self.assertEqual([gid for gid, _, _ in jobs], ['VNM.55.8_1', 'VNM.55.10_1', 'VNM.56.1_1'])

    def test_missing_completion_evidence_inside_range_still_blocks_restart(self):
        admin = self.range_admin()
        rows = {row['GID_2']: row for row in admin.to_dict('records')}
        diag = {'claimed_done': 1, 'claimed_done_gids': ['VNM.55.8_1']}
        with patch.multiple(v, MODE='full', START_GID='55.8', ADMIN_BY_GID=rows, RESUME_DIAGNOSTICS=diag):
            with self.assertRaises(RuntimeError):
                v.check_resume(v.load_targets(admin), {})

    def test_resume_skips_complete_start_but_keeps_missing_later_districts(self):
        with patch.multiple(v, MODE='full', START_GID='55.8'):
            targets = v.load_targets(self.range_admin())
        rows = {row['GID_2']: row for row in targets.to_dict('records')}
        states = {'VNM.55.8_1': complete_state('VNM.55.8_1')}
        jobs = v.next_round_jobs(list(targets.GID_2), rows, states)
        self.assertEqual([gid for gid, _, _ in jobs], ['VNM.55.10_1', 'VNM.56.1_1'])


    def test_explicit_repairs_run_after_tail_without_duplicates(self):
        with patch.multiple(v, MODE='full', START_GID='55.8', REPAIR_GIDS='55.7,55.6;55.8,55.7,'):
            targets = v.load_targets(self.range_admin())
        self.assertEqual(list(targets.GID_2), ['VNM.55.8_1', 'VNM.55.10_1', 'VNM.56.1_1',
                                             'VNM.55.7_1', 'VNM.55.6_1'])

    def test_invalid_repair_fails_instead_of_ignoring_district(self):
        with patch.multiple(v, MODE='full', START_GID='55.8', REPAIR_GIDS='55.9'):
            with self.assertRaises(ValueError):
                v.load_targets(self.range_admin())
        with patch.multiple(v, MODE='full', START_GID='55.8', REPAIR_GIDS='none'):
            self.assertEqual(len(v.load_targets(self.range_admin())), 3)

    def test_exhausted_explicit_repair_reopens_once_and_preserves_month_evidence(self):
        state = complete_state(ROW['GID_2'])
        state['attempts'] = v.MAX_ATTEMPTS
        state['status'] = 'partial'
        state['t1_by_month']['2024-07'] = 'no_data'
        states = {ROW['GID_2']: state, URBAN['GID_2']: {**state, 'gid_2': URBAN['GID_2']}}
        with patch.multiple(v, MODE='full', REPAIR_GIDS=ROW['GID_2']):
            v.reopen_requested_repairs(states)
            self.assertEqual(states[ROW['GID_2']]['attempts'], 0)
            self.assertEqual(states[ROW['GID_2']]['t2'], state['t2'])
            self.assertEqual(states[ROW['GID_2']]['t1_by_month']['2024-07'], 'no_data')
            self.assertEqual(states[URBAN['GID_2']]['attempts'], v.MAX_ATTEMPTS)
            v.reopen_requested_repairs(states)
        self.assertEqual(len(Path(v.STATUS_FILE).read_text().splitlines()), 1)

    def test_completed_or_missing_asset_repair_is_not_reopened(self):
        for state in [complete_state(), {**complete_state(), 'status': 'not_in_asset',
                                        't2': {}, 'attempts': v.MAX_ATTEMPTS}]:
            with self.subTest(status=state['status']), patch.multiple(v, MODE='full', REPAIR_GIDS=ROW['GID_2']):
                with patch.object(v, 'write_status') as save:
                    v.reopen_requested_repairs({ROW['GID_2']: state})
                    save.assert_not_called()

    def test_csv_only_scope_selects_exact_repairs_and_ignores_start(self):
        with patch.multiple(v, MODE='full', CSV_REPAIR_ONLY=True, START_GID='invalid start',
                            REPAIR_GIDS='55.7,55.6'):
            targets = v.load_targets(self.range_admin())
            self.assertEqual(list(targets.GID_2), ['VNM.55.7_1', 'VNM.55.6_1'])
            self.assertEqual(v.progress_filename(), 'progress_csv_repair.csv')
        for ids in ['none', '', '55.9']:
            with self.subTest(ids=ids), patch.multiple(v, MODE='full', CSV_REPAIR_ONLY=True, REPAIR_GIDS=ids):
                with self.assertRaises(ValueError):
                    v.load_targets(self.range_admin())

    def test_csv_complete_does_not_claim_tiffs_complete_and_is_not_queued_again(self):
        st = complete_state()
        st.update(t2={}, t3img={}, status='partial', attempts=1)
        with patch.multiple(v, MODE='full', CSV_REPAIR_ONLY=True):
            self.assertTrue(v.csv_complete(st))
            self.assertFalse(v.district_complete(st))
            self.assertTrue(v.core_finished(st))
            self.assertEqual(v.next_round_jobs([ROW['GID_2']], {ROW['GID_2']: ROW}, {ROW['GID_2']: st}), [])
            st['t1_by_month']['2024-07'] = 'no_data'
            self.assertFalse(v.core_finished(st))


class StableUploadTests(LocalCase):
    def test_live_status_parts_and_log_append_do_not_change_upload_source(self):
        v.write_status(complete_state())
        v.append_parts('day', [{'GID_2': ROW['GID_2'], 'YEAR': 2024, 'MONTH': 7}])
        log_path = self.root / '_control/logs/run.log'
        log_path.parent.mkdir()
        log_path.write_text('before\n', encoding='utf-8')
        (self.root / '_control/incomplete.part').write_text('not ready', encoding='utf-8')
        snapshots = []
        def upload(args, **kwargs):
            src = Path(args[1]);snapshots.append(src)
            self.assertNotEqual(src, self.root / '_control')
            original = (src / 'status/status_test.jsonl').read_text()
            parts = (src / 'parts/day_test.jsonl').read_text()
            self.assertFalse((src / 'incomplete.part').exists())
            v.write_status({'gid_2': 'VNM.55.8_1', 'status': 'partial'})
            v.append_parts('day', [{'GID_2': 'VNM.55.8_1', 'YEAR': 2024, 'MONTH': 8}])
            with log_path.open('a', encoding='utf-8') as f: f.write('after\n')
            self.assertEqual((src / 'status/status_test.jsonl').read_text(), original)
            self.assertEqual((src / 'parts/day_test.jsonl').read_text(), parts)
            self.assertEqual((src / 'logs/run.log').read_text(), 'before\n')
            return True
        with patch.object(v, '_rclone', side_effect=upload):
            self.assertTrue(v._copy_stable_directory(v.D_CONTROL))
        self.assertFalse(snapshots[0].exists())
        self.assertEqual(len(Path(v.STATUS_FILE).read_text().splitlines()), 2)
        self.assertEqual(log_path.read_text(), 'before\nafter\n')

    def test_failed_upload_keeps_original_checkpoint(self):
        v.write_status(complete_state())
        before = Path(v.STATUS_FILE).read_text()
        with patch.object(v, '_rclone', return_value=False):
            self.assertFalse(v._copy_stable_directory(v.D_CONTROL))
        self.assertEqual(Path(v.STATUS_FILE).read_text(), before)

    def test_checkpoint_upload_precedes_tiffs_and_marker_upload_follows(self):
        day = self.root / 'Day/day.tif';day.parent.mkdir()
        v.write_day_int16(day, np.full((10,2,2),0.2,'float32'), from_origin(105,22,0.001,0.001),
                          'EPSG:4326', np.nan, v.DAY_BANDS_ALL)
        v.write_status(complete_state())
        calls = []
        def upload(args, **kwargs):
            calls.append((args[0],args[2]))
            return True
        with patch.object(v, '_rclone', side_effect=upload):
            self.assertTrue(v.rclone_sync_once(final=True))
        self.assertEqual(calls[0], ('copy', f'{v.REMOTE_BASE}/_control'))
        self.assertEqual(calls[1], ('move', f'{v.REMOTE_BASE}/Day'))
        self.assertEqual(calls[-1], ('copy', f'{v.REMOTE_BASE}/_control'))

    def test_csv_repair_does_not_upload_or_remove_existing_local_tiff(self):
        day = self.root / 'Day/old.tif';day.parent.mkdir()
        day.write_bytes(b'existing TIFF is untouched')
        with patch.multiple(v, MODE='full', CSV_REPAIR_ONLY=True), patch.object(v, '_rclone', return_value=True) as upload:
            self.assertTrue(v.rclone_sync_once(final=True))
        self.assertTrue(day.exists())
        self.assertFalse(any(c.args[0][0] == 'move' for c in upload.call_args_list))


class Node:
    def __init__(self,calls,kind='node'):
        self.calls,self.kind=calls,kind
    def __getattr__(self,name):
        def method(*args,**kwargs):
            self.calls.append((name,args,kwargs))
            if name=='map' and self.kind=='featurecollection':
                args[0](Node(self.calls,'feature'))
            if name=='reduceRegions':
                return Node(self.calls,'featurecollection')
            return self
        return method


def fake_ee(calls):
    return SimpleNamespace(ImageCollection=lambda *a:Node(calls,'imagecollection'),
                           FeatureCollection=lambda *a:Node(calls,'featurecollection'),
                           Image=lambda *a:Node(calls),Dictionary=lambda a:a,List=lambda a:a,
                           Reducer=Node(calls),Filter=Node(calls),
                           Algorithms=SimpleNamespace(If=lambda condition,a,b:a))


class QueryTests(unittest.TestCase):
    def test_fetch_plan_queries_exact_year_month_dates(self):
        calls=[]
        result={'n_fc':1,'months':[[1,0,0,1,0] for _ in v.PERIODS]}
        with patch.object(v,'ee',fake_ee(calls)),patch.object(v,'ee_getinfo',return_value=result):
            count,plan=v.fetch_plan(Node(calls),Node(calls))
        self.assertEqual(count,1)
        self.assertEqual(list(plan),v.PERIODS)
        dates=[args for name,args,kw in calls if name=='filterDate']
        self.assertIn(('2025-01-01','2025-02-01'),dates)
        self.assertNotIn(('2024-01-01','2024-02-01'),dates)

    def test_task1_tags_year_and_month_on_each_feature(self):
        calls=[]
        with patch.object(v,'ee',fake_ee(calls)),patch.object(v,'ee_getinfo',return_value={'features':[]}):
            v.task1_all_months(Node(calls))
        tags=[args[0] for name,args,kw in calls if name=='set']
        self.assertEqual(tags,[{'YEAR':y,'MONTH':m} for y,m in v.PERIODS])
        selected=[args[0] for name,args,kw in calls if name=='select' and args and isinstance(args[0],list)]
        self.assertTrue(any('GID_2' in cols for cols in selected))

    def night_data(self,missing=None):
        return {'area_ha':123.0,'months':[{'n':0} if i==missing else
                 {'n':1,'all':{'avg_rad_count':2,'avg_rad_sum':float(i+1),'avg_rad_mean':0.5,
                               'avg_rad_stdDev':0.1,'avg_rad_min':0.0,'avg_rad_max':1.0},
                  'cnt':{'is_lit':1},'cf':{'cf_cvg':4},'lit':{'lit_rad':0.2}}
                  for i in range(12)]}

    def night_frame(self,data):
        calls=[]
        with patch.object(v,'ee',fake_ee(calls)),patch.object(v,'ee_getinfo',return_value=data):
            return v.task3_all_months(Node(calls),ROW)

    def test_night_rolling_and_growth_continue_over_new_year(self):
        frame=self.night_frame(self.night_data())
        january=frame[(frame.YEAR==2025)&(frame.MONTH==1)].iloc[0]
        self.assertEqual(january.TIME,'2025-01')
        self.assertEqual(january.TNL_MA3,6)
        self.assertAlmostEqual(january.TNL_MOM_GROWTH_PCT,(7/6-1)*100)
        self.assertEqual(list(frame.columns),v.NIGHT_COLUMNS)

    def test_missing_viirs_month_is_null_and_not_bridged_for_growth(self):
        frame=self.night_frame(self.night_data(missing=5))
        self.assertEqual(len(frame),12)
        self.assertEqual(frame.iloc[5].DATA_STATUS,'no_data')
        self.assertTrue(pd.isna(frame.iloc[5].TNL))
        self.assertTrue(pd.isna(frame.iloc[6].TNL_MOM_GROWTH_PCT))

    def test_no_viirs_data_does_not_create_zero_measurements(self):
        frame=self.night_frame({'area_ha':10,'months':[{'n':0}]*12})
        self.assertTrue(frame.DATA_STATUS.eq('no_data').all())
        self.assertTrue(frame.TNL.isna().all())

    def test_night_csv_repair_monthly_queries_preserve_rolling_and_growth(self):
        data = self.night_data(missing=5)
        expected = self.night_frame(data)
        calls = []
        monthly = [{'area_ha': data['area_ha'], 'months': [mo]} for mo in data['months']]
        with patch.multiple(v, MODE='full', CSV_REPAIR_ONLY=True), \
             patch.object(v, 'ee', fake_ee(calls)), patch.object(v, 'ee_getinfo', side_effect=monthly) as query:
            actual = v.task3_all_months(Node(calls), ROW)
        self.assertEqual(query.call_count, 12)
        pd.testing.assert_frame_equal(actual, expected)


def tif_bytes(array,transform,nodata=np.nan,crs='EPSG:4326'):
    with rasterio.MemoryFile() as mf:
        with mf.open(driver='GTiff',height=array.shape[1],width=array.shape[2],count=array.shape[0],
                     dtype=array.dtype,crs=crs,transform=transform,nodata=nodata) as dst:
            dst.write(array)
        return mf.read()


class TiffTests(LocalCase):
    def tiles(self,bad=False,misaligned=False):
        full=np.arange(10*6*6,dtype='float32').reshape(10,6,6)
        res=20/111319.49
        tr=from_origin(105,22,res,res)
        paths=[]
        for i,(r,c) in enumerate([(0,0),(0,2),(2,0),(2,2)]):
            a=full[:,r:r+4,c:c+4].copy()
            if bad and i==1:a[:,0,0]+=100
            transform=from_origin(105+c*res+(res/2 if misaligned and i==1 else 0),22-r*res,res,res)
            path=self.root/f'{i}.tile';path.write_bytes(tif_bytes(a,transform));paths.append(str(path))
        return full,tr,paths

    def test_streaming_mosaic_preserves_all_pixels_and_transform(self):
        full,tr,paths=self.tiles()
        path=self.root/'merged.tif';v.mosaic_tile_files(paths,str(path))
        with rasterio.open(path) as src:
            np.testing.assert_array_equal(src.read(),full)
            self.assertEqual(src.transform,tr)
            self.assertEqual(src.compression.value,'DEFLATE')
        self.assertEqual(v.inspect_tif(str(path),10),(True,False,''))

    def test_overlap_with_different_values_is_rejected(self):
        _,_,paths=self.tiles(bad=True)
        with self.assertRaisesRegex(RuntimeError,'chồng lấn'):
            v.mosaic_tile_files(paths,str(self.root/'bad.tif'))

    def test_half_pixel_shift_is_rejected(self):
        _,_,paths=self.tiles(misaligned=True)
        with self.assertRaisesRegex(RuntimeError,'lưới pixel'):
            v.mosaic_tile_files(paths,str(self.root/'bad.tif'))

    def test_large_download_uses_same_scale_for_every_tile(self):
        full,tr,paths=self.tiles()
        payloads=[Path(p).read_bytes() for p in paths]
        response=Mock(side_effect=[v.TooLargeError('request size too large (60000000 bytes)'),*payloads])
        path=self.root/'download.tif'
        with patch.object(v,'fetch_geotiff_bytes',response),patch.object(v,'_bbox',return_value=(0,0,6,6)),\
             patch.object(v,'_split_bbox',return_value=['a','b','c','d']):
            self.assertEqual(v.download_tif('image','region',20,str(path),'test'),4)
        self.assertTrue(all(call.args[2]==20 for call in response.call_args_list))
        with rasterio.open(path) as src:np.testing.assert_array_equal(src.read(),full)

    def test_legitimate_zero_night_radiance_is_not_empty(self):
        a=np.zeros((2,2,2),'float64');a[1]=5
        path=self.root/'night.tif';path.write_bytes(tif_bytes(a,from_origin(105,22,500/111319.49,500/111319.49)))
        self.assertEqual(v.inspect_tif(str(path),2),(True,False,''))

    def test_all_nodata_is_empty(self):
        path=self.root/'empty.tif';path.write_bytes(tif_bytes(np.full((10,2,2),np.nan,'float32'),from_origin(105,22,.001,.001)))
        self.assertEqual(v.inspect_tif(str(path),10),(True,True,''))


class ProcessTests(LocalCase):
    def setUp(self):
        super().setUp()
        self.fc=Mock();self.fc.filter.return_value=self.fc
        self.downloads=[]
        mocks=dict(districts_fc=self.fc,fetch_plan=Mock(return_value=(1,{p:{'s2_window':0,'viirs':v.VIIRS_A} for p in v.PERIODS})),
                   task1_all_months=Mock(return_value=day_props()),task3_all_months=Mock(return_value=night_records()),
                   day_image=Mock(),night_image=Mock(),_download_month=Mock(side_effect=self.download))
        p=patch.multiple(v,**mocks);p.start();self.addCleanup(p.stop)
        p=patch.object(v.ee.Filter,'eq',return_value='filter');p.start();self.addCleanup(p.stop)

    def download(self,kind,ctx,period,img,path):
        self.downloads.append((kind,period))
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        bands,scale,dtype=(10,20,'float32') if kind=='day' else (2,500,'float64')
        arr=np.ones((bands,2,2),dtype)
        tr=from_origin(105,22,scale/111319.49,scale/111319.49)
        if kind=='day' and v.DAY_FORMAT=='int16':
            v.write_day_int16(path,arr,tr,'EPSG:4326',np.nan,v.DAY_BANDS_ALL)
        else:
            Path(path).write_bytes(tif_bytes(arr,tr))
        return 1,False

    def test_process_writes_all_months_and_verified_csv_tiff(self):
        state=v.process_district(ROW,None)
        self.assertTrue(v.district_complete(state));self.assertEqual(state['status'],'done')
        self.assertEqual(len(self.downloads),24)
        self.assertEqual(set(state['t2']),set(v.MONTH_KEYS))
        v.write_status(state);v.build_national_csv()
        day=pd.read_csv(self.root/'CSV/day_indices.csv');night=pd.read_csv(self.root/'CSV/night_indices.csv')
        self.assertEqual(len(day),12);self.assertEqual(len(night),12)
        checks=verify.verify_district(str(self.root),ROW['GID_2'],state,day,night)
        self.assertTrue(all(level=='PASS' for _,level,_ in checks),checks)
        v.process_district(ROW,state)
        self.assertEqual(len(self.downloads),24)

    def test_csv_only_repairs_day_and_preserves_complete_night_without_tiffs(self):
        previous = complete_state()
        previous.update(t1='missing', t2={}, t3img={}, status='partial')
        previous['t1_by_month']['2024-07'] = 'no_data'
        with patch.multiple(v, MODE='full', CSV_REPAIR_ONLY=True), patch.object(v, 'ee_getinfo', return_value=1):
            state = v.process_district(ROW, previous)
            self.assertTrue(v.csv_complete(state))
            self.assertFalse(v.district_complete(state))
        v.task1_all_months.assert_called_once();v.task3_all_months.assert_not_called()
        v.fetch_plan.assert_not_called();v._download_month.assert_not_called()
        self.assertEqual(state['t2'], {});self.assertEqual(state['t3img'], {})
        v.build_national_csv()
        self.assertEqual(len(pd.read_csv(self.root/'CSV/day_indices.csv')), 12)

    def test_csv_only_repairs_night_and_preserves_day(self):
        previous = complete_state()
        previous.update(t3csv='fail', t3csv_by_month={}, status='partial')
        with patch.multiple(v, MODE='full', CSV_REPAIR_ONLY=True), patch.object(v, 'ee_getinfo', return_value=1):
            state = v.process_district(ROW, previous)
            self.assertTrue(v.csv_complete(state))
        v.task3_all_months.assert_called_once();v.task1_all_months.assert_not_called()
        v.fetch_plan.assert_not_called();v._download_month.assert_not_called()
        self.assertEqual(state['t2'], previous['t2'])

    def test_csv_only_preflight_does_not_download_sample_images(self):
        with patch.multiple(v, MODE='full', CSV_REPAIR_ONLY=True), \
             patch.object(v, 'ee_getinfo', return_value=1), patch.object(v, 'fetch_geotiff_bytes') as download:
            self.assertIn('CSV', v._probe_ee(ROW))
        v.fetch_plan.assert_not_called();download.assert_not_called()

    def test_resume_redownloads_only_missing_january_file(self):
        state=v.process_district(ROW,None);v.write_status(state)
        ctx=v.build_ctx(ROW);path=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,(2025,1))))
        path.unlink()
        restored=v.load_all_status()[ROW['GID_2']]
        self.assertEqual(restored['t2']['2025-01'],'pending')
        self.assertEqual(restored['t2']['2024-12'],'ok')
        v.process_district(ROW,restored)
        self.assertEqual(self.downloads[24:],[('day',(2025,1))])

    def test_verifier_uses_canonical_output_when_legacy_folder_copy_remains(self):
        state=v.process_district(ROW,None);v.write_status(state);v.build_national_csv()
        ctx=v.build_ctx(ROW)
        original=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,(2024,7))))
        legacy=self.root/'Day'/'legacy_province'/f"{ROW['GID_2']}_legacy"/original.name
        legacy.parent.mkdir(parents=True);legacy.write_bytes(original.read_bytes())
        checks=verify.verify_district(str(self.root),ROW['GID_2'],state,
            pd.read_csv(self.root/'CSV/day_indices.csv'),pd.read_csv(self.root/'CSV/night_indices.csv'))
        self.assertTrue(all(level=='PASS' for _,level,_ in checks),checks)

    def test_no_source_month_stays_partial_and_csv_has_nulls(self):
        props=day_props()[1:]
        v.task1_all_months.return_value=props
        plan={p:{'s2_window':None if p==(2024,7) else 0,'viirs':v.VIIRS_A} for p in v.PERIODS}
        v.fetch_plan.return_value=(1,plan)
        state=v.process_district(ROW,None)
        self.assertEqual(state['status'],'partial');self.assertFalse(v.district_complete(state))
        self.assertEqual(state['t2']['2024-07'],'no_data')
        v.build_national_csv();day=pd.read_csv(self.root/'CSV/day_indices.csv')
        self.assertEqual(len(day),12);self.assertEqual(day.iloc[0].DATA_STATUS,'no_data')
        self.assertTrue(day.iloc[0][v.T1_FEATURES].isna().all())

    def test_missing_csv_parts_reset_csv_completion_on_resume(self):
        state=v.process_district(ROW,None);v.write_status(state)
        for path in (self.root/'_control/parts').glob('day_*.jsonl'):path.unlink()
        restored=v.load_all_status()[ROW['GID_2']]
        self.assertEqual(restored['t1'],'pending')
        self.assertEqual(restored['status'],'partial')

    def test_status_from_different_period_is_ignored(self):
        state=complete_state();state['period']='202401-202412';v.write_status(state)
        self.assertEqual(v.load_all_status(),{})

    def test_csv_deduplicates_by_year_month_and_filters_foreign_periods(self):
        records=v.day_records(ROW,day_props())[:1]
        records += [{**records[0],'YEAR':2025},{**records[0],'YEAR':2023}]
        with patch.object(v,'PERIODS',v.PERIODS+[(2025,7)]):
            v.append_parts('day',records)
            v.append_parts('day',[{**records[0],'BLUE_mean':9}])
            v.build_national_csv()
        day=pd.read_csv(self.root/'CSV/day_indices.csv')
        self.assertEqual(list(day.YEAR),[2024,2025])
        self.assertEqual(day.iloc[0].BLUE_mean,9)

    def test_wrong_gid_in_statistics_is_rejected(self):
        props=day_props();props[0]['GID_2']=URBAN['GID_2']
        with self.assertRaisesRegex(RuntimeError,'GID_2'):
            v.day_records(ROW,props)

    def test_missing_band_mean_is_not_a_complete_statistics_month(self):
        props=day_props();props[0]['NDVI_mean']=None
        records=v.day_records(ROW,props)
        self.assertEqual(records[0]['DATA_STATUS'],'no_data')
        self.assertEqual(records[1]['DATA_STATUS'],'ok')

    def test_checkpoint_before_exception_is_preserved_by_run_round(self):
        def failing_process(row,previous):
            period=v.PERIODS[0];ctx=v.build_ctx(row)
            path=v.L(ctx['rel_day_dir'],v.day_name(ctx,period))
            self.download('day',ctx,period,None,path)
            state={'gid_2':row['GID_2'],'period':v.PERIOD_ID,'profile':v.OUTPUT_PROFILE,
                   't2':{v.month_key(period):'ok'},'t3img':{},'errors':[]}
            v._checkpoint(state)
            raise RuntimeError('Temporary error after one download')
        with patch.object(v,'process_district',side_effect=failing_process):
            v.run_round([(ROW['GID_2'],ROW,'full')],{})
        restored=v.load_all_status()[ROW['GID_2']]
        self.assertEqual(restored['t2'][v.MONTH_KEYS[0]],'ok')
        self.assertEqual(restored['attempts'],1)


class DriveResumeTests(LocalCase):
    def test_partial_marker_and_pending_overwrite_recover_from_verified_history(self):
        rows={r['GID_2']:r for r in (ROW,URBAN)};parts={'day':[],'night':[]}
        for gid,row in rows.items():
            v.write_status(complete_state(gid));ctx=v.build_ctx(row)
            for period in v.PERIODS:
                v.REMOTE_TIFS.add(ctx['rel_day_dir']+'/'+v.day_name(ctx,period))
                v.REMOTE_TIFS.add(ctx['rel_night_dir']+'/'+v.night_name(ctx,period))
                for kind in parts:
                    parts[kind].append({'GID_2':gid,'YEAR':period[0],'MONTH':period[1],
                                        '_profile':v.OUTPUT_PROFILE,'DATA_STATUS':'ok'})
        v.REMOTE_INT16_TIFS.add(v.build_ctx(ROW)['rel_day_dir']+'/'+v.day_name(v.build_ctx(ROW),v.PERIODS[0]))
        damaged=complete_state();damaged.update(status='partial',convert_day_months=['2024-08'])
        damaged['t2']['2024-08']='pending';damaged['t3img']['2024-08']='pending';v.write_status(damaged)
        with patch.multiple(v,ADMIN_BY_GID=rows,RESTORE_INT16_MARKER=True), \
             patch.object(v,'_read_parts',side_effect=lambda kind:parts[kind]):
            states=v.load_all_status()
        self.assertEqual(len(v.REMOTE_INT16_TIFS),24)
        self.assertTrue(all(v.district_complete(st) for st in states.values()))
        self.assertEqual(states[ROW['GID_2']]['convert_day_months'],[])

    def test_history_recovery_does_not_override_explicit_no_data_or_missing_tiff(self):
        v.write_status(complete_state());state=complete_state()
        state.update(status='partial');state['t2']['2024-07']='no_data';v.write_status(state)
        ctx=v.build_ctx(ROW)
        for period in v.PERIODS[:-1]:v.REMOTE_TIFS.add(ctx['rel_day_dir']+'/'+v.day_name(ctx,period))
        with patch.object(v,'RESTORE_INT16_MARKER',True):states=v.load_all_status()
        self.assertEqual(states[ROW['GID_2']]['t2']['2024-07'],'no_data')
        self.assertEqual(states[ROW['GID_2']]['t2']['2025-06'],'pending')
        self.assertEqual(len(v.REMOTE_INT16_TIFS),11)

    def test_resume_610_done_districts_keeps_only_100_jobs(self):
        rows={f'VNM.1.{i}_1':{**ROW,'GID_2':f'VNM.1.{i}_1'} for i in range(1,711)}
        parts={'day':[],'night':[]}
        for gid,row in list(rows.items())[:610]:
            v.write_status(complete_state(gid))
            ctx=v.build_ctx(row)
            for period in v.PERIODS:
                for kind in ('day','night'):
                    parts[kind].append({'GID_2':gid,'YEAR':period[0],'MONTH':period[1],
                                        'DATA_STATUS':'ok','_profile':v.OUTPUT_PROFILE})
                v.REMOTE_TIFS.add(ctx['rel_day_dir']+'/'+v.day_name(ctx,period))
                v.REMOTE_TIFS.add(ctx['rel_night_dir']+'/'+v.night_name(ctx,period))
        targets=pd.DataFrame(rows.values())
        # Reproduce the old --sync-only bug: Drive has all TIFFs, marker is empty.
        with patch.multiple(v,ADMIN_BY_GID=rows,MODE='full',RESTORE_INT16_MARKER=True), \
             patch.object(v,'_read_parts',side_effect=lambda kind:parts[kind]):
            states=v.load_all_status();v.check_resume(targets,states)
            jobs=v.next_round_jobs(list(rows),rows,states)
        self.assertEqual(sum(v.district_complete(st) for st in states.values()),610)
        self.assertEqual(len(jobs),100)
        self.assertEqual(len(v.REMOTE_INT16_TIFS),610*12)
        self.assertNotIn('VNM.1.1_1',[gid for gid,_,_ in jobs])

    def test_fresh_sync_process_preserves_marker_saved_by_previous_process(self):
        control=self.root/'_control';marker=control/'int16_uploaded.json'
        previous=['Day/a/old1.tif','Day/a/old2.tif']
        marker.write_text(json.dumps(previous))
        with patch.object(v,'_rclone',return_value=True):
            self.assertTrue(v.rclone_sync_once(final=True))
        self.assertEqual(set(json.loads(marker.read_text())),set(previous))
        self.assertEqual(v.REMOTE_INT16_TIFS,set(previous))

    def test_missing_csv_evidence_does_not_fake_completed_districts(self):
        gid=ROW['GID_2'];v.write_status(complete_state(gid));ctx=v.build_ctx(ROW)
        for period in v.PERIODS:
            rel=ctx['rel_day_dir']+'/'+v.day_name(ctx,period)
            v.REMOTE_TIFS.add(rel);v.REMOTE_INT16_TIFS.add(rel)
            v.REMOTE_TIFS.add(ctx['rel_night_dir']+'/'+v.night_name(ctx,period))
        with patch.object(v,'MODE','full'):
            states=v.load_all_status()
            self.assertFalse(v.district_complete(states[gid]))
            with self.assertRaisesRegex(RuntimeError,'tránh tự tải lại toàn bộ'):
                v.check_resume(pd.DataFrame([ROW]),states)

    def test_existing_tiffs_without_checkpoint_stop_before_download(self):
        v.REMOTE_TIFS.add('Day/a/file.tif')
        with self.assertRaisesRegex(RuntimeError,'không khôi phục'):
            v.check_resume(pd.DataFrame([ROW]),{})
        with patch.object(v,'ALLOW_FULL_RESTART',True):
            v.check_resume(pd.DataFrame([ROW]),{})

    def test_empty_new_folder_is_allowed(self):
        v.check_resume(pd.DataFrame([ROW]),{})

    def test_recovery_does_not_trust_missing_or_wrong_profile_records(self):
        state=complete_state();state['profile']='different-profile';v.write_status(state)
        v.REMOTE_TIFS.add('Day/a/file.tif')
        with patch.object(v,'RESTORE_INT16_MARKER',True):
            self.assertEqual(v.load_all_status(),{})
        self.assertEqual(v.REMOTE_INT16_TIFS,set())

    def test_marker_recovery_requires_matching_manifest_and_50m(self):
        for scale,manifest_exists,expected in [(50,True,True),(20,True,False),(50,False,False)]:
            with self.subTest(scale=scale,manifest_exists=manifest_exists):
                manifest={'schema':v.SCHEMA_ID,'period':v.PERIOD_ID,'profile':v.OUTPUT_PROFILE,
                          'level':2,'months':v.MONTH_KEYS}
                def command(args,**kwargs):
                    if args[1]=='cat' and args[2].endswith('pipeline.json'):
                        return SimpleNamespace(returncode=0 if manifest_exists else 3,
                                               stdout=json.dumps(manifest),stderr='' if manifest_exists else 'object not found')
                    if args[1]=='cat':
                        return SimpleNamespace(returncode=0,stdout='[]',stderr='')
                    return SimpleNamespace(returncode=0,stdout='',stderr='')
                with patch.multiple(v,DAY_IMAGE_SCALE=scale,CACHE_DIR=str(self.root/'cache')), \
                     patch.object(v.shutil,'which',return_value='/bin/rclone'), \
                     patch.object(v,'_rclone',return_value=True),patch.object(v.subprocess,'run',side_effect=command):
                    v.init_storage()
                self.assertEqual(v.RESTORE_INT16_MARKER,expected)


class DriveRequestTests(LocalCase):
    def test_quota_error_with_missing_exit_code_never_triggers_ee_download(self):
        ctx=v.build_ctx(ROW);ctx.update(convert_day_months=['2024-07'],geom=object())
        path=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,(2024,7))))
        rel=str(path.relative_to(self.root));v.REMOTE_TIFS.add(rel)
        quota=SimpleNamespace(returncode=3,stdout='',stderr='directory not found: drive.googleapis.com RATE_LIMIT_EXCEEDED rateLimitExceeded')
        with patch.object(v.subprocess,'run',return_value=quota) as command, \
             patch.object(v,'DRIVE_MAX_RETRIES',2),patch.object(v.time,'sleep'), \
             patch.object(v,'download_tif') as download:
            with self.assertRaisesRegex(RuntimeError,'quota'):
                v._download_month('day',ctx,v.PERIODS[0],None,str(path))
        self.assertEqual(command.call_count,2);download.assert_not_called()
        self.assertIn(rel,v.REMOTE_TIFS)

    def test_drive_quota_retries_with_exponential_backoff(self):
        limited=SimpleNamespace(returncode=1,stdout='',stderr='rateLimitExceeded')
        ok=SimpleNamespace(returncode=0,stdout='data',stderr='')
        with patch.object(v.subprocess,'run',side_effect=[limited,limited,ok]), \
             patch.object(v.random,'uniform',return_value=0),patch.object(v.time,'sleep') as sleep:
            result=v._run_rclone(['cat','gdrive:file'])
        self.assertIs(result,ok);self.assertEqual([c.args[0] for c in sleep.call_args_list],[5,10])

    def test_read_and_write_commands_all_receive_drive_rate_limits(self):
        ok=SimpleNamespace(returncode=0,stdout='',stderr='')
        with patch.object(v.subprocess,'run',return_value=ok) as command:
            for name in ('cat','copyto','lsf','about','move'):
                v._run_rclone([name,'gdrive:folder'])
        for call in command.call_args_list:
            args=call.args[0]
            self.assertEqual(args[args.index('--tpslimit')+1],str(v.DRIVE_TPS_LIMIT))
            self.assertEqual(args[args.index('--tpslimit-burst')+1],'1')
            self.assertEqual(args[args.index('--transfers')+1],str(v.DRIVE_TRANSFERS))

    def test_only_one_rclone_process_runs_at_a_time(self):
        active=0;peak=0;lock=threading.Lock()
        def command(*args,**kwargs):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            v.time.sleep(0.005)
            with lock:active-=1
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        with patch.object(v.subprocess,'run',side_effect=command),v.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _:v._run_rclone(['lsf','gdrive:folder']),range(12)))
        self.assertEqual(peak,1);self.assertEqual(active,0)

    def test_permission_error_does_not_retry_or_become_missing_file(self):
        denied=SimpleNamespace(returncode=3,stdout='',stderr='HTTP 403 permission denied')
        with patch.object(v.subprocess,'run',return_value=denied) as command,patch.object(v.time,'sleep') as sleep:
            self.assertIs(v._rclone(['copyto','gdrive:file','local'],missing_ok=True),False)
        command.assert_called_once();sleep.assert_not_called()


class SpeedTests(LocalCase):
    def test_speed_counts_only_fully_completed_districts(self):
        done=complete_state();partial=complete_state(URBAN['GID_2'])
        partial.update(status='partial');partial['t2']['2024-07']='no_data'
        states={ROW['GID_2']:done,URBAN['GID_2']:partial}
        jobs=[(row['GID_2'],row,'full') for row in (ROW,URBAN)]
        with patch.object(v,'process_district',side_effect=lambda row,prev:states[row['GID_2']]), \
             self.assertLogs(v.log,level='INFO') as logs:
            self.assertEqual(v.run_round(jobs,{}),'ok')
        summary=next(line for line in logs.output if '[speed]' in line)
        self.assertIn('1 huyện done mới',summary)
        self.assertIn('hàng đợi còn 1/2',summary)


class RestPolicyTests(LocalCase):
    def rows(self,n,province='VNM.1_1'):
        return [{**ROW,'GID_1':province,'GID_2':f'{province}.{i}'} for i in range(n)]

    def test_only_new_complete_districts_count_toward_ten(self):
        rows=self.rows(12);policy=v.DistrictRestPolicy(rows,{})
        for row in rows[:9]:
            self.assertEqual(policy.observe(row['GID_2'],complete_state(row['GID_2'])),[])
        gid=rows[9]['GID_2'];partial=complete_state(gid)
        partial.update(status='partial');partial['t2']['2024-07']='no_data'
        self.assertEqual(policy.observe(gid,partial),[])
        self.assertEqual(len(policy.observe(gid,complete_state(gid))),1)
        self.assertEqual(policy.observe(gid,complete_state(gid)),[])
        self.assertEqual(policy.new_done,10)

    def test_province_completion_uses_previous_done_districts(self):
        rows=self.rows(3)
        previous={row['GID_2']:complete_state(row['GID_2']) for row in rows[:2]}
        policy=v.DistrictRestPolicy(rows,previous)
        reasons=policy.observe(rows[2]['GID_2'],complete_state(rows[2]['GID_2']))
        self.assertEqual(policy.new_done,1)
        self.assertEqual(len(reasons),1);self.assertIn('tỉnh An Giang (3 huyện)',reasons[0])
        self.assertEqual(policy.observe(rows[2]['GID_2'],complete_state(rows[2]['GID_2'])),[])

    def test_province_rest_does_not_reset_ten_district_counter(self):
        rows=self.rows(4)+self.rows(7,'VNM.2_1');policy=v.DistrictRestPolicy(rows,{})
        for row in rows[:3]:policy.observe(row['GID_2'],complete_state(row['GID_2']))
        reasons=policy.observe(rows[3]['GID_2'],complete_state(rows[3]['GID_2']))
        self.assertEqual(len(reasons),1);self.assertIn('tỉnh',reasons[0])
        for row in rows[4:9]:self.assertEqual(policy.observe(row['GID_2'],complete_state(row['GID_2'])),[])
        reasons=policy.observe(rows[9]['GID_2'],complete_state(rows[9]['GID_2']))
        self.assertEqual(len(reasons),1);self.assertIn('10 huyện mới',reasons[0])

    def test_pilot_subset_does_not_imply_entire_province_finished(self):
        rows=self.rows(3);policy=v.DistrictRestPolicy(rows,{})
        self.assertEqual(policy.observe(rows[0]['GID_2'],complete_state(rows[0]['GID_2'])),[])
        self.assertEqual(policy.finished_provinces,set())

    def test_coincident_ten_and_province_milestones_pause_only_once(self):
        rows=self.rows(10);jobs=[(r['GID_2'],r,'full') for r in rows]
        policy=v.DistrictRestPolicy(rows,{});gate=Mock()
        with patch.multiple(v,REST_SEC=30,EE_SEM=gate), \
             patch.object(v,'process_district',side_effect=lambda row,prev:complete_state(row['GID_2'])):
            self.assertEqual(v.run_round(jobs,{},policy),'ok')
        gate.pause.assert_called_once()
        seconds,reason=gate.pause.call_args.args
        self.assertEqual(seconds,30);self.assertIn('10 huyện mới',reason);self.assertIn('tỉnh An Giang',reason)

    def test_counter_survives_retry_rounds_and_stop_interrupts_rest(self):
        rows=self.rows(3);policy=v.DistrictRestPolicy(rows,{});states={}
        def stop_in_rest(seconds,reason):v.request_stop('deadline');return False
        gate=Mock();gate.pause.side_effect=stop_in_rest
        with patch.multiple(v,REST_SEC=30,REST_EVERY_N=2,REST_AFTER_PROVINCE=False,EE_SEM=gate), \
             patch.object(v,'process_district',side_effect=lambda row,prev:complete_state(row['GID_2'])):
            self.assertEqual(v.run_round([(rows[0]['GID_2'],rows[0],'full')],states,policy),'ok')
            gate.pause.assert_not_called()
            self.assertEqual(v.run_round([(rows[1]['GID_2'],rows[1],'full')],states,policy),'stop')
        gate.pause.assert_called_once();self.assertEqual(policy.new_done,2)
        self.assertEqual(states[rows[1]['GID_2']]['status'],'done')

    def test_rest_can_be_disabled_without_changing_completed_status(self):
        rows=self.rows(1);policy=v.DistrictRestPolicy(rows,{});gate=Mock();states={}
        with patch.object(v,'EE_SEM',gate), \
             patch.object(v,'process_district',return_value=complete_state(rows[0]['GID_2'])):
            self.assertEqual(v.run_round([(rows[0]['GID_2'],rows[0],'full')],states,policy),'ok')
        gate.pause.assert_not_called();self.assertEqual(states[rows[0]['GID_2']]['status'],'done')
        with patch.multiple(v,REST_EVERY_N=0,REST_AFTER_PROVINCE=False):
            self.assertEqual(v.DistrictRestPolicy(rows,{}).observe(rows[0]['GID_2'],complete_state(rows[0]['GID_2'])),[])


class MainTests(LocalCase):
    def setUp(self):
        super().setUp();self.states={};self.rounds=[]
        values=dict(MODE='full',PREFLIGHT=False,MAX_RUNTIME_SEC=0,ADMIN_DF=None,
                    setup_logging=Mock(),init_earth_engine=Mock(),init_storage=Mock(),
                    build_admin_table=Mock(return_value=pd.DataFrame([ROW,URBAN])),
                    load_all_status=Mock(side_effect=lambda:self.states.copy()),install_signal_handlers=Mock(),
                    drive_stop_exists=Mock(return_value=False),Uploader=Mock(),
                    run_round=Mock(side_effect=self.finish),build_national_csv=Mock(),
                    rclone_sync_once=Mock(return_value=True))
        p=patch.multiple(v,**values);p.start();self.addCleanup(p.stop)

    def finish(self,jobs,statuses,rest_policy=None):
        self.rounds.append([gid for gid,_,_ in jobs])
        for gid,_,_ in jobs:self.states[gid]=complete_state(gid)
        return 'ok'

    def test_deadline_then_resume_processes_only_unfinished_districts(self):
        def deadline(jobs,statuses,rest_policy=None):
            self.finish(jobs[:1],statuses);v.request_stop('deadline');return 'stop'
        with patch.object(v,'run_round',side_effect=deadline):self.assertEqual(v.main(),3)
        v.STOP_EVENT.clear();v.STOP_REASON[0]=None
        self.assertEqual(v.main(),0)
        self.assertEqual(self.rounds,[[ROW['GID_2']],[URBAN['GID_2']]])

    def test_exhausted_missing_data_is_failure_not_success(self):
        state=complete_state();state['t2']['2025-01']='no_data';state.update(status='partial',attempts=3)
        self.states={ROW['GID_2']:state,URBAN['GID_2']:complete_state(URBAN['GID_2'])}
        self.assertEqual(v.main(),1);v.run_round.assert_not_called()

    def test_csv_repair_returns_success_for_valid_csv_without_claiming_tiffs_complete(self):
        state = complete_state()
        state.update(t2={}, t3img={}, status='partial')
        self.states = {ROW['GID_2']: state}
        with patch.multiple(v, CSV_REPAIR_ONLY=True, START_GID='55.8', REPAIR_GIDS=ROW['GID_2']):
            self.assertEqual(v.main(), 0)
        v.run_round.assert_not_called()
        report = pd.read_csv(self.root/'_control/progress_csv_repair.csv')
        self.assertEqual(list(report.GID_2), [ROW['GID_2']])
        self.assertTrue(report.iloc[0].csv_complete)
        self.assertEqual(report.iloc[0].status, 'partial')

    def test_csv_repair_missing_data_at_retry_limit_is_failure(self):
        state = complete_state()
        state.update(t1='missing', status='partial', attempts=v.MAX_ATTEMPTS)
        state['t1_by_month']['2024-07'] = 'no_data'
        with patch.multiple(v, CSV_REPAIR_ONLY=True, REPAIR_GIDS=ROW['GID_2']), patch.object(v, 'run_round') as run:
            def exhausted(jobs, statuses, rest_policy=None):
                self.states = {ROW['GID_2']: state}
                return 'ok'
            run.side_effect = exhausted
            self.assertEqual(v.main(), 1)

    def test_final_upload_failure_is_not_reported_as_success(self):
        self.states={r['GID_2']:complete_state(r['GID_2']) for r in [ROW,URBAN]}
        v.rclone_sync_once.return_value=False
        self.assertEqual(v.main(),1)

    def test_empty_pilot_verification_fails(self):
        with patch('sys.argv',['verify_pilot.py','--root',str(self.root)]):
            self.assertEqual(verify.main(),1)


class Int16UpgradeTests(LocalCase):
    def test_fast_day_download_and_verifier_use_50m_while_csv_stays_original(self):
        ctx=v.build_ctx(ROW);ctx.update(geom=object())
        path=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,(2024,7))))
        path.parent.mkdir(parents=True)
        def download(img,region,scale,target,label,writer,force_tiles):
            self.assertEqual(scale,50)
            writer(target,np.full((10,2,2),0.2,'float32'),from_origin(105,22,50/111319.49,50/111319.49),'EPSG:4326',np.nan,v.DAY_BANDS_ALL)
            return 1
        with patch.object(v,'DAY_IMAGE_SCALE',50),patch.object(v,'download_tif',side_effect=download):
            self.assertEqual(v._download_month('day',ctx,(2024,7),None,str(path)),(1,False))
        self.assertEqual(verify.check_tif(path,10,50)[0],'PASS')
        self.assertEqual(verify.check_tif(path,10,20)[0],'FAIL')

    def test_next_month_reuses_tile_hint_without_repeating_oversize_probe(self):
        ctx=v.build_ctx(ROW);ctx.update(geom=object())
        def download(img,region,scale,target,label,writer,force_tiles):
            Path(target).parent.mkdir(parents=True,exist_ok=True)
            writer(target,np.full((10,2,2),0.2,'float32'),from_origin(105,22,.001,.001),'EPSG:4326',np.nan,v.DAY_BANDS_ALL)
            return 4
        with patch.object(v,'download_tif',side_effect=download) as get:
            for period in [(2024,7),(2024,8)]:
                v._download_month('day',ctx,period,None,v.L(ctx['rel_day_dir'],v.day_name(ctx,period)))
        self.assertEqual(get.call_args_list[0].kwargs['force_tiles'],0)
        self.assertEqual(get.call_args_list[1].kwargs['force_tiles'],2)

    def test_quantization_preserves_scale_nodata_and_csv_precision(self):
        arr=np.array([[[0.123456, -0.201234], [np.nan, 0.0]]]*10, dtype='float32')
        source=self.root/'source.tif'; target=self.root/'target.tif'
        source.write_bytes(tif_bytes(arr,from_origin(105,22,20/111319.49,20/111319.49)))
        v.convert_day_file(str(source),str(target))
        with rasterio.open(target) as dst:
            self.assertEqual(dst.dtypes,('int16',)*10)
            self.assertEqual(dst.scales,(0.0001,)*10)
            self.assertEqual(dst.nodata,-32768)
            decoded=dst.read().astype(float)*dst.scales[0]
            valid=np.isfinite(arr)
            self.assertLessEqual(np.max(np.abs(decoded[valid]-arr[valid])),0.00005)
            self.assertEqual(dst.read()[0,1,0],-32768)
        props=day_props();props[0]['BLUE_mean']=0.123456789
        self.assertEqual(v.day_records(ROW,props)[0]['BLUE_mean'],0.123456789)
        self.assertEqual(verify.check_tif(target,10,20)[0],'PASS')

    def test_out_of_range_is_rejected_instead_of_silently_clipped(self):
        with self.assertRaisesRegex(RuntimeError,'ngoài miền Int16'):
            v.quantize_day(np.array([4.0]),None)
        self.assertEqual(v.quantize_day(np.array([np.inf,np.nan]),None).tolist(),[-32768,-32768])

    def test_tiled_int16_export_streams_mosaic_and_preserves_decoded_pixels(self):
        full=np.arange(10*4*4,dtype='float32').reshape(10,4,4)/1000
        res=20/111319.49
        tiles=[tif_bytes(full[:,r:r+2,c:c+2],from_origin(105+c*res,22-r*res,res,res))
               for r,c in [(0,0),(0,2),(2,0),(2,2)]]
        target=self.root/'tiled.tif'
        with patch.object(v,'fetch_geotiff_bytes',side_effect=tiles),patch.object(v,'_bbox',return_value=(105,21,106,22)), \
             patch.object(v,'_split_bbox',return_value=[1,2,3,4]),patch.object(v,'mosaic_tiles') as in_memory:
            self.assertEqual(v.download_tif(None,None,20,str(target),'test',writer=v.write_day_int16,force_tiles=2),4)
            in_memory.assert_not_called()
        with rasterio.open(target) as dst:
            np.testing.assert_allclose(dst.read()*dst.scales[0],full,atol=0.00005)
        self.assertEqual(verify.check_tif(target,10,20)[0],'PASS')

    def test_legacy_upgrade_reuses_night_and_schedules_day_conversion(self):
        old=complete_state();old.update(profile=v.LEGACY_FLOAT_PROFILE,attempts=3)
        upgraded=v.migrate_float_status(old)
        self.assertEqual(upgraded['profile'],v.OUTPUT_PROFILE)
        self.assertEqual(upgraded['attempts'],0)
        self.assertEqual(upgraded['t1'],'pending')
        self.assertEqual(set(upgraded['convert_day_months']),set(v.MONTH_KEYS))
        self.assertEqual(set(upgraded['t2'].values()),{'pending'})
        self.assertEqual(set(upgraded['t3img'].values()),{'ok'})
        self.assertEqual(old['profile'],v.LEGACY_FLOAT_PROFILE)
        self.assertTrue(v.part_current('night',{'_profile':v.LEGACY_FLOAT_PROFILE}))
        self.assertFalse(v.part_current('day',{'_profile':v.LEGACY_FLOAT_PROFILE}))

    def test_converts_existing_day_without_any_earth_engine_download(self):
        ctx=v.build_ctx(ROW);ctx['convert_day_months']=['2024-07']
        path=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,(2024,7))))
        path.parent.mkdir(parents=True)
        path.write_bytes(tif_bytes(np.full((10,3,3),0.123456,'float32'),from_origin(105,22,20/111319.49,20/111319.49)))
        with patch.object(v,'download_tif') as download:
            self.assertEqual(v._download_month('day',ctx,(2024,7),None,str(path)),(1,False))
            download.assert_not_called()
        self.assertEqual(verify.check_tif(path,10,20)[0],'PASS')

    def test_remote_conversion_uses_rclone_and_cleans_temporary_files(self):
        ctx=v.build_ctx(ROW);ctx['convert_day_months']=['2024-07']
        path=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,(2024,7))))
        v.REMOTE_TIFS.add(str(path.relative_to(self.root)))
        data=tif_bytes(np.full((10,2,2),0.2,'float32'),from_origin(105,22,20/111319.49,20/111319.49))
        def copy(args,**kwargs):
            self.assertEqual(args[0],'copyto');Path(args[2]).write_bytes(data);return True
        with patch.object(v,'_rclone',side_effect=copy),patch.object(v,'download_tif') as download:
            self.assertEqual(v._download_month('day',ctx,(2024,7),None,str(path)),(1,False))
            download.assert_not_called()
        self.assertFalse(Path(str(path)+'.source.part').exists())
        self.assertEqual(verify.check_tif(path,10,20)[0],'PASS')

    def test_missing_legacy_tiff_downloads_only_requested_month_from_ee(self):
        ctx=v.build_ctx(ROW);ctx.update(convert_day_months=['2024-07'],geom=object())
        path=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,(2024,7))))
        def download(img,region,scale,target,label,writer,force_tiles=0):
            self.assertEqual(scale,20);self.assertIn('2024-07',label)
            self.assertIs(writer,v.write_day_int16)
            writer(target,np.full((10,2,2),0.2,'float32'),from_origin(105,22,.001,.001),'EPSG:4326',np.nan,v.DAY_BANDS_ALL)
            return 1
        with patch.object(v,'_rclone') as copy,patch.object(v,'download_tif',side_effect=download) as get:
            self.assertEqual(v._download_month('day',ctx,(2024,7),None,str(path)),(1,False))
            copy.assert_not_called();self.assertEqual(get.call_count,1)

    def test_file_disappearing_after_listing_falls_back_and_removes_partial_copy(self):
        ctx=v.build_ctx(ROW);ctx.update(convert_day_months=['2024-07'],geom=object())
        path=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,(2024,7))))
        rel=str(path.relative_to(self.root));v.REMOTE_TIFS.add(rel)
        def missing(args,**kwargs):
            Path(args[2]).write_bytes(b'partial');self.assertTrue(kwargs['missing_ok']);return None
        def download(img,region,scale,target,label,writer,force_tiles=0):
            writer(target,np.full((10,2,2),0.2,'float32'),from_origin(105,22,.001,.001),'EPSG:4326',np.nan,v.DAY_BANDS_ALL)
            return 1
        with patch.object(v,'_rclone',side_effect=missing),patch.object(v,'download_tif',side_effect=download) as get:
            self.assertEqual(v._download_month('day',ctx,(2024,7),None,str(path)),(1,False))
            self.assertEqual(get.call_count,1)
        self.assertNotIn(rel,v.REMOTE_TIFS)
        self.assertFalse(Path(str(path)+'.source.part').exists())

    def test_copy_permission_failure_does_not_trigger_ee_redownload(self):
        ctx=v.build_ctx(ROW);ctx.update(convert_day_months=['2024-07'],geom=object())
        path=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,(2024,7))))
        v.REMOTE_TIFS.add(str(path.relative_to(self.root)))
        with patch.object(v,'_rclone',return_value=False),patch.object(v,'download_tif') as get:
            with self.assertRaisesRegex(RuntimeError,'quyền/token/kết nối'):
                v._download_month('day',ctx,(2024,7),None,str(path))
            get.assert_not_called()

    def test_existing_source_uses_actual_legacy_folder_and_filename(self):
        ctx=v.build_ctx(ROW);ctx['convert_day_months']=['2024-07']
        path=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,(2024,7))))
        legacy=f"Day/old_province/old_district/{ctx['safe_gid2']}_day_202407.tif"
        v.REMOTE_TIFS.add(legacy)
        data=tif_bytes(np.full((10,2,2),0.2,'float32'),from_origin(105,22,.001,.001))
        def copy(args,**kwargs):
            self.assertEqual(args[1],v.REMOTE_BASE+'/'+legacy)
            Path(args[2]).write_bytes(data);return True
        with patch.object(v,'_rclone',side_effect=copy),patch.object(v,'download_tif') as get:
            self.assertEqual(v._download_month('day',ctx,(2024,7),None,str(path)),(1,False))
            get.assert_not_called()

    def test_ambiguous_legacy_sources_are_not_guessed(self):
        ctx=v.build_ctx(ROW)
        for folder in ['old_a','old_b']:
            v.REMOTE_TIFS.add(f"Day/{folder}/{v.day_name(ctx,(2024,7))}")
        with self.assertRaisesRegex(RuntimeError,'Nhiều TIFF'):
            v.existing_day_source(ctx,(2024,7))

    def test_missing_conversion_is_cleared_and_exhausted_old_copy_errors_recover_once(self):
        state=complete_state();state.update(attempts=3,status='partial',convert_day_months=['2024-07'])
        state['t2']['2024-07']='fail'
        ctx=v.build_ctx(ROW)
        for period in v.PERIODS:
            if period != (2024,7):
                rel=ctx['rel_day_dir']+'/'+v.day_name(ctx,period)
                v.REMOTE_TIFS.add(rel);v.REMOTE_INT16_TIFS.add(rel)
            v.REMOTE_TIFS.add(ctx['rel_night_dir']+'/'+v.night_name(ctx,period))
        restored=v.reconcile_status(state)
        self.assertEqual(restored['convert_day_months'],[])
        self.assertEqual(restored['t2']['2024-07'],'pending')
        self.assertEqual(restored['attempts'],0)
        restored['attempts']=3
        again=v.reconcile_status(restored)
        self.assertEqual(again['attempts'],3);self.assertTrue(v.core_finished(again))

    def test_rclone_distinguishes_missing_object_from_other_failures(self):
        for code,error,expected in [(3,'directory not found',None),(4,'object not found',None),
                                    (1,"Source doesn't exist or is a directory and destination is a file",None),
                                    (1,'HTTP 401 token invalid',False),(0,'',True)]:
            with self.subTest(code=code),patch.object(v.subprocess,'run',return_value=SimpleNamespace(returncode=code,stderr=error)):
                self.assertIs(v._rclone(['copyto','source','target'],missing_ok=True,quiet=True),expected)

    def test_exhausted_old_path_errors_recover_when_actual_legacy_source_exists(self):
        state=complete_state();state.update(attempts=3,status='partial',convert_day_months=['2024-07'],
            errors=['day 2024-07: RuntimeError: Không tải được TIFF đã có để chuyển Int16: old'])
        state['t2']['2024-07']='fail'
        ctx=v.build_ctx(ROW)
        for period in v.PERIODS:
            if period != (2024,7):
                rel=ctx['rel_day_dir']+'/'+v.day_name(ctx,period)
                v.REMOTE_TIFS.add(rel);v.REMOTE_INT16_TIFS.add(rel)
            v.REMOTE_TIFS.add(ctx['rel_night_dir']+'/'+v.night_name(ctx,period))
        v.REMOTE_TIFS.add('Day/legacy/'+v.day_name(ctx,(2024,7)))
        restored=v.reconcile_status(state)
        self.assertEqual(restored['attempts'],0)
        self.assertEqual(restored['convert_day_months'],['2024-07'])
        restored['attempts']=3
        self.assertEqual(v.reconcile_status(restored)['attempts'],3)

    def test_partial_rclone_move_still_remembers_successfully_uploaded_file(self):
        ctx=v.build_ctx(ROW);path=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,(2024,7))))
        path.parent.mkdir(parents=True)
        v.write_day_int16(str(path),np.full((10,2,2),0.2,'float32'),from_origin(105,22,.001,.001),'EPSG:4326',np.nan,v.DAY_BANDS_ALL)
        rel=str(path.relative_to(self.root))
        def move(args,**kwargs):
            if args[0]=='move':
                snapshot=Path(args[args.index('--files-from')+1]).read_text()
                self.assertIn(path.name,snapshot)
                self.assertTrue(v._sync_lock.locked())
                path.unlink();return False
            return True
        with patch.object(v,'_rclone',side_effect=move):
            self.assertFalse(v.rclone_sync_once(final=True))
        self.assertIn(rel,v.REMOTE_TIFS)
        state=complete_state();state['attempts']=2
        for period in v.PERIODS:
            for folder,name in [('rel_day_dir',v.day_name),('rel_night_dir',v.night_name)]:
                v.REMOTE_TIFS.add(ctx[folder]+'/'+name(ctx,period))
        v.REMOTE_INT16_TIFS.update(v.REMOTE_TIFS)
        restored=v.reconcile_status(state)
        self.assertEqual(restored['attempts'],2)
        self.assertEqual(restored['t2']['2024-07'],'ok')

    def test_periodic_upload_filters_age_before_files_from_without_conflicting_flags(self):
        ctx=v.build_ctx(ROW)
        paths=[]
        for period in [(2024,7),(2024,8)]:
            path=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,period)))
            path.parent.mkdir(parents=True,exist_ok=True)
            v.write_day_int16(str(path),np.full((10,2,2),0.2,'float32'),from_origin(105,22,.001,.001),'EPSG:4326',np.nan,v.DAY_BANDS_ALL)
            paths.append(path)
        old,recent=paths
        timestamp=v.time.time()-180;os.utime(old,(timestamp,timestamp))
        moves=[]
        def upload(args,**kwargs):
            if args[0]=='move':
                moves.append(args)
                self.assertNotIn('--min-age',args);self.assertNotIn('--filter',args)
                listed=Path(args[args.index('--files-from')+1]).read_text().splitlines()
                self.assertEqual(listed,[str(old.relative_to(self.root/'Day'))])
                old.unlink()
            return True
        with patch.object(v,'_rclone',side_effect=upload):
            self.assertTrue(v.rclone_sync_once())
        self.assertEqual(len(moves),1);self.assertTrue(recent.is_file())
        self.assertIn(str(old.relative_to(self.root)),v.REMOTE_INT16_TIFS)

    def test_final_upload_includes_recent_files_without_conflicting_flags(self):
        ctx=v.build_ctx(ROW);path=Path(v.L(ctx['rel_day_dir'],v.day_name(ctx,(2024,7))))
        path.parent.mkdir(parents=True)
        v.write_day_int16(str(path),np.full((10,2,2),0.2,'float32'),from_origin(105,22,.001,.001),'EPSG:4326',np.nan,v.DAY_BANDS_ALL)
        moves=[]
        def upload(args,**kwargs):
            if args[0]=='move':
                self.assertNotIn('--min-age',args);self.assertNotIn('--filter',args)
                self.assertIn(path.name,Path(args[args.index('--files-from')+1]).read_text())
                moves.append(args);path.unlink()
            return True
        with patch.object(v,'_rclone',side_effect=upload):
            self.assertTrue(v.rclone_sync_once(final=True))
        self.assertEqual(len(moves),1);self.assertFalse(path.exists())

    def test_status_reconciliation_shares_upload_lock(self):
        v.write_status(complete_state())
        def reconcile(state,parts):
            self.assertTrue(v._sync_lock.locked());return state
        with patch.object(v,'reconcile_status',side_effect=reconcile):
            self.assertIn(ROW['GID_2'],v.load_all_status())

    def test_old_float_on_drive_is_not_mistaken_for_uploaded_int16(self):
        ctx=v.build_ctx(ROW)
        for period in v.PERIODS:
            v.REMOTE_TIFS.add(ctx['rel_day_dir']+'/'+v.day_name(ctx,period))
            v.REMOTE_TIFS.add(ctx['rel_night_dir']+'/'+v.night_name(ctx,period))
        state=complete_state();state['attempts']=2
        restored=v.reconcile_status(state)
        self.assertFalse(v.district_complete(restored))
        self.assertEqual(set(restored['convert_day_months']),set(v.MONTH_KEYS))
        v.REMOTE_INT16_TIFS.update(v.REMOTE_TIFS)
        self.assertTrue(v.district_complete(v.reconcile_status(state)))

    def test_missing_july_csv_retries_only_july_with_same_calendar_dates(self):
        calls=[];primary=day_props();primary[0]['BLUE_mean']=None
        fixed=day_props()[0];fixed.update({b+'_count':10 for b in v.DAY_BANDS_ALL})
        results=[{'features':[{'properties':p} for p in primary]},
                 {'scenes':3,'features':[{'properties':fixed}]}]
        with patch.object(v,'ee',fake_ee(calls)),patch.object(v,'ee_getinfo',side_effect=results) as query:
            records=v.task1_all_months(Node(calls))
        self.assertEqual(query.call_count,2)
        self.assertTrue(all(r['DATA_STATUS']=='ok' for r in v.day_records(ROW,records)))
        dates=[args for name,args,kw in calls if name=='filterDate']
        self.assertEqual(dates[-1],('2024-07-01','2024-08-01'))

    def test_no_valid_pixels_still_reports_missing_band_and_bounds_retries(self):
        props=day_props();props[0]['BLUE_mean']=None
        records=v.day_records(ROW,props)
        self.assertEqual(records[0]['DATA_STATUS'],'no_data')
        self.assertIn('BLUE',records[0]['ERROR'])
        state=complete_state();state.update(attempts=3,status='partial')
        state['t1_by_month']['2024-07']='no_data'
        self.assertTrue(v.core_finished(state));self.assertFalse(v.district_complete(state))


class RecoveryTests(LocalCase):
    def setUp(self):
        super().setUp()
        p=patch.multiple(v,RECOVER_DRIVE=True,MODE='full',REMOTE_MANIFEST_MATCHED=True)
        p.start();self.addCleanup(p.stop)

    def parts(self):
        v.append_parts('day',v.day_records(ROW,day_props()))
        night=night_records().fillna(0).to_dict('records')
        v.append_parts('night',night)

    def test_all_country_targets_prioritize_34_to_54_even_when_csv_flag_true(self):
        priority={**ROW,'GID_1':'VNM.34_1','GID_2':'VNM.34.1_1'}
        with patch.multiple(v,START_GID='VNM.55.8_1',CSV_REPAIR_ONLY=True):
            chosen=v.load_targets(pd.DataFrame([ROW,priority]))
            self.assertFalse(v.csv_repair_mode())
            self.assertEqual(v.progress_filename(),'progress_recovery.csv')
        self.assertEqual(list(chosen.GID_2),['VNM.34.1_1',ROW['GID_2']])

    def test_csv_evidence_does_not_mark_missing_tiffs_complete(self):
        self.parts();statuses={}
        v.restore_recovery_statuses(statuses)
        st=statuses[ROW['GID_2']]
        self.assertTrue(v.csv_complete(st));self.assertFalse(v.district_complete(st))
        self.assertEqual(st['status'],'partial')
        self.assertEqual(len(v.next_round_jobs([ROW['GID_2']],{ROW['GID_2']:ROW},statuses)),1)

    def test_marker_is_only_proof_if_file_still_exists_and_missing_attempts_reopen(self):
        self.parts();ctx=v.build_ctx(ROW)
        rel=f"{ctx['rel_day_dir']}/{v.day_name(ctx,v.PERIODS[0])}"
        v.REMOTE_INT16_TIFS.add(rel)
        statuses={ROW['GID_2']:{**complete_state(),'attempts':3}}
        v.restore_recovery_statuses(statuses)
        self.assertEqual(statuses[ROW['GID_2']]['t2']['2024-07'],'pending')
        self.assertEqual(statuses[ROW['GID_2']]['attempts'],0)
        v.REMOTE_TIFS.add(rel)
        v.restore_recovery_statuses(statuses)
        self.assertEqual(statuses[ROW['GID_2']]['t2']['2024-07'],'ok')

    def test_complete_district_not_queued_and_csv_not_recomputed(self):
        self.parts();ctx=v.build_ctx(ROW)
        for period in v.PERIODS:
            day=f"{ctx['rel_day_dir']}/{v.day_name(ctx,period)}"
            v.REMOTE_TIFS.update([day,f"{ctx['rel_night_dir']}/{v.night_name(ctx,period)}"])
            v.REMOTE_INT16_TIFS.add(day)
        statuses={ROW['GID_2']:complete_state()}
        v.restore_recovery_statuses(statuses)
        self.assertTrue(v.district_complete(statuses[ROW['GID_2']]))
        self.assertEqual(v.next_round_jobs([ROW['GID_2']],{ROW['GID_2']:ROW},statuses),[])

    def test_import_csv_preserves_existing_parts_rejects_no_data_and_duplicate_month(self):
        existing=v.day_records(ROW,day_props())[:1];existing[0]['BLUE_mean']=.99
        v.append_parts('day',existing)
        day=pd.DataFrame(v.day_records(ROW,day_props()),columns=v.DAY_COLUMNS)
        day.loc[1,'DATA_STATUS']='no_data'
        day=pd.concat([day,day.iloc[2:3]],ignore_index=True)
        night=night_records().fillna(0)
        def copy(args,**kwargs):
            (day if '/day_indices.csv' in args[1] else night).to_csv(args[2],index=False)
            return True
        with patch.object(v,'_rclone',side_effect=copy):v.import_recovery_csv()
        parts=v._read_parts('day')
        self.assertEqual(len(parts),10)
        self.assertEqual(parts[0]['BLUE_mean'],.99)
        self.assertEqual(len(v._read_parts('night')),12)

    def test_import_manifest_mismatch_or_drive_read_error_stops_instead_of_recomputing(self):
        with patch.object(v,'REMOTE_MANIFEST_MATCHED',False),patch.object(v,'_rclone') as command:
            with self.assertRaisesRegex(RuntimeError,'manifest'):v.import_recovery_csv()
            command.assert_not_called()
        with patch.object(v,'_rclone',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'API'):v.import_recovery_csv()
        self.assertEqual(v._read_parts('day'),[])

    def test_existing_night_tif_is_inspected_and_reused_without_ee_download(self):
        ctx=v.build_ctx(ROW);ctx['geom']=object()
        rel=f"{ctx['rel_night_dir']}/{v.night_name(ctx,v.PERIODS[0])}"
        v.REMOTE_TIFS.add(rel)
        def copy(args,**kwargs):
            v.write_tif(args[2],np.ones((2,2,2),'float64'),from_origin(105,22,.001,.001),'EPSG:4326',np.nan,['avg_rad','cf_cvg'])
            return True
        with patch.object(v,'_rclone',side_effect=copy),patch.object(v,'download_tif') as download:
            result=v._download_month('night',ctx,v.PERIODS[0],object(),v.L(rel))
        self.assertEqual(result,(1,False));download.assert_not_called()
        self.assertTrue(Path(v.L(rel)).is_file())

    def test_night_read_permission_error_never_causes_ee_redownload(self):
        ctx=v.build_ctx(ROW);ctx['geom']=object()
        rel=f"{ctx['rel_night_dir']}/{v.night_name(ctx,v.PERIODS[0])}"
        v.REMOTE_TIFS.add(rel)
        with patch.object(v,'_rclone',return_value=False),patch.object(v,'download_tif') as download:
            with self.assertRaisesRegex(RuntimeError,'Không đọc'):v._download_month('night',ctx,v.PERIODS[0],object(),v.L(rel))
        download.assert_not_called()

    def test_recovery_periodic_sync_builds_csv_before_upload_even_when_no_new_images(self):
        self.parts()
        with patch.object(v,'_copy_stable_directory',return_value=True) as copy,patch.object(v,'_rclone',return_value=True):
            self.assertTrue(v.rclone_sync_once())
        self.assertEqual([call.args[0] for call in copy.call_args_list],
                         [v.D_CONTROL,v.D_CSV,v.D_CSV,v.D_CONTROL])
        self.assertEqual(len(pd.read_csv(v.L(v.DAY_CSV))),12)
        self.assertEqual(len(pd.read_csv(v.L(v.NIGHT_CSV))),12)


if __name__=='__main__':
    unittest.main()
