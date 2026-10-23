# -*- coding: utf-8 -*-
"""
Các hàm tiện ích: ghi log chuẩn, checkpoint/resume, xuất bảng đa định dạng (CSV, XLSX, DTA),
đo thời gian từng bước, kiểm tra dung lượng ổ đĩa.
"""
import os
import sys
import json
import time
import shutil
import getpass
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import pandas as pd

UPDATE_JOURNAL = "nhat_ky_cap_nhat.txt"


def current_user():
    """Người thực hiện ghi trong nhật ký: biến môi trường VNGIS_USER, mặc định tên tài khoản máy."""
    name = os.environ.get("VNGIS_USER", "").strip()
    if name:
        return name
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def setup_pipeline_logger(log_dir, pipeline_name):
    """
    Logger ghi ra màn hình, file log của lượt chạy, file lỗi riêng và nhật ký cập nhật dùng chung
    (logs/nhat_ky_cap_nhat.txt, nối tiếp qua các lượt chạy).
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(pipeline_name)
    logger.setLevel(logging.INFO)
    for h in list(logger.handlers):
        h.close()
    logger.handlers.clear()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{pipeline_name}_{stamp}.log"
    formatter = logging.Formatter("%(message)s")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    journal = logging.FileHandler(log_dir / UPDATE_JOURNAL, encoding="utf-8")
    journal.setFormatter(formatter)
    logger.addHandler(journal)

    eh = logging.FileHandler(log_dir / f"{pipeline_name}_errors_{stamp}.log", encoding="utf-8", delay=True)
    eh.setLevel(logging.ERROR)
    eh.setFormatter(formatter)
    logger.addHandler(eh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    logger.propagate = False
    return logger, log_file


def log_audit(logger, performer=None, sensor_type="General", content="", error=False):
    """
    Ghi nhật ký theo mẫu kế hoạch:
    Ngày cập nhật | Người thực hiện | Loại ảnh cập nhật | Nội dung chi tiết
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{now_str} | {performer or current_user()} | {sensor_type} | {content}"
    if error:
        logger.error("LỖI: " + line)
    else:
        logger.info(line)


