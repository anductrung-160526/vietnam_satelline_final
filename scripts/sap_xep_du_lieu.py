"""Soát thư mục data_processed: cái gì là bộ dữ liệu chính, cái gì là di sản bỏ được.

    python scripts/sap_xep_du_lieu.py --root E:\\SatelliteData            # chỉ xem
    python scripts/sap_xep_du_lieu.py --root E:\\SatelliteData --xoa      # xoá thật

Mặc định KHÔNG xoá gì. Xoá là việc không hoàn tác được nên phải gõ --xoa, và kể cả
khi đó cũng chỉ đụng vào danh sách GIU_LAI=False dưới đây, không bao giờ quét bừa.

Mỗi bảng có ba tệp .csv/.xlsx/.dta sinh ra từ cùng một nguồn. Giữ cả ba là có chủ ý:
.csv để máy đọc, .xlsx để mở bằng Excel, .dta cho Stata. Đó không phải tệp thừa.
"""
import argparse
from pathlib import Path

NTL_PACKAGE = 'VN_NTL_Panel_2004_2025'
DUOI = ('.csv', '.xlsx', '.dta')

# tên bảng -> (giữ lại?, vì sao)
BANG = {
    'ntl_panel': (True, 'BỘ CHÍNH: DMSP theo năm 2004–2013 + VIIRS theo tháng 2014–2025'),
    'ntl_annual': (True, 'chuỗi theo năm, cần cho bước hiệu chỉnh và cho biểu đồ năm của app'),
    'ntl_monthly': (True, 'mọi tháng VIIRS, kể cả 2013 — nguồn để dựng ntl_panel'),
    'ntl_overlap_2013': (True, 'cặp DMSP–VIIRS năm 2013, mô hình hiệu chỉnh khớp trên bảng này'),
    'ntl_indices_ee': (False, 'DI SẢN luồng Earth Engine cũ. Tên cột không còn khớp schema '
                              'hiện tại nên nạp vào chỉ tạo ra bảng toàn cột rỗng.'),
}


def kiem_ke(root):
    thu_muc = Path(root) / NTL_PACKAGE / 'data_processed'
    if not thu_muc.is_dir():
        raise SystemExit(f'Không thấy {thu_muc}.')
    co = {}
    for path in sorted(thu_muc.iterdir()):
        if path.suffix in DUOI:
            co.setdefault(path.stem, []).append(path)
    return thu_muc, co


def main():
    parser = argparse.ArgumentParser(description='Soát và dọn data_processed')
    parser.add_argument('--root', default='/data/SatelliteData')
    parser.add_argument('--xoa', action='store_true',
                        help='Xoá thật các tệp di sản (mặc định chỉ liệt kê)')
    arguments = parser.parse_args()
    thu_muc, co = kiem_ke(arguments.root)
    print(f'{thu_muc}\n')

    bo_di = []
    for ten, paths in sorted(co.items()):
        giu, vi_sao = BANG.get(ten, (True, 'chưa rõ — KHÔNG đụng tới'))
        tong = sum(p.stat().st_size for p in paths) / 1048576
        thieu = [d for d in DUOI if not any(p.suffix == d for p in paths)]
        print(f"{'GIỮ   ' if giu else 'BỎ ĐI '} {ten:<20} {tong:>7.1f} MB  "
              f"{len(paths)} tệp{'  (thiếu ' + ', '.join(thieu) + ')' if thieu else ''}")
        print(f'       {vi_sao}')
        if not giu:
            bo_di += paths

    if 'ntl_panel' not in co:
        print('\nCHƯA CÓ ntl_panel — bộ dữ liệu gộp chưa được sinh ra.')
        print('Chạy lại bước tính chỉ số: scripts\\windows\\chi_so_dem.ps1')

    if not bo_di:
        print('\nKhông có tệp nào cần bỏ.')
        return
    tong = sum(p.stat().st_size for p in bo_di) / 1048576
    print(f'\n{len(bo_di)} tệp di sản, {tong:.1f} MB.')
    if not arguments.xoa:
        print('Chưa xoá gì. Muốn xoá thật thì chạy lại với --xoa.')
        return
    for path in bo_di:
        path.unlink()
        print(f'  đã xoá {path.name}')


if __name__ == '__main__':
    main()
