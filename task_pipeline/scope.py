import json
import re
from pathlib import Path
ROOT=Path(__file__).parent
RANGES=((1,11),(12,22),(23,33),(34,43),(44,53),(54,63))
PROJECT='vngis-ee-cao-bang-hanoi'


def provinces():
    rows=json.loads((ROOT/'provinces.json').read_text(encoding='utf-8'))
    if [r['number'] for r in rows]!=list(range(1,64)) or len({r['ma_tinh'] for r in rows})!=63:
        raise ValueError('Invalid fixed 63-province roster')
    return rows


def scope(mode,path=ROOT/'branch_range.json',ref=None):
    if mode not in ('pilot','full'):
        raise ValueError('mode must be pilot or full')
    r=json.loads(Path(path).read_text())
    if set(r)!= {'start','end'} or any(type(r[k]) is not int for k in ('start','end')) or (r['start'],r['end']) not in RANGES:
        raise ValueError('Unsupported fixed province range')
    name=f"vngis-tinh-{r['start']:03}-{r['end']:03}"
    if ref is not None and ref!=name:
        raise ValueError('Branch name does not match fixed branch_range.json')
    rows=[p for p in provinces() if r['start']<=p['number']<=r['end']]
    return dict(**r,branch=name,mode=mode,provinces=rows[:1] if mode=='pilot' else rows)


def configure(base,selection):
    from province_pipeline.profiles import apply_profile
    if base.get('project')!=PROJECT:
        raise ValueError('Keep existing project vngis-ee-cao-bang-hanoi; config project must match')
    c=apply_profile(base,'full_2004_2025','notebook_tasks')
    c.update(algorithm_version='v004tasks',crs='EPSG:4326',pause=False,
             run_profile=f"task123_{selection['start']:03}_{selection['end']:03}_{selection['mode']}",
             province_codes=[p['ma_tinh'] for p in selection['provinces']],task_scope=selection)
    c['quality']['lit_threshold_viirs']=1.5
    return c


def relative_root(selection):
    return f"Task123_branches/{selection['start']:03}_{selection['end']:03}"
