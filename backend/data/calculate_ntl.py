"""Tính lại chỉ số đêm từ GeoTIFF đã lọc, đã cắt/mask theo tỉnh.

Công thức ntl_stats trích từ task_pipeline/derive.py tại commit 25bf350.
Không tải ảnh, không lọc ảnh thô, không suy ra ảnh năm từ bảng tháng.
Chạy: python -m backend.data.calculate_ntl --manifest danh_sach_anh.csv --root /data/SatelliteData
"""
import argparse
import csv
import math
import os
import tempfile
from pathlib import Path

import numpy as np
from rasterio.windows import Window

NODATA = -9999
STATS_VERSION = 6  # v5 pipeline + mask/NaN/Inf và kiểm tra CRS; không dùng cache cũ
LIT_THRESHOLD = {'VIIRS': 1.5, 'DMSP': 5.0}
BACKGROUND = {'VIIRS': 0.5, 'DMSP': 0.0}


def windows(height, width):
    for row in range(0, height, 512):
        for col in range(0, width, 512):
            yield Window(col, row, min(512, width-col), min(512, height-row))


def pixel_area_km2(transform, window, crs):
    """Giữ công thức diện tích của pipeline cho WGS84 và lưới chiếu mét."""
    if crs is None:
        raise ValueError('Ảnh thiếu CRS; không thể tính diện tích sáng.')
    if transform.b or transform.d:
        raise ValueError('Chưa hỗ trợ lưới ảnh xoay; cần ảnh north-up.')
    if crs.to_epsg() == 4326:
        rows = np.arange(window.row_off, window.row_off+window.height)+0.5
        lat = transform.f+rows*transform.e
        return (abs(transform.a*transform.e)*111.320**2*np.cos(np.radians(lat)))[:, None]
    if not crs.is_projected or crs.linear_units != 'metre':
        raise ValueError('CRS phải là EPSG:4326 hoặc hệ chiếu có đơn vị mét.')
    return np.full((int(window.height), 1), abs(transform.a*transform.e)/1e6)


def ntl_stats(path,threshold=None,background=0.0):
    """Thống kê một ảnh đêm trong một lượt đọc. Tên khoá = tên cột trong bảng xuất ra.

    background: ngưỡng nền. Pixel dưới ngưỡng vẫn là pixel hợp lệ (vẫn tính vào diện tích
    và vào rad_mean/rad_std) nhưng đóng góp 0 vào sol — đó là nghĩa của "trừ ánh sáng nền".
    sol_raw giữ tổng chưa trừ nền để đo được bước này lấy đi bao nhiêu.

    threshold=None thì bỏ qua mọi chỉ số vùng sáng (trả None), không coi mọi pixel là sáng.

    cloud_free_obs đọc từ thẻ CF_CVG_MEAN do viirs_filtered ghi; ảnh DMSP không có thẻ này
    nên trả None. Đây là trường chất lượng: tháng mùa mưa ít lượt quan sát sạch mây hơn,
    con số của tháng đó dựa trên ít dữ liệu hơn.
    """
    import rasterio
    total=0.0;tho=0.0;sq=0.0;n=0;nen=0;lit=0;lit_total=0.0;lit_area=0.0;mx=None;mn=None
    with rasterio.open(path) as ds:
        if ds.count != 1:
            raise ValueError('Cần ảnh một băng đã lọc, không dùng ảnh thô nhiều băng/RGB.')
        pixel_area_km2(ds.transform, Window(0, 0, 1, 1), ds.crs)
        cov=ds.tags().get('CF_CVG_MEAN')
        for w in windows(ds.height,ds.width):
            a=ds.read(1,window=w).astype('float64')
            valid=ds.read_masks(1,window=w).astype(bool) & np.isfinite(a) & (a!=NODATA)
            if not valid.any():continue
            x=a[valid]
            tho+=x.sum()
            tren_nen=x>=background if background else np.ones(x.shape,dtype=bool)
            nen+=int((~tren_nen).sum())
            total+=float(x[tren_nen].sum())
            sq+=float((x*x).sum());n+=x.size
            mx=x.max() if mx is None else max(mx,x.max())
            mn=x.min() if mn is None else min(mn,x.min())
            if threshold is not None:
                sang=valid&(a>=threshold)
                if sang.any():
                    lit+=int(sang.sum());lit_total+=float(a[sang].sum())
                    lit_area+=float(np.broadcast_to(
                        pixel_area_km2(ds.transform,w,ds.crs),sang.shape)[sang].sum())
    try:
        cov=round(float(cov),4) if cov is not None else None
        if cov is not None and not math.isfinite(cov):
            cov=None
    except ValueError:
        cov=None
    if not n:
        return dict(sol=None,sol_raw=None,valid_pixels=0,background_pixels=None,
                    rad_max=None,rad_min=None,rad_mean=None,rad_std=None,rad_cv=None,
                    lit_pixels=None,lit_sol=None,lit_area_km2=None,lit_pixel_pct=None,
                    background_threshold=background,cloud_free_obs=cov)
    mean=tho/n
    std=math.sqrt(max(sq/n-mean*mean,0))
    co_nguong=threshold is not None
    return dict(sol=round(total,4),sol_raw=round(tho,4),
                valid_pixels=n,background_pixels=nen,background_threshold=background,
                rad_max=round(float(mx),4),rad_min=round(float(mn),4),
                rad_mean=round(mean,6),rad_std=round(std,6),
                # Hệ số biến thiên: mức chênh lệch sáng-tối bên trong tỉnh.
                rad_cv=round(std/mean,4) if mean>0 else None,
                lit_pixels=lit if co_nguong else None,
                lit_sol=round(lit_total,4) if co_nguong else None,
                lit_area_km2=round(lit_area,4) if co_nguong else None,
                # Tỷ lệ SỐ PIXEL sáng (notebook gốc gọi là electrification ratio), khác
                # lit_area_pct vốn chia cho diện tích tự nhiên của tỉnh.
                lit_pixel_pct=round(100*lit/n,4) if co_nguong else None,
                cloud_free_obs=cov)


