"""Allowlisted error codes and structural config status only; never echo rclone output."""
import configparser
import json
from pathlib import Path

MESSAGES = {
    'RCLONE_REMOTE_NOT_FOUND': 'Selected remote is absent; set PROVINCE_RCLONE_REMOTE to the existing Drive remote name.',
    'RCLONE_CONFIG_FORMAT': 'RCLONE_CONF must be a complete rclone INI configuration with a [remote] section, not a token/JSON alone.',
    'RCLONE_CONFIG_ENCRYPTED': 'Rclone config is encrypted; provide its password securely to rclone or use a dedicated usable config.',
    'RCLONE_TOKEN_REVOKED': 'Google rejected the refresh token (invalid_grant); reconnect this remote locally, then update RCLONE_CONF securely.',
    'RCLONE_CLIENT_REJECTED': 'Google rejected the OAuth client; check the existing client configuration before reconnecting.',
    'RCLONE_TOKEN_MISSING': 'The Drive remote has no usable OAuth token; authorize it locally and update RCLONE_CONF securely.',
    'RCLONE_SCOPE_DENIED': 'Drive OAuth scopes are insufficient; authorize the required Drive access.',
    'RCLONE_DRIVE_API_DISABLED': 'Drive API is disabled or blocked for the OAuth client project; enable/check that project.',
    'RCLONE_RATE_LIMIT': 'Drive returned a rate/quota limit; retain credentials and retry after investigating quota.',
    'RCLONE_PERMISSION_DENIED': 'Drive denied the request; check account permissions/scopes; this does not prove token expiry.',
    'RCLONE_NETWORK': 'Network/DNS/TLS failed; retain credentials and check connectivity/trust.',
    'RCLONE_UNSUPPORTED_COMMAND': 'Installed rclone does not support the requested command/flag; inspect the logged version.',
    'RCLONE_EXECUTABLE_NOT_FOUND': 'Rclone executable was not found; install rclone or configure its executable path.',
    'RCLONE_TIMEOUT': 'Rclone did not finish within 120 seconds; inspect connectivity before changing credentials.',
    'RCLONE_EXECUTION_FAILED': 'Rclone could not be started; check executable permissions and configuration.',
    'RCLONE_INVALID_JSON': 'Rclone returned unexpected output; raw stdout is withheld to protect credentials.',
    'RCLONE_UNKNOWN': 'Rclone failed for an unclassified reason; inspect the command locally without sharing tokens/config contents.',
}


class RcloneFailure(RuntimeError):
    def __init__(self, code, returncode=None):
        self.code = code
        self.returncode = returncode
        suffix = f' (exit {returncode})' if returncode is not None else ''
        super().__init__(f'[{code}]{suffix} {MESSAGES[code]} Raw command output withheld.')


def classify(output):
    """Match known signatures to constant codes; no substring of input is returned."""
    text=output.lower()
    signatures = [
        ('RCLONE_REMOTE_NOT_FOUND', ('didn\'t find section', 'section not found', 'couldn\'t find section')),
        ('RCLONE_CONFIG_ENCRYPTED', ('encrypted configuration', 'configuration is encrypted', 'incorrect password', 'unable to decrypt')),
        ('RCLONE_CONFIG_FORMAT', ('failed to load config file', 'couldn\'t load config', 'could not load config', 'ini:','key-value delimiter not found')),
        ('RCLONE_CLIENT_REJECTED', ('invalid_client', 'unauthorized_client', 'deleted_client', 'client authentication failed')),
        ('RCLONE_TOKEN_REVOKED', ('invalid_grant', 'token has been expired or revoked', 'token has expired or been revoked')),
        ('RCLONE_TOKEN_MISSING', ('empty token', 'token is empty', 'no token found', 'missing refresh token', 'failed to get token')),
        ('RCLONE_DRIVE_API_DISABLED', ('accessnotconfigured','servicedisabled','api has not been used','api is disabled')),
        ('RCLONE_SCOPE_DENIED', ('insufficient authentication scopes','insufficientpermissions','insufficient_scope')),
        ('RCLONE_RATE_LIMIT', ('ratelimitexceeded','userratelimitexceeded','dailylimitexceeded','quotaexceeded','error 429')),
        ('RCLONE_UNSUPPORTED_COMMAND', ('unknown command','unknown flag','flag provided but not defined')),
        ('RCLONE_NETWORK', ('no such host','dial tcp','tls handshake','x509:','certificate verify','connection refused','i/o timeout')),
        ('RCLONE_PERMISSION_DENIED', ('error 403','status code 403','permission denied','access denied','forbidden')),
    ]
    for code, terms in signatures:
        if any(term in text for term in terms):
            return code
    return 'RCLONE_UNKNOWN'


def inspect_config(path, selected):
    """Read option names/status, never report values, account names, tokens or section names."""
    try:
        content=Path(path).read_text(encoding='utf-8-sig')
    except (OSError,UnicodeError):
        raise RcloneFailure('RCLONE_CONFIG_FORMAT') from None
    if content.lstrip().startswith('RCLONE_ENCRYPT_V'):
        return dict(format='encrypted',selected_remote_present='unknown')
    parser=configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(content)
    except configparser.Error:
        # ConfigParser exception text can contain the entire offending secret line.
        raise RcloneFailure('RCLONE_CONFIG_FORMAT') from None
    present=parser.has_section(selected)
    drives=sum(parser.get(s,'type',fallback='')=='drive' for s in parser.sections())
    result=dict(format='ini',selected_remote_present=present,drive_remote_count=drives)
    if present:
        remote=parser[selected]
        result['selected_type_is_drive']=remote.get('type')=='drive'
        result['oauth_client']='custom' if remote.get('client_id','').strip() else 'rclone_default'
        token=remote.get('token','').strip()
        if not token:
            result['token']='missing'
        else:
            try:
                parsed=json.loads(token)
                result['token']='json' if isinstance(parsed,dict) else 'wrong_type'
            except ValueError:
                result['token']='malformed_json'
    return result
