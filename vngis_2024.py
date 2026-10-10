# -*- coding: utf-8 -*-
"""
VNGISDash 07/2024–06/2025: pipeline tự động cấp huyện chạy trên GitHub Actions.

Nguồn khoa học: VNGISDash_Task123_Merged_final.ipynb. Pipeline chỉ giữ 3 chức năng:
  (1) trích xuất chỉ số từ ảnh ngày (Task 1) và ảnh đêm (Task 3.2), (2) lấy ảnh tif ngày (Task 2),
  (3) lấy ảnh tif đêm (Task 3.1). Không có bước chọn tỉnh, huyện: VNGIS_MODE=pilot tự lấy VNGIS_PILOT_N huyện,
  VNGIS_MODE=full chạy toàn bộ 710 huyện theo GADM 4.1.

Cấu trúc đầu ra (cấp 1 = thư mục trên Drive):
  Day/<GID_1>_<tỉnh>/<GID_2>_<huyện>/<GID_2>_day_YYYYMM.tif
  Night/<GID_1>_<tỉnh>/<GID_2>_<huyện>/<GID_2>_night_YYYYMM.tif
  CSV/day_indices.csv, CSV/night_indices.csv         (gộp cấp huyện toàn quốc)
  _control/                                         (trạng thái, log, báo cáo)

Giữ công thức chỉ số từ notebook, tính trực tiếp trên huyện: Task 1 và Task 3.2 gom các tháng thành 1 lần gọi
Earth Engine; việc kiểm tra "tháng có ảnh không" của Task 2/3.1 gom thành 1 lần gọi; truy vấn và tải ảnh
tuân theo một giới hạn đồng thời chung để hỗ trợ project ở Restricted Mode.

Chạy:
    python vngis_2024.py               chạy pipeline
    python vngis_2024.py --sync-only   đẩy nốt dữ liệu trên máy lên Drive

Mã thoát: 0 xong toàn bộ | 1 lỗi cấu hình hoặc preflight | 2 sự cố EE kéo dài | 3 hết giờ (nối lượt) | 130 dừng tay
"""

import os, io, re, sys, json, time, glob, math, shutil, zipfile, signal, logging, calendar, struct
import threading, subprocess, unicodedata, warnings, random, tempfile
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings("ignore")


def _env(name, default, cast=str):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    if cast is bool:
        return raw.strip().lower() in ("1", "true", "yes", "y")
    return cast(raw.strip())


# =====================================================================================
# 1. CẤU HÌNH
# =====================================================================================
def month_pairs(start, end):
    """Khoảng tháng đóng hai đầu, với năm/tháng hợp lệ và đúng cú pháp YYYY-MM."""
    def parse(text):
        if not re.fullmatch(r"\d{4}-\d{2}", text):
            raise ValueError("Tháng phải có dạng YYYY-MM")
        date = datetime.strptime(text, "%Y-%m")
        return date.year * 12 + date.month - 1
    first, last = parse(start), parse(end)
    if first > last:
        raise ValueError("Tháng bắt đầu phải trước hoặc bằng tháng kết thúc")
    return [(index // 12, index % 12 + 1) for index in range(first, last + 1)]


START_MONTH = _env("VNGIS_START_MONTH", "2024-07")
END_MONTH = _env("VNGIS_END_MONTH", "2025-06")
PERIODS = month_pairs(START_MONTH, END_MONTH)
PERIOD_ID = START_MONTH.replace("-", "") + "-" + END_MONTH.replace("-", "")
MONTH_KEYS = [f"{year}-{month:02d}" for year, month in PERIODS]
SCHEMA_ID = "districts-l2-v1"


def month_key(period):
    year, month = period
    return f"{year}-{month:02d}"

PROJECT_ID = _env("VNGIS_EE_PROJECT", "vngis-ee-2")               # project chịu quota Earth Engine
ASSET_ID = _env("VNGIS_EE_ASSET", f"projects/{PROJECT_ID}/assets/districts_l2")             # notebook cell 11

MODE = _env("VNGIS_MODE", "pilot").lower()                        # pilot | full
if MODE not in ("pilot", "full"):
    raise SystemExit(f"VNGIS_MODE phải là 'pilot' hoặc 'full', đang là '{MODE}'")
PILOT_N = _env("VNGIS_PILOT_N", 2, int)
if PILOT_N < 1:
    raise SystemExit("VNGIS_PILOT_N phải >= 1")

# Ảnh ngày: số kênh lưu vào tif. 6 = BLUE..SWIR2 (NDVI, NDBI, MNDWI, BSI tính lại được từ 6 kênh này);
# 10 = đủ 10 kênh như notebook (file lớn gần gấp đôi).
DAY_BANDS_ALL = ["BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2", "NDVI", "NDBI", "MNDWI", "BSI"]
DAY_BANDS = _env("VNGIS_DAY_BANDS", 10, int)
if DAY_BANDS not in (6, 10):
    raise SystemExit("VNGIS_DAY_BANDS phải là 6 hoặc 10")
# Kiểu lưu ảnh ngày: float = giữ nguyên giá trị Earth Engine trả về, nén DEFLATE không mất dữ liệu (như bản 4);
# int16 = round(giá trị × VNGIS_DAY_SCALE), dữ liệu thô bằng nửa Float32; đọc giá trị bằng DN × scale.
DAY_FORMAT = _env("VNGIS_DAY_FORMAT", "int16").lower()
if DAY_FORMAT not in ("float", "int16"):
    raise SystemExit("VNGIS_DAY_FORMAT phải là float hoặc int16")
DAY_SCALE_INV = _env("VNGIS_DAY_SCALE", 10000, int)
if DAY_SCALE_INV not in (1000, 10000):
    raise SystemExit("VNGIS_DAY_SCALE phải là 10000 hoặc 1000")
DAY_NODATA = -32768
DAY_IMAGE_SCALE = _env("VNGIS_DAY_IMAGE_SCALE", 20, int)
if DAY_IMAGE_SCALE not in (20, 50):
    raise SystemExit("VNGIS_DAY_IMAGE_SCALE phải là 20 hoặc 50 mét")
TIFF_ZLEVEL = _env("VNGIS_TIFF_ZLEVEL", 6, int)
if not 1 <= TIFF_ZLEVEL <= 9:
    raise SystemExit("VNGIS_TIFF_ZLEVEL phải nằm trong 1..9")

N_WORKERS = _env("VNGIS_WORKERS", 2, int)                         # số huyện chạy song song
MONTH_THREADS = _env("VNGIS_MONTH_THREADS", 2, int)               # số ảnh tải song song trong 1 huyện
EE_CONCURRENCY = _env("VNGIS_EE_CONCURRENCY", 1, int)             # giới hạn CHUNG truy vấn và tải ảnh
EE_MAX_RETRIES = _env("VNGIS_EE_MAX_RETRIES", 8, int)
if min(N_WORKERS, MONTH_THREADS, EE_CONCURRENCY, EE_MAX_RETRIES) < 1:
    raise SystemExit("VNGIS_WORKERS, VNGIS_MONTH_THREADS, VNGIS_EE_CONCURRENCY và VNGIS_EE_MAX_RETRIES phải >= 1")
REST_EVERY_N = _env("VNGIS_REST_EVERY_N", 10, int)
REST_AFTER_PROVINCE = _env("VNGIS_REST_AFTER_PROVINCE", True, bool)
REST_SEC = _env("VNGIS_REST_SEC", 30, int)
ALLOW_FULL_RESTART = _env("VNGIS_ALLOW_FULL_RESTART", False, bool)
if REST_EVERY_N < 0 or REST_SEC < 0:
    raise SystemExit("VNGIS_REST_EVERY_N và VNGIS_REST_SEC phải >= 0")
RUN_ID = _env("VNGIS_RUN_ID", "local")
MAX_RUNTIME_SEC = _env("VNGIS_MAX_RUNTIME_SEC", 0, int)
EE_KEY_FILE = _env("VNGIS_EE_KEY_FILE", "")
EE_HIGH_VOLUME = _env("VNGIS_EE_HIGH_VOLUME", False, bool)
MAX_ATTEMPTS = _env("VNGIS_MAX_ATTEMPTS", 3, int)
PREFLIGHT = _env("VNGIS_PREFLIGHT", True, bool)
PREFLIGHT_TILE_TEST = _env("VNGIS_PREFLIGHT_TILE_TEST", True, bool)
EE_DEADLINE_SEC = 300
DOWNLOAD_FAIL_LIMIT = 24
MAX_TILE_SPLIT = _env("VNGIS_MAX_TILE_SPLIT", 32, int)
TILING_OK = [True]

class EERequestGate:
    """Giới hạn chung, giảm số slot khi server báo 429; không tự tăng lại trong lượt."""
    def __init__(self, limit):
        self.limit = limit
        self.active = 0
        self.paused = False
        self.condition = threading.Condition()

    def __enter__(self):
        with self.condition:
            while self.paused or self.active >= self.limit:
                check_stop()
                self.condition.wait(timeout=0.5)
            check_stop()
            self.active += 1
        return self

    def __exit__(self, *args):
        with self.condition:
            self.active -= 1
            self.condition.notify_all()

    def reduce(self, restricted=False):
        with self.condition:
            old = self.limit
            self.limit = 1 if restricted else max(1, old // 2)
            self.condition.notify_all()
        return old, self.limit

    def pause(self, seconds, reason):
        """Chặn yêu cầu mới, đợi yêu cầu đang chạy xong rồi nghỉ; STOP ngắt được."""
        with self.condition:
            self.paused = True
        try:
            log.info(f"[rest] {reason}: chờ các yêu cầu EE đang chạy kết thúc.")
            with self.condition:
                while self.active and not STOP_EVENT.is_set():
                    self.condition.wait(timeout=0.5)
            if STOP_EVENT.is_set():
                return False
            log.info(f"[rest] Nghỉ chủ động {seconds}s cho tất cả luồng EE; đồng bộ Drive vẫn chạy.")
            interrupted = STOP_EVENT.wait(seconds)
            if not interrupted:
                log.info("[rest] Hết thời gian nghỉ, tiếp tục lấy dữ liệu.")
            return not interrupted
        finally:
            with self.condition:
                self.paused = False
                self.condition.notify_all()


EE_SEM = EERequestGate(EE_CONCURRENCY)
_ee_cooldown_lock = threading.Lock()
_ee_cooldown_until = 0.0

DRIVE_FOLDER = _env("VNGIS_DRIVE_FOLDER", f"VNGISDash_{PERIOD_ID.replace('-', '_')}_Districts"
                   + ("_50m" if DAY_IMAGE_SCALE == 50 else "")
                   + ("_PILOT" if MODE == "pilot" else ""))
RCLONE_REMOTE = _env("VNGIS_RCLONE_REMOTE", "gdrive")
REMOTE_BASE = f"{RCLONE_REMOTE}:{DRIVE_FOLDER}"
LOCAL_ROOT = _env("VNGIS_LOCAL_ROOT", os.path.expanduser(f"~/vngis_2024/{DRIVE_FOLDER}"))
CACHE_DIR = _env("VNGIS_CACHE_DIR", os.path.expanduser("~/vngis_2024/_cache"))
UPLOAD_EVERY_SEC = _env("VNGIS_UPLOAD_EVERY_SEC", 300, int)
DRIVE_STOP_POLL_SEC = 300

D_DAY, D_NIGHT, D_CSV, D_CONTROL = "Day", "Night", "CSV", "_control"
D_STATUS = f"{D_CONTROL}/status"
D_PARTS = f"{D_CONTROL}/parts"          # chỉ số từng huyện, gom thành CSV toàn quốc
D_LOGS = f"{D_CONTROL}/logs"
DAY_CSV = f"{D_CSV}/day_indices.csv"
NIGHT_CSV = f"{D_CSV}/night_indices.csv"

GADM_VNM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/shp/gadm41_VNM_shp.zip"   # notebook cell 3
ADM_COLS = ["GID_1", "NAME_1", "GID_2", "NAME_2", "TYPE_2"]     # notebook cell 3

T1_FEATURES = [f"{b}_{s}" for b in DAY_BANDS_ALL for s in ("mean", "stdDev")]    # notebook cell 15
DAY_COLUMNS = ADM_COLS + T1_FEATURES + ["YEAR", "MONTH", "DATA_STATUS", "ERROR"]
NIGHT_COLUMNS = ADM_COLS + ["YEAR", "MONTH", "TIME", "DISTRICT_AREA_HA", "TNL",
                 "MEAN_RAD", "STD_RAD", "MIN_RAD", "MAX_RAD", "SPATIAL_CV", "LIT_PIXELS", "LIT_AREA_HA",
                 "ELECTRIFICATION_RATIO_PCT", "LIT_POP_PROXY", "CLOUD_FREE_OBS", "TNL_MA3",
                 "TNL_MOM_GROWTH_PCT", "DATA_STATUS", "ERROR"]
LEGACY_FLOAT_PROFILE = f"{SCHEMA_ID}:{PERIOD_ID}:day-float-{DAY_BANDS}-{DAY_SCALE_INV}"
OUTPUT_PROFILE = f"{SCHEMA_ID}:{PERIOD_ID}:day-{DAY_FORMAT}-{DAY_BANDS}-{DAY_SCALE_INV}:csv-calendar-v2"
if DAY_IMAGE_SCALE != 20:
    OUTPUT_PROFILE += f":day-scale-{DAY_IMAGE_SCALE}"

log = logging.getLogger("vngis")


def L(*parts):
    return os.path.join(LOCAL_ROOT, *parts)


# 2. DỪNG CÓ TRẬT TỰ, LOG
# =====================================================================================
class StopRequested(BaseException):
    """Kế thừa BaseException để khối `except Exception` của từng huyện không nuốt mất."""


STOP_EVENT = threading.Event()
STOP_REASON = [None]


def request_stop(reason):
    if not STOP_EVENT.is_set():
        STOP_REASON[0] = reason
        STOP_EVENT.set()
        why = {"deadline": "hết thời gian của lượt", "fatal": "lỗi tải ảnh nghiêm trọng",
               "drive_stop": "có file STOP trên Drive"}.get(reason, "nhận tín hiệu dừng")
        log.warning(f"Dừng có trật tự ({why}): làm nốt bước đang chạy, đồng bộ rồi thoát.")


def check_stop():
    if STOP_EVENT.is_set():
        raise StopRequested()


def install_signal_handlers():
    def handler(_s, _f):
        if STOP_EVENT.is_set():
            os._exit(130)
        request_stop("signal")
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handler)


def setup_logging():
    os.makedirs(L(D_LOGS), exist_ok=True)
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname).1s [%(threadName)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    fh = logging.FileHandler(L(D_LOGS, f"run_{stamp}_{RUN_ID}.log"), encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    log.propagate = False


def _nb_print(*args, **_kw):
    """Các hàm chép từ notebook gọi print(); ở pipeline chuyển thành log mức DEBUG cho gọn."""
    log.debug(" ".join(str(a) for a in args))


# =====================================================================================
# =====================================================================================
# 3. CHUẨN HÓA TÊN (đúng notebook cell 15, 17)
# =====================================================================================
def normalize_str_t1(s):
    """Bản của Task 1 (notebook cell 15): bỏ ký tự đặc biệt, không thêm '_'."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", str(s))
    s = re.sub(r"[̀-ͯ]", "", s)
    s = s.replace("đ", "d").replace("Đ", "d")
    return re.sub(r"[^a-zA-Z0-9]", "", s).lower()


def normalize_str(s):
    """Bản của Task 2/3 (notebook cell 17)."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", str(s))
    s = re.sub(r"[̀-ͯ]", "", s)
    s = s.replace("đ", "d").replace("Đ", "d")
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s)
    return s.strip("_").lower()


def district_full_name(row):
    """Tên huyện kèm loại đơn vị, đúng build_district_map (notebook cell 13)."""
    c_type = str(row.get("TYPE_2", "")).strip()
    c_name = str(row["NAME_2"]).strip()
    return f"{c_type} {c_name}" if c_type and c_type.lower() != "nan" else c_name




def build_ctx(row):
    row = dict(row)
    gid1, gid2 = str(row["GID_1"]), str(row["GID_2"])
    name1 = str(row["NAME_1"])
    dname_full = district_full_name(row)
    clean_pname = normalize_str(name1)
    clean_cname = normalize_str(dname_full)
    safe_gid2 = gid2.replace(".", "_")
    rel_sub = f"{gid1}_{clean_pname}/{gid2}_{clean_cname}"
    return {"row": row, "gid1": gid1, "gid2": gid2, "name1": name1, "dname_full": dname_full,
            "safe_gid2": safe_gid2,
            "rel_day_dir": f"{D_DAY}/{rel_sub}", "rel_night_dir": f"{D_NIGHT}/{rel_sub}"}


def day_name(ctx, period):
    year, month = period
    return f"{ctx['gid2']}_day_{year}{month:02d}.tif"


def night_name(ctx, period):
    year, month = period
    return f"{ctx['gid2']}_night_{year}{month:02d}.tif"


# =====================================================================================
# 4. EARTH ENGINE
# =====================================================================================
import ee

districts_fc = None
EE_CREDENTIALS = None


def init_earth_engine():
    global districts_fc, EE_CREDENTIALS
    kwargs = {"project": PROJECT_ID}
    if EE_HIGH_VOLUME:
        kwargs["opt_url"] = "https://earthengine-highvolume.googleapis.com"
    if EE_KEY_FILE:
        with open(EE_KEY_FILE, encoding="utf-8") as f:
            email = json.load(f)["client_email"]
        EE_CREDENTIALS = ee.ServiceAccountCredentials(email, EE_KEY_FILE)
        ee.Initialize(credentials=EE_CREDENTIALS, **kwargs)
        log.info(f"Earth Engine sẵn sàng: project={PROJECT_ID}, service account {email}, endpoint "
                 f"{'high-volume' if EE_HIGH_VOLUME else 'standard'}.")
    else:
        ee.Initialize(**kwargs)
        try:
            EE_CREDENTIALS = ee.data.get_persistent_credentials()
        except Exception:
            EE_CREDENTIALS = None
        log.info(f"Earth Engine sẵn sàng: project={PROJECT_ID} (tài khoản cá nhân).")
    ee.data.setDeadline(EE_DEADLINE_SEC * 1000)
    # _ee_call quản lý retry/cooldown chung; tránh SDK retry riêng trước khi gate nhận 429.
    ee.data.setMaxRetries(0)
    districts_fc = ee.FeatureCollection(ASSET_ID)


# ---------- Task 1: chép nguyên văn notebook cell 15 (print -> _nb_print, thêm tham số district_gid như bản [LOCAL]) ----------
def mask_s2_sr(img):
  qa = img.select("QA60")
  cloud_mask = (qa.bitwiseAnd(1 << 10).eq(0)).And(qa.bitwiseAnd(1 << 11).eq(0))
  return (
      img.updateMask(cloud_mask)
      .divide(10000)
      .select(
          ["B2", "B3", "B4", "B8", "B11", "B12"],
          ["BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2"],
      )
  )


def add_indices(img):
  ndvi = img.normalizedDifference(["NIR", "RED"]).rename("NDVI")
  ndbi = img.normalizedDifference(["SWIR1", "NIR"]).rename("NDBI")
  mndwi = img.normalizedDifference(["GREEN", "SWIR1"]).rename("MNDWI")
  bsi = img.expression(
      "((SWIR1 + RED) - (NIR + BLUE)) / ((SWIR1 + RED) + (NIR + BLUE))",
      {
          "SWIR1": img.select("SWIR1"),
          "RED": img.select("RED"),
          "NIR": img.select("NIR"),
          "BLUE": img.select("BLUE"),
      },
  ).rename("BSI")
  return img.addBands([ndvi, ndbi, mndwi, bsi])


# ---------- notebook cell 18 ----------
def mask_s2_clean(img):
  qa = img.select("QA60")
  cloud_mask = (qa.bitwiseAnd(1 << 10).eq(0)).And(qa.bitwiseAnd(1 << 11).eq(0))
  return (
      img.updateMask(cloud_mask)
      .divide(10000)
      .select(
          ["B2", "B3", "B4", "B8", "B11", "B12"],
          ["BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2"],
      )
  )




# ---------- Ngày tháng (đúng cách notebook tính s_date, e_date) ----------
def _month_dates(year, month):
  start = datetime(year, month, 1)
  end = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1)
  return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _s2_windows(year, month):
  """3 cửa sổ thời gian của get_adaptive_monthly_composite (notebook cell 18): tháng, ±15 ngày, ±30 ngày."""
  start, end = _month_dates(year, month)
  dt_start, dt_end = datetime.fromisoformat(start), datetime.fromisoformat(end)
  return [
      (dt_start.strftime("%Y-%m-%d"), dt_end.strftime("%Y-%m-%d")),
      ((dt_start - timedelta(days=15)).strftime("%Y-%m-%d"), (dt_end + timedelta(days=15)).strftime("%Y-%m-%d")),
      ((dt_start - timedelta(days=30)).strftime("%Y-%m-%d"), (dt_end + timedelta(days=30)).strftime("%Y-%m-%d")),
  ]


