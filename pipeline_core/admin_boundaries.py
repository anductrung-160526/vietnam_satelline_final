# -*- coding: utf-8 -*-
"""
Xử lý dữ liệu ranh giới hành chính cấp Huyện (GADM Level 2) tại Việt Nam
"""
import os
import re
import struct
import zipfile
import unicodedata
import requests
import pandas as pd
from pathlib import Path
from .config import GADM_VNM_URL

DISTRICT_COLS = ["GID_1", "NAME_1", "GID_2", "NAME_2", "TYPE_2", "ENGTYPE_2"]

def normalize_text(s):
    if not s or pd.isna(s):
        return ""
    s = unicodedata.normalize("NFD", str(s))
    s = re.sub(r"[̀-ͯ]", "", s)
    s = s.replace("đ", "d").replace("Đ", "d")
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s)
    return s.strip("_").lower()

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

def load_district_boundaries(cache_dir=None):
    """
    Tải và xử lý bảng danh mục toàn bộ ~705 quận/huyện/thị xã Việt Nam từ GADM 4.1 Level 2
    """
    if cache_dir is None:
        cache_dir = Path.home() / "vngis_data" / "_cache"
    else:
        cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    csv_cache = cache_dir / "vietnam_districts_l2.csv"
    if csv_cache.is_file():
        df = pd.read_csv(csv_cache, dtype=str, keep_default_na=False)
        return df

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
        z.extract("gadm41_VNM_2.dbf", cache_dir)
        cpg_file = "gadm41_VNM_2.cpg"
        enc = "utf-8"
        if cpg_file in z.namelist():
            enc_raw = z.read(cpg_file).decode().strip()
            if enc_raw.upper().replace("-", "") in ("UTF8", ""):
                enc = "utf-8"
            else:
                enc = enc_raw

    dbf_file = cache_dir / "gadm41_VNM_2.dbf"
    df_raw = read_dbf(dbf_file, enc)

    # Lọc cột và chuẩn hóa
    cols = [c for c in DISTRICT_COLS if c in df_raw.columns]
    df = df_raw[cols].drop_duplicates("GID_2").reset_index(drop=True)

    # Thêm các cột chuẩn hóa
    df["ma_tinh"] = df["GID_1"]
    df["ten_tinh"] = df["NAME_1"]
    df["ma_huyen"] = df["GID_2"]
    df["ten_huyen"] = df["NAME_2"]
    df["loai_huyen"] = df["TYPE_2"] if "TYPE_2" in df.columns else ""
    df["slug_tinh"] = df["NAME_1"].apply(normalize_text)
    df["slug_huyen"] = df["NAME_2"].apply(normalize_text)

    df.to_csv(csv_cache, index=False, encoding="utf-8-sig")
    return df

def get_pilot_districts(df_districts, n=3):
    """
    Chọn n huyện thí điểm tiêu biểu:
    - Đại diện khu vực đô thị (Quận/Thành phố)
    - Đại diện khu vực nông thôn đồng bằng (Huyện)
    - Đại diện khu vực miền núi/rừng
    """
    types = df_districts["loai_huyen"].str.lower()
    urban_pool = df_districts[types.str.contains("quận|thành phố|thị xã", na=False)]
    rural_pool = df_districts[types.str.contains("huyện", na=False)]

    selected = []
    if not urban_pool.empty:
        selected.append(urban_pool.iloc[0])
    if not rural_pool.empty:
        selected.append(rural_pool.iloc[0])
    if len(rural_pool) > 10:
        selected.append(rural_pool.iloc[len(rural_pool) // 2])

    remaining_needed = n - len(selected)
    if remaining_needed > 0:
        for _, row in df_districts.iterrows():
            if row["ma_huyen"] not in [x["ma_huyen"] for x in selected]:
                selected.append(row)
                if len(selected) >= n:
                    break

    return pd.DataFrame(selected[:n]).reset_index(drop=True)
