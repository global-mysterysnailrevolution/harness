#!/usr/bin/env python3
"""Set up Codex CLI on VPS with API key auth and MCP server bridge."""
import json
import os
import subprocess
import sys
from pathlib import Path

CODEX_HOME = Path.home() / ".codex"
HARNESS_DIR = Path("/opt/harness")
OPENCLAW_ENV = Path("/docker/openclaw-kx9d/.env")

def get_openai_key():
    """Extract OPENAI_API_KEY from OpenClaw .env."""
    if not OPENCLAW_ENV.exists():
        return None
    for line in OPENCLAW_ENV.read_text().splitlines():
        line = line.strip()
        if line.startswith("OPENAI_API_KEY=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

def setup_config():
    """Create Codex config.toml for headless VPS usage."""
    CODEX_HOME.mkdir(parents=True, exist_ok=True)

    config = CODEX_HOME / "config.toml"
    config_content = """\
# Codex CLI config for OpenClaw VPS (headless)
# Store credentials in file (no keyring on headless server)
cli_auth_credentials_store = "file"

# Use API key auth (not ChatGPT login)
forced_login_method = "api"

# Default model
model = "gpt-5.3-codex"

# Sandbox: read-only by default for safety
# Override per-call with --sandbox flag
# sandbox_permissions = ["disk-full-read-access"]
"""
    config.write_text(config_content)
    print(f"  Created {config}")

def setup_auth():
    """Create auth.json with API key."""
    api_key = get_openai_key()
    if not api_key:
        print("ERROR: Could not find OPENAI_API_KEY in OpenClaw .env")
        return False

    auth_file = CODEX_HOME / "auth.json"
    auth_data = {
        "api_key": api_key,
    }
    auth_file.write_text(json.dumps(auth_data, indent=2))
    os.chmod(auth_file, 0o600)
    print(f"  Created {auth_file} (mode 600)")
    print(f"  API key: {api_key[:8]}...{api_key[-4:]}")
    return True

def test_codex():
    """Quick test of Codex CLI."""
    try:
        r = subprocess.run(
            ["codex", "--version"],
            capture_output=True, text=True, timeout=10
        )
        print(f"  Codex version: {r.stdout.strip()}")
    except Exception as e:
        print(f"  Codex version check failed: {e}")
        return False

    # Test a simple exec with the API key
    try:
        env = {**os.environ, "CODEX_HOME": str(CODEX_HOME)}
        r = subprocess.run(
            ["codex", "exec", "-q", "echo hello from codex"],
            capture_output=True, text=True, timeout=30, env=env
        )
        if r.returncode == 0:
            print(f"  Codex exec test: OK ({r.stdout.strip()[:60]})")
        else:
            print(f"  Codex exec test: exit {r.returncode}")
            if r.stderr:
                print(f"    stderr: {r.stderr.strip()[:200]}")
    except subprocess.TimeoutExpired:
        print("  Codex exec test: timeout (expected for first run)")
    except Exception as e:
        print(f"  Codex exec test: {e}")

    return True

def setup_bridge_config():
    """Add codex to the MCP bridges config."""
    bridge_config = HARNESS_DIR / "ai" / "supervisor" / "mcp_bridges.json"
    if not bridge_config.exists():
        print(f"  ERROR: {bridge_config} not found")
        return False

    config = json.loads(bridge_config.read_text())
    bridges = config.get("bridges", {})

    if "codex" not in bridges:
        bridges["codex"] = {
            "port": 8105,
            "command": "codex",
            "args": ["mcp-server"],
            "enabled": True,
            "note": "Codex CLI MCP server - provides gpt-5.3-codex access"
        }
        config["bridges"] = bridges
        bridge_config.write_text(json.dumps(config, indent=2))
        print("  Added codex bridge to mcp_bridges.json (port 8105)")
    else:
        print("  Codex bridge already in mcp_bridges.json")

    return True

def main():
    print("=== Setting up Codex CLI ===")
    print()
    print("1. Config:")
    setup_config()
    print()
    print("2. Auth:")
    ok = setup_auth()
    if not ok:
        return 1
    print()
    print("3. Test:")
    test_codex()
    print()
    print("4. Bridge config:")
    setup_bridge_config()
    print()
    print("=== Done ===")
    print("Start the Codex MCP bridge with:")
    print("  MCP_BIND=0.0.0.0 node /opt/harness/scripts/mcp_stdio_to_http_bridge.js --port 8105 -- codex mcp-server &")
    print()
    print("Or restart all bridges:")
    print("  bash /opt/harness/scripts/vps/restart_bridges.sh")
    return 0

if __name__ == "__main__":
    sys.exit(main())
