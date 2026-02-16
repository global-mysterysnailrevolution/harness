#!/bin/bash
# Start igfetch server. Run on VPS.
# Usage: IGFETCH_TOKEN=your-secret-token bash scripts/vps/igfetch_start.sh
# Or: create /opt/harness/igfetch/.env with IGFETCH_TOKEN=...

set -e

TOKEN="${IGFETCH_TOKEN:?Set IGFETCH_TOKEN (e.g. export IGFETCH_TOKEN=your-secret-token)}"
cd /opt/harness/igfetch/app/scripts/reels

export IGFETCH_BASE=/opt/harness/igfetch
export IGFETCH_BIND=127.0.0.1
export IGFETCH_PORT=8787
export IGFETCH_TOKEN="$TOKEN"

echo "Starting igfetch on 127.0.0.1:8787"
exec node igfetch_server.js
