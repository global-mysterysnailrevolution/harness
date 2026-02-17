#!/usr/bin/env python3
"""Add Codex documentation to AGENTS.md and add model alias to openclaw.json."""
import json
import shutil
from pathlib import Path
from datetime import datetime

AGENTS_MD = Path("/docker/openclaw-kx9d/data/.openclaw/workspace/AGENTS.md")
OPENCLAW_CONFIG = Path("/docker/openclaw-kx9d/data/.openclaw/openclaw.json")

# 1. Update AGENTS.md
print("=== Updating AGENTS.md ===")
if AGENTS_MD.exists():
    content = AGENTS_MD.read_text()
    if "## Codex CLI (gpt-5.3-codex)" not in content:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(AGENTS_MD, AGENTS_MD.with_suffix(f".md.bak.{ts}"))
        content += """
## Codex CLI (gpt-5.3-codex)

The Codex CLI runs as an MCP bridge on port 8105, giving you access to **gpt-5.3-codex** (OpenAI's most capable coding model) even though it's not yet available via the standard API.

**When to use Codex vs standard models:**
- Use Codex for: complex multi-file refactors, architecture decisions, hard debugging, code generation requiring deep reasoning
- Use standard models for: simple queries, status checks, formatting, boilerplate

**Usage (from container via MCP bridge):**
The Codex bridge is at `https://172.18.0.1:8105/mcp` and exposes two tools:

1. **`codex`** - Start a new Codex session:
```json
{
  "prompt": "Refactor the authentication module to use JWT tokens",
  "cwd": "/data/harness",
  "approval-policy": "on-failure",
  "sandbox": "workspace-write"
}
```

2. **`codex-reply`** - Continue an existing session:
```json
{
  "threadId": "<thread-id-from-previous-call>",
  "prompt": "Now add unit tests for the JWT validation"
}
```

**Approval policies:** `untrusted` (safest), `on-failure`, `on-request`, `never`
**Sandbox modes:** `read-only`, `workspace-write`, `danger-full-access`

**Direct CLI usage (on VPS host):**
```bash
codex exec "describe what this repo does" --cwd /opt/harness
codex "refactor the bridge scripts" --approval-policy on-failure
```
"""
        AGENTS_MD.write_text(content)
        print("  Added Codex CLI section")
    else:
        print("  Codex section already present")
else:
    print("  ERROR: AGENTS.md not found")

# 2. Add gpt-5.3-codex model alias to openclaw.json
print("\n=== Updating openclaw.json models ===")
if OPENCLAW_CONFIG.exists():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(OPENCLAW_CONFIG, OPENCLAW_CONFIG.with_suffix(f".json.bak.{ts}"))

    config = json.loads(OPENCLAW_CONFIG.read_text())
    models = config.get("agents", {}).get("defaults", {}).get("models", {})

    if "openai/gpt-5.3-codex" not in models:
        models["openai/gpt-5.3-codex"] = {
            "alias": "Codex 5.3"
        }
        config["agents"]["defaults"]["models"] = models
        OPENCLAW_CONFIG.write_text(json.dumps(config, indent=2))
        print("  Added openai/gpt-5.3-codex model alias")
    else:
        print("  gpt-5.3-codex already configured")

    # Also add it as a fallback
    fallbacks = config.get("agents", {}).get("defaults", {}).get("model", {}).get("fallbacks", [])
    print(f"  Current fallbacks: {fallbacks}")
else:
    print("  ERROR: openclaw.json not found")

print("\n=== Done ===")
