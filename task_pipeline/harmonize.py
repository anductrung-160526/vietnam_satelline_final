"""Hiệu chỉnh liên kết DMSP-OLS → SNPP-VIIRS để có chuỗi so sánh được 2004–2025.

    python3 -m task_pipeline.harmonize --root E:\\SatelliteData

Chạy SAU khi cả 63 tỉnh đã có chỉ số (derive + merge), vì mô hình được khớp trên toàn
bộ 63 tỉnh của năm chồng lấn 2013 — năm duy nhất có cả ảnh DMSP lẫn ảnh VIIRS.

Phương pháp
-----------
DMSP (DN 0–63, bão hòa ở lõi đô thị) và VIIRS (bức xạ, không bão hòa) là hai thang đo
khác nhau; cộng thẳng vào một chuỗi là sai. Cách làm chuẩn trong tài liệu là khớp một
hàm lũy thừa trên năm chồng lấn rồi quy một bên về thang của bên kia:

    sol_viirs = a * sol_dmsp ** b          (khớp bằng hồi quy tuyến tính trên log–log)

Chọn quy DMSP về thang VIIRS (không phải ngược lại) vì VIIRS là dữ liệu tốt hơn, còn
tiếp tục về sau, và dashboard chủ yếu dùng giai đoạn gần đây. Số liệu VIIRS 2014–2025
giữ nguyên, không bị một phép biến đổi nào chạm vào.

Số mũ b > 1 là dấu hiệu mô hình đang bù cho sự bão hòa của DMSP ở các tỉnh sáng nhất.

Kết quả ghi thêm cột, KHÔNG ghi đè cột gốc:
    sol_cal, sol_density_cal, sol_change_cal_pct, calibration
Tham số mô hình lưu ở metadata/hieu_chinh_dmsp_viirs.json để trích vào báo cáo.
"""
import argparse
import json
import math
from pathlib import Path

from province_pipeline.sources import NTL_PACKAGE

METHOD = 'DMSP_TO_VIIRS_POWER_OVERLAP2013_v1'
OVERLAP_YEAR = 2013
MIN_PROVINCES = 30          # dưới mức này thì mô hình không đáng tin, thà không hiệu chỉnh


def fit(pairs):
    """Khớp sol_viirs = a * sol_dmsp**b bằng hồi quy bình phương nhỏ nhất trên log–log.

    pairs: danh sách (sol_dmsp, sol_viirs). Chỉ nhận cặp cả hai đều dương — log của 0
    hoặc số âm không tồn tại, và một tỉnh tối om không nói gì về quan hệ hai thang đo.
    """
    points = [(math.log(d), math.log(v)) for d, v in pairs
              if d is not None and v is not None and d > 0 and v > 0]
    n = len(points)
    if n < MIN_PROVINCES:
        return None
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    sxx = sum((x - mx) ** 2 for x, _ in points)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in points)
    b = sxy / sxx
    ln_a = my - b * mx
    du = sum((y - (ln_a + b * x)) ** 2 for x, y in points)
    tong = sum((y - my) ** 2 for _, y in points)
    return {'phuong_phap': METHOD, 'a': math.exp(ln_a), 'b': b,
            'r2': 1 - du / tong if tong else None, 'so_tinh': n,
            'nam_chong_lan': OVERLAP_YEAR,
            'huong': 'DMSP -> thang VIIRS; số liệu VIIRS giữ nguyên'}


def convert(value, model):
    if value is None or model is None or value <= 0:
        return 0.0 if value == 0 else None
    return model['a'] * value ** model['b']


def pct(cur, prev):
    if cur is None or prev in (None, 0) or prev <= 0:
        return None
    return round(100 * (cur / prev - 1), 4)


def apply(rows, model):
    """Thêm cột đã hiệu chỉnh. Giữ nguyên mọi cột gốc để còn đối chiếu được."""
    theo_tinh = {}
    for row in rows:
        theo_tinh.setdefault(row['province_code'], []).append(row)
    for cua_tinh in theo_tinh.values():
        # Sắp theo (năm, tháng) để dùng được cho cả bảng năm lẫn bảng gộp năm+tháng.
        cua_tinh.sort(key=lambda r: (int(r['year']), int(r.get('month') or 0)))
        truoc = None
        for row in cua_tinh:
            nguon = row.get('source')
            goc = row.get('sol')
            if model is None:
                row['sol_cal'] = None
                row['calibration'] = 'KHONG_DU_DU_LIEU_CHONG_LAN'
            elif nguon == 'DMSP':
                row['sol_cal'] = (None if goc is None
                                  else round(convert(goc, model) or 0.0, 4))
                row['calibration'] = METHOD
            else:
                row['sol_cal'] = goc          # VIIRS đã ở thang đích, không đổi
                row['calibration'] = METHOD
            area = row.get('area_km2')
            row['sol_density_cal'] = (round(row['sol_cal'] / area, 6)
                                      if row['sol_cal'] is not None and area else None)
            # Sau hiệu chỉnh thì so sánh xuyên mốc 2013–2014 mới có nghĩa.
            row['sol_change_cal_pct'] = (pct(row['sol_cal'], truoc['sol_cal'])
                                         if truoc is not None else None)
            truoc = row
    return rows


