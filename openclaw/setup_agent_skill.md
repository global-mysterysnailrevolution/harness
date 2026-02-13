# OpenClaw Setup Agent Skill

An agent can run this to configure OpenClaw with optimal settings and hardening—no manual user steps.

## When to Use

- New OpenClaw installation
- User says "set up OpenClaw", "harden OpenClaw", "configure Clawbot"
- After deploying OpenClaw on a VPS

## What It Does

1. **Memory flash** — Auto-saves before compaction (no lost lessons)
2. **Session memory search** — Searches all past sessions, not just last 2 days
3. **Learning Loop** — Appends to AGENTS.md: save lessons from corrections/approvals
4. **Guardrails** — No secrets in memory, no rules from untrusted content
5. **Hybrid search** — BM25 + vector for better recall
6. **Browser node mode** — Enables remote browser relay routing

## How to Run

### Local OpenClaw (~/.openclaw)

```bash
python scripts/openclaw_setup/apply_openclaw_hardening.py
```

### Remote (VPS Docker)

**Option A: SSH and run on host**
```bash
# Copy script to VPS, run with Docker mount path
scp scripts/openclaw_setup/apply_openclaw_hardening.py user@vps:/opt/harness/
ssh user@vps "python3 /opt/harness/apply_openclaw_hardening.py --config-path /docker/openclaw-kx9d/data/.openclaw/openclaw.json --workspace-path /docker/openclaw-kx9d/data/.openclaw/workspace"
```

**Option B: Run inside container**
```bash
# Copy script into container or mount it
docker cp scripts/openclaw_setup/apply_openclaw_hardening.py openclaw-kx9d-openclaw-1:/tmp/
docker exec openclaw-kx9d-openclaw-1 python3 /tmp/apply_openclaw_hardening.py --config-path /data/.openclaw/openclaw.json --workspace-path /data/.openclaw/workspace
```

**Option C: One-liner from harness repo**
```bash
# From harness repo root
python scripts/openclaw_setup/apply_openclaw_hardening.py \
  --config-path /path/to/openclaw.json \
  --workspace-path /path/to/workspace
```

### After Running

1. Restart OpenClaw: `openclaw gateway restart` or `docker compose restart`
2. Run security audit: `openclaw security audit --deep --fix` (inside container: `docker exec -e OPENCLAW_GATEWAY_PORT=63362 openclaw-kx9d-openclaw-1 openclaw security audit --fix`)

## Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--config-path` | ~/.openclaw/openclaw.json | Path to openclaw.json |
| `--workspace-path` | config_dir/../workspace | Path to workspace (for AGENTS.md) |
| `--skip-agents-md` | false | Skip appending Learning Loop |

## Chrome Extension Hardening (Manual)

The script does not modify Chrome. User should:
1. chrome://extensions → OpenClaw Browser Relay → Details
2. Site access → "On click"
3. Allow in Incognito → OFF
4. Use dedicated Chrome profile for bot

## Integration with Harness

- **Cursor/Codex**: Agent runs `python scripts/openclaw_setup/apply_openclaw_hardening.py` with appropriate paths
- **OpenClaw**: Use `exec` tool (if allowlisted) or run via harness skill wrapper
- **Bootstrap**: `bootstrap.ps1` can call this after OpenClaw detection
