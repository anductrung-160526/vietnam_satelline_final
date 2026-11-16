"""Reuse the current project/secrets; materialize an immutable branch scope."""
import json
import os
from pathlib import Path
from province_pipeline.ci_setup import prepare
from province_pipeline.common import atomic_json
from .scope import scope,configure


def main():
    # No PROVINCE_RUN_PROFILE in the six-branch workflow: retain connection config,
    # then replace only the scientific/scope settings using the fixed range file.
    prepare()
    selection=scope(os.environ.get('TASK_MODE','pilot'),ref=os.environ.get('GITHUB_REF_NAME'))
    path=Path('.province-local/config.json')
    c=configure(json.loads(path.read_text()),selection)
    c.update(boundary_provider='gadm41',boundary_policy='gadm41_research',
             boundaries='province_pipeline/config/boundaries.geojson',
             boundary_metadata='province_pipeline/config/boundaries.metadata.json')
    atomic_json(path,c)
    print('Fixed scope:',selection['branch'],selection['mode'],[p['ten_tinh'] for p in selection['provinces']])
    print('Earth Engine project retained:',c['project'])

if __name__=='__main__':main()
