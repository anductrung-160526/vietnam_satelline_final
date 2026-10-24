"""Failure diagnostics cannot leak raw credential/API exception content."""
import unittest
from types import SimpleNamespace
from province_pipeline.receiver import failure_reason


class ReceiverErrorTests(unittest.TestCase):
    def test_diagnostic_is_static_even_with_sensitive_error_content(self):
        for text,code in [('Cannot prove staging ancestry or conditional delete support','DELETE_GUARD_UNAVAILABLE'),
                          ('Downloaded MD5 mismatch','DATA_CHECKSUM_MISMATCH'),
                          ('Remote receipt persistence not confirmed','RECEIPT_VERIFICATION_FAILED'),
                          ('External disk full','LOCAL_DISK_FULL'),
                          ('other failure','RECEIVE_ERROR')]:
            result=failure_reason(RuntimeError(text+' SECRET_MUST_NOT_APPEAR'))
            self.assertEqual(result,code)
            self.assertNotIn('SECRET_MUST_NOT_APPEAR',result)

    def test_http_condition_failures_are_distinct(self):
        for status,code in [(403,'DRIVE_PERMISSION_DENIED'),(404,'REMOTE_FILE_NOT_FOUND'),
                            (412,'REMOTE_FILE_CHANGED'),(429,'DRIVE_RATE_LIMIT')]:
            error=RuntimeError('DO_NOT_ECHO_API_RESPONSE');error.resp=SimpleNamespace(status=status)
            self.assertEqual(failure_reason(error),code)


if __name__=='__main__':unittest.main()
