"""Run locally, never in Actions. Creates an authorized-user file with refresh token."""
import argparse
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', required=True, help='Google Desktop OAuth client JSON')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    dest = Path(args.output)
    if dest.exists():
        raise ValueError('Refusing to overwrite an existing credentials file')
    flow = InstalledAppFlow.from_client_secrets_file(args.client, scopes=[
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/earthengine',
        'https://www.googleapis.com/auth/cloud-platform'])
    credentials = flow.run_local_server(port=0, access_type='offline', prompt='consent')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('x', encoding='utf-8') as stream:
        stream.write(credentials.to_json())
    dest.chmod(0o600)
    print('Credentials saved locally. Keep private; never commit or paste into chat.')


if __name__ == '__main__':
    main()
