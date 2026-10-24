"""Verified store-and-forward receiver. Remote deletion is opt-in and file-ID scoped."""
import contextlib
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from .common import atomic_json, audit, local_path
from .projection import same_crs


def hashes(path):
    md5, sha = hashlib.md5(), hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            md5.update(block)
            sha.update(block)
    return md5.hexdigest(), sha.hexdigest()


def windows_serial(anchor):
    if os.name != 'nt':
        raise RuntimeError('Disk enrollment/receiver must run on the Windows computer with the external drive')
    import ctypes
    from ctypes import wintypes
    fn = ctypes.windll.kernel32.GetVolumeInformationW
    fn.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
                   ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                   ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD]
    fn.restype = wintypes.BOOL
    serial = wintypes.DWORD()
    ok = fn(str(anchor), None, 0,
            ctypes.byref(serial), None, None, None, 0)
    if not ok:
        raise OSError('Unable to identify external volume')
    return str(serial.value)


def enroll(root):
    root = Path(root).absolute()
    anchor = Path(root.anchor)
    if not root.is_absolute() or not anchor.exists():
        raise ValueError('External drive is absent')
    serial = windows_serial(anchor)
    marker = anchor / '.satellite-volume.json'
    if marker.exists():
        data = json.loads(marker.read_text(encoding='utf-8'))
        if data['serial'] != serial:
            raise ValueError('Existing marker belongs to another volume')
    else:
        data = {'token': str(uuid.uuid4()), 'serial': serial}
        atomic_json(marker, data)
    root.mkdir(parents=True, exist_ok=True)
    return data['token']


def verify_volume(config):
    root = Path(config['local_root']).absolute()
    marker = Path(root.anchor) / '.satellite-volume.json'
    if not config.get('volume_marker') or not marker.is_file():
        raise RuntimeError('External volume not enrolled/connected; receiver paused')
    data = json.loads(marker.read_text(encoding='utf-8'))
    if data.get('token') != config['volume_marker'] or data.get('serial') != windows_serial(root.anchor):
        raise RuntimeError('Wrong external disk; receiver paused')
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError('Local root missing or unsafe')
    return root


@contextlib.contextmanager
def single_receiver(root):
    """OS lock is released on process exit; no stale PID lock removal needed."""
    lock = root / '.receiver.lock'
    with lock.open('a+b') as stream:
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            if lock.stat().st_size == 0:
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def validate(path, file, job):
    if path.stat().st_size != int(file['size']):
        raise ValueError('Downloaded size mismatch')
    md5, sha = hashes(path)
    if not file.get('md5Checksum') or md5 != file['md5Checksum']:
        raise ValueError('Downloaded MD5 mismatch')
    if job['kind'] == 'image':
        import rasterio
        from affine import Affine
        with rasterio.open(path) as ds:
            if not same_crs(ds.crs,job['crs']) or ds.count != len(job['bands']) or ds.nodata != -9999:
                raise ValueError('TIFF CRS/bands/nodata mismatch')
            if ds.width != ds.height or ds.width * job['scale'] != job['tile']['bounds'][2]-job['tile']['bounds'][0]:
                raise ValueError('TIFF dimensions do not match bounded tile')
            if not ds.transform.almost_equals(Affine(*job['tile']['transform'])):
                raise ValueError('TIFF grid mismatch')
            if any(t != 'float32' for t in ds.dtypes):
                raise ValueError('TIFF dtype mismatch')
            for band in range(1, ds.count+1):
                for _, window in ds.block_windows(band):
                    ds.read(band, window=window)  # Decode every block, not just the header.
    else:
        import pandas as pd
        frame = pd.read_csv(path, dtype={'ma_tinh': str, 'period': str, 'job_id': str})
        required = {'ma_tinh','nam','period','job_id','valid_area','total_area'}
        if len(frame) != 1 or not required <= set(frame.columns):
            raise ValueError('Statistics CSV schema mismatch')
        row = frame.iloc[0]
        if row['ma_tinh'] != job['province']['ma_tinh'] or row['period'] != job['period'] or row['job_id'] != job['job_id']:
            raise ValueError('Statistics CSV identity mismatch')
    return sha


def _not_found(error):
    return getattr(getattr(error, 'resp', None), 'status', None) == 404


