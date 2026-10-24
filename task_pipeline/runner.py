"""Long-lived one-branch runner. No workflow restart after ten jobs."""
import argparse
import json
import logging
import os
import signal
import time
from pathlib import Path
from collections import Counter
from functools import lru_cache
from province_pipeline.common import load_config,atomic_json,audit
from province_pipeline.drive import Drive,FOLDER
from province_pipeline.auth import drive_credentials,ee_credentials
from province_pipeline.boundaries import load_boundaries
from province_pipeline.controller import control_folders,reconcile_existing,work
from province_pipeline.priority import prepare_priority
from province_pipeline.panels import publish
from .scope import relative_root
from .province_image import ExportInterrupted

STOP=False

def request_stop(*_):
    global STOP
    STOP=True
    from . import province_image
    province_image.CANCELLED=True


def resolve(config,drive):
    """Independent writer root per fixed branch; shared pilot/full to reuse verified work."""
    parent=config['drive_root_id']; selection=config['task_scope']
    # Leave budget for data from older pipelines. New branches have six fixed shares,
    # so six controllers never each assume they own the entire 20 GB budget.
    legacy=0
    for f in drive.children(parent):
        if f['name']=='Task123_branches':continue
        legacy+=drive.usage(f['id']) if f['mimeType']==FOLDER else int(f.get('size',0))
    remaining=config['drive_staging_budget_gib']-legacy/1024**3
    margin=config['drive_safety_margin_gib']/6
    share=remaining/6
    if share<=margin:raise RuntimeError('Existing staging data consumes the shared budget; receive to E first')
    root=parent
    for part in relative_root(selection).split('/'):root=drive.folder(root,part)
    c=dict(config,drive_root_id=root,drive_staging_budget_gib=share,drive_safety_margin_gib=margin,
           task_parent_root=parent)
    return c


def run(config,drive,boundaries,metadata,max_seconds=18900,transfer=work,clock=time.monotonic):
    start=clock()
    config=dict(config,_task_deadline=start+max_seconds-300)
    selection=config['task_scope'];folders=control_folders(drive,config['drive_root_id'])
    completed=[];exit_code=0
    # Sequential province completion gives visible first-province outputs early.
    # Scientific job IDs don't include pilot/full or branch range, so full reuses pilot.
    for province in selection['provinces']:
        active=dict(config,province_codes=[province['ma_tinh']])
        def check(job):
            import ee
            from .methods import inventory
            return inventory(job,ee.Geometry(boundaries[job['province']['ma_tinh']]['geometry']))
        while True:
            if STOP or Path('STOP').exists():exit_code=130;break
            if clock()-start>max_seconds-300:exit_code=3;break
            if drive.find(folders['root'],'STOP'):exit_code=130;break
            plan=prepare_priority(active,drive,boundaries,metadata,check)
            state=drive.read_json(folders['root'],'state.json')
            if state['current_stage']=='complete':
                completed.append(province['number']);break
            for job in plan['jobs']:
                if STOP or clock()-start>max_seconds-300:
                    exit_code=130 if STOP else 3;break
                # Single job at a time, one EE request stream per branch/project share.
                try:transfer(active,drive,dict(plan,jobs=[job]),job['province']['group_id'],boundaries)
                except ExportInterrupted:
                    exit_code=3;break
                except RuntimeError:
                    audit('task_transfer_retry_pending',job_id=job['job_id'])
            reconcile_existing(config,drive)
            state=drive.read_json(folders['root'],'state.json')
            publish(config,drive,state,metadata)
            if state.get('waiting_for_space'):
                exit_code=4;break
            if any(j['status']=='BLOCKED_AMBIGUOUS' for j in state['jobs'].values()):
                exit_code=2;break
            # Never spin indefinitely when a direct uploaded report has no visible file.
            if not plan['jobs'] and any(j['status']=='RUNNING' for j in state['jobs'].values()):
                exit_code=2;break
            if exit_code:break
        if exit_code:break
    state=drive.read_json(folders['root'],'state.json',{'jobs':{}})
    publish(config,drive,state,metadata)
    failures=Counter(j['status'] for j in state['jobs'].values() if j['status'] in ('FAILED','BLOCKED_OUTPUT','MISSING_SOURCE','INSUFFICIENT_QUALITY')
                     and j['province']['ma_tinh'] in config['province_codes'])
    summary=dict(branch=selection['branch'],mode=selection['mode'],project=config['project'],
        requested_provinces=[p['number'] for p in selection['provinces']],completed_provinces=completed,
        status='complete_with_gaps' if exit_code==0 and failures else 'complete' if exit_code==0 else 'paused',
        exit_code=exit_code,issues=dict(failures),drive_root_id=config['drive_root_id'])
    atomic_json('.province-local/panels/branch_progress.json',summary)
    drive.write_json(folders['root'],'branch_progress.json',summary)
    audit('branch_progress',**summary)
    return exit_code


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',default='.province-local/config.json');parser.add_argument('--max-seconds',type=int,default=18900)
    args=parser.parse_args();c=load_config(args.config,live=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    signal.signal(signal.SIGTERM,request_stop);signal.signal(signal.SIGINT,request_stop)
    drive=Drive(drive_credentials())
    # Scoped folders are never renamed by this runner; cache their ID lookups within
    # a run, not data/version checks. Content and receipt checks stay live.
    drive.folder=lru_cache(maxsize=4096)(drive.folder)
    c=resolve(c,drive);atomic_json('.province-local/resolved-config.json',c)
    boundaries,metadata=load_boundaries(c)
    from province_pipeline.earth_engine import initialize
    initialize(c,ee_credentials())
    from province_pipeline.projection import probe_download_projection
    probe_download_projection(c)
    raise SystemExit(run(c,drive,boundaries,metadata,args.max_seconds))

if __name__=='__main__':main()
