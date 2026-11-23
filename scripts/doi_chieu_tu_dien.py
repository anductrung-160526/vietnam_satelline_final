r"""Đối chiếu bốn tầng của hai màn chỉ số đêm, lấy Night Data Dictionary làm chuẩn.

Một con số hiện trên màn hình đi qua bốn tầng. Lệch ở bất kỳ tầng nào cũng cho ra ô
trống hoặc số sai mà KHÔNG có gì báo lỗi:

  1. TỪ ĐIỂN   docs/NIGHT_DATA_DICTIONARY.md — chuẩn tham chiếu
  2. TÍNH      backend/data/calculate_ntl.py — trường nào CSV chuẩn thật sự ghi ra
  3. KHO       cột thật trong SQLite, và cột đó có số hay rỗng
  4. HIỂN THỊ  trường mà API THẬT SỰ trả về cho từng màn

Tầng 4 hỏi thẳng API đang chạy chứ không đọc mã. Lý do: màn Kinh tế đêm đã chuyển
sang /api/demo/economy, trong khi store.kinh_te_dem vẫn còn trong mã nguồn và không
ai gọi — đọc mã thì đối chiếu nhầm đúng cái nhánh chết đó.

    python -m uvicorn backend.api.main:app --port 8000     # cửa sổ khác
    python scripts/doi_chieu_tu_dien.py
    python scripts/doi_chieu_tu_dien.py --url http://localhost:8000 --nam 2024
"""
import argparse
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))
TU_DIEN = GOC / 'docs' / 'NIGHT_DATA_DICTIONARY.md'
COT = ('table', 'group', 'field', 'task3_field_lowercase', 'description',
       'formula', 'unit', 'frequency', 'storage', 'note')


def doc_tu_dien(path=TU_DIEN):
    """Bảng markdown một hàng một trường -> {tên trường: hàng}."""
    ra = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.startswith('|'):
            continue
        o = [c.strip() for c in line.strip('|').split('|')]
        if len(o) < len(COT) or o[2] in ('field', '---'):
            continue
        ten = o[2].strip('`')
        if ten and ten != '—':
            ra[ten] = dict(zip(COT, o))
    return ra


def tra_ten(tu_dien, ten):
    """(trạng thái, trường gốc) của một tên đang hiển thị. Bốn kết cục khác hẳn nhau:

      'chuan'   tên trường có thật trong từ điển
      'bi_danh' từ điển khai nó là tên khác của một trường (province_name ~ name_1)
      'cam'     từ điển nhắc tên này ĐỂ CẤM ("không thêm field ... vào dictionary")
      None      từ điển không biết tên này

    Gộp bốn cái này lại là mất hết thông tin: 'cam' nặng hơn None nhiều.
    """
    if ten in tu_dien:
        return 'chuan', ten
    for ten_truong, hang in tu_dien.items():
        for cot in ('description', 'storage', 'formula', 'task3_field_lowercase'):
            van = hang.get(cot, '')
            # Khớp trọn từ: 'grdp' nằm trong 'grdp_so_sanh' không phải là bí danh.
            if not re.search(r'(?<![A-Za-z0-9_])' + re.escape(ten) + r'(?![A-Za-z0-9_])', van):
                continue
            if re.search(r'không (thêm|dùng|đưa)[^.;]*' + re.escape(ten), van):
                return 'cam', ten_truong
            return 'bi_danh', ten_truong
    return None, None


def lay(url):
    with urllib.request.urlopen(url, timeout=180) as r:
        return json.loads(r.read().decode('utf-8'))


def kho(cur, ten, cac_bang):
    """(bảng, tổng dòng, số dòng có giá trị) của cột này, tìm trong các bảng cho trước."""
    for b in cac_bang:
        try:
            cot = [r[1] for r in cur.execute(f'PRAGMA table_info({b})')]
        except sqlite3.Error:
            continue
        if ten not in cot:
            continue
        tong = cur.execute(f'SELECT COUNT(*) FROM {b}').fetchone()[0]
        co = cur.execute(f'SELECT COUNT("{ten}") FROM {b}').fetchone()[0]
        return b, tong, co
    return None, None, None


def mo_ta_kho(bang, tong, co):
    if bang is None:
        return 'không có cột trong DB'
    if not tong:
        return f'{bang}: bảng rỗng'
    if co == 0:
        return f'{bang}: TOÀN NULL ({tong} dòng)'
    if co < tong:
        return f'{bang}: {co}/{tong} dòng có số'
    return f'{bang}: đủ {tong} dòng'


