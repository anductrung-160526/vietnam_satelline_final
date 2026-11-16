r"""Soi tháng trống và dao động bất thường của sol trong chuỗi VIIRS theo tháng.

CÂU HỎI CẦN TRẢ LỜI: tháng bị "–" và sol nhảy từ hàng chục lên hàng nghìn là do
tải thiếu ảnh, do lỗi tính, hay do bản chất sản phẩm VIIRS?

Script không đoán. Nó dùng đúng ba cột đã có sẵn trong bảng — `valid_pixels`,
`cloud_free_obs`, `sol` — để tách ba nguyên nhân:

  (a) KHÔNG CÓ ẢNH      status = CHUA_CO_ANH / MISSING_SOURCE, hoặc không có dòng.
  (b) CÓ ẢNH, KHÔNG PIXEL   valid_pixels = 0. Ảnh về nhưng cf_cvg = 0 trên toàn tỉnh:
      tháng đó không có lượt quan sát nào sạch mây. Mùa mưa, không phải lỗi.
  (c) PIXEL THIẾU MỘT PHẦN  valid_pixels thấp hơn hẳn mức thường của chính tỉnh đó.
      Đây là nguyên nhân chính của dao động: `sol` là TỔNG trên các pixel hợp lệ,
      nên tháng chỉ quan sát được 30 % diện tích thì sol cũng chỉ còn khoảng 30 %,
      dù tỉnh không hề tối đi.

Phép kiểm quyết định nằm ở mục 4: chia sol cho độ phủ. Nếu dao động xẹp xuống thì
nguyên nhân đúng là độ phủ chứ không phải kinh tế hay lỗi tính.

    python scripts\kiem_tra_thang_thieu.py --root E:\SatelliteData
    python scripts\kiem_tra_thang_thieu.py --root E:\SatelliteData --tinh 01 79
"""
import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

GOI_NTL = 'VN_NTL_Panel_2004_2025'
NGUONG_PHU = 0.80      # dưới 80 % mức phủ thường lệ thì sol không so sánh được
NGUONG_IT_OBS = 2.0    # trùng IT_TIN_CAY của derive.py


