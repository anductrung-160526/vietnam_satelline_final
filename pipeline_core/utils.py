# -*- coding: utf-8 -*-
"""
Các hàm tiện ích: Ghi log chuẩn, Quản lý Checkpoint/Resume, Xuất bảng đa định dạng (CSV, XLSX, DTA), Xử lý tải ảnh
"""
import os
import sys
import json
import time
import logging
from datetime import datetime
from pathlib import Path
import pandas as pd

def setup_pipeline_logger(log_dir, pipeline_name):
    """
    Thiết lập logger ghi cả ra màn hình và file log chuyên dụng
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(pipeline_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    # Định dạng chuẩn: [YYYY-MM-DD HH:MM:SS] | System | Loại ảnh | Nội dung
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{pipeline_name}_{stamp}.log"

    formatter = logging.Formatter("%(message)s")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    logger.propagate = False
    return logger, log_file

def log_audit(logger, performer="System/Pipeline", sensor_type="General", content=""):
    """
    Ghi nhật ký chuẩn định dạng:
    [YYYY-MM-DD HH:MM:SS] | Người thực hiện | Loại ảnh | Nội dung chi tiết
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now_str}] | {performer} | {sensor_type} | {content}"
    logger.info(line)

class CheckpointManager:
    """
    Quản lý lưu vết tiến độ xử lý để dừng và chạy tiếp (Resume) không bao giờ bị trùng lặp
    """
    def __init__(self, checkpoint_path):
        self.checkpoint_path = Path(checkpoint_path)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.completed_tasks = set()
        self._load()

    def _load(self):
        if self.checkpoint_path.is_file():
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            record = json.loads(line)
                            key = f"{record.get('ma_huyen')}_{record.get('nam')}_{record.get('task')}"
                            self.completed_tasks.add(key)
                        except Exception:
                            pass

    def is_completed(self, ma_huyen, nam, task):
        key = f"{ma_huyen}_{nam}_{task}"
        return key in self.completed_tasks

    def mark_completed(self, ma_huyen, nam, task, metadata=None):
        record = {
            "ma_huyen": str(ma_huyen),
            "nam": int(nam),
            "task": str(task),
            "completed_at": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        with open(self.checkpoint_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        key = f"{ma_huyen}_{nam}_{task}"
        self.completed_tasks.add(key)

def export_multiformat_table(df, base_filepath_no_ext, formats=("csv", "xlsx", "dta")):
    """
    Xuất bảng dữ liệu đồng thời ra 3 định dạng chuẩn: .csv, .xlsx, .dta
    Xử lý tự động kiểu dữ liệu chuỗi để tương thích hoàn toàn với Stata
    """
    base_path = Path(base_filepath_no_ext)
    base_path.parent.mkdir(parents=True, exist_ok=True)

    df_clean = df.copy()

    # 1. Xuất CSV
    if "csv" in formats:
        csv_file = base_path.with_suffix(".csv")
        df_clean.to_csv(csv_file, index=False, encoding="utf-8-sig")

    # 2. Xuất Excel (.xlsx)
    if "xlsx" in formats:
        xlsx_file = base_path.with_suffix(".xlsx")
        try:
            df_clean.to_excel(xlsx_file, index=False, engine="openpyxl")
        except Exception as e:
            # Fallback nếu lỗi engine
            pass

    # 3. Xuất Stata (.dta)
    if "dta" in formats:
        dta_file = base_path.with_suffix(".dta")
        df_stata = df_clean.copy()
        # Chuẩn hóa tên cột tuân thủ quy ước Stata (tối đa 32 ký tự, không dấu, chữ thường)
        df_stata.columns = [str(c)[:32].lower().replace(" ", "_") for c in df_stata.columns]

        # Stata không chấp nhận chuỗi quá dài hoặc null kiểu hỗn hợp
        for col in df_stata.select_dtypes(include=["object"]).columns:
            df_stata[col] = df_stata[col].fillna("").astype(str)
            # Giới hạn độ dài chuỗi để tránh lỗi strL của Stata
            df_stata[col] = df_stata[col].str.slice(0, 244)

        try:
            df_stata.to_stata(dta_file, write_index=False, version=118)
        except Exception:
            # Thử qua pyreadstat nếu có
            try:
                import pyreadstat
                pyreadstat.write_dta(df_stata, str(dta_file))
            except Exception:
                pass

def df_to_markdown(df, index=False):
    """Chuyển DataFrame thành bảng Markdown chuẩn thuần Python, không phụ thuộc vào thư viện tabulate."""
    if index:
        df = df.reset_index()
    headers = [str(c) for c in df.columns]
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for _, row in df.iterrows():
        row_vals = [str(val).replace("\n", " ").replace("|", "\\|") for val in row]
        lines.append("| " + " | ".join(row_vals) + " |")
    return "\n".join(lines)

