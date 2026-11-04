"""Nút Export: một ZIP gồm 4 phần đúng yêu cầu của giảng viên.

    (a) ảnh đêm của tỉnh đã chọn   (b) chỉ số ảnh ngày
    (c) chỉ số ảnh đêm             (d) chỉ số kinh tế

Sinh trực tiếp khi người dùng bấm, không tiền tạo file. Phần nào chưa có dữ liệu thì vẫn
có file nhưng chỉ chứa dòng tiêu đề và một ghi chú — người dùng phải thấy rõ là thiếu,
chứ không phải lặng lẽ biến mất.
"""
import csv
import io
import zipfile
from pathlib import Path

from . import store

README = """VNGISDash — dữ liệu trích xuất
Tỉnh: {ten_tinh} (mã {ma_tinh})
Giai đoạn: {nam_tu}-{nam_den}
Ngày trích xuất: {thoi_diem}

Nội dung:
  chi_so_dem.csv       chỉ số ánh sáng ban đêm theo năm
  chi_so_ngay.csv      chỉ số ảnh quang học ban ngày theo năm
  chi_so_kinh_te.csv   dân số, GDP (nguồn: giảng viên cung cấp)
  anh_dem/             ảnh ánh sáng ban đêm (GeoTIFF) của các năm đã chọn

Nguồn ảnh:
  Ảnh đêm  DMSP-OLS 2004-2013 (1 km), VIIRS DNB 2014-2025 (500 m)
  Ảnh ngày Landsat 2004-2014 (30 m), Sentinel-2 2015-2025 (10 m)

Lưu ý phương pháp (bắt buộc đọc trước khi phân tích):
{canh_bao}

Ảnh ngày bản gốc (đầy đủ độ phân giải, ~24 GB mỗi năm) không kèm trong gói này; ảnh
được lưu ở tầng lạnh. Liên hệ nhóm dữ liệu để lấy liên kết tải.
"""


def _csv_bytes(rows, fields, note):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fields), extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    if not rows:
        buffer.write(f'# {note}\n')
    return buffer.getvalue().encode('utf-8-sig')


def build(code, year_from, year_to, include_images=True, timestamp=''):
    """Trả về (tên file, bytes của ZIP). None nếu mã tỉnh không tồn tại."""
    data = store.indices(code, year_from, year_to)
    if data is None:
        return None
    warnings = '\n'.join(f'  - {w}' for w in data['canh_bao']) or '  (không có)'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('DOC_TRUOC.txt', README.format(
            ten_tinh=data['ten_tinh'], ma_tinh=code, nam_tu=year_from, nam_den=year_to,
            thoi_diem=timestamp, canh_bao=warnings).encode('utf-8'))
        archive.writestr('chi_so_dem.csv', _csv_bytes(
            data['dem'], store.NIGHT_FIELDS,
            'Chưa có chỉ số ánh sáng đêm cho tỉnh/giai đoạn này.'))
        archive.writestr('chi_so_ngay.csv', _csv_bytes(
            data['ngay'], store.DAY_FIELDS,
            'Chưa có chỉ số ảnh ngày cho tỉnh/giai đoạn này.'))
        archive.writestr('chi_so_kinh_te.csv', _csv_bytes(
            data['kinh_te'], store.ECONOMY_FIELDS,
            'Chưa có dữ liệu kinh tế (dân số, GDP) — chờ giảng viên cung cấp.'))
        if include_images:
            added = 0
            for entry in store.cog_years('NTL'):
                if not (year_from <= entry['nam'] <= year_to):
                    continue
                path = Path(entry['duong_dan'])
                if path.is_file():
                    archive.write(path, f'anh_dem/{path.name}')
                    added += 1
            if not added:
                archive.writestr('anh_dem/CHUA_CO_ANH.txt',
                                 'Chưa có ảnh đêm dạng COG trong khoảng năm đã chọn.\n'
                                 'Chạy: python3 -m app.data.build_cogs\n'.encode('utf-8'))
    # slug không dấu: tên file đi vào HTTP header, mà header chỉ nhận latin-1.
    name = f"vngisdash_{data['slug']}_{year_from}_{year_to}.zip"
    return name, buffer.getvalue()