def pct(current, previous):
    return (round(100*(current/previous-1), 4)
            if current is not None and previous is not None and previous > 0 else None)


def read_manifest(path):
    """Mỗi dòng là một ảnh tỉnh, area_km2 là diện tích TỰ NHIÊN, không phải vùng hợp lệ."""
    path = Path(path).resolve()
    records, seen = [], set()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'province_code', 'province_name', 'year', 'month', 'source', 'path', 'area_km2'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('Manifest thiếu cột: '+', '.join(sorted(required-set(reader.fieldnames or []))))
        for number, raw in enumerate(reader, 2):
            if any(raw.get(k) is None for k in required):
                raise ValueError(f'Dòng {number}: thiếu ô dữ liệu trong CSV.')
            code = raw['province_code'].strip().zfill(2)
            year, month = int(raw['year']), int(raw['month'] or 0)
            source = raw['source'].strip().upper()
            area = float(raw['area_km2'])
            if not code.isdigit() or len(code) != 2 or not raw['province_name'].strip():
                raise ValueError(f'Dòng {number}: mã/tên tỉnh không hợp lệ.')
            if not 2004 <= year <= 2025 or not 0 <= month <= 12:
                raise ValueError(f'Dòng {number}: năm/tháng ngoài phạm vi.')
            if source not in LIT_THRESHOLD or (source == 'DMSP' and (month or year > 2013)) or (source == 'VIIRS' and year < 2013):
                raise ValueError(f'Dòng {number}: nguồn ảnh không khớp giai đoạn/tần suất.')
            if not math.isfinite(area) or area <= 0:
                raise ValueError(f'Dòng {number}: area_km2 phải dương và hữu hạn.')
            key = (code, year, month, source)
            if key in seen:
                raise ValueError(f'Dòng {number}: trùng ảnh {key}.')
            seen.add(key)
            image = Path(raw['path'].strip())
            if not raw['path'].strip():
                raise ValueError(f'Dòng {number}: thiếu đường dẫn ảnh.')
            image = image if image.is_absolute() else path.parent/image
            if not image.is_file():
                raise FileNotFoundError(image)
            records.append(dict(province_code=code, province_name=raw['province_name'].strip(),
                                year=year, month=month, source=source, path=image, area_km2=area))
    if not records:
        raise ValueError('Manifest không có ảnh nào.')
    return records


