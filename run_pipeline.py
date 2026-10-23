# -*- coding: utf-8 -*-
"""
TRÌNH ĐIỀU PHỐI TRUNG TÂM (MASTER PIPELINE RUNNER)
Xử lý dữ liệu viễn thám cấp Huyện tại Việt Nam (2004–2025)
Hỗ trợ:
- Tùy biến thư mục lưu trữ trên bất kỳ ổ cứng nào (--output-dir)
- Tự động thiết lập cấu trúc 2 gói dữ liệu độc lập
- Sinh Codebook (MD & XLSX) và bộ mẫu kiểm chứng mặt đất
- Chạy Pipeline Ánh sáng ban đêm (NTL) và Lớp phủ bề mặt (Land Cover)
- Hỗ trợ chế độ Thử nghiệm (--mode pilot) và Toàn quốc (--mode full)
"""
import os
import sys
import shutil
import argparse
from pathlib import Path

# Đảm bảo mã hóa UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Nạp các mô-đun cốt lõi
from pipeline_core.config import START_YEAR, END_YEAR, resolve_output_dir
from pipeline_core.admin_boundaries import load_district_boundaries, get_pilot_districts
from pipeline_core.codebook_gen import generate_codebooks
from pipeline_core.samples_gen import generate_sample_dataset
from VN_NTL_Panel_2004_2025.code.ntl_pipeline import NTLPipeline
from VN_LandCover_Panel_2004_2025.code.landcover_pipeline import LandCoverPipeline
from VN_LandCover_Panel_2004_2025.code.accuracy_assessment import evaluate_classification_accuracy

def setup_directory_structure(output_dir):
    """
    Tự động khởi tạo đầy đủ hệ thống cây thư mục cho 2 gói dữ liệu trên ổ đĩa được chỉ định
    """
    output_dir = Path(output_dir).resolve()
    print(f"\n==================================================================")
    print(f"[*] KHỞI TẠO CẤU TRÚC THƯ MỤC TẠI: {output_dir}")
    print(f"==================================================================")

    # 1. Gói NTL
    ntl_pkg = output_dir / "VN_NTL_Panel_2004_2025"
    ntl_subdirs = [
        ntl_pkg / "raw_data" / "NTL" / "DMSP",
        ntl_pkg / "raw_data" / "NTL" / "VIIRS",
        ntl_pkg / "data_intermediate",
        ntl_pkg / "data_processed",
        ntl_pkg / "metadata",
        ntl_pkg / "code",
        ntl_pkg / "docs",
        ntl_pkg / "logs"
    ]
    for d in ntl_subdirs:
        d.mkdir(parents=True, exist_ok=True)

    # 2. Gói Land Cover
    lc_pkg = output_dir / "VN_LandCover_Panel_2004_2025"
    lc_subdirs = [
        lc_pkg / "raw_data" / "DAY" / "LANDSAT",
        lc_pkg / "raw_data" / "DAY" / "SENTINEL2",
        lc_pkg / "data_intermediate",
        lc_pkg / "data_processed",
        lc_pkg / "metadata",
        lc_pkg / "samples",
        lc_pkg / "code",
        lc_pkg / "docs",
        lc_pkg / "logs"
    ]
    for d in lc_subdirs:
        d.mkdir(parents=True, exist_ok=True)

    # Sao chép các tệp tài liệu và script vào gói dữ liệu nếu output_dir khác thư mục hiện tại
    cur_dir = Path(__file__).resolve().parent
    if output_dir != cur_dir:
        # Đồng bộ tài liệu và mã nguồn
        for pkg_name in ["VN_NTL_Panel_2004_2025", "VN_LandCover_Panel_2004_2025"]:
            src_pkg = cur_dir / pkg_name
            dst_pkg = output_dir / pkg_name
            if src_pkg.exists():
                for item in src_pkg.iterdir():
                    if item.is_file():
                        shutil.copy2(item, dst_pkg / item.name)
                    elif item.is_dir() and item.name in ["code", "docs", "samples"]:
                        shutil.copytree(item, dst_pkg / item.name, dirs_exist_ok=True)

    # Sinh Codebooks và Samples tự động
    generate_codebooks(output_dir)
    generate_sample_dataset(lc_pkg / "samples")
    evaluate_classification_accuracy(output_dir)

    print("[*] Hoàn tất thiết lập cấu trúc 2 gói dữ liệu.")
    return ntl_pkg, lc_pkg