def doc(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def so(x):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return None


def nap(path, tinh=None):
    """Mỗi dòng tháng -> (mã tỉnh, mốc, sol, valid_pixels, cloud_free_obs, status)."""
    ra = []
    for r in doc(path):
        thang = so(r.get('month'))
        if not thang:                       # month = 0 là dòng theo năm, không xét ở đây
            continue
        ma = (r.get('province_code') or '').zfill(2)
        if tinh and ma not in tinh:
            continue
        ra.append({'ma': ma, 'ten': r.get('province_name') or ma,
                   'moc': r.get('period') or f"{r.get('year')}-{int(thang):02d}",
                   'sol': so(r.get('sol')), 'pix': so(r.get('valid_pixels')),
                   'cf': so(r.get('cloud_free_obs')),
                   'status': (r.get('status') or '').strip(),
                   'obs': (r.get('obs_status') or '').strip()})
    return ra


def do_phu(dong):
    """Độ phủ = valid_pixels / mức phủ thường lệ CỦA CHÍNH TỈNH ĐÓ (trung vị tháng đầy).

    Lấy trung vị thay vì cực đại: một tháng quang mây bất thường không được thành
    thước đo cho cả chuỗi.
    """
    theo_tinh = defaultdict(list)
    for d in dong:
        if d['pix']:
            theo_tinh[d['ma']].append(d['pix'])
    chuan = {ma: statistics.median(v) for ma, v in theo_tinh.items() if v}
    for d in dong:
        goc = chuan.get(d['ma'])
        d['phu'] = (d['pix'] / goc) if (goc and d['pix'] is not None) else None
    return chuan


def phan_loai(d):
    # Ranh giới quan trọng nhất của cả script: "không có ảnh" là việc PHẢI TẢI LẠI,
    # còn "có ảnh mà 0 pixel" là mây và không sửa được bằng cách tải. Chỉ status và
    # obs_status mới phân biệt được hai cái đó — sol rỗng thì cả hai đều rỗng như nhau.
    if d['status'] in ('CHUA_CO_ANH', 'MISSING_SOURCE') or d['obs'] == 'O':
        return 'a_khong_co_anh'
    if not d['pix']:
        return 'b_khong_pixel'
    if d['phu'] is not None and d['phu'] < NGUONG_PHU:
        return 'c_phu_thieu'
    return 'd_binh_thuong'


def bang_thang(dong):
    theo_moc = defaultdict(list)
    for d in dong:
        theo_moc[d['moc']].append(d)
    return theo_moc


def in_muc_1(theo_moc, so_tinh):
    print('\n1. THÁNG YẾU TRÊN TOÀN QUỐC (xếp theo độ phủ trung vị, thấp nhất trước)')
    print('   Độ phủ = số pixel hợp lệ / mức thường lệ của chính tỉnh đó.')
    hang = []
    for moc, ds in theo_moc.items():
        phu = [d['phu'] for d in ds if d['phu'] is not None]
        cf = [d['cf'] for d in ds if d['cf'] is not None]
        trong = sum(1 for d in ds if phan_loai(d) in ('a_khong_co_anh', 'b_khong_pixel'))
        hang.append((statistics.median(phu) if phu else 0.0, moc, len(ds), trong,
                     statistics.median(cf) if cf else None))
    hang.sort()
    print(f"   {'Mốc':<9}{'Tỉnh có dòng':>13}{'Tỉnh trống':>12}{'Phủ trung vị':>14}"
          f"{'cf_cvg trung vị':>17}")
    for phu, moc, n, trong, cf in hang[:15]:
        cua = f'{cf:.2f}' if cf is not None else '—'
        co = '  << yếu' if phu < NGUONG_PHU else ''
        print(f'   {moc:<9}{n:>13}{trong:>12}{phu:>13.0%}{cua:>17}{co}')
    if len(hang) > 15:
        print(f'   … còn {len(hang) - 15} mốc nữa, đều khá hơn.')
    yeu = [h for h in hang if h[0] < NGUONG_PHU]
    print(f'\n   => {len(yeu)}/{len(hang)} mốc có độ phủ trung vị dưới {NGUONG_PHU:.0%}.')
    if yeu:
        print('   Những mốc này KHÔNG so sánh được với mốc khác bằng cột sol thô.')


def in_muc_2(dong):
    print('\n2. VÌ SAO TRỐNG — tách ba nguyên nhân')
    dem = defaultdict(int)
    for d in dong:
        dem[phan_loai(d)] += 1
    tong = len(dong) or 1
    nhan = {'a_khong_co_anh': 'Không có ảnh (tải thiếu hoặc NOAA không phát hành)',
            'b_khong_pixel': 'Có ảnh nhưng 0 pixel hợp lệ (cf_cvg = 0 toàn tỉnh)',
            'c_phu_thieu':   f'Pixel thiếu một phần (phủ < {NGUONG_PHU:.0%})',
            'd_binh_thuong': 'Bình thường'}
    for k in ('a_khong_co_anh', 'b_khong_pixel', 'c_phu_thieu', 'd_binh_thuong'):
        print(f'   {dem[k]:>6} dòng ({dem[k]/tong:5.1%})  {nhan[k]}')
    if dem['a_khong_co_anh']:
        print('\n   >>> Có dòng thiếu ẢNH: đây là việc phải tải lại, xem mục 3.')
    if dem['b_khong_pixel'] or dem['c_phu_thieu']:
        print('\n   >>> Phần lớn ô trống và dao động đến từ MÂY, không phải lỗi tải hay lỗi tính.')


def in_muc_3(dong):
    thieu = defaultdict(list)
    for d in dong:
        if phan_loai(d) == 'a_khong_co_anh':
            thieu[d['moc']].append(d['ten'])
    if not thieu:
        print('\n3. ẢNH THIẾU CẦN TẢI LẠI: không có. Mọi tỉnh-tháng đều có ảnh.')
        return
    print('\n3. ẢNH THIẾU CẦN TẢI LẠI')
    for moc in sorted(thieu):
        ten = thieu[moc]
        print(f'   {moc}: {len(ten)} tỉnh — ' + ', '.join(ten[:6])
              + (' …' if len(ten) > 6 else ''))


def in_muc_4(dong, so_tinh_mau=3):
    """Phép kiểm quyết định: chia sol cho độ phủ, xem dao động có xẹp không."""
    print('\n4. PHÉP KIỂM: chia sol cho độ phủ')
    print('   Nếu dao động của sol là do thiếu pixel thì sol/độ-phủ phải mượt hơn hẳn.')
    theo_tinh = defaultdict(list)
    for d in dong:
        if d['sol'] and d['phu']:
            theo_tinh[d['ma']].append(d)
    if not theo_tinh:
        print('   Không đủ dòng hợp lệ để kiểm.')
        return
    def bien_thien(v):
        return statistics.pstdev(v) / statistics.fmean(v) if len(v) > 1 and statistics.fmean(v) else 0

    truoc, sau = [], []
    for ma, ds in theo_tinh.items():
        if len(ds) < 6:
            continue
        truoc.append(bien_thien([d['sol'] for d in ds]))
        sau.append(bien_thien([d['sol'] / d['phu'] for d in ds]))
    if not truoc:
        print('   Không tỉnh nào đủ 6 tháng để kiểm.')
        return
    a, b = statistics.fmean(truoc), statistics.fmean(sau)
    print(f'   Hệ số biến thiên trung bình của sol      : {a:.3f}')
    print(f'   Hệ số biến thiên sau khi chia cho độ phủ : {b:.3f}')
    if b < a * 0.7:
        print(f'   => Giảm {1 - b/a:.0%}. ĐỘ PHỦ là nguyên nhân chính của dao động.')
    elif b < a:
        print(f'   => Chỉ giảm {1 - b/a:.0%}. Độ phủ giải thích một phần, còn nguyên nhân khác.')
    else:
        print('   => Không giảm. Dao động KHÔNG do độ phủ — phải soi tiếp phần tính toán.')

    print('\n   Vài tỉnh làm ví dụ (mốc phủ thấp nhất của mỗi tỉnh):')
    for ma in sorted(theo_tinh)[:so_tinh_mau]:
        ds = sorted(theo_tinh[ma], key=lambda d: d['phu'])[:3]
        print(f"   {ds[0]['ten']}:")
        for d in ds:
            print(f"     {d['moc']}  sol = {d['sol']:>12,.0f}  phủ = {d['phu']:>5.0%}"
                  f"  -> quy về đủ phủ: {d['sol']/d['phu']:>12,.0f}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', type=Path, default=Path('/data/SatelliteData'))
    p.add_argument('--bang', type=Path, default=None,
                   help='Đường dẫn thẳng tới ntl_monthly.csv, bỏ qua --root')
    p.add_argument('--tinh', nargs='*', default=None, help='Lọc theo mã tỉnh, ví dụ 01 79')
    a = p.parse_args()

    path = a.bang or (a.root / GOI_NTL / 'data_processed' / 'ntl_monthly.csv')
    if not path.is_file():
        raise SystemExit(f'Không thấy {path}')
    tinh = {t.zfill(2) for t in a.tinh} if a.tinh else None
    dong = nap(path, tinh)
    if not dong:
        raise SystemExit('Không có dòng theo tháng nào trong bảng.')
    do_phu(dong)
    so_tinh = len({d['ma'] for d in dong})
    print(f'Nguồn: {path}')
    print(f'{len(dong)} dòng tháng · {so_tinh} tỉnh · '
          f"{min(d['moc'] for d in dong)} → {max(d['moc'] for d in dong)}")
    in_muc_1(bang_thang(dong), so_tinh)
    in_muc_2(dong)
    in_muc_3(dong)
    in_muc_4(dong)
    print('\nĐỌC KẾT QUẢ: mục 3 là việc phải sửa (tải lại ảnh). Mục 1, 2, 4 là bản chất')
    print('sản phẩm VIIRS theo tháng — cách xử lý xem docs/CHI_SO_KINH_TE_DEM.md.')


if __name__ == '__main__':
    main()
