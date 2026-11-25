r"""So ba cách chọn hai mốc trên của phân lớp sáng, trên chính dữ liệu của dự án.

CHỈ ĐỌC. Không ghi cơ sở dữ liệu, không tạo ảnh, không đụng mã đang chạy.
Mục đích: nhìn số rồi quyết, thay vì chọn theo tên thuật toán.

Ba cách so sánh, đều chỉ thay hai mốc TRÊN:

  phan_vi   P50/P90 của pixel sáng — cách đang dùng
  kmeans    k-means (Lloyd) k=3 trên log(bức xạ) của pixel sáng
  jenks     Fisher-Jenks k=3 trên log(bức xạ), giải bằng quy hoạch động

Hai mốc DƯỚI giữ nguyên 0,5 và 1,5 ở cả ba cách. Đây là chủ ý, không phải lười:
0,5 là ngưỡng nền và 1,5 là ngưỡng sáng, cả hai có căn cứ riêng và quyết định
`sol`, `lit_pixels`, `lit_area_km2`. Thả cho thuật toán tự chọn cả bốn mốc thì
`backend/data/spatial_analysis.py:108` âm thầm sai: chỗ đó dựa vào việc breaks[1]
đúng bằng ngưỡng sáng để suy "lớp >= 2 tức là pixel sáng".

Vì sao log: bức xạ đêm đuôi rất nặng (một tỉnh có rad_max gấp hàng chục lần
rad_mean). k-means và Jenks đều tối thiểu BÌNH PHƯƠNG sai lệch nên trên thang
tuyến tính sẽ bị vài pixel cực sáng kéo hết mốc về phía sáng.

    python scripts\so_sanh_nguong_phan_lop.py --db backend\data\vngis.db
    python scripts\so_sanh_nguong_phan_lop.py --nam 2020 --tinh 01 79 06 --bin 512
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import rasterio

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

NGUONG_NEN = 0.5
NGUONG_SANG = 1.5
TEN_LOP = ['Tối / dưới ngưỡng nền', 'Sáng yếu', 'Sáng vừa', 'Sáng mạnh', 'Rất sáng']


def anh_nam_tham_chieu(db, nam):
    """Ảnh VIIRS theo năm của từng tỉnh, lấy đúng bảng mà build_light_classes dùng."""
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(r) for r in connection.execute(
            "SELECT province_code,path FROM demo_asset "
            "WHERE kind='processed' AND source='VIIRS' AND year=? AND month=0 "
            "ORDER BY province_code", (nam,))]


def doc_pixel_sang(anh):
    """Gom bức xạ của mọi pixel sáng, đúng cách choose_thresholds đang làm."""
    from backend.data.calculate_ntl import windows
    phan = []
    for item in anh:
        with rasterio.open(item['path']) as image:
            if image.scales[0] != 1 or image.offsets[0] != 0:
                raise SystemExit(f"Ảnh chưa chuẩn hoá scale/offset: {item['path']}")
            for window in windows(image.height, image.width):
                data = image.read(1, window=window).astype(float)
                valid = (image.read_masks(1, window=window).astype(bool)
                         & np.isfinite(data) & (data != -9999))
                values = data[valid & (data >= NGUONG_SANG)]
                if values.size:
                    phan.append(values.astype('float32'))
    if not phan:
        raise SystemExit('Không có pixel sáng nào ở năm tham chiếu.')
    return np.concatenate(phan)


def hist_log(bright, so_bin):
    x = np.log(bright)
    dem, canh = np.histogram(x, bins=so_bin)
    tam = (canh[:-1] + canh[1:]) / 2
    giu = dem > 0
    return tam[giu], dem[giu].astype('float64')


def sse_theo_ranh(tam, dem, ranh):
    """Tổng bình phương sai lệch trong nhóm — hàm mục tiêu CHUNG của k-means và Jenks.

    Có con số này thì không phải tranh luận bộ nào "đẹp hơn": cả hai cùng tối thiểu
    đại lượng này, bộ nào thấp hơn là bộ ấy giải tốt hơn.
    """
    nhom = np.digitize(tam, ranh, right=False)
    tong = 0.0
    for j in range(len(ranh) + 1):
        o = nhom == j
        if not np.any(o):
            continue
        tb = np.average(tam[o], weights=dem[o])
        tong += float(np.sum(dem[o] * (tam[o] - tb) ** 2))
    return tong


def _lloyd(tam, dem, tam_cum, vong=300):
    tam_cum = np.sort(np.asarray(tam_cum, dtype='float64'))
    for _ in range(vong):
        gan = np.argmin(np.abs(tam[:, None] - tam_cum[None, :]), axis=1)
        moi = np.array([np.average(tam[gan == j], weights=dem[gan == j])
                        if np.any(gan == j) else tam_cum[j] for j in range(len(tam_cum))])
        moi = np.sort(moi)
        if np.allclose(moi, tam_cum):
            break
        tam_cum = moi
    return tam_cum


def kmeans_1d(tam, dem, k, vong=300):
    """Lloyd có trọng số, chạy từ nhiều khởi tạo tất định rồi giữ bộ có SSE thấp nhất.

    Một khởi tạo duy nhất theo phân vị cho kết quả SAI khi các cụm chênh lệch nhiều
    về số pixel: cả ba tâm bị hút vào vùng đông, bỏ sót cụm sáng. Đã kiểm trên bộ
    dữ liệu dựng sẵn ba cụm — khởi tạo phân vị ra 3,0/12,7 trong khi đáp án là
    9,6/94. Chạy nhiều khởi tạo là cách k-means thật sự được dùng (n_init của
    scikit-learn), không phải mẹo riêng.

    Vẫn tất định: mọi khởi tạo đều suy từ dữ liệu, không có số ngẫu nhiên.
    """
    tich = np.cumsum(dem)
    khoi_tao = [
        # theo phân vị của trọng số
        [tam[np.searchsorted(tich, tich[-1] * q)] for q in np.linspace(0, 1, k + 2)[1:-1]],
        # chia đều trên khoảng giá trị
        list(np.linspace(tam[0], tam[-1], k + 2)[1:-1]),
        # kiểu k-means++ nhưng chọn tất định: điểm xa các tâm đã có nhất
        None,
    ]
    xa = [float(np.average(tam, weights=dem))]
    for _ in range(k - 1):
        d = np.min(np.abs(tam[:, None] - np.array(xa)[None, :]), axis=1) ** 2 * dem
        xa.append(float(tam[int(np.argmax(d))]))
    khoi_tao[2] = xa

    tot_nhat, sse_tot = None, np.inf
    for kt in khoi_tao:
        tam_cum = _lloyd(tam, dem, kt, vong)
        ranh = [(tam_cum[j] + tam_cum[j + 1]) / 2 for j in range(k - 1)]
        gia = sse_theo_ranh(tam, dem, ranh)
        if gia < sse_tot:
            tot_nhat, sse_tot = ranh, gia
    return tot_nhat


def jenks_1d(tam, dem, k):
    """Fisher-Jenks bằng quy hoạch động trên bin: tối ưu TOÀN CỤC, khác k-means.

    Chi phí O(n²k) nên chạy trên bin chứ không trên từng pixel; n là số bin.
    """
    n = len(tam)
    w = np.concatenate([[0], np.cumsum(dem)])
    s = np.concatenate([[0], np.cumsum(dem * tam)])
    s2 = np.concatenate([[0], np.cumsum(dem * tam * tam)])

    def sse(i, j):                      # sai lệch bình phương của bin i..j-1
        n_ = w[j] - w[i]
        if n_ <= 0:
            return 0.0
        return float(s2[j] - s2[i] - (s[j] - s[i]) ** 2 / n_)

    chi_phi = np.full((k + 1, n + 1), np.inf)
    cat = np.zeros((k + 1, n + 1), dtype=int)
    chi_phi[0, 0] = 0.0
    for lop in range(1, k + 1):
        for j in range(lop, n + 1):
            for i in range(lop - 1, j):
                gia = chi_phi[lop - 1, i] + sse(i, j)
                if gia < chi_phi[lop, j]:
                    chi_phi[lop, j] = gia
                    cat[lop, j] = i
    ranh, j = [], n
    for lop in range(k, 1, -1):
        i = cat[lop, j]
        ranh.append((tam[i - 1] + tam[i]) / 2)
        j = i
    return sorted(ranh)


def bo_moc(ten, tren):
    return ten, [NGUONG_NEN, NGUONG_SANG, float(tren[0]), float(tren[1])]


def dien_tich_lop(path, breaks):
    """Tỷ lệ pixel từng lớp trên tổng pixel hợp lệ của tỉnh.

    Dùng tỷ lệ pixel chứ không phải km²: ba bộ ngưỡng chạy trên CÙNG tập pixel nên
    tỷ lệ đủ để so sánh, và không phải nạp mô hình diện tích giao biên.
    """
    from backend.data.calculate_ntl import windows
    dem = np.zeros(5)
    with rasterio.open(path) as image:
        for window in windows(image.height, image.width):
            data = image.read(1, window=window).astype(float)
            valid = (image.read_masks(1, window=window).astype(bool)
                     & np.isfinite(data) & (data != -9999))
            v = data[valid]
            if v.size:
                np.add.at(dem, np.digitize(v, breaks, right=False), 1)
    return dem


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--db', type=Path, default=GOC / 'backend' / 'data' / 'vngis.db')
    p.add_argument('--nam', type=int, default=2020, help='Năm tham chiếu để khớp ngưỡng')
    p.add_argument('--bin', type=int, default=512, dest='so_bin',
                   help='Số bin trên thang log cho k-means và Jenks')
    p.add_argument('--tinh', nargs='*', default=['01', '79', '06'],
                   help='Mã tỉnh để in bảng diện tích so sánh')
    a = p.parse_args()

    if not a.db.exists():
        raise SystemExit(f'Không thấy {a.db}')
    anh = anh_nam_tham_chieu(a.db, a.nam)
    if not anh:
        raise SystemExit(f'Không có ảnh VIIRS năm {a.nam} trong bảng demo_asset. '
                         'Chạy bộ chuẩn bị demo trước.')
    print(f'Năm tham chiếu {a.nam} · {len(anh)} ảnh tỉnh')
    if len(anh) != 63:
        print(f'  CẢNH BÁO: chỉ có {len(anh)}/63 tỉnh. Ngưỡng khớp trên mẫu thiếu '
              'KHÔNG dùng để chốt được, chỉ để xem thử.')

    bright = doc_pixel_sang(anh)
    print(f'{bright.size:,} pixel sáng (>= {NGUONG_SANG}) · '
          f'nhỏ nhất {bright.min():.2f} · lớn nhất {bright.max():.2f}')

    q50, q90 = np.quantile(bright, [.5, .9], method='linear')
    tam, dem = hist_log(bright, a.so_bin)
    km = np.exp(kmeans_1d(tam, dem, 3))
    jk = np.exp(jenks_1d(tam, dem, 3))

    cac_bo = [bo_moc('phan_vi (đang dùng)', [q50, q90]),
              bo_moc('kmeans log', km),
              bo_moc('jenks log', jk)]

    print('\n=== BỐN MỐC ===')
    print('  SSE = tổng bình phương sai lệch trong nhóm trên thang log, tính trên hai')
    print('  mốc trên. Cùng một hàm mục tiêu cho cả ba cách, THẤP HƠN LÀ CHIA TỐT HƠN.')
    print(f'  {"cách":<22}{"mốc 1":>8}{"mốc 2":>8}{"mốc 3":>10}{"mốc 4":>10}{"SSE":>14}')
    for ten, b in cac_bo:
        gia = sse_theo_ranh(tam, dem, [np.log(b[2]), np.log(b[3])])
        print(f'  {ten:<22}{b[0]:>8.2f}{b[1]:>8.2f}{b[2]:>10.2f}{b[3]:>10.2f}{gia:>14,.0f}')
        if not all(x < y for x, y in zip(b, b[1:])):
            print('     >>> KHÔNG TĂNG DẦN: bộ này không dùng được.')

    ten_tinh = {r['province_code']: r['path'] for r in anh}
    for ma in [t.zfill(2) for t in a.tinh]:
        if ma not in ten_tinh:
            print(f'\n{ma}: không có ảnh năm {a.nam}')
            continue
        print(f'\n=== TỈNH {ma} · tỷ lệ pixel từng lớp (%) ===')
        print(f'  {"lớp":<26}' + ''.join(f'{t:>14}' for t, _ in cac_bo))
        bang = [dien_tich_lop(ten_tinh[ma], b) for _, b in cac_bo]
        tong = [max(1.0, x.sum()) for x in bang]
        for i, ten in enumerate(TEN_LOP):
            print(f'  {ten:<26}' + ''.join(f'{100*x[i]/t:>13.1f} ' for x, t in zip(bang, tong)))

    print('\nĐỌC KẾT QUẢ')
    print('  Bộ nào dồn gần hết pixel vào một lớp là bộ chia kém, dù thuật toán nghe hay.')
    print('  Mốc 1 và 2 giống nhau ở cả ba bộ là ĐÚNG: chỉ hai mốc trên được thay.')
    print('  Jenks tối ưu toàn cục nên nếu nó khác k-means thì k-means đã rơi cực trị')
    print('  địa phương — lúc đó chọn Jenks.')
    print('\n  Số này CHƯA phải quyết định cuối: ngưỡng chốt rồi phải đóng băng và')
    print('  chạy lại build_light_classes, vì ảnh phân lớp cũ mang thẻ THRESHOLDS khác.')


if __name__ == '__main__':
    main()
