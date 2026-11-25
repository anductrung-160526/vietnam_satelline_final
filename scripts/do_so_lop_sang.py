r"""Dữ liệu ánh sáng đêm đỡ được mấy lớp? Đo bằng GVF, có hai đường đối chứng.

CHỈ ĐỌC. Không ghi cơ sở dữ liệu, không tạo ảnh, không đụng mã đang chạy.

Câu hỏi: con số 5 lớp là do dữ liệu hay do người đặt ra?

Cách đo là GVF (goodness of variance fit) theo số lớp k:

    GVF(k) = 1 − SSE(k) / SSE(1)

SSE(k) lấy từ lời giải Fisher-Jenks, tức TỐI ƯU TOÀN CỤC với mỗi k, nên không lẫn
sai số thuật toán vào kết luận. Một lần quy hoạch động cho ra SSE của mọi k.

VÌ SAO PHẢI CÓ ĐƯỜNG ĐỐI CHỨNG. Tự thân "GVF(5) = 0,83" không nói lên điều gì:
mọi phân bố đều cho GVF tăng dần tới 1 khi k tăng. Chỉ so với hai đường chuẩn mới
đọc được:

  doi_chung_tron   log-chuẩn cùng trung bình và độ lệch với dữ liệu thật.
                   KHÔNG có cụm nào. Đây là đường "không có cấu trúc".
  doi_chung_cum    ba cụm tách hẳn nhau. CÓ cấu trúc thật ở k=3.
                   Đây là hình dạng của một đường CÓ khuỷu.

DẤU HIỆU ĐỌC LÀ GÌ. Không phải "chỗ GVF tăng mạnh nhất" — chỗ đó LUÔN là k=2 với
mọi phân bố, kể cả phân bố không có cụm nào; đã kiểm và quy tắc đó sai.

Dấu hiệu thật là mức tăng SỤP xuống gần 0 ngay sau một k nào đó:

  có cấu trúc ở k*  -> tăng(k*+1) gần như bằng 0, vì đã chia đúng các cụm
  không có cấu trúc -> mức tăng giảm đều đều theo cấp số nhân, không bao giờ sụp

Script tìm k nhỏ nhất mà mức tăng kế tiếp dưới 5 % mức tăng hiện tại.

    python scripts\do_so_lop_sang.py
    python scripts\do_so_lop_sang.py --k-max 12 --bin 512
"""
import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))


