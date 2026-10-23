# -*- coding: utf-8 -*-
"""
Lớp nền cho 2 pipeline (NTL và LandCover): thư mục, log, checkpoint, kết nối GEE,
hình học huyện, tải .tif có đo thời gian và dung lượng.
"""
import re
from pathlib import Path

from .config import DEFAULT_EE_PROJECT, resolve_output_dir
from .admin_boundaries import load_district_geometries
from .utils import setup_pipeline_logger, log_audit, CheckpointManager, StepTimer
from . import ee_utils

ID_COLS = ["ma_tinh", "ten_tinh", "ma_huyen", "ten_huyen", "ma_huyen_gadm"]


class BasePipeline:
    PACKAGE = ""
    NAME = ""
    SUBDIRS = ()

    def __init__(self, output_dir=None, ee_project=None, timer=None, download_tif=True, cache_dir=None):
        self.output_dir = resolve_output_dir(output_dir)
        self.pkg_dir = self.output_dir / self.PACKAGE
        for sub in self.SUBDIRS:
            (self.pkg_dir / sub).mkdir(parents=True, exist_ok=True)
        self.processed_dir = self.pkg_dir / "data_processed"
        self.intermediate_dir = self.pkg_dir / "data_intermediate"
        self.logs_dir = self.pkg_dir / "logs"
        self.docs_dir = self.pkg_dir / "docs"
        self.cache_dir = cache_dir
        self.logger, self.log_file = setup_pipeline_logger(self.logs_dir, self.NAME)
        self.checkpoint = CheckpointManager(self.logs_dir / f"{self.NAME}_checkpoint.jsonl")
        self.ee_project = ee_project or DEFAULT_EE_PROJECT
        self.timer = timer or StepTimer()
        self.download_tif = download_tif
        self.ee = None
        self.geoms = {}
        self.bytes_downloaded = 0
        self.files_downloaded = 0

    # ------------------------------------------------------------------ helpers
    def log(self, sensor, content, error=False):
        log_audit(self.logger, sensor_type=sensor, content=content, error=error)

    def connect(self):
        if self.ee is None:
            with self.timer.step(self.NAME, "xac_thuc_gee"):
                self.ee = ee_utils.init_ee(self.ee_project, self.logger)
            self.log("EarthEngine", f"Kết nối GEE thành công (project: {self.ee_project})")
        return self.ee

    def load_geometries(self, districts_df):
        missing = [g for g in districts_df["ma_huyen_gadm"] if g not in self.geoms]
        if missing:
            with self.timer.step(self.NAME, "doc_ranh_gioi_huyen"):
                self.geoms.update(load_district_geometries(missing, self.cache_dir))
        lost = [g for g in missing if g not in self.geoms]
        if lost:
            self.log("Boundary", f"Không tìm thấy hình học cho: {', '.join(lost)}", error=True)

    @staticmethod
    def file_id(row):
        """Mã dùng trong tên tệp: mã huyện Cục Thống kê, nếu chưa có thì mã GADM (bỏ ký tự đặc biệt)."""
        code = str(row.get("ma_huyen_tk") or "").strip()
        return code if code else re.sub(r"[^A-Za-z0-9]+", "_", str(row["ma_huyen_gadm"])).strip("_")

    @staticmethod
    def id_fields(row):
        return {
            "ma_tinh": row.get("ma_tinh_tk") or row["ma_tinh"],
            "ten_tinh": row["ten_tinh"],
            "ma_huyen": row.get("ma_huyen_tk") or row["ma_huyen_gadm"],
            "ten_huyen": row["ten_huyen"],
            "ma_huyen_gadm": row["ma_huyen_gadm"],
        }

    def save_tif(self, image, row, dest, scale, n_bands, dtype, sensor, year):
        """Tải 1 ảnh .tif cho 1 huyện (bỏ qua nếu đã có). Ghi nhật ký và thời gian."""
        if not self.download_tif:
            return
        dest = Path(dest)
        if dest.is_file():
            return
        geom = self.geoms[row["ma_huyen_gadm"]]
        with self.timer.step(self.NAME, f"tai_tif_{dest.parent.name.lower()}", row["ma_huyen_gadm"], year,
                             tep=dest.name) as _:
            size = ee_utils.download_image(self.ee, image, geom, scale, dest, n_bands=n_bands, dtype=dtype)
        self.bytes_downloaded += size
        self.files_downloaded += 1
        self.timer.rows[-1]["mb"] = round(size / 1024 ** 2, 2)
        self.log(sensor, f"Tải {dest.name} ({size / 1024 ** 2:.1f} MB) -> {dest.parent}")

    def prepare_districts(self, districts_df):
        df = districts_df.copy()
        if "ma_huyen_gadm" not in df.columns:
            df["ma_huyen_gadm"] = df["ma_huyen"]
        for col in ("ma_tinh_tk", "ma_huyen_tk"):
            if col not in df.columns:
                df[col] = ""
        no_code = df[df["ma_huyen_tk"] == ""]
        if len(no_code):
            self.log("Boundary", "Chưa có mã Cục Thống kê (dùng tạm mã GADM): "
                     + ", ".join(f"{r.ten_huyen} ({r.ma_huyen_gadm})" for r in no_code.itertuples()))
        return df