S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
VIIRS_A = "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG"
VIIRS_B = "NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG"


def ee_getinfo(obj):
  return _ee_call(obj.getInfo)


# ---------- Kế hoạch tải: 1 lần gọi cho cả 12 tháng ----------
def fetch_plan(district_fc, district_geom):
  """Số cảnh ảnh của từng cửa sổ (Task 2) và từng bộ VIIRS (Task 3.1) cho 12 tháng, cùng số huyện khớp trong asset.
  Python dùng các con số này để chọn nhánh y hệt các câu lệnh if trong notebook cell 18 và 34."""
  months = []
  for year, m in PERIODS:
    s2 = [ee.ImageCollection(S2_COLLECTION).filterBounds(district_geom).filterDate(s, e).size()
          for s, e in _s2_windows(year, m)]
    s_date, e_date = _month_dates(year, m)
    va = ee.ImageCollection(VIIRS_A).filterBounds(district_geom).filterDate(s_date, e_date).size()
    vb = ee.ImageCollection(VIIRS_B).filterBounds(district_geom).filterDate(s_date, e_date).size()
    months.append(ee.List(s2 + [va, vb]))
  out = ee_getinfo(ee.Dictionary({"n_fc": district_fc.size(), "months": ee.List(months)}))
  plan = {}
  for period, row in zip(PERIODS, out["months"]):
    c0, c1, c2, va, vb = row
    win = 0 if c0 > 0 else (1 if c1 > 0 else (2 if c2 > 0 else None))
    viirs = VIIRS_A if va > 0 else (VIIRS_B if vb > 0 else None)
    plan[period] = {"s2_window": win, "viirs": viirs}
  return out["n_fc"], plan


def day_image(period, window, district_geom):
  """= add_indices(get_adaptive_monthly_composite(...)).clip(district_geom) của notebook cell 18-19,
  với cửa sổ thời gian đã chọn ở fetch_plan."""
  s, e = _s2_windows(*period)[window]
  col = ee.ImageCollection(S2_COLLECTION).filterBounds(district_geom).filterDate(s, e)
  composite = col.map(mask_s2_clean).median()
  return add_indices(composite).clip(district_geom)


def night_image(period, collection_id, district_geom):
  """= get_viirs_monthly_composite(...) của notebook cell 34, rồi .toDouble() như cell 36."""
  s_date, e_date = _month_dates(*period)
  col = ee.ImageCollection(collection_id).filterBounds(district_geom).filterDate(s_date, e_date)
  return (col.select(["avg_rad", "cf_cvg"]).mean().clip(district_geom)
          .set("system:time_start", s_date).toDouble())


# ---------- Task 1: notebook cell 15, gom 12 tháng thành 1 lần gọi ----------
def task1_all_months(district_fc):
  """Mỗi tháng: lọc CLOUDY_PIXEL_PERCENTAGE < 85, nếu rỗng thì dùng toàn bộ cảnh; median; add_indices;
  reduceRegions(mean + stdDev, scale 50, tileScale 4, EPSG:4326). Tháng không có cảnh nào: bỏ (như notebook).
  Nhánh if/else của notebook chuyển thành ee.Algorithms.If phía máy chủ, cùng điều kiện, cùng kết quả."""
  bands = DAY_BANDS_ALL
  reducers = ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True)
  selected_cols = ["GID_2"] + T1_FEATURES
  per_month = []
  for year, m in PERIODS:
    s_date, e_date = _month_dates(year, m)
    raw_col = ee.ImageCollection(S2_COLLECTION).filterBounds(district_fc).filterDate(s_date, e_date)
    filtered_col = raw_col.filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 85))
    composite = ee.Image(ee.Algorithms.If(filtered_col.size().eq(0),
                                          raw_col.map(mask_s2_sr).median(),
                                          filtered_col.map(mask_s2_sr).median()))
    tensor = add_indices(composite)
    stats = tensor.select(bands).reduceRegions(
        collection=district_fc, reducer=reducers, scale=50, tileScale=4, crs="EPSG:4326", maxPixelsPerRegion=1e9)
    stats = stats.select(selected_cols).map(lambda f, year=year, m=m: f.set({"YEAR": year, "MONTH": m}))
    per_month.append(ee.FeatureCollection(ee.Algorithms.If(raw_col.size().gt(0), stats,
                                                           ee.FeatureCollection([]))))
  feats = ee_getinfo(ee.FeatureCollection(per_month).flatten())["features"]
  props = [f["properties"] for f in feats]
  indexed = {(int(p["YEAR"]), int(p["MONTH"])): p for p in props}
  for year, month in PERIODS:
    p = indexed.get((year, month), {})
    missing = [b for b in bands if _clean(p.get(f"{b}_mean")) is None]
    if not missing:
      continue
    log.warning(f"CSV day {year}-{month:02d}: thiếu mean {','.join(missing)}; thử toàn bộ cảnh của đúng tháng, vẫn mask QA60")
    s, e = _month_dates(year, month)
    raw = ee.ImageCollection(S2_COLLECTION).filterBounds(district_fc).filterDate(s, e)
    tensor = add_indices(raw.map(mask_s2_sr).median())
    stats = tensor.select(bands).reduceRegions(
        collection=district_fc, reducer=reducers.combine(ee.Reducer.count(), sharedInputs=True),
        scale=50, tileScale=4, crs="EPSG:4326", maxPixelsPerRegion=1e9)
    result = ee_getinfo(ee.Dictionary({"features": ee.Algorithms.If(raw.size().gt(0),
        stats.toList(stats.size()), ee.List([])), "scenes": raw.size()}))
    for feature in result.get("features", []):
      candidate = dict(feature["properties"], YEAR=year, MONTH=month)
      absent = [b for b in bands if _clean(candidate.get(f"{b}_mean")) is None]
      log.info(f"CSV day {year}-{month:02d}: cảnh={result.get('scenes', '?')}, "
               f"pixel={ {b: candidate.get(b + '_count', 0) for b in bands} }, thiếu mean={absent}")
      candidate["_diagnostic"] = (f"cảnh={result.get('scenes', '?')}; thiếu mean={','.join(absent)}; "
                                  f"pixel={ {b: candidate.get(b + '_count', 0) for b in bands} }")
      indexed[(year, month)] = candidate
  return list(indexed.values())


