"""Mã snapshot theo nội dung CSV, schema cộng thêm và kiểm tra file nguồn còn hiệu lực."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

DEMO_SCHEMA_VERSION = 2  # B–E là schema cộng thêm v1 chưa ghi phiên bản; F thêm provenance/check.
TABLES = ('ntl_annual','ntl_monthly','ntl_panel','ntl_overlap_2013','night_data','night_economy',
          'calculation_models','economy_validation')


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def file_signature(path, digest=False):
    path=Path(path).resolve();stat=path.stat()
    result=dict(path=str(path),size=stat.st_size,mtime_ns=stat.st_mtime_ns)
    if digest:result['sha256']=sha256(path)
    return result


def signature_status(record):
    if not record:return 'unverified'
    path=Path(record['path'])
    try:
        if not path.is_file():return 'missing'
        stat=path.stat()
    except OSError:return 'unreadable'
    return 'ready' if stat.st_size==record['size'] and stat.st_mtime_ns==record['mtime_ns'] else 'changed'


def make_snapshot(directory, stats_version):
    directory=Path(directory).resolve()
    files={}
    for name in TABLES:
        path=directory/(name+'.csv')
        if not path.is_file():continue
        with path.open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream);rows=list(reader)
            if any(k != k.lower() for k in reader.fieldnames or []):
                raise ValueError(f'Tên cột phải là chữ thường: {path}')
        files[name]=dict(file_signature(path,True),rows=len(rows))
    identity={k:dict(sha256=v['sha256'],rows=v['rows']) for k,v in sorted(files.items())}
    dataset_id=hashlib.sha256(json.dumps(dict(stats_version=stats_version,files=identity),sort_keys=True).encode()).hexdigest()
    result=dict(format_version=1,dataset_id=dataset_id,stats_version=stats_version,files=files,
                created_at=datetime.now(timezone.utc).isoformat())
    return result


def write_snapshot(directory, stats_version):
    result=make_snapshot(directory,stats_version)
    path=Path(directory)/'dataset_manifest.json'
    temporary=path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
    return result


def checked_snapshot(directory):
    path=Path(directory)/'dataset_manifest.json'
    if not path.exists():return None  # Luồng CSV cũ vẫn đọc được, nhưng không giả định đã kiểm chứng F.
    result=json.loads(path.read_text(encoding='utf-8'))
    current=make_snapshot(directory,result['stats_version'])
    if current['dataset_id']!=result['dataset_id']:
        raise ValueError('CSV khác dataset_manifest.json; chưa nạp để tránh trộn phiên bản.')
    # Đường dẫn/stat có thể đổi khi di chuyển cùng nội dung; dùng chữ ký hiện tại sau khi kiểm SHA.
    return dict(result,files=current['files'])


def migrate_demo(connection):
    table=connection.execute("SELECT 1 FROM sqlite_master WHERE name='demo_schema_meta'").fetchone()
    found=connection.execute("SELECT value FROM demo_schema_meta WHERE key='version'").fetchone() if table else None
    if found and int(found[0])>DEMO_SCHEMA_VERSION:
        raise ValueError('Database demo có schema mới hơn code; cần cập nhật code trước.')
    from .load_demo import SCHEMA
    connection.executescript(SCHEMA.read_text(encoding='utf-8'))
    connection.execute("INSERT OR REPLACE INTO demo_schema_meta VALUES('version',?)",(str(DEMO_SCHEMA_VERSION),))
    connection.commit()


def register_snapshot(connection,snapshot,directory,manifest):
    """Ghi xuất xứ đúng các dòng CSV đã nạp, không gán dữ liệu cũ ngoài phạm vi sang phiên bản mới."""
    if snapshot is not None:
        connection.execute('INSERT OR REPLACE INTO demo_dataset VALUES(?,?,?)',
                           (snapshot['dataset_id'],str(Path(directory).resolve()),json.dumps(snapshot,ensure_ascii=False)))
        connection.execute("INSERT OR REPLACE INTO demo_schema_meta VALUES('current_dataset',?)",(snapshot['dataset_id'],))
    elif any((Path(directory)/(table+'.csv')).is_file() for table in TABLES):
        connection.execute("DELETE FROM demo_schema_meta WHERE key='current_dataset'")
    sources={(r['province_code'].zfill(2),int(r['year']),int(r['month'])):str(Path(r['path']).resolve()) for r in manifest}
    from .prepare_grdp import provinces
    gid={r['gid_1']:r['ma_tinh'] for r in provinces()}
    entries=[]
    for table in ('night_data','night_economy','ntl_annual','ntl_monthly'):
        path=Path(directory)/(table+'.csv')
        if not path.exists():continue
        with path.open(encoding='utf-8-sig',newline='') as stream:
            for row in csv.DictReader(stream):
                code=row.get('province_code') or gid.get(row.get('gid_1'))
                key=(code.zfill(2),int(row['year']),int(row.get('month') or 0))
                basis=row.get('grdp_price_basis','') if table=='night_economy' else ''
                if snapshot is None:
                    connection.execute('DELETE FROM demo_provenance WHERE province_code=? AND year=? AND month=? AND table_name=? AND price_basis=?',(*key,table,basis))
                else:entries.append((*key,table,basis,snapshot['dataset_id'],sources.get(key)))
    if entries:connection.executemany('INSERT OR REPLACE INTO demo_provenance VALUES(?,?,?,?,?,?,?)',entries)


def snapshot_status(connection):
    exists=connection.execute("SELECT 1 FROM sqlite_master WHERE name='demo_dataset'").fetchone()
    if not exists:return {}
    result={}
    for row in connection.execute('SELECT * FROM demo_dataset'):
        data=json.loads(row['manifest_json'])
        states={name:signature_status(item) for name,item in data['files'].items()}
        result[row['dataset_id']]=dict(dataset_id=row['dataset_id'],stats_version=data['stats_version'],
                                     available=all(s=='ready' for s in states.values()),files=states)
    return result


def provenance_rows(connection):
    exists=connection.execute("SELECT 1 FROM sqlite_master WHERE name='demo_provenance'").fetchone()
    if not exists:return {}
    return {(r['province_code'],r['year'],r['month'],r['table_name'],r['price_basis']):dict(r)
            for r in connection.execute('SELECT * FROM demo_provenance')}
