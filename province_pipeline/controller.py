"""Single-writer admission controller; workers never edit the shared state document.

Run only under the supplied workflow-wide concurrency group. Drive JSON writes are
NOT distributed locks. Running an additional controller outside that workflow is unsupported.
"""
import copy
import uuid
from datetime import datetime, timezone
from .common import audit, digest
from .drive import FOLDER
from .layout import LAYOUT_VERSION

ACTIVE = {'RESERVED', 'SUBMITTING', 'RUNNING', 'BLOCKED_AMBIGUOUS'}


def control_folders(drive, root):
    control = drive.folder(root, '_control')
    return {name: drive.folder(control, name) for name in ('reports', 'receipts', 'manifests')} | {'root': control}


def admit(config, state, candidates, used, free):
    """Pure, global admission. Outstanding exports reserve their entire byte upper bound."""
    budget = int(config['drive_staging_budget_gib'] * 1024**3)
    margin = int(config['drive_safety_margin_gib'] * 1024**3)
    outstanding = [j for j in state['jobs'].values() if j['status'] in ACTIVE]
    reserved = sum(j['reserved_bytes'] for j in outstanding)
    occupancy = used + reserved
    waiting = state.get('waiting_for_space', False)
    if waiting and occupancy > budget * config['low_watermark']:
        return []
    state['waiting_for_space'] = False
    slots = max(0, config['max_active_exports'] - len(outstanding))
    selected = []
    blocked_for_space = False
    if not slots:
        return selected
    if occupancy >= budget * config['high_watermark'] or reserved + margin >= free:
        state['waiting_for_space'] = True
        return selected
    for job in candidates:
        if not slots:
            break
        if job['job_id'] in state['jobs']:
            continue
        size = job['reserved_bytes']
        if (occupancy + size > budget * config['high_watermark'] or
                occupancy + size + margin > budget or reserved + size + margin > free):
            blocked_for_space = True
            continue
        selected.append(copy.deepcopy(job))
        occupancy += size
        reserved += size
        slots -= 1
        if not slots:
            break
    state['waiting_for_space'] = blocked_for_space and not selected
    return selected


def job_output_files(drive,job):
    files=list(drive.children(job['folder_id']))
    if job.get('layout_version',1) >= 2:
        extension='.tif' if job['kind']=='image' else '.csv'
        files=[f for f in files if f['name']==job['prefix']+extension]
    return files


def _remote_manifest(drive, job):
    files = job_output_files(drive,job)
    extension = '.tif' if job['kind'] == 'image' else '.csv'
    if not files:
        return None  # Drive listing can lag after EE reports completion.
    if len(files) != 1:
        raise RuntimeError('Expected exactly one output matching this job; inspect duplicate filenames')
    f = files[0]
    if f['mimeType'] == FOLDER or not f['name'].startswith(job['prefix']) or not f['name'].endswith(extension):
        raise RuntimeError('Unexpected output file in unique export folder')
    if not f.get('md5Checksum') or not int(f.get('size', 0)):
        raise RuntimeError('Output missing checksum/size')
    if int(f['size']) > job['reserved_bytes']:
        raise RuntimeError('Output exceeded reservation; review byte bound')
    return dict(schema_version=1, job_id=job['job_id'], job=job, files=[dict(
        f, local_relative_path=job['local_directory']+'/'+f['name'])])


def report_name(job):
    if job.get('export_backend') == 'direct':
        return job['job_id']+'-a'+str(job.get('attempt',1))+'.json'
    return job['job_id']+'.json'


