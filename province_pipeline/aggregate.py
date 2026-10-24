"""Local, single-writer source panels; no cross-sensor harmonization is implied."""
import json
import math
from pathlib import Path
from .sources import SOURCES, NTL_PACKAGE, DAY_PACKAGE
from .common import atomic_json


def growth(frame, value):
    import pandas as pd
    frame = frame.sort_values(['ma_tinh', 'period']).copy()
    prior = frame.groupby('ma_tinh')[value].shift()
    previous_period = frame.groupby('ma_tinh')['period'].shift()
    frequency = 'M' if frame['period'].str.len().eq(7).all() else 'Y'
    current_ord = frame['period'].map(lambda s: pd.Period(s, freq=frequency).ordinal)
    prev_ord = previous_period.map(lambda s: pd.Period(s, freq=frequency).ordinal if pd.notna(s) else float('nan'))
    usable = (current_ord-prev_ord).eq(1) & prior.gt(0) & frame[value].notna()
    frame['thay_doi_ntl'] = ((frame[value]/prior-1)*100).where(usable)
    frame['growth_qa'] = usable.map({True:'OK', False:'NO_VALID_PREVIOUS_PERIOD'})
    return frame


def row_statistics(row, product):
    source = SOURCES[product]
    valid = float(row.get('valid_area', 0) or 0)
    total = float(row.get('total_area', 0) or 0)
    if not math.isfinite(valid):
        valid = 0
    if not math.isfinite(total) or total <= 0 or valid < 0 or valid > total * 1.000001:
        raise ValueError('Invalid province coverage area')
    row['valid_fraction'] = valid/total if total > 0 else float('nan')
    row['qa'] = 'NO_VALID_PIXELS' if valid <= 0 else ('PARTIAL_COVERAGE' if valid/total < 0.95 else 'OK')
    for b in source['bands']:
        w, w2 = row.get(b+'_w'), row.get(b+'_w2')
        mean = float(w)/valid if valid > 0 and w is not None and math.isfinite(float(w)) else float('nan')
        row[b+'_mean'] = mean
        row[b+'_std'] = math.sqrt(max(0, float(w2)/valid-mean**2)) if valid > 0 and w2 is not None and math.isfinite(float(w2)) and math.isfinite(mean) else float('nan')
    if product.startswith(('DMSP', 'VIIRS')):
        band = 'stable_lights' if product == 'DMSP' else 'avg_rad'
        row['sol_ntl'] = row.get(band+'_sum') if valid > 0 else float('nan')
        row['dien_tich_km2'] = total/1e6
        row['mat_do_ntl'] = row['sol_ntl']/(total/1e6) if total > 0 and valid > 0 else float('nan')
        row['sol_area_integral'] = row.get(band+'_w', float('nan'))/1e6 if valid > 0 else float('nan')
    return row


def aggregate(root):
    import pandas as pd
    root = Path(root)
    manifests = root / '.manifests'
    grouped = {}
    for path in sorted(manifests.glob('*.json')):
        manifest = json.loads(path.read_text(encoding='utf-8'))
        job = manifest['job']
        if job['kind'] != 'table':
            continue
        # Only aggregate files with a verified local receipt and revalidated bytes/schema.
        from .receiver import validate
        from .common import local_path
        receipt = json.loads((root / '.receipts' / path.name).read_text(encoding='utf-8'))
        for f in manifest['files']:
            local = local_path(root, f['local_relative_path'])
            sha = validate(local, f, job)
            if not any(i['id'] == f['id'] and i.get('verified') and i['sha256'] == sha for i in receipt['files']):
                raise ValueError('Statistics receipt mismatch')
            row = pd.read_csv(local, dtype={'ma_tinh': str, 'period': str, 'job_id': str}).iloc[0].to_dict()
            row = row_statistics(row, job['product'])
            row['recipe_hash'] = job['recipe_hash']
            grouped.setdefault((job['product'], job['recipe_hash']), []).append(row)
    for (product, recipe), rows in grouped.items():
        frame = pd.DataFrame(rows)
        if frame.duplicated(['ma_tinh','period']).any():
            raise ValueError('Duplicate province/period within recipe; inspect versions')
        if product.startswith(('DMSP','VIIRS')):
            frame = growth(frame, 'sol_ntl')
        package = NTL_PACKAGE if product.startswith(('DMSP','VIIRS')) else DAY_PACKAGE
        dest=root/package/'data_processed'
        write_panel(frame,dest/f'{product}_{recipe[:12]}')
        # Province folders sit directly under data_processed. National panel files
        # may coexist at its root, without an extra top-level "panels" directory.
        from .common import provinces
        names={p['ma_tinh']:p['ma_tinh']+'_'+p['slug'] for p in provinces()}
        for code,subset in frame.groupby('ma_tinh'):
            if code not in names:
                raise ValueError('Unknown province code in received statistics')
            write_panel(subset,dest/names[code]/'panels'/f'{product}_{recipe[:12]}')
    write_package_docs(root)
    return len(grouped)


