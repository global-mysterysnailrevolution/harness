# Audit Logging for Claude Code
## Porting from OpenClaw `tool_broker.py`

**Document version**: 1.0
**Source system**: OpenClaw `tool_broker.py` — `_audit_log()`, `call_tool()`
**Target system**: Claude Code hook system + `/audit` command
**Status**: Implementation reference (sole source of truth)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Problem Statement](#2-problem-statement)
3. [Source Analysis](#3-source-analysis)
4. [Target Architecture](#4-target-architecture)
5. [File Layout](#5-file-layout)
6. [Data Structures](#6-data-structures)
7. [Implementation Plan](#7-implementation-plan)
8. [Integration Points](#8-integration-points)
9. [Configuration](#9-configuration)
10. [Query & Analysis](#10-query--analysis)
11. [Testing Plan](#11-testing-plan)
12. [Example Usage](#12-example-usage)
13. [Hook Implementation Detail](#13-hook-implementation-detail)

---

## 1. Overview

Audit logging captures every tool call made by Claude Code agents and commands into a structured, append-only JSONL file. Each entry records what tool was called, by which agent, with what argument fingerprint, whether it was blocked, and what classification it received (read/write/network/credential/exec).

The log is the ground truth for:
- **Security review** — what did the AI actually do?
- **Debugging** — why did a tool call fail or get blocked?
- **Compliance** — did any agent exceed its allowlist?
- **Performance** — which tools are called most, by whom?
- **Incident response** — reconstruct the exact sequence of events in a session

This feature is a direct port of OpenClaw's `_audit_log()` function and the logging side of `call_tool()`. The port adapts the Python JSONL writer into Claude Code's bash hook system while preserving exact log entry semantics.

---

## 2. Problem Statement

### Current Gap

Claude Code currently has two hook stubs:

```
~/.claude/hooks/trace-pre.sh
~/.claude/hooks/trace-post.sh
```

Both are skeleton files. No tool call data is captured. No persistent record of agent activity exists. The result:

- **Zero observability**: You cannot answer "what did the AI do last session?" without reading the entire conversation transcript.
- **No anomaly detection baseline**: Without a log, you cannot identify unusual tool usage patterns.
- **No audit trail for dangerous actions**: When an agent calls a shell command or credential tool, there is no record — not even a hash of the arguments.
- **Debugging is blind**: When a workflow fails, there is no machine-readable record of which tool, in which step, returned which error.
- **No rate limit enforcement evidence**: Even if rate limiting is conceptually described in the tool-broker agent's prompt, there is no log to verify whether limits were respected.

### Security Model Requirement

The harness security model requires that every tool call be:
1. **Classified** (read/write/network/credential/exec) before execution
2. **Logged** after execution regardless of outcome
3. **Flagged** if the classification is a dangerous action class
4. **Queryable** after the fact by the user or by other agents

Without the log, (3) and (4) are impossible, and (1) and (2) are unverifiable.

### Windows Context

Claude Code runs on Windows with bash. Python is available but adds a runtime dependency. The implementation therefore uses bash for the hook layer (compatible with the existing hook infrastructure) and optionally calls a lightweight Python helper only for rotation and complex queries.

---

## 3. Source Analysis

### 3.1 Log Path Resolution

```python
_AUDIT_LOG_PATH = Path(os.environ.get("HARNESS_DIR", Path.cwd())) / "ai" / "supervisor" / "audit_log.jsonl"
```

OpenClaw places the log relative to `HARNESS_DIR`, inside the supervisor's directory. This keeps the log co-located with security policy files. The environment variable fallback to `cwd()` means the log appears in the project directory when `HARNESS_DIR` is not set.

**Port decision**: Claude Code uses a fixed global path (`~/.claude/audit/tool-calls.jsonl`) rather than a project-relative path, because:
- Claude Code's hooks execute without a reliable project CWD
- A global path makes `/audit` queries work across all sessions without path discovery
- Multiple project logs would fragment the audit trail

### 3.2 The `_audit_log()` Function

```python
def _audit_log(entry: Dict[str, Any]):
    _AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry["timestamp"] = datetime.now().isoformat()
    with open(_AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

Key behaviors:
- **Idempotent directory creation** — `mkdir(parents=True, exist_ok=True)` ensures the log directory is created on first write without error on subsequent writes.
- **Timestamp injection** — the timestamp is added at write time, not call time. This means the timestamp reflects log write latency, not the moment `_audit_log()` was called. In practice these differ by microseconds.
- **Append-only** — `"a"` mode. The file is never truncated by the logger itself. Rotation is handled separately.
- **UTF-8 with non-ASCII passthrough** — `ensure_ascii=False` allows non-ASCII characters in tool arguments to be logged as-is rather than escaped.
- **No locking** — OpenClaw runs in a single-threaded async loop, so no file locking is needed. The Claude Code port similarly runs in a bash subshell per hook invocation; sequential writes are safe because bash `>>` appends atomically on POSIX systems (and Windows NTFS for small writes).

### 3.3 Events Logged by `call_tool()`

The broker logs these event types:

| Event | When | Additional Fields |
|-------|------|-------------------|
| `call_tool` | Every successful tool call | `status: ok` |
| `call_blocked` | Tool call blocked before execution | `reason`, `status: blocked` |
| `dangerous_action` | Call classified as exec/credential/network | `action_class`, `status: ok` or `status: blocked` |

For every event, these fields are always present:
- `event` — event type string
- `tool_id` — the MCP tool identifier (e.g., `bash`, `read_file`, `github_create_pr`)
- `agent_id` — which agent made the call (e.g., `supervisor`, `implementer`, `browser`)
- `action_class` — classification result from `classify_action()`
- `args_hash` — SHA256 of the JSON-serialized arguments (not raw args, to avoid logging secrets)
- `server` — which MCP server the tool lives on
- `status` — `ok`, `error`, or `blocked`
- `timestamp` — ISO 8601 datetime

Blocked calls additionally carry:
- `reason` — one of `allowlist`, `rate_limit`, `argument_validation`, `budget`

Error calls additionally carry:
- `error` — error message string (not stack trace)

### 3.4 Arguments Hash

```python
"args_hash": hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
```

The hash uses `sort_keys=True` for determinism — identical argument sets always produce the same hash regardless of key ordering. This enables detecting repeated identical calls (potential loops) and cross-referencing log entries with known-safe call signatures.

**Security note**: Raw arguments are deliberately not logged. Tool arguments may contain file contents, API keys, user data, or other sensitive material. The hash allows correlation (two log entries with the same `args_hash` used identical arguments) without exposing the content.

### 3.5 Dangerous Action Detection

```python
_DANGEROUS_ACTIONS = {"exec", "credential", "network"}
```

The broker checks `classify_action()` and, if the result is in `_DANGEROUS_ACTIONS`, emits a `dangerous_action` event alongside the normal `call_tool` event. This means dangerous calls appear twice in the log — once as the action event and once as the danger flag. The dual-event pattern allows simple `grep dangerous_action` audits without requiring join logic.

---

## 4. Target Architecture

### 4.1 Component Map

```
Claude Code Hook System
│
├── ~/.claude/hooks/trace-post.sh          ← PRIMARY: captures every tool call
│   │   Reads: CLAUDE_TOOL_NAME, CLAUDE_TOOL_INPUT, CLAUDE_TOOL_OUTPUT
│   │   Writes: ~/.claude/audit/tool-calls.jsonl
│   └── Calls: ~/.claude/audit/rotate.sh   ← Rotation (keep 10k entries / 30 days)
│
├── ~/.claude/audit/
│   ├── tool-calls.jsonl                   ← Append-only audit log
│   ├── rotate.sh                          ← Log rotation script
│   └── .last-rotation                     ← Rotation state marker
│
├── ~/.claude/commands/audit.md            ← /audit command: query interface
│
└── ~/.claude/plugins/action-policy.json  ← Classification config (shared with action-classification.md)
```

### 4.2 Hook Execution Model

Claude Code invokes hooks as subshell processes. The hook receives tool call data via environment variables set by Claude Code's hook runner:

| Variable | Content |
|----------|---------|
| `CLAUDE_TOOL_NAME` | Tool identifier (e.g., `Bash`, `Read`, `WebFetch`) |
| `CLAUDE_TOOL_INPUT` | JSON string of tool arguments |
| `CLAUDE_TOOL_OUTPUT` | JSON string of tool result (post hooks only) |
| `CLAUDE_SESSION_ID` | Session identifier |
| `CLAUDE_AGENT_ID` | Agent identifier if set by harness convention |

**Important**: Claude Code's native tools use PascalCase names (`Bash`, `Read`, `Edit`, `Glob`, `Grep`, `Write`). MCP tools use their server-prefixed names (e.g., `mcp__chrome-devtools__navigate_page`). The hook must handle both naming conventions.

### 4.3 Agent ID Resolution

OpenClaw passes `agent_id` explicitly to every `call_tool()` invocation because it manages agents as explicit objects. Claude Code does not have this: the hook runs in the context of Claude Code's native execution without a passed agent identifier.

Resolution strategy (in order):
1. Read `CLAUDE_AGENT_ID` environment variable (harness convention — agents set this before spawning)
2. Read `CLAUDE_SESSION_ID` and look for agent context file at `~/.claude/audit/sessions/$CLAUDE_SESSION_ID.agent`
3. Default to `"claude-code"` (the top-level Claude Code process itself)

### 4.4 Server Resolution

OpenClaw knows the MCP server from its routing table. Claude Code hooks must infer it from the tool name:

- Native tools (`Bash`, `Read`, `Edit`, `Glob`, `Grep`, `Write`, `WebFetch`, `WebSearch`) → server: `"native"`
- MCP tools with prefix `mcp__<server>__<tool>` → server: the middle segment
- Skills invoked via `Skill` tool → server: `"skill-router"`

### 4.5 Classification in the Hook

The hook performs a lightweight keyword-score classification inline (no Python needed for the common path). See the [action classification document](./action-classification.md) for the full algorithm. The hook embeds a simplified version that covers 95% of cases; edge cases that require Python-level scoring fall back to `"read"` (the safe default).

### 4.6 Rotation Policy

Log rotation runs at the end of `trace-post.sh` if:
- Entry count exceeds 10,000, OR
- The oldest entry's timestamp is more than 30 days ago

Rotation truncates the file to the most recent 10,000 entries (not a rolling delete — a single atomic rewrite). The timestamp check uses the first line of the JSONL file.

---

## 5. File Layout

Every file listed here must be created or modified exactly as specified.

```
~/.claude/
├── hooks/
│   ├── trace-pre.sh                   MODIFY  (currently skeleton)
│   └── trace-post.sh                  MODIFY  (currently skeleton — primary implementation target)
├── audit/
│   ├── tool-calls.jsonl               CREATE  (on first write by hook)
│   ├── rotate.sh                      CREATE
│   └── .last-rotation                 CREATE  (on first rotation)
├── commands/
│   └── audit.md                       CREATE
└── plugins/
    └── action-policy.json             CREATE  (shared with action-classification)
```

### File Purposes

**`~/.claude/hooks/trace-post.sh`** (primary)
Runs after every tool call. Reads tool name, input, and output from environment. Computes action class, args hash, server name, agent ID. Appends a JSONL entry. Triggers rotation check.

**`~/.claude/hooks/trace-pre.sh`** (secondary)
Runs before every tool call. Currently used only to set up timing data (`CLAUDE_TOOL_START_MS`). May be extended later for pre-call blocking (see action-classification.md for blocking integration).

**`~/.claude/audit/tool-calls.jsonl`**
The audit log. Append-only JSONL. One JSON object per line. Never contains embedded newlines. UTF-8.

**`~/.claude/audit/rotate.sh`**
Called by `trace-post.sh` when rotation is needed. Uses Python (available on the system) for reliable line-count and date parsing, then rewrites the log atomically via a temp file.

**`~/.claude/audit/.last-rotation`**
Contains the ISO timestamp of the last rotation. Used to skip the expensive date-check on entries younger than 30 days.

**`~/.claude/commands/audit.md`**
The `/audit` slash command. Loaded by Claude Code's command system. Contains the prompt that instructs Claude to read, parse, and analyze `tool-calls.jsonl`.

**`~/.claude/plugins/action-policy.json`**
Configuration for both audit logging (which action classes are "dangerous") and action classification (keyword lists). Shared with action-classification.md to avoid duplication.

---

## 6. Data Structures

### 6.1 JSONL Entry Schema

Every log entry is a single JSON object on one line. Fields:

```jsonc
{
  // REQUIRED — always present
  "timestamp":    "2026-03-12T14:23:01.847Z",   // ISO 8601, UTC preferred
  "event":        "call_tool",                    // see Event Types below
  "tool_id":      "Bash",                         // tool name as received
  "agent_id":     "implementer",                  // resolved agent identifier
  "action_class": "exec",                         // read|write|network|credential|exec
  "args_hash":    "a3f9e2b1...",                  // SHA256 hex, 64 chars
  "server":       "native",                       // native|mcp-server-name|skill-router
  "status":       "ok",                           // ok|error|blocked

  // CONDITIONAL — event-dependent
  "reason":       "allowlist",                    // present when event=call_blocked
  "error":        "command not found: foobar",    // present when status=error
  "duration_ms":  142,                            // present when trace-pre.sh sets start time
  "dangerous":    true,                           // present when action_class in dangerous set

  // OPTIONAL — metadata
  "session_id":   "sess_abc123",                  // CLAUDE_SESSION_ID if available
  "tool_input_size": 847,                         // byte length of CLAUDE_TOOL_INPUT
  "tool_output_size": 2341                        // byte length of CLAUDE_TOOL_OUTPUT
}
```

### 6.2 Event Types

| `event` value | Meaning |
|---------------|---------|
| `call_tool` | Tool was called and completed (ok or error) |
| `call_blocked` | Tool call was intercepted before execution |
| `dangerous_action` | Tool call was classified as a dangerous action class |
| `hook_error` | The hook itself failed (meta-event for hook debugging) |
| `rotation` | Log rotation was performed (housekeeping event) |

**Note on `dangerous_action`**: Like OpenClaw, a dangerous call emits BOTH a `call_tool` entry AND a `dangerous_action` entry. This redundancy is intentional — it allows `grep '"event":"dangerous_action"'` to find all dangerous calls without needing to filter by `action_class`.

### 6.3 Action Class Values

| Value | Description |
|-------|-------------|
| `read` | Read-only operations: search, list, get, describe, read, query, fetch, find |
| `write` | Mutating operations: write, create, update, delete, put, patch, remove, move, rename |
| `network` | Network I/O: http, curl, fetch, request, download, upload, send, post |
| `credential` | Auth/secrets: auth, token, secret, key, password, credential, login, oauth |
| `exec` | Code execution: exec, run, shell, command, spawn, evaluate, interpret, compile |

### 6.4 Status Values

| Value | Description |
|-------|-------------|
| `ok` | Tool completed without error |
| `error` | Tool completed with an error |
| `blocked` | Tool was not executed (blocked before call) |

### 6.5 Reason Values (blocked calls only)

| Value | Description |
|-------|-------------|
| `allowlist` | Tool not in agent's allowlist |
| `rate_limit` | Agent exceeded call frequency for this tool |
| `argument_validation` | Arguments failed validation rules |
| `budget` | Session cost budget exceeded |
| `policy` | Blocked by action-policy.json rule |

### 6.6 JSONL File Format Invariants

1. One JSON object per line. No multi-line JSON.
2. No trailing comma on the last field.
3. No BOM at file start.
4. UTF-8 encoding.
5. Lines end with `\n` (LF), not `\r\n` (CRLF) — even on Windows, to allow portable `wc -l` and line-based tools.
6. The file does not begin with `[` and does not end with `]`. It is not a JSON array — it is JSONL.
7. The file must be parseable line-by-line; a corrupted or truncated line does not corrupt other lines.

### 6.7 Rotation Record Schema

When rotation runs, a `rotation` event is appended after the rewrite:

```json
{
  "timestamp": "2026-03-12T00:00:00.000Z",
  "event": "rotation",
  "agent_id": "hook",
  "action_class": "write",
  "args_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "server": "native",
  "status": "ok",
  "tool_id": "__rotation__",
  "entries_before": 10847,
  "entries_after": 10000,
  "entries_dropped": 847
}
```

---

## 7. Implementation Plan

Steps are numbered and must be executed in order. Each step is atomic — it can be completed and verified independently.

### Step 1: Create the audit directory

```bash
mkdir -p ~/.claude/audit
chmod 700 ~/.claude/audit
```

The directory must not be world-readable because the log contains tool names and argument hashes that could reveal project structure.

### Step 2: Create `action-policy.json`

Create `~/.claude/plugins/action-policy.json` with the content specified in Section 9.1. This file is read by `trace-post.sh` for the dangerous-action set. If the file does not exist, the hook falls back to hardcoded defaults.

### Step 3: Implement `trace-post.sh`

See Section 13 for the complete bash implementation. Key implementation points:

- Must handle missing environment variables gracefully (default to empty string / "unknown")
- Must not fail if the log directory does not exist (create it inline)
- Must not fail if `action-policy.json` does not exist (use hardcoded dangerous set)
- Must use `>>` append (not `>` overwrite)
- Must write a single line with no embedded newlines
- Must escape all JSON string values (double quotes, backslashes, control characters)
- Must run in under 50ms on typical calls (no heavy computation)

### Step 4: Implement `trace-pre.sh`

Add timing support to the pre-hook:

```bash
#!/usr/bin/env bash
# trace-pre.sh — Set timing baseline for duration_ms calculation
export CLAUDE_TOOL_START_MS=$(date +%s%3N 2>/dev/null || echo "0")
```

This exports the millisecond timestamp so `trace-post.sh` can compute `duration_ms`.

**Note**: Environment variable exports from subshell hooks may not be visible to `trace-post.sh` depending on how Claude Code runs hooks. If they run as separate subshells (most likely), use a tempfile instead:

```bash
#!/usr/bin/env bash
# trace-pre.sh
TIMING_DIR="${TMPDIR:-/tmp}/.claude-hook-timing"
mkdir -p "$TIMING_DIR"
echo "$(date +%s%3N 2>/dev/null || echo 0)" > "$TIMING_DIR/${CLAUDE_SESSION_ID:-default}.start"
```

### Step 5: Implement `rotate.sh`

```bash
#!/usr/bin/env bash
# rotate.sh — Rotate ~/.claude/audit/tool-calls.jsonl
# Called by trace-post.sh when rotation criteria are met.
# Usage: rotate.sh [max_entries] [max_days]

set -euo pipefail

LOG_FILE="${HOME}/.claude/audit/tool-calls.jsonl"
MAX_ENTRIES="${1:-10000}"
MAX_DAYS="${2:-30}"
MARKER="${HOME}/.claude/audit/.last-rotation"

[[ -f "$LOG_FILE" ]] || exit 0

python3 - "$LOG_FILE" "$MAX_ENTRIES" "$MAX_DAYS" "$MARKER" <<'PYEOF'
import sys, json, os, datetime, tempfile, shutil

log_path  = sys.argv[1]
max_lines = int(sys.argv[2])
max_days  = int(sys.argv[3])
marker    = sys.argv[4]

with open(log_path, "r", encoding="utf-8") as f:
    lines = [l for l in f if l.strip()]

total = len(lines)
if total <= max_lines:
    # Check oldest entry date
    try:
        first = json.loads(lines[0])
        ts = datetime.datetime.fromisoformat(first.get("timestamp","").replace("Z","+00:00"))
        age = (datetime.datetime.now(datetime.timezone.utc) - ts).days
        if age < max_days:
            sys.exit(0)
    except Exception:
        sys.exit(0)

keep = lines[-max_lines:]
dropped = total - len(keep)

tmp = log_path + ".tmp"
with open(tmp, "w", encoding="utf-8", newline="\n") as f:
    f.writelines(keep)

shutil.move(tmp, log_path)

rotation_event = {
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"),
    "event": "rotation",
    "agent_id": "hook",
    "action_class": "write",
    "args_hash": "0" * 64,
    "server": "native",
    "status": "ok",
    "tool_id": "__rotation__",
    "entries_before": total,
    "entries_after": len(keep),
    "entries_dropped": dropped
}
with open(log_path, "a", encoding="utf-8", newline="\n") as f:
    f.write(json.dumps(rotation_event, ensure_ascii=False) + "\n")

with open(marker, "w") as f:
    f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())

print(f"Rotated: {dropped} entries dropped, {len(keep)} kept")
PYEOF
```

### Step 6: Create `~/.claude/commands/audit.md`

See Section 10 for the full command content.

### Step 7: Make scripts executable

```bash
chmod +x ~/.claude/hooks/trace-pre.sh
chmod +x ~/.claude/hooks/trace-post.sh
chmod +x ~/.claude/audit/rotate.sh
```

### Step 8: Verify hook registration

Check that Claude Code's settings file (`~/.claude/settings.json` or `~/.claude/settings.local.json`) references the hooks:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "*", "hooks": [{ "type": "command", "command": "~/.claude/hooks/trace-pre.sh" }] }
    ],
    "PostToolUse": [
      { "matcher": "*", "hooks": [{ "type": "command", "command": "~/.claude/hooks/trace-post.sh" }] }
    ]
  }
}
```

If these entries are missing, add them. If the settings file uses a different hook registration format, adapt accordingly — the key requirement is that both hooks run for every tool call (matcher `"*"`).

### Step 9: Seed the log file

Create an empty log file so `/audit` commands work before the first real tool call:

```bash
touch ~/.claude/audit/tool-calls.jsonl
chmod 600 ~/.claude/audit/tool-calls.jsonl
```

### Step 10: Smoke test

Run a simple Claude Code command that invokes a tool, then verify the log has an entry:

```bash
# After running a Claude Code session that calls Bash or Read:
tail -1 ~/.claude/audit/tool-calls.jsonl | python3 -m json.tool
```

Expected: a valid JSON object with all required fields.

---

## 8. Integration Points

### 8.1 With Action Classification

The `trace-post.sh` hook calls the same keyword-scoring logic described in `action-classification.md`. The audit log entry's `action_class` field is the direct output of that classification. The integration is:

1. `trace-post.sh` runs classification inline (bash keyword matching)
2. Result is written to `action_class` field in the JSONL entry
3. If `action_class` is in the dangerous set (loaded from `action-policy.json`), a second `dangerous_action` entry is appended
4. The full classification algorithm (Python, with scores) is available via `~/.claude/plugins/classify.py` for the `/audit` command to use in post-hoc analysis

### 8.2 With the Tool-Broker Agent

The `tool-broker` agent (described in CLAUDE.md) conceptually manages per-agent allowlists and meta-tool patterns. Currently this is prompt-only — no runtime enforcement.

The audit log enables the tool-broker to become runtime-aware:
- When the tool-broker agent is invoked, it can be given the last N entries from the audit log as context
- This allows it to detect patterns: "agent X has called exec tools 8 times in this session — flag for review"
- The tool-broker's future blocking decisions can be logged as `call_blocked` events with `reason: allowlist`

The convention for tool-broker-initiated blocks: the tool-broker agent writes a block record to the log by calling `~/.claude/audit/block.sh <tool_id> <agent_id> <reason>`. This script appends a `call_blocked` entry without requiring a full tool call cycle.

### 8.3 With `/vet`

If a `/vet` command exists or is planned, it can use the audit log as its primary data source:
- Scan for `dangerous_action` events in the last session
- Check for any `action_class: credential` entries (potential secret exposure)
- Count `call_blocked` events and their reasons (security policy effectiveness)
- Alert on repeated identical `args_hash` values (loop detection)

The `/vet` command can be implemented as a `/audit` alias with a security-focused default query.

### 8.4 With `/forge`

The `/forge` command generates MCP servers. When forge creates a new server and tools, those tools will have names like `mcp__<forge-server>__<tool>`. The audit log's `server` field will automatically capture these. The `/audit` command can be used post-forge to inspect what the new MCP tools are doing:

```
/audit server=<forge-server-name> last=100
```

### 8.5 With `/checkpoint`

The memory-scribe agent that runs `/checkpoint` should include an audit summary in `WORKING_MEMORY.md`. The summary format:

```
## Tool Activity (last session)
- Total calls: 47
- Dangerous actions: 3 (exec: 2, network: 1)
- Blocked: 0
- Most-used tools: Bash (18), Read (12), Edit (9)
```

This requires the memory-scribe to have read access to `~/.claude/audit/tool-calls.jsonl` and call `/audit summary last-session`.

---

## 9. Configuration

### 9.1 `action-policy.json` Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12",
  "version": "1.0",
  "dangerous_action_classes": ["exec", "credential", "network"],
  "blocked_action_classes": [],
  "log_path": "~/.claude/audit/tool-calls.jsonl",
  "rotation": {
    "max_entries": 10000,
    "max_days": 30
  },
  "classification": {
    "read":       ["search", "list", "get", "describe", "read", "query", "fetch", "find"],
    "write":      ["write", "create", "update", "delete", "put", "patch", "remove", "move", "rename"],
    "network":    ["http", "curl", "fetch", "request", "download", "upload", "send", "post"],
    "credential": ["auth", "token", "secret", "key", "password", "credential", "login", "oauth"],
    "exec":       ["exec", "run", "shell", "command", "spawn", "evaluate", "interpret", "compile"]
  },
  "agent_allowlists": {
    "supervisor":    ["*"],
    "implementer":   ["Bash", "Read", "Edit", "Write", "Glob", "Grep"],
    "researcher":    ["Read", "Glob", "Grep", "WebFetch", "WebSearch"],
    "browser":       ["mcp__chrome-devtools__*"],
    "wheel-scout":   ["Read", "Glob", "Grep", "WebFetch", "WebSearch"],
    "memory-scribe": ["Read", "Write"]
  }
}
```

### 9.2 Defaults When Config File Is Missing

If `action-policy.json` does not exist, `trace-post.sh` uses these hardcoded defaults:

```bash
DANGEROUS_CLASSES="exec credential network"
MAX_ENTRIES=10000
MAX_DAYS=30
```

### 9.3 Overriding the Log Path

Set `CLAUDE_AUDIT_LOG` in the environment to override the default log path:

```bash
export CLAUDE_AUDIT_LOG="/custom/path/audit.jsonl"
```

The hook checks this variable first, then falls back to `~/.claude/audit/tool-calls.jsonl`.

### 9.4 Disabling Audit Logging

Set `CLAUDE_AUDIT_DISABLED=1` to disable logging entirely (e.g., for performance testing):

```bash
export CLAUDE_AUDIT_DISABLED=1
```

The hook checks this at startup and exits 0 immediately if set. This is a bypass escape hatch — do not enable in production harness configurations.

---

## 10. Query & Analysis

### 10.1 `/audit` Command

Create `~/.claude/commands/audit.md` with this content:

````markdown
# /audit — Audit Log Query Command

Read and analyze the Claude Code audit log at `~/.claude/audit/tool-calls.jsonl`.

## Invocation

```
/audit [filter] [options]
```

## Filter Syntax

Filters are space-separated key=value pairs:

| Filter | Example | Description |
|--------|---------|-------------|
| `event=` | `event=dangerous_action` | Filter by event type |
| `tool=` | `tool=Bash` | Filter by tool_id (partial match) |
| `agent=` | `agent=implementer` | Filter by agent_id |
| `class=` | `class=exec` | Filter by action_class |
| `status=` | `status=blocked` | Filter by status |
| `server=` | `server=native` | Filter by server |
| `last=` | `last=100` | Show only the last N entries |
| `since=` | `since=2026-03-12` | Show entries after this date |
| `before=` | `before=2026-03-13` | Show entries before this date |
| `session=` | `session=sess_abc` | Filter by session_id |
| `hash=` | `hash=a3f9e2b1` | Filter by args_hash (prefix match) |

## Built-in Queries

- `/audit summary` — Count events by type, class, and tool for the last session
- `/audit dangerous` — All dangerous_action events, most recent first
- `/audit blocked` — All call_blocked events with reasons
- `/audit loops` — Entries where args_hash repeats 3+ times (loop detection)
- `/audit timeline` — All entries sorted by timestamp, formatted as a timeline
- `/audit top-tools` — Top 10 tools by call count
- `/audit top-agents` — Tool usage breakdown per agent

## Instructions

When the user runs `/audit [query]`:

1. Read the file `~/.claude/audit/tool-calls.jsonl` using the Read tool.
2. Parse each line as JSON. Skip blank lines and malformed lines (log a warning count).
3. Apply any filters specified in the query.
4. Format the results as a clean markdown table or list.
5. Always show: total entries read, total matching, date range of the log.
6. For `summary`, produce a breakdown table.
7. For `dangerous`, highlight the action_class and tool_id prominently.
8. For `loops`, group by args_hash and show the tool and repeat count.

## Output Format

### For filtered queries:
```
## Audit Results — [filter description]
Log range: 2026-03-10 → 2026-03-12 (847 total entries, 12 matching)

| Timestamp           | Event        | Tool          | Agent       | Class  | Status  |
|---------------------|--------------|---------------|-------------|--------|---------|
| 2026-03-12 14:23:01 | call_tool    | Bash          | implementer | exec   | ok      |
| 2026-03-12 14:23:05 | dangerous_action | Bash     | implementer | exec   | ok      |
```

### For `summary`:
```
## Audit Summary — Last Session (sess_abc123)
Period: 2026-03-12 14:20:01 → 2026-03-12 14:47:33 (47 calls, 27m 32s)

### By Event Type
| Event           | Count |
|-----------------|-------|
| call_tool       | 44    |
| dangerous_action| 3     |
| call_blocked    | 0     |

### By Action Class
| Class      | Count |
|------------|-------|
| read       | 18    |
| exec       | 12    |
| write      | 9     |
| network    | 4     |
| credential | 4     |

### Top Tools
| Tool       | Count |
|------------|-------|
| Bash       | 18    |
| Read       | 12    |
| Edit       | 9     |
```
````

### 10.2 Programmatic Query (Python)

For scripts and agents that need to query the log programmatically:

```python
import json
from pathlib import Path
from datetime import datetime, timezone

def read_audit_log(
    log_path=Path.home() / ".claude" / "audit" / "tool-calls.jsonl",
    event=None,
    tool=None,
    agent=None,
    action_class=None,
    status=None,
    last=None,
    since=None,
):
    entries = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event and entry.get("event") != event:
                continue
            if tool and tool.lower() not in entry.get("tool_id", "").lower():
                continue
            if agent and entry.get("agent_id") != agent:
                continue
            if action_class and entry.get("action_class") != action_class:
                continue
            if status and entry.get("status") != status:
                continue
            if since:
                ts = datetime.fromisoformat(entry.get("timestamp","").replace("Z","+00:00"))
                if ts < since:
                    continue
            entries.append(entry)
    if last:
        entries = entries[-last:]
    return entries
```

---

## 11. Testing Plan

### 11.1 Unit Tests for Hook Logic

Test each component of `trace-post.sh` independently:

**Test 1: Directory creation**
```bash
rm -rf /tmp/audit-test
CLAUDE_AUDIT_LOG="/tmp/audit-test/sub/test.jsonl" \
CLAUDE_TOOL_NAME="Read" \
CLAUDE_TOOL_INPUT='{"file_path":"/tmp/test.txt"}' \
CLAUDE_TOOL_OUTPUT='{"content":"hello"}' \
bash ~/.claude/hooks/trace-post.sh
# Expected: /tmp/audit-test/sub/test.jsonl exists with one entry
```

**Test 2: Valid JSON output**
```bash
tail -1 ~/.claude/audit/tool-calls.jsonl | python3 -c "import sys,json; json.load(sys.stdin); print('VALID')"
# Expected: VALID
```

**Test 3: Required fields present**
```bash
tail -1 ~/.claude/audit/tool-calls.jsonl | python3 -c "
import sys, json
e = json.load(sys.stdin)
required = ['timestamp','event','tool_id','agent_id','action_class','args_hash','server','status']
missing = [f for f in required if f not in e]
print('MISSING:', missing if missing else 'none')
"
```

**Test 4: Args hash is SHA256**
```bash
tail -1 ~/.claude/audit/tool-calls.jsonl | python3 -c "
import sys, json, re
e = json.load(sys.stdin)
h = e.get('args_hash','')
print('HASH OK' if re.fullmatch(r'[0-9a-f]{64}', h) else f'BAD HASH: {h!r}')
"
```

**Test 5: Dangerous action double-logging**
```bash
# Trigger a Bash call, then check both events appear
CLAUDE_TOOL_NAME="Bash" \
CLAUDE_TOOL_INPUT='{"command":"echo test"}' \
CLAUDE_TOOL_OUTPUT='{"output":"test"}' \
bash ~/.claude/hooks/trace-post.sh

python3 - <<'EOF'
import json
from pathlib import Path
log = Path.home() / ".claude/audit/tool-calls.jsonl"
entries = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
bash_entries = [e for e in entries[-5:] if e.get("tool_id") == "Bash"]
events = {e["event"] for e in bash_entries}
assert "call_tool" in events, "Missing call_tool event"
assert "dangerous_action" in events, "Missing dangerous_action event"
print("PASS: both events present")
EOF
```

**Test 6: Disabled mode**
```bash
CLAUDE_AUDIT_DISABLED=1 \
CLAUDE_TOOL_NAME="Bash" \
CLAUDE_TOOL_INPUT='{"command":"echo test"}' \
bash ~/.claude/hooks/trace-post.sh
echo "Exit: $?"
# Expected: Exit: 0, and no new entry in the log
```

### 11.2 Rotation Tests

**Test 7: Rotation triggers at limit**
```bash
# Generate 10001 fake entries
python3 -c "
import json, datetime
log = open('/tmp/rotation-test.jsonl','w')
for i in range(10001):
    ts = datetime.datetime(2026,1,1) + datetime.timedelta(seconds=i)
    e = {'timestamp': ts.isoformat()+'Z', 'event':'call_tool', 'tool_id':'Read',
         'agent_id':'test', 'action_class':'read', 'args_hash':'a'*64,
         'server':'native', 'status':'ok'}
    log.write(json.dumps(e)+'\n')
log.close()
"
python3 ~/.claude/audit/rotate.py /tmp/rotation-test.jsonl 10000 30 /tmp/.last-rotation
wc -l /tmp/rotation-test.jsonl
# Expected: 10001 lines (10000 kept + 1 rotation event)
```

### 11.3 Integration Test

**Test 8: End-to-end with real Claude Code session**
1. Start a Claude Code session
2. Run a simple command that triggers Bash (e.g., `list files in current directory`)
3. Exit the session
4. Run `/audit last=5` in a new session
5. Verify the Bash call from step 2 appears in the output

### 11.4 Performance Test

**Test 9: Hook latency**
```bash
time for i in $(seq 1 100); do
  CLAUDE_TOOL_NAME="Read" \
  CLAUDE_TOOL_INPUT='{"file_path":"/tmp/test.txt"}' \
  CLAUDE_TOOL_OUTPUT='{}' \
  bash ~/.claude/hooks/trace-post.sh
done
# Expected: 100 iterations in under 5 seconds total (< 50ms per call)
```

---

## 12. Example Usage

### 12.1 Normal Tool Call

Scenario: Implementer agent reads a TypeScript file.

```json
{
  "timestamp": "2026-03-12T14:23:01.847Z",
  "event": "call_tool",
  "tool_id": "Read",
  "agent_id": "implementer",
  "action_class": "read",
  "args_hash": "7f4e3a2b1c9d8e5f6a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f",
  "server": "native",
  "status": "ok",
  "session_id": "sess_20260312_1423",
  "duration_ms": 8,
  "tool_input_size": 52,
  "tool_output_size": 3847
}
```

### 12.2 Bash Call (Dangerous Action — Dual Event)

Scenario: Implementer runs `npm test` via Bash.

Entry 1 — the call itself:
```json
{
  "timestamp": "2026-03-12T14:24:15.003Z",
  "event": "call_tool",
  "tool_id": "Bash",
  "agent_id": "implementer",
  "action_class": "exec",
  "args_hash": "3c7f9a1b2e4d6c8a0b1c3d5e7f9a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a",
  "server": "native",
  "status": "ok",
  "dangerous": true,
  "session_id": "sess_20260312_1423",
  "duration_ms": 4821,
  "tool_input_size": 31,
  "tool_output_size": 1204
}
```

Entry 2 — the danger flag:
```json
{
  "timestamp": "2026-03-12T14:24:15.004Z",
  "event": "dangerous_action",
  "tool_id": "Bash",
  "agent_id": "implementer",
  "action_class": "exec",
  "args_hash": "3c7f9a1b2e4d6c8a0b1c3d5e7f9a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a",
  "server": "native",
  "status": "ok",
  "dangerous": true,
  "session_id": "sess_20260312_1423"
}
```

### 12.3 Blocked Call

Scenario: Researcher agent attempts Bash (not in its allowlist).

```json
{
  "timestamp": "2026-03-12T14:25:44.210Z",
  "event": "call_blocked",
  "tool_id": "Bash",
  "agent_id": "researcher",
  "action_class": "exec",
  "args_hash": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b",
  "server": "native",
  "status": "blocked",
  "reason": "allowlist",
  "dangerous": true,
  "session_id": "sess_20260312_1423"
}
```

### 12.4 MCP Tool Call

Scenario: Browser agent navigates a page via Chrome DevTools MCP.

```json
{
  "timestamp": "2026-03-12T14:26:33.891Z",
  "event": "call_tool",
  "tool_id": "mcp__chrome-devtools__navigate_page",
  "agent_id": "browser",
  "action_class": "network",
  "args_hash": "9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d",
  "server": "chrome-devtools",
  "status": "ok",
  "dangerous": true,
  "session_id": "sess_20260312_1426",
  "duration_ms": 234,
  "tool_input_size": 89,
  "tool_output_size": 145
}
```

### 12.5 Tool Error

Scenario: Read tool called on a nonexistent file.

```json
{
  "timestamp": "2026-03-12T14:27:01.554Z",
  "event": "call_tool",
  "tool_id": "Read",
  "agent_id": "implementer",
  "action_class": "read",
  "args_hash": "c4a3f2e1b9d8c7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2",
  "server": "native",
  "status": "error",
  "error": "File not found: /tmp/does-not-exist.txt",
  "session_id": "sess_20260312_1423",
  "duration_ms": 3
}
```

### 12.6 WebFetch (Network — Dangerous)

Scenario: Wheel-scout agent fetches a library's documentation page.

Entry 1:
```json
{
  "timestamp": "2026-03-12T14:30:11.002Z",
  "event": "call_tool",
  "tool_id": "WebFetch",
  "agent_id": "wheel-scout",
  "action_class": "network",
  "args_hash": "5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3",
  "server": "native",
  "status": "ok",
  "dangerous": true,
  "session_id": "sess_20260312_1430",
  "duration_ms": 1847
}
```

Entry 2:
```json
{
  "timestamp": "2026-03-12T14:30:11.003Z",
  "event": "dangerous_action",
  "tool_id": "WebFetch",
  "agent_id": "wheel-scout",
  "action_class": "network",
  "args_hash": "5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3",
  "server": "native",
  "status": "ok",
  "dangerous": true,
  "session_id": "sess_20260312_1430"
}
```

### 12.7 `/audit summary` Output Example

```
## Audit Summary
Log: ~/.claude/audit/tool-calls.jsonl
Period: 2026-03-12 14:20:01Z → 2026-03-12 14:30:11Z (52 total entries)

### Event Types
| Event           | Count | % of Total |
|-----------------|-------|------------|
| call_tool       | 44    | 84.6%      |
| dangerous_action| 7     | 13.5%      |
| call_blocked    | 1     | 1.9%       |

### Action Classes
| Class      | Count |
|------------|-------|
| read       | 19    |
| exec       | 13    |
| write      | 8     |
| network    | 7     |
| credential | 1     |

### Status Breakdown
| Status  | Count |
|---------|-------|
| ok      | 43    |
| error   | 1     |
| blocked | 1     |

### Top Tools (by call count)
| Tool          | Count | Dangerous |
|---------------|-------|-----------|
| Bash          | 13    | yes       |
| Read          | 12    | no        |
| Edit          | 8     | no        |
| WebFetch      | 5     | yes       |
| Glob          | 4     | no        |
| Write         | 2     | no        |
```

---

## 13. Hook Implementation Detail

### `~/.claude/hooks/trace-post.sh` — Complete Implementation

```bash
#!/usr/bin/env bash
# trace-post.sh — Audit log writer for Claude Code
# Runs after every tool call. Appends one JSONL entry to the audit log.
# Environment variables consumed:
#   CLAUDE_TOOL_NAME     — tool identifier
#   CLAUDE_TOOL_INPUT    — JSON string of tool arguments
#   CLAUDE_TOOL_OUTPUT   — JSON string of tool result
#   CLAUDE_SESSION_ID    — session identifier (optional)
#   CLAUDE_AGENT_ID      — agent identifier (optional, harness convention)
#   CLAUDE_TOOL_STATUS   — "ok" or "error" (optional, defaults to inferring from output)
#   CLAUDE_TOOL_ERROR    — error message if status is error (optional)
#   CLAUDE_AUDIT_LOG     — override log file path (optional)
#   CLAUDE_AUDIT_DISABLED — set to 1 to disable logging entirely

set -euo pipefail

# ── 0. Disabled check ──────────────────────────────────────────────────────────
[[ "${CLAUDE_AUDIT_DISABLED:-0}" == "1" ]] && exit 0

# ── 1. Resolve paths ───────────────────────────────────────────────────────────
AUDIT_LOG="${CLAUDE_AUDIT_LOG:-${HOME}/.claude/audit/tool-calls.jsonl}"
AUDIT_DIR="$(dirname "$AUDIT_LOG")"
POLICY_FILE="${HOME}/.claude/plugins/action-policy.json"
TIMING_DIR="${TMPDIR:-/tmp}/.claude-hook-timing"
ROTATE_SCRIPT="${HOME}/.claude/audit/rotate.sh"

# ── 2. Ensure log directory exists ────────────────────────────────────────────
mkdir -p "$AUDIT_DIR"

# ── 3. Read tool call context ─────────────────────────────────────────────────
TOOL_ID="${CLAUDE_TOOL_NAME:-unknown}"
TOOL_INPUT="${CLAUDE_TOOL_INPUT:-{}}"
TOOL_OUTPUT="${CLAUDE_TOOL_OUTPUT:-{}}"
SESSION_ID="${CLAUDE_SESSION_ID:-}"
AGENT_ID="${CLAUDE_AGENT_ID:-}"

# ── 4. Resolve agent_id ───────────────────────────────────────────────────────
if [[ -z "$AGENT_ID" ]]; then
  if [[ -n "$SESSION_ID" ]] && [[ -f "${AUDIT_DIR}/sessions/${SESSION_ID}.agent" ]]; then
    AGENT_ID="$(cat "${AUDIT_DIR}/sessions/${SESSION_ID}.agent")"
  else
    AGENT_ID="claude-code"
  fi
fi

# ── 5. Determine status ───────────────────────────────────────────────────────
STATUS="${CLAUDE_TOOL_STATUS:-ok}"
ERROR_MSG="${CLAUDE_TOOL_ERROR:-}"
# Infer error from output if status not explicitly set
if [[ "$STATUS" == "ok" ]] && [[ -n "$TOOL_OUTPUT" ]]; then
  if echo "$TOOL_OUTPUT" | grep -qi '"error"' 2>/dev/null; then
    # Lightweight heuristic — output JSON has an "error" key at root
    if echo "$TOOL_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'error' not in d else 1)" 2>/dev/null; then
      STATUS="ok"
    else
      STATUS="error"
      ERROR_MSG="$(echo "$TOOL_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(d.get('error','unknown error'))[:200])" 2>/dev/null || echo "parse error")"
    fi
  fi
fi

# ── 6. Compute args hash (SHA256 of sorted JSON input) ────────────────────────
ARGS_HASH="$(echo "$TOOL_INPUT" | python3 -c "
import sys, json, hashlib
try:
    data = json.load(sys.stdin)
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    print(hashlib.sha256(canonical.encode('utf-8')).hexdigest())
except Exception:
    # If input is not valid JSON, hash the raw string
    raw = sys.stdin.buffer.read() if hasattr(sys.stdin,'buffer') else b''
    print(hashlib.sha256(sys.stdin.read().encode('utf-8') if not raw else raw).hexdigest())
" 2>/dev/null || printf '%064d' 0)"

# ── 7. Classify action ────────────────────────────────────────────────────────
# Keyword scoring: combined string of tool name + input, lowercased
COMBINED="${TOOL_ID,,} $(echo "$TOOL_INPUT" | tr '[:upper:]' '[:lower:]' | tr -d '\n')"

classify_action() {
  local combined="$1"
  local -A scores=([read]=0 [write]=0 [network]=0 [credential]=0 [exec]=0)

  # Read keywords
  for kw in search list get describe read query find; do
    [[ "$combined" == *"$kw"* ]] && scores[read]=$((scores[read]+1))
  done
  # Fetch counts for both read and network — resolve below
  [[ "$combined" == *"fetch"* ]] && scores[read]=$((scores[read]+1)) && scores[network]=$((scores[network]+1))

  # Write keywords
  for kw in write create update delete put patch remove move rename; do
    [[ "$combined" == *"$kw"* ]] && scores[write]=$((scores[write]+1))
  done

  # Network keywords
  for kw in http curl request download upload send post; do
    [[ "$combined" == *"$kw"* ]] && scores[network]=$((scores[network]+1))
  done

  # Credential keywords
  for kw in auth token secret key password credential login oauth; do
    [[ "$combined" == *"$kw"* ]] && scores[credential]=$((scores[credential]+1))
  done

  # Exec keywords
  for kw in exec run shell command spawn evaluate interpret compile; do
    [[ "$combined" == *"$kw"* ]] && scores[exec]=$((scores[exec]+1))
  done

  # Native tool overrides (authoritative — no ambiguity)
  case "$TOOL_ID" in
    Bash)        echo "exec";       return ;;
    Read|Glob|Grep) echo "read";   return ;;
    Edit|Write)  echo "write";      return ;;
    WebFetch|WebSearch) echo "network"; return ;;
  esac

  # MCP tool prefix override
  case "$TOOL_ID" in
    mcp__chrome-devtools__*) echo "network"; return ;;
    mcp__github__*create*|mcp__github__*update*|mcp__github__*delete*)
      echo "write"; return ;;
    mcp__github__*get*|mcp__github__*list*|mcp__github__*search*)
      echo "read"; return ;;
  esac

  # Score-based fallback: find max
  local best="read"
  local best_score=0
  for class in read write network credential exec; do
    if [[ ${scores[$class]} -gt $best_score ]]; then
      best_score=${scores[$class]}
      best="$class"
    fi
  done

  # All-zero scores → default "read" (safe)
  echo "$best"
}

ACTION_CLASS="$(classify_action "$COMBINED")"

# ── 8. Resolve server name ────────────────────────────────────────────────────
resolve_server() {
  local tool="$1"
  case "$tool" in
    Bash|Read|Edit|Write|Glob|Grep|WebFetch|WebSearch|Skill|Task|TodoRead|TodoWrite)
      echo "native" ;;
    mcp__*__*)
      # Extract middle segment: mcp__<server>__<tool> → <server>
      echo "$tool" | sed 's/^mcp__\([^_]*\([-][^_]*\)*\)__.*$/\1/' ;;
    *)
      echo "unknown" ;;
  esac
}

