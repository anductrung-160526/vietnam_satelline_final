"""Shared E:\\SatelliteData layout for six concurrent branches.

    <root>/VN_NTL_Panel_2004_2025/...        shared data package (plan section 3)
    <root>/VN_LandCover_Panel_2004_2025/...  shared data package
    <root>/_control/<NNN_NNN>/               private state, receipts, scratch, table parts

Images live in per-province folders and each province belongs to exactly one branch,
so branches never write the same image. Shared files (merged tables, logs, README)
are only written under a cross-process file lock.
"""
import contextlib
import os
import time
from datetime import datetime
from pathlib import Path
from province_pipeline.common import local_path
from province_pipeline.sources import NTL_PACKAGE,DAY_PACKAGE

PACKAGES=(NTL_PACKAGE,DAY_PACKAGE)
CONTROL='_control'
LEGACY='_legacy'
PACKAGE_DIRECTORIES={
    NTL_PACKAGE:('raw_data/NTL/DMSP','raw_data/NTL/VIIRS','data_intermediate','data_processed',
                 'metadata','code','dashboard','docs','logs'),
    DAY_PACKAGE:('raw_data/DAY/LANDSAT','raw_data/DAY/SENTINEL2','data_intermediate','data_processed',
                 'metadata','samples','code','dashboard','docs','logs'),
}
LOG_HEADER='Ngày cập nhật | Người thực hiện | Loại ảnh cập nhật | Nội dung chi tiết\n'


def branch_name(selection):
    return f"{selection['start']:03}_{selection['end']:03}"


def control_root(root,selection):
    return Path(root)/CONTROL/branch_name(selection)


def resolve(root,control,relative):
    """Package files live under the shared root; old per-job CSV staging under control."""
    if relative.split('/')[0] in PACKAGES:
        return local_path(root,relative)
    return local_path(control,relative)


def ensure_packages(root):
    for package,folders in PACKAGE_DIRECTORIES.items():
        for folder in folders:
            (Path(root)/package/folder).mkdir(parents=True,exist_ok=True)


@contextlib.contextmanager
def file_lock(path,timeout=600):
    """Blocking cross-process lock (released automatically if the process dies)."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        deadline=time.monotonic()+timeout
        while True:
            try:
                if os.name=='nt':
                    import msvcrt
                    stream.seek(0)
                    if path.stat().st_size==0:
                        stream.write(b'0');stream.flush();stream.seek(0)
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>deadline:raise TimeoutError('Shared file lock busy: '+str(path))
                time.sleep(0.2)
        try:
            yield
        finally:
            if os.name=='nt':
                import msvcrt
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream,fcntl.LOCK_UN)


def operator():
    return os.environ.get('SATELLITE_OPERATOR') or os.environ.get('USERNAME') or os.environ.get('USER') or 'unknown'


def append_log(root,package,image_type,content):
    """Plan section 5 log line: date | operator | image type | details."""
    log=Path(root)/package/'logs'/'nhat_ky_cap_nhat.txt'
    with file_lock(Path(root)/CONTROL/'.logs.lock'):
        log.parent.mkdir(parents=True,exist_ok=True)
        new=not log.exists()
        with log.open('a',encoding='utf-8') as stream:
            if new:stream.write(LOG_HEADER)
            stream.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {operator()} | {image_type} | {content}\n")
