"""Sinh ảnh COG nhẹ cho bản đồ web, rồi ghi đường dẫn vào SQLite.

    python3 -m app.data.build_cogs --root /data/SatelliteData --db app/data/vngis.db

Hai loại ảnh, theo đúng lời dặn của giảng viên:
  NTL  mỗi năm một ảnh ánh sáng đêm toàn quốc. Vốn đã nhẹ (500 m–1 km), chỉ đổi sang COG.
  DAY  mỗi năm MỘT ảnh ngày duy nhất để minh họa, RGB 8-bit giảm mẫu còn ~100 m
       (từ 24 GB xuống ~100 MB). Ảnh gốc KHÔNG lên đám mây: nó ở tầng lạnh (ổ E / NAS),
       bảng anh_goc chỉ ghi nhận nó nằm ở đâu.

Ảnh đêm đổi được bằng rasterio nếu máy không có gdal_translate (thường là Windows).
Ảnh ngày vẫn cần gdal_translate vì phải giảm mẫu và đổi sang 8-bit.
"""
import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Thứ tự băng của pipeline: 1=BLUE 2=GREEN 3=RED 4=NIR 5=SWIR1 6=SWIR2 → màu thật là 3,2,1.
RGB = ('3', '2', '1')


def co_gdal():
    from shutil import which
    return which('gdal_translate') is not None


