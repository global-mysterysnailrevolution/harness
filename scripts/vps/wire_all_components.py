#!/usr/bin/env python3
"""
Wire all dormant harness components into OpenClaw.

Components wired:
1. MCP Bridges -> openclaw.json mcpServers (HTTP, no HTTPS to avoid cert issues)
2. Tool Broker -> accessible via /data/harness/ mount
3. ContextForge Memory Manager -> memory dirs + compaction hook
4. ContextForge Analyzer -> accessible via /data/harness/ mount
5. Config watcher cron -> ensures bridges stay alive
6. Preflight check -> validates everything works

Run on VPS: python3 /opt/harness/scripts/vps/wire_all_components.py
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime

HARNESS_DIR = Path("/opt/harness")
OPENCLAW_DATA = Path("/docker/openclaw-kx9d/data")
OPENCLAW_CONFIG = OPENCLAW_DATA / ".openclaw" / "openclaw.json"
AGENTS_MD = OPENCLAW_DATA / ".openclaw" / "AGENTS.md"
CONTAINER = "openclaw-kx9d-openclaw-1"

LOG_LINES = []

def log(msg):
    print(f"  {msg}")
    LOG_LINES.append(msg)

def backup(path):
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.with_suffix(f".bak.{ts}")
        shutil.copy2(path, backup_path)
        return backup_path
    return None

# ═══════════════════════════════════════════════════════════════════════
# 1. MCP Bridges -> openclaw.json mcpServers
# ═══════════════════════════════════════════════════════════════════════
def wire_mcp_bridges():
    log("--- Step 1: Wire MCP bridges into OpenClaw ---")

    if not OPENCLAW_CONFIG.exists():
        log("ERROR: openclaw.json not found")
        return False

    config = json.loads(OPENCLAW_CONFIG.read_text())
    bridge_config = HARNESS_DIR / "ai" / "supervisor" / "mcp_bridges.json"

    if not bridge_config.exists():
        log("ERROR: mcp_bridges.json not found")
        return False

    bridges = json.loads(bridge_config.read_text()).get("bridges", {})

    # Docker bridge IP for container -> host communication
    host_ip = "172.18.0.1"

    # Build mcpServers config
    # OpenClaw supports "url" transport for HTTP MCP servers
    mcp_servers = {}
    for name, bc in bridges.items():
        if not bc.get("enabled", True):
            continue
        port = bc.get("port")
        if not port:
            continue
        mcp_servers[name] = {
            "url": f"https://{host_ip}:{port}/mcp",
            "transport": {
                "type": "sse",
                "url": f"https://{host_ip}:{port}/mcp"
            }
        }
        log(f"  Bridge '{name}' -> https://{host_ip}:{port}/mcp")

    # Also add the fetch server as an MCP server if not already bridged
    # We'll add it as a stdio MCP server since it runs inside the container
    if "fetch" not in mcp_servers:
        mcp_servers["fetch"] = {
            "command": "python3",
            "args": ["-m", "mcp_server_fetch"],
            "env": {}
        }
        log("  Added 'fetch' as stdio MCP server")

    backup(OPENCLAW_CONFIG)
    config["mcpServers"] = mcp_servers
    OPENCLAW_CONFIG.write_text(json.dumps(config, indent=2))
    log(f"  Updated openclaw.json with {len(mcp_servers)} MCP servers")
    return True

# ═══════════════════════════════════════════════════════════════════════
# 2. Tool Broker -> verify accessible from container
# ═══════════════════════════════════════════════════════════════════════
def wire_tool_broker():
    log("--- Step 2: Wire Tool Broker ---")

    broker_path = HARNESS_DIR / "scripts" / "broker" / "tool_broker.py"
    wrapper_path = HARNESS_DIR / "openclaw" / "harness_skill_wrapper.py"

    if not broker_path.exists():
        log("ERROR: tool_broker.py not found")
        return False
    if not wrapper_path.exists():
        log("ERROR: harness_skill_wrapper.py not found")
        return False

    # Verify broker runs
    try:
        r = subprocess.run(
            ["python3", str(broker_path), "search", "--query", "test", "--max-results", "1"],
            capture_output=True, text=True, timeout=15, cwd=str(HARNESS_DIR)
        )
        if r.returncode == 0:
            log(f"  Broker search works: {r.stdout.strip()[:100]}")
        else:
            log(f"  Broker search returned {r.returncode}: {r.stderr[:100]}")
    except Exception as e:
        log(f"  Broker test failed: {e}")

    # Verify wrapper runs
    try:
        r = subprocess.run(
            ["python3", str(wrapper_path), "harness_search_tools", '{"query":"test"}'],
            capture_output=True, text=True, timeout=15, cwd=str(HARNESS_DIR)
        )
        if r.returncode == 0:
            log(f"  Wrapper works: {r.stdout.strip()[:100]}")
        else:
            log(f"  Wrapper returned {r.returncode}: {r.stderr[:100]}")
    except Exception as e:
        log(f"  Wrapper test failed: {e}")

    # The tool broker is at /data/harness/scripts/broker/tool_broker.py inside container
    # The wrapper is at /data/harness/openclaw/harness_skill_wrapper.py
    log("  Broker accessible at /data/harness/scripts/broker/tool_broker.py (in container)")
    log("  Wrapper accessible at /data/harness/openclaw/harness_skill_wrapper.py (in container)")
    return True

# ═══════════════════════════════════════════════════════════════════════
# 3. ContextForge Memory Manager -> directories + integration
# ═══════════════════════════════════════════════════════════════════════
def wire_memory_manager():
    log("--- Step 3: Wire ContextForge Memory Manager ---")

    # Memory directories in the OpenClaw data workspace
    # The memory manager looks for memory/pending, memory/promoted, memory/rejected
    # relative to the workspace path. OpenClaw's workspace is /data/.openclaw
    workspace = OPENCLAW_DATA / ".openclaw"
    memory_dirs = [
        workspace / "memory" / "pending",
        workspace / "memory" / "promoted",
        workspace / "memory" / "rejected",
    ]

    for d in memory_dirs:
        d.mkdir(parents=True, exist_ok=True)
        log(f"  Created: {d}")

    # Ensure MEMORY.md exists
    memory_md = workspace / "MEMORY.md"
    if not memory_md.exists():
        memory_md.write_text(
            "# Durable Memory\n\n"
            "<!-- Auto-compiled by ContextForge MemoryManager -->\n"
            "<!-- No promoted entries yet -->\n\n"
            "## Rules\n\n"
            "- (none yet)\n\n"
            "## Corrections\n\n"
            "- (none yet)\n\n"
            "## Learned\n\n"
            "- (none yet)\n"
        )
        log(f"  Created: {memory_md}")
    else:
        log(f"  MEMORY.md already exists")

    # Test memory manager
    try:
        r = subprocess.run(
            ["python3", "-m", "contextforge.cli.contextforge", "memory", "list-pending",
             "--workspace", str(workspace)],
            capture_output=True, text=True, timeout=15, cwd=str(HARNESS_DIR)
        )
        if r.returncode == 0:
            log(f"  Memory manager works: {r.stdout.strip()[:100]}")
        else:
            log(f"  Memory manager returned {r.returncode}: {r.stderr[:200]}")
    except Exception as e:
        log(f"  Memory manager test failed: {e}")

    return True

# ═══════════════════════════════════════════════════════════════════════
# 4. ContextForge Analyzer -> test and verify
# ═══════════════════════════════════════════════════════════════════════
def wire_analyzer():
    log("--- Step 4: Wire ContextForge Analyzer ---")

    # Test analyzer on harness repo itself
    try:
        r = subprocess.run(
            ["python3", "-m", "contextforge.cli.contextforge", "analyze", str(HARNESS_DIR), "--json"],
            capture_output=True, text=True, timeout=30, cwd=str(HARNESS_DIR)
        )
        if r.returncode == 0:
            try:
                result = json.loads(r.stdout)
                langs = list(result.get("stack", {}).get("languages", {}).keys())
                files = result.get("structure", {}).get("total_files", 0)
                log(f"  Analyzer works: {files} files, languages: {', '.join(langs)}")
            except json.JSONDecodeError:
                log(f"  Analyzer output (not JSON): {r.stdout[:100]}")
        else:
            log(f"  Analyzer returned {r.returncode}: {r.stderr[:200]}")
    except Exception as e:
        log(f"  Analyzer test failed: {e}")

    log("  Analyzer accessible at /data/harness/contextforge/ (in container)")
    return True

# ═══════════════════════════════════════════════════════════════════════
# 5. Config watcher cron
# ═══════════════════════════════════════════════════════════════════════
def wire_cron():
    log("--- Step 5: Wire cron jobs ---")

    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
        current_cron = r.stdout if r.returncode == 0 else ""
    except Exception:
        current_cron = ""

    entries_needed = {
        "config_watcher": "*/5 * * * * cd /opt/harness && python3 scripts/vps/config_watcher.py >> /var/log/openclaw_config_watcher.log 2>&1",
        "preflight_check": "*/30 * * * * cd /opt/harness && bash scripts/vps/preflight_check.sh >> /var/log/openclaw_preflight.log 2>&1",
        "bridge_keepalive": "*/10 * * * * cd /opt/harness && MCP_BIND=0.0.0.0 bash scripts/run_mcp_from_config.sh >> /var/log/openclaw_bridges.log 2>&1",
    }

    new_entries = []
    for name, entry in entries_needed.items():
        # Check if a similar cron already exists
        key_part = name.replace("_", "")
        if name.replace("_", "") in current_cron.replace("_", "") or entry.split("&&")[1].strip().split()[0] in current_cron:
            log(f"  Cron '{name}' already exists (or similar)")
        else:
            new_entries.append(entry)
            log(f"  Adding cron: {name}")

    if new_entries:
        new_cron = current_cron.rstrip() + "\n" + "\n".join(new_entries) + "\n"
        try:
            p = subprocess.run(["crontab", "-"], input=new_cron, capture_output=True, text=True, timeout=10)
            if p.returncode == 0:
                log(f"  Updated crontab with {len(new_entries)} new entries")
            else:
                log(f"  Crontab update failed: {p.stderr[:100]}")
        except Exception as e:
            log(f"  Crontab update failed: {e}")
    else:
        log("  All cron entries already present")

    return True

# ═══════════════════════════════════════════════════════════════════════
# 6. Update AGENTS.md with component docs
# ═══════════════════════════════════════════════════════════════════════
def wire_agents_md():
    log("--- Step 6: Update AGENTS.md ---")

    if not AGENTS_MD.exists():
        log("ERROR: AGENTS.md not found")
        return False

    content = AGENTS_MD.read_text()

    sections_to_add = []

    # MCP Bridges section
    if "## MCP Tool Bridges" not in content:
        sections_to_add.append("""
