"""Ghép ảnh đêm 63 tỉnh của từng tháng thành một ảnh toàn quốc, rồi ghi ra COG.

    python3 -m app.data.build_monthly_cogs --root E:\\SatelliteData

Ảnh VIIRS được tải theo TỈNH theo THÁNG, mỗi tháng 63 file rời. Bản đồ của app thì đọc
một ảnh toàn quốc cho mỗi mốc thời gian. Mô-đun này lấp đúng khoảng đó: ghép 63 mảnh của
cùng một tháng, không tải thêm gì từ Earth Engine.

Dùng ảnh đã lọc nhiễu ở data_intermediate/VIIRS_MONTHLY/ nếu có (cf_cvg=0 -> NoData,
giá trị âm -> 0, đỉnh bất thường bị cắt theo trung vị năm) để ảnh trên bản đồ khớp với
chính con số trong bảng chỉ số. Thiếu thì lùi về ảnh thô ở raw_data/ và nói rõ.

Mỗi file tỉnh phủ hình chữ nhật bao quanh tỉnh, phần ngoài ranh giới là -9999. Khi ghép,
-9999 được coi là "không có dữ liệu" nên không đè lên phần hợp lệ của tỉnh bên cạnh.
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

from province_pipeline.sources import NTL_PACKAGE

HERE = Path(__file__).resolve().parent
NODATA = -9999.0
# <bất kỳ>_VIIRS_2016-07_filtered.tif  hoặc  40_nghe_an_VIIRS_2016-07_province_...tif
KY = re.compile(r'_VIIRS_(\d{4})-(\d{2})[_.]')


def tim_anh_thang(root):
    """{(năm, tháng): [đường dẫn từng tỉnh]}, ưu tiên ảnh đã lọc nhiễu."""
    goc = Path(root) / NTL_PACKAGE
    da_loc = goc / 'data_intermediate' / 'VIIRS_MONTHLY'
    tho = goc / 'raw_data' / 'NTL' / 'VIIRS'
    thu_muc, nhan = (da_loc, 'đã lọc nhiễu') if da_loc.is_dir() else (tho, 'THÔ, chưa lọc nhiễu')
    theo_ky = defaultdict(list)
    for path in thu_muc.rglob('*.tif'):
        khop = KY.search(path.name)
        if khop:
            theo_ky[(int(khop.group(1)), int(khop.group(2)))].append(path)
    return dict(sorted(theo_ky.items())), nhan, thu_muc


def ghep(cac_manh, target):
    """Ghép các mảnh tỉnh thành một ảnh, ghi COG kèm mức thu nhỏ."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.merge import merge
    from rasterio.shutil import copy as rio_copy

    mo = [rasterio.open(p) for p in cac_manh]
    try:
        # indexes=[1]: ảnh thô có 2 băng (avg_rad, cf_cvg), ảnh đã lọc có 1. Luôn lấy băng bức xạ.
        anh, bien_doi = merge(mo, indexes=[1], nodata=NODATA, resampling=Resampling.nearest)
        ho_so = mo[0].profile.copy()
    finally:
        for ds in mo:
            ds.close()

    ho_so.update(driver='GTiff', height=anh.shape[1], width=anh.shape[2], count=1,
                 dtype='float32', nodata=NODATA, transform=bien_doi, crs='EPSG:4326',
                 tiled=True, blockxsize=512, blockysize=512,
                 compress='DEFLATE', predictor=3, BIGTIFF='IF_SAFER')
    tam = Path(str(target) + '.tam.tif')
    with rasterio.open(tam, 'w', **ho_so) as dst:
        dst.write(anh[0].astype('float32'), 1)
        dst.set_band_description(1, 'avg_rad')
        dst.build_overviews([2, 4, 8, 16], Resampling.average)
        dst.update_tags(ns='rio_overview', resampling='average')
        dst.update_tags(SOURCE='VIIRS_MONTHLY_MOSAIC', UNIT='nW/cm2/sr',
                        PROVINCES=str(len(cac_manh)))
    try:
        rio_copy(tam, target, driver='COG', COMPRESS='DEFLATE', BIGTIFF='IF_SAFER')
    finally:
        tam.unlink(missing_ok=True)
    return anh.shape[2], anh.shape[1]


def main():
    parser = argparse.ArgumentParser(description='Ghép ảnh đêm toàn quốc theo tháng')
    parser.add_argument('--root', default='/data/SatelliteData')
    parser.add_argument('--out', default=None, help='Nơi ghi COG (mặc định <root>/cog)')
    parser.add_argument('--db', default=str(HERE / 'vngis.db'))
    parser.add_argument('--tu', type=int, default=2014, help='Năm bắt đầu')
    parser.add_argument('--den', type=int, default=2025, help='Năm kết thúc')
    parser.add_argument('--lam-lai', action='store_true', dest='lam_lai',
                        help='Ghép lại cả những tháng đã có COG')
    parser.add_argument('--kiem-ke', action='store_true', dest='kiem_ke',
                        help='Chỉ đếm, không ghép')
    arguments = parser.parse_args()

    theo_ky, nhan, thu_muc = tim_anh_thang(arguments.root)
    trong_khoang = {k: v for k, v in theo_ky.items() if arguments.tu <= k[0] <= arguments.den}

    print(f'Nguồn ảnh: {thu_muc}')
    print(f'  loại: {nhan}')
    print(f'  {len(theo_ky)} tháng có ảnh, {len(trong_khoang)} tháng trong khoảng '
          f'{arguments.tu}–{arguments.den}')
    thieu = [f'{y}-{m:02}' for (y, m), v in sorted(trong_khoang.items()) if len(v) < 63]
    if thieu:
        print(f'  {len(thieu)} tháng chưa đủ 63 tỉnh: {", ".join(thieu[:8])}'
              + (' …' if len(thieu) > 8 else ''))
        print('  Vẫn ghép được, nhưng ảnh sẽ thiếu đúng những tỉnh đó.')
    if arguments.kiem_ke:
        return

    if not trong_khoang:
        raise SystemExit('Không tìm thấy ảnh tháng nào. Kiểm tra --root và --tu/--den.')

    out = Path(arguments.out or Path(arguments.root) / 'cog')
    out.mkdir(parents=True, exist_ok=True)
    from .build_cogs import pham_vi, record

    ban_ghi, bo_qua = [], 0
    for (nam, thang), cac_manh in trong_khoang.items():
        target = out / f'NTL_{nam}-{thang:02}_cog.tif'
        if target.exists() and not arguments.lam_lai:
            bo_qua += 1
        else:
            print(f'{nam}-{thang:02}: ghép {len(cac_manh)} tỉnh…', flush=True)
            try:
                rong, cao = ghep(sorted(cac_manh), target)
                print(f'  {rong}x{cao} · {target.stat().st_size / 1048576:.1f} MB')
            except Exception as error:                      # noqa: BLE001
                print(f'  BỎ QUA: {type(error).__name__}: {error}', file=sys.stderr)
                continue
        ban_ghi.append(('NTL', nam, thang, str(target.resolve()), 'VIIRS',
                        target.stat().st_size, *pham_vi(target)))

    if ban_ghi:
        record(arguments.db, 'cog_image', ban_ghi, theo_thang=True)
    print(f'\n{len(ban_ghi)} tháng đã vào sổ' + (f', {bo_qua} tháng đã có sẵn.' if bo_qua else '.'))
    print('Nạp lại chỉ số rồi mở app:')
    print(f'  python3 -m app.data.build_indices --root {arguments.root}')


if __name__ == '__main__':
    main()
