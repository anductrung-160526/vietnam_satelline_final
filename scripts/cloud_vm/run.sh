#!/usr/bin/env bash
# Start one background tmux session per Earth Engine account; each takes its share of every year.
#   bash scripts/cloud_vm/run.sh SENTINEL2 2016-2025
# Sessions keep running after you close the browser SSH window. Same command again = resume.
set -euo pipefail
PRODUCT=$1; YEARS=$2; WORKERS=${WORKERS:-1}
ACCOUNTS=(acc-wqiqc:vngis-ee-2 acc-ftu:vngis-ee-ha-tinh-lai-chau acc-quynhmai:vngis-ee-soc-trang-yen-bai
          acc-work:vngis-ee-cao-bang-hanoi acc-qec:vngis-ee-lam-dong-quang-tri acc-4usd:vgis-ee-6)
N=${#ACCOUNTS[@]}; CODE=~/vietnam_satelline_final; LOGS=/data/SatelliteData/_control/national
mkdir -p "$LOGS"
for i in "${!ACCOUNTS[@]}"; do
  NAME=${ACCOUNTS[$i]%%:*}; PROJECT=${ACCOUNTS[$i]##*:}; PART=$((i+1)); S="p$PART"
  tmux has-session -t "$S" 2>/dev/null && { echo "$S already running"; continue; }
  tmux new-session -d -s "$S" "cd $CODE && HOME=$HOME/ee/$NAME $CODE/.venv/bin/python -m task_pipeline.national \
    --product $PRODUCT --years $YEARS --project $PROJECT --shard $PART/$N --workers $WORKERS --root /data/SatelliteData \
    2>&1 | tee -a $LOGS/log_${PRODUCT}_$S.txt; echo FINISHED; sleep infinity"
  echo "started $S: $NAME / $PROJECT / shard $PART/$N"
done
echo "Watch:  tmux attach -t p1   (leave with Ctrl+B then D)   |   tail -f $LOGS/log_${PRODUCT}_p1.txt"
