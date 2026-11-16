r"""Hỏi thẳng Earth Engine: tỉnh-tháng này NOAA có ảnh VIIRS hay không?

VÌ SAO CẦN: `kiem_tra_thang_thieu.py` chỉ nói được "bảng không có dòng". Nó không
phân biệt nổi hai khả năng khác hẳn nhau:

  (1) NOAA/Earth Engine KHÔNG có ảnh cho vùng đó tháng đó -> tải lại vô ích, phải
      ghi vào phần lưu ý của báo cáo và để trống.
  (2) Earth Engine CÓ ảnh nhưng luồng tải bỏ sót -> phải tải lại, và phải tìm xem
      vì sao sót.

Chỉ có cách hỏi Earth Engine mới trả lời được. Script đếm số cảnh trong cả hai sản
phẩm VCMSLCFG (ưu tiên) và VCMCFG (dự phòng) đúng theo thứ tự `methods.inventory`
đang dùng, trên đúng ranh giới tỉnh của dự án — không phải một hộp bao quanh.

    python scripts\kiem_tra_nguon_viirs.py --moc 2022-07
    python scripts\kiem_tra_nguon_viirs.py --moc 2022-07 2021-09 --tinh 01 83 84
    python scripts\kiem_tra_nguon_viirs.py --moc 2022-07 --project vngis-ee-2

Cần tài khoản Earth Engine đã đăng nhập (xem task_pipeline/SETUP_LUONG_GEE_VI.md).
Chỉ đọc siêu dữ liệu, không tải ảnh, không tốn quota xuất.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from task_pipeline.methods import VIIRS_A, VIIRS_B, collection, dates  # noqa: E402


def nap_ranh_gioi(config_path=None):
    """Dùng đúng ranh giới mà luồng tải đã dùng, không phải hộp bao hay bản rút gọn của web.

    Giá trị mặc định lấy y như app/data/build_boundaries.py, nên chạy không cần --config.
    """
    import json
    from province_pipeline.boundaries import load_boundaries
    config = (json.loads(Path(config_path).read_text(encoding='utf-8')) if config_path else
              {'boundaries': 'province_pipeline/config/boundaries.geojson',
               'boundary_metadata': 'province_pipeline/config/boundaries.metadata.json',
               'boundary_policy': 'gadm41_research'})
    thieu = [config[k] for k in ('boundaries', 'boundary_metadata') if not Path(config[k]).exists()]
    if thieu:
        raise SystemExit('Chưa có tệp ranh giới: ' + ', '.join(thieu)
                         + '\nChạy: python -m app.data.build_boundaries --tai-gadm')
    found, _meta = load_boundaries(config)
    return found


def dem(product, moc, hinh, cid):
    """Số cảnh của một sản phẩm, trên đúng ranh giới tỉnh, trong đúng cửa sổ ngày."""
    import ee
    col = collection(product, moc, ee.Geometry(hinh), collection_id=cid)
    return int(col.size().getInfo())


def do_cf(moc, hinh, cid):
    """Số pixel có cf_cvg > 0 và cf_cvg trung bình của một sản phẩm, trong ranh giới tỉnh.

    Đếm cảnh KHÔNG đủ để biết ảnh có dùng được hay không: tháng 2022-07 có đủ một
    cảnh VCMSLCFG cho cả 63 tỉnh, nhưng cf_cvg bằng 0 trên toàn ảnh nên không một
    pixel nào dùng được. `methods.inventory` chỉ chuyển sang sản phẩm dự phòng khi
    số cảnh bằng 0, nên trường hợp "có cảnh mà rỗng" không bao giờ kích hoạt dự
    phòng. Hàm này đo đúng thứ quyết định: số pixel thật sự quan sát được.
    """
    import ee
    col = collection('VIIRS_MONTHLY', moc, ee.Geometry(hinh), collection_id=cid)
    if int(col.size().getInfo()) == 0:
        return None
    cf = col.select('cf_cvg').mean().clip(ee.Geometry(hinh))
    kw = dict(geometry=ee.Geometry(hinh), scale=500, crs='EPSG:4326', maxPixels=int(1e13),
              tileScale=4)
    ra = ee.Dictionary({
        'duong': cf.gt(0).rename('x').reduceRegion(ee.Reducer.sum(), **kw).get('x'),
        'tong': cf.mask(cf.mask()).rename('x').reduceRegion(ee.Reducer.count(), **kw).get('x'),
        'tb': cf.rename('x').reduceRegion(ee.Reducer.mean(), **kw).get('x'),
    }).getInfo()
    return ra


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--moc', nargs='+', required=True, help='Mốc tháng, ví dụ 2022-07')
    p.add_argument('--tinh', nargs='*', default=None, help='Mã tỉnh; bỏ trống = cả 63')
    p.add_argument('--project', default=None, help='Project Earth Engine')
    p.add_argument('--config', default=None, help='direct-config.json nếu máy khác đã dựng ranh giới')
    p.add_argument('--do-cf', action='store_true', dest='do_cf',
                   help='Đo số pixel cf_cvg > 0 của CẢ HAI sản phẩm. Chậm hơn nhiều '
                        'nhưng trả lời được câu "có cảnh mà rỗng thì sản phẩm kia có '
                        'cứu được không" — điều mà phép đếm cảnh không trả lời nổi.')
    a = p.parse_args()

    # Nạp ranh giới TRƯỚC khi gọi Earth Engine: thiếu tệp thì báo ngay, khỏi bắt người
    # dùng đăng nhập xong mới biết là chạy sai máy.
    found = nap_ranh_gioi(a.config)
    import ee
    ee.Initialize(project=a.project) if a.project else ee.Initialize()
    ma_list = sorted(found) if not a.tinh else [t.zfill(2) for t in a.tinh]

    for moc in a.moc:
        tu, den = dates(moc)
        print(f'\n=== {moc} · cửa sổ lọc {tu} → {den} (Earth Engine loại trừ ngày cuối) ===')
        co_a, co_b, trong = [], [], []
        for ma in ma_list:
            if ma not in found:
                print(f'  {ma}: không có trong bảng ranh giới, bỏ qua')
                continue
            hinh = found[ma]['geometry']
            ten = found[ma].get('properties', {}).get('ten_tinh') or ma
            try:
                na = dem('VIIRS_MONTHLY', moc, hinh, VIIRS_A)
                nb = dem('VIIRS_MONTHLY', moc, hinh, VIIRS_B) if na == 0 else None
            except Exception as loi:                                  # noqa: BLE001
                print(f'  {ma} {ten}: LỖI {loi}')
                continue
            if na:
                co_a.append((ma, ten, na))
            elif nb:
                co_b.append((ma, ten, nb))
            else:
                trong.append((ma, ten))
            if a.do_cf:
                try:
                    ca = do_cf(moc, hinh, VIIRS_A)
                    cb = do_cf(moc, hinh, VIIRS_B)
                except Exception as loi:                              # noqa: BLE001
                    print(f'  {ma} {ten}: LỖI đo cf_cvg — {loi}')
                    ca = cb = None
                def mo_ta(c):
                    if c is None:
                        return 'không có cảnh'
                    duong, tong = c.get('duong') or 0, c.get('tong') or 0
                    tb = c.get('tb')
                    return (f"{int(duong):,}/{int(tong):,} pixel có cf_cvg>0"
                            + (f", tb={tb:.2f}" if tb is not None else ''))
                print(f'  {ma} {ten}')
                print(f'       VCMSLCFG (đang dùng): {mo_ta(ca)}')
                print(f'       VCMCFG   (dự phòng) : {mo_ta(cb)}')
                tot_a = (ca or {}).get('duong') or 0
                tot_b = (cb or {}).get('duong') or 0
                if tot_a == 0 and tot_b > 0:
                    print('       >>> Sản phẩm dự phòng CÓ dữ liệu ở chỗ sản phẩm chính rỗng.')
                continue
            print(f'  {ma} {ten:<22} VCMSLCFG={na}'
                  + (f'  VCMCFG={nb}' if nb is not None else ''))

        n = len(co_a) + len(co_b) + len(trong)
        print(f'\n  Tổng {n} tỉnh: {len(co_a)} có VCMSLCFG · {len(co_b)} chỉ có VCMCFG · '
              f'{len(trong)} KHÔNG có ảnh ở cả hai sản phẩm.')
        if co_a or co_b:
            print('  >>> Earth Engine CÓ ảnh cho những tỉnh này. Nếu bảng vẫn trống thì')
            print('      là luồng tải bỏ sót — phải chạy lại tháng này, không phải lỗi NOAA.')
        if trong:
            print('  >>> Những tỉnh dưới đây NOAA thực sự không có ảnh; tải lại vô ích,')
            print('      phải ghi vào phần lưu ý và để trống:')
            print('      ' + ', '.join(t for _, t in trong[:12])
                  + (' …' if len(trong) > 12 else ''))


if __name__ == '__main__':
    main()
