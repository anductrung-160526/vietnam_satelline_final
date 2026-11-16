"""Bounded workflow redispatch using the job-scoped GitHub token, never a new secret."""
import json
import os
from .common import load_config, audit


def decision(state, remaining):
    if not 1 <= remaining <= 20:
        raise ValueError('cycles must be an integer in 1..20')
    if remaining <= 1:
        return 'CYCLE_LIMIT'
    if state.get('waiting_for_space'):
        return 'DRIVE_CAPACITY'
    if state.get('current_stage')=='complete':
        return 'COMPLETE'
    if any(j['status']=='BLOCKED_AMBIGUOUS' for j in state['jobs'].values()):
        return 'AMBIGUOUS_TRANSFER_REQUIRES_REVIEW'
    return None


def main():
    from .drive import Drive
    from .auth import drive_credentials
    from .controller import control_folders
    config=load_config('.province-local/config.json',live=True)
    drive=Drive(drive_credentials())
    state=drive.read_json(control_folders(drive,config['drive_root_id'])['root'],'state.json')
    remaining=int(os.environ.get('PROVINCE_CYCLES','20'))
    reason=decision(state,remaining)
    if reason:
        audit('continuation_stopped',reason=reason,stage=state.get('current_stage'))
        return
    from urllib.request import Request,urlopen
    from urllib.error import HTTPError
    from urllib.parse import quote
    repo=os.environ['GITHUB_REPOSITORY']
    branch=os.environ['GITHUB_REF_NAME']
    workflow=os.environ['GITHUB_WORKFLOW_REF'].split('@')[0].rsplit('/',1)[-1]
    body=json.dumps(dict(ref=branch,inputs=dict(mode='run',sample=config['run_profile'],processing=config['quality'].get('processing_mode','quality_filtered'),cycles=str(remaining-1)))).encode()
    request=Request('https://api.github.com/repos/'+repo+'/actions/workflows/'+quote(workflow,safe='')+'/dispatches',
                    data=body,headers={'Authorization':'Bearer '+os.environ['GH_WORKFLOW_TOKEN'],
                    'Accept':'application/vnd.github+json','Content-Type':'application/json',
                    'X-GitHub-Api-Version':'2022-11-28'},method='POST')
    try:
        # No retry: an uncertain dispatch response must not create duplicate chains.
        with urlopen(request,timeout=30) as response:
            if response.status!=204:
                raise RuntimeError('Unexpected workflow dispatch response')
    except HTTPError as error:
        raise RuntimeError(f'Continuation dispatch HTTP {error.code}; rerun manually if needed') from None
    audit('continuation_dispatched',profile=config['run_profile'],remaining_batches=remaining-1)

if __name__=='__main__':
    main()
