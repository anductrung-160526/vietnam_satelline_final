"""Run Task123 on the Windows laptop and commit verified outputs straight to E.

No Drive API, rclone, upload, staging quota or GitHub runner is used here.
"""
import argparse
import json
import logging
import os
import shutil
import signal
import tempfile
from pathlib import Path
from collections import Counter
from province_pipeline.common import atomic_json,local_path,audit
from province_pipeline.receiver import verify_volume,enroll,single_receiver,hashes,validate
from province_pipeline.quality import NoValidPixels
from province_pipeline.jobs import generate_v2
from province_pipeline.panels import build_panels,csv_bytes,write_docs
from .scope import PROJECT,scope,configure,relative_root
from . import province_image

STOP=False


def request_stop(*_):
    global STOP
    STOP=True;province_image.CANCELLED=True


def credentials(key=None):
    import ee
    key=key or os.environ.get('PROVINCE_EE_CREDENTIALS')
    if key:
        from google.oauth2.service_account import Credentials
        return Credentials.from_service_account_file(key,scopes=[
            'https://www.googleapis.com/auth/earthengine','https://www.googleapis.com/auth/cloud-platform'])
    return ee.data.get_persistent_credentials()


def prepare(mode,config_path=None,root=None):
    source=Path(config_path or 'province_pipeline/config/local.json')
    if not source.exists():source=Path('province_pipeline/config/example.json')
    base=json.loads(source.read_text(encoding='utf-8-sig'))
    base['project']=base.get('project') or PROJECT
    selection=scope(mode)
    c=configure(base,selection)
    c.update(execution_backend='local',local_root=root or base.get('local_root') or r'E:\SatelliteData',
        boundary_provider='gadm41',boundary_policy='gadm41_research',
        boundaries='province_pipeline/config/boundaries.geojson',
        boundary_metadata='province_pipeline/config/boundaries.metadata.json')
    if not c.get('volume_marker'):
        c['volume_marker']=enroll(c['local_root'])
    elif not Path(c['local_root']).exists():
        anchor=Path(c['local_root']).absolute().anchor
        verify_volume(dict(c,local_root=anchor))
        Path(c['local_root']).mkdir(parents=True,exist_ok=True)
    disk=verify_volume(c)
    dest=local_path(disk,relative_root(selection));dest.mkdir(parents=True,exist_ok=True)
    atomic_json('.province-local/direct-config.json',c)
    return c,dest


def read_table(path):
    import pandas as pd
    frame=pd.read_csv(path,dtype={k:str for k in ('ma_tinh','period','job_id','crs','algorithm_version','boundary_sha256')})
    # Convert numpy scalars/NaN to JSON-compatible native values/nulls.
    import math
    record=frame.iloc[0].to_dict()
    for key,value in record.items():
        if hasattr(value,'item'):value=value.item()
        if isinstance(value,float) and not math.isfinite(value):value=None
        record[key]=value
    return record


def prior(config,root,job):
    """Recover a locally committed file, or adopt a verified earlier receiver output."""
    jid=job['job_id'];receipt=root/'.local_state'/'receipts'/(jid+'.json')
    if receipt.exists():
        info=json.loads(receipt.read_text(encoding='utf-8'))
        if info['job_id']!=jid:raise ValueError('Local receipt identity mismatch')
        dest=local_path(root,info['relative_path'])
        if dest.exists():
            if validate(dest,info['file'],job)!=info['sha256']:raise ValueError('Local output changed')
            return info
    manifest_path=root/'.manifests'/(jid+'.json');received_path=root/'.receipts'/(jid+'.json')
    if not manifest_path.exists() or not received_path.exists():return None
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    received=json.loads(received_path.read_text(encoding='utf-8'))
    if manifest.get('job_id')!=jid or received.get('volume_marker')!=config['volume_marker']:
        raise ValueError('Previous receiver provenance does not match job/disk')
    for f in manifest['files']:
        if f.get('role')=='preview':continue
        dest=local_path(root,f['local_relative_path'])
        if not dest.exists():continue
        sha=validate(dest,f,job)
        if not any(r.get('verified') and r['id']==f['id'] and r['sha256']==sha for r in received['files']):
            raise ValueError('Previous receiver receipt mismatch')
        return dict(job_id=jid,relative_path=f['local_relative_path'],file=dict(size=f['size'],md5Checksum=f['md5Checksum']),sha256=sha)
    return None


