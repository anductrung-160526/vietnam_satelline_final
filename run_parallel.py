# -*- coding: utf-8 -*-
r"""
CHẠY SONG SONG NHIỀU TỈNH (cấp tỉnh).

Mặc định lưu vào E:\VNGIS_Data (nếu máy có ổ E). Mỗi tỉnh chạy trong một tiến trình riêng:
- ảnh .tif về cây thư mục chung, mỗi tỉnh một thư mục tên tỉnh, vd
  E:\VNGIS_Data\VN_NTL_Panel_2004_2025\raw_data\NTL\VIIRS\Hà Nội\VIIRS_01_2024_03.tif
- checkpoint, log, bảng tạm của từng tỉnh ở <output>/_tien_do_tinh/<mã>_<tên>/ (không ghi đè nhau)
Xong thì gộp bảng mọi tỉnh vào <output>/VN_*_Panel_2004_2025/data_processed/vietnam_province_*.csv.

    python run_parallel.py --workers 8 --years 2004-2025 --monthly --monthly-tif --tif night   # CSV ngày+đêm, ảnh đêm
    python run_parallel.py --workers 8 --years 2004-2025 --monthly --tif day                   # sau đó: ảnh ngày năm
    python run_parallel.py --workers 8 --years 2004-2025 --monthly --no-tif     # chỉ bảng CSV (nhanh nhất)
    python run_parallel.py --workers 8 --provinces "01,79,48" --years 2024      # chỉ vài tỉnh (mã hoặc tên)
    python run_parallel.py --merge-only                                         # chỉ gộp bảng đã có

Chạy lại đúng lệnh cũ để làm tiếp phần còn thiếu (mỗi tỉnh có checkpoint riêng).
"""
import os
import sys
import time
import argparse
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline_core.config import resolve_output_dir, NTL_PACKAGE, LANDCOVER_PACKAGE, DEFAULT_EE_PROJECT
from pipeline_core.admin_boundaries import load_province_boundaries, normalize_text
from pipeline_core.utils import export_multiformat_table
from run_pipeline import setup_directory_structure

REPO = Path(__file__).resolve().parent
PRINT_LOCK = threading.Lock()
WORK = "_tien_do_tinh"  # thư mục làm việc từng tỉnh (checkpoint, log, bảng tạm)


def say(msg):
    with PRINT_LOCK:
        print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def province_dir(base, row):
    code = row["ma_tinh_tk"] or normalize_text(row["ma_tinh"])
    return base / WORK / f"{code}_{normalize_text(row['ten_tinh'])}"


def run_one(row, base, args, passthrough):
    """Chạy run_pipeline.py cho 1 tỉnh; thử lại 1 lần nếu lỗi."""
    out = province_dir(base, row)
    out.mkdir(parents=True, exist_ok=True)
    key = row["ma_tinh_tk"] or row["ma_tinh"]
    cmd = [sys.executable, str(REPO / "run_pipeline.py"), "--level", "tinh", "--province", key,
           "--output-dir", str(out), "--tif-dir", str(base), "--cache-dir", str(base / "_cache"),
           "--min-free-gb", "0", *passthrough]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    for attempt in (1, 2):
        t0 = time.perf_counter()
        with open(out / "console.log", "a", encoding="utf-8") as log:
            log.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} lần {attempt}: {' '.join(cmd)}\n")
            log.flush()
            code = subprocess.call(cmd, cwd=REPO, stdout=log, stderr=subprocess.STDOUT, env=env)
        mins = (time.perf_counter() - t0) / 60
        if code == 0:
            return row["ten_tinh"], True, mins
        say(f"!! {row['ten_tinh']} lỗi (mã {code}) sau {mins:.0f} phút, xem {out / 'console.log'}"
            + (" -> thử lại" if attempt == 1 else ""))
    return row["ten_tinh"], False, mins