SERVER="$(resolve_server "$TOOL_ID")"

# ── 9. Compute duration_ms ────────────────────────────────────────────────────
DURATION_MS=""
SESSION_KEY="${SESSION_ID:-default}"
TIMING_FILE="${TIMING_DIR}/${SESSION_KEY}.start"
if [[ -f "$TIMING_FILE" ]]; then
  START_MS="$(cat "$TIMING_FILE" 2>/dev/null || echo 0)"
  NOW_MS="$(date +%s%3N 2>/dev/null || echo 0)"
  if [[ "$START_MS" -gt 0 ]] && [[ "$NOW_MS" -gt 0 ]]; then
    DURATION_MS=$((NOW_MS - START_MS))
  fi
  rm -f "$TIMING_FILE"
fi

# ── 10. Check dangerous action set ───────────────────────────────────────────
DANGEROUS_CLASSES="exec credential network"
if [[ -f "$POLICY_FILE" ]]; then
  DANGEROUS_CLASSES="$(python3 -c "
import json, sys
try:
    p = json.load(open('$POLICY_FILE'))
    print(' '.join(p.get('dangerous_action_classes', ['exec','credential','network'])))
except Exception:
    print('exec credential network')
" 2>/dev/null || echo "exec credential network")"
fi

IS_DANGEROUS="false"
for dc in $DANGEROUS_CLASSES; do
  [[ "$ACTION_CLASS" == "$dc" ]] && IS_DANGEROUS="true" && break
