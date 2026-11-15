"""Kiểm nghiệm chất lượng bộ dữ liệu đêm: ô trống, sai định dạng, phân phối bất thường.

    python scripts/kiem_dinh_chat_luong.py --root E:\\SatelliteData
    python scripts/kiem_dinh_chat_luong.py --root E:\\SatelliteData --bang ntl_panel

Khác với kiem_tra_chi_so_dem.py (soát LOGIC: nguồn ảnh đúng giai đoạn, mốc đổi vệ tinh,
xếp hạng có hợp lý không), script này soát CHẤT LƯỢNG KỸ THUẬT của bảng: kiểu dữ liệu,
khoá, ô trống, giá trị ngoài miền hợp lệ, điểm dị biệt.

Một ô trống không mặc nhiên là lỗi: cột sol_change_pct BẮT BUỘC trống ở năm đầu chuỗi và
ở mốc đổi vệ tinh. Vì vậy mỗi cột có một mức trống DỰ KIẾN, và chỉ phần vượt quá mới
được báo. In ra con số để tự phán, không chỉ "đạt" hay "không đạt".
"""
import argparse
import csv
import math
import re
from pathlib import Path

NTL_PACKAGE = 'VN_NTL_Panel_2004_2025'
SO_TINH = 63

# Cột -> miền giá trị hợp lệ. None = không chặn phía đó.
MIEN = {
    'sol': (0, None), 'sol_raw': (0, None), 'sol_cal': (0, None),
    'sol_density': (0, None), 'sol_density_cal': (0, None),
    'rad_mean': (0, None), 'rad_std': (0, None), 'rad_max': (0, None),
    'rad_cv': (0, None), 'lit_pixels': (0, None),
    # valid_pixels = 0 là trạng thái HỢP LỆ: tháng đó cả tỉnh không có lượt quan sát
    # sạch mây nào, mọi pixel thành NoData. Ghi 0 là đúng, không phải lỗi.
    'valid_pixels': (0, None),
    'background_pixels': (0, None), 'lit_area_km2': (0, None), 'lit_sol': (0, None),
    'area_km2': (1, None), 'lit_area_pct': (0, 100), 'lit_pixel_pct': (0, 100),
    'cloud_free_obs': (0, 31), 'year': (2004, 2025), 'month': (0, 12),
}
# lit_area_pct vượt 100 là tạo tác của lưới pixel, không phải hỏng dữ liệu: lit_area_km2
# cộng TRỌN vẹn mọi pixel chạm ranh giới, trong khi area_km2 là diện tích đa giác chính
# xác. Tỉnh sáng kín ở DMSP 1 km vì thế ra 101-112%. Chỉ báo khi vượt quá mức đó.
NGUONG_TAO_TAC = {'lit_area_pct': 120, 'lit_pixel_pct': 100.001}
# Cột được phép trống, kèm lý do. Các cột khác trống là đáng ngờ.
TRONG_HOP_LE = {
    'sol_change_yoy_pct': 'năm đầu của chuỗi tháng',
    'sol_change_mom_pct': 'tháng đầu chuỗi và chỗ thiếu tháng',
    'sol_change_cal_pct': 'mốc thời gian đầu tiên của mỗi tỉnh',
    'cloud_free_obs': 'ảnh DMSP không có băng cf_cvg',
    'note': 'rỗng là trạng thái bình thường',
    'lit_threshold': 'dòng chưa có ảnh',
    'rad_min': 'dòng chưa có ảnh',
    'sol_ma3': 'chỉ có ở nửa theo tháng của bảng gộp',
    'sol_change_pct': 'chỉ có ở nửa theo năm; năm đầu chuỗi và mốc đổi nguồn ảnh',
}
CHU = {'province_code', 'province_name', 'source', 'period', 'frequency',
       'status', 'calibration', 'note', 'reflectance_type'}