def reconcile(drive, folders, state, tasks):
    by_description = {}
    for task in tasks:
        by_description.setdefault(task.get('description'), []).append(task)
    for job in state['jobs'].values():
        if job['status'] in ('ACKED', 'DELETED_REMOTE', 'FAILED', 'BLOCKED_OUTPUT', 'MIGRATING'):
            continue
        if job['status'] == 'REMOTE_READY':
            receipt = drive.read_json(folders['receipts'], job['job_id']+'.json')
            if receipt:
                manifest = drive.read_json(folders['manifests'], job['job_id']+'.json')
                expected = {f['id'] for f in manifest['files']}
                received = {f['id'] for f in receipt.get('files', []) if f.get('verified')}
                if receipt.get('job_id') != job['job_id'] or expected != received:
                    raise RuntimeError('Malformed receipt')
                if receipt.get('remote_deleted'):
                    job['status'] = 'DELETED_REMOTE'
                # Keep REMOTE_READY until deletion so the receiver can retry a failed cleanup.
            continue
        report = drive.read_json(folders['reports'], report_name(job))
        if job.get('export_backend') == 'direct':
            if report:
                if report.get('status') == 'UPLOADED':
                    try:
                        manifest = _remote_manifest(drive, job)
                        if manifest:
                            output=manifest['files'][0]
                            if output['id'] != report.get('file_id') or output['md5Checksum'] != report.get('md5Checksum'):
                                raise RuntimeError('Direct upload report does not match Drive output')
                            drive.write_json(folders['manifests'],job['job_id']+'.json',manifest)
                            job['status']='REMOTE_READY'
                            if job.get('pipeline_version') == 2 and job['kind'] == 'table':
                                record = report.get('statistics')
                                if not record or record.get('job_id') != job['job_id']:
                                    raise RuntimeError('Missing verified statistics report')
                                state.setdefault('statistics', {})[job['job_id']] = record
                        else:
                            job['status']='RUNNING'  # Wait for Drive visibility, never upload twice.
                    except RuntimeError as error:
                        job.update(status='BLOCKED_OUTPUT',error=str(error))
                else:
                    # No asynchronous EE task survives this direct worker. Under workflow-wide
                    # serialization, a new controller runs only after the old worker ended.
                    files=job_output_files(drive,job)
                    if files:
                        job.update(status='BLOCKED_OUTPUT',error='Unconfirmed upload exists; inspect checksum before retry')
                    elif job.get('attempt',1) < job.get('quality',{}).get('max_transfer_attempts',4):
                        job.update(status='RESERVED',attempt=job.get('attempt',1)+1)
                    else:
                        job.update(status='FAILED',error='Direct transfer failed after four attempts; inspect reports')
            continue
        matches = by_description.get('province_'+job['job_id'], [])
        if len(matches) > 1:
            raise RuntimeError('Duplicate EE tasks: stop and reconcile explicitly')
        if matches:
            task = matches[0]
            job['task_id'] = task['id']
            job['operation'] = task.get('name')
            status = task['state']
            if status == 'COMPLETED':
                try:
                    manifest = _remote_manifest(drive, job)
                    if manifest:
                        drive.write_json(folders['manifests'], job['job_id']+'.json', manifest)
                        job['status'] = 'REMOTE_READY'
                    else:
                        job['status'] = 'RUNNING'
                except RuntimeError as error:
                    job.update(status='BLOCKED_OUTPUT', error=str(error))
            elif status in ('FAILED', 'CANCELLED'):
                job.update(status='FAILED', error=task.get('error_message', status))
            else:
                job['status'] = 'RUNNING'
        elif report:
            # Submission may have succeeded. Never release its reservation or blindly resubmit.
            job.update(status='BLOCKED_AMBIGUOUS', error='Submission intent exists but no task visible; inspect EE operations')
        # No intent/report: worker did not attempt submission. RESERVED can be dispatched again.


def prepare(config, drive, candidates, inventory_callback, tasks):
    root = config['drive_root_id']
    folders = control_folders(drive, root)
    state = drive.read_json(folders['root'], 'state.json', {'schema_version': 1, 'jobs': {}, 'inventory': {}, 'cursor': 0})
    if any(j['status']=='MIGRATING' for j in state['jobs'].values()):
        raise RuntimeError('Finish organize_only layout migration before running exports')
    reconcile(drive, folders, state, tasks)
    if state.get('layout_version',1)<LAYOUT_VERSION:
        from .layout import ensure_drive_packages
        ensure_drive_packages(drive,root)
        state['layout_version']=LAYOUT_VERSION
    # Pending legacy jobs with no output can adopt canonical folders without moving data.
    from .layout import canonical_job, ensure_output_folder
    for job in state['jobs'].values():
        if (job['status']=='RESERVED' and job.get('export_backend')=='direct'
                and job.get('layout_version',1)<LAYOUT_VERSION and not job_output_files(drive,job)):
            updated=canonical_job(job)
            folder_id,folder_name=ensure_output_folder(drive,root,updated)
            job.update(updated,folder_id=folder_id,folder_name=folder_name)
    plan = []
    if not config.get('pause', True):
        # Existing RESERVED entries have never had a persisted submit intent.
        own = {'province_'+jid for jid in state['jobs']}
        external = sum(t.get('state') in ('READY','RUNNING') and t.get('description') not in own for t in tasks)
        capacity = max(0, config['max_active_exports']-external)
        inflight = sum(j['status'] in ACTIVE and j['status'] != 'RESERVED' for j in state['jobs'].values())
        pending = [j for j in state['jobs'].values() if j['status'] == 'RESERVED']
        plan.extend(pending[:max(0, capacity-inflight)])
        used, free = drive.usage(root), drive.account_free()
        candidates = list(candidates)
        cursor = state.get('cursor', 0)
        candidates.sort(key=lambda j: ((j['province']['group_id']-cursor) % 10, j['job_id']))
        def eligible():
            checks = 0
            for job in candidates:
                if job['job_id'] in state['jobs']:
                    continue
                ikey = digest([job['province']['ma_tinh'], job['product'], job['period'], job['recipe_hash']])
                if ikey not in state['inventory']:
                    # Bound new live catalog queries per cycle; continue in later scheduled runs.
                    if checks >= config.get('max_inventory_checks_per_cycle', 20):
                        return
                    state['inventory'][ikey] = inventory_callback(job)
                    checks += 1
                record = state['inventory'][ikey]
                if record['status'] != 'AVAILABLE':
                    continue
                job['inventory'] = record
                yield job
        new = admit(dict(config, max_active_exports=capacity), state, eligible(), used, free)
        for job in new:
            if job.get('layout_version',1)>=2:
                if job.get('export_backend')!='direct':
                    raise ValueError('Canonical shared folders require export_backend=direct')
                from .layout import ensure_output_folder
                folder_id,folder_name=ensure_output_folder(drive,root,job)
            else:
                # Existing legacy jobs stay readable until explicitly organized.
                p=job['province']
                parent=drive.folder(root,f"{p['ma_tinh']}_{p['slug']}")
                for part in job['local_directory'].split('/'):
                    parent=drive.folder(parent,part)
                folder_name=f"{p['ma_tinh']}_{p['slug']}_{job['job_id']}"
                folder_id=drive.folder(parent,folder_name)
                drive.assert_unique_folder_name(folder_name,folder_id)
            job.update(folder_name=folder_name,folder_id=folder_id,request_id=str(uuid.uuid4()),attempt=1,status='RESERVED')
            state['jobs'][job['job_id']] = job
            plan.append(job)
        state['cursor'] = (cursor+1) % 10
        audit('admission', used=used, free=free, new=len(new), waiting=state.get('waiting_for_space'))
    state['updated_at'] = datetime.now(timezone.utc).isoformat()
    drive.write_json(folders['root'], 'state.json', state)
    # State/reservations are persisted BEFORE workers get the plan.
    return dict(root=root, folders=folders, jobs=plan, config_hash=digest(config))


