"""Kiểm kê database đang dùng, không thay đổi dữ liệu."""
import sqlite3
from pathlib import Path
from .purge_simulated import hide_simulated

TABLES=('province','ntl_annual','ntl_monthly','economy','economy_prices','demo_asset','light_class','light_class_summary',
        'demo_result','demo_dataset','demo_provenance','demo_asset_check','spatial_run','cog_image')


def inspect_database(db):
    path=Path(db).resolve()
    result=dict(database=str(path),exists=path.is_file(),tables={})
    if not path.is_file():return result
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as connection:
        connection.row_factory=sqlite3.Row
        result['schema_version']=connection.execute('PRAGMA user_version').fetchone()[0]
        names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        hide_simulated(connection)
        for table in TABLES:
            result['tables'][table]=dict(exists=table in names,rows=connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] if table in names else 0)
        if 'economy_prices' in names:
            result['grdp_by_price']=[dict(r) for r in connection.execute('SELECT price_basis,COUNT(grdp) AS grdp_values,COUNT(population) AS population_values,MIN(year) AS year_start,MAX(year) AS year_end FROM economy_prices GROUP BY price_basis')]
        if 'demo_schema_meta' in names:
            row=connection.execute("SELECT value FROM demo_schema_meta WHERE key='current_dataset'").fetchone()
            result['dataset_id']=row[0] if row else None
        result['missing_demo_components']=[table for table in ('economy_prices','demo_asset','light_class','spatial_run') if result['tables'][table]['rows']==0]
    return result