def nap_bo_so_sanh():
    """Dùng lại phần đọc ảnh của so_sanh_nguong_phan_lop.py, không viết bản thứ hai."""
    spec = importlib.util.spec_from_file_location(
        'so_sanh', GOC / 'scripts' / 'so_sanh_nguong_phan_lop.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def jenks_moi_k(tam, dem, k_max):
    """Một lượt quy hoạch động cho ra SSE tối ưu của MỌI k từ 1 đến k_max.

    Bảng chi_phi[lop, n] chính là SSE tối ưu khi chia thành `lop` nhóm, nên không
    phải chạy lại từ đầu cho từng k. Vector hoá theo i để chạy được với 512 bin.
    """
    n = len(tam)
    w = np.concatenate([[0.0], np.cumsum(dem)])
    s = np.concatenate([[0.0], np.cumsum(dem * tam)])
    s2 = np.concatenate([[0.0], np.cumsum(dem * tam * tam)])

    def sse_den(j):                       # sai lệch của bin i..j-1, với mọi i < j
        i = np.arange(j)
        n_ = w[j] - w[i]
        with np.errstate(divide='ignore', invalid='ignore'):
            gia = s2[j] - s2[i] - np.where(n_ > 0, (s[j] - s[i]) ** 2 / n_, 0.0)
        return np.maximum(gia, 0.0)

    chi_phi = np.full((k_max + 1, n + 1), np.inf)
    cat = np.zeros((k_max + 1, n + 1), dtype=int)
    chi_phi[0, 0] = 0.0
    for lop in range(1, k_max + 1):
        for j in range(lop, n + 1):
            gia = chi_phi[lop - 1, :j] + sse_den(j)
            i = int(np.argmin(gia))
            chi_phi[lop, j] = gia[i]
            cat[lop, j] = i
    sse = {k: float(chi_phi[k, n]) for k in range(1, k_max + 1)}

    def moc(k):
        ranh, j = [], n
        for lop in range(k, 1, -1):
            i = cat[lop, j]
            ranh.append(float((tam[i - 1] + tam[i]) / 2))
            j = i
        return sorted(ranh)

    return sse, moc


def duong_gvf(tam, dem, k_max):
    sse, moc = jenks_moi_k(tam, dem, k_max)
    goc = sse[1] or 1.0
    return {k: 1 - sse[k] / goc for k in sse}, moc


def hist_tu_mau(mau, so_bin):
    x = np.log(mau)
    dem, canh = np.histogram(x, bins=so_bin)
    tam = (canh[:-1] + canh[1:]) / 2
    giu = dem > 0
    return tam[giu], dem[giu].astype('float64')


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--db', type=Path, default=GOC / 'backend' / 'data' / 'vngis.db')
    p.add_argument('--nam', type=int, default=2020)
    p.add_argument('--bin', type=int, default=512, dest='so_bin')
    p.add_argument('--k-max', type=int, default=10, dest='k_max')
    a = p.parse_args()

    ss = nap_bo_so_sanh()
    if not a.db.exists():
        raise SystemExit(f'Không thấy {a.db}')
    anh = ss.anh_nam_tham_chieu(a.db, a.nam)
    if not anh:
        raise SystemExit(f'Không có ảnh VIIRS năm {a.nam} trong demo_asset.')
    print(f'Năm tham chiếu {a.nam} · {len(anh)} ảnh tỉnh')
    if len(anh) != 63:
        print(f'  CẢNH BÁO: chỉ {len(anh)}/63 tỉnh, kết luận chỉ để xem thử.')

    bright = ss.doc_pixel_sang(anh)
    x = np.log(bright)
    print(f'{bright.size:,} pixel sáng · log: trung bình {x.mean():.3f}, '
          f'độ lệch {x.std():.3f}')

    rng = np.random.default_rng(20261125)
    tron = np.exp(rng.normal(x.mean(), x.std(), bright.size))
    cum = np.concatenate([
        np.exp(rng.normal(np.log(3), 0.15, int(bright.size * 0.6))),
        np.exp(rng.normal(np.log(30), 0.15, int(bright.size * 0.3))),
        np.exp(rng.normal(np.log(300), 0.15, int(bright.size * 0.1)))])

    print(f'\nĐang chạy Fisher-Jenks tới k={a.k_max} cho ba bộ, trên {a.so_bin} bin…')
    ket = {}
    moc_that = None
    for ten, mau in (('THẬT', bright), ('doi_chung_tron', tron), ('doi_chung_cum', cum)):
        tam, dem = hist_tu_mau(mau, a.so_bin)
        gvf, moc = duong_gvf(tam, dem, a.k_max)
        ket[ten] = gvf
        if ten == 'THẬT':
            moc_that = moc

    def tang(gvf, k):
        return gvf[k] - gvf[k - 1] if k > 1 else 0.0

    def k_tu_nhien(gvf):
        """k nhỏ nhất mà mức tăng kế tiếp sụp dưới 5% mức tăng hiện tại."""
        for k in range(2, a.k_max):
            hien, ke = tang(gvf, k), tang(gvf, k + 1)
            if hien > 0 and ke < 0.05 * hien:
                return k
        return None

    print('\n=== GVF THEO SỐ LỚP ===')
    print('  Cột (tăng) là mức GVF thêm được khi tách thêm một lớp.')
    print(f'  {"k":>3}{"THẬT":>9}{"(tăng)":>9}{"tròn":>9}{"(tăng)":>9}{"cụm":>9}{"(tăng)":>9}')
    for k in range(1, a.k_max + 1):
        print(f'  {k:>3}'
              + f"{ket['THẬT'][k]:>9.3f}{tang(ket['THẬT'], k):>9.3f}"
              + f"{ket['doi_chung_tron'][k]:>9.3f}{tang(ket['doi_chung_tron'], k):>9.3f}"
              + f"{ket['doi_chung_cum'][k]:>9.3f}{tang(ket['doi_chung_cum'], k):>9.3f}")

    k_that = k_tu_nhien(ket['THẬT'])
    k_tron = k_tu_nhien(ket['doi_chung_tron'])
    k_cum = k_tu_nhien(ket['doi_chung_cum'])
    print('\n=== KẾT LUẬN ===')
    print(f'  đối chứng CÓ cụm (đáp án 3) : tìm được k = {k_cum}')
    print(f'  đối chứng KHÔNG cụm         : tìm được k = {k_tron}')
    print(f'  DỮ LIỆU THẬT                : tìm được k = {k_that}')
    if k_cum != 3:
        print('\n  >>> Phép đo KHÔNG đáng tin: nó trượt cả trên bộ có đáp án biết trước.')
        print('      Đừng dùng kết quả dòng trên để quyết định gì.')
    elif k_that is None:
        print('\n  => DỮ LIỆU KHÔNG CÓ SỐ LỚP TỰ NHIÊN. Mức tăng giảm đều, không sụp ở đâu,')
        print('     giống hệt phân bố log-chuẩn không cụm. Chọn 5 lớp hay 4 hay 7 đều là')
        print('     QUY ƯỚC TRÌNH BÀY. Phải viết rõ điều đó trong báo cáo, thay vì để')
        print('     người đọc tưởng năm lớp là cấu trúc tìm được từ dữ liệu.')
    else:
        print(f'\n  => Dữ liệu ủng hộ {k_that} lớp: mức tăng sụp ngay sau đó, đúng dấu hiệu')
        print('     của đối chứng có cụm. Cân nhắc đổi số lớp — nhưng xem chi phí trước:')
        print('     đổi SỐ LỚP là sửa schema, không phải sửa tham số.')

    print(f'\n=== MỐC TỐI ƯU Ở k = 5 (để đối chiếu với bộ đang dùng) ===')
    print('  ' + ' · '.join(f'{np.exp(v):.2f}' for v in moc_that(5)))
    print('  Đây là 4 mốc Jenks trên TOÀN BỘ pixel sáng, không ép giữ 0,5 và 1,5.')
    print('  Khác bộ đang chạy là chuyện bình thường: bộ kia giữ hai mốc vật lý.')


if __name__ == '__main__':
    main()
