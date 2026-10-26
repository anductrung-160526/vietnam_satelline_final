"""Run one branch on the Windows laptop, straight into E:\\SatelliteData. No Google Drive.

Order inside a branch (each stage for every province before the next):
  1. raw night images   (Earth Engine)   VN_NTL_Panel_2004_2025/raw_data/NTL/...
  2. raw day images     (Earth Engine)   VN_LandCover_Panel_2004_2025/raw_data/DAY/...
  3. data_intermediate  (laptop only)    filtered night images, annual dry-season day composites
  4. data_processed     (laptop only)    index tables, merged across the six branches
Files with a valid receipt (or an untracked file at the exact expected path that passes
grid/band validation) are kept; only missing work runs. Branch state lives in
_control/<NNN_NNN>/, so six branches can run at the same time.
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
from province_pipeline.common import atomic_json,audit
from province_pipeline.receiver import verify_volume,enroll,single_receiver,hashes,validate
from province_pipeline.quality import NoValidPixels
from province_pipeline.sources import NTL_PACKAGE,DAY_PACKAGE
from .scope import PROJECT,scope,configure
from .paths import control_root,resolve,ensure_packages,append_log,branch_name
from . import province_image
from . import raw as raw_jobs
from . import derive

STOP=False
STAGES=('night_raw','day_raw','intermediate','processed')
IMAGE_TYPE={'DMSP':'DMSP','VIIRS_MONTHLY':'VIIRS','VIIRS_ANNUAL_EOG':'VIIRS','LANDSAT':'Landsat','SENTINEL2':'Sentinel-2'}


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


# Earth Engine project (separate quota) of each fixed province range.
RANGE_PROJECTS={(1,11):'vngis-ee-2',(12,22):'vngis-ee-ha-tinh-lai-chau',(23,33):'vngis-ee-soc-trang-yen-bai',
                (34,43):'vngis-ee-cao-bang-hanoi',(44,53):'vngis-ee-lam-dong-quang-tri',(54,63):'vgis-ee-6'}


def selection_for(mode,range_text=None):
    """Range from --range 54-63 (one checkout can run all six), else branch_range.json."""
    if not range_text:
        return scope(mode)
    start,end=(int(x) for x in range_text.replace('_','-').split('-'))
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'range.json';path.write_text(json.dumps(dict(start=start,end=end)))
        return scope(mode,path)


def prepare(mode,config_path=None,root=None,project=None,range_text=None):
    source=Path(config_path or 'province_pipeline/config/local.json')
    if not source.exists():source=Path('province_pipeline/config/example.json')
    base=json.loads(source.read_text(encoding='utf-8-sig'))
    selection=selection_for(mode,range_text)
    # The range's own Earth Engine project (quota) always wins over a shared local.json.
    base['project']=project or (RANGE_PROJECTS[(selection['start'],selection['end'])] if range_text else PROJECT)
    c=configure(dict(base),selection) if base['project']==PROJECT else configure_for(base,selection)
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
    root=verify_volume(c)
    ensure_packages(root)
    control=control_root(root,selection);control.mkdir(parents=True,exist_ok=True)
    atomic_json(control/'direct-config.json',c)
    return c,root,control


def configure_for(base,selection):
    """Same scientific configuration under an explicitly chosen project (--project)."""
    from . import scope as module
    original=module.PROJECT
    try:
        module.PROJECT=base['project'];return configure(base,selection)
    finally:
        module.PROJECT=original


def receipt_path(control,job):
    return Path(control)/'.local_state'/'receipts'/(job['job_id']+'.json')


def relative_of(job):
    return job['local_directory']+'/'+job['prefix']+('.tif' if job['kind']=='image' else '.csv')


def prior(config,root,control,job):
    """Existing verified output for this job, or None.

    1. receipt written by this tool;  2. receipt of the earlier Drive receiver;
    3. an untracked file at the exact expected path that passes grid/band/dtype validation
       (recorded as adopted, so work done before a lost state file is not fetched again).
    """
    jid=job['job_id'];receipt=receipt_path(control,job)
    if receipt.exists():
        info=json.loads(receipt.read_text(encoding='utf-8'))
        if info['job_id']!=jid:raise ValueError('Local receipt identity mismatch')
        dest=resolve(root,control,info['relative_path'])
        if dest.exists():
            if validate(dest,info['file'],job)!=info['sha256']:raise ValueError('Local output changed')
            return info
    manifest_path=Path(control)/'.manifests'/(jid+'.json');received_path=Path(control)/'.receipts'/(jid+'.json')
    if manifest_path.exists() and received_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        received=json.loads(received_path.read_text(encoding='utf-8'))
        if manifest.get('job_id')!=jid or received.get('volume_marker')!=config['volume_marker']:
            raise ValueError('Previous receiver provenance does not match job/disk')
        for f in manifest['files']:
            if f.get('role')=='preview':continue
            dest=resolve(root,control,f['local_relative_path'])
            if not dest.exists():continue
            sha=validate(dest,f,job)
            if not any(r.get('verified') and r['id']==f['id'] and r['sha256']==sha for r in received['files']):
                raise ValueError('Previous receiver receipt mismatch')
            return dict(job_id=jid,relative_path=f['local_relative_path'],file=dict(size=f['size'],md5Checksum=f['md5Checksum']),sha256=sha)
    if job['kind']=='image':
        relative=relative_of(job);dest=resolve(root,control,relative)
        if dest.exists():
            md5,sha=hashes(dest);file=dict(size=str(dest.stat().st_size),md5Checksum=md5)
            try:
                validate(dest,file,job)
            except Exception:
                return None   # leave it untouched; export refuses to overwrite it
            info=dict(job_id=jid,relative_path=relative,file=file,sha256=sha,adopted=True)
            atomic_json(receipt,info)
            return info
    return None


def export(config,root,control,job,boundary):
    """Build in same-volume scratch, verify, persist receipt, then atomic rename."""
    import ee
    import rasterio
    from .methods import composite
    from province_pipeline.quality import inspect_raster
    verify_volume(config)
    relative=relative_of(job);dest=resolve(root,control,relative)
    if dest.exists():raise RuntimeError('Existing output has no valid receipt; refusing overwrite')
    scratch=Path(control)/'.work';scratch.mkdir(parents=True,exist_ok=True)
    geometry=ee.Geometry(boundary['geometry']);image=composite(config,job,geometry)
    with tempfile.TemporaryDirectory(prefix=job['job_id']+'-',dir=scratch) as tmp:
        path=Path(tmp)/(job['prefix']+'.tif')
        province_image.download(image,job,path,boundary,config)
        qa=inspect_raster(path,job)
        if not qa['valid_pixel_pct']:raise NoValidPixels('No valid source pixels')
        inv=job.get('inventory',{})
        with rasterio.open(path,'r+') as ds:
            ds.update_tags(PROJECT=config['project'],SOURCE=job['product'],PERIOD=job['period'],
                METHOD_VERSION=job['algorithm_version'],JOB_ID=job['job_id'],
                VALID_PIXEL_PCT=str(qa['valid_pixel_pct']),QA_FLAGS=';'.join(qa['flags']),
                WINDOW_DAYS=str(inv.get('window_days',0)),COLLECTIONS=','.join(inv.get('collections',[])),
                SCENES=str(inv.get('count','')))
        if path.stat().st_size>job['reserved_bytes']:raise province_image.OutputLimit('Local file exceeds disk reservation')
        md5,sha=hashes(path);file=dict(size=str(path.stat().st_size),md5Checksum=md5)
        validate(path,file,job)
        verify_volume(config)
        receipt=dict(job_id=job['job_id'],relative_path=relative,file=file,sha256=sha)
        # Receipt precedes rename: recovery is safe after a crash between rename/state save.
        atomic_json(receipt_path(control,job),receipt)
        dest.parent.mkdir(parents=True,exist_ok=True)
        path.replace(dest)
    package=NTL_PACKAGE if job['product'] in ('DMSP','VIIRS_MONTHLY','VIIRS_ANNUAL_EOG') else DAY_PACKAGE
    append_log(root,package,IMAGE_TYPE.get(job['product'],job['product']),
               f"{job['province']['ma_tinh']} {job['province']['ten_tinh']} {job['period']}: {dest.name} ({int(file['size'])/1024**2:.1f} MB)")
    audit('saved_local',job_id=job['job_id'],destination=str(dest),backend='local_e')
    return receipt


def raw_stage(config,root,control,state,save,boundaries,metadata,kind,inventory,exporter,job_source):
    """One Earth Engine stage over every province of the branch. Returns an exit code."""
    from province_pipeline.priority import inventory_key
    for province in config['task_scope']['provinces']:
        active=dict(config,province_codes=[province['ma_tinh']])
        if (shutil.disk_usage(root).free-2*1024**3)<=0:return 4
        state['current_province']=province['number'];state['current_stage']=kind+'_raw'
        for job in job_source(active,boundaries,metadata,kind,province):
            verify_volume(config)
            if STOP:return 130
            jid=job['job_id'];old=state['jobs'].get(jid,{})
            if old.get('status') in ('MISSING_SOURCE','INSUFFICIENT_QUALITY','FAILED'):continue
            if prior(config,root,control,job):
                if old.get('status')!='DONE_LOCAL':state['jobs'][jid]=dict(job,status='DONE_LOCAL')
                continue
            job['reserved_bytes']=min(job['reserved_bytes'],max(0,(shutil.disk_usage(root).free-2*1024**3)//2))
            if job['reserved_bytes']<=0:return 4
            state['jobs'][jid]=dict(job,status='RUNNING_LOCAL',attempt=old.get('attempt',0)+1)
            save()
            key=inventory_key(job)
            try:
                if key not in state['inventory']:state['inventory'][key]=inventory(job)
                record=state['inventory'][key]
                if record['status']!='AVAILABLE':
                    state['jobs'][jid]['status']='MISSING_SOURCE' if not record.get('count') else 'INSUFFICIENT_QUALITY'
                    save();continue
                job['inventory']=record
                exporter(active,root,control,job,boundaries[job['province']['ma_tinh']])
                state['jobs'][jid]=dict(job,status='DONE_LOCAL')
            except NoValidPixels:
                state['jobs'][jid].update(status='INSUFFICIENT_QUALITY',error='NO_VALID_PIXELS')
            except province_image.ExportInterrupted:
                state['jobs'][jid]['status']='RETRY_PENDING';save();return 130
            except province_image.OutputLimit:
                state['jobs'][jid]['status']='RETRY_PENDING';save();return 4
            except Exception as error:
                verify_volume(config)
                state['jobs'][jid].update(status='FAILED' if state['jobs'][jid]['attempt']>=4 else 'RETRY_PENDING',error_type=type(error).__name__)
                audit('local_export_failed',job_id=jid,error_type=type(error).__name__)
                save()
                # Configuration, network and permission failures need a fresh run;
                # do not burn through the remaining provinces with the same failure.
                return 2
            save()
        save()
    return 0


def raw_index(root,control,state,province,kind,job_source,config,boundaries,metadata):
    """{(product, period): path} of committed raw files and {(product, period): status}."""
    files,status={},{}
    for job in job_source(dict(config,province_codes=[province['ma_tinh']]),boundaries,metadata,kind,province):
        key=(job['product'],job['period']);entry=state['jobs'].get(job['job_id'],{})
        status[key]=entry.get('status')
        receipt=receipt_path(control,job)
        if entry.get('status')=='DONE_LOCAL' and receipt.exists():
            path=resolve(root,control,json.loads(receipt.read_text(encoding='utf-8'))['relative_path'])
            if path.exists():files[key]=path
    return files,status


def local_stages(config,root,control,state,boundaries,metadata,job_source):
    """Stages 3 and 4 on the laptop only. Rebuilds only outputs whose inputs changed."""
    cache=derive.Cache(Path(control)/'derive_cache.json')
    tables={name:[] for name in derive.TABLES}
    override=config.get('dry_season_months_by_province')
    for province in config['task_scope']['provinces']:
        if STOP:return 130
        p=dict(province)
        area=derive.province_area_km2(boundaries[p['ma_tinh']])
        night,_=raw_index(root,control,state,p,raw_jobs.NIGHT,job_source,config,boundaries,metadata)
        day,day_status=raw_index(root,control,state,p,raw_jobs.DAY,job_source,config,boundaries,metadata)
        state['current_province']=p['number'];state['current_stage']='intermediate'
        filtered=derive.viirs_filtered(night,p,root)
        annual=derive.viirs_annual(night,filtered,p,root)
        dmsp=derive.dmsp_annual(night,p,root)
        derive.day_annual(day,p,root,override)
        state['current_stage']='processed'
        tables['day_indices_monthly']+=derive.day_rows(p,day_status,day,area,cache)
        tables['ntl_monthly']+=derive.ntl_monthly_rows(p,filtered,area,cache)
        rows,overlap=derive.ntl_annual_rows(p,{y:v for y,v in dmsp.items()},annual,area,cache)
        tables['ntl_annual']+=rows
        if overlap:tables['ntl_overlap_2013'].append(overlap)
        cache.save()
    for name,rows in tables.items():
        if rows:derive.write_part(control,name,rows)
    derive.merge(root);derive.write_docs(root)
    state['landcover']=derive.landcover_status(root)
    return 0


def run(config,root,boundaries,metadata,inventory=None,exporter=export,control=None,job_source=None,local=None):
    """Earth Engine requests and local filesystem writes only. No Drive, no remote deletion."""
    if inventory is None:
        def inventory(job):
            import ee
            from .methods import inventory as query
            return query(job,ee.Geometry(boundaries[job['province']['ma_tinh']]['geometry']))
    job_source=job_source or raw_jobs.jobs
    local=local or local_stages
    root=Path(root);control=Path(control or control_root(root,config['task_scope']))
    control.mkdir(parents=True,exist_ok=True)
    state_path=control/'.local_state'/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else dict(jobs={},inventory={})
    state.setdefault('jobs',{});state.setdefault('inventory',{})
    state['execution_backend']='local';state['layout']='shared_packages_v4'
    def save():
        verify_volume(config);atomic_json(state_path,state)
    exit_code=0
    with single_receiver(control):
        for kind in (raw_jobs.NIGHT,raw_jobs.DAY):
            audit('local_stage_started',stage=kind+'_raw',province_codes=config['province_codes'])
            exit_code=raw_stage(config,root,control,state,save,boundaries,metadata,kind,inventory,exporter,job_source)
            save()
            if exit_code:break
        if not exit_code:
            audit('local_stage_started',stage='intermediate+processed',province_codes=config['province_codes'])
            exit_code=local(config,root,control,state,boundaries,metadata,job_source)
        state['local_exit_code']=exit_code
        state['summary']=dict(Counter(j['status'] for j in state['jobs'].values() if j['province']['ma_tinh'] in config['province_codes']))
        if exit_code==0:state['current_stage']='complete'
        gaps=any(k in state['summary'] for k in ('MISSING_SOURCE','INSUFFICIENT_QUALITY','FAILED'))
        state['status']='paused' if exit_code else 'complete_with_gaps' if gaps else 'complete'
        save()
        atomic_json(control/'branch_progress.json',dict(backend='local_e',branch=config['task_scope']['branch'],
            mode=config['task_scope']['mode'],stage=state.get('current_stage'),status=state['status'],
            exit_code=exit_code,statuses=state['summary'],landcover=state.get('landcover'),destination=str(root)))
        audit('local_progress',mode=config['task_scope']['mode'],branch=config['task_scope']['branch'],
              exit_code=exit_code,statuses=state['summary'],destination=str(root))
    return exit_code


def main():
    parser=argparse.ArgumentParser(description='Earth Engine -> external E drive directly; no Google Drive')
    sub=parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('authenticate');a.add_argument('--project')
    m=sub.add_parser('migrate');m.add_argument('--root',default=r'E:\SatelliteData')
    for name in ('run','derive'):
        p=sub.add_parser(name);p.add_argument('--mode',choices=['pilot','full'],default='pilot')
        p.add_argument('--config');p.add_argument('--root');p.add_argument('--ee-key');p.add_argument('--project')
        p.add_argument('--range',help='Province range, e.g. 54-63 (default: branch_range.json)')
    args=parser.parse_args();logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    if args.command=='migrate':
        from .migrate import main as migrate
        raise SystemExit(migrate(args.root))
    import ee
    if args.command=='authenticate':
        project=args.project or PROJECT
        ee.Authenticate(auth_mode='localhost',scopes=['https://www.googleapis.com/auth/earthengine','https://www.googleapis.com/auth/cloud-platform'])
        ee.Initialize(project=project)
        if ee.Number(1).getInfo()!=1:raise RuntimeError('Earth Engine authentication probe failed')
        print('Earth Engine:',project,'PASS')
        return
    if os.name!='nt':raise SystemExit('Run this command on the Windows computer with external drive E')
    c,root,control=prepare(args.mode,args.config,args.root,args.project,args.range)
    from province_pipeline.prepare_gadm import prepare as prepare_boundaries
    from province_pipeline.boundaries import load_boundaries
    if not Path(c['boundaries']).exists() or not Path(c['boundary_metadata']).exists():prepare_boundaries(c)
    boundaries,metadata=load_boundaries(c)
    signal.signal(signal.SIGINT,request_stop);signal.signal(signal.SIGTERM,request_stop)
    if args.command=='derive':
        # Stages 3-4 only, for raw files already on E. No Earth Engine request.
        state_path=control/'.local_state'/'state.json'
        state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else dict(jobs={})
        with single_receiver(control):
            code=local_stages(c,root,control,state,boundaries,metadata,raw_jobs.jobs)
            atomic_json(state_path,state)
        raise SystemExit(code)
    from province_pipeline.earth_engine import initialize
    initialize(c,credentials(args.ee_key))
    raise SystemExit(run(c,root,boundaries,metadata,control=control))

if __name__=='__main__':main()
