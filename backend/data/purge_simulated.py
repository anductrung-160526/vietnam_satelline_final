"""Xóa các dòng được đánh dấu giả lập, có backup; không xóa dòng thật theo giá trị số."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
from .load_demo import backup_database

MARKERS=('GIA_LAP','SIMULATED','SYNTHETIC')

def fake_predicate(columns):
    tests=[]
    for field in ('source','status','note','economy_source','image_source'):
        if field in columns:
            tests.extend(f"instr(upper(coalesce(\"{field}\",'')),'{marker}')>0" for marker in MARKERS)
    if 'payload' in columns:
        for field in ('source','status','economy_source','image_source'):
            tests.extend(f"(json_valid(payload) AND json_type(payload,'$.{field}')='text' AND instr(upper(coalesce(json_extract(payload,'$.{field}'),'')),'{marker}')>0)" for marker in MARKERS)
    return ' OR '.join(tests) or '0'


def hide_simulated(connection):
    """View tạm của mỗi kết nối chỉ đọc: dữ liệu giả không xuất hiện trước khi chạy purge."""
    tables=connection.execute("SELECT name FROM main.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    for row in tables:
        name=row[0]
        if name in ('spatial_run','demo_asset_check','demo_dataset','demo_provenance','demo_schema_meta'):continue
        if not name.replace('_','').isalnum():continue
        columns=[c[1] for c in connection.execute(f'PRAGMA main.table_info("{name}")')]
        predicate=fake_predicate(columns)
        if {'province_code','year','month'}<=set(columns) and name!='ntl_monthly':
            dependencies=[]
            for parent in ('ntl_annual','ntl_monthly'):
                if not connection.execute("SELECT 1 FROM main.sqlite_master WHERE name=?",(parent,)).fetchone():continue
                parent_cols=[c[1] for c in connection.execute(f'PRAGMA main.table_info("{parent}")')]
                period='p.month' if parent=='ntl_monthly' else '0'
                dependencies.append(f'EXISTS(SELECT 1 FROM main.{parent} p WHERE p.province_code=main."{name}".province_code AND p.year=main."{name}".year AND {period}=main."{name}".month AND ({fake_predicate(parent_cols)}))')
            if dependencies:predicate+=' OR '+' OR '.join(dependencies)
        if predicate!='0':connection.execute(f'CREATE TEMP VIEW "{name}" AS SELECT * FROM main."{name}" WHERE NOT ({predicate})')



def purge(db):
    db=Path(db)
    if not db.is_file():raise FileNotFoundError(db)
    backup=backup_database(db);counts={}
    with sqlite3.connect(db) as connection:
        image_keys=[]
        tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for parent in ('ntl_annual','ntl_monthly'):
            if parent not in tables:continue
            cols=[c[1] for c in connection.execute(f'PRAGMA table_info({parent})')]
            month='month' if parent=='ntl_monthly' else '0'
            image_keys+=connection.execute(f'SELECT province_code,year,{month} FROM {parent} WHERE {fake_predicate(cols)}').fetchall()
        for table in ('demo_result','demo_asset','demo_asset_check','demo_provenance','light_class','light_class_summary','annual_observation_support','monthly_recovery_audit'):
            if table not in tables:continue
            cols={c[1] for c in connection.execute(f'PRAGMA table_info({table})')}
            for code,year,month in image_keys:
                sql=f'DELETE FROM {table} WHERE province_code=? AND year=?';args=[code,year]
                if 'month' in cols:sql+=' AND month=?';args.append(month)
                count=connection.execute(sql,args).rowcount
                if count:counts[table]=counts.get(table,0)+counts.get(table,0)+count
        for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
            if not table.replace('_','').isalnum():continue
            cols=[c[1] for c in connection.execute(f'PRAGMA table_info("{table}")')]
            predicate=fake_predicate(cols)
            count=connection.execute(f'DELETE FROM "{table}" WHERE {predicate}').rowcount
            if count:counts[table]=counts.get(table,0)+count
        if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database không toàn vẹn; rollback.')
    return dict(backup=backup,deleted=counts,total_deleted=sum(counts.values()))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=Path(os.environ.get('VNGIS_DB',Path(__file__).with_name('vngis.db'))))
    args=parser.parse_args();print(json.dumps(purge(args.db),ensure_ascii=False,indent=2))
