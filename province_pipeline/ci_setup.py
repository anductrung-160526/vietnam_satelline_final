"""Materialize existing legacy GitHub Secrets locally; output paths only, never values."""
import json
import os
from pathlib import Path


def prepare(environment=os.environ):
    out=Path('.province-local')
    out.mkdir(exist_ok=True)
    try:
        config=json.loads(environment['PROVINCE_CONFIG_JSON'])
        key=json.loads(environment['EE_SERVICE_ACCOUNT_JSON'])
    except (KeyError,ValueError):
        raise ValueError('Set PROVINCE_CONFIG_JSON variable and existing EE_SERVICE_ACCOUNT_JSON secret') from None
    if key.get('type') != 'service_account' or not all(key.get(k) for k in ('client_email','private_key','token_uri')):
        raise ValueError('EE_SERVICE_ACCOUNT_JSON must contain a service-account key')
    conf=environment.get('RCLONE_CONF','')
    if not conf.strip():
        raise ValueError('Existing RCLONE_CONF secret is missing or empty')
    # Legacy service-account EE identity cannot export to a user's personal My Drive.
    config['export_backend']='direct'
    (out/'config.json').write_text(json.dumps(config),encoding='utf-8')
    private=Path(environment['RUNNER_TEMP'])/'province-auth'
    private.mkdir(mode=0o700,exist_ok=True)
    for name,value in [('ee-key.json',json.dumps(key)),('rclone.conf',conf)]:
        path=private/name
        path.write_text(value,encoding='utf-8')
        path.chmod(0o600)
    remote=environment.get('PROVINCE_RCLONE_REMOTE') or 'gdrive'
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]+',remote):
        raise ValueError('Invalid PROVINCE_RCLONE_REMOTE')
    with open(environment['GITHUB_ENV'],'a',encoding='utf-8') as stream:
        stream.write('PROVINCE_EE_CREDENTIALS='+str((private/'ee-key.json').absolute())+'\n')
        stream.write('PROVINCE_RCLONE_CONFIG='+str((private/'rclone.conf').absolute())+'\n')
        stream.write('PROVINCE_RCLONE_REMOTE='+remote+'\n')


if __name__ == '__main__':
    prepare()
