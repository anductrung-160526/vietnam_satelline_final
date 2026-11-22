"""Trạng thái snapshot/file nguồn, chỉ đọc SQLite và stat; không tính raster trong API."""
import json
from pathlib import Path

from backend.data.dataset import signature_status,snapshot_status,provenance_rows


def has_table(connection,name):
    return connection.execute('SELECT 1 FROM sqlite_master WHERE name=?',(name,)).fetchone() is not None


def current_id(connection):
    if not has_table(connection,'demo_schema_meta'):return None
    row=connection.execute("SELECT value FROM demo_schema_meta WHERE key='current_dataset'").fetchone()
    return row[0] if row else None


def available_asset(connection,code,year,month,kind):
    if not has_table(connection,'demo_asset'):return None
    row=connection.execute('SELECT * FROM demo_asset WHERE province_code=? AND year=? AND month=? AND kind=?',(code,year,month,kind)).fetchone()
    if not row:return None
    item=dict(row);record=None
    if has_table(connection,'demo_asset_check'):
        found=connection.execute('SELECT payload FROM demo_asset_check WHERE province_code=? AND year=? AND month=? AND kind=?',(code,year,month,kind)).fetchone()
        if found:record=json.loads(found['payload'])
    if record:
        state=signature_status(record['source'])
        if str(Path(item['path']).resolve())!=record['source']['path']:state='changed_registration'
        export_state=signature_status(record['export'])
        ready=state=='ready' and export_state=='ready'
        reason='' if ready else ('Ảnh nguồn không còn ở đường dẫn đã đăng ký.' if state=='missing' else 'Ảnh nguồn/bản xuất đã đổi hoặc mất; cần kiểm chứng lại.')
        item.update(available=ready,file_status=state,verification_status='verified' if ready else 'stale',
                    export_path=record['export']['path'],source_sha256=record['source']['sha256'],
                    export_sha256=record['export']['sha256'],mask_rule=record['mask_rule'],reason=reason)
    else:
        ready=Path(item['path']).is_file()
        item.update(available=ready,file_status='ready' if ready else 'missing',verification_status='unverified',
                    export_path=item['path'],source_sha256=None,export_sha256=None,mask_rule=None,
                    reason='Chưa kiểm chứng xuất ảnh theo tỉnh.' if ready else 'Ảnh nguồn không còn ở đường dẫn đã đăng ký.')
    return item


def observation_info(connection,code,year,month,versions=None,rows=None):
    versions=versions if versions is not None else snapshot_status(connection)
    rows=rows if rows is not None else provenance_rows(connection)
    table='ntl_monthly' if month else 'ntl_annual'
    row=rows.get((code,year,month,table,''))
    item=available_asset(connection,code,year,month,'processed')
    dataset=versions.get(row['dataset_id'],{}) if row else {}
    reason=''
    if row and row['source_path'] and (not item or str(Path(item['path']).resolve())!=row['source_path']):
        reason='Ảnh đăng ký khác nguồn dùng cho snapshot chỉ số.'
    elif item and not item['available']:reason=item['reason']
    elif row and not dataset.get('available'):reason='CSV của snapshot đã mất hoặc đổi; cần kiểm chứng lại.'
    return dict(dataset_id=row['dataset_id'] if row else None,stats_version=dataset.get('stats_version'),
                dataset_available=dataset.get('available') if row else None,
                consistent=not reason,reason=reason,
                source_path=row['source_path'] if row else (item or {}).get('path'),
                source_sha256=(item or {}).get('source_sha256'),
                verification_status=(item or {}).get('verification_status','unverified'))
