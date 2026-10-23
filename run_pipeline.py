# -*- coding: utf-8 -*-
"""
TRÌNH ĐIỀU PHỐI TRUNG TÂM (MASTER PIPELINE RUNNER)
Thu thập, tiền xử lý, xử lý dữ liệu viễn thám CẤP HUYỆN tại Việt Nam (2004–2025).

- Đầu ra mặc định: C:\\VNGIS_Data (Windows), đổi bằng --output-dir hoặc biến môi trường OUTPUT_ROOT
- Tự tạo cấu trúc 2 gói dữ liệu VN_NTL_Panel_2004_2025 và VN_LandCover_Panel_2004_2025
- Ánh sáng ban đêm (DMSP/VIIRS) và lớp phủ ảnh ban ngày (Landsat/Sentinel-2, phân lớp theo ngưỡng, không ML)
- Bảng .csv/.xlsx/.dta + ảnh .tif theo từng huyện; chạy tiếp được khi bị ngắt (checkpoint)

Ví dụ:
    python run_pipeline.py --province "Hà Nội" --years 2024
    python run_pipeline.py --mode full --years 2004-2025 --monthly --monthly-tif
"""
import sys
import time
import shutil
import argparse
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pipeline_core.config import (START_YEAR, END_YEAR, NTL_PACKAGE, LANDCOVER_PACKAGE, DEFAULT_EE_PROJECT,
                                  resolve_output_dir)
from pipeline_core.admin_boundaries import load_district_boundaries, filter_districts, get_pilot_districts
from pipeline_core.codebook_gen import generate_codebooks
from pipeline_core.samples_gen import generate_sample_dataset
from pipeline_core.utils import StepTimer, check_disk_space

REPO_DIR = Path(__file__).resolve().parent
PACKAGE_DIRS = {
    NTL_PACKAGE: ["raw_data/NTL/DMSP", "raw_data/NTL/VIIRS", "data_intermediate", "data_processed",
                  "metadata", "code", "dashboard", "docs", "logs"],
    LANDCOVER_PACKAGE: ["raw_data/DAY/LANDSAT", "raw_data/DAY/SENTINEL2", "data_intermediate", "data_processed",
                        "metadata", "samples", "code", "dashboard", "docs", "logs"],
}


def setup_directory_structure(output_dir):
    """Tạo cây thư mục 2 gói dữ liệu, chép README/code/docs, sinh codebook và bộ điểm mẫu."""
    output_dir = Path(output_dir).resolve()
    print(f"[*] Thư mục dữ liệu: {output_dir}")
    for pkg, subdirs in PACKAGE_DIRS.items():
        for sub in subdirs:
            (output_dir / pkg / sub).mkdir(parents=True, exist_ok=True)
        src = REPO_DIR / pkg
        if src.exists() and src.resolve() != (output_dir / pkg).resolve():
            for item in src.iterdir():
                if item.is_file() and item.suffix in (".md",):
                    shutil.copy2(item, output_dir / pkg / item.name)
                elif item.is_dir() and item.name in ("code", "docs"):
                    shutil.copytree(item, output_dir / pkg / item.name, dirs_exist_ok=True,
                                    ignore=shutil.ignore_patterns("__pycache__"))
    generate_codebooks(output_dir)
    generate_sample_dataset(output_dir / LANDCOVER_PACKAGE / "samples")
    return output_dir


def parse_years(text, start=START_YEAR, end=END_YEAR):
    """'2024' | '2010-2015' | '2004,2010,2024' -> danh sách năm."""
    if not text:
        return list(range(start, end + 1))
    years = set()
    for part in str(text).split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            years.update(range(int(a), int(b) + 1))
        elif part:
            years.add(int(part))
    bad = [y for y in years if y < START_YEAR or y > END_YEAR + 5]
    if bad:
        raise ValueError(f"Năm không hợp lệ: {bad}")
    return sorted(years)


def build_parser():
    p = argparse.ArgumentParser(description="Pipeline dữ liệu viễn thám cấp huyện Việt Nam (2004–2025)")
    p.add_argument("--output-dir", default="", help="Thư mục gốc lưu dữ liệu (mặc định C:\\VNGIS_Data)")
    p.add_argument("--pipeline", choices=["all", "ntl", "landcover", "init-only"], default="all")
    p.add_argument("--province", default="", help='Lọc theo tỉnh, vd "Hà Nội" (nhiều tỉnh cách nhau dấu phẩy)')
    p.add_argument("--districts", default="", help="Lọc theo tên/mã huyện, cách nhau dấu phẩy")
    p.add_argument("--mode", choices=["pilot", "full"], default="full",
                   help="full: mọi huyện sau khi lọc; pilot: chỉ lấy --pilot-n huyện đầu")
    p.add_argument("--pilot-n", type=int, default=3)
    p.add_argument("--years", default="", help="Năm cần chạy: 2024 | 2010-2015 | 2004,2024 (mặc định 2004-2025)")
    p.add_argument("--start-year", type=int, default=START_YEAR)
    p.add_argument("--end-year", type=int, default=END_YEAR)
    p.add_argument("--monthly", action="store_true",
                   help="Lấy thêm dữ liệu 12 tháng cho nguồn có ảnh tháng: VIIRS, Landsat, Sentinel-2 (DMSP chỉ có năm)")
    p.add_argument("--monthly-tif", action="store_true", help="Tải thêm ảnh .tif từng tháng (cần --monthly)")
    p.add_argument("--day-sensors", default="landsat,sentinel2", help="landsat,sentinel2 | landsat | sentinel2")
    p.add_argument("--no-tif", action="store_true", help="Chỉ tính bảng số liệu, không tải ảnh .tif")
    p.add_argument("--no-accuracy", action="store_true", help="Bỏ qua đánh giá độ chính xác phân lớp")
    p.add_argument("--ee-project", default=DEFAULT_EE_PROJECT, help="Google Cloud Project ID đã đăng ký GEE")
    p.add_argument("--min-free-gb", type=float, default=5.0, help="Cảnh báo nếu ổ đĩa còn trống ít hơn (GB)")
    return p