done

# ── 11. Get size metrics ──────────────────────────────────────────────────────
INPUT_SIZE="${#TOOL_INPUT}"
OUTPUT_SIZE="${#TOOL_OUTPUT}"

# ── 12. Get timestamp ─────────────────────────────────────────────────────────
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%S.000Z 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"

# ── 13. JSON escape helper ────────────────────────────────────────────────────
json_escape() {
  # Escape a string for use as a JSON string value
  # Uses python3 for correctness (handles all Unicode and control chars)
  python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$1" 2>/dev/null || echo '"unknown"'
}

# ── 14. Build and append the call_tool entry ─────────────────────────────────
build_entry() {
  local event="$1"
  local extra_fields="$2"

  local entry
  entry="{"
  entry+="\"timestamp\":$(json_escape "$TIMESTAMP"),"
  entry+="\"event\":$(json_escape "$event"),"
  entry+="\"tool_id\":$(json_escape "$TOOL_ID"),"
  entry+="\"agent_id\":$(json_escape "$AGENT_ID"),"
  entry+="\"action_class\":$(json_escape "$ACTION_CLASS"),"
  entry+="\"args_hash\":$(json_escape "$ARGS_HASH"),"
  entry+="\"server\":$(json_escape "$SERVER"),"
  entry+="\"status\":$(json_escape "$STATUS")"

  # Optional fields
  [[ -n "$SESSION_ID" ]] && entry+=",\"session_id\":$(json_escape "$SESSION_ID")"
  [[ -n "$DURATION_MS" ]] && entry+=",\"duration_ms\":$DURATION_MS"
  [[ "$IS_DANGEROUS" == "true" ]] && entry+=",\"dangerous\":true"
  [[ "$STATUS" == "error" ]] && [[ -n "$ERROR_MSG" ]] && \
    entry+=",\"error\":$(json_escape "$ERROR_MSG")"
  [[ "$INPUT_SIZE" -gt 0 ]] && entry+=",\"tool_input_size\":$INPUT_SIZE"
  [[ "$OUTPUT_SIZE" -gt 0 ]] && entry+=",\"tool_output_size\":$OUTPUT_SIZE"

  # Inject any extra fields (pre-built JSON fragment, no leading comma)
  [[ -n "$extra_fields" ]] && entry+=",$extra_fields"

  entry+="}"
  echo "$entry"
}

