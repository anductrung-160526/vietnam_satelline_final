# -*- coding: utf-8 -*-
"""
Ranh giới hành chính cấp huyện (GADM 4.1 Level 2, địa giới trước sáp nhập) và mã Cục Thống kê.

- Danh mục huyện đọc từ tệp .dbf, hình học đọc từ tệp .shp (thư viện pyshp, thuần Python).
- Mã Cục Thống kê (ma_tinh_tk, ma_huyen_tk) tra từ pipeline_core/data/gso_district_codes.csv.
  Huyện không khớp được mã sẽ để trống và ghi vào log, KHÔNG tự sinh mã.
"""
import re
import struct
import zipfile
import unicodedata
import requests
from functools import lru_cache
import pandas as pd
from pathlib import Path
from .config import GADM_VNM_URL

DISTRICT_COLS = ["GID_1", "NAME_1", "GID_2", "NAME_2", "TYPE_2", "ENGTYPE_2"]
GSO_CODES_CSV = Path(__file__).resolve().parent / "data" / "gso_district_codes.csv"
GSO_PROVINCE_CSV = Path(__file__).resolve().parent / "data" / "gso_province_codes.csv"
SHP_BASENAME = "gadm41_VNM_2"
LEVELS = {"huyen": "gadm41_VNM_2", "tinh": "gadm41_VNM_1"}
GID_FIELD = {"huyen": "GID_2", "tinh": "GID_1"}


def normalize_text(s):
    if s is None or (not isinstance(s, str) and pd.isna(s)):
        return ""
    s = unicodedata.normalize("NFD", str(s))
    s = re.sub(r"[̀-ͯ]", "", s)
    s = s.replace("đ", "d").replace("Đ", "d")
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s)
    return s.strip("_").lower()


def match_key(s):
    """Khóa so khớp tên: bỏ dấu, bỏ khoảng trắng (GADM hay viết liền 'HàNội').
    Tên trong gso_district_codes.csv ghi KHÔNG kèm tiền tố 'Quận/Huyện/Thị xã'."""
    return normalize_text(s).replace("_", "")


def read_dbf(path, encoding="utf-8"):
    """Đọc tệp thuộc tính DBF thuần Python không phụ thuộc thư viện ngoài C-extension."""
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
                val = rec[pos:pos + size].decode(encoding, errors="replace").strip()
                row[name] = val
                pos += size
            rows.append(row)
    return pd.DataFrame(rows)


def default_cache_dir():
    from .config import resolve_output_dir
    return resolve_output_dir() / "_cache"


