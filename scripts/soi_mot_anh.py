r"""Mở thẳng một ảnh VIIRS thô ra xem, để biết tháng trống là mây hay là lỗi.

Ảnh VIIRS thô có hai băng: `avg_rad` (bức xạ) và `cf_cvg` (số lượt quan sát sạch
mây của chính pixel đó trong tháng). `derive.viirs_filtered` chỉ giữ pixel có
`cf_cvg > 0`; pixel nào tháng đó không có lượt quan sát sạch mây nào thì bị loại
thành NoData. Tỉnh nào mất sạch pixel thì `sol` rỗng.

Script đếm thẳng trên ảnh: bao nhiêu pixel có cf_cvg > 0. Đó là bằng chứng cuối
cùng phân biệt hai thứ mà mọi tầng ở trên đều không phân biệt nổi:

  cf_cvg = 0 gần hết  -> mây che kín. Tải lại bao nhiêu lần cũng ra y như vậy.
  cf_cvg bình thường  -> ảnh tốt, lỗi nằm ở khâu lọc hoặc khâu tính.

    python scripts\soi_mot_anh.py --root E:\SatelliteData --tinh 01 --moc 2022-07
    python scripts\soi_mot_anh.py --root E:\SatelliteData --tinh 01 06 79 --moc 2022-07 2022-06

Chỉ đọc ảnh, không sửa gì.
"""
import argparse
import json
from pathlib import Path

GOI_NTL = 'VN_NTL_Panel_2004_2025'


def thu_muc_tinh(root, ma):
    goc = Path(root) / GOI_NTL / 'raw_data' / 'NTL' / 'VIIRS'
    ds = [d for d in goc.glob(f'{ma}_*') if d.is_dir()] if goc.is_dir() else []
    return ds[0] if ds else None


def soi(path):
    import numpy as np
    import rasterio
    with rasterio.open(path) as ds:
        ra = {'bang': ds.count, 'kich_thuoc': f'{ds.width}x{ds.height}',
              'nodata': ds.nodata, 'ten_bang': list(ds.descriptions)}
        rad = ds.read(1).astype('float64')
        nod = ds.nodata
        co_rad = np.isfinite(rad) if nod is None else (rad != nod) & np.isfinite(rad)
        ra['pixel_tong'] = int(rad.size)
        ra['pixel_co_rad'] = int(co_rad.sum())
        if ds.count >= 2:
            cov = ds.read(2).astype('float64')
            co_cov = np.isfinite(cov) if nod is None else (cov != nod) & np.isfinite(cov)
            hop_le = co_rad & co_cov & (cov > 0)
            ra['pixel_cf_duong'] = int(hop_le.sum())
            ra['cf_trung_binh'] = (round(float(cov[hop_le].mean()), 3)
                                   if hop_le.any() else None)
            ra['cf_lon_nhat'] = round(float(cov[co_cov].max()), 3) if co_cov.any() else None
            ra['sol_neu_tinh'] = (round(float(np.maximum(rad[hop_le], 0).sum()), 2)
                                  if hop_le.any() else None)
        else:
            ra['pixel_cf_duong'] = None
        return ra


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', type=Path, default=Path('/data/SatelliteData'))
    p.add_argument('--tinh', nargs='+', required=True, help='Mã tỉnh, ví dụ 01')
    p.add_argument('--moc', nargs='+', required=True, help='Mốc tháng, ví dụ 2022-07')
    a = p.parse_args()

    for ma in [t.zfill(2) for t in a.tinh]:
        thu_muc = thu_muc_tinh(a.root, ma)
        if thu_muc is None:
            print(f'\n{ma}: không thấy thư mục ảnh thô.')
            continue
        print(f'\n=== {thu_muc.name} ===')
        for moc in a.moc:
            tep = sorted(thu_muc.glob(f'*{moc}*.tif'))
            if not tep:
                print(f'  {moc}: KHÔNG CÓ TỆP')
                continue
            for t in tep:
                try:
                    r = soi(t)
                except Exception as loi:                               # noqa: BLE001
                    print(f'  {moc}: MỞ KHÔNG ĐƯỢC — {loi}')
                    continue
                tong, co_rad = r['pixel_tong'], r['pixel_co_rad']
                hop_le = r['pixel_cf_duong']
                print(f'  {moc}  {t.name}')
                print(f'     {r["bang"]} băng {r["ten_bang"]} · {r["kich_thuoc"]} · '
                      f'nodata={r["nodata"]}')
                print(f'     pixel có avg_rad : {co_rad:>10,} / {tong:,}')
                if hop_le is None:
                    print('     KHÔNG CÓ BĂNG cf_cvg — ảnh này không đúng dạng mong đợi.')
                    continue
                print(f'     pixel cf_cvg > 0 : {hop_le:>10,}'
                      f'  ({hop_le/tong:.1%} toàn ảnh)')
                print(f'     cf_cvg trung bình: {r["cf_trung_binh"]}  '
                      f'· lớn nhất: {r["cf_lon_nhat"]}')
                print(f'     sol nếu tính ngay: {r["sol_neu_tinh"]}')
                if hop_le == 0:
                    print('     >>> KHÔNG pixel nào có lượt quan sát sạch mây. Ảnh về đủ,')
                    print('         nhưng cả tháng tỉnh này bị mây che. Tải lại vô ích.')
                elif co_rad and hop_le < co_rad * 0.2:
                    print('     >>> Dưới 20% pixel quan sát được. Giá trị sol tháng này')
                    print('         không so sánh được với tháng đủ phủ.')

    print('\nĐọc kết quả: cf_cvg là số lượt quan sát SẠCH MÂY của từng pixel trong tháng.')
    print('Bằng 0 nghĩa là tháng đó vệ tinh không nhìn thấy mặt đất ở pixel ấy lần nào.')


if __name__ == '__main__':
    main()