def run(command):
    print('  $', ' '.join(str(c) for c in command), flush=True)
    subprocess.run([str(c) for c in command], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


def ntl_cog_rasterio(source, target):
    """Đổi ảnh đêm sang COG bằng rasterio, cho máy không cài gdal-bin (thường là Windows).

    Cùng kết quả với gdal_translate -of COG: ô 512, nén DEFLATE, kèm ảnh tổng quan
    (overview) để TiTiler không phải đọc toàn bộ ảnh ở mức thu nhỏ.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.shutil import copy as rio_copy
    with rasterio.open(source) as src:
        profile = src.profile.copy()
        profile.update(driver='GTiff', tiled=True, blockxsize=512, blockysize=512,
                       compress='DEFLATE', predictor=3 if src.dtypes[0].startswith('float') else 2,
                       BIGTIFF='IF_SAFER')
        tam = Path(str(target) + '.tam.tif')
        with rasterio.open(tam, 'w', **profile) as dst:
            for _, window in src.block_windows(1):
                dst.write(src.read(window=window), window=window)
            # Mức thu nhỏ: thiếu nó thì bản đồ ở mức zoom thấp phải đọc cả ảnh gốc.
            dst.build_overviews([2, 4, 8, 16, 32], Resampling.average)
            dst.update_tags(ns='rio_overview', resampling='average')
    try:
        rio_copy(tam, target, driver='COG', COMPRESS='DEFLATE', BIGTIFF='IF_SAFER')
    finally:
        tam.unlink(missing_ok=True)


def day_cog(source, target, resolution):
    """VRT 6 băng Int16 → COG RGB 8-bit giảm mẫu, đủ để nhìn chứ không để đo."""
    run(['gdal_translate', '-b', RGB[0], '-b', RGB[1], '-b', RGB[2],
         '-ot', 'Byte', '-scale', '0', '3000', '0', '255',
         '-tr', resolution, resolution, '-r', 'average',
         '-of', 'COG', '-co', 'COMPRESS=DEFLATE', '-co', 'PREDICTOR=2',
         '-co', 'NUM_THREADS=ALL_CPUS', '-co', 'OVERVIEWS=AUTO',
         source, target])


def ntl_cog(source, target):
    run(['gdal_translate', '-of', 'COG',
         '-co', 'COMPRESS=DEFLATE', '-co', 'PREDICTOR=3',
         '-co', 'NUM_THREADS=ALL_CPUS', '-co', 'OVERVIEWS=AUTO',
         source, target])


def find_sources(root, kind):
    """Tìm VRT/TIF theo năm. Chấp nhận cả VN_<SẢN PHẨM>_<NĂM>.vrt lẫn .tif."""
    found = {}
    for pattern in (f'**/VN_*_{kind}_*.vrt', f'**/VN_{kind}_*.vrt',
                    f'**/VN_*_{kind}_*.tif', f'**/VN_{kind}_*.tif'):
        for path in Path(root).glob(pattern):
            for piece in path.stem.split('_'):
                if piece.isdigit() and len(piece) == 4:
                    found.setdefault(int(piece), path)
    return dict(sorted(found.items()))


def pham_vi(path):
    """Phạm vi ảnh theo WGS84, để giao diện chỉ xin ô bản đồ trong vùng có ảnh."""
    import rasterio
    from rasterio.warp import transform_bounds
    with rasterio.open(path) as ds:
        if ds.crs is None:
            return (None, None, None, None)
        return tuple(round(v, 6) for v in transform_bounds(ds.crs, 'EPSG:4326', *ds.bounds))


def record(db, table, rows):
    from .build_indices import mo
    connection = mo(db)
    if table == 'anh_cog':
        connection.executemany(
            'INSERT OR REPLACE INTO anh_cog(loai,nam,duong_dan,nguon_anh,dung_luong_byte,'
            'tay,nam_do,dong,bac) VALUES(?,?,?,?,?,?,?,?,?)', rows)
    else:
        connection.executemany(
            'INSERT OR REPLACE INTO anh_goc(loai,nam,duong_dan,dung_luong_byte,ghi_chu) '
            'VALUES(?,?,?,?,?)', rows)
    connection.commit()
    connection.close()


def main():
    parser = argparse.ArgumentParser(description='Sinh COG nhẹ cho bản đồ VNGISDash')
    parser.add_argument('--root', default='/data/SatelliteData')
    parser.add_argument('--out', default=None, help='Nơi ghi COG (mặc định <root>/cog)')
    parser.add_argument('--db', default=str(HERE / 'vngis.db'))
    parser.add_argument('--day-resolution', default='0.001',
                        help='Độ phân giải ảnh ngày minh họa, theo độ (0.001 ≈ 100 m)')
    parser.add_argument('--kinds', nargs='+', default=['VIIRS', 'DMSP', 'SENTINEL2', 'LANDSAT'])
    arguments = parser.parse_args()

    out = Path(arguments.out or Path(arguments.root) / 'cog')
    out.mkdir(parents=True, exist_ok=True)
    cogs, originals = [], []
    for kind in arguments.kinds:
        sources = find_sources(arguments.root, kind)
        if not sources:
            print(f'{kind}: không tìm thấy ảnh nào dưới {arguments.root}')
            continue
        night = kind in ('VIIRS', 'DMSP')
        for year, source in sources.items():
            target = out / f'{kind}_{year}_cog.tif'
            print(f'{kind} {year}: {source}')
            if not target.exists():
                try:
                    if night and not co_gdal():
                        print('  (không có gdal_translate — dùng rasterio)')
                        ntl_cog_rasterio(source, target)
                    elif night:
                        ntl_cog(source, target)
                    else:
                        day_cog(source, target, arguments.day_resolution)
                except subprocess.CalledProcessError as error:
                    print(f'  BỎ QUA: gdal lỗi ({error})', file=sys.stderr)
                    continue
                except Exception as error:                      # noqa: BLE001
                    print(f'  BỎ QUA: {type(error).__name__}: {error}', file=sys.stderr)
                    continue
            cogs.append(('NTL' if night else 'DAY', year, str(target.resolve()),
                         kind, target.stat().st_size, *pham_vi(target)))
            if not night:
                originals.append((kind, year, str(Path(source).resolve()),
                                  Path(source).stat().st_size,
                                  'Tầng lạnh — không tải lên đám mây (tránh chi phí egress)'))

    if cogs:
        record(arguments.db, 'anh_cog', cogs)
    if originals:
        record(arguments.db, 'anh_goc', originals)
    print(json.dumps({'cog': len(cogs), 'anh_goc': len(originals),
                      'tong_byte_cog': sum(r[4] for r in cogs)}, indent=2))


if __name__ == '__main__':
    main()
