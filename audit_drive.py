"""Read-only inventory of district outputs on Drive; never initializes Earth Engine."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import io
import json
from pathlib import Path
import tempfile

import pandas as pd
import vngis_2024 as v


def csv_months(text, kind):
    """Count unique valid months; duplicates/null metrics are not complete."""
    if text is None:
        return {}
    frame = pd.read_csv(io.StringIO(text), dtype={"GID_2": str}, keep_default_na=False)
    required = v.DAY_COLUMNS if kind == "day" else v.NIGHT_COLUMNS
    if list(frame.columns) != required:
        raise ValueError(f"CSV {kind}: sai schema, không thể xác nhận dữ liệu")
    metrics = ([f"{band}_mean" for band in v.DAY_BANDS_ALL] if kind == "day"
               else ["TNL", "MEAN_RAD", "LIT_PIXELS", "CLOUD_FREE_OBS"])
    keys = Counter()
    valid = {}
    for row in frame.to_dict("records"):
        year, month = int(row["YEAR"]), int(row["MONTH"])
        if (year, month) not in v.PERIODS:
            continue
        key = (row["GID_2"], v.month_key((year, month)))
        keys[key] += 1
        values = pd.to_numeric(pd.Series([row[col] for col in metrics]), errors="coerce")
        valid[key] = row["DATA_STATUS"] == "ok" and values.notna().all() and all(
            float("-inf") < number < float("inf") for number in values)
    result = defaultdict(set)
    for (gid, month), count in keys.items():
        if count == 1 and valid[(gid, month)]:
            result[gid].add(month)
    return result


def build_reports(admin, inventory, day_csv, night_csv, checked_at, remote):
    """File presence/size and CSV row checks, not a TIFF pixel integrity check."""
    by_path = defaultdict(list)
    for item in inventory:
        if not item.get("IsDir", False):
            by_path[item["Path"]].append(item)
    csv_keys = {"day": csv_months(day_csv, "day"), "night": csv_months(night_csv, "night")}
    rows, files = [], []
    for row in sorted(admin.to_dict("records"), key=lambda r: v.natural_sort_key(r["GID_2"])):
        gid, ctx = row["GID_2"], v.build_ctx(row)
        out = {**{key: row[key] for key in v.ADM_COLS}, "checked_at_utc": checked_at,
               "remote": remote}
        for kind in ("day", "night"):
            found, duplicate, total_bytes = set(), [], 0
            folder = ctx[f"rel_{kind}_dir"]
            naming = v.day_name if kind == "day" else v.night_name
            for period in v.PERIODS:
                month, path = v.month_key(period), f"{folder}/{naming(ctx, period)}"
                entries = by_path.get(path, [])
                if len(entries) > 1:
                    duplicate.append(month)
                if len(entries) == 1 and entries[0].get("Size", 0) > 0:
                    found.add(month)
                    total_bytes += entries[0]["Size"]
                for entry in entries:
                    files.append({"GID_1": row["GID_1"], "GID_2": gid, "kind": kind,
                                  "month": month, "path": path, "bytes": entry.get("Size", 0),
                                  "drive_modtime": entry.get("ModTime", ""),
                                  "drive_id": entry.get("ID", ""), "observed_at_utc": checked_at})
            out[f"{kind}_tiff_on_drive"] = len(found)
            out[f"{kind}_tiff_missing_months"] = ";".join(m for m in v.MONTH_KEYS if m not in found)
            out[f"{kind}_tiff_duplicate_months"] = ";".join(duplicate)
            out[f"{kind}_bytes"] = total_bytes
            valid_csv = csv_keys[kind].get(gid, set())
            out[f"{kind}_csv_valid_months"] = len(valid_csv)
            out[f"{kind}_csv_missing_or_invalid_months"] = ";".join(m for m in v.MONTH_KEYS if m not in valid_csv)
        out["inventory_complete"] = all(out[f"{kind}_{slot}"] == len(v.PERIODS)
                                        for kind in ("day", "night")
                                        for slot in ("tiff_on_drive", "csv_valid_months"))
        rows.append(out)
    districts = pd.DataFrame(rows)
    provinces = districts.groupby(["GID_1", "NAME_1"], sort=False).agg(
        districts_expected=("GID_2", "size"), districts_inventory_complete=("inventory_complete", "sum"),
        day_tiff_on_drive=("day_tiff_on_drive", "sum"), night_tiff_on_drive=("night_tiff_on_drive", "sum"),
        day_csv_valid_months=("day_csv_valid_months", "sum"),
        night_csv_valid_months=("night_csv_valid_months", "sum")).reset_index()
    provinces["tiff_expected_per_kind"] = provinces["districts_expected"] * len(v.PERIODS)
    provinces["checked_at_utc"] = checked_at
    file_columns = ["GID_1", "GID_2", "kind", "month", "path", "bytes", "drive_modtime", "drive_id", "observed_at_utc"]
    return districts, provinces, pd.DataFrame(files, columns=file_columns)


def read_inventory(remote):
    result = v._run_rclone(["lsjson", remote, "--recursive", "--files-only"], timeout=1800)
    if result.returncode:
        raise RuntimeError("Không đọc được inventory Drive; không coi lỗi API là thư mục trống: "
                           + result.stderr[-400:])
    inventory = json.loads(result.stdout)
    if not isinstance(inventory, list):
        raise ValueError("Inventory Drive không hợp lệ")
    return inventory


def read_remote_csv(remote, kind, inventory):
    path = f"CSV/{kind}_indices.csv"
    entries = [item for item in inventory if item.get("Path") == path and not item.get("IsDir", False)]
    if not entries:
        return None
    if len(entries) != 1:
        raise ValueError(f"Drive có CSV trùng đường dẫn {path}; cần xử lý trước khi xác nhận")
    result = v._run_rclone(["cat", f"{remote}/{path}"], timeout=600)
    if result.returncode:
        raise RuntimeError(f"Không đọc được {path}; báo cáo không được xác nhận: " + result.stderr[-400:])
    return result.stdout.lstrip("\ufeff")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", default=v.REMOTE_BASE)
    parser.add_argument("--output", default="artifacts/drive_audit")
    parser.add_argument("--admin", help="CSV GADM cấp 2 đã chuẩn bị, tùy chọn")
    args = parser.parse_args()
    print(f"[audit] Đọc file thực có trên {args.remote}; không tải TIFF hoặc gọi EE.", flush=True)
    started = datetime.now(timezone.utc).isoformat()
    inventory = read_inventory(args.remote)
    day = read_remote_csv(args.remote, "day", inventory)
    night = read_remote_csv(args.remote, "night", inventory)
    admin = (pd.read_csv(args.admin, dtype=str, keep_default_na=False)
             if args.admin else v.build_admin_table())
    if len(admin) != 710 or admin.GID_2.nunique() != 710 or admin.GID_1.nunique() != 63:
        raise ValueError("Danh sách GADM phải đủ 710 huyện / 63 tỉnh")
    checked = datetime.now(timezone.utc).isoformat()
    checked_vn = datetime.fromisoformat(checked).astimezone(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M:%S")
    districts, provinces, files = build_reports(admin, inventory, day, night, checked, args.remote)
    output = Path(args.output)
    # Only publish a report after all reads succeeded, not a misleading partial report.
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audit_", dir=output) as temp:
        for name, frame in (("districts_on_drive.csv", districts), ("provinces_on_drive.csv", provinces),
                            ("files_on_drive.csv", files)):
            staged = Path(temp, name)
            frame.to_csv(staged, index=False, encoding="utf-8-sig")
            staged.replace(output / name)
    summary = ["# Kiểm kê dữ liệu thực có trên Drive", "", f"Đích: `{args.remote}`", "",
               f"Đọc từ {started} đến {checked} (UTC). Kiểm tra xong lúc {checked_vn} giờ Việt Nam (UTC+7).", "",
               f"- Huyện đủ TIFF và dòng CSV theo inventory: {int(districts.inventory_complete.sum())}/710.",
               f"- TIFF ngày: {int(districts.day_tiff_on_drive.sum())}/8520.",
               f"- TIFF đêm: {int(districts.night_tiff_on_drive.sum())}/8520.", "",
               "Đây là kiểm kê đường dẫn, kích thước > 0 và CSV tổng hợp; chưa kiểm tra pixel/kiểu dữ liệu TIFF.",
               "Nếu CSV tổng hợp chưa được cập nhật, báo cáo chưa xác nhận các tháng chỉ có trong parts.",
               "Drive vẫn upload trong lúc quét nên đây là quan sát trong khoảng thời gian trên, không phải ảnh chụp nguyên tử.",
               "`drive_modtime` có thể là thời gian file trên runner được rclone giữ lại, không phải giờ upload.",
               "`observed_at_utc` là lúc kiểm tra thấy file. Không suy ra giờ upload chính xác của các lượt cũ.", "",
               "| Tỉnh | Huyện đủ theo inventory / tổng | TIFF ngày | TIFF đêm | TIFF cần mỗi loại |",
               "|---|---:|---:|---:|---:|"]
    summary += [f"| {r.NAME_1} | {r.districts_inventory_complete}/{r.districts_expected} | "
                f"{r.day_tiff_on_drive} | {r.night_tiff_on_drive} | {r.tiff_expected_per_kind} |"
                for r in provinces.itertuples()]
    (output / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary), flush=True)
    print(f"[audit] Báo cáo: {output}", flush=True)
    return 0  # Incomplete data is a finding, not a failed audit command.


if __name__ == "__main__":
    raise SystemExit(main())
