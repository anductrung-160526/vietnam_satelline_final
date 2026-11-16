#!/usr/bin/env bash
# Log one Google account into Earth Engine, kept in its own folder ~/ee/<name>.
#   bash scripts/cloud_vm/login.sh acc-ftu vngis-ee-ha-tinh-lai-chau
# Open the printed link in a browser, sign in with THAT account, paste the code back here.
set -euo pipefail
NAME=$1; PROJECT=$2
mkdir -p ~/ee/"$NAME"
cd ~/vietnam_satelline_final
HOME=~/ee/"$NAME" .venv/bin/python -c "
import ee
ee.Authenticate(auth_mode='notebook',scopes=['https://www.googleapis.com/auth/earthengine','https://www.googleapis.com/auth/cloud-platform'])
ee.Initialize(project='$PROJECT'); assert ee.Number(1).getInfo()==1
print('Earth Engine: $PROJECT PASS')"
