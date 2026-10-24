"""Separate EE service-account and Drive/rclone identities; never log secret content."""
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from google.auth.credentials import Credentials


class RcloneCredentials(Credentials):
    """Let rclone refresh its own built-in/custom OAuth client, then use the token in Drive API.

    No embedded rclone client secret, token printing, or secret recovery from GitHub.
    A local rclone config is required on Windows independently of GitHub Secrets.
    """
    def __init__(self, config_path, remote='gdrive', executable='rclone'):
        super().__init__()
        self.config_path = str(Path(config_path).absolute())
        self.remote = remote
        self.executable = executable
        if not Path(self.config_path).is_file():
            raise ValueError('Rclone configuration file not found')
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]+', remote):
            raise ValueError('Invalid rclone remote name')
        self.refresh(None)

    def _run(self, args):
        try:
            result = subprocess.run([self.executable, '--config', self.config_path,
                '--log-level', 'ERROR', *args], capture_output=True, text=True,
                encoding='utf-8', timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError('Cannot execute rclone; install it and check the configured path') from None
        if result.returncode:
            raise RuntimeError('Rclone authentication failed; check the remote and reconnect locally if required')
        try:
            return json.loads(result.stdout)
        except ValueError:
            raise RuntimeError('Rclone returned invalid JSON; check configuration locally') from None

    def refresh(self, request):
        # A read-only operation makes rclone refresh/write its token using its own OAuth client.
        self._run(['about', self.remote+':', '--json'])
        data = self._run(['config', 'dump'])
        remote = data.get(self.remote, {})
        if remote.get('type') != 'drive':
            raise ValueError('Selected rclone remote must be a Google Drive remote')
        token = remote.get('token')
        try:
            token = json.loads(token) if isinstance(token, str) else token
            access = token['access_token']
            expiry = datetime.fromisoformat(token['expiry'].replace('Z','+00:00'))
        except (TypeError, KeyError, ValueError):
            raise ValueError('Rclone OAuth token or expiry is missing; reconnect the remote locally') from None
        if not access or expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError('Rclone access token is empty/expired after refresh')
        self.token = access
        # google-auth expects a naive UTC datetime for expiry.
        self.expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)


def drive_credentials():
    path = os.environ.get('PROVINCE_RCLONE_CONFIG')
    if path:
        return RcloneCredentials(path, os.environ.get('PROVINCE_RCLONE_REMOTE','gdrive'),
                                 os.environ.get('PROVINCE_RCLONE_EXECUTABLE','rclone'))
    path = os.environ.get('PROVINCE_GOOGLE_CREDENTIALS')
    if path:
        from .drive import credentials
        return credentials(path)
    raise ValueError('Set PROVINCE_RCLONE_CONFIG to a local rclone config (or PROVINCE_GOOGLE_CREDENTIALS)')


def ee_credentials():
    path = os.environ.get('PROVINCE_EE_CREDENTIALS')
    if path:
        from google.oauth2.service_account import Credentials as ServiceAccount
        return ServiceAccount.from_service_account_file(path, scopes=[
            'https://www.googleapis.com/auth/earthengine',
            'https://www.googleapis.com/auth/cloud-platform'])
    path = os.environ.get('PROVINCE_GOOGLE_CREDENTIALS')
    if path:
        from .drive import credentials
        return credentials(path)
    raise ValueError('Set PROVINCE_EE_CREDENTIALS to the EE service-account file; Drive-only commands do not need it')
