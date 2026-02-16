#!/bin/bash
# igfetch deployment script — run on VPS via SSH.
# Usage: ssh root@VPS 'bash -s' < scripts/vps/igfetch_deploy.sh
# Or: copy to VPS and run with sudo bash igfetch_deploy.sh

set -e

TBALL="/docker/openclaw-kx9d/data/.openclaw/workspace/tmp/reels_pipeline_harness.tar.gz"

echo "=== Step 0: sudo check ==="
sudo -v

echo "=== Step 1: ffmpeg ==="
sudo apt-get update -qq
sudo apt-get install -y ffmpeg
ffmpeg -version | head -n 2
ffprobe -version | head -n 2

echo "=== Step 2: user + dirs ==="
sudo useradd -m -s /bin/bash igfetch 2>/dev/null || true
sudo mkdir -p /opt/harness/igfetch/{app,state,downloads,frames,results,logs}
sudo chown -R igfetch:igfetch /opt/harness/igfetch
sudo chmod 700 /opt/harness/igfetch/state

echo "=== Step 3: extract tarball ==="
if [[ ! -f "$TBALL" ]]; then
  echo "ERROR: Tarball not found at $TBALL"
  exit 1
fi
# Inspect structure
echo "Tarball contents (first 15):"
tar -tzf "$TBALL" | head -15
# Extract — adjust --strip-components if tarball has different layout
sudo tar -xzf "$TBALL" -C /opt/harness/igfetch/app --strip-components=1 2>/dev/null || \
  sudo tar -xzf "$TBALL" -C /opt/harness/igfetch/app
sudo chown -R igfetch:igfetch /opt/harness/igfetch/app

echo "=== npm install (if package.json exists) ==="
if [[ -f /opt/harness/igfetch/app/package.json ]]; then
  sudo -u igfetch bash -c 'cd /opt/harness/igfetch/app && npm install'
elif [[ -f /opt/harness/igfetch/app/scripts/reels/package.json ]]; then
  sudo -u igfetch bash -c 'cd /opt/harness/igfetch/app/scripts/reels && npm install'
else
  echo "No package.json found — skip npm install. Add package.json to tarball if Node deps needed."
fi

echo "=== Done. Step 4: run Instagram auth when ready. ==="