def soi(ten, tu_dien, tinh_duoc, cur, cac_bang, loi, man):
    tt, goc = tra_ten(tu_dien, ten)
    nhan = {'chuan': 'TĐ  ', 'bi_danh': 'TĐ~ ', 'cam': 'CẤM ', None: '--  '}[tt]
    bang, tong, co = kho(cur, ten, cac_bang) if cur else (None, None, None)
    them = ''
    if tt == 'bi_danh':
        them = f'   [từ điển gọi là {goc}]'
    elif tt == 'cam':
        them = '   [từ điển CẤM thêm trường này]'
        loi.append((man, ten, f'từ điển ghi rõ không thêm field {ten}'))
    elif tt is None:
        loi.append((man, ten, 'không có trong từ điển'))
    if bang and tong and co == 0:
        loi.append((man, ten, f'có cột nhưng toàn NULL trong {bang}'))
    print(f'  {ten:<26}{nhan}{"TÍNH" if ten in tinh_duoc else "----":<6}'
          f'{mo_ta_kho(bang, tong, co)}{them}')


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--url', default='http://localhost:8000')
    p.add_argument('--db', type=Path, default=GOC / 'backend' / 'data' / 'vngis.db')
    p.add_argument('--nam', type=int, default=2024)
    a = p.parse_args()

    tu_dien = doc_tu_dien()
    from backend.data.calculate_ntl import NIGHT_DATA_FIELDS, NIGHT_ECONOMY_FIELDS
    from backend.api.demo_view import FIELD_ALIASES
    nguoc = {v: k for k, v in FIELD_ALIASES.items()}
    tinh_duoc = set(NIGHT_DATA_FIELDS) | set(NIGHT_ECONOMY_FIELDS)
    tinh_duoc |= {nguoc[f] for f in tinh_duoc if f in nguoc}

    cn = sqlite3.connect(a.db) if a.db.exists() else None
    cur = cn.cursor() if cn else None
    bang_dem = ['ntl_annual', 'ntl_monthly', 'demo_result', 'light_class_summary']
    bang_kt = ['economy_prices', 'economy', 'demo_result']

    print(f'Từ điển      : {len(tu_dien)} trường · {TU_DIEN.relative_to(GOC)}')
    print(f'calculate_ntl: {len(NIGHT_DATA_FIELDS)} night_data + '
          f'{len(NIGHT_ECONOMY_FIELDS)} night_economy')
    print(f'Cơ sở dữ liệu: {a.db}' + ('' if a.db.exists() else '  (CHƯA CÓ)'))
    print(f'API          : {a.url}')
    print('\nCỘT: tên · TĐ=trường trong từ điển, TĐ~=bí danh, CẤM=từ điển cấm, --=không biết'
          '\n     · TÍNH=calculate_ntl ghi ra · kho dữ liệu')
    loi = []

    try:
        chi_so = lay(f'{a.url}/api/indicators')['chi_so']
        print(f'\n=== MÀN "CHỈ SỐ ĐÊM" · khung Bảng · /api/indicators — {len(chi_so)} chỉ số ===')
        for c in chi_so:
            soi(c['ma'], tu_dien, tinh_duoc, cur, bang_dem + bang_kt, loi, 'Chỉ số đêm · Bảng')

        d = lay(f'{a.url}/api/demo/data?nam={a.nam}&thang=0')
        cols = d.get('columns', [])
        print(f'\n=== MÀN "CHỈ SỐ ĐÊM" · khung Chi tiết · /api/demo/data — {len(cols)} cột ===')
        for c in cols:
            soi(c['field'], tu_dien, tinh_duoc, cur, bang_dem + bang_kt, loi,
                'Chỉ số đêm · Chi tiết')

        e = lay(f'{a.url}/api/demo/economy?nam={a.nam}')
        truong = sorted((e.get('dong') or [{}])[0].keys())
        print(f'\n=== MÀN "CHỈ SỐ KINH TẾ ĐÊM" · /api/demo/economy — {len(truong)} trường ===')
        for t in truong:
            soi(t, tu_dien, tinh_duoc, cur, bang_kt + bang_dem, loi, 'Kinh tế đêm')
        hq = (e.get('hoi_quy') or {}).get('so_sanh') or {}
        if hq:
            print('  -- ô hồi quy --')
            for t in sorted(hq):
                soi(t, tu_dien, tinh_duoc, cur, bang_kt, loi, 'Kinh tế đêm · hồi quy')
    except (urllib.error.URLError, OSError) as err:
        print(f'\nKHÔNG GỌI ĐƯỢC API ({err}). Chạy uvicorn trước:')
        print('  python -m uvicorn backend.api.main:app --port 8000')
        return 2

    print('\n' + '=' * 72)
    if not loi:
        print('\nKhông thấy lệch nào giữa bốn tầng.')
    else:
        print(f'\n{len(loi)} ĐIỂM LỆCH:')
        for man, ten, vi_sao in loi:
            print(f'  · [{man}] {ten}: {vi_sao}')
    if cn:
        cn.close()
    return 1 if loi else 0


if __name__ == '__main__':
    sys.exit(main())
