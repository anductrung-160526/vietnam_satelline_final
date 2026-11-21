"""Bốn hàm của province_pipeline/common.py mà việc dựng ranh giới cần.

Chép nguyên văn, không sửa một dòng nào. Gói province_pipeline gốc dài 3.530 dòng và
common.py kéo theo cả drive, earth_engine, controller qua các import trong thân hàm;
nhánh này chỉ cần đọc danh mục tỉnh và ghi JSON nguyên tử, nên chép bốn hàm còn hơn
kéo cả gói vào một nhánh chỉ để chạy app.

provinces() đọc danh mục ở backend/core/ranh_gioi/config/provinces.json.
"""
import json
import os
from pathlib import Path


def _windows_fsync(fd):
    """Flush the writable kernel handle, without the Windows CRT _commit wrapper.

    Keep native errors visible: a disconnected or unwritable volume must never
    be treated as a successful checkpoint. HANDLE is pointer-sized on Win64.
    """
    import ctypes
    from ctypes import wintypes
    import msvcrt
    handle = msvcrt.get_osfhandle(fd)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    flush = kernel32.FlushFileBuffers
    flush.argtypes = [wintypes.HANDLE]
    flush.restype = wintypes.BOOL
    if not flush(wintypes.HANDLE(handle)):
        raise ctypes.WinError(ctypes.get_last_error())


def sync_file(stream):
    """Flush Python buffers and require an OS-level flush before publishing."""
    stream.flush()
    if os.name == 'nt':
        _windows_fsync(stream.fileno())
    else:
        os.fsync(stream.fileno())


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        sync_file(stream)
    temp.replace(path)


def provinces():
    path = Path(__file__).parent / 'config' / 'provinces.json'
    rows = json.loads(path.read_text(encoding='utf-8'))['provinces']
    assert len(rows) == len({r['ma_tinh'] for r in rows}) == 63
    assert [sum(r['group_id'] == i for r in rows) for i in range(10)] == [7]*3 + [6]*7
    return rows