class CheckpointManager:
    """
    Lưu vết tiến độ (JSONL). Mỗi dòng giữ cả bản ghi kết quả để dựng lại bảng khi chạy tiếp (resume).
    """
    def __init__(self, checkpoint_path):
        self.checkpoint_path = Path(checkpoint_path)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.records = {}
        self._load()

    @staticmethod
    def _key(ma_huyen, nam, task):
        return f"{ma_huyen}|{nam}|{task}"

    def _load(self):
        if not self.checkpoint_path.is_file():
            return
        with open(self.checkpoint_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                self.records[self._key(rec.get("ma_huyen"), rec.get("nam"), rec.get("task"))] = rec

    def is_completed(self, ma_huyen, nam, task):
        return self._key(ma_huyen, nam, task) in self.records

    def get(self, ma_huyen, nam, task):
        rec = self.records.get(self._key(ma_huyen, nam, task))
        return rec.get("metadata") if rec else None

    def mark_completed(self, ma_huyen, nam, task, metadata=None):
        rec = {
            "ma_huyen": str(ma_huyen),
            "nam": int(nam),
            "task": str(task),
            "completed_at": datetime.now().isoformat(timespec="seconds"),
            "metadata": metadata or {},
        }
        with open(self.checkpoint_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.records[self._key(ma_huyen, nam, task)] = rec

    def results(self, task_prefix):
        """Tất cả bản ghi kết quả của các task bắt đầu bằng task_prefix."""
        return [r["metadata"] for r in self.records.values()
                if str(r.get("task", "")).startswith(task_prefix) and r.get("metadata")]


def export_multiformat_table(df, base_filepath_no_ext, formats=("csv", "xlsx", "dta"), logger=None):
    """Xuất bảng ra .csv, .xlsx, .dta. Lỗi định dạng nào thì báo lỗi định dạng đó."""
    base_path = Path(base_filepath_no_ext)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    written = []

    if "csv" in formats:
        f = base_path.with_suffix(".csv")
        df.to_csv(f, index=False, encoding="utf-8-sig")
        written.append(f)

    if "xlsx" in formats:
        f = base_path.with_suffix(".xlsx")
        try:
            df.to_excel(f, index=False, engine="openpyxl")
            written.append(f)
        except Exception as e:
            if logger:
                log_audit(logger, sensor_type="Export", content=f"Không ghi được {f.name}: {e}", error=True)

    if "dta" in formats:
        f = base_path.with_suffix(".dta")
        df_stata = df.copy()
        df_stata.columns = [str(c)[:32].lower().replace(" ", "_") for c in df_stata.columns]
        for col in df_stata.columns:
            if df_stata[col].dtype == object or str(df_stata[col].dtype).startswith("string"):
                df_stata[col] = df_stata[col].fillna("").astype(str).str.slice(0, 244)
        try:
            df_stata.to_stata(f, write_index=False, version=118)
            written.append(f)
        except Exception as e:
            if logger:
                log_audit(logger, sensor_type="Export", content=f"Không ghi được {f.name}: {e}", error=True)
    return written


def combine_annual_monthly(annual, monthly, sort_keys=("ma_huyen_gadm",)):
    """Gộp bản ghi năm và tháng vào một bảng: cột 'ky' = 'Năm' | 'Tháng', 'thang' để trống ở dòng năm."""
    parts = []
    if annual is not None and not annual.empty:
        a = annual.copy()
        a.insert(a.columns.get_loc("nam") + 1, "ky", "Năm")
        a["thang"] = pd.NA
        parts.append(a)
    if monthly is not None and not monthly.empty:
        m = monthly.copy()
        m.insert(m.columns.get_loc("nam") + 1, "ky", "Tháng")
        parts.append(m)
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True, sort=False)
    cols = list(parts[0].columns)
    cols = cols[:cols.index("ky") + 1] + ["thang"] + [c for c in df.columns if c not in cols[:cols.index("ky") + 1] + ["thang"]]
    df = df[list(dict.fromkeys(cols))]
    df["_ord"] = (df["ky"] == "Tháng").astype(int)
    df["thang"] = pd.to_numeric(df["thang"], errors="coerce").astype("Int64")
    df = df.sort_values([*sort_keys, "nam", "_ord", "thang"], na_position="first").drop(columns="_ord")
    return df.reset_index(drop=True)


def pct_change_consecutive(df, group_col, value_col, year_col="nam", extra_keys=()):
    """% thay đổi so với năm liền trước; năm đầu hoặc năm bị khuyết -> NaN (không điền 0)."""
    keys = [group_col, *extra_keys]
    df = df.sort_values([*keys, year_col]).copy()
    prev_val = df.groupby(keys)[value_col].shift(1)
    prev_year = df.groupby(keys)[year_col].shift(1)
    ok = (df[year_col] - prev_year == 1) & (prev_val > 0)
    df_out = ((df[value_col] - prev_val) / prev_val * 100.0).where(ok)
    return df_out.round(2)


def check_disk_space(path, required_gb=1.0, logger=None):
    """Kiểm tra dung lượng trống của ổ chứa path. Trả về số GB trống."""
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    free_gb = shutil.disk_usage(p).free / 1024 ** 3
    if free_gb < required_gb:
        msg = f"Ổ đĩa chứa {path} chỉ còn {free_gb:.1f} GB, cần khoảng {required_gb:.1f} GB."
        if logger:
            log_audit(logger, sensor_type="Disk", content=msg, error=True)
        else:
            print("[!] " + msg)
    return free_gb


class StepTimer:
    """Đo thời gian từng bước; ghi ra CSV (dùng cho file timing của lượt chạy thử)."""
    def __init__(self):
        self.rows = []

    @contextmanager
    def step(self, pipeline, step, ma_huyen="", nam="", **extra):
        t0 = time.perf_counter()
        status = "ok"
        try:
            yield
        except Exception:
            status = "loi"
            raise
        finally:
            self.rows.append({
                "pipeline": pipeline, "buoc": step, "ma_huyen": ma_huyen, "nam": nam,
                "giay": round(time.perf_counter() - t0, 2), "trang_thai": status, **extra,
            })

    def add(self, **row):
        self.rows.append(row)

    def to_frame(self):
        return pd.DataFrame(self.rows)

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.to_frame().to_csv(path, index=False, encoding="utf-8-sig")
        return path


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
