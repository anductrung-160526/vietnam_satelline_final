"""Đối chiếu tên trường tài liệu, CSV chuẩn, JSON dictionary và ánh xạ API."""
from pathlib import Path
import csv


def check_fields(directory):
    from .calculate_ntl import NIGHT_DATA_FIELDS,NIGHT_ECONOMY_FIELDS
    from backend.api.demo_view import PROCESSED,FIELD_ALIASES
    dictionary=Path(__file__).resolve().parents[2]/'docs/NIGHT_DATA_DICTIONARY.md'
    names={line.strip('|').split('|')[2].strip().strip('`') for line in dictionary.read_text(encoding='utf-8').splitlines()[4:] if line.startswith('|')}
    required=set(NIGHT_DATA_FIELDS+NIGHT_ECONOMY_FIELDS)
    required|={FIELD_ALIASES.get(r[0],r[0]) for r in PROCESSED}
    if not required<=names:raise ValueError('Dictionary thiếu trường CSV/API: '+', '.join(sorted(required-names)))
    result=[]
    for table,fields in [('night_data',NIGHT_DATA_FIELDS),('night_economy',NIGHT_ECONOMY_FIELDS)]:
        with (Path(directory)/(table+'.csv')).open(encoding='utf-8-sig',newline='') as stream:
            actual=csv.DictReader(stream).fieldnames or []
        if not set(fields)<=set(actual):raise ValueError(f'{table} thiếu trường chuẩn CSV.')
        for field in fields:
            sql=next((k for k,v in FIELD_ALIASES.items() if v==field),field)
            note='demo_result JSON giữ tên chuẩn; cột SQL cũ được ánh xạ khi hiển thị.'
            if field=='tnl':sql='sol_raw';note='Chỉ bằng sol_raw trên cùng ảnh/mask/mốc; không gộp TNL theo thời gian với SOL.'
            if field in ('tnl_ma3','tnl_mom_growth_pct'):sql='demo_result JSON';note='Không thay bằng sol_ma3 hoặc sol_change_mom_pct vì khác cửa sổ.'
            if field in ('avg_rad','cf_cvg'):sql='demo_asset';note='CSV tính lại là tham chiếu băng đầu vào đã lọc; Raw trên app là ảnh raw đã đăng ký, ghi rõ giai đoạn nguồn.'
            result.append(dict(table=table,field=field,sql_or_api_alias=sql,in_dictionary=True,note=note))
    return result
