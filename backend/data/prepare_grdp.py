"""Chuẩn hóa hai sheet GRDP, giữ nguyên số gốc và xuất các cờ cần đối chiếu."""
import csv
import hashlib
import json
import math
import unicodedata
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / 'core/ranh_gioi/config/danh_muc_tinh.json'


def normalized_name(text):
    text = unicodedata.normalize('NFD', text.lower().replace('đ', 'd'))
    return ''.join(c for c in text if not unicodedata.combining(c) and c.isalnum())


def provinces():
    rows = json.loads(CATALOG.read_text(encoding='utf-8'))
    if len(rows) != 63 or len({r['ma_tinh'] for r in rows}) != 63:
        raise ValueError('Danh mục phải có đúng 63 mã tỉnh duy nhất.')
    return rows


def write_csv(path, rows, fields):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def prepare_grdp(path, output):
    """Không nội suy N/a, không sửa giá trị nghi ngờ và không gộp hai cơ sở giá."""
    import openpyxl
    path, output = Path(path), Path(output)
    lookup = {normalized_name(r['ten_tinh']): r for r in provinces()}
    lookup[normalized_name('TP.Hồ Chí Minh')] = next(r for r in provinces() if r['ma_tinh'] == '79')
    workbook = openpyxl.load_workbook(path, data_only=True)
    formula_book = openpyxl.load_workbook(path, data_only=False)
    rows, issues = [], []
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    for sheet_name, basis, start_col in [('GRDP_So Sánh', 'so_sanh', 3),
                                        ('GRDP_Hiện hành', 'hien_hanh', 2)]:
        sheet = workbook[sheet_name]
        years = []
        for col in range(start_col, sheet.max_column + 1):
            header = str(sheet.cell(3, col).value)
            import re
            match = re.search(r'20\d{2}', header)
            if not match:
                raise ValueError(f'Không đọc được năm: {sheet_name}, cột {col}')
            years.append((col, int(match[0]), 'sơ bộ' in header.lower()))
        if len({y for _, y, _ in years}) != len(years):
            raise ValueError('Năm bị lặp trong sheet GRDP.')
        groups = {}
        for cells in sheet.iter_rows(min_row=4):
            name = cells[0].value
            if name is None:
                continue
            if normalized_name(str(name)) not in lookup:
                raise ValueError(f'Tên tỉnh chưa ánh xạ chính xác: {name}')
            province = lookup[normalized_name(str(name))]
            groups.setdefault(province['ma_tinh'], []).append(cells)
            if basis == 'so_sanh' and cells[1].value != 'Tổng số':
                continue
            for col, year, provisional in years:
                cell = cells[col-1]
                original = cell.value
                valid = (isinstance(original, (int, float)) and not isinstance(original, bool)
                         and math.isfinite(original) and original > 0)
                formula = formula_book[sheet_name][cell.coordinate]
                if formula.data_type == 'f':
                    raise ValueError(f'Có công thức cần xác minh cache Excel: {sheet_name}!{cell.coordinate}')
                row = dict(province_code=province['ma_tinh'], province_name=province['ten_tinh'],
                           year=year, grdp=original if valid else '', grdp_price_basis=basis,
                           price_base_year=2010 if basis == 'so_sanh' else '', unit='ty_vnd',
                           is_provisional=int(provisional), source_sheet=sheet_name,
                           source_cell=cell.coordinate, source=str(sheet.cell(2, 1).value).strip(),
                           source_sha256=source_hash, quality_flags='')
                rows.append(row)
                if not valid:
                    issues.append(dict(province_code=row['province_code'], year=year,
                                       grdp_price_basis=basis, check='missing_value',
                                       source_cell=cell.coordinate, detail=f'Ô nguồn: {original!r}; giữ trống.'))
                if basis == 'so_sanh':
                    sectors = [r for r in sheet.iter_rows(min_row=4)
                               if r[0].value == name and r[1].value != 'Tổng số']
                    if len(sectors) != 4:
                        raise ValueError(f'{name}: cần 4 thành phần GRDP để đối chiếu.')
                    total = sum(float(r[col-1].value) for r in sectors)
                    if valid and abs(original-total) > max(1, original*.001):
                        issues.append(dict(province_code=row['province_code'], year=year,
                                           grdp_price_basis=basis, check='sector_sum_mismatch',
                                           source_cell=cell.coordinate,
                                           detail=f'Tổng={original}; tổng thành phần={total}; không tự sửa.'))
        if set(groups) != {p['ma_tinh'] for p in provinces()}:
            raise ValueError(f'{sheet_name}: không đủ đúng 63 tỉnh.')
    workbook.close()
    formula_book.close()
    by_key = {(r['province_code'], r['year'], r['grdp_price_basis']): r for r in rows}
    if len(by_key) != len(rows):
        raise ValueError('Trùng khóa tỉnh–năm–cơ sở giá.')
    for row in rows:
        previous = by_key.get((row['province_code'], row['year']-1, row['grdp_price_basis']))
        if previous and row['grdp'] != '' and previous['grdp'] != '':
            growth = 100*(row['grdp']/previous['grdp']-1)
            if growth < -10 or growth > 30:
                issues.append(dict(province_code=row['province_code'], year=row['year'],
                                   grdp_price_basis=row['grdp_price_basis'], check='growth_review',
                                   source_cell=row['source_cell'],
                                   detail=f'Tăng trưởng {growth:.2f}%; chỉ là cờ rà soát, chưa kết luận sai.'))
        row['quality_flags'] = ';'.join(sorted({i['check'] for i in issues
                                               if (i['province_code'], i['year'], i['grdp_price_basis']) ==
                                               (row['province_code'], row['year'], row['grdp_price_basis'])}))
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output/'grdp_all_prices.csv', sorted(rows, key=lambda r: (r['province_code'], r['year'], r['grdp_price_basis'])), list(rows[0]))
    for basis in ('so_sanh', 'hien_hanh'):
        write_csv(output/f'economy_{basis}.csv', [r for r in rows if r['grdp_price_basis'] == basis], list(rows[0]))
    write_csv(output/'grdp_checks.csv', issues,
              ['province_code', 'year', 'grdp_price_basis', 'check', 'source_cell', 'detail'])
    # Chưa ghép hai loại giá vào calculate_ntl cùng lúc: bộ đọc hiện dùng khóa tỉnh-năm.
    return {'rows': len(rows), 'valid_values': sum(r['grdp'] != '' for r in rows),
            'missing_values': sum(r['grdp'] == '' for r in rows), 'checks': len(issues),
            'years': sorted({r['year'] for r in rows}), 'provinces': 63, 'sha256': source_hash}
