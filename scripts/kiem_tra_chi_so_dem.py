"""Soi bảng chỉ số đêm: tìm chỗ sai trước khi số liệu đi vào báo cáo.

    python scripts/kiem_tra_chi_so_dem.py --root E:\\SatelliteData
    python scripts/kiem_tra_chi_so_dem.py --root E:\\SatelliteData --tinh 01

Không sửa gì, chỉ đọc. Mỗi mục in ĐẠT hoặc XEM LẠI kèm con số để tự phán đoán,
vì một chỉ số bất thường chưa chắc là lỗi — có thể là hiện tượng thật.
"""
import argparse
import csv
from pathlib import Path

NTL_PACKAGE = 'VN_NTL_Panel_2004_2025'
NAM_DAU, NAM_CUOI = 2004, 2025
SO_TINH = 63


def so(value):
    text = str(value or '').strip()
    if text in ('', 'NA', 'NaN', 'None', '-9999'):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def doc(path):
    with open(path, encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def ket(dat, nhan, chi_tiet=''):
    print(f"  [{'ĐẠT' if dat else 'XEM LẠI'}] {nhan}" + (f' — {chi_tiet}' if chi_tiet else ''))
    return dat


def kiem_tra(rows):
    tot = True
    print('\n1. Độ phủ')
    tinh = {r['ma_tinh'] for r in rows}
    tot &= ket(len(tinh) == SO_TINH, f'{len(tinh)} tỉnh', f'cần {SO_TINH}')
    thieu = [f"{r['ma_tinh']}/{r['nam']}" for r in rows if so(r.get('sol_ntl')) is None]
    tot &= ket(not thieu, f'{len(rows) - len(thieu)}/{len(rows)} dòng có sol_ntl',
               ', '.join(thieu[:6]) + (' …' if len(thieu) > 6 else '') if thieu else '')

    print('\n2. Nguồn ảnh đúng giai đoạn (DMSP ≤2013, VIIRS ≥2014)')
    sai = [f"{r['ma_tinh']}/{r['nam']}={r.get('nguon_anh')}" for r in rows
           if r.get('nguon_anh') != ('DMSP' if int(r['nam']) <= 2013 else 'VIIRS')]
    tot &= ket(not sai, f'{len(rows) - len(sai)}/{len(rows)} dòng đúng nguồn',
               ', '.join(sai[:6]) if sai else '')

    print('\n3. Trừ ánh sáng nền có tác dụng thật không')
    viirs = [r for r in rows if r.get('nguon_anh') == 'VIIRS']
    cap = [(so(r.get('sol_ntl')), so(r.get('sol_ntl_tho'))) for r in viirs]
    cap = [(a, b) for a, b in cap if a is not None and b is not None and b > 0]
    if cap:
        ty = 100 * (1 - sum(a for a, _ in cap) / sum(b for _, b in cap))
        tot &= ket(0.1 < ty < 60, f'nền chiếm {ty:.1f}% tổng thô của VIIRS',
                   'bằng 0 là chưa trừ; trên 60% là ngưỡng quá cao')
    dmsp = [r for r in rows if r.get('nguon_anh') == 'DMSP']
    bang = sum(1 for r in dmsp if so(r.get('sol_ntl')) == so(r.get('sol_ntl_tho')))
    tot &= ket(bang == len(dmsp), f'DMSP: {bang}/{len(dmsp)} dòng không bị trừ nền',
               'đúng quy tắc, stable_lights đã loại nền sẵn')

    print('\n4. Mốc đổi vệ tinh 2013→2014')
    goc, hc = [], []
    for ma in sorted({r['ma_tinh'] for r in rows}):
        theo = {int(r['nam']): r for r in rows if r['ma_tinh'] == ma}
        a, b = theo.get(2013), theo.get(2014)
        if not (a and b):
            continue
        if so(b.get('thay_doi_ntl')) is not None:
            goc.append(ma)
        v = so(b.get('thay_doi_ntl_hc'))
        if v is not None:
            hc.append(abs(v))
    tot &= ket(not goc, f'cột gốc bỏ trống ở mốc đổi nguồn ({len(goc)} tỉnh có số)',
               'cột gốc không được so xuyên hai thang đo')
    if hc:
        tb = sum(hc) / len(hc)
        tot &= ket(tb < 60, f'cột _hc: biến động trung bình {tb:.1f}% tại mốc',
                   f'{len(hc)} tỉnh; trên 60% nghĩa là hiệu chỉnh chưa khớp')

    print('\n5. Xếp hạng 2025 — kiểm tra bằng hiểu biết thực tế')
    cuoi = sorted((r for r in rows if int(r['nam']) == NAM_CUOI
                   and so(r.get('sol_ntl')) is not None),
                  key=lambda r: -so(r['sol_ntl']))[:5]
    for i, r in enumerate(cuoi, 1):
        print(f"     {i}. {r['ten_tinh']:<20} sol={so(r['sol_ntl']):>12,.0f}"
              f"  mật độ={so(r.get('mat_do_ntl')) or 0:>8.2f}"
              f"  sáng={so(r.get('ty_le_sang_pct')) or 0:>5.1f}%")
    ten = ' '.join(r['ten_tinh'] for r in cuoi).lower()
    tot &= ket('chí minh' in ten or 'nội' in ten, 'hai đô thị lớn nhất nằm trong tốp 5',
               'nếu không, nhiều khả năng ảnh bị lệch tỉnh')

    print('\n6. Biến động bất thường trong cùng một nguồn ảnh')
    manh = [(abs(so(r['thay_doi_ntl'])), r) for r in rows
            if so(r.get('thay_doi_ntl')) is not None and abs(so(r['thay_doi_ntl'])) > 50]
    tot &= ket(len(manh) < len(rows) * 0.02,
               f'{len(manh)} dòng biến động quá 50%/năm', 'dưới 2% tổng số là bình thường')
    # Một tỉnh nhảy vọt là chuyện thường. Nhiều tỉnh cùng nhảy trong MỘT năm thì không
    # phải kinh tế, mà là lỗi xử lý của riêng năm đó — đây mới là dấu hiệu đáng tìm.
    theo_nam = {}
    for _, r in manh:
        theo_nam[r['nam']] = theo_nam.get(r['nam'], 0) + 1
    dong_loat = sorted(((n, c) for n, c in theo_nam.items() if c >= 10), key=lambda x: -x[1])
    tot &= ket(not dong_loat, 'không năm nào có từ 10 tỉnh cùng biến động mạnh',
               '; '.join(f'{n}: {c} tỉnh' for n, c in dong_loat[:4]) if dong_loat else '')
    for _, r in sorted(manh, reverse=True, key=lambda x: x[0])[:5]:
        print(f"     {r['ten_tinh']:<20} {r['nam']}  {so(r['thay_doi_ntl']):+8.1f}%"
              f"  ({r.get('nguon_anh')})")
    return tot


def mot_tinh(rows, ma):
    cua = sorted((r for r in rows if r['ma_tinh'] == ma.zfill(2)), key=lambda r: int(r['nam']))
    if not cua:
        raise SystemExit(f'Không có tỉnh mã {ma}.')
    print(f"\n=== {cua[0]['ten_tinh']} (mã {cua[0]['ma_tinh']}) ===")
    print(f"{'Năm':<6}{'Nguồn':<7}{'sol_ntl':>14}{'sol_ntl_hc':>14}"
          f"{'mật độ':>10}{'%sáng':>8}{'thay đổi':>10}{'cv':>7}")
    for r in cua:
        def c(k, d=2):
            v = so(r.get(k))
            return f'{v:,.{d}f}' if v is not None else '—'
        print(f"{r['nam']:<6}{r.get('nguon_anh', ''):<7}{c('sol_ntl', 0):>14}"
              f"{c('sol_ntl_hc', 0):>14}{c('mat_do_ntl'):>10}{c('ty_le_sang_pct', 1):>8}"
              f"{c('thay_doi_ntl', 1):>10}{c('cv_ntl'):>7}")
    print('\nCột thay đổi bỏ trống ở 2014 là đúng: đó là mốc đổi vệ tinh, '
          'muốn so xuyên mốc thì dùng thay_doi_ntl_hc.')


def main():
    parser = argparse.ArgumentParser(description='Kiểm tra bảng chỉ số đêm')
    parser.add_argument('--root', default='/data/SatelliteData')
    parser.add_argument('--tinh', default=None, help='Mã tỉnh, ví dụ 01, để in cả chuỗi 22 năm')
    arguments = parser.parse_args()

    path = Path(arguments.root) / NTL_PACKAGE / 'data_processed' / 'ntl_annual.csv'
    if not path.exists():
        raise SystemExit(f'Chưa có {path}.')
    rows = doc(path)
    print(f'Nguồn: {path}\n{len(rows)} dòng, {len(rows[0])} cột')

    if arguments.tinh:
        mot_tinh(rows, arguments.tinh)
        return
    tot = kiem_tra(rows)
    print('\n' + ('TẤT CẢ ĐẠT — số liệu dùng được.' if tot else
                  'CÓ MỤC CẦN XEM LẠI ở trên. Không phải mục nào cũng là lỗi, '
                  'nhưng phải giải thích được trước khi đưa vào báo cáo.'))
    print('Xem chuỗi một tỉnh:  --tinh 01')
    raise SystemExit(0 if tot else 1)


if __name__ == '__main__':
    main()