def calculate(records):
    annual, monthly, overlap = [], [], []
    lookup = {}
    for record in records:
        row = {k: v for k, v in record.items() if k != 'path'}
        source = row['source']
        row.update(ntl_stats(record['path'], LIT_THRESHOLD[source], BACKGROUND[source]))
        row['lit_threshold'] = LIT_THRESHOLD[source]
        row['sol_density'] = (round(row['sol']/row['area_km2'], 6)
                              if row['sol'] is not None else None)
        row['lit_area_pct'] = (round(100*row['lit_area_km2']/row['area_km2'], 4)
                               if row['lit_area_km2'] is not None else None)
        row['period'] = f"{row['year']}-{row['month']:02}" if row['month'] else str(row['year'])
        row['frequency'] = 'monthly' if row['month'] else 'annual'
        row['calibration'] = 'PENDING'
        row['status'] = 'OK' if row['valid_pixels'] else 'INSUFFICIENT_QUALITY'
        row['obs_status'] = ('L' if not row['valid_pixels'] else
                             'B' if not row['month'] and row['year'] in (2010, 2014) else
                             'U' if row['cloud_free_obs'] is not None and row['cloud_free_obs'] < 2 else 'A')
        lookup[(row['province_code'], row['year'], row['month'], source)] = row
        if row['month']:
            monthly.append(row)
        elif source == 'DMSP' or row['year'] >= 2014:
            annual.append(row)
    # Annual VIIRS 2013 belongs only to the overlap pair, never to ntl_annual.
    for row in annual:
        previous = (lookup.get((row['province_code'], row['year']-1, 0, row['source']))
                    if row['year'] != 2014 else None)
        row['sol_change_pct'] = pct(row['sol'], previous['sol']) if previous else None
        row['note'] = 'DOI_NGUON_ANH_CHUA_HIEU_CHINH' if row['year'] == 2014 else ''
    for row in monthly:
        code, year, month = row['province_code'], row['year'], row['month']
        previous_year = lookup.get((code, year-1, month, 'VIIRS'))
        previous_month = lookup.get((code, year if month > 1 else year-1, month-1 if month > 1 else 12, 'VIIRS'))
        row['sol_change_yoy_pct'] = pct(row['sol'], previous_year['sol']) if previous_year else None
        row['sol_change_mom_pct'] = pct(row['sol'], previous_month['sol']) if previous_month else None
        # Calendar window: do not use older observations across a missing month.
        values = []
        for offset in range(3):
            index = year*12+month-1-offset
            item = lookup.get((code, index//12, index % 12+1, 'VIIRS'))
            if item and item['sol'] is not None:
                values.append(item['sol'])
        row['sol_ma3'] = round(sum(values)/len(values), 4) if values else None
    for code in sorted({r['province_code'] for r in records}):
        dmsp = lookup.get((code, 2013, 0, 'DMSP'))
        viirs = lookup.get((code, 2013, 0, 'VIIRS'))
        if dmsp and viirs:
            overlap.append(dict(province_code=code, province_name=dmsp['province_name'], year=2013,
                                sol_dmsp=dmsp['sol'], sol_viirs=viirs['sol'], area_km2=dmsp['area_km2']))
    panel = [dict(r) for r in annual if r['source'] == 'DMSP']
    panel += [dict(r) for r in monthly if r['year'] >= 2014]
    return dict(ntl_annual=annual, ntl_monthly=monthly, ntl_panel=panel, ntl_overlap_2013=overlap)


def write_tables(tables, directory, overwrite=False):
    """Xuất từng file nguyên tử; chặn ghi đè mặc định để giữ kết quả đang dùng."""
    directory = Path(directory)
    paths = {name: directory/(name+'.csv') for name in tables}
    if not overwrite and any(p.exists() for p in paths.values()):
        raise FileExistsError('Đã có bảng kết quả; chọn thư mục khác hoặc thêm --overwrite.')
    directory.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        fields = sorted({k for row in rows for k in row}) or ['province_code', 'year']
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8-sig', newline='',
                                             dir=directory, delete=False) as stream:
                temporary = Path(stream.name)
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(sorted(rows, key=lambda r: (r['province_code'], r['year'], r.get('month', 0))))
            os.replace(temporary, paths[name])
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path, help='CSV danh sách ảnh theo tỉnh')
    parser.add_argument('--root', type=Path, default=Path('/data/SatelliteData'))
    parser.add_argument('--output', type=Path, help='Thư mục CSV; mặc định <root>/VN_NTL_Panel_2004_2025/data_processed')
    parser.add_argument('--overwrite', action='store_true', help='Cho phép thay các bảng kết quả đã có')
    args = parser.parse_args()
    directory = args.output or args.root/'VN_NTL_Panel_2004_2025'/'data_processed'
    try:
        records = read_manifest(args.manifest)
        # Check before spending time reading large rasters.
        if not args.overwrite and any((directory/(n+'.csv')).exists() for n in ('ntl_annual', 'ntl_monthly', 'ntl_panel', 'ntl_overlap_2013')):
            raise FileExistsError('Đã có bảng kết quả; chọn --output khác hoặc thêm --overwrite.')
        tables = calculate(records)
        write_tables(tables, directory, args.overwrite)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Lỗi: {error}\n')
    for name, rows in tables.items():
        print(f'{name}: {len(rows)} dòng -> {directory/(name+".csv")}')
    print('Chưa hiệu chỉnh DMSP–VIIRS: calibration=PENDING, các cột _cal chưa được tính.')
    print('Nạp vào app: python -m backend.data.build_indices --root '+str(args.root))


if __name__ == '__main__':
    main()
