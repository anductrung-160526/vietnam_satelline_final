"""Drive API adapter: IDs, pagination, exact parent/name lookup, bounded requests."""
import io
import json
from .common import retry

FOLDER = 'application/vnd.google-apps.folder'
FIELDS = 'id,name,mimeType,size,md5Checksum,version,parents,trashed,appProperties'


def credentials(path):
    from google.auth import load_credentials_from_file
    creds, _ = load_credentials_from_file(path, scopes=[
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/earthengine',
        'https://www.googleapis.com/auth/cloud-platform'])
    return creds


class Drive:
    def __init__(self, creds):
        from googleapiclient.discovery import build
        self.api = build('drive', 'v3', credentials=creds, cache_discovery=False)

    def execute(self, req):
        return retry(req.execute)

    def metadata(self, file_id):
        req = self.api.files().get(fileId=file_id, fields=FIELDS, supportsAllDrives=True)
        original = req.postproc
        headers = {}

        def capture(resp, content):
            headers.update(resp)
            return original(resp, content)
        req.postproc = capture
        result = self.execute(req)
        result['_etag'] = headers.get('etag')
        return result

    def children(self, parent):
        token = None
        while True:
            data = self.execute(self.api.files().list(
                q=f"'{parent}' in parents and trashed = false", spaces='drive',
                pageToken=token, pageSize=1000, fields=f'nextPageToken,files({FIELDS})',
                supportsAllDrives=True, includeItemsFromAllDrives=True))
            yield from data.get('files', [])
            token = data.get('nextPageToken')
            if not token:
                break

    def find(self, parent, name):
        found = [f for f in self.children(parent) if f['name'] == name]
        if len(found) > 1:
            raise RuntimeError(f'Ambiguous Drive filename under {parent}: {name}')
        return found[0] if found else None

    def folder(self, parent, name):
        found = self.find(parent, name)
        if found:
            if found['mimeType'] != FOLDER:
                raise RuntimeError('Expected folder')
            return found['id']
        result = self.execute(self.api.files().create(body={
            'name': name, 'mimeType': FOLDER, 'parents': [parent]}, fields='id', supportsAllDrives=True))
        return result['id']

    def assert_unique_folder_name(self, name, folder_id):
        # Export.toDrive resolves a NAME over the account, not a path or folder ID.
        safe = name.replace("'", "\\'")
        data = self.execute(self.api.files().list(
            q=f"name = '{safe}' and mimeType = '{FOLDER}' and trashed = false",
            fields='nextPageToken,files(id)', supportsAllDrives=True, includeItemsFromAllDrives=True))
        if data.get('nextPageToken') or [f['id'] for f in data.get('files', [])] != [folder_id]:
            raise RuntimeError('Earth Engine export folder name is not unique/visible')

    def read_bytes(self, file_id):
        return self.execute(self.api.files().get_media(fileId=file_id, supportsAllDrives=True))

    def read_json(self, parent, name, default=None):
        item = self.find(parent, name)
        return json.loads(self.read_bytes(item['id'])) if item else default

    def write_json(self, parent, name, value):
        from googleapiclient.http import MediaIoBaseUpload
        content = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype='application/json', resumable=False)
        found = self.find(parent, name)
        if found:
            req = self.api.files().update(fileId=found['id'], media_body=media, fields='id', supportsAllDrives=True)
        else:
            req = self.api.files().create(body={'name': name, 'parents': [parent]},
                                          media_body=media, fields='id', supportsAllDrives=True)
        return self.execute(req)['id']

    def upload_verified(self, parent, path):
        """Unique job folder + checksummed upload; reconcile a lost response without duplicates."""
        from googleapiclient.http import MediaFileUpload
        from .receiver import hashes
        expected_md5 = hashes(path)[0]
        found = self.find(parent, path.name)
        if found:
            if found.get('md5Checksum') == expected_md5 and int(found.get('size', 0)) == path.stat().st_size:
                return found['id']
            raise RuntimeError('Upload destination already contains different data; refusing overwrite')
        req = self.api.files().create(body={'name':path.name,'parents':[parent]},
            media_body=MediaFileUpload(str(path),resumable=True), fields=FIELDS, supportsAllDrives=True)
        result = None
        # Media upload retries only the current resumable session, not files.create.
        while result is None:
            _, result = retry(req.next_chunk)
        if result.get('md5Checksum') != expected_md5 or int(result.get('size',0)) != path.stat().st_size:
            raise RuntimeError('Uploaded Drive file checksum mismatch')
        return result['id']

    def download(self, file_id, path):
        from googleapiclient.http import MediaIoBaseDownload
        with path.open('wb') as stream:
            dl = MediaIoBaseDownload(stream, self.api.files().get_media(
                fileId=file_id, supportsAllDrives=True), chunksize=8*1024*1024)
            done = False
            while not done:
                _, done = retry(dl.next_chunk)
            stream.flush()
            import os
            os.fsync(stream.fileno())

    def usage(self, root):
        total = 0
        for f in self.children(root):
            total += self.usage(f['id']) if f['mimeType'] == FOLDER else int(f.get('size', 0))
        return total

    def account_free(self):
        quota = self.execute(self.api.about().get(fields='storageQuota'))['storageQuota']
        if 'limit' not in quota or 'usage' not in quota:
            raise RuntimeError('Account quota unknown (e.g. Shared Drive): configure a supported account; refusing exports')
        return max(0, int(quota['limit']) - int(quota['usage']))

    def delete_verified(self, expected, root):
        current = self.metadata(expected['id'])
        for key in ('version', 'md5Checksum', 'size', 'parents'):
            if current.get(key) != expected.get(key):
                raise RuntimeError('Source changed since verification; deletion blocked')
        # Walk parents by ID. Never delete control metadata or outside staging.
        parent = current.get('parents', [])
        visited = set()
        while parent and parent[0] != root:
            pid = parent[0]
            if pid in visited:
                raise RuntimeError('Drive ancestry cycle')
            visited.add(pid)
            node = self.metadata(pid)
            if node['name'] == '_control':
                raise RuntimeError('Control files must never be deleted')
            parent = node.get('parents', [])
        if parent != [root] or not current.get('_etag'):
            raise RuntimeError('Cannot prove staging ancestry or conditional delete support')
        req = self.api.files().delete(fileId=current['id'], supportsAllDrives=True)
        req.headers['If-Match'] = current['_etag']
        # No retry of destructive requests with an unknown outcome.
        req.execute()
