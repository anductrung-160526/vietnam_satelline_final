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


def _moc_chuan(dong):
    """Với mỗi tỉnh-năm, lấy trung vị sol của các tháng ĐỦ PHỦ làm mức tham chiếu.

    Phải so trong cùng một tỉnh và cùng một năm. So trên cả chuỗi 2013–2025 là trộn
    xu thế dài hạn và chu kỳ mùa vào cùng một con số, phần do độ phủ sẽ chìm mất —
    đó là lỗi của bản đầu tiên của phép kiểm này.
    """
    gom = defaultdict(list)
    for d in dong:
        if d['sol'] and d['phu'] and d['phu'] >= NGUONG_PHU:
            gom[(d['ma'], d['moc'][:4])].append(d['sol'])
    return {k: statistics.median(v) for k, v in gom.items() if len(v) >= 4}


def in_muc_4(dong, so_tinh_mau=3):
    """sol có co theo độ phủ không? So mỗi dòng với mức thường lệ của CHÍNH tỉnh-năm đó."""
    import math
    print('\n4. sol CÓ CO THEO ĐỘ PHỦ KHÔNG')
    print('   Mỗi dòng so với trung vị các tháng đủ phủ của chính tỉnh đó, trong chính')
    print('   năm đó. Nếu mất pixel là nguyên nhân thì tỷ lệ sol phải bằng đúng độ phủ.')
    chuan = _moc_chuan(dong)
    cap = [(d, chuan[(d['ma'], d['moc'][:4])]) for d in dong
           if d['sol'] and d['phu'] and (d['ma'], d['moc'][:4]) in chuan]
    thap = [(d, c) for d, c in cap if d['phu'] < NGUONG_PHU]
    if len(thap) < 10:
        print(f'   Chỉ {len(thap)} dòng phủ thấp có mức tham chiếu — không đủ để kết luận.')
        return
    # Độ co giãn log-log: d(log sol)/d(log phủ). Bằng 1 nghĩa là mất một nửa pixel thì
    # mất đúng một nửa sol (pixel mất đi sáng ngang mức trung bình). Dưới 1: pixel mất
    # đi TỐI hơn trung bình. Trên 1: pixel mất đi SÁNG hơn trung bình.
    xs = [math.log(d['phu']) for d, c in thap]
    ys = [math.log(d['sol'] / c) for d, c in thap]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    tu = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    mau = sum((x - mx) ** 2 for x in xs)
    doc_giai = tu / mau if mau else None
    ty_le = statistics.median(math.exp(y) for y in ys)
    phu_tv = statistics.median(d['phu'] for d, c in thap)
    print(f'   {len(thap)} dòng có độ phủ < {NGUONG_PHU:.0%} và có mức tham chiếu.')
    print(f'   Độ phủ trung vị của nhóm này      : {phu_tv:.0%}')
    print(f'   sol còn lại so với mức thường lệ  : {ty_le:.0%}')
    if doc_giai is not None:
        print(f'   Độ co giãn sol theo độ phủ        : {doc_giai:.2f}')
        if doc_giai < 0.15:
            print('   => sol gần như KHÔNG đổi theo độ phủ. Mất pixel không giải thích')
            print('      được dao động — nguyên nhân nằm chỗ khác.')
        elif doc_giai > 1.25:
            print('   => sol tụt NHANH HƠN độ phủ: phần bị mây che chính là vùng sáng')
            print('      (đô thị). Mất 1/2 pixel mất hơn 1/2 ánh sáng.')
        elif doc_giai < 0.75:
            print('   => sol tụt CHẬM HƠN độ phủ: phần bị mất chủ yếu là vùng tối.')
        else:
            print('   => sol co gần đúng theo độ phủ: pixel mất đi sáng ngang mức trung bình.')

    # Dao động còn lại khi CHỈ giữ các tháng đủ phủ, so trong từng năm một.
    du = defaultdict(list)
    for d, c in cap:
        if d['phu'] >= NGUONG_PHU:
            du[(d['ma'], d['moc'][:4])].append(d['sol'])
    cv = [statistics.pstdev(v) / statistics.fmean(v)
          for v in du.values() if len(v) >= 6 and statistics.fmean(v)]
    if cv:
        print(f'\n   Dao động trong năm khi CHỈ lấy tháng đủ phủ: hệ số biến thiên trung')
        print(f'   bình {statistics.fmean(cv):.2f} ({len(cv)} tỉnh-năm).')
        if statistics.fmean(cv) > 0.3:
            print('   => Ngay cả tháng đủ phủ cũng dao động mạnh. Đây mới là vấn đề chính,')
            print('      và nó KHÔNG phải do mất pixel. Xem mục 5.')

    print('\n   Vài tỉnh làm ví dụ (mốc phủ thấp nhất của mỗi tỉnh):')
    theo_tinh = defaultdict(list)
    for d, c in cap:
        theo_tinh[d['ma']].append((d, c))
    for ma in sorted(theo_tinh)[:so_tinh_mau]:
        ds = sorted(theo_tinh[ma], key=lambda t: t[0]['phu'])[:3]
        print(f"   {ds[0][0]['ten']}:")
        for d, c in ds:
            print(f"     {d['moc']}  sol = {d['sol']:>11,.0f}  phủ = {d['phu']:>5.0%}"
                  f"  mức thường lệ cùng năm = {c:>11,.0f}"
                  f"  -> còn {d['sol']/c:>5.0%}")


def in_muc_5(dong):
    """Số lượt quan sát sạch mây: ít lượt thì giá trị tháng nào cũng nhiễu, kể cả đủ phủ."""
    print('\n5. SỐ LƯỢT QUAN SÁT SẠCH MÂY (cf_cvg)')
    cf = [d['cf'] for d in dong if d['cf'] is not None]
    if not cf:
        print('   Bảng không có cột cloud_free_obs — không kiểm được.')
        return
    cf.sort()
    def pv(p):
        return cf[min(len(cf) - 1, int(len(cf) * p))]
    print(f'   Trung vị {statistics.median(cf):.2f} lượt · '
          f'phân vị 10 % = {pv(.10):.2f} · phân vị 90 % = {pv(.90):.2f}')
    it = sum(1 for x in cf if x < NGUONG_IT_OBS)
    print(f'   {it}/{len(cf)} dòng ({it/len(cf):.0%}) dưới {NGUONG_IT_OBS} lượt.')
    if statistics.median(cf) < 3:
        print('   => Trung vị rất thấp. Giá trị mỗi tháng dựng trên một hai lượt quan sát,')
        print('      nên nhiễu lớn là chuyện đương nhiên — kể cả tháng đủ phủ pixel.')
        print('      Chuỗi theo NĂM (trung vị 12 tháng) đáng tin hơn hẳn chuỗi theo tháng.')


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
    in_muc_5(dong)
    print('\nĐỌC KẾT QUẢ')
    print('  Mục 3 là việc phải sửa: tải lại, hoặc xác nhận NOAA không có ảnh tháng đó.')
    print('  Mục 4 cho biết mất pixel có giải thích được dao động hay không.')
    print('  Mục 5 cho biết mỗi giá trị tháng dựng trên bao nhiêu lượt quan sát; ít lượt')
    print('  thì nhiễu lớn ngay cả khi đủ pixel, và chuỗi theo năm đáng tin hơn hẳn.')


if __name__ == '__main__':
    main()