def main():
    parser = argparse.ArgumentParser(
        description="Master Pipeline điều phối trích xuất dữ liệu viễn thám cấp Huyện Việt Nam (2004–2025)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="Đường dẫn thư mục lưu trữ trên ổ cứng (mặc định lấy thư mục dự án hoặc biến môi trường OUTPUT_ROOT)"
    )
    parser.add_argument(
        "--pipeline",
        type=str,
        choices=["all", "ntl", "landcover", "init-only"],
        default="all",
        help="Chọn pipeline cần chạy: all (cả hai), ntl (chỉ ảnh đêm), landcover (chỉ lớp phủ), init-only (chỉ tạo cấu trúc thư mục)"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["pilot", "full"],
        default="pilot",
        help="Chế độ chạy: pilot (thử nghiệm vài huyện) hoặc full (toàn bộ ~705 huyện)"
    )
    parser.add_argument(
        "--pilot-n",
        type=int,
        default=3,
        help="Số lượng huyện chạy thử ở chế độ pilot (mặc định 3)"
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=START_YEAR,
        help=f"Năm bắt đầu (mặc định {START_YEAR})"
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=END_YEAR,
        help=f"Năm kết thúc (mặc định {END_YEAR})"
    )
    parser.add_argument(
        "--ee-project",
        type=str,
        default="",
        help="Google Cloud Project ID đã đăng ký Google Earth Engine"
    )

    args = parser.parse_args()

    # 1. Xác định đường dẫn đích và khởi tạo cấu trúc thư mục
    target_output_dir = resolve_output_dir(args.output_dir)
    setup_directory_structure(target_output_dir)

    if args.pipeline == "init-only":
        print("[*] Đã hoàn thành khởi tạo cấu trúc thư mục và tài liệu. Dừng theo yêu cầu --pipeline init-only.")
        return 0

    years_to_run = list(range(args.start_year, args.end_year + 1))
    print(f"\n[*] CHUỖI THỜI GIAN XỬ LÝ: {args.start_year} -> {args.end_year} ({len(years_to_run)} năm)")
    print(f"[*] CHẾ ĐỘ THỰC THI: {args.mode.upper()} (Số huyện: {args.pilot_n if args.mode == 'pilot' else 'Toàn quốc'})")

    # 2. Chạy Pipeline Ánh sáng ban đêm (NTL)
    if args.pipeline in ["all", "ntl"]:
        print(f"\n------------------------------------------------------------------")
        print(f"[*] KÍCH HOẠT: PIPELINE ÁNH SÁNG BAN ĐÊM (NTL)")
        print(f"------------------------------------------------------------------")
        ntl_runner = NTLPipeline(output_dir=target_output_dir, ee_project=args.ee_project)
        df_ntl = ntl_runner.run(mode=args.mode, pilot_n=args.pilot_n, years=years_to_run)
        print(f"[*] Kết quả NTL: Đã xuất {len(df_ntl)} dòng dữ liệu bảng.")

    # 3. Chạy Pipeline Lớp phủ bề mặt (Land Cover)
    if args.pipeline in ["all", "landcover"]:
        print(f"\n------------------------------------------------------------------")
        print(f"[*] KÍCH HOẠT: PIPELINE LỚP PHỦ BỀ MẶT (LAND COVER)")
        print(f"------------------------------------------------------------------")
        lc_runner = LandCoverPipeline(output_dir=target_output_dir, ee_project=args.ee_project)
        df_lc = lc_runner.run(mode=args.mode, pilot_n=args.pilot_n, years=years_to_run)
        print(f"[*] Kết quả Land Cover: Đã xuất {len(df_lc)} dòng dữ liệu bảng.")

    print(f"\n==================================================================")
    print(f"[✓] HOÀN TẤT THỰC THI TOÀN BỘ YÊU CẦU PIPELINE!")
    print(f"[✓] Bảng số liệu hoàn chỉnh đã sẵn sàng tại:")
    print(f"    - NTL: {target_output_dir / 'VN_NTL_Panel_2004_2025' / 'data_processed'}")
    print(f"    - Land Cover: {target_output_dir / 'VN_LandCover_Panel_2004_2025' / 'data_processed'}")
    print(f"==================================================================\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
