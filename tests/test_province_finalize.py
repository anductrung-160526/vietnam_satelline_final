"""Worker-to-receiver handoff: no extra exports, READY only after verified upload."""
import copy
import unittest
from unittest.mock import patch
from province_pipeline.controller import reconcile_existing
from test_province_pipeline import FakeDrive


class FinalizeTests(unittest.TestCase):
    def fixture(self):
        d=FakeDrive();d.folder=lambda parent,name:parent+'/'+name
        j=dict(job_id='j',status='RESERVED',export_backend='direct',attempt=1,layout_version=3,
               kind='image',prefix='01_ha_noi_tile',folder_id='data',reserved_bytes=100,
               local_directory='package/raw_data/DAY/LANDSAT/01_ha_noi')
        state=dict(jobs={'j':j},inventory={},cursor=0)
        d.documents['root/_control','state.json']=copy.deepcopy(state)
        return d,dict(drive_root_id='root',export_backend='direct')

    def test_uploaded_reserved_job_becomes_ready_without_admitting_new_jobs(self):
        d,c=self.fixture()
        d.documents['root/_control/reports','j-a1.json']=dict(status='UPLOADED',file_id='f',md5Checksum='md5')
        d.files['f']=dict(id='f',name='01_ha_noi_tile.tif',parents=['data'],mimeType='image/tiff',
                         size='10',md5Checksum='md5',version='1')
        with patch('province_pipeline.controller.admit') as admit:
            counts=reconcile_existing(c,d)
        admit.assert_not_called()
        self.assertEqual(counts,{'REMOTE_READY':1})
        self.assertEqual(len(d.documents['root/_control','state.json']['jobs']),1)
        manifest=d.documents['root/_control/manifests','j.json']
        self.assertEqual(manifest['files'][0]['id'],'f')
        self.assertLess(d.events.index(('write','root/_control/manifests')),d.events.index(('write','root/_control')))
        self.assertEqual(reconcile_existing(c,d),{'REMOTE_READY':1})

    def test_no_upload_report_never_fabricates_ready(self):
        d,c=self.fixture()
        self.assertEqual(reconcile_existing(c,d),{'RESERVED':1})
        self.assertNotIn(('root/_control/manifests','j.json'),d.documents)

    def test_missing_remote_file_is_not_marked_ready(self):
        d,c=self.fixture()
        d.documents['root/_control/reports','j-a1.json']=dict(status='UPLOADED',file_id='f',md5Checksum='md5')
        self.assertEqual(reconcile_existing(c,d),{'RUNNING':1})
        self.assertNotIn(('root/_control/manifests','j.json'),d.documents)

    def test_conflicting_checksum_is_blocked(self):
        d,c=self.fixture()
        d.documents['root/_control/reports','j-a1.json']=dict(status='UPLOADED',file_id='f',md5Checksum='md5')
        d.files['f']=dict(id='f',name='01_ha_noi_tile.tif',parents=['data'],mimeType='image/tiff',size='10',md5Checksum='other')
        self.assertEqual(reconcile_existing(c,d),{'BLOCKED_OUTPUT':1})

    def test_missing_state_does_not_overwrite_it_with_empty_state(self):
        d,c=self.fixture();d.documents.clear()
        with self.assertRaisesRegex(RuntimeError,'No pipeline state'):reconcile_existing(c,d)
        self.assertFalse(d.events)

    def test_inflight_organization_cannot_be_overwritten(self):
        d,c=self.fixture();d.documents['root/_control','state.json']['jobs']['j']['status']='MIGRATING'
        with self.assertRaisesRegex(RuntimeError,'organize_only'):reconcile_existing(c,d)
        self.assertFalse(d.events)


if __name__=='__main__':unittest.main()
