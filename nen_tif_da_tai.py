# -*- coding: utf-8 -*-
"""
Nén KHÔNG MẤT DỮ LIỆU các ảnh .tif đã tải trước đây (DEFLATE + predictor), giá trị pixel giữ nguyên.

    python nen_tif_da_tai.py                       # mặc định C:\\VNGIS_Data
    python nen_tif_da_tai.py --output-dir D:\\VNGIS_Data
"""
import sys
import argparse
from pathlib import Path

from pipeline_core.config import resolve_output_dir
from pipeline_core.ee_utils import compress_tif


def main(argv=None):
    p = argparse.ArgumentParser(description="Nén không mất dữ liệu các ảnh .tif đã tải")
    p.add_argument("--output-dir", default="")
    args = p.parse_args(argv)
    root = resolve_output_dir(args.output_dir)
    files = [f for f in root.rglob("*.tif") if "_cache" not in f.parts]
    before = after = 0
    for i, f in enumerate(files, 1):
        b = f.stat().st_size
        compress_tif(f)
        a = f.stat().st_size
        before, after = before + b, after + a
        if i % 50 == 0 or i == len(files):
            print(f"[{i}/{len(files)}] {before / 1024 ** 2:.1f} MB -> {after / 1024 ** 2:.1f} MB")
    if files:
        print(f"[✓] Tiết kiệm {(before - after) / 1024 ** 2:.1f} MB ({(1 - after / before) * 100:.0f}%)")
    else:
        print(f"Không có tệp .tif trong {root}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
