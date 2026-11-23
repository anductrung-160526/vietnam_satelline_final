r"""Liệt kê trường trong Night Data Dictionary, lọc theo bảng hoặc nhóm.

Cố ý KHÔNG sinh ra một tệp tài liệu thứ hai: bản chép sẽ lệch khỏi từ điển ngay lần
sửa sau mà không ai biết. Cần danh sách thì chạy lại lệnh này.

    python scripts/liet_ke_truong.py                       # cả hai bảng, gom theo nhóm
    python scripts/liet_ke_truong.py --bang "Night Data"
    python scripts/liet_ke_truong.py --bang "Night Data" --cot field unit note
    python scripts/liet_ke_truong.py --nhom Moran --day-du
    python scripts/liet_ke_truong.py --bang "Night Data" --csv > night_data.csv
"""
import argparse
import csv
import importlib.util
import sys
from collections import OrderedDict
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent


def nap_tu_dien():
    """Dùng lại bộ đọc của doi_chieu_tu_dien.py, không viết bộ đọc thứ hai."""
    spec = importlib.util.spec_from_file_location(
        'doi_chieu', GOC / 'scripts' / 'doi_chieu_tu_dien.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.doc_tu_dien()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--bang', default=None, help='"Night Data" hoặc "Night Economy"')
    p.add_argument('--nhom', default=None, help='Lọc theo nhóm, khớp một phần, không phân biệt hoa thường')
    p.add_argument('--cot', nargs='*', default=None,
                   help='Cột muốn in: field group description formula unit frequency storage note')
    p.add_argument('--day-du', action='store_true', dest='day_du',
                   help='In cả công thức và nơi lưu, không cắt ngắn mô tả')
    p.add_argument('--csv', action='store_true', help='Xuất CSV ra màn hình')
    a = p.parse_args()

    td = nap_tu_dien()
    hang = [h for h in td.values()
            if (not a.bang or h['table'] == a.bang)
            and (not a.nhom or a.nhom.lower() in h['group'].lower())]
    if not hang:
        raise SystemExit('Không có trường nào khớp bộ lọc.')

    if a.csv:
        cot = a.cot or list(hang[0].keys())
        w = csv.DictWriter(sys.stdout, fieldnames=cot, extrasaction='ignore')
        w.writeheader()
        w.writerows(hang)
        return

    nhom = OrderedDict()
    for h in hang:
        nhom.setdefault((h['table'], h['group']), []).append(h)

    print(f'{len(hang)} trường · {len(nhom)} nhóm'
          + (f' · bảng {a.bang}' if a.bang else '')
          + (f' · nhóm khớp "{a.nhom}"' if a.nhom else ''))
    for (bang, ten_nhom), ds in nhom.items():
        print(f'\n## {bang} — {ten_nhom}  ({len(ds)})')
        for h in ds:
            raw = 'Raw' if h['note'] == 'Raw' else 'Proc'
            don_vi = h['unit'] if h['unit'] not in ('', '—') else ''
            print(f'  {h["field"]:<28}{raw:<6}{don_vi}')
            if a.day_du:
                print(f'      {h["description"]}')
                print(f'      công thức: {h["formula"]}')
                print(f'      lưu ở    : {h["storage"]}')
            else:
                mo_ta = h['description']
                print(f'      {mo_ta[:150]}{"…" if len(mo_ta) > 150 else ""}')


if __name__ == '__main__':
    main()
