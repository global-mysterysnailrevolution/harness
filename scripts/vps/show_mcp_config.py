#!/usr/bin/env python3
"""Show OpenClaw MCP server configuration."""
import json
from pathlib import Path

cfg_path = Path("/docker/openclaw-kx9d/data/.openclaw/openclaw.json")
if not cfg_path.exists():
    print("openclaw.json not found")
    exit(1)

cfg = json.loads(cfg_path.read_text())
print("=== mcpServers ===")
print(json.dumps(cfg.get("mcpServers", {}), indent=2))

print("\n=== customModes ===")
modes = cfg.get("customModes", [])
if modes:
    for m in modes:
        print(json.dumps(m, indent=2))
else:
    print("None")

# Also check AGENTS.md for MCP references
agents_path = Path("/docker/openclaw-kx9d/data/.openclaw/AGENTS.md")
if agents_path.exists():
    text = agents_path.read_text()
    for line in text.split("\n"):
        if "mcp" in line.lower() or "bridge" in line.lower() or "8101" in line or "8102" in line or "8104" in line:
            print(f"  AGENTS.md: {line.strip()}")
