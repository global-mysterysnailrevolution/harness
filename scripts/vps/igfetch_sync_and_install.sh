#!/bin/bash
# Sync reels from OpenClaw workspace harness to igfetch app and run npm install.
# Run on VPS: bash scripts/vps/igfetch_sync_and_install.sh

set -e

WORKSPACE_HARNESS="/docker/openclaw-kx9d/data/.openclaw/workspace/harness"
IGFETCH_APP="/opt/harness/igfetch/app"

echo "=== Syncing scripts/reels from workspace to igfetch app ==="
if [[ ! -d "$WORKSPACE_HARNESS/scripts/reels" ]]; then
  echo "ERROR: $WORKSPACE_HARNESS/scripts/reels not found"
  exit 1
fi

sudo mkdir -p "$IGFETCH_APP/scripts/reels"
sudo rsync -a --delete "$WORKSPACE_HARNESS/scripts/reels/" "$IGFETCH_APP/scripts/reels/"
sudo chown -R igfetch:igfetch "$IGFETCH_APP/scripts/reels"

echo "=== npm install ==="
if [[ -f "$IGFETCH_APP/scripts/reels/package.json" ]]; then
  sudo -u igfetch bash -c "cd $IGFETCH_APP/scripts/reels && npm install"
  echo "Done."
else
  echo "ERROR: package.json not found after sync"
  exit 1
fi
