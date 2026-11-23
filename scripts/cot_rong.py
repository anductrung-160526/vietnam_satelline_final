r"""Quét cơ sở dữ liệu: cột nào rỗng hoàn toàn, bảng nào không có dòng nào.

Một cột tồn tại nhưng toàn NULL trông giống hệt một cột tính đúng mà giá trị bằng
trống: trên giao diện cả hai đều là dấu gạch. Khác nhau ở chỗ cột toàn NULL nghĩa
là có một khâu nào đó chưa chạy, còn ô trống lẻ tẻ là chuyện bình thường của dữ liệu
vệ tinh. Script tách hai thứ đó bằng con số.

Ba mức, xếp theo độ nghiêm trọng:

  BẢNG RỖNG    không có dòng nào -> khâu nạp chưa chạy
  CỘT TOÀN NULL có dòng nhưng cột không một giá trị -> khâu tính cột đó chưa chạy
  CỘT THƯA     dưới ngưỡng --nguong phần trăm có giá trị -> đáng nhìn lại

Cột khoá và cột chú thích (note, status...) rỗng là chuyện thường, nên script có
ghi rõ cột nào thuộc loại mong đợi rỗng thay vì báo động đều.

    python scripts/cot_rong.py
    python scripts/cot_rong.py --db backend/data/vngis.db --nguong 20
    python scripts/cot_rong.py --tat-ca        # in cả cột đầy đủ
"""
import argparse
import sqlite3
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

# Rỗng ở đây là trạng thái hợp lệ, không phải dấu hiệu hỏng.
MONG_DOI_RONG = {
    'note': 'chỉ điền tại năm đổi nguồn ảnh, mọi dòng khác rỗng là đúng',
    'calibration': 'rỗng khi chưa chạy bước hiệu chỉnh DMSP→VIIRS',
    'sol_cal': 'rỗng khi chưa chạy bước hiệu chỉnh DMSP→VIIRS',
    'gdp_per_capita': 'chỉ có khi nguồn kinh tế cung cấp sẵn',
    'gid_1': 'chỉ có khi danh mục tỉnh mang mã GADM',
}


def quet(cur, bang):
    cot = [r[1] for r in cur.execute(f'PRAGMA table_info("{bang}")')]
    tong = cur.execute(f'SELECT COUNT(*) FROM "{bang}"').fetchone()[0]
    if not tong:
        return tong, []
    # Một lượt quét cho cả bảng: COUNT(cột) bỏ qua NULL nên đếm được ngay.
    bieu_thuc = ', '.join(f'COUNT("{c}")' for c in cot)
    so = cur.execute(f'SELECT {bieu_thuc} FROM "{bang}"').fetchone()
    return tong, list(zip(cot, so))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--db', type=Path, default=GOC / 'backend' / 'data' / 'vngis.db')
    p.add_argument('--nguong', type=float, default=20.0,
                   help='Dưới bao nhiêu %% có giá trị thì coi là thưa (mặc định 20)')
    p.add_argument('--tat-ca', action='store_true', dest='tat_ca')
    a = p.parse_args()

    if not a.db.exists():
        raise SystemExit(f'Không thấy {a.db}')
    cn = sqlite3.connect(a.db)
    cur = cn.cursor()
    bang = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    print(f'{a.db}\n{len(bang)} bảng\n')

    rong, null_het, thua = [], [], []
    for b in bang:
        tong, cot = quet(cur, b)
        if not tong:
            rong.append(b)
            print(f'{b:<28}BẢNG RỖNG')
            continue
        xau = [(c, n) for c, n in cot if n == 0]
        it = [(c, n) for c, n in cot if 0 < n < tong * a.nguong / 100]
        print(f'{b:<28}{tong:>8,} dòng · {len(cot)} cột · '
              f'{len(xau)} toàn NULL · {len(it)} thưa')
        for c, _ in xau:
            null_het.append((b, c))
        for c, n in it:
            thua.append((b, c, n, tong))
        if a.tat_ca:
            for c, n in cot:
                print(f'    {c:<30}{n:>8,}/{tong:,}')

    print('\n' + '=' * 70)
    if null_het:
        print(f'\nCỘT TOÀN NULL ({len(null_het)}):')
        for b, c in null_het:
            vi_sao = MONG_DOI_RONG.get(c)
            print(f'  {b}.{c}' + (f'   [mong đợi: {vi_sao}]' if vi_sao else ''))
        la = [x for x in null_het if x[1] not in MONG_DOI_RONG]
        if la:
            print(f'\n  >>> {len(la)} cột KHÔNG nằm trong danh sách mong đợi rỗng.')
            print('      Đây là chỗ cần truy: khâu tính cột đó chưa chạy, hoặc tên cột')
            print('      trong CSV lệch tên cột trong bảng nên nạp vào rỗng.')
    else:
        print('\nKhông có cột nào toàn NULL.')
    if rong:
        print(f'\nBẢNG RỖNG ({len(rong)}): ' + ', '.join(rong))
    if thua:
        print(f'\nCỘT THƯA (dưới {a.nguong:.0f}% có giá trị) ({len(thua)}):')
        for b, c, n, tong in thua:
            print(f'  {b}.{c:<28}{n:,}/{tong:,} = {100*n/tong:.1f}%')
    cn.close()
    return 1 if [x for x in null_het if x[1] not in MONG_DOI_RONG] or rong else 0


if __name__ == '__main__':
    sys.exit(main())