def ensure_gadm_shapefile(cache_dir=None, level="huyen"):
    """Tải (một lần) gói GADM 4.1 và giải nén bộ tệp của cấp yêu cầu (huyện: Level 2, tỉnh: Level 1)."""
    cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    basename = LEVELS[level]
    shp = cache_dir / f"{basename}.shp"
    if shp.is_file() and (cache_dir / f"{basename}.dbf").is_file():
        return shp

    zip_path = cache_dir / "gadm41_VNM_shp.zip"
    if not zip_path.is_file():
        print(f"[*] Đang tải dữ liệu ranh giới GADM 4.1 Việt Nam ({GADM_VNM_URL})...")
        r = requests.get(GADM_VNM_URL, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=900)
        r.raise_for_status()
        part_path = cache_dir / "gadm41_VNM_shp.zip.part"
        with open(part_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        part_path.replace(zip_path)
        print("[*] Tải dữ liệu ranh giới hoàn tất.")

    with zipfile.ZipFile(zip_path) as z:
        for ext in (".shp", ".shx", ".dbf", ".cpg", ".prj"):
            name = basename + ext
            if name in z.namelist():
                z.extract(name, cache_dir)
    return shp


def load_gso_codes(path=GSO_CODES_CSV):
    if not Path(path).is_file():
        return pd.DataFrame(columns=["ma_tinh_tk", "ten_tinh_tk", "ma_huyen_tk", "ten_huyen_tk"])
    df = pd.read_csv(path, dtype=str, keep_default_na=False, comment="#")
    df["k_tinh"] = df["ten_tinh_tk"].apply(match_key)
    df["k_huyen"] = df["ten_huyen_tk"].apply(match_key)
    return df


def attach_gso_codes(df, gso=None):
    """Gắn mã Cục Thống kê theo tên tỉnh + tên huyện đã chuẩn hóa. Không khớp -> để trống."""
    gso = load_gso_codes() if gso is None else gso
    df = df.copy()
    df["k_tinh"] = df["ten_tinh"].apply(match_key)
    df["k_huyen"] = df["ten_huyen"].apply(match_key)
    look = gso.drop_duplicates(["k_tinh", "k_huyen"]).set_index(["k_tinh", "k_huyen"])
    tinh_look = load_province_codes()
    ma_huyen_tk, ma_tinh_tk = [], []
    for kt, kh in zip(df["k_tinh"], df["k_huyen"]):
        ma_huyen_tk.append(look["ma_huyen_tk"].get((kt, kh), "") if not look.empty else "")
        ma_tinh_tk.append(tinh_look.get(kt, ""))
    df["ma_tinh_tk"] = ma_tinh_tk
    df["ma_huyen_tk"] = ma_huyen_tk
    return df.drop(columns=["k_tinh", "k_huyen"])


def load_province_codes(path=GSO_PROVINCE_CSV):
    """{khóa tên tỉnh: mã tỉnh Cục Thống kê}"""
    if not Path(path).is_file():
        return pd.Series(dtype=str)
    df = pd.read_csv(path, dtype=str, keep_default_na=False, comment="#")
    return df.assign(k=df["ten_tinh_tk"].apply(match_key)).drop_duplicates("k").set_index("k")["ma_tinh_tk"]


def _read_level_dbf(cache_dir, level):
    shp = ensure_gadm_shapefile(cache_dir, level)
    enc = "utf-8"
    cpg = shp.with_suffix(".cpg")
    if cpg.is_file():
        raw = cpg.read_text().strip()
        if raw and raw.upper().replace("-", "") != "UTF8":
            enc = raw
    return read_dbf(shp.with_suffix(".dbf"), enc)


@lru_cache(maxsize=1)
def province_names():
    """{mã tỉnh Cục Thống kê: tên tỉnh có dấu, có khoảng trắng} để đặt tên thư mục ảnh."""
    if not GSO_PROVINCE_CSV.is_file():
        return {}
    df = pd.read_csv(GSO_PROVINCE_CSV, dtype=str, keep_default_na=False, comment="#")
    return dict(zip(df["ma_tinh_tk"], df["ten_tinh_tk"]))


def province_folder_name(row):
    """Tên thư mục tỉnh cho ảnh: tên chuẩn của Cục Thống kê (vd 'Hà Nội'), thiếu mã thì dùng tên GADM."""
    name = province_names().get(str(row.get("ma_tinh_tk") or ""), "") or str(row.get("ten_tinh") or "khac")
    return re.sub(r'[<>:"/\\|?*]', "-", name).strip() or "khac"


def load_province_boundaries(cache_dir=None):
    """
    Danh mục 63 tỉnh/thành (GADM 4.1 Level 1) ở dạng 'đơn vị' dùng chung cho pipeline:
    ma_huyen/ma_huyen_gadm = GID_1, ten_huyen = tên tỉnh (pipeline đổi tên cột khi xuất bảng cấp tỉnh).
    """
    cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
    csv_cache = cache_dir / "vietnam_provinces_l1.csv"
    if csv_cache.is_file():
        df = pd.read_csv(csv_cache, dtype=str, keep_default_na=False)
    else:
        df_raw = _read_level_dbf(cache_dir, "tinh")
        df = df_raw[["GID_1", "NAME_1"]].drop_duplicates("GID_1").reset_index(drop=True)
        df.to_csv(csv_cache, index=False, encoding="utf-8-sig")
    codes = load_province_codes()
    out = pd.DataFrame({
        "ma_tinh": df["GID_1"], "ten_tinh": df["NAME_1"],
        "ma_huyen": df["GID_1"], "ten_huyen": df["NAME_1"], "loai_huyen": "Tỉnh",
    })
    out["ma_tinh_tk"] = [codes.get(match_key(n), "") for n in out["ten_tinh"]]
    out["ma_huyen_tk"] = out["ma_tinh_tk"]
    return out


def load_units(level="huyen", cache_dir=None):
    return load_province_boundaries(cache_dir) if level == "tinh" else load_district_boundaries(cache_dir)


def load_district_boundaries(cache_dir=None):
    """
    Bảng danh mục ~705 quận/huyện/thị xã Việt Nam từ GADM 4.1 Level 2, kèm mã Cục Thống kê.
    Cột chính: ma_tinh, ten_tinh, ma_huyen (GID_2, khớp hình học), ten_huyen, ma_tinh_tk, ma_huyen_tk.
    """
    cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
    csv_cache = cache_dir / "vietnam_districts_l2.csv"
    if csv_cache.is_file():
        df = pd.read_csv(csv_cache, dtype=str, keep_default_na=False)
    else:
        df_raw = _read_level_dbf(cache_dir, "huyen")
        cols = [c for c in DISTRICT_COLS if c in df_raw.columns]
        df = df_raw[cols].drop_duplicates("GID_2").reset_index(drop=True)
        df["ma_tinh"] = df["GID_1"]
        df["ten_tinh"] = df["NAME_1"]
        df["ma_huyen"] = df["GID_2"]
        df["ten_huyen"] = df["NAME_2"]
        df["loai_huyen"] = df["TYPE_2"] if "TYPE_2" in df.columns else ""
        df.to_csv(csv_cache, index=False, encoding="utf-8-sig")
    return attach_gso_codes(df)


def filter_districts(df, province=None, districts=None):
    """Lọc theo tên tỉnh (vd 'Hà Nội') và/hoặc danh sách tên/mã huyện."""
    out = df
    if province:
        keys = {match_key(p) for p in str(province).split(",") if p.strip()}
        out = out[out["ten_tinh"].apply(match_key).isin(keys) | out["ma_tinh_tk"].isin(
            [p.strip() for p in str(province).split(",")])]
    if districts:
        wanted = [d.strip() for d in (districts.split(",") if isinstance(districts, str) else districts) if d.strip()]
        keys = {match_key(d) for d in wanted}
        out = out[out["ten_huyen"].apply(match_key).isin(keys) | out["ma_huyen"].isin(wanted)
                  | out["ma_huyen_tk"].isin(wanted)]
    return out.reset_index(drop=True)


def get_pilot_districts(df_districts, n=3):
    """Chọn n huyện thí điểm: ưu tiên quận đô thị và huyện nông thôn."""
    types = df_districts["loai_huyen"].str.lower()
    urban = df_districts[types.str.contains("quận|thành phố|thị xã", na=False)]
    rural = df_districts[types.str.contains("huyện", na=False)]
    picked = pd.concat([urban.head(1), rural.head(1), df_districts]).drop_duplicates("ma_huyen")
    return picked.head(n).reset_index(drop=True)


def _round_coords(obj, nd=5):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(v), nd) for v in obj]
        return [_round_coords(o, nd) for o in obj]
    return obj


def load_district_geometries(gids, cache_dir=None, level="huyen"):
    """Trả về {GID: geojson geometry} cho các đơn vị yêu cầu (huyện: GID_2, tỉnh: GID_1)."""
    import shapefile  # pyshp
    shp = ensure_gadm_shapefile(cache_dir, level)
    wanted = set(gids)
    out = {}
    with shapefile.Reader(str(shp), encoding="utf-8") as r:
        names = [f[0] for f in r.fields[1:]]
        gid_idx = names.index(GID_FIELD[level])
        for sr in r.iterShapeRecords():
            gid = sr.record[gid_idx]
            if gid in wanted:
                geo = sr.shape.__geo_interface__
                out[gid] = {"type": geo["type"], "coordinates": _round_coords(geo["coordinates"])}
    return out