def read_csv(path):
    import csv
    with open(path, encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def number(value):
    text = str(value or '').strip()
    if text in ('', 'NA', 'NaN', 'None', '-9999'):
        return None
    try:
        return float(text)
    except ValueError:
        return None


COT_MOI = ('sol_cal', 'sol_density_cal', 'sol_change_cal_pct')


def _hieu_chinh_bang(path, model):
    """Đọc một bảng, thêm ba cột đã hiệu chỉnh, ghi đè bằng thay thế nguyên tử."""
    import csv
    header, rows = read_csv(path)
    for row in rows:
        row['sol'] = number(row.get('sol'))
        row['area_km2'] = number(row.get('area_km2'))
        row['year'] = int(row['year'])
    apply(rows, model)
    header = header + [c for c in COT_MOI if c not in header]
    if 'calibration' not in header:
        header.append('calibration')
    tmp = path.with_suffix('.csv.hc')
    with tmp.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=header, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)
    return len(rows)


def run(root):
    root = Path(root)
    processed = root / NTL_PACKAGE / 'data_processed'
    overlap_path = processed / 'ntl_overlap_2013.csv'
    annual_path = processed / 'ntl_annual.csv'
    if not annual_path.exists():
        raise SystemExit(f'Chưa có {annual_path}. Chạy bước tính chỉ số trước.')
    if not overlap_path.exists():
        raise SystemExit(
            f'Chưa có {overlap_path}.\nBảng này do derive sinh ra cho năm {OVERLAP_YEAR}, '
            'cần có cả ảnh DMSP 2013 lẫn ảnh VIIRS 2013 của cùng một tỉnh.')

    _, overlap_rows = read_csv(overlap_path)
    pairs = [(number(r.get('sol_dmsp')), number(r.get('sol_viirs'))) for r in overlap_rows]
    model = fit(pairs)

    # Bảng gộp cũng phải mang cột đã hiệu chỉnh, nếu không người dùng bảng chính sẽ
    # không có cách nào so sánh xuyên mốc 2013.
    da_ghi = {}
    for ten in ('ntl_annual', 'ntl_panel'):
        path = processed / f'{ten}.csv'
        if path.exists():
            da_ghi[ten] = _hieu_chinh_bang(path, model)

    meta_dir = root / NTL_PACKAGE / 'metadata'
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / 'hieu_chinh_dmsp_viirs.json').write_text(
        json.dumps(model or {'phuong_phap': None,
                             'ly_do': f'Dưới {MIN_PROVINCES} tỉnh có cặp DMSP–VIIRS dương '
                                      f'ở năm {OVERLAP_YEAR}'},
                   ensure_ascii=False, indent=2), encoding='utf-8')
    return model, da_ghi


def main():
    parser = argparse.ArgumentParser(description='Hiệu chỉnh liên kết DMSP–VIIRS')
    parser.add_argument('--root', default='/data/SatelliteData')
    model, da_ghi = run(parser.parse_args().root)
    if model is None:
        print('KHÔNG hiệu chỉnh được: thiếu dữ liệu năm chồng lấn 2013.')
        print('Các dòng được đánh hieu_chinh=KHONG_DU_DU_LIEU_CHONG_LAN.')
        raise SystemExit(1)
    print(f"Mô hình: sol_viirs = {model['a']:.6g} * sol_dmsp ^ {model['b']:.6g}")
    print(f"  khớp trên {model['so_tinh']} tỉnh của năm {model['nam_chong_lan']}"
          f" · R² = {model['r2']:.4f}")
    print(f"  {model['huong']}")
    for ten, count in da_ghi.items():
        print(f'Đã ghi {ten}.csv: {count} dòng, thêm cột ' + ', '.join(COT_MOI) + '.')
    if model['b'] > 1:
        print('  b > 1: mô hình đang bù cho sự bão hòa của DMSP ở các tỉnh sáng nhất.')
    else:
        print('  CẢNH BÁO b <= 1: sai chiều vật lý. DMSP bão hòa ở DN 63 nên tỉnh càng sáng'
              ' thì DMSP càng hụt so với VIIRS, b phải > 1. Kiểm tra lại bảng chồng lấn'
              ' có đo cùng đại lượng với cột sol_ntl (cùng ngưỡng nền) hay không.')
    if model['r2'] is not None and model['r2'] < 0.8:
        print(f"  CẢNH BÁO R² = {model['r2']:.4f} < 0,80: quan hệ hai thang đo yếu."
              ' Chuỗi _hc dùng được để vẽ xu thế, nhưng KHÔNG nên rút kết luận định lượng'
              ' bắc qua mốc 2013 mà không nói rõ mức tin cậy này trong báo cáo.')


if __name__ == '__main__':
    main()