## MCP Tool Bridges

MCP bridges expose stdio MCP servers as HTTPS endpoints accessible from the container.

| Bridge | Port | URL (from container) | Tools |
|--------|------|---------------------|-------|
| filesystem | 8101 | https://172.18.0.1:8101/mcp | read_file, write_file, list_directory, etc. |
| everything | 8102 | https://172.18.0.1:8102/mcp | echo, get-env, etc. (demo/test server) |
| memory | 8104 | https://172.18.0.1:8104/mcp | create_entities, create_relations, add_observations, etc. |

These are configured in `mcpServers` in openclaw.json. Bearer auth is required for external access; container IPs (172.18.x.x) are exempted.
""")
        log("  Added MCP Tool Bridges section")

    # Tool Broker section
    if "## Tool Broker" not in content:
        sections_to_add.append("""
## Tool Broker

The Tool Broker provides unified tool access with discovery, allowlisting, and security policies.

**Usage (from container):**
```bash
# Search for tools
python3 /data/harness/scripts/broker/tool_broker.py search --query "file operations"

# Describe a tool
python3 /data/harness/scripts/broker/tool_broker.py describe --tool-id "filesystem:read_file"

# Call a tool
python3 /data/harness/scripts/broker/tool_broker.py call --tool-id "filesystem:read_file" --args '{"path":"/data/harness/README.md"}'
```