def work(config, drive, plan, group_id, boundaries):
    from .earth_engine import build_export, submit_with_request_id
    if plan['config_hash'] != digest(config) or config.get('pause', True):
        raise RuntimeError('Plan/config mismatch or paused')
    failures = []
    for job in plan['jobs']:
        if job['province']['group_id'] != group_id:
            continue
        name = report_name(job)
        if drive.read_json(plan['folders']['reports'], name):
            # The controller, not a second worker, resolves ambiguous submissions.
            continue
        folder = drive.metadata(job['folder_id'])
        if folder['name'] != job['folder_name'] or folder['mimeType'] != FOLDER:
            raise RuntimeError('Export destination changed')
        if job.get('export_backend') == 'direct':
            from .direct_export import transfer
            drive.write_json(plan['folders']['reports'],name,dict(job_id=job['job_id'],status='TRANSFERRING'))
            try:
                output=transfer(config,drive,job,boundaries[job['province']['ma_tinh']])
                drive.write_json(plan['folders']['reports'],name,dict(job_id=job['job_id'],status='UPLOADED',**output))
            except Exception as error:
                # Keep original error type only; no signed URL or token is persisted in reports.
                drive.write_json(plan['folders']['reports'],name,dict(job_id=job['job_id'],status='FAILED',error_type=type(error).__name__))
                failures.append(job['job_id'])
            continue
        drive.assert_unique_folder_name(job['folder_name'], job['folder_id'])
        task = build_export(config, job, boundaries[job['province']['ma_tinh']])
        report = dict(job_id=job['job_id'], status='SUBMITTING', request_id=job['request_id'])
        drive.write_json(plan['folders']['reports'], name, report)
        try:
            operation = submit_with_request_id(task, job['request_id'])
            drive.write_json(plan['folders']['reports'], name, dict(report, status='SUBMITTED', operation=operation))
            audit('submitted', job_id=job['job_id'], group_id=group_id, operation=operation)
        except Exception:
            # Keep persisted SUBMITTING intent and byte reservation even on unknown outcome.
            audit('submission_uncertain', job_id=job['job_id'], group_id=group_id)
            raise

    if failures:
        raise RuntimeError(f'{len(failures)} direct transfers failed; bounded retry on next run')


def reconcile_existing(config,drive):
    """Finalize worker reports without creating/reserving/submitting new data jobs.

    Same single-writer workflow concurrency contract as prepare/organize. A missing
    state is an error, not an excuse to replace a real state with an empty document.
    """
    from collections import Counter
    if config.get('export_backend','direct')!='direct':
        raise ValueError('reconcile-only currently supports direct transfers only')
    folders=control_folders(drive,config['drive_root_id'])
    state=drive.read_json(folders['root'],'state.json')
    if state is None:
        raise RuntimeError('No pipeline state found; verify Drive root before reconciliation')
    if any(j['status']=='MIGRATING' for j in state['jobs'].values()):
        raise RuntimeError('Finish organize_only migration before reconciliation')
    reconcile(drive,folders,state,[])
    state['updated_at']=datetime.now(timezone.utc).isoformat()
    drive.write_json(folders['root'],'state.json',state)
    counts=dict(Counter(j['status'] for j in state['jobs'].values()))
    audit('reconciliation_complete',status_counts=counts,ready_jobs=counts.get('REMOTE_READY',0),new_jobs=0)
    return counts
