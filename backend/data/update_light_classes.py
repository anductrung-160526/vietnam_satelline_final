"""Cập nhật riêng phân lớp 0,50/2,00/10,00/20,00 trên ảnh đã kiểm chứng F.

python -m backend.data.update_light_classes --root E:\\SatelliteData --publish
"""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import sqlite3

from backend.api.provenance import available_asset, current_id, observation_info
from backend.core.light_classification import SCHEME, BREAKS
from .build_light_classes import build
from .dataset import file_signature, snapshot_status, provenance_rows, signature_status
from .fractional_area import load_area_model
from .load_demo import backup_database
from .verify_demo import inspect_asset


def update(root, db, publish=False, area_model=None, resume_dir=None):
    root,db=Path(root).resolve(),Path(db).resolve()
    if not db.is_file():raise ValueError('Không tìm thấy database app đã nạp dữ liệu thật.')
    baseline=file_signature(db,True)
    model=area_model or load_area_model(root)
    with sqlite3.connect(db) as connection:
        connection.row_factory=sqlite3.Row
        snapshot=current_id(connection)
        versions=snapshot_status(connection)
        if not snapshot or not versions.get(snapshot,{}).get('available'):
            raise ValueError('Cần snapshot F hiện hành còn đủ CSV đã kiểm chứng; không tự nạp lại dữ liệu.')
        provenance=provenance_rows(connection)
        assets=[dict(r) for r in connection.execute("SELECT * FROM demo_asset WHERE kind='processed' AND source='VIIRS' AND year BETWEEN 2020 AND 2024")]
        signatures=[]
        for row in assets:
            key=(row['province_code'],row['year'],row['month'])
            info=observation_info(connection,*key,versions,provenance)
            asset=available_asset(connection,*key,'processed')
            if info['dataset_id']!=snapshot or not info['consistent'] or not asset or asset['verification_status']!='verified':
                raise ValueError(f'Ảnh {key} chưa khớp snapshot F hiện hành.')
            check=json.loads(connection.execute("SELECT payload FROM demo_asset_check WHERE province_code=? AND year=? AND month=? AND kind='processed'",key).fetchone()[0])
            if check['boundary_sha256']!=model.metadata['sha256']:
                raise ValueError('Ranh giới khác bộ đã kiểm chứng F; không trộn diện tích.')
            signatures.extend((check['source'],check['export']))
    if not assets:raise ValueError('Chưa có ảnh VIIRS đã nạp trong giai đoạn 2020–2024.')
    output=root/'_demo_classification'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output.mkdir(parents=True,exist_ok=False)
    candidate=output/'candidate.db'
    with sqlite3.connect(db) as source,sqlite3.connect(candidate) as target:source.backup(target)
    print('1/3 Tính lại lớp và diện tích giao pixel–tỉnh; giữ nguyên chỉ số và GRDP.',flush=True)
    result=build(root,candidate,area_model=model,reuse_registered=True,scheme='literature',resume_dir=resume_dir)
    print('2/3 Kiểm chứng từng ảnh lớp và cập nhật đăng ký bản xuất.',flush=True)
    with sqlite3.connect(candidate) as connection:
        connection.row_factory=sqlite3.Row
        for i,row in enumerate(assets,1):
            key=(row['province_code'],row['year'],row['month'])
            target=dict(connection.execute("SELECT * FROM demo_asset WHERE province_code=? AND year=? AND month=? AND kind='classes'",key).fetchone())
            checked=inspect_asset(target,model,output/'verified_exports',processed_path=row['path'])
            signatures.extend((checked['source'],checked['export']))
            areas=[r[0] for r in connection.execute('SELECT area_km2 FROM light_class WHERE province_code=? AND year=? AND month=? ORDER BY class_index',key)]
            if not all(math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-8) for a,b in zip(areas,checked['class_areas'])):
                raise ValueError('Diện tích lớp không khớp raster đã kiểm chứng.')
            connection.execute('INSERT OR REPLACE INTO demo_asset_check VALUES(?,?,?,?,?)',(*key,'classes',json.dumps(checked,ensure_ascii=False)))
            if i%100==0:print(f'Đã kiểm chứng {i}/{len(assets)} ảnh lớp',flush=True)
        connection.commit()
        if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database tạm không toàn vẹn.')
        if current_id(connection)!=snapshot:raise ValueError('Snapshot chỉ số bị đổi trong lúc cập nhật phân lớp.')
    report=dict(scheme=SCHEME,breaks=BREAKS,dataset_id=snapshot,classification=result,
                output=str(output),candidate=str(candidate),images=len(assets),published=False,backup=None)
    if publish:
        if file_signature(db,True)['sha256']!=baseline['sha256']:
            raise ValueError('Database app đã đổi trong lúc tính; chưa ghi đè. Dừng server và chạy lại.')
        if any(signature_status(record)!='ready' for record in signatures):
            raise ValueError('Ảnh bức xạ nguồn đã đổi trong lúc tính; chưa xuất bản.')
        report['backup']=backup_database(db)
        with sqlite3.connect(candidate) as source,sqlite3.connect(db) as target:source.backup(target)
        report['published']=True
    print('3/3 '+('Đã cập nhật app, có sao lưu database.' if publish else 'Đã tạo candidate.db; chưa cập nhật app vì thiếu --publish.'),flush=True)
    (output/'classification_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--db',type=Path,default=Path(__file__).with_name('vngis.db'))
    parser.add_argument('--boundaries',type=Path)
    parser.add_argument('--boundary-metadata',type=Path)
    parser.add_argument('--resume-dir',type=Path,help='Tiếp tục thư mục ngưỡng tài liệu đã có method.json, không dùng lượt P50/P90.')
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    model=load_area_model(args.root,args.boundaries,args.boundary_metadata)
    print(json.dumps(update(args.root,args.db,args.publish,model,args.resume_dir),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
