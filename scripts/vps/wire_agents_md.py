#!/usr/bin/env python3
"""Add component documentation to AGENTS.md."""
import shutil
from pathlib import Path
from datetime import datetime

AGENTS_MD = Path("/docker/openclaw-kx9d/data/.openclaw/workspace/AGENTS.md")

if not AGENTS_MD.exists():
    print(f"ERROR: AGENTS.md not found at {AGENTS_MD}")
    exit(1)

content = AGENTS_MD.read_text()
sections_added = 0

# MCP Bridges section
if "## MCP Tool Bridges" not in content:
    content += """
## MCP Tool Bridges

MCP bridges expose stdio MCP servers as HTTPS endpoints accessible from the container.

| Bridge | Port | URL (from container) | Tools |
|--------|------|---------------------|-------|
| filesystem | 8101 | https://172.18.0.1:8101/mcp | read_file, write_file, list_directory, etc. |
| everything | 8102 | https://172.18.0.1:8102/mcp | echo, get-env, etc. (demo/test server) |
| memory | 8104 | https://172.18.0.1:8104/mcp | create_entities, create_relations, add_observations, etc. |

These are configured in `mcpServers` in openclaw.json. Bearer auth is required for external access; container IPs (172.18.x.x) are exempted.
"""
    sections_added += 1
    print("  Added MCP Tool Bridges section")

# Tool Broker section
if "## Tool Broker" not in content:
    content += """
## Tool Broker

The Tool Broker provides unified tool access with discovery, allowlisting, and security policies.

**Usage (from container):**
```bash
# Search for tools
python3 /data/harness/scripts/broker/tool_broker.py search --query "file operations"

# Describe a tool
python3 /data/harness/scripts/broker/tool_broker.py describe --tool-id "filesystem:read_file"

# Call a tool (with Gate B security)
python3 /data/harness/scripts/broker/tool_broker.py call --tool-id "filesystem:read_file" --args '{"path":"/data/harness/README.md"}'
```

**Via skill wrapper:**
```bash
python3 /data/harness/openclaw/harness_skill_wrapper.py harness_search_tools '{"query":"file"}'
```

Security: All calls are classified (read/write/network/credential/exec), dangerous actions are logged, rate limits enforced, secrets redacted.
"""
    sections_added += 1
    print("  Added Tool Broker section")

# ContextForge Memory section
if "## ContextForge Memory" not in content:
    content += """
## ContextForge Memory Manager

Durable memory with pending-to-promoted approval workflow. Prevents prompt injection from becoming permanent rules.

**Usage (from container):**
```bash
# Submit a memory entry (goes to pending)
cd /data/harness && python3 -m contextforge.cli.contextforge memory submit "Always use UTC timestamps" --category rule

# List pending entries
cd /data/harness && python3 -m contextforge.cli.contextforge memory list-pending

# Promote (approve) an entry
cd /data/harness && python3 -m contextforge.cli.contextforge memory promote <entry_id>

# Reject an entry
cd /data/harness && python3 -m contextforge.cli.contextforge memory reject <entry_id> --reason "not accurate"
```

Memory states: pending -> promoted (approved) or rejected. MEMORY.md is auto-compiled from promoted entries.
"""
    sections_added += 1
    print("  Added ContextForge Memory section")

# ContextForge Analyzer section
if "## ContextForge Analyzer" not in content:
    content += """
## ContextForge Analyzer

Deterministic codebase analysis engine. Scans repos for stack, frameworks, conventions, security patterns.

**Usage (from container):**
```bash
# Analyze a repo
cd /data/harness && python3 -m contextforge.cli.contextforge analyze /data/harness --json

# Full generation (skills + agents from analysis)
cd /data/harness && python3 -m contextforge.cli.contextforge generate /data/harness -o /data/harness/.contextforge

# Security vetting
cd /data/harness && python3 -m contextforge.cli.contextforge vet /data/harness
```

Use analysis output to populate context packs (see Context Pack Skill).
"""
    sections_added += 1
    print("  Added ContextForge Analyzer section")

if sections_added > 0:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(AGENTS_MD, AGENTS_MD.with_suffix(f".md.bak.{ts}"))
    AGENTS_MD.write_text(content)
    print(f"  Updated AGENTS.md with {sections_added} new sections")
else:
    print("  All sections already present in AGENTS.md")
