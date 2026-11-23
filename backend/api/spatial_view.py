"""P1 chỉ đọc kết quả offline cùng snapshot F; không xử lý raster trong request."""
import json
from pathlib import Path
from . import store
from .provenance import current_id,has_table,available_asset
from backend.data.dataset import signature_status,snapshot_status


def read_spatial(year_start,year_end):
    with store.connect() as connection:
        connection.execute('BEGIN');snapshot=current_id(connection)
        missing=dict(status='missing',snapshot_id=snapshot,message='Chưa có kết quả Moran được nạp trong database đang mở. Kiểm tra hoặc phục hồi lượt phân tích đã kiểm chứng trước khi tính lại.')
        if not has_table(connection,'spatial_run'):return missing
        rows=connection.execute('SELECT payload FROM spatial_run ORDER BY rowid DESC').fetchall()
        reports=[json.loads(row[0]) for row in rows]
        pairs=sorted({(r['year_start'],r['year_end']) for r in reports})
        missing['available_pairs']=pairs
        # Moran là kết quả riêng từng năm; không bắt buộc lượt lưu phủ hết bộ lọc.
        # Chỉ dùng một lượt cùng snapshot, không ghép số từ các lượt khác nhau.
        requested=set(range(year_start,year_end+1))
        def result_years(report):
            return {r['year'] for r in report['moran']} & requested
        eligible=[r for r in reports if result_years(r)]
        current=[r for r in eligible if r['dataset_id']==snapshot]
        report=max(current or eligible,key=lambda r:len(result_years(r)),default=None)
        if reports:
            missing['message']=f'Chưa có kết quả Moran đã lưu trong khoảng {year_start}–{year_end}.'
        if report is None:return missing
        reason=None
        if report.get('version')!=1:reason='Phiên bản P1 không được code hiện tại hỗ trợ; cần cập nhật code.'
        elif report['dataset_id']!=snapshot:reason='Kết quả P1 thuộc snapshot cũ; cần tính lại trên bộ F hiện tại.'
        elif not snapshot_status(connection).get(snapshot,{}).get('available'):reason='CSV nền đã mất/đổi; cần kiểm chứng lại F và P1.'
        else:
            for record in report['source_signatures']:
                asset=available_asset(connection,record['province_code'],record['year'],0,'processed')
                if signature_status(record)!='ready' or not asset or str(Path(asset['path']).resolve())!=record['path'] or not asset['available']:
                    reason='Ảnh nguồn P1 đã mất/đổi hoặc đăng ký lại; cần kiểm chứng lại.';break
        if reason:return dict(status='stale',snapshot_id=snapshot,message=reason,available_pairs=pairs)
        if any(signature_status(record)!='ready' for record in report['files'].values()):
            return dict(status='stale',snapshot_id=snapshot,message='File kết quả P1 đã mất/đổi; cần tính lại.',available_pairs=pairs)
    years=sorted(result_years(report))
    return dict(report,status='ready',snapshot_id=snapshot,available_pairs=pairs,
                available_years=years,missing_years=sorted(requested-set(years)),
                moran=[r for r in report['moran'] if r['year'] in years])
