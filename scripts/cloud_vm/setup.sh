#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu Google Cloud VM: data disk on /data, Python env, code.
set -euo pipefail
DISK=${DISK:-/dev/sdb}
if ! mountpoint -q /data; then
  if ! sudo blkid "$DISK" >/dev/null 2>&1; then
    echo "Formatting $DISK (new, empty data disk)"; sudo mkfs.ext4 -m 0 -F "$DISK"
  fi
  sudo mkdir -p /data && sudo mount -o discard,defaults "$DISK" /data
  grep -q " /data " /etc/fstab || echo "UUID=$(sudo blkid -s UUID -o value "$DISK") /data ext4 discard,defaults,nofail 0 2" | sudo tee -a /etc/fstab
  sudo chown "$USER" /data
fi
sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv git tmux >/dev/null
cd ~
[ -d vietnam_satelline_final ] || git clone -q -b vngis-tinh-001-011 https://github.com/anductrung-160526/vietnam_satelline_final.git
cd vietnam_satelline_final && git pull -q
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r province_pipeline/requirements.txt
mkdir -p /data/SatelliteData/_control/national ~/ee
echo "Setup done. Disk:"; df -h /data | tail -1
