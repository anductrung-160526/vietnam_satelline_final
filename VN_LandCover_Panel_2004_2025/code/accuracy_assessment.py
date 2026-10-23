# -*- coding: utf-8 -*-
"""
Đánh giá độ chính xác phân lớp lớp phủ bằng bộ điểm mẫu kiểm chứng (samples/).
Điểm mẫu CHỈ dùng để kiểm chứng, không dùng huấn luyện (phân lớp theo ngưỡng, không ML).
Kết quả lấy thật từ ảnh phân lớp trên Google Earth Engine: ma trận nhầm lẫn, OA, Kappa, PA/UA.
"""
import sys
import json
from datetime import datetime
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from pipeline_core.config import LANDCOVER_CLASSES, LANDCOVER_THRESHOLDS
from pipeline_core.samples_gen import SAMPLE_POINTS
from pipeline_core.utils import df_to_markdown, log_audit
from pipeline_core import ee_utils

CLASS_IDS = list(LANDCOVER_CLASSES)


def load_samples(pkg_dir):
    f = Path(pkg_dir) / "samples" / "ground_truth_samples.csv"
    if f.is_file():
        df = pd.read_csv(f)
        return df[["lon", "lat", "class"]].to_dict("records")
    return [{"lon": p["lon"], "lat": p["lat"], "class": p["class"]} for p in SAMPLE_POINTS]


def metrics_from_matrix(matrix):
    """matrix[i][j]: hàng = lớp thực tế, cột = lớp phân loại (theo thứ tự CLASS_IDS)."""
    n = sum(sum(r) for r in matrix)
    if n == 0:
        raise ValueError("Không có điểm mẫu nào nằm trong vùng ảnh có dữ liệu")
    diag = sum(matrix[i][i] for i in range(len(matrix)))
    oa = diag / n
    rows = [sum(r) for r in matrix]
    cols = [sum(matrix[i][j] for i in range(len(matrix))) for j in range(len(matrix))]
    pe = sum(r * c for r, c in zip(rows, cols)) / (n * n)
    kappa = (oa - pe) / (1 - pe) if pe < 1 else 1.0
    pa = [matrix[i][i] / rows[i] if rows[i] else None for i in range(len(matrix))]
    ua = [matrix[i][i] / cols[i] if cols[i] else None for i in range(len(matrix))]
    return {"n": n, "oa": oa, "kappa": kappa, "pa": pa, "ua": ua}


def evaluate_classification_accuracy(ee, classified, pkg_dir, sensor, year, logger=None):
    pts = load_samples(pkg_dir)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([p["lon"], p["lat"]]), {"lop_thuc": int(p["class"])})
                               for p in pts])
    sampled = classified.sampleRegions(collection=fc, properties=["lop_thuc"], scale=30, geometries=False)
    rows = ee_utils.get_info(sampled.reduceColumns(ee.Reducer.toList(2), ["lop_thuc", "classification"]))["list"]

    idx = {c: i for i, c in enumerate(CLASS_IDS)}
    matrix = [[0] * len(CLASS_IDS) for _ in CLASS_IDS]
    for truth, pred in rows:
        if int(truth) in idx and int(pred) in idx:
            matrix[idx[int(truth)]][idx[int(pred)]] += 1
    m = metrics_from_matrix(matrix)

    names = [LANDCOVER_CLASSES[c]["name"] for c in CLASS_IDS]
    cm = pd.DataFrame(matrix, index=names, columns=names)
    per_class = pd.DataFrame({
        "Lớp": names,
        "Số điểm thực tế": [sum(r) for r in matrix],
        "Producer's accuracy (%)": [round(v * 100, 1) if v is not None else "" for v in m["pa"]],
        "User's accuracy (%)": [round(v * 100, 1) if v is not None else "" for v in m["ua"]],
    })

    docs = Path(pkg_dir) / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    tag = f"{sensor.upper()}_{year}"
    (docs / f"do_chinh_xac_{tag}.json").write_text(json.dumps({
        "nguon_anh": sensor, "nam": year, "so_diem": m["n"], "so_diem_tong": len(pts),
        "overall_accuracy": m["oa"], "kappa": m["kappa"], "ma_tran": matrix, "lop": names,
        "nguong": LANDCOVER_THRESHOLDS,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    report = docs / f"BAO_CAO_DO_CHINH_XAC_{tag}.md"
    with open(report, "w", encoding="utf-8") as f:
        f.write(f"# Báo cáo độ chính xác phân lớp lớp phủ: {sensor} năm {year}\n\n")
        f.write(f"- Ngày tạo: {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write("- Phương pháp phân lớp: luật ngưỡng chỉ số phổ NDVI/MNDWI/NDBI + độ dốc SRTM "
                "(không dùng machine learning)\n")
        f.write(f"- Số điểm kiểm chứng có dữ liệu ảnh: {m['n']} / {len(pts)}\n\n")
        f.write(f"**Overall Accuracy:** {m['oa'] * 100:.2f}%  \n**Kappa:** {m['kappa']:.3f}\n\n")
        f.write("## Ma trận nhầm lẫn (hàng = thực tế, cột = phân lớp)\n\n")
        f.write(df_to_markdown(cm, index=True) + "\n\n")
        f.write("## Độ chính xác theo lớp\n\n" + df_to_markdown(per_class) + "\n\n")
        f.write("## Ngưỡng đã dùng\n\n```json\n" + json.dumps(LANDCOVER_THRESHOLDS, indent=2) + "\n```\n\n")
        f.write("Lưu ý: bộ điểm mẫu hiện còn nhỏ và không gắn năm quan sát; điểm được giả định đúng cho "
                "năm đánh giá. Nên bổ sung điểm mẫu theo năm, nhất là trong phạm vi tỉnh đang xử lý.\n")
    if logger:
        log_audit(logger, sensor_type=sensor, content=f"Độ chính xác {year}: OA={m['oa'] * 100:.1f}%, "
                                                       f"Kappa={m['kappa']:.3f} (n={m['n']}) -> {report}")
    return m