# ---------- Task 3.2: notebook cell 38, gom 12 tháng thành 1 lần gọi ----------
def task3_all_months(district_geom, row):
  reducers = (
      ee.Reducer.sum()
      .combine(ee.Reducer.mean(), sharedInputs=True)
      .combine(ee.Reducer.stdDev(), sharedInputs=True)
      .combine(ee.Reducer.min(), sharedInputs=True)
      .combine(ee.Reducer.max(), sharedInputs=True)
      .combine(ee.Reducer.count(), sharedInputs=True)
  )
  per_month = []
  for year, m in PERIODS:
    s_date, e_date = _month_dates(year, m)
    col_a = ee.ImageCollection(VIIRS_A).filterBounds(district_geom).filterDate(s_date, e_date)
    col_b = ee.ImageCollection(VIIRS_B).filterBounds(district_geom).filterDate(s_date, e_date)
    col = ee.ImageCollection(ee.Algorithms.If(col_a.size().eq(0), col_b, col_a))
    img = col.mean().clip(district_geom)
    rad = img.select("avg_rad")
    cf_cvg = img.select("cf_cvg")
    lit_mask = rad.gte(1.5).rename("is_lit")
    lit_rad = rad.updateMask(lit_mask).rename("lit_rad")
    kw = dict(geometry=district_geom, scale=500, maxPixels=1e9, tileScale=4, crs="EPSG:4326")
    d = ee.Dictionary({
        "n": col.size(),
        "all": rad.reduceRegion(reducer=reducers, **kw),
        "lit": lit_rad.reduceRegion(reducer=ee.Reducer.sum(), **kw),
        "cnt": lit_mask.reduceRegion(reducer=ee.Reducer.sum(), **kw),
        "cf": cf_cvg.reduceRegion(reducer=ee.Reducer.mean(), **kw),
    })
    per_month.append(ee.Algorithms.If(col.size().gt(0), d, ee.Dictionary({"n": 0})))
  out = ee_getinfo(ee.Dictionary({"area_ha": district_geom.area(maxError=1).divide(10000),
                                  "months": ee.List(per_month)}))
  district_area_ha = out["area_ha"]

  # Phần tính chỉ số dưới đây chép nguyên văn notebook cell 38
  records = []
  for (yr, m), mo in zip(PERIODS, out["months"]):
    if not mo or mo.get("n", 0) == 0:
      records.append({**{k: row[k] for k in ADM_COLS}, "YEAR": yr, "MONTH": m,
                      "TIME": f"{yr}-{m:02d}", "DATA_STATUS": "no_data", "ERROR": "Không có ảnh VIIRS"})
      continue
    stats_all = mo.get("all") or {}
    stats_lit = mo.get("lit") or {}
    lit_pixel_count = (mo.get("cnt") or {}).get("is_lit", 0)
    cloud_free_obs = (mo.get("cf") or {}).get("cf_cvg", 0)

    total_pixels = stats_all.get("avg_rad_count", 0)
    tnl = stats_all.get("avg_rad_sum", 0.0) or 0.0
    mean_rad = stats_all.get("avg_rad_mean", 0.0) or 0.0
    std_rad = stats_all.get("avg_rad_stdDev", 0.0) or 0.0
    min_rad = stats_all.get("avg_rad_min", 0.0) or 0.0
    max_rad = stats_all.get("avg_rad_max", 0.0) or 0.0
    lit_pop_proxy = (stats_lit.get("lit_rad", 0.0) or 0.0)
    electrification_ratio = (
        (lit_pixel_count / total_pixels * 100.0) if total_pixels > 0 else 0.0
    )
    lit_area_ha = lit_pixel_count * 25.0
    spatial_cv = (std_rad / mean_rad) if mean_rad > 0 else 0.0

    if not total_pixels:
      records.append({**{k: row[k] for k in ADM_COLS}, "YEAR": yr, "MONTH": m,
                      "TIME": f"{yr}-{m:02d}", "DATA_STATUS": "no_data", "ERROR": "VIIRS không có pixel hợp lệ"})
      continue
    records.append({
        **{k: row[k] for k in ADM_COLS},
        "YEAR": yr,
        "MONTH": m,
        "TIME": f"{yr}-{m:02d}",
        "DISTRICT_AREA_HA": round(district_area_ha, 2),
        "TNL": round(tnl, 4),
        "MEAN_RAD": round(mean_rad, 4),
        "STD_RAD": round(std_rad, 4),
        "MIN_RAD": round(min_rad, 4),
        "MAX_RAD": round(max_rad, 4),
        "SPATIAL_CV": round(spatial_cv, 4),
        "LIT_PIXELS": int(lit_pixel_count),
        "LIT_AREA_HA": round(lit_area_ha, 2),
        "ELECTRIFICATION_RATIO_PCT": round(electrification_ratio, 2),
        "LIT_POP_PROXY": round(lit_pop_proxy, 4),
        "CLOUD_FREE_OBS": round(cloud_free_obs, 1),
        "DATA_STATUS": "ok", "ERROR": "",
    })

  df_ntl = pd.DataFrame(records)
  df_ntl = df_ntl.reindex(columns=NIGHT_COLUMNS)
  df_ntl["TNL"] = pd.to_numeric(df_ntl["TNL"], errors="coerce")
  df_ntl["TNL_MA3"] = df_ntl["TNL"].rolling(window=3, min_periods=1).mean()
  df_ntl["TNL_MOM_GROWTH_PCT"] = df_ntl["TNL"].pct_change(fill_method=None) * 100.0
  return df_ntl


# =====================================================================================
# 5. TẢI ẢNH (getDownloadURL như notebook cell 21) + CHIA Ô KHI QUÁ HẠN MỨC
# =====================================================================================
_dl_lock = threading.Lock()
_dl_stats = {"ok": 0, "fail": 0, "last_err": ""}
_PERMANENT_ERR = ("401", "403", "forbidden", "unauthorized", "permission denied", "permission_denied",
                  "not authorized", "caller does not have permission")
_TOO_LARGE_ERR = ("must be less than or equal to", "request size", "too large", "request payload size",
                  "user memory limit", "pixel grid dimensions")


class PermanentError(RuntimeError):
    pass


class TooLargeError(RuntimeError):
    pass


class _RetryableEEError(RuntimeError):
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after_seconds(value):
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return 0.0


def _wait_ee_cooldown():
    while True:
        check_stop()
        with _ee_cooldown_lock:
            remaining = _ee_cooldown_until - time.monotonic()
        if remaining <= 0:
            return
        STOP_EVENT.wait(min(remaining, 60))


def _ee_call(call, max_retry=EE_MAX_RETRIES):
    """Một hạn mức cho getInfo, tạo URL và tải ảnh; mọi luồng cùng nghỉ khi gặp 429."""
    global _ee_cooldown_until
    last = None
    for attempt in range(max_retry):
        check_stop()
        with EE_SEM:
            _wait_ee_cooldown()
            try:
                return call()
            except (ee.EEException, requests.RequestException, _RetryableEEError) as exc:
                kind = _classify(str(exc))
                if kind == "too_large":
                    raise TooLargeError(str(exc)) from exc
                if kind == "permanent":
                    raise PermanentError(str(exc)) from exc
                last = exc
                delay = max(min(60, 5 * 2 ** attempt) + random.uniform(0, 5),
                            _retry_after_seconds(getattr(exc, "retry_after", None)))
                if kind == "rate_limit":
                    if hasattr(EE_SEM, "reduce"):
                        old, new = EE_SEM.reduce(restricted="restricted" in str(exc).lower())
                        if new < old:
                            log.warning(f"[quota] Giảm số yêu cầu EE đồng thời {old} -> {new}; giữ mức này đến hết lượt")
                    with _ee_cooldown_lock:
                        _ee_cooldown_until = max(_ee_cooldown_until, time.monotonic() + delay)
        if attempt + 1 < max_retry:
            log.warning(f"Earth Engine {'HTTP 429 / quá hạn mức' if kind == 'rate_limit' else 'lỗi tạm thời'}: "
                        f"chờ {delay:.1f}s, thử lại {attempt + 2}/{max_retry}.")
            STOP_EVENT.wait(delay)
    raise RuntimeError(f"Earth Engine thất bại sau {max_retry} lần: {last}") from last


def _dl_record(ok, err=None):
    trip = False
    with _dl_lock:
        if ok:
            _dl_stats["ok"] += 1
        else:
            _dl_stats["fail"] += 1
            _dl_stats["last_err"] = str(err)[:500]
            trip = _dl_stats["ok"] == 0 and _dl_stats["fail"] >= DOWNLOAD_FAIL_LIMIT
    if trip:
        log.error(f"{DOWNLOAD_FAIL_LIMIT} lượt tải liên tiếp thất bại, chưa có lượt nào thành công. "
                  f"Lỗi gần nhất: {_dl_stats['last_err']}")
        request_stop("fatal")


def _http_get(url, timeout=600):
    r = requests.get(url, timeout=timeout)
    if r.status_code in (401, 403) and EE_CREDENTIALS is not None:
        try:
            from google.auth.transport.requests import AuthorizedSession
            r2 = AuthorizedSession(EE_CREDENTIALS).get(url, timeout=timeout)
            if r2.status_code < 400:
                return r2
            r = r2
        except Exception as exc:
            log.debug(f"AuthorizedSession lỗi: {exc}")
    return r


def _classify(msg):
    low = msg.lower()
    if re.search(r"\b429\b", low) or "too many requests" in low or "concurrency limit" in low:
        return "rate_limit"
    if any(k in low for k in _TOO_LARGE_ERR):
        return "too_large"
    if any(k in low for k in _PERMANENT_ERR):
        return "permanent"
    return "transient"


def fetch_geotiff_bytes(img, region, scale, max_retry=EE_MAX_RETRIES):
    """Đúng tham số notebook cell 21. Trả bytes GeoTIFF; lỗi nào cũng kèm mã HTTP và nội dung."""
    def fetch_once():
        url = img.getDownloadURL({"region": region, "scale": scale, "crs": "EPSG:4326",
                                  "format": "GEO_TIFF", "filePerBand": False})
        r = _http_get(url)
        if r.status_code >= 400:
            body = (r.text or "")[:400].replace("\n", " ")
            msg = f"HTTP {r.status_code}: {body}"
            if r.status_code in (401, 403):
                raise PermanentError(msg)
            raise _RetryableEEError(msg, r.headers.get("Retry-After"))
        data = r.content
        if data[:2] == b"PK":                       # đôi khi EE trả về file zip (notebook cell 21)
            z = zipfile.ZipFile(io.BytesIO(data))
            data = z.read([n for n in z.namelist() if n.lower().endswith(".tif")][0])
        if len(data) < 200:
            raise _RetryableEEError(f"file tải về chỉ {len(data)} byte")
        return data
    return _ee_call(fetch_once, max_retry)


def _grid_offset(a, b, res):
    """Số pixel lệch giữa hai gốc tọa độ; phải là số nguyên nếu cùng lưới."""
    k = (a - b) / res
    if abs(k - round(k)) > 1e-3:
        raise RuntimeError(f"Các ô ảnh không cùng lưới pixel (lệch {k:.4f} pixel). Không ghép để tránh sai giá trị.")
    return int(round(k))


def mosaic_tiles(tile_bytes_list):
    """Ghép các ô GeoTIFF cùng lưới pixel thành một mảng. Không resample: chỉ đặt từng ô vào đúng vị trí."""
    import rasterio
    tiles = []
    for data in tile_bytes_list:
        with rasterio.MemoryFile(data) as mf, mf.open() as src:
            tiles.append({"arr": src.read(), "tr": src.transform, "crs": src.crs, "nodata": src.nodata,
                          "dtype": src.dtypes[0], "desc": src.descriptions, "h": src.height, "w": src.width})
    t0 = tiles[0]
    resx, resy = t0["tr"].a, t0["tr"].e
    for t in tiles:
        if abs(t["tr"].a - resx) > 1e-12 or abs(t["tr"].e - resy) > 1e-12 or t["dtype"] != t0["dtype"] \
                or t["arr"].shape[0] != t0["arr"].shape[0]:
            raise RuntimeError("Các ô ảnh khác độ phân giải, kiểu dữ liệu hoặc số kênh: không ghép.")
    left = min(t["tr"].c for t in tiles)
    top = max(t["tr"].f for t in tiles)
    pos = []
    for t in tiles:
        col = _grid_offset(t["tr"].c, left, resx)
        row = _grid_offset(t["tr"].f, top, resy)
        pos.append((row, col))
    H = max(r + t["h"] for (r, _c), t in zip(pos, tiles))
    W = max(c + t["w"] for (_r, c), t in zip(pos, tiles))
    fill = t0["nodata"] if t0["nodata"] is not None else 0
    out = np.full((t0["arr"].shape[0], H, W), fill, dtype=t0["dtype"])
    filled = np.zeros((H, W), dtype=bool)
    for (r, c), t in zip(pos, tiles):
        a = t["arr"]
        if t["nodata"] is not None:
            valid = ~np.all((a == t["nodata"]) | np.isnan(a) if np.issubdtype(a.dtype, np.floating)
                            else (a == t["nodata"]), axis=0)
        else:
            valid = np.ones(a.shape[1:], dtype=bool)
        sub = out[:, r:r + t["h"], c:c + t["w"]]
        seen = filled[r:r + t["h"], c:c + t["w"]]
        # Phần chồng lấn giữa hai ô phải có giá trị trùng nhau (cùng lưới, cùng ảnh)
        both = seen & valid
        if both.any() and not np.allclose(sub[:, both], a[:, both], equal_nan=True, rtol=0, atol=0):
            raise RuntimeError("Phần chồng lấn giữa các ô ảnh không trùng giá trị: không ghép.")
        write = valid | ~seen
        sub[:, write] = a[:, write]
        seen |= valid
    from rasterio.transform import Affine
    transform = Affine(resx, 0, left, 0, resy, top)
    return out, transform, t0["crs"], t0["nodata"], t0["desc"]


