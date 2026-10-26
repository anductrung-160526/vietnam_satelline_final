"""Receive six branch roots using the existing disk marker and verified deletion."""
import argparse
import logging
from pathlib import Path
from province_pipeline.common import load_config,local_path
from province_pipeline.auth import drive_credentials
from province_pipeline.drive import Drive
from province_pipeline.receiver import verify_volume,single_receiver,run
from .scope import RANGES


def receive(config,drive,dry_run=False):
    base=verify_volume(config)
    with single_receiver(base):
        parent=drive.find(config['drive_root_id'],'Task123_branches')
        if not parent:return
        failures=[]
        for start,end in RANGES:
            name=f'{start:03}_{end:03}'
            folder=drive.find(parent['id'],name)
            if not folder:continue
            if not drive.find(folder['id'],'_control'):continue
            verify_volume(config)
            dest=local_path(base,'Task123_branches/'+name)
            if not dry_run:dest.mkdir(parents=True,exist_ok=True)
            elif not dest.exists():continue
            owner=dest/'.local_state'/'state.json'
            if owner.exists():
                import json
                if json.loads(owner.read_text(encoding='utf-8')).get('execution_backend')=='local':
                    from province_pipeline.common import audit
                    audit('branch_receive_skipped',branch=name,reason='DIRECT_LOCAL_OWNER')
                    continue
            child=dict(config,drive_root_id=folder['id'],local_root=str(dest))
            try:
                run(child,drive,dry_run)
            except Exception as error:
                from province_pipeline.receiver import failure_reason
                from province_pipeline.common import audit
                audit('branch_receive_failed',branch=name,error_code=failure_reason(error))
                failures.append(name)
        if failures:
            raise RuntimeError('Some branch receivers failed; sources retained: '+','.join(failures))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',default='province_pipeline/config/local.json');parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args();logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    receive(load_config(args.config,live=True),Drive(drive_credentials()),args.dry_run)

if __name__=='__main__':main()