def select_districts(args, cache_dir):
    df = load_district_boundaries(cache_dir)
    df = filter_districts(df, province=args.province or None, districts=args.districts or None)
    if df.empty:
        raise SystemExit(f"[!] Không tìm thấy huyện nào khớp --province '{args.province}' "
                         f"--districts '{args.districts}'")
    if args.mode == "pilot":
        df = get_pilot_districts(df, n=args.pilot_n)
    return df


def run(args, timer=None):
    """Chạy theo tham số; trả về dict tóm tắt (dùng chung cho run_hanoi_pilot.py, run_auto_update.py)."""
    timer = timer or StepTimer()
    t0 = time.perf_counter()
    out = resolve_output_dir(args.output_dir)
    setup_directory_structure(out)
    free_gb = check_disk_space(out, args.min_free_gb)
    print(f"[*] Ổ đĩa còn trống: {free_gb:.1f} GB")
    summary = {"output_dir": str(out), "ntl": None, "landcover": None, "files": 0, "bytes": 0, "districts": 0}
    if args.pipeline == "init-only":
        return summary

    years = parse_years(args.years, args.start_year, args.end_year)
    cache = out / "_cache"
    with timer.step("chung", "tai_danh_muc_ranh_gioi"):
        districts = select_districts(args, cache)
    summary["districts"] = len(districts)
    summary["years"] = years
    print(f"[*] {len(districts)} huyện: {', '.join(districts['ten_huyen'].head(40))}"
          f"{' ...' if len(districts) > 40 else ''}")
    print(f"[*] Năm: {years[0]}–{years[-1]} ({len(years)} năm)")

    common = dict(output_dir=out, ee_project=args.ee_project, timer=timer, download_tif=not args.no_tif,
                  cache_dir=cache)
    if args.pipeline in ("all", "ntl"):
        from VN_NTL_Panel_2004_2025.code.ntl_pipeline import NTLPipeline
        print("\n[*] PIPELINE ÁNH SÁNG BAN ĐÊM (NTL)")
        ntl = NTLPipeline(monthly=args.monthly, monthly_tif=args.monthly_tif, **common)
        df = ntl.run(districts, years)
        summary["ntl"] = len(df)
        if not df.empty:
            ran = df[df["ma_huyen_gadm"].isin(districts["ma_huyen"])].drop_duplicates("ma_huyen_gadm")
            summary["area_km2"] = float(ran["dien_tich_km2"].sum())
        summary["files"] += ntl.files_downloaded
        summary["bytes"] += ntl.bytes_downloaded

    if args.pipeline in ("all", "landcover"):
        from VN_LandCover_Panel_2004_2025.code.landcover_pipeline import LandCoverPipeline
        print("\n[*] PIPELINE LỚP PHỦ BỀ MẶT (ẢNH BAN NGÀY)")
        sensors = [s.strip().lower() for s in args.day_sensors.split(",") if s.strip()]
        lc = LandCoverPipeline(sensors=sensors, accuracy=not args.no_accuracy, monthly=args.monthly,
                               monthly_tif=args.monthly_tif, **common)
        df = lc.run(districts, years)
        summary["landcover"] = len(df)
        if not df.empty and not summary.get("area_km2"):
            ran = df[df["ma_huyen_gadm"].isin(districts["ma_huyen"])].drop_duplicates("ma_huyen_gadm")
            summary["area_km2"] = float(ran["tong_dien_tich_ha"].sum()) / 100
        summary["files"] += lc.files_downloaded
        summary["bytes"] += lc.bytes_downloaded

    summary["seconds"] = round(time.perf_counter() - t0, 1)
    return summary


def main(argv=None):
    args = build_parser().parse_args(argv)
    timer = StepTimer()
    s = run(args, timer)
    if args.pipeline != "init-only":
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        timer.save(Path(s["output_dir"]) / "timing" / f"timing_{stamp}.csv")
        print(f"\n[✓] Xong sau {s['seconds']:.0f} giây. Bảng NTL: {s['ntl']} dòng, lớp phủ: {s['landcover']} dòng, "
              f"{s['files']} tệp .tif ({s['bytes'] / 1024 ** 2:.1f} MB) tại {s['output_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
