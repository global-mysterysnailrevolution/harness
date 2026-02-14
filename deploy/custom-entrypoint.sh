#!/bin/sh
# Custom OpenClaw container entrypoint wrapper.
# Creates python -> python3 symlink (Debian images only ship python3)
# then delegates to the original entrypoint.
#
# Deploy to: /docker/openclaw-kx9d/data/custom-entrypoint.sh
# Referenced by docker-compose.yml: entrypoint: ["/data/custom-entrypoint.sh"]

ln -sf /usr/bin/python3 /usr/bin/python 2>/dev/null || true
exec /entrypoint.sh "$@"
