#!/bin/sh
# Custom OpenClaw container entrypoint wrapper.
# Creates python -> python3 symlink (Debian images only ship python3)
# Adds /data/.local/bin to PATH for skill CLIs (gh, gemini, codex)
# then delegates to the original entrypoint.

ln -sf /usr/bin/python3 /usr/bin/python 2>/dev/null || true
export PATH="/data/.local/bin:$PATH"
exec /entrypoint.sh "$@"