def merge_tables(base):
    """Gộp mọi bảng vietnam_province_*.csv của từng tỉnh thành bảng toàn quốc."""
    merged = []
    for pkg in (NTL_PACKAGE, LANDCOVER_PACKAGE):
        names = sorted({f.name for f in (base / WORK).glob(f"*/{pkg}/data_processed/vietnam_province_*.csv")})
        for name in names:
            parts = [pd.read_csv(f, dtype={"ma_tinh": str}, encoding="utf-8-sig")
                     for f in (base / WORK).glob(f"*/{pkg}/data_processed/{name}")]
            df = pd.concat(parts, ignore_index=True)
            sort = [c for c in ("ma_tinh", "nam", "ky", "thang") if c in df.columns]
            if "ky" in df.columns:
                df["_o"] = (df["ky"] == "Tháng").astype(int)
                df = df.sort_values(["ma_tinh", "nam", "_o", "thang"], na_position="first").drop(columns="_o")
            else:
                df = df.sort_values(sort)
            if "thang" in df.columns:
                df["thang"] = pd.to_numeric(df["thang"], errors="coerce").astype("Int64")
            target = base / pkg / "data_processed" / Path(name).stem
            export_multiformat_table(df.reset_index(drop=True), target)
            merged.append((target.with_suffix(".csv"), len(df), df["ma_tinh"].nunique()))
    for f, n, k in merged:
        say(f"Gộp: {f} ({n} dòng, {k} tỉnh)")
    return merged


def main(argv=None):
    p = argparse.ArgumentParser(description="Chạy song song nhiều tỉnh rồi gộp bảng toàn quốc")
    p.add_argument("--workers", type=int, default=8, help="Số tỉnh chạy cùng lúc (khuyên 6–10)")
    p.add_argument("--provinces", default="", help="Danh sách mã hoặc tên tỉnh, cách nhau dấu phẩy (mặc định 63 tỉnh)")
    p.add_argument("--output-dir", default="")
    p.add_argument("--merge-only", action="store_true")
    args, passthrough = p.parse_known_args(argv)

    base = resolve_output_dir(args.output_dir)
    if args.merge_only:
        merge_tables(base)
        return 0
    if not any(a.startswith("--ee-project") for a in passthrough):
        passthrough += ["--ee-project", DEFAULT_EE_PROJECT]

    setup_directory_structure(base)
    provinces = load_province_boundaries(base / "_cache")
    if args.provinces:
        wanted = [w.strip() for w in args.provinces.split(",") if w.strip()]
        keys = {normalize_text(w).replace("_", "") for w in wanted}
        provinces = provinces[provinces["ma_tinh_tk"].isin(wanted)
                              | provinces["ten_tinh"].apply(lambda n: normalize_text(n).replace("_", "")).isin(keys)]
    provinces = provinces.reset_index(drop=True)
    total = len(provinces)
    say(f"Bắt đầu {total} tỉnh, {args.workers} tiến trình song song. Tham số: {' '.join(passthrough)}")
    say(f"Ảnh .tif: {base}\\VN_*\\raw_data|data_intermediate\\...\\<Tên tỉnh>\\  |  "
        f"Log từng tỉnh: {base / WORK}\\<mã>_<tên>\\console.log")

    t0 = time.perf_counter()
    done, failed = [], []

    def task(row):
        say(f"-> bắt đầu {row['ten_tinh']}")
        name, ok, mins = run_one(row, base, args, passthrough)
        (done if ok else failed).append(name)
        elapsed = (time.perf_counter() - t0) / 3600
        n = len(done) + len(failed)
        eta = elapsed / n * (total - n) if n else 0
        say(f"{'OK ' if ok else 'LỖI'} {name} ({mins:.0f} phút) | xong {n}/{total} | đã chạy {elapsed:.1f} giờ"
            f" | còn khoảng {eta:.1f} giờ")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(task, [r for _, r in provinces.iterrows()]))

    merge_tables(base)
    say(f"Hoàn tất sau {(time.perf_counter() - t0) / 3600:.1f} giờ. Thành công {len(done)}/{total}.")
    if failed:
        say("Tỉnh lỗi (chạy lại đúng lệnh này để làm tiếp): " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