def mosaic_tile_files(paths, target):
    """Ghép theo block trên đĩa, kiểm tra lưới/chồng lấn chính xác, không resample."""
    import rasterio
    from rasterio.transform import Affine
    from rasterio.windows import Window
    metadata = []
    for path in paths:
        with rasterio.open(path) as src:
            metadata.append(dict(path=path, tr=src.transform, crs=src.crs, count=src.count,
                                 dtype=src.dtypes[0], nodata=src.nodata, desc=src.descriptions,
                                 width=src.width, height=src.height))
    if not metadata:
        raise RuntimeError("Không có ô để ghép")
    first = metadata[0]
    resx, resy = first['tr'].a, first['tr'].e
    if resx <= 0 or resy >= 0:
        raise RuntimeError("Lưới TIFF không có hướng north-up")
    for tile in metadata:
        if (tile['crs'] != first['crs'] or tile['count'] != first['count']
                or tile['dtype'] != first['dtype'] or abs(tile['tr'].a-resx)>1e-12
                or abs(tile['tr'].e-resy)>1e-12 or tile['tr'].b or tile['tr'].d):
            raise RuntimeError("Các ô khác CRS, kiểu, số kênh hoặc độ phân giải: không ghép")
        a, b = tile['nodata'], first['nodata']
        same_nodata = a == b or (a is not None and b is not None and np.isnan(a) and np.isnan(b))
        if not same_nodata:
            raise RuntimeError("Các ô khác NoData: không ghép")
    left = min(t['tr'].c for t in metadata)
    top = max(t['tr'].f for t in metadata)
    for tile in metadata:
        tile['col'] = _grid_offset(tile['tr'].c, left, resx)
        tile['row'] = _grid_offset(tile['tr'].f, top, resy)
    height=max(t['row']+t['height'] for t in metadata)
    width=max(t['col']+t['width'] for t in metadata)
    profile=dict(driver='GTiff',width=width,height=height,count=first['count'],dtype=first['dtype'],
                 crs=first['crs'],transform=Affine(resx,0,left,0,resy,top),nodata=first['nodata'],
                 compress='DEFLATE',zlevel=TIFF_ZLEVEL,predictor=3 if np.issubdtype(np.dtype(first['dtype']),np.floating) else 2,
                 tiled=True,blockxsize=256,blockysize=256,BIGTIFF='IF_SAFER')
    previous=[]
    with rasterio.open(target,'w+',**profile) as dst:
        # Khởi tạo block để khoảng không được phủ có đúng NoData, không đọc toàn ảnh vào RAM.
        fill=first['nodata'] if first['nodata'] is not None else 0
        for _, win in dst.block_windows(1):
            dst.write(np.full((first['count'],int(win.height),int(win.width)),fill,dtype=first['dtype']),window=win)
        for tile in metadata:
            check_stop()
            with rasterio.open(tile['path']) as src:
                for _, win in src.block_windows(1):
                    a=src.read(window=win,masked=True)
                    if np.issubdtype(a.dtype,np.floating):
                        a=np.ma.masked_invalid(a)
                    valid=np.any(~np.ma.getmaskarray(a),axis=0)
                    r,c=tile['row']+int(win.row_off),tile['col']+int(win.col_off)
                    h,w=int(win.height),int(win.width)
                    dest_win=Window(c,r,w,h)
                    old=dst.read(window=dest_win,masked=True)
                    if np.issubdtype(old.dtype,np.floating):
                        old=np.ma.masked_invalid(old)
                    seen=np.zeros((h,w),dtype=bool)
                    for prev in previous:
                        r0,c0=max(r,prev['row']),max(c,prev['col'])
                        r1,c1=min(r+h,prev['row']+prev['height']),min(c+w,prev['col']+prev['width'])
                        if r1>r0 and c1>c0:
                            seen[r0-r:r1-r,c0-c:c1-c]=True
                    both=seen & valid & np.any(~np.ma.getmaskarray(old),axis=0)
                    if both.any() and not np.array_equal(old.data[:,both],a.data[:,both],equal_nan=True):
                        raise RuntimeError("Phần chồng lấn khác giá trị: không ghép")
                    out=old.data.copy()
                    write=valid | ~seen
                    out[:,write]=a.data[:,write]
                    dst.write(out,window=dest_win)
            previous.append(tile)
        for i, desc in enumerate(first['desc'],1):
            if desc:dst.set_band_description(i,desc)


def compare_on_grid(a_ref, tr_ref, a_new, tr_new):
    """a_new phải cùng lưới với a_ref, trùng giá trị ở phần chung, phần thừa (nếu có) chỉ là NoData/0."""
    if abs(tr_ref.a - tr_new.a) > 1e-12 or abs(tr_ref.e - tr_new.e) > 1e-12:
        raise RuntimeError("khác kích thước pixel")
    c = _grid_offset(tr_ref.c, tr_new.c, tr_new.a)
    r = _grid_offset(tr_ref.f, tr_new.f, tr_new.e)
    if r < 0 or c < 0 or r + a_ref.shape[1] > a_new.shape[1] or c + a_ref.shape[2] > a_new.shape[2]:
        raise RuntimeError(f"ảnh ghép không phủ hết ảnh gốc (lệch {r},{c})")
    win = a_new[:, r:r + a_ref.shape[1], c:c + a_ref.shape[2]]
    if not np.array_equal(win, a_ref, equal_nan=True):
        raise RuntimeError("giá trị pixel khác nhau ở phần chung")
    extra = np.ones(a_new.shape[1:], dtype=bool)
    extra[r:r + a_ref.shape[1], c:c + a_ref.shape[2]] = False
    if extra.any():
        e = a_new[:, extra]
        if np.any(np.nan_to_num(e, nan=0.0) != 0):
            raise RuntimeError("phần viền thừa có giá trị khác NoData")
    return True


def write_tif(path, arr, transform, crs, nodata, desc):
    import rasterio
    profile = {"driver": "GTiff", "height": arr.shape[1], "width": arr.shape[2], "count": arr.shape[0],
               "dtype": arr.dtype, "crs": crs, "transform": transform, "nodata": nodata,
               "compress": "DEFLATE", "zlevel": TIFF_ZLEVEL,
               "predictor": 3 if np.issubdtype(arr.dtype, np.floating) else 2,
               "tiled": True, "blockxsize": 256, "blockysize": 256, "BIGTIFF": "IF_SAFER"}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr)
        for i, d in enumerate(desc or [], start=1):
            if d:
                dst.set_band_description(i, d)


_COMP = []


def _best_compression():
    """ZSTD (nhỏ hơn DEFLATE ~5-10%) nếu GDAL hỗ trợ, nếu không thì DEFLATE mức 9. Cả hai đều không mất dữ liệu."""
    if not _COMP:
        import rasterio
        try:
            with rasterio.MemoryFile() as mf, mf.open(driver="GTiff", width=8, height=8, count=1, dtype="int16",
                                                      compress="ZSTD", zstd_level=19) as d:
                d.write(np.zeros((1, 8, 8), "int16"))
            _COMP.append({"compress": "DEFLATE", "zlevel": TIFF_ZLEVEL})   # DEFLATE: mọi phần mềm GIS đọc được
        except Exception:
            _COMP.append({"compress": "DEFLATE", "zlevel": TIFF_ZLEVEL})
    return _COMP[0]


def quantize_day(arr, nodata):
    a = arr.astype("float64")
    invalid = ~np.isfinite(a)
    if nodata is not None:
        invalid |= arr == nodata
    q = np.round(np.where(invalid, 0, a) * DAY_SCALE_INV)
    if np.any((np.abs(q) > 32767) & ~invalid):
        raise RuntimeError(f"Giá trị ngoài miền Int16 với scale {1.0 / DAY_SCALE_INV:g}; không tự cắt giá trị. Dùng TIFF float cho dữ liệu này.")
    q = q.astype("int16")
    q[invalid] = DAY_NODATA
    return q


def write_day_int16(path, arr, transform, crs, nodata, desc):
    """Ảnh ngày: lưu reflectance/chỉ số dưới dạng int16 = round(giá trị × DAY_SCALE_INV), scale ghi trong file.
    Với 10000: sai số tối đa 0,00005 (nửa bước 1e-4, bằng độ chính xác gốc của Sentinel-2 SR). NoData = -32768."""
    q = quantize_day(arr, nodata)
    import rasterio
    profile = {"driver": "GTiff", "height": q.shape[1], "width": q.shape[2], "count": q.shape[0], "dtype": "int16",
               "crs": crs, "transform": transform, "nodata": DAY_NODATA, "predictor": 2,
               "tiled": True, "BIGTIFF": "IF_SAFER", "blockxsize": 256, "blockysize": 256, **_best_compression()}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(q)
        dst.scales = [1.0 / DAY_SCALE_INV] * q.shape[0]
        dst.offsets = [0.0] * q.shape[0]
        dst.update_tags(SCALE_FACTOR=str(1.0 / DAY_SCALE_INV),
                        NOTE=f"value = DN * {1.0 / DAY_SCALE_INV:g}; NoData = {DAY_NODATA}")
        for i, d in enumerate(desc or [], start=1):
            if d:
                dst.set_band_description(i, d)