def write_panel(frame,stem):
    stem.parent.mkdir(parents=True,exist_ok=True)
    frame.to_csv(stem.with_suffix('.csv'),index=False,encoding='utf-8-sig')
    frame.to_excel(stem.with_suffix('.xlsx'),index=False)
    mapping={c:c if len(c)<=32 else c[:23]+'_'+__import__('hashlib').sha256(c.encode()).hexdigest()[:8]
             for c in frame.columns}
    stata=frame.rename(columns=mapping).copy()
    for col in stata.select_dtypes(include=['object','str']).columns:
        stata[col]=stata[col].fillna('').astype(str)
    stata.to_stata(stem.with_suffix('.dta'),write_index=False,version=118)
    atomic_json(stem.with_suffix('.columns.json'),mapping)


def write_package_docs(root):
    import pandas as pd
    from .common import provinces
    for package in (NTL_PACKAGE, DAY_PACKAGE):
        base = Path(root) / package
        from .layout import PACKAGE_DIRECTORIES
        for name in PACKAGE_DIRECTORIES[package]:
            (base/name).mkdir(parents=True, exist_ok=True)
        if package == DAY_PACKAGE:
            (base/'samples').mkdir(exist_ok=True)
        (base/'README.md').write_text(
            '# Province satellite source products\n\n63-province identity roster; see manifests for boundary source and date. '
            '`raw_data` contains clipped source products / annual composites, not sensor raw scenes. '
            'Source-specific panels are not a harmonized DMSP–VIIRS series. '
            'No land-cover classification or simulated accuracy assessment is included.\n', encoding='utf-8')
        (base/'dashboard'/'README.md').write_text('Reserved package directory; dashboard implementation deferred by user request.\n',encoding='utf-8')
        records = []
        for product, spec in SOURCES.items():
            if product.startswith(('DMSP','VIIRS')) != (package == NTL_PACKAGE):
                continue
            records.append(dict(product=product, collections=';'.join(spec['collections']),
                bands=','.join(spec['bands']), nominal_grid_m=spec['scale'], unit=spec['unit'],
                reference=spec['reference']))
        pd.DataFrame(records).to_csv(base/'metadata'/'sources.csv', index=False, encoding='utf-8-sig')
        pd.DataFrame(records).to_excel(base/'metadata'/'sources.xlsx', index=False)
        (base/'metadata'/'formulas.md').write_text(
            'NDVI=(NIR-RED)/(NIR+RED); NDBI=(SWIR1-NIR)/(SWIR1+NIR); '
            'MNDWI=(GREEN-SWIR1)/(GREEN+SWIR1); '
            'BSI=((SWIR1+RED)-(NIR+BLUE))/((SWIR1+RED)+(NIR+BLUE)).\n'
            'Means/stddev are population area-weighted over pixels valid in all exported bands. '
            'Coverage=valid_area/total_area. SOL=sum of valid pixel values on the documented equal-area source grid; '
            'not comparable across sensor grids without harmonization. Density=SOL/province pixel area km²; '
            'sol_area_integral=sum(value*pixelArea)/1e6 is a separate area-integrated measure. '
            'Growth is NA without a positive immediately preceding period.\n', encoding='utf-8')

        dictionary = [
            dict(name='ma_tinh', label='Mã thống kê tỉnh theo bộ 2024', dtype='String', unit='code', formula='two-character code'),
            dict(name='ten_tinh', label='Tên tỉnh lịch sử', dtype='String', unit='', formula='2024 boundary crosswalk'),
            dict(name='nam', label='Năm lịch', dtype='Numeric', unit='year', formula='period year'),
            dict(name='thang', label='Tháng; 0 cho bảng năm', dtype='Numeric', unit='month', formula='period month or 0'),
            dict(name='nguon_anh', label='Sản phẩm nguồn, chưa harmonize', dtype='String', unit='', formula='source definition in manifest'),
            dict(name='valid_fraction', label='Tỷ lệ diện tích hợp lệ', dtype='Numeric', unit='fraction', formula='valid_area/total_area'),
            dict(name='qa', label='Cờ chất lượng coverage', dtype='String', unit='', formula='NO_VALID_PIXELS / PARTIAL_COVERAGE / OK'),
            dict(name='valid_area', label='Diện tích pixel hợp lệ', dtype='Numeric', unit='m2', formula='sum(pixelArea over common valid mask)'),
            dict(name='total_area', label='Diện tích tỉnh raster hóa', dtype='Numeric', unit='m2', formula='sum(pixelArea over province)'),
        ]
        if package == NTL_PACKAGE:
            dictionary.extend([
                dict(name='sol_ntl', label='Tổng giá trị pixel theo lưới từng nguồn', dtype='Numeric', unit='source value sum', formula='sum(valid values); see METHODS.md'),
                dict(name='mat_do_ntl', label='Mật độ SOL', dtype='Numeric', unit='source sum/km2', formula='sol_ntl/(total_area/1e6)'),
                dict(name='sol_area_integral', label='Tích phân ánh sáng theo diện tích', dtype='Numeric', unit='source value*km2', formula='sum(value*pixelArea)/1e6'),
                dict(name='thay_doi_ntl', label='Tăng trưởng kỳ liền trước', dtype='Numeric', unit='percent', formula='100*(SOL_t/SOL_previous-1); NA for gap or nonpositive previous'),
            ])
        for product, spec in SOURCES.items():
            if product.startswith(('DMSP','VIIRS')) != (package == NTL_PACKAGE):
                continue
            for band in spec['bands']:
                for suffix, label, formula in [('_mean','Trung bình trọng số diện tích','sum(value*area)/valid_area'),
                                                ('_std','Độ lệch chuẩn tổng thể','sqrt(sum(value^2*area)/valid_area-mean^2)'),
                                                ('_w','Tổng có trọng số diện tích','sum(value*area)'),
                                                ('_w2','Tổng bình phương có trọng số','sum(value^2*area)'),
                                                ('_sum','Tổng giá trị pixel','sum(value)')]:
                    dictionary.append(dict(name=band+suffix, product=product, label=label, dtype='Numeric', unit=spec['unit'], formula=formula))
        pd.DataFrame(dictionary).to_csv(base/'metadata'/'codebook.csv', index=False, encoding='utf-8-sig')
        pd.DataFrame(dictionary).to_excel(base/'metadata'/'codebook.xlsx', index=False)
        pd.DataFrame(provinces()).to_csv(base/'metadata'/'province_groups.csv', index=False, encoding='utf-8-sig')
        (base/'code'/'README.md').write_text('Implementation: repository province_pipeline/. Algorithm version, source assets, boundary provenance and grid are retained in local .manifests; keep the matching repository revision for reproduction.\n', encoding='utf-8')
