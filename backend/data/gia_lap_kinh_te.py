r"""Sinh số liệu kinh tế GIẢ LẬP để chạy thử màn "Chỉ số kinh tế đêm".

LÝ DO TỒN TẠI: cô chưa gửi dân số và GRDP, nên bảng `economy` rỗng và màn thứ ba
không có gì để vẽ. Script này dựng một bộ số có hình dạng đúng để kiểm thử đường
ống đầu-cuối: nạp CSV -> build_indices -> /api/kinh-te-dem -> bảng + hệ số beta.

CẢNH BÁO: MỌI CON SỐ NÓ SINH RA ĐỀU KHÔNG THẬT.
GRDP được dựng từ chính `sol` theo công thức grdp = exp(ALPHA) * sol^BETA * nhiễu,
nên hệ số beta mà app ước lượng chỉ là con số đã cấy vào đây — nó chứng minh phép
hồi quy chạy đúng, KHÔNG nói gì về quan hệ ánh sáng–GRDP của Việt Nam. Dân số cũng
là số bịa. Cột `source` ghi GIA_LAP ở mọi dòng để API tự gắn cảnh báo lên giao diện,
không thể lỡ tay trích vào báo cáo mà không thấy.

Khi có số thật: xoá tệp này sinh ra, điền backend/data/economy_mau.csv rồi đổi tên thành
data_processed/economy.csv và chạy lại build_indices.

    python scripts\gia_lap_kinh_te.py --root E:\SatelliteData
    python scripts\gia_lap_kinh_te.py --root E:\SatelliteData --beta 0.6
    python -m backend.data.build_indices --root E:\SatelliteData
"""
import argparse
import csv
import math
import random
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
# Cùng bố cục với backend/data/build_indices.py: bảng chỉ số đêm nằm trong gói dữ liệu
# dưới gốc ổ dữ liệu (E:\SatelliteData hoặc /data/SatelliteData), không nằm trong repo.
GOI_NTL = 'VN_NTL_Panel_2004_2025'
ROOT_MAC_DINH = Path('/data/SatelliteData')
# economy.csv thì ngược lại: build_indices đọc nó theo đường dẫn tương đối trong repo.
DICH_MAC_DINH = GOC / 'data_processed' / 'economy.csv'

NHAN_GIA_LAP = 'GIA_LAP'          # backend/api/store.py dò chuỗi này để gắn cảnh báo
BETA_MAC_DINH = 0.45              # độ co giãn cấy vào; app phải ước lượng ra xấp xỉ số này
ALPHA_MAC_DINH = 9.0              # hằng số, chỉ để GRDP rơi vào khoảng tỷ đồng dễ đọc
NHIEU_MAC_DINH = 0.22             # độ lệch chuẩn của nhiễu log; 0 thì R² = 1, không thật
DAN_SO_CA_NUOC_2014 = 90_700_000  # chia theo tỷ trọng sáng, KHÔNG phải dân số thật
TANG_DAN_SO = 0.0105              # 1,05 %/năm


