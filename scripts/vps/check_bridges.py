#!/usr/bin/env python3
"""Quick check of MCP bridge status. Run on VPS host."""
import os, json, signal, urllib.request
from pathlib import Path

PID_DIR = Path("/tmp/mcp-bridges")
CONFIG = Path("/opt/harness/ai/supervisor/mcp_bridges.json")

def check_pid(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def check_http(port):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/mcp",
            data=b'{"jsonrpc":"2.0","method":"tools/list","id":1}',
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()[:200]
    except Exception as e:
        return 0, str(e)[:100]

# Check PID files
print("=== Bridge PIDs ===")
for pf in sorted(PID_DIR.glob("*.pid")):
    name = pf.stem
    pid = int(pf.read_text().strip())
    alive = check_pid(pid)
    print(f"  {name}: pid={pid} alive={alive}")

# Check config
print("\n=== Bridge Config ===")
if CONFIG.exists():
    cfg = json.loads(CONFIG.read_text())
    for name, bc in cfg.get("bridges", {}).items():
        port = bc.get("port", "?")
        enabled = bc.get("enabled", True)
        print(f"  {name}: port={port} enabled={enabled}")

# HTTP health check
print("\n=== HTTP Health ===")
if CONFIG.exists():
    cfg = json.loads(CONFIG.read_text())
    for name, bc in cfg.get("bridges", {}).items():
        if not bc.get("enabled", True):
            continue
        port = bc.get("port")
        if port:
            status, body = check_http(port)
            ok = "OK" if status == 200 else "FAIL"
            print(f"  {name} (:{port}): {ok} status={status}")

# Check from Docker bridge perspective
print("\n=== Container Access ===")
print("  From container, bridges are at http://172.18.0.1:<port>/mcp")
print("  Test: docker exec openclaw-kx9d-openclaw-1 curl -s http://172.18.0.1:8101/mcp -X POST -H 'Content-Type: application/json' -d '{}'")
