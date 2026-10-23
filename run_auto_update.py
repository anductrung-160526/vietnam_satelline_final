# -*- coding: utf-8 -*-
"""
CẬP NHẬT TỰ ĐỘNG (dùng với Windows Task Scheduler hoặc cron).

    python run_auto_update.py --scope monthly   # VIIRS tháng: năm nay và năm trước
    python run_auto_update.py --scope annual    # NTL + lớp phủ: mọi năm 2004..năm mới nhất còn thiếu
    python run_auto_update.py --scope all --province "Hà Nội"

Pipeline đọc checkpoint trong logs/ nên chỉ xử lý huyện/năm/tháng CHƯA có dữ liệu;
ảnh .tif đã có trên ổ đĩa sẽ không tải lại. Mọi lượt cập nhật ghi vào logs/nhat_ky_cap_nhat.txt.
"""
import sys
from datetime import date, datetime
from pathlib import Path

from run_pipeline import build_parser, run, select_districts, setup_directory_structure
from pipeline_core.config import START_YEAR, resolve_output_dir
from pipeline_core.utils import StepTimer, check_disk_space


def latest_complete_year(today=None):
    """Năm mới nhất có thể đã đủ ảnh: ảnh mùa khô kết thúc tháng 4; VIIRS năm thường có sau vài tháng."""
    today = today or date.today()
    return today.year if today.month >= 6 else today.year - 1


def run_monthly(args, timer):
    from VN_NTL_Panel_2004_2025.code.ntl_pipeline import NTLPipeline
    out = resolve_output_dir(args.output_dir)
    setup_directory_structure(out)
    check_disk_space(out, args.min_free_gb)
    districts = select_districts(args, out / "_cache")
    ntl = NTLPipeline(output_dir=out, ee_project=args.ee_project, timer=timer, download_tif=not args.no_tif,
                      cache_dir=out / "_cache", monthly=True, monthly_tif=args.monthly_tif)
    d = ntl.prepare_districts(districts)
    ntl.connect()
    ntl.load_geometries(d)
    this_year = date.today().year
    for year in (this_year - 1, this_year):
        ntl.log("VIIRS", f"Cập nhật tự động dữ liệu tháng năm {year} cho {len(d)} huyện")
        ntl.process_monthly(year, d)
    ntl.export_tables()


def main(argv=None):
    parser = build_parser()
    parser.add_argument("--scope", choices=["monthly", "annual", "all"], default="all")
    args = parser.parse_args(argv)
    timer = StepTimer()
    print(f"[*] Cập nhật tự động ({args.scope}) lúc {datetime.now():%Y-%m-%d %H:%M}")

    if args.scope in ("annual", "all"):
        args.years = f"{START_YEAR}-{latest_complete_year()}"
        run(args, timer)
    if args.scope in ("monthly", "all"):
        run_monthly(args, timer)

    out = resolve_output_dir(args.output_dir)
    f = timer.save(out / "timing" / f"timing_auto_{datetime.now():%Y%m%d_%H%M%S}.csv")
    print(f"[✓] Hoàn tất cập nhật. Thời gian từng bước: {f}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