def convert_day_file(source, target):
    """Lượng tử hóa theo block; không giữ cả TIFF huyện trong RAM."""
    import rasterio
    with rasterio.open(source) as src:
        profile = src.profile.copy()
        profile.update(dtype="int16", nodata=DAY_NODATA, compress="DEFLATE", predictor=2,
                       zlevel=TIFF_ZLEVEL, tiled=True, blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER")
        with rasterio.open(target, "w", **profile) as dst:
            for _, window in src.block_windows(1):
                dst.write(quantize_day(src.read(window=window), src.nodata), window=window)
            dst.scales = [1.0 / DAY_SCALE_INV] * src.count
            dst.offsets = [0.0] * src.count
            dst.update_tags(SCALE_FACTOR=str(1.0 / DAY_SCALE_INV), NOTE="value = DN * scale; CSV tính trên float gốc")
            for i, desc in enumerate(src.descriptions, 1):
                if desc:
                    dst.set_band_description(i, desc)


def _rewrite_bytes_to_tif(data, path, writer):
    import rasterio
    with rasterio.MemoryFile(data) as mf, mf.open() as src:
        arr, tr, crs, nd, desc = src.read(), src.transform, src.crs, src.nodata, src.descriptions
    writer(path, arr, tr, crs, nd, desc)


def _bbox(region):
    coords = ee_getinfo(region.bounds(maxError=1))["coordinates"][0]
    xs, ys = [c[0] for c in coords], [c[1] for c in coords]
    return min(xs), min(ys), max(xs), max(ys)


def _split_bbox(bbox, n):
    x0, y0, x1, y1 = bbox
    dx, dy = (x1 - x0) / n, (y1 - y0) / n
    return [ee.Geometry.Rectangle([x0 + i * dx, y0 + j * dy, x0 + (i + 1) * dx, y0 + (j + 1) * dy],
                                  "EPSG:4326", False)
            for j in range(n) for i in range(n)]


def download_tif(img, region, scale, path, label, writer=write_tif, force_tiles=0):
    """Tải ảnh về `path`. Nếu vượt hạn mức thì chia ô (cùng scale, cùng lưới) rồi ghép.
    Trả số ô đã dùng (1 = tải nguyên). Mọi thất bại đều được ném ra kèm nguyên nhân."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    try:
        if not force_tiles:
            try:
                data = fetch_geotiff_bytes(img, region, scale)
                _rewrite_bytes_to_tif(data, tmp, writer)
                os.replace(tmp, path)
                _dl_record(True)
                return 1
            except TooLargeError as exc:
                m = re.search(r"\((\d+)\s*bytes\)", str(exc))
                ratio = (int(m.group(1)) / (32 * 1024 * 1024)) if m else 4
                n = max(2, math.ceil(math.sqrt(ratio * 1.3)))
                log.info(f"{label}: vượt hạn mức tải, chia {n}x{n} ô (giữ nguyên scale={scale})")
        else:
            n = force_tiles
        if not TILING_OK[0]:
            raise RuntimeError(f"{label}: ảnh vượt hạn mức tải nhưng bước kiểm tra chia ô ở preflight không đạt, "
                               f"nên không ghép ô để tránh sai lưới pixel. Huyện này cần xử lý riêng.")
        bbox = _bbox(region)
        while n <= MAX_TILE_SPLIT:
            try:
                with tempfile.TemporaryDirectory(prefix="vngis_tiles_") as tile_dir:
                    paths = []
                    for i, rect in enumerate(_split_bbox(bbox, n)):
                        check_stop()
                        data = fetch_geotiff_bytes(img, rect, scale)
                        tile_path = os.path.join(tile_dir, f"{i}.tile")
                        with open(tile_path, "wb") as f:
                            f.write(data)
                        paths.append(tile_path)
                    if writer is write_tif:
                        mosaic_tile_files(paths, tmp)
                    elif writer is write_day_int16:
                        float_path = os.path.join(tile_dir, "mosaic.tif")
                        mosaic_tile_files(paths, float_path)
                        convert_day_file(float_path, tmp)
                    else:
                        parts = []
                        for tile_path in paths:
                            with open(tile_path, "rb") as f:
                                parts.append(f.read())
                        arr, tr, crs, nd, desc = mosaic_tiles(parts)
                        writer(tmp, arr, tr, crs, nd, desc)
                os.replace(tmp, path)
                _dl_record(True)
                return n * n
            except TooLargeError:
                n += 1
                log.info(f"{label}: ô vẫn quá lớn, tăng lên {n}x{n}")
        raise RuntimeError(f"{label}: vẫn vượt hạn mức khi đã chia {MAX_TILE_SPLIT}x{MAX_TILE_SPLIT} ô")
    except StopRequested:
        raise
    except Exception as exc:
        _dl_record(False, exc)
        raise
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def inspect_tif(path, expect_bands):
    """Đọc lại file vừa ghi. Trả (ok, empty, ghi_chú)."""
    import rasterio
    try:
        with rasterio.open(path) as src:
            if src.count != expect_bands:
                return False, False, f"có {src.count} kênh, cần {expect_bands}"
            if src.crs is None or src.crs.to_epsg() != 4326:
                return False, False, f"CRS {src.crs}"
            for _, window in src.block_windows(1):
                a = src.read(window=window, masked=True)
                if np.issubdtype(a.dtype, np.floating):
                    a = np.ma.masked_invalid(a)
                if a.count():
                    return True, False, ""
            return True, True, ""
    except Exception as exc:
        return False, False, f"không đọc được: {exc}"



def _write_csv(df, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path + ".part", index=False, encoding="utf-8-sig")
    os.replace(path + ".part", path)


# =====================================================================================
# 7. XỬ LÝ MỘT XÃ
# =====================================================================================
class NotInAsset(RuntimeError):
    pass


ADMIN_DF = None      # bảng hành chính GADM (vai trò gdf_cleaned trong notebook)
ADMIN_BY_GID = {}
_parts_lock = threading.Lock()
PARTS_STAMP = None


def append_parts(kind, records):
    """Ghi chỉ số của 1 huyện vào file .jsonl của lượt này; CSV toàn quốc được dựng lại từ các file này."""
    with _parts_lock:
        os.makedirs(L(D_PARTS), exist_ok=True)
        with open(L(D_PARTS, f"{kind}_{PARTS_STAMP}.jsonl"), "a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps({**r, "_profile": OUTPUT_PROFILE}, ensure_ascii=False,
                                   default=lambda o: None) + "\n")


def _clean(v):
    if isinstance(v, (np.floating, float)) and not np.isfinite(v):
        return None
    if isinstance(v, np.generic):
        return v.item()
    return v


def existing_day_source(ctx, period):
    """Đường dẫn thật trên Drive; hỗ trợ thư mục/tên GID đã chuẩn hóa của bản cũ."""
    canonical = f"{ctx['rel_day_dir']}/{day_name(ctx, period)}"
    if canonical in REMOTE_TIFS:
        return canonical
    year, month = period
    names = {day_name(ctx, period), f"{ctx['safe_gid2']}_day_{year}{month:02d}.tif"}
    candidates = sorted(rel for rel in REMOTE_TIFS
                        if rel.startswith(D_DAY + "/") and rel.rsplit("/", 1)[-1] in names)
    if len(candidates) > 1:
        raise RuntimeError(f"Nhiều TIFF cũ cùng huyện/tháng, không tự chọn: {candidates}")
    return candidates[0] if candidates else None


def reuse_day_tif(ctx, period, path, label):
    """Trả kết quả chuyển file có thật; None nghĩa là cần tải lại ảnh từ EE."""
    with _sync_lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        source = path
        try:
            if not os.path.isfile(path):
                rel = existing_day_source(ctx, period)
                if rel is None:
                    log.warning(f"{label}: trạng thái cũ có TIFF nhưng không thấy file trên Drive; tải lại tháng này từ EE")
                    return None
                source = path + ".source.part"
                copied = _rclone(["copyto", f"{REMOTE_BASE}/{rel}", source,
                                   "--retries", "1", "--low-level-retries", "2"],
                                  timeout=1800, missing_ok=True)
                if copied is None:
                    REMOTE_TIFS.discard(rel)
                    REMOTE_INT16_TIFS.discard(rel)
                    log.warning(f"{label}: TIFF cũ đã mất sau lúc liệt kê Drive; tải lại tháng này từ EE")
                    return None
                if not copied:
                    raise RuntimeError(f"Không đọc được TIFF trên Drive (quyền/token/kết nối): {rel}")
            import rasterio
            with rasterio.open(source) as src:
                already = all(d == "int16" for d in src.dtypes) and all(
                    abs(s - 1.0 / DAY_SCALE_INV) < 1e-12 for s in src.scales)
            if already:
                if source != path:
                    os.replace(source, path)
            else:
                convert_day_file(source, path + ".part")
                os.replace(path + ".part", path)
            ok, empty, note = inspect_tif(path, DAY_BANDS)
            if not ok:
                raise RuntimeError(note)
            log.info(f"{label}: dùng TIFF đã có, chuyển Int16; không tải lại từ EE")
            return 1, empty
        finally:
            for leftover in (path + ".source.part", path + ".part"):
                if os.path.isfile(leftover):
                    os.remove(leftover)


def _download_month(kind, ctx, period, img, path):
    label = f"[{ctx['gid2']}] {kind} {month_key(period)}"
    if kind == "day":
        if DAY_FORMAT == "int16" and month_key(period) in ctx.get("convert_day_months", []):
            reused = reuse_day_tif(ctx, period, path, label)
            if reused is not None:
                return reused
        n = download_tif(img, img_region(ctx), DAY_IMAGE_SCALE, path, label,
                         writer=write_day_int16 if DAY_FORMAT == "int16" else write_tif,
                         force_tiles=(ctx.get("tile_hints") or {}).get(kind, 0))
        ok, empty, note = inspect_tif(path, DAY_BANDS)
    else:
        n = download_tif(img, img_region(ctx), 500, path, label, writer=write_tif,
                         force_tiles=(ctx.get("tile_hints") or {}).get(kind, 0))
        ok, empty, note = inspect_tif(path, 2)
    if not ok:
        raise RuntimeError(f"file kiểm tra lỗi: {note}")
    if n > 1:
        hints = ctx.setdefault("tile_hints", {})
        hints[kind] = max(hints.get(kind, 0), math.ceil(math.sqrt(n)))
    log.info(f"{label}: {'no_data' if empty else 'OK'}, {n} ô, {os.path.getsize(path)/1024/1024:.1f} MB")
    return n, empty


def img_region(ctx):
    return ctx["geom"]


def current_status(st):
    return bool(st) and st.get("profile") == OUTPUT_PROFILE and st.get("period") == PERIOD_ID


def district_complete(st):
    return current_status(st) and all(
        all((st.get(slot) or {}).get(key) == "ok" for key in MONTH_KEYS)
        for slot in ("t2", "t3img", "t1_by_month", "t3csv_by_month")
    )


def day_records(row, props):
    indexed = {}
    for p in props:
        if p.get("GID_2") != row["GID_2"]:
            raise RuntimeError("Task 1 trả về GID_2 khác huyện đang xử lý")
        period = (int(p["YEAR"]), int(p["MONTH"]))
        if period in PERIODS:
            indexed[period] = p
    records = []
    for year, month in PERIODS:
        p = indexed.get((year, month))
        r = {**{k: row[k] for k in ADM_COLS}, "YEAR": year, "MONTH": month}
        r.update({k: _clean(p.get(k)) if p else None for k in T1_FEATURES})
        valid = all(r[f"{band}_mean"] is not None for band in DAY_BANDS_ALL)
        r.update(DATA_STATUS="ok" if valid else "no_data",
                 ERROR="" if valid else "Thiếu mean: " + ",".join(
                     b for b in DAY_BANDS_ALL if r[f"{b}_mean"] is None) +
                     "; " + (p.get("_diagnostic", "Không có pixel hợp lệ hoặc không có cảnh") if p else "Không có cảnh"))
        records.append(r)
    return records


def _checkpoint(info):
    info["status"] = "done" if district_complete(info) else "partial"
    write_status(info)


def process_district(row, prev):
    check_stop()
    t_start = time.time()
    ctx = build_ctx(row)
    gid2 = ctx["gid2"]
    prev = prev if current_status(prev) else {}
    ctx["convert_day_months"] = list(prev.get("convert_day_months", []))
    ctx["tile_hints"] = {kind: max([0] + [math.ceil(math.sqrt(n))
        for key, n in (prev.get("tiles_used") or {}).items() if key.startswith(kind + "_")])
        for kind in ("day", "night")}
    info = {"gid_2": gid2, "gid_1": ctx["gid1"], "run_id": RUN_ID,
            "period": PERIOD_ID, "profile": OUTPUT_PROFILE, "schema": SCHEMA_ID,
            "attempts": int(prev.get("attempts", 0)),
            "t1": prev.get("t1", "pending"), "t3csv": prev.get("t3csv", "pending"),
            "t1_by_month": dict(prev.get("t1_by_month") or {}),
            "t3csv_by_month": dict(prev.get("t3csv_by_month") or {}),
            "t2": dict(prev.get("t2") or {}), "t3img": dict(prev.get("t3img") or {}),
            "empty_months_t2": list(prev.get("empty_months_t2") or []),
            "tiles_used": dict(prev.get("tiles_used") or {}), "day_bands": DAY_BANDS, "errors": []}
    info["convert_day_months"] = list(ctx["convert_day_months"])
    if prev.get("recovery_revision"):
        info["recovery_revision"] = prev["recovery_revision"]
    fc = districts_fc.filter(ee.Filter.eq("GID_2", gid2))
    geom = fc.geometry()
    ctx["geom"] = geom
    _checkpoint(info)
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix=f"{gid2}-q") as qp:
        f_plan = qp.submit(fetch_plan, fc, geom)
        f_t1 = qp.submit(task1_all_months, fc) if info["t1"] != "ok" else None
        f_t3 = qp.submit(task3_all_months, geom, row) if info["t3csv"] != "ok" else None
        n_fc, plan = f_plan.result()
        if n_fc != 1:
            raise NotInAsset(f"GID_2 {gid2} khớp {n_fc} bản ghi trong asset {ASSET_ID}; cần đúng một huyện")

        jobs = []
        for period in PERIODS:
            key = month_key(period)
            for kind, slot, choice in (("day", "t2", plan[period]["s2_window"]),
                                       ("night", "t3img", plan[period]["viirs"])):
                if info[slot].get(key) == "ok":
                    continue
                if choice is None:
                    info[slot][key] = "no_data"
                    info["errors"].append(f"{kind} {key}: không có cảnh ảnh")
                    continue
                if kind == "day":
                    img = day_image(period, choice, geom).select(DAY_BANDS_ALL[:DAY_BANDS])
                    path = L(ctx["rel_day_dir"], day_name(ctx, period))
                else:
                    img = night_image(period, choice, geom)
                    path = L(ctx["rel_night_dir"], night_name(ctx, period))
                jobs.append((kind, period, img, path))
        _checkpoint(info)
        with ThreadPoolExecutor(max_workers=MONTH_THREADS, thread_name_prefix=f"{gid2}-m") as mp:
            futures = {mp.submit(_download_month, kind, ctx, period, img, path): (kind, period)
                       for kind, period, img, path in jobs}
            for fut in as_completed(futures):
                kind, period = futures[fut]
                key = month_key(period)
                slot = info["t2"] if kind == "day" else info["t3img"]
                try:
                    n, empty = fut.result()
                    slot[key] = "no_data" if empty else "ok"
                    if kind == "day" and key in info["convert_day_months"]:
                        info["convert_day_months"].remove(key)
                    if empty:
                        info["errors"].append(f"{kind} {key}: TIFF không có pixel hợp lệ")
                        if kind == "day" and key not in info["empty_months_t2"]:
                            info["empty_months_t2"].append(key)
                    if n > 1:
                        info["tiles_used"][f"{kind}_{key}"] = n
                except (StopRequested, PermanentError):
                    raise
                except Exception as exc:
                    slot[key] = "fail"
                    info["errors"].append(f"{kind} {key}: {type(exc).__name__}: {str(exc)[:200]}")
                _checkpoint(info)

        for kind, future, label, slot in (("day", f_t1, "t1", "t1_by_month"),
                                           ("night", f_t3, "t3csv", "t3csv_by_month")):
            if future is None:
                continue
            try:
                result = future.result()
                records = day_records(row, result) if kind == "day" else result.to_dict("records")
                records = [{k: _clean(val) for k, val in rec.items()} for rec in records]
                keys = {month_key((int(r["YEAR"]), int(r["MONTH"]))) for r in records}
                if keys != set(MONTH_KEYS) or len(records) != len(PERIODS):
                    raise RuntimeError(f"CSV {kind} không có đúng một dòng cho mỗi tháng của khoảng chạy")
                append_parts(kind, records)
                info[slot] = {month_key((r["YEAR"], r["MONTH"])): r["DATA_STATUS"] for r in records}
                info[label] = "ok" if all(v == "ok" for v in info[slot].values()) else "missing"
                info[f"{label}_months"] = sum(v == "ok" for v in info[slot].values())
                if info[label] != "ok":
                    info["errors"].append(f"CSV {kind}: thiếu dữ liệu ở " +
                                          ", ".join(k for k, val in info[slot].items() if val != "ok"))
            except StopRequested:
                raise
            except Exception as exc:
                info[label] = "fail"
                info["errors"].append(f"CSV {kind}: {type(exc).__name__}: {str(exc)[:200]}")
            _checkpoint(info)
    info["status"] = "done" if district_complete(info) else "partial"
    info["seconds"] = round(time.time() - t_start, 1)
    info["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return info

# =====================================================================================
# 7b. CSV TOÀN QUỐC (dựng lại từ _control/parts sau mỗi lượt)
# =====================================================================================
def _read_parts(kind):
    rows = []
    for p in sorted(glob.glob(L(D_PARTS, f"{kind}_*.jsonl"))):
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    return rows


def part_current(kind, record):
    return record.get("_profile") == OUTPUT_PROFILE or (
        kind == "night" and DAY_IMAGE_SCALE == 20 and DAY_FORMAT == "int16" and record.get("_profile") == LEGACY_FLOAT_PROFILE)


def build_national_csv():
    os.makedirs(L(D_CSV), exist_ok=True)
    for kind, rel, cols in (("day", DAY_CSV, DAY_COLUMNS), ("night", NIGHT_CSV, NIGHT_COLUMNS)):
        rows = _read_parts(kind)
        if not rows:
            continue
        rows = [r for r in rows if part_current(kind, r)
                and (int(r.get("YEAR", 0)), int(r.get("MONTH", 0))) in PERIODS
                and (not ADMIN_BY_GID or r.get("GID_2") in ADMIN_BY_GID)]
        if not rows:
            continue
        df = pd.DataFrame(rows).reindex(columns=cols)
        df = df.drop_duplicates(subset=["GID_2", "YEAR", "MONTH"], keep="last")
        for c in ("YEAR", "MONTH", "LIT_PIXELS"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
        df["_k"] = df["GID_2"].map(lambda g: tuple(natural_sort_key(g)))
        df = df.sort_values(["_k", "YEAR", "MONTH"]).drop(columns="_k")
        path = L(rel)
        df.to_csv(path + ".part", index=False, encoding="utf-8-sig")
        os.replace(path + ".part", path)
        log.info(f"{rel}: {len(df):,} dòng, {df['GID_2'].nunique():,} huyện")


# =====================================================================================
# 8. TRẠNG THÁI (mỗi lượt một file .jsonl trong _control/status, bản ghi sau cùng thắng)
# =====================================================================================
_status_lock = threading.Lock()
STATUS_FILE = None
RESUME_DIAGNOSTICS = {}


def write_status(info):
    line = json.dumps(info, ensure_ascii=False, default=str)
    with _status_lock:
        os.makedirs(L(D_STATUS), exist_ok=True)
        with open(STATUS_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def load_all_status():
    global RESUME_DIAGNOSTICS
    out = {}
    files = sorted(glob.glob(L(D_STATUS, "status_*.jsonl")))
    ignored = 0
    for p in files:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(d, dict) and "gid_2" in d:
                        d = migrate_float_status(d)
                    if isinstance(d, dict) and "gid_2" in d and current_status(d):
                        out[d["gid_2"]] = d
                    elif isinstance(d, dict) and "gid_2" in d:
                        ignored += 1
        except OSError:
            continue
    part_keys = {
        kind: {(r.get("GID_2"), month_key((int(r["YEAR"]), int(r["MONTH"]))))
               for r in _read_parts(kind) if part_current(kind, r)
               and r.get("DATA_STATUS") == "ok"}
        for kind in ("day", "night")
    }
    # Cùng khóa với uploader: không nhìn thấy khoảng trống giữa move và cập nhật REMOTE_TIFS.
    with _sync_lock:
        if RESTORE_INT16_MARKER:
            recovered = set()
            for gid, st in out.items():
                row = ADMIN_BY_GID.get(gid)
                if row is None:
                    continue
                ctx = build_ctx(row)
                for period in PERIODS:
                    key = month_key(period)
                    if (st.get("t2") or {}).get(key) != "ok" or key in st.get("convert_day_months", []):
                        continue
                    rel = f"{ctx['rel_day_dir']}/{day_name(ctx, period)}"
                    if rel in REMOTE_TIFS and rel not in REMOTE_INT16_TIFS:
                        recovered.add(rel)
            if recovered:
                REMOTE_INT16_TIFS.update(recovered)
                log.warning(f"[resume] Khôi phục marker cho {len(recovered)} TIFF ngày 50m từ checkpoint "
                            "cùng profile Int16 và file thực có trên Drive; không tải lại EE.")
        restored = {gid: reconcile_status(st, part_keys) for gid, st in out.items()}
    RESUME_DIAGNOSTICS = {"files": len(files), "ignored": ignored,
                          "claimed_done": sum(district_complete(st) for st in out.values()),
                          "day_parts": len(part_keys["day"]), "night_parts": len(part_keys["night"])}
    return restored


def check_resume(targets, statuses):
    """Báo bằng chứng khôi phục; không âm thầm làm lại toàn bộ khi mất checkpoint."""
    gids = set(targets["GID_2"])
    known = sum(gid in statuses for gid in gids)
    done = sum(district_complete(statuses.get(gid)) for gid in gids)
    diag = RESUME_DIAGNOSTICS
    log.info(f"[resume] Đích {REMOTE_BASE} | profile={OUTPUT_PROFILE}")
    log.info(f"[resume] {diag.get('files', 0)} file checkpoint; {known}/{len(gids)} huyện có trạng thái; "
             f"{done} huyện đã hoàn tất, {len(gids)-done} huyện chưa đủ dữ liệu.")
    log.info(f"[resume] Drive: {len(REMOTE_TIFS)} TIFF, {len(REMOTE_INT16_TIFS)} TIFF có marker Int16; "
             f"CSV parts hợp lệ: ngày={diag.get('day_parts', 0)}, đêm={diag.get('night_parts', 0)}; "
             f"bản ghi khác profile/kỳ bị bỏ qua={diag.get('ignored', 0)}.")
    lost_checkpoint = bool(REMOTE_TIFS) and known == 0
    lost_evidence = diag.get("claimed_done", 0) > 0 and done == 0 and MODE == "full"
    if lost_checkpoint or lost_evidence:
        message = ("Drive đã có dữ liệu/checkpoint nhưng không khôi phục được huyện hoàn tất. "
                   "Dừng để tránh tự tải lại toàn bộ. Kiểm tra đúng tài khoản Drive, thư mục 20m/50m/pilot, "
                   "_control/status, _control/parts, int16_uploaded.json và bước đồng bộ cuối của lượt trước. "
                   "Không xóa dữ liệu cũ. Chỉ đặt VNGIS_DISTRICTS_ALLOW_FULL_RESTART=true nếu chủ động muốn chạy lại toàn bộ.")
        if not ALLOW_FULL_RESTART:
            raise RuntimeError(message)
        log.warning("[resume] " + message + " Đã cho phép chạy lại toàn bộ theo cấu hình.")


def migrate_float_status(st):
    if DAY_IMAGE_SCALE != 20 or DAY_FORMAT != "int16" or st.get("profile") != LEGACY_FLOAT_PROFILE or st.get("period") != PERIOD_ID:
        return st
    st = dict(st)
    old_day = dict(st.get("t2") or {})
    st.update(profile=OUTPUT_PROFILE, status="partial", attempts=0,
              t1="pending", t1_by_month={},
              convert_day_months=[k for k, val in old_day.items() if val == "ok"],
              t2={k: "pending" if val == "ok" else val for k, val in old_day.items()})
    return st


REMOTE_TIFS = set()
REMOTE_INT16_TIFS = set()
RESTORE_INT16_MARKER = False


def reconcile_status(st, part_keys=None):
    """Không bỏ qua TIFF đã ghi trạng thái nhưng chưa được lưu bền vững trên Drive."""
    row = ADMIN_BY_GID.get(st["gid_2"])
    if row is None:
        return st
    st = {**st, "t2": dict(st.get("t2") or {}), "t3img": dict(st.get("t3img") or {})}
    ctx = build_ctx(row)
    conversions = set(st.get("convert_day_months", []))
    missing_conversion = False
    for period in PERIODS:
        key = month_key(period)
        for slot, folder, name in (("t2", "rel_day_dir", day_name), ("t3img", "rel_night_dir", night_name)):
            rel = f"{ctx[folder]}/{name(ctx, period)}"
            if slot == "t2" and key in conversions and not os.path.isfile(L(rel)) and existing_day_source(ctx, period) is None:
                conversions.remove(key)
                st[slot][key] = "pending"
                missing_conversion = True
            if (slot == "t2" and DAY_FORMAT == "int16" and st[slot].get(key) == "ok"
                    and not os.path.isfile(L(rel)) and rel in REMOTE_TIFS and rel not in REMOTE_INT16_TIFS):
                st[slot][key] = "pending"
                conversions.add(key)
                st["attempts"] = 0
            if st[slot].get(key) == "ok" and rel not in REMOTE_TIFS and not os.path.isfile(L(rel)):
                st[slot][key] = "pending"
                # Mất file chưa đồng bộ không tiêu tốn thêm số lần thử dữ liệu.
                st["attempts"] = 0
    st["convert_day_months"] = sorted(conversions)
    legacy_copy_error = bool(conversions) and any(
        "Không tải được TIFF đã có để chuyển Int16" in error for error in st.get("errors", []))
    if (missing_conversion or legacy_copy_error) and st.get("recovery_revision") != "missing-source-v1":
        # Một lần phục hồi cho lỗi copyto cũ; lỗi dữ liệu sau đó vẫn chịu MAX_ATTEMPTS.
        st["attempts"] = 0
        st["recovery_revision"] = "missing-source-v1"
    if part_keys is not None:
        for kind, slot, label in (("day", "t1_by_month", "t1"), ("night", "t3csv_by_month", "t3csv")):
            st[slot] = dict(st.get(slot) or {})
            for key in MONTH_KEYS:
                if st[slot].get(key) == "ok" and (st["gid_2"], key) not in part_keys[kind]:
                    st[slot][key] = "pending"
                    st[label] = "pending"
                    st["attempts"] = 0
    st["status"] = "done" if district_complete(st) else ("partial" if st.get("status") == "done" else st.get("status"))
    return st


def core_finished(st):
    return current_status(st) and (district_complete(st) or st.get("status") == "not_in_asset"
                         or int(st.get("attempts", 0)) >= MAX_ATTEMPTS)



# =====================================================================================
# 9. RCLONE
# =====================================================================================
RCLONE_COMMON = ["--transfers", "4", "--checkers", "8", "--tpslimit", "8",
                 "--retries", "5", "--low-level-retries", "20", "--stats-log-level", "NOTICE"]


def _rclone(args, timeout=6 * 3600, quiet=False, missing_ok=False):
    try:
        res = subprocess.run(["rclone", *args], capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        log.warning(f"rclone {' '.join(args[:2])} lỗi: {exc}")
        return False
    if res.returncode != 0 and missing_ok and (res.returncode in (3, 4) or any(
            msg in res.stderr.lower() for msg in ("directory not found", "object not found", "file not found",
                                                   "source doesn't exist"))):
        return None
    if res.returncode != 0 and not quiet:
        log.warning(f"rclone {' '.join(args[:3])} lỗi: {res.stderr.strip()[-400:]}")
    return res.returncode == 0


_sync_lock = threading.Lock()


def rclone_sync_once(final=False):
    """TIF: move (rclone chỉ xóa bản trên máy sau khi đã kiểm tra kích thước/hash bản trên Drive).
    CSV, trạng thái, log: copy."""
    if not os.path.isdir(LOCAL_ROOT):
        return True
    success = True
    with _sync_lock:
        # --sync-only chạy trong Python mới: nạp marker bền vững trước khi ghi lại,
        # tránh xóa danh sách đã upload chỉ vì tập hợp trong RAM bắt đầu rỗng.
        marker = L(D_CONTROL, "int16_uploaded.json")
        if DAY_FORMAT == "int16" and os.path.isfile(marker):
            with open(marker, encoding="utf-8") as f:
                saved = json.load(f)
            if not isinstance(saved, list) or not all(isinstance(p, str) for p in saved):
                raise RuntimeError("Marker Int16 không hợp lệ; không ghi đè trạng thái đã lưu.")
            REMOTE_INT16_TIFS.update(saved)
        # rclone mới không cho kết hợp --files-from với --min-age (cùng nhóm filter).
        # Chọn file đã ổn định >= 2 phút trước khi tạo danh sách, final lấy mọi TIFF.
        cutoff = None if final else time.time() - 120
        for d in (D_DAY, D_NIGHT):
            src = L(d)
            if os.path.isdir(src):
                candidates = list(glob.glob(os.path.join(src, "**", "*.tif"), recursive=True))
                if cutoff is not None:
                    candidates = [p for p in candidates if os.path.getmtime(p) <= cutoff]
                int16_candidates = []
                if d == D_DAY and DAY_FORMAT == "int16":
                    import rasterio
                    for p in candidates:
                        with rasterio.open(p) as tif:
                            if all(dtype == "int16" for dtype in tif.dtypes) and all(
                                    abs(scale - 1.0 / DAY_SCALE_INV) < 1e-12 for scale in tif.scales):
                                int16_candidates.append(p)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".files") as snapshot:
                    snapshot.write("\n".join(os.path.relpath(p, src).replace(os.sep, "/") for p in candidates))
                    snapshot.flush()
                    ok = _rclone(["move", src, f"{REMOTE_BASE}/{d}", "--files-from", snapshot.name,
                                  *RCLONE_COMMON]) if candidates else True
                success = ok and success
                # rclone move chỉ xóa file đã upload thành công, kể cả khi một file khác lỗi.
                REMOTE_TIFS.update(os.path.relpath(p, LOCAL_ROOT).replace(os.sep, "/")
                                   for p in candidates if not os.path.isfile(p))
                REMOTE_INT16_TIFS.update(os.path.relpath(p, LOCAL_ROOT).replace(os.sep, "/")
                                         for p in int16_candidates if not os.path.isfile(p))
        if DAY_FORMAT == "int16":
            os.makedirs(L(D_CONTROL), exist_ok=True)
            marker = L(D_CONTROL, "int16_uploaded.json")
            with open(marker + ".part", "w", encoding="utf-8") as f:
                json.dump(sorted(REMOTE_INT16_TIFS), f)
            os.replace(marker + ".part", marker)
        for d in (D_CSV, D_CONTROL):
            src = L(d)
            if os.path.isdir(src):
                success = _rclone(["copy", src, f"{REMOTE_BASE}/{d}", "--filter", "- *.part", *RCLONE_COMMON]) and success
    return success


class Uploader(threading.Thread):
    def __init__(self):
        super().__init__(name="uploader", daemon=True)
        self.stop_event = threading.Event()

    def run(self):
        last_stop_check = 0
        while not self.stop_event.wait(min(UPLOAD_EVERY_SEC, 60)):
            now = time.time()
            if now - last_stop_check >= DRIVE_STOP_POLL_SEC:
                last_stop_check = now
                if drive_stop_exists():
                    request_stop("drive_stop")
            if now - getattr(self, "_last_sync", 0) >= UPLOAD_EVERY_SEC:
                self._last_sync = now
                try:
                    if rclone_sync_once():
                        log.info("Đã đồng bộ lên Drive (định kỳ).")
                    else:
                        log.warning("Đồng bộ Drive chưa hoàn tất; sẽ thử lại, giữ file chưa tải lên trên máy.")
                except Exception as exc:
                    log.warning(f"Đồng bộ định kỳ lỗi: {exc}")


def drive_stop_exists():
    try:
        res = subprocess.run(["rclone", "lsf", f"{REMOTE_BASE}/{D_CONTROL}", "--files-only"],
                             capture_output=True, text=True, timeout=120)
        return res.returncode == 0 and "STOP" in [x.strip() for x in res.stdout.splitlines()]
    except Exception:
        return False


def init_storage():
    global REMOTE_TIFS, REMOTE_INT16_TIFS, RESTORE_INT16_MARKER
    for d in (LOCAL_ROOT, L(D_STATUS), L(D_PARTS), L(D_LOGS), CACHE_DIR):
        os.makedirs(d, exist_ok=True)
    if shutil.which("rclone") is None:
        raise RuntimeError("Chưa cài rclone.")
    if not _rclone(["mkdir", f"{REMOTE_BASE}/{D_STATUS}"], timeout=180):
        raise RuntimeError(f"rclone không ghi được vào '{REMOTE_BASE}'. Kiểm tra secret RCLONE_CONF.")
    manifest = {"schema": SCHEMA_ID, "period": PERIOD_ID, "profile": OUTPUT_PROFILE,
                "level": 2, "months": MONTH_KEYS}
    old_manifest = subprocess.run(["rclone", "cat", f"{REMOTE_BASE}/{D_CONTROL}/pipeline.json"],
                                  capture_output=True, text=True, timeout=180)
    matched_manifest = old_manifest.returncode == 0 and json.loads(old_manifest.stdout) == manifest
    if old_manifest.returncode == 0 and not matched_manifest:
        old = json.loads(old_manifest.stdout)
        if DAY_IMAGE_SCALE != 20 or DAY_FORMAT != "int16" or old != {**manifest, "profile": LEGACY_FLOAT_PROFILE}:
            raise RuntimeError("Thư mục Drive có cấu hình cấp hành chính/thời gian khác. Chọn thư mục đầu ra mới.")
        log.info("Nâng cấp thư mục float cũ: giữ TIFF đêm/CSV đêm, chuyển TIFF ngày đã có sang Int16, tính lại CSV ngày.")
    if old_manifest.returncode != 0 and not any(s in old_manifest.stderr.lower() for s in ("not found", "doesn't exist")):
        raise RuntimeError("Không kiểm tra được manifest Drive: " + old_manifest.stderr[-200:])
    with open(L(D_CONTROL, "pipeline.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)
    for d in (D_STATUS, D_PARTS):        # vài file nhỏ: trạng thái và chỉ số của các lượt trước
        res = subprocess.run(["rclone", "copy", f"{REMOTE_BASE}/{d}", L(d), "--update"],
                             capture_output=True, text=True, timeout=3600)
        if res.returncode != 0 and "directory not found" not in res.stderr:
            raise RuntimeError(f"Không kéo được {d} từ Drive: {res.stderr.strip()[-300:]}")
    listing = subprocess.run(["rclone", "lsf", REMOTE_BASE, "--recursive", "--files-only", "--include", "*.tif"],
                             capture_output=True, text=True, timeout=3600)
    if listing.returncode != 0:
        raise RuntimeError("Không kiểm tra được TIFF trên Drive: " + listing.stderr[-200:])
    REMOTE_TIFS = set(listing.stdout.splitlines())
    log.info(f"[resume] Đã kéo checkpoint từ {REMOTE_BASE}: "
             f"{len(glob.glob(L(D_STATUS, 'status_*.jsonl')))} file trạng thái, "
             f"{len(glob.glob(L(D_PARTS, '*.jsonl')))} file CSV parts, {len(REMOTE_TIFS)} TIFF trên Drive.")
    if DAY_FORMAT == "int16":
        marker = subprocess.run(["rclone", "cat", f"{REMOTE_BASE}/{D_CONTROL}/int16_uploaded.json"],
                                capture_output=True, text=True, timeout=180)
        if marker.returncode == 0:
            REMOTE_INT16_TIFS = set(json.loads(marker.stdout)) & REMOTE_TIFS
        elif any(s in marker.stderr.lower() for s in ("not found", "doesn't exist")):
            REMOTE_INT16_TIFS = set()
        else:
            raise RuntimeError("Không kiểm tra được trạng thái TIFF Int16 trên Drive: " + marker.stderr[-200:])
        RESTORE_INT16_MARKER = matched_manifest and DAY_IMAGE_SCALE == 50 and not REMOTE_INT16_TIFS
        if RESTORE_INT16_MARKER:
            log.warning("[resume] Marker Int16 rỗng/thiếu trong thư mục 50m có manifest khớp; "
                        "sẽ đối chiếu checkpoint cùng profile và TIFF trên Drive để phục hồi.")
    # Cảnh báo nếu đích còn cấu trúc của bản pipeline cũ
    old = subprocess.run(["rclone", "lsf", REMOTE_BASE, "--dirs-only"], capture_output=True, text=True, timeout=120)
    if any(x.strip("/") in ("03_Provinces", "04_Status", "1_Task1_Spectral_Indices", "2_Task2_Day_S2")
           for x in old.stdout.splitlines()):
        log.warning(f"Thư mục '{DRIVE_FOLDER}' trên Drive còn dữ liệu của bản pipeline cũ. "
                    f"Nên xóa thư mục cũ rồi chạy lại để không lẫn dữ liệu.")


# =====================================================================================
# =====================================================================================
# 10. DANH SÁCH XÃ (GADM 4.1, giống notebook cell 3; đọc thẳng file .dbf, không cần geopandas)
# =====================================================================================
def read_dbf(path, encoding="utf-8"):
    """Đọc bảng thuộc tính dBase của shapefile (chỉ cần để lấy cột hành chính)."""
    with open(path, "rb") as f:
        head = f.read(32)
        n_rec, hdr_len, rec_len = struct.unpack("<IHH", head[4:12])
        fields = []
        while True:
            d = f.read(32)
            if not d or d[0] == 0x0D:
                break
            name = d[:11].split(b"\x00")[0].decode("ascii")
            fields.append((name, d[16]))
        f.seek(hdr_len)
        rows = []
        for _ in range(n_rec):
            rec = f.read(rec_len)
            if not rec or rec[0:1] == b"*":
                continue
            pos, row = 1, {}
            for name, size in fields:
                row[name] = rec[pos:pos + size].decode(encoding, errors="replace").strip()
                pos += size
            rows.append(row)
    return pd.DataFrame(rows)


def build_admin_table():
    idx_csv = os.path.join(CACHE_DIR, "gadm41_VNM_2_admin.csv")
    if os.path.isfile(idx_csv):
        return pd.read_csv(idx_csv, dtype=str, keep_default_na=False)
    os.makedirs(CACHE_DIR, exist_ok=True)
    zip_path = os.path.join(CACHE_DIR, "gadm41_VNM_shp.zip")
    if not os.path.isfile(zip_path):
        log.info("Tải ranh giới GADM 4.1 (một lần, sau đó dùng cache)...")
        r = requests.get(GADM_VNM_URL, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=900)
        r.raise_for_status()
        with open(zip_path + ".part", "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
        os.replace(zip_path + ".part", zip_path)
    with zipfile.ZipFile(zip_path) as z:
        z.extract("gadm41_VNM_2.dbf", CACHE_DIR)
        cpg = "gadm41_VNM_2.cpg"
        enc = z.read(cpg).decode().strip() if cpg in z.namelist() else "utf-8"
    enc = "utf-8" if enc.upper().replace("-", "") in ("UTF8", "") else enc
    tbl = read_dbf(os.path.join(CACHE_DIR, "gadm41_VNM_2.dbf"), enc)[ADM_COLS].drop_duplicates("GID_2")
    tbl.to_csv(idx_csv, index=False, encoding="utf-8-sig")
    return pd.read_csv(idx_csv, dtype=str, keep_default_na=False)


def natural_sort_key(gid_str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(gid_str))]


def load_targets(admin):
    """Full lấy toàn bộ GADM cấp 2; pilot chọn xen kẽ huyện và đơn vị đô thị."""
    df = admin.iloc[sorted(range(len(admin)), key=lambda i: natural_sort_key(admin.iloc[i]["GID_2"]))]
    df = df.reset_index(drop=True)
    if MODE == "full":
        return df
    kinds = df["TYPE_2"].str.strip().str.lower()
    pools = [list(df.index[kinds == "huyện"]), list(df.index[kinds != "huyện"])]
    picks = []
    while len(picks) < PILOT_N and any(pools):
        for pool in pools:
            if pool and len(picks) < PILOT_N:
                picks.append(pool.pop(0))
        if PILOT_N >= 6 and len(picks) >= 2:
            # Pilot lớn lấy thêm các huyện phân bố trên cả nước để đo tốc độ thực tế.
            goal = min(PILOT_N, len(df))
            for i in np.linspace(0, len(df)-1, goal-1, dtype=int)[1:]:
                if int(i) not in picks:
                    picks.append(int(i))
            for i in df.index:
                if len(picks) >= goal:
                    break
                if int(i) not in picks:
                    picks.append(int(i))
            break
    return df.loc[sorted(picks)].reset_index(drop=True)


# =====================================================================================
# =====================================================================================
# 11. PREFLIGHT
# =====================================================================================
class PreflightError(RuntimeError):
    pass


PREFLIGHT_HINT = (
    "Gợi ý: (1) HTTP 401/403 hoặc 'permission': cấp role 'Earth Engine Resource Writer' (roles/earthengine.writer) "
    "và 'Service Usage Consumer' (roles/serviceusage.serviceUsageConsumer) cho service account, đăng ký project "
    "với Earth Engine; (2) lỗi quota: kiểm tra quota project và các workflow đang dùng chung project; "
    "(3) lỗi rclone: kiểm tra RCLONE_CONF và dung lượng Drive.")


def _probe_drive():
    probe = L(D_CONTROL, "preflight_probe.txt")
    stamp = f"{RUN_ID} {datetime.now(timezone.utc).isoformat()}"
    with open(probe, "w", encoding="utf-8") as f:
        f.write(stamp)
    if not _rclone(["copyto", probe, f"{REMOTE_BASE}/{D_CONTROL}/preflight_probe.txt"], timeout=300):
        raise PreflightError("rclone không ghi được lên Drive.")
    res = subprocess.run(["rclone", "cat", f"{REMOTE_BASE}/{D_CONTROL}/preflight_probe.txt"],
                         capture_output=True, text=True, timeout=300)
    if res.returncode != 0 or res.stdout.strip() != stamp:
        raise PreflightError(f"Đọc lại file thử trên Drive không khớp: {res.stderr.strip()[-200:]}")
    about = subprocess.run(["rclone", "about", RCLONE_REMOTE + ":", "--json"],
                           capture_output=True, text=True, timeout=120)
    if about.returncode == 0:
        try:
            quota = json.loads(about.stdout)
            if "free" in quota:
                return f"Drive OK; còn {int(quota['free'])/1024**3:.1f} GiB trống"
        except (ValueError, TypeError):
            pass
    return "Drive OK; chưa đọc được dung lượng trống"


def _probe_ee(row):
    gid2 = row["GID_2"]
    fc = districts_fc.filter(ee.Filter.eq("GID_2", gid2))
    geom = fc.geometry()
    n_fc, plan = fetch_plan(fc, geom)
    if n_fc != 1:
        raise PreflightError(f"Asset khớp {n_fc} bản ghi cho {gid2}, cần đúng một huyện. Kiểm tra GID_2.")
    region = geom.centroid(maxError=1).buffer(1500)
    m_day = next((m for m in PERIODS if plan[m]["s2_window"] is not None), None)
    m_night = next((m for m in PERIODS if plan[m]["viirs"] is not None), None)
    if m_day is None or m_night is None:
        raise PreflightError(f"Huyện thử {gid2} không có ảnh Sentinel-2 hoặc VIIRS nào trong khoảng {START_MONTH}–{END_MONTH}.")
    img = day_image(m_day, plan[m_day]["s2_window"], geom).select(DAY_BANDS_ALL[:DAY_BANDS]).clip(region)
    try:
        whole = fetch_geotiff_bytes(img, region, DAY_IMAGE_SCALE)
        night = fetch_geotiff_bytes(night_image(m_night, plan[m_night]["viirs"], geom).clip(region), region, 500)
    except Exception as exc:
        raise PreflightError(f"Tải ảnh thử thất bại: {exc}")
    import rasterio
    with rasterio.MemoryFile(whole) as mf, mf.open() as src:
        if src.count != DAY_BANDS:
            raise PreflightError(f"Ảnh ngày có {src.count} kênh, cần {DAY_BANDS}.")
        a_whole, tr_whole = src.read(), src.transform
    msg = f"ảnh ngày {len(whole)/1024:.0f} KB, ảnh đêm {len(night)/1024:.0f} KB"
    if PREFLIGHT_TILE_TEST:
        try:
            parts = [fetch_geotiff_bytes(img, rect, DAY_IMAGE_SCALE) for rect in _split_bbox(_bbox(region), 2)]
            a_tiled, tr_tiled, *_ = mosaic_tiles(parts)
            compare_on_grid(a_whole, tr_whole, a_tiled, tr_tiled)
            msg += "; chia ô trùng khớp từng pixel"
        except Exception as exc:
            TILING_OK[0] = False
            raise PreflightError(f"Kiểm tra chia ô không đạt; không ghép ảnh huyện sai lưới: {exc}") from exc
    else:
        msg += "; bỏ qua kiểm tra chia ô (chế độ thí điểm)"
    return msg


def preflight(row):
    """Kiểm tra Earth Engine và Drive song song."""
    log.info(f"[preflight] Kiểm tra Earth Engine (huyện {row['GID_2']}) và Google Drive...")
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_ee, f_dr = ex.submit(_probe_ee, row), ex.submit(_probe_drive)
        msg_ee, msg_dr = f_ee.result(), f_dr.result()
    log.info(f"[preflight] ĐẠT: {msg_ee}; {msg_dr}.")


# =====================================================================================
# 12. TIẾN ĐỘ
# =====================================================================================
def write_progress(targets, statuses):
    rows = []
    for r in targets.itertuples():
        st = statuses.get(r.GID_2) or {}
        t2 = st.get("t2") or {}
        t3 = st.get("t3img") or {}
        rows.append({"GID_1": r.GID_1, "NAME_1": r.NAME_1, "GID_2": r.GID_2, "NAME_2": r.NAME_2,
                     "TYPE_2": r.TYPE_2, "period": PERIOD_ID,
                     "status": st.get("status", "pending"), "attempts": st.get("attempts", 0),
                     "t1": st.get("t1"), "t2_ok": sum(v == "ok" for v in t2.values()),
                     "t2_no_data": sum(v == "no_data" for v in t2.values()),
                     "t3img_ok": sum(v == "ok" for v in t3.values()), "t3csv": st.get("t3csv"),
                     "t3img_no_data": sum(v == "no_data" for v in t3.values()),
                     "t1_ok": sum(v == "ok" for v in (st.get("t1_by_month") or {}).values()),
                     "t3csv_ok": sum(v == "ok" for v in (st.get("t3csv_by_month") or {}).values()),
                     "seconds": st.get("seconds"), "finished_at": st.get("finished_at"),
                     "errors": " | ".join(st.get("errors") or [])[:500]})
    df = pd.DataFrame(rows)
    _write_csv(df, L(D_CONTROL, "progress.csv"))
    return df


# 13. VÒNG CHẠY
# =====================================================================================
OUTAGE_STREAK = 10
OUTAGE_SLEEP_SEC = 900
MAX_OUTAGES = 8


def next_round_jobs(gids, rows, statuses):
    return [(g, rows[g], "full") for g in gids if not core_finished(statuses.get(g))]


class DistrictRestPolicy:
    """Đếm huyện mới hoàn tất trong lượt; dùng toàn bộ GADM để xác nhận hết tỉnh."""
    def __init__(self, rows, statuses):
        self.provinces = {}
        self.names = {}
        self.province_by_gid = {}
        for row in rows:
            province, gid = row["GID_1"], row["GID_2"]
            self.provinces.setdefault(province, set()).add(gid)
            self.names[province] = row["NAME_1"]
            self.province_by_gid[gid] = province
        self.done = {gid for gid in self.province_by_gid if district_complete(statuses.get(gid))}
        self.finished_provinces = {p for p, gids in self.provinces.items() if gids <= self.done}
        self.new_done = 0

    def observe(self, gid, info):
        if gid in self.done or gid not in self.province_by_gid or info.get("status") != "done" or not district_complete(info):
            return []
        self.done.add(gid)
        self.new_done += 1
        reasons = []
        if REST_EVERY_N and self.new_done % REST_EVERY_N == 0:
            reasons.append(f"đã hoàn tất {self.new_done} huyện mới trong lượt (mỗi {REST_EVERY_N} huyện)")
        province = self.province_by_gid[gid]
        if province not in self.finished_provinces and self.provinces[province] <= self.done:
            self.finished_provinces.add(province)
            if REST_AFTER_PROVINCE:
                reasons.append(f"đã hoàn tất tỉnh {self.names[province]} ({len(self.provinces[province])} huyện)")
        return reasons


def run_round(jobs, statuses, rest_policy=None):
    """jobs: list (gid, row, kind)."""
    if rest_policy is None:
        rows = {**ADMIN_BY_GID, **{gid: row for gid, row, _ in jobs}}
        rest_policy = DistrictRestPolicy(rows.values(), statuses)
    t0 = time.time()
    done_now = 0
    completed_now = 0
    pending_fail = []
    outage = False
    pool = ThreadPoolExecutor(max_workers=N_WORKERS, thread_name_prefix="w")
    futures = {}
    for gid, row, kind in jobs:
        futures[pool.submit(process_district, row, statuses.get(gid))] = (gid, kind)
    handled = set()

    def consume(fut):
        nonlocal done_now, completed_now
        handled.add(fut)
        if fut.cancelled():
            return
        gid, kind = futures[fut]
        prev = statuses.get(gid) or {}
        attempts = int(prev.get("attempts", 0)) + 1
        try:
            info = fut.result()
        except StopRequested:
            return
        except NotInAsset as exc:
            info = {"gid_2": gid, "period": PERIOD_ID, "profile": OUTPUT_PROFILE, "status": "not_in_asset", "attempts": MAX_ATTEMPTS, "errors": [str(exc)],
                    "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            statuses[gid] = info
            write_status(info)
            log.error(f"[{gid}] {exc}")
            return
        except PermanentError as exc:
            log.error(f"[{gid}] lỗi quyền truy cập: {exc}")
            _dl_record(False, exc)
            pending_fail.append((gid, exc, attempts))
            return
        except Exception as exc:
            pending_fail.append((gid, exc, attempts))
            log.warning(f"[{gid}] lỗi: {type(exc).__name__}: {str(exc)[:200]}")
            return
        for g, e, a in pending_fail:
            statuses[g] = _fail_info(g, e, a, statuses.get(g))
            write_status(statuses[g])
        pending_fail.clear()
        info["attempts"] = attempts
        statuses[gid] = info
        write_status(info)
        done_now += 1
        completed_now += info.get("status") == "done"
        errs = f" | lỗi: {info['errors'][:2]}" if info.get("errors") else ""
        t2 = info.get("t2") or {}
        log.info(f"[{gid}] {kind} -> {info.get('status')} | T1={info.get('t1')} "
                 f"T2={sum(v == 'ok' for v in t2.values())}/{len(PERIODS)} T3img={sum(v == 'ok' for v in (info.get('t3img') or {}).values())}/{len(PERIODS)} "
                 f"T3csv={info.get('t3csv')} | {info.get('seconds', 0)}s | lần {attempts}{errs}")
        if done_now % 5 == 0 or done_now == len(jobs):
            elapsed = max(time.time() - t0, 1)
            rate = completed_now / elapsed * 3600
            remaining = sum(not district_complete(statuses.get(g)) for g, _, _ in jobs)
            eta = (datetime.now(timezone.utc) + timedelta(hours=remaining / rate)).astimezone(
                timezone(timedelta(hours=7))).strftime("%d/%m %H:%M") if rate > 0 else "chưa đủ dữ liệu"
            log.info(f"[speed] {completed_now} huyện done mới trong {elapsed/60:.1f} phút | "
                     f"{rate:.1f} huyện/giờ | hàng đợi còn {remaining}/{len(jobs)} | "
                     f"ETA tham khảo {eta} giờ Việt Nam")
        reasons = rest_policy.observe(gid, info)
        if reasons and REST_SEC > 0 and not STOP_EVENT.is_set():
            EE_SEM.pause(REST_SEC, "; ".join(reasons))

    try:
        for fut in as_completed(futures):
            consume(fut)
            if STOP_EVENT.is_set():
                break
            if len(pending_fail) >= OUTAGE_STREAK:
                log.error(f"{OUTAGE_STREAK} huyện lỗi liên tiếp: nghi sự cố chung, tạm dừng vòng.")
                outage = True
                break
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True, cancel_futures=True)
    for fut in futures:
        if fut not in handled and fut.done():
            consume(fut)
    if outage:
        return "outage"
    for g, e, a in pending_fail:
        statuses[g] = _fail_info(g, e, a, statuses.get(g))
        write_status(statuses[g])
    return "stop" if STOP_EVENT.is_set() else "ok"


def _fail_info(gid, exc, attempts, prev):
    # Giữ checkpoint vừa ghi trước lỗi thay vì quay về snapshot đầu vòng.
    info = dict(load_all_status().get(gid) or prev or {})
    info.update({"gid_2": gid, "period": PERIOD_ID, "profile": OUTPUT_PROFILE, "status": "failed", "attempts": attempts, "run_id": RUN_ID,
                 "errors": [f"{type(exc).__name__}: {str(exc)[:300]}"],
                 "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return info


def main():
    global STATUS_FILE, ADMIN_DF, ADMIN_BY_GID, PARTS_STAMP
    os.makedirs(L(D_STATUS), exist_ok=True)
    PARTS_STAMP = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{RUN_ID}"
    STATUS_FILE = L(D_STATUS, f"status_{PARTS_STAMP}.jsonl")
    setup_logging()
    log.info(f"VNGISDash huyện {START_MONTH}–{END_MONTH} | chế độ {MODE} | đích {REMOTE_BASE} | {N_WORKERS} huyện x {MONTH_THREADS} ảnh song song"
             f" | ảnh ngày {DAY_BANDS} kênh {DAY_FORMAT} {DAY_IMAGE_SCALE} m | tối đa {EE_CONCURRENCY} yêu cầu EE cùng lúc")
    log.info(f"[rest] Cấu hình: mỗi {REST_EVERY_N} huyện mới hoàn tất (0=tắt), "
             f"hết tỉnh={REST_AFTER_PROVINCE}, nghỉ {REST_SEC}s (0=tắt nghỉ).")
    try:
        # Khởi tạo Earth Engine song song với việc kéo trạng thái từ Drive
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_ee = ex.submit(init_earth_engine)
            init_storage()
            ADMIN_DF = build_admin_table()
            f_ee.result()
        ADMIN_BY_GID = {r["GID_2"]: r for r in ADMIN_DF.to_dict("records")}
        targets = load_targets(ADMIN_DF)
    except Exception as exc:
        log.error(f"Khởi tạo thất bại: {type(exc).__name__}: {exc}")
        log.error(PREFLIGHT_HINT)
        return 1
    rows = {r["GID_2"]: r for r in targets.to_dict("records")}
    gids = list(rows)
    log.info(f"Danh sách: {len(gids):,} huyện, {targets['GID_1'].nunique()} tỉnh"
             + (f" (pilot_n={PILOT_N}; thí điểm: {', '.join(gids)})" if MODE == "pilot" else ""))

    statuses = load_all_status()
    try:
        check_resume(targets, statuses)
    except RuntimeError as exc:
        log.error("[resume] " + str(exc))
        return 1
    if PREFLIGHT:
        pend = [g for g in gids if not core_finished(statuses.get(g))] or gids
        for attempt in (1, 2, 3):
            try:
                preflight(rows[pend[0]])
                break
            except Exception as exc:
                log.error(f"[preflight] THẤT BẠI (lần {attempt}/3): {type(exc).__name__}: {exc}")
                if isinstance(exc, PreflightError) or _classify(str(exc)) == "permanent":
                    log.error(PREFLIGHT_HINT)
                    rclone_sync_once(final=True)
                    return 1
                if attempt == 3:
                    log.error(PREFLIGHT_HINT)
                    rclone_sync_once(final=True)
                    return 1
                time.sleep(20 * attempt)

    install_signal_handlers()
    if MAX_RUNTIME_SEC > 0:
        t = threading.Timer(MAX_RUNTIME_SEC, request_stop, args=("deadline",))
        t.daemon = True
        t.start()
        log.info(f"Thời gian tối đa của lượt: {MAX_RUNTIME_SEC/3600:.2f} giờ")
    if drive_stop_exists():
        log.warning("Có file _control/STOP trên Drive: không chạy.")
        return 130

    rest_policy = DistrictRestPolicy(ADMIN_BY_GID.values(), statuses)
    uploader = Uploader()
    uploader.start()
    outages, code = 0, 0
    try:
        while not STOP_EVENT.is_set():
            statuses = load_all_status()
            write_progress(targets, statuses)
            jobs = next_round_jobs(gids, rows, statuses)
            if not jobs:
                break
            log.info(f"Vòng mới: {len(jobs):,} huyện cần xử lý")
            result = run_round(jobs, statuses, rest_policy)
            if result == "stop":
                break
            if result == "outage":
                outages += 1
                if outages >= MAX_OUTAGES:
                    code = 2
                    break
                STOP_EVENT.wait(OUTAGE_SLEEP_SEC)
            else:
                outages = 0
    except KeyboardInterrupt:
        code = 130
    finally:
        uploader.stop_event.set()
        uploader.join(timeout=60)

    statuses = load_all_status()
    progress = write_progress(targets, statuses)
    unfinished = [g for g in gids if not core_finished(statuses.get(g))]
    try:
        build_national_csv()
    except Exception as exc:
        log.error(f"Dựng CSV toàn quốc lỗi: {exc}")
        code = 1
    if not rclone_sync_once(final=True):
        log.error("Đồng bộ cuối lên Drive thất bại. Giữ trạng thái để tải lại file thiếu ở lượt sau.")
        return 1

    if not unfinished and not STOP_EVENT.is_set():
        failed = progress[progress["status"] != "done"]
        log.info(f"Kết thúc hàng đợi: {progress['status'].value_counts().to_dict()}")
        if len(failed):
            log.warning(f"{len(failed)} huyện không đạt sau {MAX_ATTEMPTS} lần, xem _control/progress.csv")
        return code or (1 if len(failed) else 0)

    log.info(f"Chưa xong: còn {len(unfinished):,} huyện | {progress['status'].value_counts().to_dict()}")
    if code:
        return code
    if STOP_REASON[0] == "fatal":
        log.error(f"Dừng vì lỗi tải ảnh. Lỗi gần nhất: {_dl_stats['last_err']}")
        log.error(PREFLIGHT_HINT)
        return 1
    if STOP_REASON[0] in ("signal", "drive_stop"):
        return 130
    return 3


if __name__ == "__main__" and os.environ.get("VNGIS_SKIP_MAIN") != "1":
    if "--sync-only" in sys.argv:
        setup_logging()
        if DAY_FORMAT == "int16" and not os.path.isfile(L(D_CONTROL, "int16_uploaded.json")):
            res = subprocess.run(["rclone", "cat", f"{REMOTE_BASE}/{D_CONTROL}/int16_uploaded.json"],
                                 capture_output=True, text=True, timeout=180)
            if res.returncode == 0:
                saved = json.loads(res.stdout)
                if not isinstance(saved, list) or not all(isinstance(p, str) for p in saved):
                    raise RuntimeError("Marker Int16 trên Drive không hợp lệ; không ghi đè.")
                REMOTE_INT16_TIFS.update(saved)
            elif not any(s in res.stderr.lower() for s in ("not found", "doesn't exist")):
                log.error("Không đọc được marker Int16 để đồng bộ nốt; không ghi đè trạng thái Drive.")
                sys.exit(1)
        ok = rclone_sync_once(final=True)
        log.info("Đồng bộ nốt xong." if ok else "Đồng bộ nốt chưa hoàn tất.")
        sys.exit(0 if ok else 1)
    sys.exit(main())