def receive_manifest(config, drive, folders, manifest, root, dry_run=False):
    from .layout import local_manifest
    manifest=local_manifest(manifest)
    job = manifest['job']
    jid = manifest['job_id']
    if jid != job['job_id']:
        raise ValueError('Manifest job identity mismatch')
    receipt_dir = root / '.receipts'
    receipt_path = receipt_dir / (jid+'.json')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else dict(
        job_id=jid, volume_marker=config['volume_marker'], files=[], remote_deleted=False)
    if receipt.get('volume_marker') != config['volume_marker']:
        raise ValueError('Receipt belongs to another disk')
    previous = {f['id']: f for f in receipt['files']}
    verified = []
    for f in manifest['files']:
        dest = local_path(root, f['local_relative_path'])
        if dry_run:
            audit('would_receive', job_id=jid, file_id=f['id'], destination=str(dest))
            continue
        if dest.exists():
            sha = validate(dest, f, job)
        else:
            # An explicit Drive organization may change the local target. Reuse a
            # verified old copy by same-volume rename; never overwrite or redownload it.
            legacy=list(f.get('legacy_local_relative_paths',[]))
            if f['id'] in previous and previous[f['id']].get('local_relative_path'):
                legacy.append(previous[f['id']]['local_relative_path'])
            for relative in legacy:
                old_path=local_path(root,relative)
                if old_path!=dest and old_path.is_file():
                    sha=validate(old_path,f,job)
                    if f['id'] in previous and previous[f['id']]['sha256']!=sha:
                        raise ValueError('Legacy copy differs from its receipt')
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    old_path.rename(dest)
                    break
            if dest.exists():
                sha=validate(dest,f,job)
            elif f['id'] in previous:
                raise RuntimeError('Previously received file missing locally; do not delete source')
            else:
                sha=None
            if sha is not None:
                old=previous.get(f['id'],{})
                verified.append(dict(id=f['id'],verified=True,sha256=sha,md5Checksum=f['md5Checksum'],
                    size=f['size'],version=f['version'],local_relative_path=f['local_relative_path'],
                    deleted=old.get('deleted',False)))
                continue
            current = drive.metadata(f['id'])
            for key in ('size', 'md5Checksum', 'version', 'parents'):
                if current.get(key) != f.get(key):
                    raise ValueError('Remote source changed since manifest publication')
            reserve = max(256*1024**2, int(f['size'])//10)
            if shutil.disk_usage(root).free < int(f['size']) + reserve:
                raise RuntimeError('External disk full; receiver paused')
            dest.parent.mkdir(parents=True, exist_ok=True)
            part = dest.with_suffix(dest.suffix+'.part')
            drive.download(f['id'], part)
            sha = validate(part, f, job)
            part.replace(dest)
        old = previous.get(f['id'], {})
        if old and old.get('sha256') != sha:
            raise ValueError('Local receipt hash mismatch')
        verified.append(dict(id=f['id'], verified=True, sha256=sha, md5Checksum=f['md5Checksum'],
                             size=f['size'], version=f['version'], local_relative_path=f['local_relative_path'],
                             deleted=old.get('deleted', False)))
    if dry_run:
        return
    receipt['files'] = verified
    atomic_json(receipt_path, receipt)
    # Retain manifests beside receipts to allow revalidation and audit after remote removal.
    atomic_json(root / '.manifests' / (jid+'.json'), manifest)
    remote_name = jid+'.json'
    drive.write_json(folders['receipts'], remote_name, receipt)
    confirmation = drive.read_json(folders['receipts'], remote_name)
    if confirmation != receipt:
        raise RuntimeError('Remote receipt persistence not confirmed; deletion blocked')
    if not config.get('allow_remote_delete', False):
        audit('local_verified_kept_remote', job_id=jid)
        return
    for item, f in zip(receipt['files'], manifest['files']):
        # Verify the same volume and bytes again immediately before irreversible deletion.
        verify_volume(config)
        dest = local_path(root, f['local_relative_path'])
        if validate(dest, f, job) != item['sha256']:
            raise ValueError('Local file changed before cleanup')
        if item['deleted']:
            continue
        try:
            current = drive.metadata(f['id'])
        except Exception as error:
            if not _not_found(error):
                raise
            # Only this path has an already-persisted verified receipt. It may be a resumed delete.
            item['deleted'] = True
        else:
            expected = dict(f)
            drive.delete_verified(expected, config['drive_root_id'])
            item['deleted'] = True
        atomic_json(receipt_path, receipt)
        drive.write_json(folders['receipts'], remote_name, receipt)
    receipt['remote_deleted'] = all(f['deleted'] for f in receipt['files'])
    atomic_json(receipt_path, receipt)
    drive.write_json(folders['receipts'], remote_name, receipt)
    audit('received', job_id=jid, remote_deleted=receipt['remote_deleted'])


def failure_reason(error):
    """Only constant reason codes leave the exception boundary, never raw API bodies."""
    status=getattr(getattr(error,'resp',None),'status',None)
    if status in (403,404,412,429):
        return {403:'DRIVE_PERMISSION_DENIED',404:'REMOTE_FILE_NOT_FOUND',
                412:'REMOTE_FILE_CHANGED',429:'DRIVE_RATE_LIMIT'}[status]
    message=str(error).lower()
    for phrase,code in [('conditional delete support','DELETE_GUARD_UNAVAILABLE'),
                        ('checksum','DATA_CHECKSUM_MISMATCH'),('md5','DATA_CHECKSUM_MISMATCH'),
                        ('receipt','RECEIPT_VERIFICATION_FAILED'),('wrong external disk','WRONG_DISK'),
                        ('disk full','LOCAL_DISK_FULL'),('source changed','REMOTE_FILE_CHANGED')]:
        if phrase in message:
            return code
    return 'RECEIVE_ERROR'


def run(config, drive, dry_run=False):
    from .controller import control_folders
    root = verify_volume(config)
    with single_receiver(root):
        folders = control_folders(drive, config['drive_root_id'])
        state = drive.read_json(folders['root'], 'state.json', {'jobs': {}})
        from collections import Counter
        counts=dict(Counter(j['status'] for j in state['jobs'].values()))
        audit('receiver_summary',total_jobs=sum(counts.values()),status_counts=counts,
              ready_jobs=counts.get('REMOTE_READY',0),dry_run=dry_run)
        if not counts.get('REMOTE_READY',0):
            audit('receiver_waiting',reason='NO_REMOTE_READY',next_step='Run GitHub mode reconcile_only to finalize worker reports')
        failures = []
        for job in state['jobs'].values():
            if job['status'] != 'REMOTE_READY':
                continue
            manifest = drive.read_json(folders['manifests'], job['job_id']+'.json')
            if not manifest:
                raise RuntimeError('REMOTE_READY missing manifest')
            try:
                receive_manifest(config, drive, folders, manifest, root, dry_run)
            except Exception as error:
                audit('receive_failed', job_id=job['job_id'], error_type=type(error).__name__,
                      error_code=failure_reason(error))
                failures.append(job['job_id'])
        if failures:
            raise RuntimeError(f'{len(failures)} batches failed; sources retained for retry')
