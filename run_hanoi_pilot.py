# -*- coding: utf-8 -*-
"""
CHẠY HÀ NỘI: lấy bảng .csv và ảnh .tif ban đêm/ban ngày cho tất cả quận/huyện của Hà Nội,
đo thời gian từng bước và ước tính thời gian, dung lượng để chạy toàn quốc.

Mặc định lấy cả dữ liệu NĂM và 12 THÁNG (bảng + ảnh .tif từng tháng) cho mọi nguồn có ảnh tháng.
Ảnh ngày: Landsat 2004–2014, Sentinel-2 2015–2025. Ảnh đêm: DMSP (chỉ có năm) + VIIRS (năm + tháng).
Tắt dữ liệu tháng: --no-monthly.

CSV chỉ số (mỗi file gồm cả dòng năm và dòng tháng, cột 'ky' = Năm/Tháng):
    VN_LandCover_Panel_2004_2025/data_processed/vietnam_district_day_indices_2004_2025.csv
    VN_NTL_Panel_2004_2025/data_processed/vietnam_district_night_indices_2004_2025.csv

    python run_hanoi_pilot.py                 # mặc định năm 2024
    python run_hanoi_pilot.py --years 2004-2025
    python run_hanoi_pilot.py --years 2024 --output-dir D:\\VNGIS_Data

Kết quả thời gian: <output>/VN_*/logs/timing_hanoi_<thời điểm>.csv và timing_hanoi_<thời điểm>_tom_tat.txt
"""
import sys
from datetime import datetime
from pathlib import Path

from run_pipeline import build_parser, run
from pipeline_core.config import NTL_PACKAGE, LANDCOVER_PACKAGE
from pipeline_core.utils import StepTimer

NATIONAL_DISTRICTS = 705
NATIONAL_YEARS = 22
VN_AREA_KM2 = 331_000
HANOI_AREA_KM2 = 3_359


def fmt_duration(sec):
    sec = int(sec)
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = [f"{d} ngày"] if d else []
    parts += [f"{h} giờ"] if h else []
    parts += [f"{m} phút"] if m else []
    return " ".join(parts + [f"{s} giây"]) if not d else " ".join(parts)


def summarize(df, summary):
    n_d = max(summary["districts"], 1)
    n_y = max(len(summary.get("years", [1])), 1)
    lines = [
        "=" * 70,
        f"KẾT QUẢ CHẠY THỬ HÀ NỘI ({datetime.now():%Y-%m-%d %H:%M})",
        "=" * 70,
        f"Số quận/huyện: {summary['districts']} | Năm: {summary['years'][0]}–{summary['years'][-1]}",
        f"Tổng thời gian: {fmt_duration(summary['seconds'])}",
        f"Số tệp .tif đã tải: {summary['files']} | Dung lượng: {summary['bytes'] / 1024 ** 2:.1f} MB",
        f"Diện tích các huyện đã chạy: {summary.get('area_km2') or 0:.1f} km²",
        f"Bảng năm: NTL {summary['ntl']} dòng | lớp phủ {summary['landcover']} dòng "
        f"(bảng tháng nằm trong *_monthly.csv)",
        "",
        "Thời gian theo bước (giây):",
    ]
    if not df.empty:
        by_step = df.groupby(["pipeline", "buoc"])["giay"].agg(["count", "sum", "mean"]).round(1)
        lines.append(by_step.to_string())
        per_unit = df[df["ma_huyen"].astype(str) != ""]["giay"].sum() / (n_d * n_y)
        setup = df[df["ma_huyen"].astype(str) == ""]["giay"].sum() / n_y
        est_sec = per_unit * NATIONAL_DISTRICTS * NATIONAL_YEARS + setup * NATIONAL_YEARS
        # Dung lượng tỷ lệ với diện tích THỰC TẾ của các huyện vừa chạy (không phải cả Hà Nội)
        area = summary.get("area_km2") or HANOI_AREA_KM2
        est_gb = summary["bytes"] / (n_y * area) * VN_AREA_KM2 * NATIONAL_YEARS / 1024 ** 3
        lines += [
            "",
            "ƯỚC TÍNH TOÀN QUỐC (~705 huyện × 22 năm, chạy tuần tự, cùng tùy chọn):",
            f"  Thời gian trung bình mỗi huyện-năm: {per_unit:.1f} giây",
            f"  Thời gian ước tính: {fmt_duration(est_sec)}",
            f"  Dung lượng .tif ước tính (theo diện tích): {est_gb:.1f} GB",
            "  (Ước tính thô: phụ thuộc mạng, quota GEE và kích thước huyện.)",
        ]
    return "\n".join(lines)


def main(argv=None):
    parser = build_parser()
    parser.add_argument("--no-monthly", action="store_true", help="Chỉ lấy dữ liệu năm")
    parser.add_argument("--no-monthly-tif", action="store_true", help="Lấy bảng tháng nhưng không tải .tif tháng")
    parser.set_defaults(province="Hà Nội", years="2024", mode="full")
    args = parser.parse_args(argv)
    args.monthly = not args.no_monthly
    args.monthly_tif = args.monthly and not args.no_monthly_tif
    timer = StepTimer()
    summary = run(args, timer)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(summary["output_dir"])
    df = timer.to_frame()
    text = summarize(df, summary)
    print("\n" + text)
    for pkg in (NTL_PACKAGE, LANDCOVER_PACKAGE):
        logs = out / pkg / "logs"
        timer.save(logs / f"timing_hanoi_{stamp}.csv")
        (logs / f"timing_hanoi_{stamp}_tom_tat.txt").write_text(text, encoding="utf-8")
    print(f"\n[✓] File thời gian: {out / NTL_PACKAGE / 'logs' / f'timing_hanoi_{stamp}.csv'}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