# Write call_tool entry
build_entry "call_tool" "" >> "$AUDIT_LOG"

# Write dangerous_action entry (duplicate event, no size fields)
if [[ "$IS_DANGEROUS" == "true" ]]; then
  python3 - <<PYEOF >> "$AUDIT_LOG"
import json, sys
# Minimal dangerous_action entry — no size fields, just the security signal
entry = {
    "timestamp": $(json_escape "$TIMESTAMP"),
    "event": "dangerous_action",
    "tool_id": $(json_escape "$TOOL_ID"),
    "agent_id": $(json_escape "$AGENT_ID"),
    "action_class": $(json_escape "$ACTION_CLASS"),
    "args_hash": $(json_escape "$ARGS_HASH"),
    "server": $(json_escape "$SERVER"),
    "status": $(json_escape "$STATUS"),
    "dangerous": True,
}
if $(json_escape "$SESSION_ID") != '""':
    entry["session_id"] = $(json_escape "$SESSION_ID").strip('"')
print(json.dumps(entry, ensure_ascii=False))
PYEOF
fi

# ── 15. Rotation check (probabilistic — run 1 in 50 calls to save overhead) ──
RAND_CHECK=$((RANDOM % 50))
if [[ "$RAND_CHECK" -eq 0 ]] && [[ -x "$ROTATE_SCRIPT" ]]; then
  # Run in background to not block the hook
  bash "$ROTATE_SCRIPT" 10000 30 &>/dev/null &
