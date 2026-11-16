r"""Một tỉnh-tháng có ảnh trên Earth Engine nhưng không có trong bảng: rơi ở khâu nào?

Đường đi của một ảnh có bốn chặng, và mỗi chặng để lại dấu vết riêng:

    1. state.json    job được ghi nhận, có trạng thái (DONE_LOCAL / FAILED / ...)
    2. biên nhận     .local_state/receipts/<job_id>.json — đã tải và kiểm tra xong
    3. tệp thô       raw_data/NTL/VIIRS/<tỉnh>/*_<mốc>.tif
    4. bảng          data_processed/ntl_monthly.csv

`local.raw_index` chỉ nhận ảnh khi trạng thái là DONE_LOCAL **và** biên nhận có
**và** tệp còn trên đĩa. Thiếu bất kỳ cái nào thì tháng đó biến mất khỏi bảng mà
không báo lỗi. Script so bốn chặng với nhau để chỉ ra chặng đứt.

    python scripts\kiem_tra_khau_roi.py --root E:\SatelliteData --moc 2022-07
    python scripts\kiem_tra_khau_roi.py --root E:\SatelliteData --moc 2022-07 --chi-tiet

Chỉ đọc, không sửa gì.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

GOI_NTL = 'VN_NTL_Panel_2004_2025'


def cac_state(root):
    """Mỗi nhánh một state.json dưới _control/<NNN_NNN>/.local_state/."""
    return sorted(Path(root).glob('_control/*/.local_state/state.json'))


def quet_state(root, moc):
    """Trạng thái của mọi job có chứa mốc này, gom theo nhánh."""
    ra = {}
    for path in cac_state(root):
        nhanh = path.parent.parent.name
        try:
            state = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as loi:
            ra[nhanh] = {'loi': str(loi)}
            continue
        jobs = state.get('jobs') or {}
        khop = {jid: (e or {}).get('status') for jid, e in jobs.items()
                if moc in jid and 'VIIRS' in jid.upper()}
        ra[nhanh] = {'tong_job': len(jobs), 'khop': khop}
    return ra


def quet_bien_nhan(root, moc):
    ra = {}
    for path in Path(root).glob('_control/*/.local_state/receipts'):
        nhanh = path.parent.parent.name
        ra[nhanh] = sorted(f.stem for f in path.glob('*.json')
                           if moc in f.stem and 'VIIRS' in f.stem.upper())
    return ra


def quet_tep(root, moc):
    """Tệp thô VIIRS của mốc này, bất kể nằm thư mục tỉnh nào."""
    goc = Path(root) / GOI_NTL / 'raw_data' / 'NTL' / 'VIIRS'
    if not goc.is_dir():
        return None
    return sorted(p for p in goc.rglob(f'*{moc}*.tif') if p.is_file())


def quet_bang(root, moc):
    path = Path(root) / GOI_NTL / 'data_processed' / 'ntl_monthly.csv'
    if not path.is_file():
        return None
    co, trong = set(), set()
    with open(path, newline='', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if (r.get('period') or '').strip() != moc:
                continue
            ma = (r.get('province_code') or '').zfill(2)
            (co if (r.get('sol') or '').strip() else trong).add(ma)
    return co, trong


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', type=Path, default=Path('/data/SatelliteData'))
    p.add_argument('--moc', nargs='+', required=True, help='Mốc tháng, ví dụ 2022-07')
    p.add_argument('--chi-tiet', action='store_true', dest='chi_tiet',
                   help='In từng job_id thay vì chỉ đếm')
    a = p.parse_args()

    if not Path(a.root).is_dir():
        raise SystemExit(f'Không thấy thư mục gốc {a.root}')
    states = cac_state(a.root)
    print(f'Gốc dữ liệu: {a.root}')
    print(f'{len(states)} tệp state.json: '
          + (', '.join(s.parent.parent.name for s in states) or 'KHÔNG CÓ'))
    if not states:
        print('\nKhông có state.json nào. Hoặc sai --root, hoặc thư mục _control nằm trên')
        print('máy khác — trạng thái job là của riêng từng máy chạy luồng tải.')

    for moc in a.moc:
        print(f'\n=== {moc} ===')

        print('\n1. TRẠNG THÁI JOB trong state.json')
        tong = Counter()
        for nhanh, info in quet_state(a.root, moc).items():
            if 'loi' in info:
                print(f'   {nhanh}: ĐỌC KHÔNG ĐƯỢC — {info["loi"]}')
                continue
            dem = Counter(info['khop'].values())
            tong.update(dem)
            mo_ta = ', '.join(f'{k or "(trống)"}={v}' for k, v in sorted(
                dem.items(), key=lambda x: str(x[0]))) or 'không job nào khớp'
            print(f'   {nhanh}: {mo_ta}   (tổng {info["tong_job"]} job trong tệp)')
            if a.chi_tiet:
                for jid, st in sorted(info['khop'].items()):
                    print(f'      {st or "(trống)":<16} {jid}')
        if tong:
            print('   Cộng lại: ' + ', '.join(f'{k or "(trống)"}={v}'
                                              for k, v in sorted(tong.items(), key=lambda x: str(x[0]))))

        bn = quet_bien_nhan(a.root, moc)
        so_bn = sum(len(v) for v in bn.values())
        print(f'\n2. BIÊN NHẬN: {so_bn} tệp')

        tep = quet_tep(a.root, moc)
        if tep is None:
            print('\n3. TỆP THÔ: không thấy thư mục raw_data/NTL/VIIRS')
        else:
            print(f'\n3. TỆP THÔ trên đĩa: {len(tep)} tệp'
                  + (f'  (ví dụ {tep[0].name})' if tep else ''))
            rong = [t for t in tep if t.stat().st_size < 1024]
            if rong:
                print(f'   {len(rong)} tệp nhỏ bất thường (<1 KB) — nhiều khả năng hỏng.')

        bang = quet_bang(a.root, moc)
        if bang is None:
            print('\n4. BẢNG: chưa có ntl_monthly.csv')
        else:
            co, trong = bang
            print(f'\n4. BẢNG ntl_monthly: {len(co)} tỉnh có số · {len(trong)} tỉnh dòng rỗng'
                  f' · {63 - len(co) - len(trong)} tỉnh không có dòng nào')

        # ---- Kết luận: chặng nào đứt ----
        print('\nCHẶNG ĐỨT:')
        so_done = tong.get('DONE_LOCAL', 0)
        so_khop = sum(tong.values())
        co_bang = len(bang[0]) if bang else 0
        if not so_khop:
            print('   Không job nào của mốc này có trong state.json. Luồng tải chưa từng')
            print('   chạy tới đây trên máy này, hoặc state nằm ở máy khác.')
        elif so_done < so_khop:
            hong = {k: v for k, v in tong.items() if k != 'DONE_LOCAL'}
            print(f'   {so_khop - so_done}/{so_khop} job KHÔNG ở trạng thái DONE_LOCAL: '
                  + ', '.join(f'{k or "(trống)"}={v}' for k, v in sorted(hong.items(), key=lambda x: str(x[0]))))
            print('   => Đứt ở khâu TẢI. Chạy lại luồng tải cho mốc này; các job DONE_LOCAL')
            print('      sẽ được bỏ qua, chỉ tải phần còn thiếu.')
        elif so_bn < so_done:
            print(f'   {so_done} job DONE_LOCAL nhưng chỉ {so_bn} biên nhận.')
            print('   => Đứt giữa TẢI và GHI NHẬN: trạng thái nói xong mà biên nhận mất.')
        elif tep is not None and len(tep) < so_bn:
            print(f'   {so_bn} biên nhận nhưng chỉ {len(tep)} tệp trên đĩa.')
            print('   => Tệp đã bị xoá hoặc chưa chuyển về ổ này.')
        elif co_bang < so_done:
            print(f'   Đủ {so_done} tệp nhưng bảng chỉ có {co_bang} tỉnh có số.')
            print('   => Đứt ở khâu TÍNH. Chạy lại derive (local.py --only night) cho mốc này.')
        else:
            print('   Bốn chặng khớp nhau. Nếu bảng vẫn thiếu thì nguyên nhân nằm ngoài')
            print('   phạm vi script này.')


if __name__ == '__main__':
    main()