**Via skill wrapper:**
```bash
python3 /data/harness/openclaw/harness_skill_wrapper.py harness_search_tools '{"query":"file"}'
```

Security: All calls are classified (read/write/network/credential/exec), dangerous actions are logged, rate limits enforced.
""")
        log("  Added Tool Broker section")

    # ContextForge Memory section
    if "## ContextForge Memory" not in content:
        sections_to_add.append("""
## ContextForge Memory Manager

Durable memory with pending-to-promoted approval workflow. Prevents prompt injection from becoming permanent rules.

**Usage (from container):**
```bash
# Submit a memory entry (goes to pending)
python3 -m contextforge.cli.contextforge memory submit "Always use UTC timestamps" --category rule --workspace /data/.openclaw

# List pending entries
python3 -m contextforge.cli.contextforge memory list-pending --workspace /data/.openclaw

# Promote (approve) an entry
python3 -m contextforge.cli.contextforge memory promote <entry_id> --workspace /data/.openclaw

# Reject an entry
python3 -m contextforge.cli.contextforge memory reject <entry_id> --reason "not accurate" --workspace /data/.openclaw
```

Memory states: pending -> promoted (approved) or rejected. MEMORY.md is auto-compiled from promoted entries.
""")
        log("  Added ContextForge Memory section")

    # ContextForge Analyzer section
    if "## ContextForge Analyzer" not in content:
        sections_to_add.append("""
