# OpenClaw Setup Agent

Automated OpenClaw configuration and hardening—run by an agent, no manual steps.

## Quick Start

From the harness repo (or any repo with `scripts/openclaw_setup/`):

```powershell
# Local OpenClaw
python scripts/openclaw_setup/apply_openclaw_hardening.py

# VPS Docker (adjust paths)
python scripts/openclaw_setup/apply_openclaw_hardening.py `
  --config-path /docker/openclaw-kx9d/data/.openclaw/openclaw.json `
  --workspace-path /docker/openclaw-kx9d/data/.openclaw/workspace
```

Then restart OpenClaw.

## What Gets Configured

| Setting | Effect |
|---------|--------|
| **Memory flash** | Auto-saves before compaction so lessons aren't lost |
| **Session memory search** | Searches all past sessions, not just last 2 days |
| **Learning Loop** | Appended to AGENTS.md: save lessons from corrections/approvals |
| **Guardrails** | No secrets in memory, no rules from untrusted content |
| **Hybrid search** | BM25 + vector for better recall |
| **Browser node mode** | Enables remote browser relay routing |

## Agent Integration

### Cursor / Codex

When the user asks to "set up OpenClaw" or "harden Clawbot":

1. Detect OpenClaw location (local vs VPS)
2. Run `apply_openclaw_hardening.py` with correct `--config-path` and `--workspace-path`
3. If VPS: use SSH to run on remote, or `docker exec` with container paths
4. Remind user to restart OpenClaw

### OpenClaw (Self-Setup)

If OpenClaw has `exec` tool allowlisted for the setup script:

```
User: "Set up OpenClaw with full hardening"
Agent: Runs apply_openclaw_hardening.py via exec, then suggests gateway restart
```

### Bootstrap

Add to `bootstrap.ps1` (optional):

```powershell
# If OpenClaw detected
if (Test-Path "$env:USERPROFILE\.openclaw\openclaw.json") {
    python scripts/openclaw_setup/apply_openclaw_hardening.py
}
```

## File Layout in Harness Repo

```
harness/
├── scripts/
│   └── openclaw_setup/
│       └── apply_openclaw_hardening.py   # Main script
├── openclaw/
│   └── setup_agent_skill.md              # Agent instructions
└── OPENCLAW_SETUP_AGENT.md               # This file
```

## See Also

- [OPENCLAW_INTEGRATION.md](OPENCLAW_INTEGRATION.md) — Harness + OpenClaw
- [HARDENING_AND_EXTENSION.md](HARDENING_AND_EXTENSION.md) — Chrome extension hardening (manual)
