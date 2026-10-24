"""Bounded, round-robin stage admission; no scientific substitution on missing data."""
from collections import Counter, deque
from datetime import datetime, timezone
import uuid
from .common import audit, digest
TERMINAL = {'REMOTE_READY', 'DELETED_REMOTE', 'ACKED', 'FAILED', 'BLOCKED_OUTPUT',
            'MISSING_SOURCE', 'INSUFFICIENT_QUALITY'}
STAGES = {0: 'night_images', 1: 'indices_csv', 2: 'day_images'}

def fair_jobs(config, boundaries, metadata, priority, cursor):
    from .jobs import generate_v2
    from .common import provinces
    streams = deque()
    for offset in range(10):
        group = (cursor + offset) % 10
        codes = [p['ma_tinh'] for p in provinces() if p['group_id'] == group and p['ma_tinh'] in config['province_codes']]
        if codes:
            streams.append(iter(generate_v2(dict(config, province_codes=codes), boundaries, metadata, priority)))
    while streams:
        stream = streams.popleft()
        try:
            yield next(stream)
            streams.append(stream)
        except StopIteration:
            pass

def inventory_key(job):
    return digest([job['province']['ma_tinh'], job['product'], job['period'], job['recipe_hash'],job['kind'] if job.get('quality',{}).get('processing_mode')=='notebook_tasks' else ''])

def prepare_priority(config, drive, boundaries, metadata, inventory_callback):
    from .controller import control_folders, reconcile, admit
    from .layout import ensure_drive_packages, ensure_output_folder, LAYOUT_VERSION
    from .profiles import in_scope
    folders = control_folders(drive, config['drive_root_id'])
    state = drive.read_json(folders['root'], 'state.json',
                            {'schema_version': 1, 'jobs': {}, 'inventory': {}, 'cursor': 0})
    if any(j['status'] == 'MIGRATING' for j in state['jobs'].values()):
        raise RuntimeError('Finish organize_only before exports')
    if config['quality'].get('processing_mode')=='notebook_tasks':state['receipt_listing_cache']=True
    reconcile(drive, folders, state, [])
    if state.get('layout_version', 1) < LAYOUT_VERSION:
        ensure_drive_packages(drive, config['drive_root_id'])
        state['layout_version'] = LAYOUT_VERSION
    for j in state['jobs'].values():
        if j['status'] == 'RESERVED' and not in_scope(config, j):
            j['status'] = 'DEFERRED'  # only never-submitted reservations
    plan, checks = [], 0
    used, free = drive.usage(config['drive_root_id']), drive.account_free()
    cursor = state.get('cursor', 0)
    stage = None
    if not config.get('pause', True):
        for priority in STAGES:
            unfinished = False
            for candidate in fair_jobs(config, boundaries, metadata, priority, cursor):
                jid = candidate['job_id']
                existing = state['jobs'].get(jid)
                if existing and existing['status'] in TERMINAL:
                    continue
                unfinished = True
                stage = STAGES[priority]
                if existing:
                    if existing['status'] == 'DEFERRED':
                        existing['status'] = 'RESERVED'
                    if existing['status'] == 'RESERVED':
                        plan.append(existing)
                else:
                    key = inventory_key(candidate)
                    if key not in state['inventory']:
                        if checks >= config.get('max_inventory_checks_per_cycle', 20):
                            break
                        state['inventory'][key] = inventory_callback(candidate)
                        checks += 1
                    record = state['inventory'][key]
                    if record['status'] != 'AVAILABLE':
                        candidate.update(status='MISSING_SOURCE' if not record.get('count') else 'INSUFFICIENT_QUALITY', inventory=record)
                        state['jobs'][jid] = candidate
                        continue
                    candidate['inventory'] = record
                    admitted = admit(config, state, [candidate], used, free)
                    if not admitted:
                        break
                    job = admitted[0]
                    folder_id, folder_name = ensure_output_folder(drive, config['drive_root_id'], job)
                    job.update(folder_id=folder_id, folder_name=folder_name, request_id=str(uuid.uuid4()),
                               attempt=1, status='RESERVED')
                    state['jobs'][jid] = job
                    plan.append(job)
                if len(plan) >= config['max_active_exports']:
                    break
            if unfinished:
                break
    state.update(cursor=(cursor+1) % 10, updated_at=datetime.now(timezone.utc).isoformat(),
                 selection={k: config[k] for k in ('run_profile','years','province_codes','algorithm_version')},
                 current_stage=stage or 'complete')
    drive.write_json(folders['root'], 'state.json', state)
    audit('priority_progress', profile=config['run_profile'], stage=state['current_stage'],
          planned=len(plan), inventory_checks=checks, waiting_for_space=state.get('waiting_for_space',False),
          statuses=dict(Counter(j['status'] for j in state['jobs'].values() if in_scope(config,j))))
    return dict(root=config['drive_root_id'], folders=folders, jobs=plan, config_hash=digest(config))
