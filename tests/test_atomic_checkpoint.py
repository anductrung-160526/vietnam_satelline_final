"""Durable checkpoint publication; Windows kernel flushing is mocked on Linux."""
import ctypes
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from province_pipeline.common import atomic_json, sync_file, _windows_fsync


class CheckpointTests(unittest.TestCase):
    def test_windows_uses_native_flush_before_replacing_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json';path.write_text('{"old": true}')
            def flush(fd):
                self.assertEqual(json.loads(path.read_text()),{'old': True})
                # Python buffers have been flushed; the old state stays published.
                self.assertEqual(json.loads(path.with_suffix('.json.tmp').read_text()),{'new': True})
            with patch('province_pipeline.common.os',SimpleNamespace(name='nt')),patch('province_pipeline.common._windows_fsync',side_effect=flush) as native:
                atomic_json(path,{'new': True})
            native.assert_called_once()
            self.assertEqual(json.loads(path.read_text()),{'new': True})
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_native_failure_preserves_previous_checkpoint_and_is_not_swallowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json';path.write_text('{"old": true}')
            with patch('province_pipeline.common.os',SimpleNamespace(name='nt')),patch('province_pipeline.common._windows_fsync',side_effect=OSError('disk unavailable')):
                with self.assertRaisesRegex(OSError,'disk unavailable'):
                    atomic_json(path,{'new': True})
            self.assertEqual(json.loads(path.read_text()),{'old': True})

    def test_posix_still_requires_fsync(self):
        stream=Mock();stream.fileno.return_value=7
        fsync=Mock()
        with patch('province_pipeline.common.os',SimpleNamespace(name='posix',fsync=fsync)):
            sync_file(stream)
        stream.flush.assert_called_once();fsync.assert_called_once_with(7)

    def test_windows_flush_preserves_64_bit_handle_and_propagates_native_error(self):
        handle=2**40+123
        flush=Mock(return_value=1);dll=SimpleNamespace(FlushFileBuffers=flush)
        with patch.dict('sys.modules',msvcrt=SimpleNamespace(get_osfhandle=Mock(return_value=handle))),patch.object(ctypes,'WinDLL',return_value=dll,create=True),patch.object(ctypes,'get_last_error',return_value=1117,create=True),patch.object(ctypes,'WinError',side_effect=lambda code:OSError(code,'native disk error'),create=True):
            _windows_fsync(7)
            self.assertEqual(flush.call_args.args[0].value,handle)
            flush.return_value=0
            with self.assertRaisesRegex(OSError,'native disk error'):
                _windows_fsync(7)