def doc(path):
    with open(path, encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def so(value):
    text = str(value or '').strip()
    if text in ('', 'NA', 'NaN', 'None', '-9999'):
        return None
    try:
        return float(text)
    except ValueError:
        return False          # có chữ trong ô đáng lẽ là số


def phan_vi(values, q):
    if not values:
        return None
    s = sorted(values)
    i = (len(s) - 1) * q
    lo = math.floor(i)
    return s[lo] if lo == i else s[lo] + (s[lo + 1] - s[lo]) * (i - lo)


def kiem_dinh(ten_bang, header, rows):
    print(f'\n{"=" * 78}\n{ten_bang}: {len(rows)} dòng × {len(header)} cột\n{"=" * 78}')
    loi = 0

    # --- 1. Khoá ---
    khoa = [c for c in ('province_code', 'year', 'month') if c in header]
    thay = {}
    for i, r in enumerate(rows):
        k = tuple(r.get(c, '') for c in khoa)
        thay.setdefault(k, []).append(i + 2)
    lap = {k: v for k, v in thay.items() if len(v) > 1}
    print(f'\n1. KHOÁ {" + ".join(khoa)}')
    print(f'   {len(thay)} khoá khác nhau, {len(lap)} khoá lặp')
    if lap:
        loi += 1
        for k, dong in list(lap.items())[:5]:
            print(f'   LẶP {k} ở các dòng {dong[:6]}')

    ma = {r.get('province_code') for r in rows}
    sai_ma = sorted(m for m in ma if not re.fullmatch(r'\d{2}', str(m or '')))
    print(f'   {len(ma)} mã tỉnh' + (f' — cần {SO_TINH}' if len(ma) != SO_TINH else ''))
    if sai_ma:
        loi += 1
        print(f'   MÃ SAI ĐỊNH DẠNG (phải là 2 chữ số): {sai_ma[:8]}')
    if len(ma) != SO_TINH:
        loi += 1

    # --- 2. Kiểu dữ liệu ---
    print('\n2. ĐỊNH DẠNG — ô lẽ ra là số nhưng chứa chữ')
    hong = {}
    for c in header:
        if c in CHU:
            continue
        xau = [i + 2 for i, r in enumerate(rows) if so(r.get(c)) is False]
        if xau:
            hong[c] = xau
    if hong:
        loi += 1
        for c, dong in hong.items():
            print(f'   {c}: {len(dong)} ô, ví dụ dòng {dong[:5]}')
    else:
        print('   Không có ô nào sai kiểu.')

    # --- 3. Dòng không có ảnh ---
    # Tháng mà cả tỉnh không có lượt quan sát sạch mây nào thì MỌI cột thống kê đều
    # trống. Đó là trạng thái hợp lệ, không phải 15 lỗi riêng lẻ. Tách chúng ra trước
    # khi đếm ô trống, nếu không mỗi dòng như vậy sẽ kêu ở mọi cột một lần.
    def khong_co_anh(r):
        v = so(r.get('valid_pixels'))
        return (v == 0) or (str(r.get('status') or '').strip() not in ('', 'OK', 'OK_TOA'))

    rong = [r for r in rows if khong_co_anh(r)]
    co_anh = [r for r in rows if not khong_co_anh(r)]
    print(f'\n3. DÒNG KHÔNG CÓ ẢNH (valid_pixels = 0 hoặc status khác OK)')
    if not rong:
        print('   Không có dòng nào.')
    else:
        ky = sorted({str(r.get('period') or r.get('year')) for r in rong})
        print(f'   {len(rong)} dòng ({100 * len(rong) / len(rows):.1f}%) — '
              f'{len({r.get("province_code") for r in rong})} tỉnh, '
              f'{len(ky)} mốc thời gian')
        print(f'   Ví dụ: {", ".join(ky[:10])}' + (' …' if len(ky) > 10 else ''))
        print('   Mọi cột thống kê của các dòng này đều trống — đúng như phải thế.')
        print('   Chúng được loại khỏi phép đếm ô trống bên dưới.')

    # --- 4. Ô trống trên những dòng CÓ ảnh ---
    print('\n4. Ô TRỐNG (chỉ tính trên dòng có ảnh)')
    nen = co_anh or rows
    for c in header:
        n = sum(1 for r in nen if so(r.get(c)) is None and not str(r.get(c) or '').strip())
        if not n:
            continue
        pct = 100 * n / len(nen)
        if c in TRONG_HOP_LE:
            print(f'   {c:<22} {n:>6} ({pct:5.1f}%)  dự kiến: {TRONG_HOP_LE[c]}')
        else:
            loi += 1
            print(f'   {c:<22} {n:>6} ({pct:5.1f}%)  >>> KHÔNG dự kiến trống')

    # --- 5. Miền giá trị ---
    print('\n5. GIÁ TRỊ NGOÀI MIỀN HỢP LỆ')
    ngoai = False
    for c, (lo, hi) in MIEN.items():
        if c not in header:
            continue
        xau = [(i + 2, v) for i, r in enumerate(rows)
               for v in [so(r.get(c))] if isinstance(v, float)
               and ((lo is not None and v < lo) or (hi is not None and v > hi))]
        if not xau:
            continue
        mien = f'[{lo}, {hi if hi is not None else "∞"}]'
        tran = NGUONG_TAO_TAC.get(c)
        nang = [x for x in xau if tran is None or x[1] > tran]
        if tran is not None and not nang:
            # Vượt trần nhẹ là tạo tác lưới pixel đã biết, không phải hỏng dữ liệu.
            print(f'   [ĐÃ BIẾT] {c}: {len(xau)} giá trị vượt {hi} nhưng dưới {tran} — '
                  'pixel chạm ranh giới được tính trọn, lớn nhất '
                  f'{max(v for _, v in xau):g}')
            continue
        ngoai = True
        loi += 1
        print(f'   {c}: {len(nang)} giá trị ngoài {mien}, ví dụ '
              + ', '.join(f'dòng {d}={v:g}' for d, v in nang[:3]))
    if not ngoai:
        print('   Mọi giá trị nằm trong miền hợp lệ.')

    # --- 6. Phân phối ---
    print('\n6. PHÂN PHỐI (điểm dị biệt = ngoài 1,5 lần khoảng tứ phân vị)')
    print(f'   {"Cột":<22}{"nhỏ nhất":>12}{"trung vị":>12}{"lớn nhất":>14}{"dị biệt":>9}')
    for c in header:
        if c in CHU or c in ('year', 'month'):
            continue
        v = [x for r in rows for x in [so(r.get(c))] if isinstance(x, float)]
        if len(v) < 10:
            continue
        q1, q3 = phan_vi(v, .25), phan_vi(v, .75)
        iqr = q3 - q1
        dau = f'   {c:<22}{min(v):>12,.2f}{phan_vi(v, .5):>12,.2f}{max(v):>14,.2f}'
        if not iqr:
            print(dau + f'{"hằng số":>12}')
            continue
        db = sum(1 for x in v if x < q1 - 1.5 * iqr or x > q3 + 1.5 * iqr)
        print(dau + f'{db:>6} ({100 * db / len(v):.0f}%)')
    print('\n   Dị biệt KHÔNG mặc nhiên là lỗi: Hà Nội và TP.HCM luôn nằm ngoài khoảng của')
    print('   61 tỉnh còn lại, và Bình Thuận sáng bất thường vì đèn thanh long.')
    return loi


def main():
    parser = argparse.ArgumentParser(description='Kiểm nghiệm chất lượng bộ dữ liệu đêm')
    parser.add_argument('--root', default='/data/SatelliteData')
    parser.add_argument('--bang', default=None, help='Chỉ kiểm một bảng')
    arguments = parser.parse_args()
    thu_muc = Path(arguments.root) / NTL_PACKAGE / 'data_processed'
    ten = [arguments.bang] if arguments.bang else [
        'ntl_panel', 'ntl_annual', 'ntl_monthly', 'ntl_overlap_2013']

    tong = 0
    da_kiem = 0
    for t in ten:
        path = thu_muc / f'{t}.csv'
        if not path.exists():
            print(f'\n{t}: CHƯA CÓ ({path})')
            continue
        header, rows = doc(path)
        if not rows:
            print(f'\n{t}: BẢNG RỖNG')
            tong += 1
            continue
        tong += kiem_dinh(t, header, rows)
        da_kiem += 1

    print(f'\n{"=" * 78}')
    if not da_kiem:
        raise SystemExit('Không kiểm được bảng nào. Kiểm tra --root.')
    print('KHÔNG phát hiện vấn đề kỹ thuật nào.' if not tong else
          f'{tong} mục cần xem lại ở trên.')
    raise SystemExit(0 if not tong else 1)


if __name__ == '__main__':
    main()