def export(config,root,job,boundary):
    """Build in same-volume scratch, verify, persist receipt, then atomic rename."""
    import ee
    from .methods import composite
    from province_pipeline.direct_export import write_statistics
    from province_pipeline.quality import inspect_raster,NoValidPixels
    verify_volume(config)
    suffix='.tif' if job['kind']=='image' else '.csv'
    relative=job['local_directory']+'/'+job['prefix']+suffix
    dest=local_path(root,relative)
    if dest.exists():raise RuntimeError('Existing output has no valid receipt; refusing overwrite')
    scratch=root/'.work';scratch.mkdir(exist_ok=True)
    geometry=ee.Geometry(boundary['geometry']);image=composite(config,job,geometry)
    with tempfile.TemporaryDirectory(prefix=job['job_id']+'-',dir=scratch) as tmp:
        path=Path(tmp)/(job['prefix']+suffix)
        if job['kind']=='image':
            province_image.download(image,job,path,boundary,config)
            qa=inspect_raster(path,job)
            if not qa['valid_pixel_pct']:raise NoValidPixels('No valid source pixels')
            import rasterio
            with rasterio.open(path,'r+') as ds:
                ds.update_tags(PROJECT=PROJECT,SOURCE=job['product'],PERIOD=job['period'],
                    METHOD_VERSION=job['algorithm_version'],JOB_ID=job['job_id'],
                    VALID_PIXEL_PCT=str(qa['valid_pixel_pct']),QA_FLAGS=';'.join(qa['flags']))
        else:
            write_statistics(image,job,geometry,path,config)
        if path.stat().st_size>job['reserved_bytes']:raise province_image.OutputLimit('Local file exceeds disk reservation')
        md5,sha=hashes(path);file=dict(size=str(path.stat().st_size),md5Checksum=md5)
        validate(path,file,job)
        verify_volume(config)
        receipt=dict(job_id=job['job_id'],relative_path=relative,file=file,sha256=sha)
        # Receipt precedes rename: recovery is safe after a crash between rename/state save.
        atomic_json(root/'.local_state'/'receipts'/(job['job_id']+'.json'),receipt)
        dest.parent.mkdir(parents=True,exist_ok=True)
        path.replace(dest)
        audit('saved_local',job_id=job['job_id'],destination=str(dest),backend='local_e')
        return receipt


def panels(config,root,state,metadata):
    verify_volume(config)
    from province_pipeline.sources import NTL_PACKAGE,DAY_PACKAGE
    index_path=root/'.panels.json'
    previous=json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else {}
    preserve=(previous.get('profile'),previous.get('method_version'),previous.get('backend')) != (
        config['run_profile'],config['algorithm_version'],'local_e')
    for name,rows in build_panels(config,state,metadata).items():
        package=NTL_PACKAGE if name.startswith('night') else DAY_PACKAGE
        dest=local_path(root,package+'/data_processed/'+name)
        dest.parent.mkdir(parents=True,exist_ok=True)
        content=csv_bytes(name,rows)
        if dest.exists() and dest.read_bytes()==content:continue
        if dest.exists() and preserve:
            # Preserve a previous visible snapshot when local state is first adopted.
            old_hash=hashes(dest)[1]
            history=local_path(root,'.panel_history/'+dest.stem+'_'+old_hash+'.csv')
            if not history.exists():
                history.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dest,history)
        part=dest.with_suffix('.csv.part');part.write_bytes(content)
        verify_volume(config);part.replace(dest)
    atomic_json(root/'.panels.json',dict(profile=config['run_profile'],method_version=config['algorithm_version'],quality=config['quality'],backend='local_e'))
    write_docs(root)
    return {name:dict(Counter(r['DATA_STATUS'] for r in rows)) for name,rows in build_panels(config,state,metadata).items()}


