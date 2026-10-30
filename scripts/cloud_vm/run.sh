#!/usr/bin/env bash
# Start one background tmux session per Earth Engine account; each takes its share of every year.
#   bash scripts/cloud_vm/run.sh SENTINEL2 2016-2025
# Sessions keep running after you close the browser SSH window. Same command again = resume.
# Auth: a service-account key at ~/ee-keys/<name>.json is used when present (no browser login),
# otherwise the OAuth profile created by login.sh at ~/ee/<name>.
set -euo pipefail
PRODUCT=$1; YEARS=$2; WORKERS=${WORKERS:-1}
ACCOUNTS=(acc-wqiqc:vngis-ee-2 acc-ftu:vngis-ee-ha-tinh-lai-chau acc-quynhmai:vngis-ee-soc-trang-yen-bai
          acc-work:vngis-ee-cao-bang-hanoi acc-qec:vngis-ee-lam-dong-quang-tri acc-4usd:vgis-ee-6
          acc-miendao:vgis-ee-07 acc-ducanchu:vgis-ee-08 acc-linhbe:vgis-ee-09 acc-mpnguyen:vgis-ee-10)
N=${#ACCOUNTS[@]}; CODE=~/vietnam_satelline_final; LOGS=/data/SatelliteData/_control/national
mkdir -p "$LOGS"
for i in "${!ACCOUNTS[@]}"; do
  NAME=${ACCOUNTS[$i]%%:*}; PROJECT=${ACCOUNTS[$i]##*:}; PART=$((i+1)); S="p$PART"
  tmux has-session -t "$S" 2>/dev/null && { echo "$S already running"; continue; }
  KEY=~/ee-keys/$NAME.json
  if [ -f "$KEY" ]; then AUTH="--ee-key $KEY"; HOMEDIR=$HOME
  else AUTH=""; HOMEDIR=$HOME/ee/$NAME
       [ -d "$HOMEDIR" ] || { echo "SKIP $S ($NAME): no key at $KEY and no login at $HOMEDIR"; continue; }
  fi
  tmux new-session -d -s "$S" "cd $CODE && HOME=$HOMEDIR $CODE/.venv/bin/python -m task_pipeline.national \
    --product $PRODUCT --years $YEARS --project $PROJECT --shard $PART/$N --workers $WORKERS --root /data/SatelliteData $AUTH \
    2>&1 | tee -a $LOGS/log_${PRODUCT}_$S.txt; echo FINISHED; sleep infinity"
  echo "started $S: $NAME / $PROJECT / shard $PART/$N${AUTH:+ (service-account key)}"
done
echo "Watch:  tmux attach -t p1   (leave with Ctrl+B then D)   |   tail -f $LOGS/log_${PRODUCT}_p1.txt"
