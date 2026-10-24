"""Diagnostics must identify failure classes without ever echoing untrusted output."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from province_pipeline.rclone_diagnostics import classify,inspect_config,RcloneFailure
from province_pipeline.auth import RcloneCredentials


class DiagnosisTests(unittest.TestCase):
    def test_classification_returns_only_static_code(self):
        cases={
            "didn't find section in config file":'RCLONE_REMOTE_NOT_FOUND',
            'oauth2: cannot fetch token invalid_grant Token has been expired or revoked':'RCLONE_TOKEN_REVOKED',
            'invalid_client Client authentication failed':'RCLONE_CLIENT_REJECTED',
            'googleapi Error 403 insufficientPermissions':'RCLONE_SCOPE_DENIED',
            'accessNotConfigured API has not been used':'RCLONE_DRIVE_API_DISABLED',
            'userRateLimitExceeded':'RCLONE_RATE_LIMIT',
            'dial tcp no such host':'RCLONE_NETWORK',
            'unknown flag: --json':'RCLONE_UNSUPPORTED_COMMAND',
            'Failed to load config file: key-value delimiter not found':'RCLONE_CONFIG_FORMAT',
            'googleapi Error 403 Forbidden':'RCLONE_PERMISSION_DENIED',
            'unrecognized failure':'RCLONE_UNKNOWN',
        }
        for text,expected in cases.items():
            with self.subTest(expected=expected):
                code=classify(text+' DO_NOT_ECHO_TOKEN')
                self.assertEqual(code,expected)
                self.assertNotIn('DO_NOT_ECHO_TOKEN',str(RcloneFailure(code,1)))

    def test_only_presence_and_type_not_values_in_config_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'rclone.conf'
            p.write_text('[gdrive]\ntype = drive\nclient_id = DO_NOT_ECHO_ID\nclient_secret = DO_NOT_ECHO_SECRET\n'
                         'token = '+json.dumps(dict(access_token='DO_NOT_ECHO_TOKEN'))+'\n',encoding='utf-8-sig')
            info=inspect_config(p,'gdrive')
            self.assertEqual(info['token'],'json')
            self.assertEqual(info['oauth_client'],'custom')
            self.assertEqual(info['drive_remote_count'],1)
            self.assertNotIn('DO_NOT_ECHO',json.dumps(info))

    def test_parse_error_never_echoes_secret_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'config';p.write_text('DO_NOT_ECHO_TOKEN')
            with self.assertRaises(RcloneFailure) as ctx: inspect_config(p,'gdrive')
            self.assertEqual(ctx.exception.code,'RCLONE_CONFIG_FORMAT')
            self.assertNotIn('DO_NOT_ECHO_TOKEN',str(ctx.exception))

    def test_missing_remote_fails_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'config';p.write_text('[mydrive]\ntype = drive\n')
            with patch('province_pipeline.auth.subprocess.run') as run:
                with self.assertRaises(RcloneFailure) as ctx: RcloneCredentials(p,'gdrive')
            self.assertEqual(ctx.exception.code,'RCLONE_REMOTE_NOT_FOUND')
            run.assert_not_called()

    def test_stderr_classified_without_echo_or_secret_in_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'config';p.write_text('[gdrive]\ntype = drive\n')
            result=SimpleNamespace(returncode=1,stdout='DO_NOT_ECHO_TOKEN',stderr='invalid_grant DO_NOT_ECHO_SECRET')
            with patch('province_pipeline.auth.subprocess.run',return_value=result),self.assertLogs('province',level='INFO') as logs:
                with self.assertRaises(RcloneFailure) as ctx: RcloneCredentials(p)
            self.assertEqual(ctx.exception.code,'RCLONE_TOKEN_REVOKED')
            self.assertNotIn('DO_NOT_ECHO',' '.join(logs.output)+str(ctx.exception))

    def test_timeouts_distinct_from_auth_rejection(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'config';p.write_text('[gdrive]\ntype = drive\n')
            with patch('province_pipeline.auth.subprocess.run',side_effect=subprocess.TimeoutExpired('rclone',120)):
                with self.assertRaises(RcloneFailure) as ctx: RcloneCredentials(p)
            self.assertEqual(ctx.exception.code,'RCLONE_TIMEOUT')


if __name__=='__main__': unittest.main()