def run(config,root,boundaries,metadata,inventory=None,exporter=export):
    """Only EE requests and local filesystem writes. No remote state/sync/deletion."""
    if inventory is None:
        def inventory(job):
            import ee
            from .methods import inventory as query
            return query(job,ee.Geometry(boundaries[job['province']['ma_tinh']]['geometry']))
    root=Path(root);state_path=root/'.local_state'/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else dict(jobs={},statistics={},inventory={})
    state['execution_backend']='local'
    def save():
        verify_volume(config);atomic_json(state_path,state)
    exit_code=0
    with single_receiver(root):
        # Seed previously verified table outputs before any partial panel can replace
        # a receiver-produced panel. No Drive read is needed for this migration.
        from province_pipeline.profiles import table_specs
        from province_pipeline.jobs import table_job
        for spec in table_specs(config):
            job=table_job(config,spec,metadata)
            proof=prior(config,root,job)
            if proof:
                state['jobs'][job['job_id']]=dict(job,status='DONE_LOCAL')
                state['statistics'][job['job_id']]=read_table(local_path(root,proof['relative_path']))
        save()
        # Complete each stage across the whole branch before admitting the next.
        # Job identities and receipts stay unchanged, so existing work is reused.
        for stage in range(3):
            audit('local_stage_started',stage={0:'night_images',1:'indices_csv',2:'day_images'}[stage],
                  province_codes=config['province_codes'])
            for province in config['task_scope']['provinces']:
                active=dict(config,province_codes=[province['ma_tinh']])
                free=shutil.disk_usage(root).free
                active['local_output_limit_bytes']=max(0,(free-2*1024**3)//2)
                if active['local_output_limit_bytes']<=0:exit_code=4;break
                state['current_province']=province['number'];state['current_stage']={0:'night_images',1:'indices_csv',2:'day_images'}[stage]
                for job in generate_v2(active,boundaries,metadata,stage):
                    verify_volume(config)
                    if STOP:exit_code=130;break
                    jid=job['job_id'];old=state['jobs'].get(jid,{})
                    if old.get('status') in ('MISSING_SOURCE','INSUFFICIENT_QUALITY','FAILED'):continue
                    proof=prior(config,root,job)
                    if proof:
                        state['jobs'][jid]=dict(job,status='DONE_LOCAL')
                        if job['kind']=='table':state['statistics'][jid]=read_table(local_path(root,proof['relative_path']))
                        continue
                    # Limit is based on free E space, not the old 20 GB Drive budget.
                    if job['kind']=='image':
                        job['reserved_bytes']=min(job['reserved_bytes'],max(0,(shutil.disk_usage(root).free-2*1024**3)//2))
                        if job['reserved_bytes']<=0:exit_code=4;break
                    state['jobs'][jid]=dict(job,status='RUNNING_LOCAL',attempt=old.get('attempt',0)+1)
                    save()
                    from province_pipeline.priority import inventory_key
                    key=inventory_key(job)
                    try:
                        if key not in state['inventory']:state['inventory'][key]=inventory(job)
                        record=state['inventory'][key]
                        if record['status']!='AVAILABLE':
                            state['jobs'][jid]['status']='MISSING_SOURCE' if not record.get('count') else 'INSUFFICIENT_QUALITY'
                            save();continue
                        job['inventory']=record
                        proof=exporter(active,root,job,boundaries[job['province']['ma_tinh']])
                        state['jobs'][jid]=dict(job,status='DONE_LOCAL')
                        if job['kind']=='table':state['statistics'][jid]=read_table(local_path(root,proof['relative_path']))
                    except NoValidPixels:
                        state['jobs'][jid].update(status='INSUFFICIENT_QUALITY',error='NO_VALID_PIXELS')
                        save();continue
                    except province_image.ExportInterrupted:
                        state['jobs'][jid]['status']='RETRY_PENDING';exit_code=130;save();break
                    except province_image.OutputLimit:
                        state['jobs'][jid]['status']='RETRY_PENDING';exit_code=4;save();break
                    except Exception as error:
                        verify_volume(config)
                        state['jobs'][jid].update(status='FAILED' if state['jobs'][jid]['attempt']>=4 else 'RETRY_PENDING',error_type=type(error).__name__)
                        audit('local_export_failed',job_id=jid,error_type=type(error).__name__)
                        save()
                        # Configuration, network and permission failures require a fresh run;
                        # do not burn through the remaining provinces with the same failure.
                        exit_code=2;break
                    save()
                    if job['kind']=='table':panels(config,root,state,metadata)
                save();panels(config,root,state,metadata)
                if exit_code:break
            if exit_code:break
        state['local_exit_code']=exit_code
        state['summary']=dict(Counter(j['status'] for j in state['jobs'].values() if j['province']['ma_tinh'] in config['province_codes']))
        if exit_code==0:state['current_stage']='complete'
        state['status']='paused' if exit_code else 'complete_with_gaps' if any(k in state['summary'] for k in ('MISSING_SOURCE','INSUFFICIENT_QUALITY','FAILED')) else 'complete'
        counts=panels(config,root,state,metadata)
        state['panel_status_counts']=counts or {}
        if exit_code==0 and any(status not in ('OK','OK_RAW','OK_NOTEBOOK') for table in (counts or {}).values() for status in table):
            state['status']='complete_with_gaps'
        save()
        atomic_json(root/'branch_progress.json',dict(backend='local_e',branch=config['task_scope']['branch'],
            mode=config['task_scope']['mode'],stage=state['current_stage'],status=state['status'],
            exit_code=exit_code,statuses=state['summary'],destination=str(root)))
        audit('local_progress',mode=config['task_scope']['mode'],branch=config['task_scope']['branch'],
              exit_code=exit_code,statuses=state['summary'],destination=str(root))
    return exit_code


def main():
    parser=argparse.ArgumentParser(description='Earth Engine -> external E drive directly; no Google Drive')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('authenticate')
    p=sub.add_parser('run');p.add_argument('--mode',choices=['pilot','full'],default='pilot')
    p.add_argument('--config');p.add_argument('--root');p.add_argument('--ee-key')
    args=parser.parse_args();logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    import ee
    if args.command=='authenticate':
        ee.Authenticate(auth_mode='localhost',scopes=['https://www.googleapis.com/auth/earthengine','https://www.googleapis.com/auth/cloud-platform'])
        ee.Initialize(project=PROJECT)
        if ee.Number(1).getInfo()!=1:raise RuntimeError('Earth Engine authentication probe failed')
        print('Earth Engine:',PROJECT,'PASS')
        return
    if os.name!='nt':raise SystemExit('Run this command on the Windows computer with external drive E')
    c,root=prepare(args.mode,args.config,args.root)
    from province_pipeline.prepare_gadm import prepare as prepare_boundaries
    from province_pipeline.boundaries import load_boundaries
    if not Path(c['boundaries']).exists() or not Path(c['boundary_metadata']).exists():prepare_boundaries(c)
    boundaries,metadata=load_boundaries(c)
    from province_pipeline.earth_engine import initialize
    initialize(c,credentials(args.ee_key))
    signal.signal(signal.SIGINT,request_stop);signal.signal(signal.SIGTERM,request_stop)
    raise SystemExit(run(c,root,boundaries,metadata))

if __name__=='__main__':main()