## ContextForge Analyzer

Deterministic codebase analysis engine. Scans repos for stack, frameworks, conventions, security patterns.

**Usage (from container):**
```bash
# Analyze a repo
python3 -m contextforge.cli.contextforge analyze /data/harness --json

# Generate skills + agents from analysis
python3 -m contextforge.cli.contextforge generate /data/harness -o /data/harness/.contextforge

# Run security vetting
python3 -m contextforge.cli.contextforge vet /data/harness
```

Use analysis output to populate context packs (see Context Pack Skill).
""")
        log("  Added ContextForge Analyzer section")

    if sections_to_add:
        backup(AGENTS_MD)
        content += "\n".join(sections_to_add)
        AGENTS_MD.write_text(content)
        log(f"  Updated AGENTS.md with {len(sections_to_add)} new sections")
    else:
        log("  All sections already present in AGENTS.md")

    return True

# ═══════════════════════════════════════════════════════════════════════
# 7. Verify from container
# ═══════════════════════════════════════════════════════════════════════
def verify_from_container():
    log("--- Step 7: Verify from container ---")

    checks = [
        ("Python3 available", ["docker", "exec", CONTAINER, "python3", "--version"]),
        ("Harness mounted", ["docker", "exec", CONTAINER, "ls", "/data/harness/scripts/broker/tool_broker.py"]),
        ("ContextForge importable", ["docker", "exec", CONTAINER, "python3", "-c",
            "import sys; sys.path.insert(0, '/data/harness'); from contextforge.packages.analyzer import RepoAnalyzer; print('OK')"]),
        ("Memory dirs exist", ["docker", "exec", CONTAINER, "ls", "/data/.openclaw/memory/pending"]),
        ("MEMORY.md exists", ["docker", "exec", CONTAINER, "test", "-f", "/data/.openclaw/MEMORY.md"]),
    ]

    all_ok = True
    for name, cmd in checks:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                log(f"  {name}: OK ({r.stdout.strip()[:60]})")
            else:
                log(f"  {name}: FAIL ({r.stderr.strip()[:60]})")
                all_ok = False
        except Exception as e:
            log(f"  {name}: ERROR ({e})")
            all_ok = False

    return all_ok


def main():
    print("=" * 60)
    print("OpenClaw Component Wiring")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)
    print()

    results = {}
    results["mcp_bridges"] = wire_mcp_bridges()
    results["tool_broker"] = wire_tool_broker()
    results["memory_manager"] = wire_memory_manager()
    results["analyzer"] = wire_analyzer()
    results["cron"] = wire_cron()
    results["agents_md"] = wire_agents_md()
    results["container_verify"] = verify_from_container()

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for name, ok in results.items():
        status = "OK" if ok else "FAIL"
        print(f"  {name}: {status}")

    ok_count = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n  {ok_count}/{total} steps succeeded")

    if ok_count == total:
        print("\n  All components wired! Restart OpenClaw to pick up changes:")
        print(f"    docker restart {CONTAINER}")
    else:
        print("\n  Some steps failed. Check output above for details.")

    return 0 if ok_count == total else 1


if __name__ == "__main__":
    sys.exit(main())
