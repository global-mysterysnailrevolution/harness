#!/usr/bin/env python3
"""Remove invalid mcpServers key from openclaw.json to fix crash loop."""
import json
import shutil
from pathlib import Path
from datetime import datetime

config_path = Path("/docker/openclaw-kx9d/data/.openclaw/openclaw.json")
if not config_path.exists():
    print("ERROR: openclaw.json not found")
    exit(1)

# Backup
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy2(config_path, config_path.with_suffix(f".json.bak.{ts}"))

config = json.loads(config_path.read_text())

# Remove the invalid key
if "mcpServers" in config:
    removed = config.pop("mcpServers")
    config_path.write_text(json.dumps(config, indent=2))
    print(f"Removed mcpServers key ({len(removed)} servers)")
    print("Servers removed:")
    for name in removed:
        print(f"  - {name}")
else:
    print("mcpServers key not found (already removed?)")

print("\nRestart OpenClaw now:")
print("  docker restart openclaw-kx9d-openclaw-1")
