"""Explicit, resumable organization of pipeline-owned legacy outputs, without deletion.

Only run under the same workflow-wide concurrency group, with exports paused and
Windows receiver stopped. Unknown files/folders and partial uploads are untouched.
"""
from .common import audit
from .layout import canonical_job,ensure_drive_packages,ensure_output_folder,relative_output,LAYOUT_VERSION,version2_directory
from .controller import control_folders,reconcile,job_output_files


def organize(config,drive):
    if not config.get('pause',True):
        raise ValueError('Set pause=true before organize_only; stop Windows receiver during migration')
    root=config['drive_root_id']
    folders=control_folders(drive,root)
    state=drive.read_json(folders['root'],'state.json',{'schema_version':1,'jobs':{},'inventory':{},'cursor':0})
    ensure_drive_packages(drive,root)
    reconcile(drive,folders,state,[])
    changed=0
    skipped=0
    for job in state['jobs'].values():
        if job.get('layout_version',1)>=LAYOUT_VERSION and job['status']!='MIGRATING':
            continue
        if job.get('export_backend')!='direct':
            skipped+=1
            continue
        intent=job.get('layout_migration')
        if not intent:
            if job['status']=='RESERVED' and not job_output_files(drive,job):
                updated=canonical_job(job)
                fid,name=ensure_output_folder(drive,root,updated)
                job.update(updated,folder_id=fid,folder_name=name)
                changed+=1
                drive.write_json(folders['root'],'state.json',state)
                continue
            if job['status']!='REMOTE_READY':
                skipped+=1
                continue
            manifest=drive.read_json(folders['manifests'],job['job_id']+'.json')
            if not manifest or manifest['job_id']!=job['job_id']:
                raise RuntimeError('Completed legacy job is missing its manifest')
            updated=canonical_job(job)
            fid,name=ensure_output_folder(drive,root,updated)
            intent=dict(original_status=job['status'],target_folder_id=fid,target_folder_name=name,
                        files=manifest['files'],legacy_directory=job['local_directory'],
                        target_layout_version=LAYOUT_VERSION,target_directory=updated['local_directory'])
            job.update(status='MIGRATING',layout_migration=intent)
            # Intent is saved BEFORE any file movement. Receiver skips MIGRATING jobs.
            drive.write_json(folders['root'],'state.json',state)
        target_version=intent.get('target_layout_version',2)
        updated=dict(canonical_job(job),layout_version=target_version,
                     local_directory=intent.get('target_directory',version2_directory(job)))
        migrated=[]
        for source in intent['files']:
            if source['name']!=job['prefix']+('.tif' if job['kind']=='image' else '.csv'):
                raise RuntimeError('Manifest filename is not the exact owned job output')
            moved=drive.move_verified(source,intent['target_folder_id'],root)
            migrated.append(dict(moved,local_relative_path=updated['local_directory']+'/'+moved['name'],
                legacy_local_relative_paths=[source['local_relative_path'],*source.get('legacy_local_relative_paths',[])]))
        final=dict(updated,status=intent['original_status'],folder_id=intent['target_folder_id'],
                   folder_name=intent['target_folder_name'])
        final.pop('layout_migration',None)
        manifest=dict(schema_version=2,job_id=job['job_id'],job=final,files=migrated)
        drive.write_json(folders['manifests'],job['job_id']+'.json',manifest)
        job.clear();job.update(final)
        drive.write_json(folders['root'],'state.json',state)
        changed+=1
    state['layout_version']=LAYOUT_VERSION
    drive.write_json(folders['root'],'state.json',state)
    # Finish an older in-flight migration at its original target, then flatten it
    # in a second bounded pass. Never label a year-folder destination as layout 3.
    if any(j.get('layout_version',1)<LAYOUT_VERSION and j['status']=='REMOTE_READY'
           and j.get('export_backend')=='direct' for j in state['jobs'].values()):
        more,skipped=organize(config,drive)
        changed+=more
    audit('layout_organized',changed_jobs=changed,skipped_jobs=skipped,
          deleted_files=0,legacy_empty_folders_preserved=True)
    return changed,skipped


def organize_local(root):
    """Reorganize previously verified local copies, even if their Drive source was deleted."""
    import json
    from pathlib import Path
    from .layout import local_manifest
    from .common import local_path,atomic_json
    from .receiver import validate
    root=Path(root)
    moved=0
    for path in sorted((root/'.manifests').glob('*.json')):
        original=json.loads(path.read_text(encoding='utf-8'))
        manifest=local_manifest(original)
        receipt_path=root/'.receipts'/path.name
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        entries={f['id']:f for f in receipt['files']}
        for f in manifest['files']:
            dest=local_path(root,f['local_relative_path'])
            entry=entries.get(f['id'])
            if not entry or not entry.get('verified'):
                raise ValueError('Local organization requires a verified receipt')
            if not dest.exists():
                legacy=[entry['local_relative_path'],*f.get('legacy_local_relative_paths',[])]
                for relative in legacy:
                    source=local_path(root,relative)
                    if source.is_file():
                        if validate(source,f,manifest['job'])!=entry['sha256']:
                            raise ValueError('Legacy file checksum differs from receipt')
                        dest.parent.mkdir(parents=True,exist_ok=True)
                        source.rename(dest)
                        moved+=1
                        break
            if not dest.is_file() or validate(dest,f,manifest['job'])!=entry['sha256']:
                raise ValueError('Cannot find a verified local file at either layout path')
            entry['local_relative_path']=f['local_relative_path']
        # A crash between rename and these checkpoints is recoverable by finding dest next run.
        atomic_json(path,manifest)
        atomic_json(receipt_path,receipt)
    return moved
