#!/usr/bin/env python3
"""
Config watcher: ensures MCP bridges and OpenClaw stay in sync with config.
Run via cron every 5 min: */5 * * * * cd /opt/harness && python3 scripts/vps/config_watcher.py

- mcp_bridges.json: starts any missing bridges (does not restart existing ones)
- openclaw.json: restarts OpenClaw only when config actually changed
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", "/opt/harness"))
MCP_CONFIG = HARNESS_DIR / "ai" / "supervisor" / "mcp_bridges.json"
OPENCLAW_CONFIG = Path(os.environ.get("OPENCLAW_CONFIG", "/docker/openclaw-kx9d/data/.openclaw/openclaw.json"))
OPENCLAW_CONTAINER = os.environ.get("OPENCLAW_CONTAINER", "openclaw-kx9d-openclaw-1")
CONFIG_HASH_FILE = HARNESS_DIR / "ai" / "config_hashes.json"
PID_DIR = Path("/tmp/mcp-bridges")


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return default


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_bridge_running(name: str) -> bool:
    pidfile = PID_DIR / f"mcp-{name}.pid"
    if not pidfile.exists():
        return False
    try:
        pid = int(pidfile.read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def start_bridge(name: str, port: int, cmd: str, args: list[str]) -> bool:
    script_dir = HARNESS_DIR / "scripts"
    bridge_js = script_dir / "mcp_stdio_to_http_bridge.js"
    env = {**os.environ, "HARNESS_DIR": str(HARNESS_DIR)}
    full_args = ["node", str(bridge_js), "--port", str(port), "--", cmd] + args
    try:
        subprocess.Popen(
            full_args,
            cwd=str(script_dir),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except (OSError, FileNotFoundError):
        return False


def ensure_mcp_bridges() -> int:
    """Start any missing MCP bridges. Returns count started."""
    if not MCP_CONFIG.exists():
        return 0
    config = load_json(MCP_CONFIG, {})
    bridges = config.get("bridges", {})
    harness_dir = str(HARNESS_DIR)
    started = 0
    for name, cfg in bridges.items():
        if not cfg.get("enabled", True):
            continue
        if name == "github" and not os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN"):
            continue
        port = cfg.get("port")
        cmd = cfg.get("command")
        args = [a.replace("${HARNESS_DIR}", harness_dir) for a in cfg.get("args", [])]
        if not port or not cmd:
            continue
        if is_bridge_running(name):
            continue
        if start_bridge(name, port, cmd, args):
            started += 1
            print(f"[config_watcher] Started MCP bridge: {name} on port {port}")
    return started


def maybe_restart_openclaw() -> bool:
    """Restart OpenClaw only if openclaw.json changed."""
    if not OPENCLAW_CONFIG.exists():
        return False
    current = file_hash(OPENCLAW_CONFIG)
    hashes = load_json(CONFIG_HASH_FILE, {})
    prev = hashes.get("openclaw")
    if prev == current:
        return False
    try:
        subprocess.run(
            ["docker", "restart", OPENCLAW_CONTAINER],
            capture_output=True,
            timeout=30,
        )
        hashes["openclaw"] = current
        save_json(CONFIG_HASH_FILE, hashes)
        print(f"[config_watcher] Restarted OpenClaw (config changed)")
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def main() -> int:
    os.chdir(HARNESS_DIR)
    if (HARNESS_DIR / ".env").exists():
        with open(HARNESS_DIR / ".env") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
    ensure_mcp_bridges()
    maybe_restart_openclaw()
    return 0


if __name__ == "__main__":
    sys.exit(main())
