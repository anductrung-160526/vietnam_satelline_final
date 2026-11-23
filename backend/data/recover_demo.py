"""Phục hồi database đã kiểm P1, không tính lại ảnh hay tạo dữ liệu dân số."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
from .database_status import inspect_database
from .dataset import file_signature,signature_status,snapshot_status
from .load_demo import backup_database
from .build_indices import mo
from .purge_simulated import purge


def recover(root,db,spatial_report=None,publish=False):
    root,db=Path(root).resolve(),Path(db).resolve()
    candidates=[Path(spatial_report).resolve()] if spatial_report else sorted((root/'_demo_spatial').glob('*/spatial_report.json'),reverse=True)
    selected=None
    for path in candidates:
        report=json.loads(path.read_text(encoding='utf-8'))
        if report.get('published'):
            selected=(path,report);break
    if not selected:raise ValueError('Không tìm thấy spatial_report.json đã published. Chỉ định --spatial-report tới lượt P1 đã gửi.')
    report_path,report=selected;source=report_path.parent/'candidate.db'
    if not source.is_relative_to(root) or not source.is_file():raise ValueError('Không tìm thấy candidate.db của lượt P1 trong --root; chưa thay database app.')
    baseline=file_signature(db,True) if db.is_file() else None
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as connection:
        connection.row_factory=sqlite3.Row
        if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database P1 không toàn vẹn.')
        row=connection.execute("SELECT value FROM demo_schema_meta WHERE key='current_dataset'").fetchone()
        if not row or row[0]!=report['dataset_id']:raise ValueError('Snapshot candidate khác báo cáo P1.')
        if not snapshot_status(connection).get(row[0],{}).get('available'):raise ValueError('CSV của snapshot không còn ở vị trí đã kiểm; chưa phục hồi.')
        saved=connection.execute('SELECT payload FROM spatial_run WHERE run_id=?',(report['run_id'],)).fetchone()
        if saved is None:raise ValueError('Candidate không chứa đúng lượt P1.')
        payload=json.loads(saved[0])
        for item in list(payload['files'].values())+payload['source_signatures']:
            if signature_status(item)!='ready':raise ValueError('Ảnh hoặc file P1 đã mất/đổi: '+item['path'])
    output=root/'_demo_recovery'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');output.mkdir(parents=True)
    candidate=output/'candidate.db'
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as original,sqlite3.connect(candidate) as target:original.backup(target)
    migrated=mo(candidate);migrated.close()
    cleanup=purge(candidate)
    status=inspect_database(candidate)
    if status['missing_demo_components']:raise ValueError('Bản phục hồi vẫn thiếu thành phần: '+', '.join(status['missing_demo_components']))
    result=dict(published=False,source_report=str(report_path),source_database=str(source),output=str(output),
                before=inspect_database(db),after=status,removed_simulated=cleanup['deleted'],backup=None,
                note='Dân số vẫn trống nếu chưa có nguồn thật; không nội suy hoặc sinh dữ liệu.')
    if publish:
        if baseline and file_signature(db,True)['sha256']!=baseline['sha256']:raise ValueError('Database đang đổi; dừng server trước khi phục hồi.')
        result['backup']=backup_database(db)
        db.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(candidate) as original,sqlite3.connect(db) as target:original.backup(target)
        result['published']=True;result['after']=inspect_database(db)
    (output/'recovery_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--db',type=Path,default=Path(os.environ.get('VNGIS_DB',Path(__file__).with_name('vngis.db'))))
    parser.add_argument('--spatial-report',type=Path)
    parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    print(json.dumps(recover(args.root,args.db,args.spatial_report,args.publish),ensure_ascii=False,indent=2))
