"""Retain conditional deletion when v3 omits an HTTP ETag; never delete unguarded."""
import copy
import unittest
from unittest.mock import Mock
from province_pipeline.drive import Drive


class V2DeleteGuardTests(unittest.TestCase):
    def adapter(self):
        d=Drive.__new__(Drive);d.api=Mock();d._v2_api=Mock()
        expected=dict(id='file',name='tile.tif',version='7',size='123',md5Checksum='md5',parents=['province'])
        current=dict(expected,_etag=None)
        d.metadata=Mock(side_effect=lambda i:copy.deepcopy(current) if i=='file' else dict(id='province',name='01_ha_noi',parents=['root']))
        snapshot=dict(id='file',title='tile.tif',version='7',fileSize='123',md5Checksum='md5',
                      parents=[{'id':'province'}],etag='"v2-strong-etag"')
        d._v2_api.files.return_value.get.return_value.execute.return_value=snapshot
        delete=d._v2_api.files.return_value.delete.return_value;delete.headers={}
        return d,expected,snapshot,delete

    def test_fallback_uses_v2_etag_and_deletes_exact_id_via_v2(self):
        d,f,s,req=self.adapter();d.delete_verified(f,'root')
        d.api.files.return_value.delete.assert_not_called()
        d._v2_api.files.return_value.delete.assert_called_once_with(fileId='file',supportsAllDrives=True)
        self.assertEqual(req.headers['If-Match'],'"v2-strong-etag"')
        req.execute.assert_called_once()

    def test_no_etag_in_either_api_still_blocks_deletion(self):
        d,f,s,req=self.adapter();s.pop('etag')
        with self.assertRaisesRegex(RuntimeError,'conditional delete support'):d.delete_verified(f,'root')
        req.execute.assert_not_called()

    def test_v2_content_version_parent_and_name_must_all_match(self):
        for key,value in [('id','other'),('version','8'),('fileSize','124'),('md5Checksum','different'),
                          ('parents',[{'id':'elsewhere'}]),('title','different.tif')]:
            with self.subTest(key=key):
                d,f,s,req=self.adapter();s[key]=value
                with self.assertRaisesRegex(RuntimeError,'changed'):d.delete_verified(f,'root')
                req.execute.assert_not_called()

    def test_race_between_metadata_reads_blocks_delete(self):
        d,f,s,req=self.adapter()
        d.metadata=Mock(side_effect=[dict(f,_etag=None),dict(name='01_ha_noi',parents=['root']),dict(f,version='8')])
        with self.assertRaisesRegex(RuntimeError,'changed'):d.delete_verified(f,'root')
        req.execute.assert_not_called()

    def test_server_precondition_failure_propagates_without_unconditional_retry(self):
        d,f,s,req=self.adapter();req.execute.side_effect=RuntimeError('HTTP 412')
        with self.assertRaisesRegex(RuntimeError,'412'):d.delete_verified(f,'root')
        req.execute.assert_called_once()
        d.api.files.return_value.delete.assert_not_called()

    def test_ancestry_failure_is_separate_and_never_uses_fallback(self):
        d,f,s,req=self.adapter()
        d.metadata=Mock(side_effect=[dict(f,_etag=None),dict(name='01_ha_noi',parents=[])])
        with self.assertRaisesRegex(RuntimeError,'staging ancestry'):d.delete_verified(f,'root')
        d._v2_api.files.assert_not_called()
        req.execute.assert_not_called()


if __name__=='__main__':unittest.main()