fi

exit 0
```

### Implementation Notes for `trace-post.sh`

1. **Python dependency**: The hook uses Python 3 for three operations: SHA256 hashing, JSON escaping, and dangerous-action entry building. Python 3 is available on all supported platforms. The pure-bash fallbacks (using `printf '%064d' 0` for hash, manual escaping for strings) are sufficient for the common case but are not used because JSON string escaping in pure bash is error-prone.

2. **Atomic append**: The `>>` operator on Linux/macOS/Windows NTFS is safe for concurrent single-line appends because the OS serializes writes at the filesystem level for small writes. For very high-frequency parallel agent scenarios, use a lock file: `flock "${AUDIT_LOG}.lock" -c "echo \"$entry\" >> \"$AUDIT_LOG\""`. Not included in the default implementation because it adds ~5ms latency per call.

3. **Dangerous action entry via Python heredoc**: The second JSONL entry (for dangerous actions) is built via Python inline script to avoid a second call to `json_escape` for every field. This trades shell complexity for correctness.

4. **Rotation probability**: Running rotation 1 in 50 calls (2%) means rotation is checked ~every 50 tool calls. For a typical session of 50 calls, rotation is checked once per session. For long sessions (500 calls), it is checked ~10 times. This avoids the overhead of counting lines on every call.

5. **MCP server name extraction**: The `sed` pattern `mcp__<server>__<tool>` handles server names with hyphens (e.g., `mcp__chrome-devtools__navigate_page` → `chrome-devtools`). The pattern `\([^_]*\([-][^_]*\)*\)` matches one or more hyphen-separated segments.

6. **Native tool override table**: The `case` statement for native tools is authoritative — it bypasses the keyword scorer entirely for known tools. This prevents false classifications (e.g., `WebFetch` scoring as `read` because of the `fetch` keyword hitting both `read` and `network`).

7. **Error detection heuristic**: The `grep -qi '"error"'` heuristic is intentionally loose — it catches any output JSON containing a key named "error". Claude Code's native tools return error information consistently enough that this works in practice. Explicit `CLAUDE_TOOL_STATUS` from Claude Code's hook runner (if it sets this variable) takes priority.
```