def doc_sol(nguon, nam_tu, nam_den):
    """Lấy sol theo tỉnh-năm từ bảng chỉ số đêm đã tính. Chỉ dòng theo năm, sol dương."""
    theo_tinh = {}
    with open(nguon, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            try:
                nam, sol = int(row['year']), float(row['sol'] or 0)
            except (KeyError, TypeError, ValueError):
                continue
            if not (nam_tu <= nam <= nam_den) or sol <= 0:
                continue
            if str(row.get('month') or 0) not in ('0', '0.0'):
                continue
            theo_tinh.setdefault(row['province_code'].zfill(2), {})[nam] = sol
    return theo_tinh


def sinh(theo_tinh, beta, alpha, nhieu, seed=20261116):
    """Dựng dân số và GRDP từ sol. Mọi ngẫu nhiên đều có seed để chạy lại ra y hệt."""
    rng = random.Random(seed)
    nam_goc = min(min(v) for v in theo_tinh.values())
    sol_goc = {ma: v.get(nam_goc) or next(iter(sorted(v.items())))[1]
               for ma, v in theo_tinh.items()}
    tong_goc = sum(sol_goc.values())
    # Dân số: chia theo tỷ trọng sáng đã làm phẳng (mũ 0,55) để tỉnh tối không về 0 dân,
    # cộng sàn 400 nghìn. Vẫn là số bịa, chỉ cốt có bậc độ lớn hợp lý.
    dan_goc = {ma: 400_000 + DAN_SO_CA_NUOC_2014 * (s ** 0.55)
               / sum(x ** 0.55 for x in sol_goc.values()) for ma, s in sol_goc.items()}
    ra = []
    for ma in sorted(theo_tinh):
        lech = rng.gauss(0, nhieu)          # mức riêng của tỉnh, giữ nguyên qua các năm
        for nam in sorted(theo_tinh[ma]):
            sol = theo_tinh[ma][nam]
            dan = dan_goc[ma] * (1 + TANG_DAN_SO) ** (nam - nam_goc)
            log_grdp = alpha + beta * math.log(sol) + lech + rng.gauss(0, nhieu / 2)
            ra.append({'province_code': ma, 'year': nam,
                       'population': round(dan),
                       'grdp': round(math.exp(log_grdp), 1),
                       'grdp_price_basis': 'so_sanh',
                       'source': f'{NHAN_GIA_LAP} beta={beta} seed={seed}'})
    return ra


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', type=Path, default=ROOT_MAC_DINH,
                   help='Gốc ổ dữ liệu, ví dụ E:\\SatelliteData')
    p.add_argument('--nguon', type=Path, default=None,
                   help='Đường dẫn thẳng tới ntl_annual.csv, bỏ qua --root')
    p.add_argument('--ra', type=Path, default=DICH_MAC_DINH)
    p.add_argument('--tu', type=int, default=2014)
    p.add_argument('--den', type=int, default=2025)
    p.add_argument('--beta', type=float, default=BETA_MAC_DINH)
    p.add_argument('--alpha', type=float, default=ALPHA_MAC_DINH)
    p.add_argument('--nhieu', type=float, default=NHIEU_MAC_DINH)
    p.add_argument('--seed', type=int, default=20261116)
    a = p.parse_args()

    if a.nguon is None:
        a.nguon = a.root / GOI_NTL / 'data_processed' / 'ntl_annual.csv'
    if not a.nguon.is_file():
        raise SystemExit(f'Chưa có {a.nguon}. Chạy chuỗi chỉ số đêm trước '
                         '(chi_so_dem.ps1 hoặc task_pipeline.derive.merge).')
    theo_tinh = doc_sol(a.nguon, a.tu, a.den)
    if not theo_tinh:
        raise SystemExit(f'Không có dòng theo năm nào trong {a.tu}–{a.den} ở {a.nguon}.')
    dong = sinh(theo_tinh, a.beta, a.alpha, a.nhieu, a.seed)
    a.ra.parent.mkdir(parents=True, exist_ok=True)
    with open(a.ra, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['province_code', 'year', 'population', 'grdp',
                                          'grdp_price_basis', 'source'])
        w.writeheader()
        w.writerows(dong)
    nam = sorted({d['year'] for d in dong})
    print(f'Đã ghi {a.ra}: {len(dong)} dòng, {len(theo_tinh)} tỉnh, '
          f'{nam[0]}–{nam[-1]}.')
    print(f'SỐ LIỆU GIẢ LẬP — beta cấy vào = {a.beta}. App phải ước lượng ra xấp xỉ '
          'con số này; đó là phép kiểm thử, không phải kết quả nghiên cứu.')
    print('Nạp vào app:  python -m backend.data.build_indices')


if __name__ == '__main__':
    raise SystemExit('Đã tắt sinh dữ liệu giả lập. Chỉ nạp dữ liệu thật. Dùng backend.data.purge_simulated để xóa dữ liệu giả cũ.')
