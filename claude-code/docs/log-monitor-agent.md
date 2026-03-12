# Log Monitor Agent: Port from OpenClaw to Claude Code

**Document type**: Implementation reference
**Status**: Specification (not yet implemented)
**Target**: `~/.claude/agents/log-monitor.md` + changes to `~/.claude/commands/go.md`

---

## 1. Overview

The log-monitor agent watches a running dev server's stdout/stderr in real time, classifies anomalies, and writes a structured findings report that the orchestrator and implementer agents can consume. It runs as a non-blocking sidecar alongside `/go`'s main pipeline so that runtime errors — which would otherwise scroll by silently — are captured, categorized, and fed back as actionable fix context.

The agent is modeled on OpenClaw's two-component log monitoring system (`log_sentinel.py` + `log_monitor.ps1`) and adapted to Claude Code's agent/sidecar pattern.

**What it does:**

- Detects the project's dev server command from `ai/supervisor/intake.json` or by inspecting project config files
- Starts the dev server via `Bash`, capturing stdout and stderr to a raw log file at `ai/context/raw_server.log`
- Performs periodic analysis passes over the raw log using regex pattern matching
- Categorizes anomalies into: errors, exceptions, unhandled rejections, stack traces, deprecation warnings, port conflicts, module-not-found, permission errors, memory/segfault, and network errors
- Writes findings to `ai/context/LOG_FINDINGS.md` in a structured, human- and agent-readable format
- Signals the calling orchestrator when critical anomalies are found so the implementer can be redirected to fix them

**Why it matters:**

The implementer agent runs tests against a test harness, but many runtime problems only manifest when the actual dev server boots and serves requests. Without a log watcher, the following classes of errors are invisible:

- Unhandled promise rejections (Node.js prints these to stderr; test runners often don't capture them)
- Deprecation warnings from framework internals that indicate future breakage
- Port binding failures that cause silent startup crashes
- Module resolution errors that only appear on specific import paths
- Memory pressure events and OOM kills
- Framework initialization errors that occur after tests pass but before a page loads

The log-monitor agent closes this gap by being the dedicated "eyes on the console" that no other agent currently covers.

---

## 2. Problem Statement

### 2.1 The Silent Failure Gap

In the current harness:

1. `/go` spawns an implementer agent (Ralph loop)
2. The implementer writes code, runs `pnpm test` or equivalent, gets green tests
3. `/go` reports success and checkpoints memory

What `/go` does NOT do: start the dev server and watch what happens.

A passing test suite does not guarantee a working application. Common failures that tests miss:

| Failure type | Why tests miss it | Example |
|---|---|---|
| Unhandled rejection | Async errors outside test boundaries | `UnhandledPromiseRejection: Cannot read property 'x' of undefined` |
| Port conflict | Server never binds; tests mock the server | `EADDRINUSE: address already in use :::3000` |
| Hot reload crash | HMR errors only appear at runtime | `[vite] error: Failed to parse module` |
| Dep deprecation | Peer warnings suppressed in test env | `DeprecationWarning: Buffer() is deprecated` |
| Missing env var | Test uses mocks; server uses real env | `Error: OPENAI_API_KEY is not defined` |
| Segfault in native module | Node process crashes entirely | `Segmentation fault (core dumped)` |
| Memory leak growth | Tests complete before leak is visible | `FATAL ERROR: Reached heap limit` |

### 2.2 OpenClaw's Solution and Its Limits

OpenClaw solved this with two PowerShell/Python components:

- `log_sentinel.py`: batch analysis of a log file; generates `LOG_FINDINGS.md`
- `log_monitor.ps1`: background process that boots the server and pipes its output

This worked for OpenClaw's always-on background runner model. Claude Code needs a different integration because:

1. Claude Code agents are event-driven, not daemons
2. The dev server must be started fresh per `/go` session (not assumed already running)
3. Findings need to flow back to a live orchestrator, not just be written to a file
4. The pattern set needs to be expanded beyond OpenClaw's basic regex to cover modern JS/TS stacks, Python ASGI, and others

---

## 3. Source Analysis

### 3.1 OpenClaw: `log_sentinel.py`

The compiler reads a log file, applies regex patterns in order, and groups matches.

**Pattern set (original)**:

```python
patterns = {
    'error':       re.compile(r'error|Error|ERROR'),
    'exception':   re.compile(r'exception|Exception'),
    'fatal':       re.compile(r'fatal|Fatal|FATAL'),
    'stack_trace': re.compile(r'^\s+at\s+'),        # JS/Node stack frame
    'warning':     re.compile(r'warning|Warning'),
}
```

**Timestamp extraction**:

```python
timestamp_patterns = [
    re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}'),  # ISO
    re.compile(r'\d{2}:\d{2}:\d{2}'),                          # HH:MM:SS
    re.compile(r'\[\d+\]'),                                     # [timestamp_ms]
]
```

**Output format — `LOG_FINDINGS.md`**:

```markdown
# Log Analysis Findings

## Summary
- Total lines analyzed: N
- Errors: N
- Warnings: N
- Fatal errors: N

## Errors
### Line 42
`Error: Cannot connect to database`

## Recommendations
- N errors found — investigate before deploying
```

**Limits**:
- Caps at last 100 anomalies total, 20 per category in display
- No severity scoring
- No deduplication of repeated identical errors
- No context window (doesn't show lines before/after the match)
- No understanding of stack traces as multi-line units

### 3.2 OpenClaw: `log_monitor.ps1`

The worker does three things:

1. Detect the dev server command by reading `package.json` scripts
2. Start the server process, redirecting output to `ai/context/raw_server.log`
3. Loop: every N seconds, call the sentinel to re-analyze the growing log file

**Key behavior**:
- Runs as a PowerShell background job
- Exits when the server process exits or when triggered to stop
- Does not parse output in real time — reads the log file on each poll cycle

**Integration point**: The harness calls `log_monitor.ps1` as a side process when a dev server is detected and the task involves runtime testing.

---

## 4. Target Architecture

```
/go (go.md)
├── Phase 0: Intake (writes intake.json with dev_cmd)
├── Phase 5c: Implementer Ralph loop
│   └── runs tests (does NOT start dev server)
├── Phase 5e: Sidecar agents
│   └── log-monitor (NEW) ─── run_in_background: true
│       ├── Reads intake.json → extracts dev_cmd
│       ├── Falls back to project config detection if no dev_cmd
│       ├── Starts dev server via Bash (captures stdout+stderr)
│       ├── Writes raw output to ai/context/raw_server.log
│       ├── Analysis loop: tail log → regex scan → categorize
│       ├── Writes ai/context/LOG_FINDINGS.md (updated each pass)
│       └── Returns summary to /go when findings exist
└── Phase 6: Integration
    └── Reads LOG_FINDINGS.md
    └── If critical findings: re-activates implementer with anomaly context
```

**Key design decisions**:

1. **Sidecar, not wave sub-task**: The dev server watch is non-blocking with respect to the main build pipeline. The implementer can be finishing test fixes while the log-monitor is independently starting the server and watching for runtime errors. Results are folded in at Phase 6.

2. **File-based feedback**: `ai/context/LOG_FINDINGS.md` is the communication channel between log-monitor and the orchestrator. This is intentional: files are readable by any agent at any point, survive process boundaries, and require no special IPC.

3. **Non-fatal by default**: If the dev server command is unknown, or the server fails to start, the log-monitor returns a warning but does NOT block the pipeline.

4. **Platform-aware**: On Windows, Bash commands use `cmd /c start` or process substitution patterns where needed. The agent detects platform via `uname` or environment checks.

---

## 5. File Layout

Files to create:

```
~/.claude/agents/log-monitor.md          ← NEW: agent definition (this document's Section 6)
ai/context/raw_server.log                ← created at runtime by log-monitor
ai/context/LOG_FINDINGS.md               ← created at runtime by log-monitor
```

Files to modify:

```
~/.claude/commands/go.md                 ← add Phase 5e log-monitor spawn (Section 10)
```

Optional configuration file (per-project):

```
ai/supervisor/log-monitor-config.json    ← custom patterns, severity overrides, server cmd
```

No new dependencies. The log-monitor agent uses only the `Bash`, `Read`, `Write`, `Glob`, and `Grep` tools that the harness already provides.

---

## 6. Agent Definition

The complete content of `~/.claude/agents/log-monitor.md`:

```markdown
---
name: log-monitor
description: >
  Sidecar agent that starts the dev server, captures its output, analyzes
  logs for anomalies, and writes ai/context/LOG_FINDINGS.md. Runs as a
  non-blocking background agent alongside /go's build pipeline.
tools: [Bash, Read, Write, Glob, Grep]
---

# Log Monitor Agent

You are a background sidecar agent. Your job is to start the project's dev
server, watch its output for anomalies, and report findings. You run in
parallel with the main build pipeline — your job is NOT to block it.

## Inputs

You receive a context pack with:
- `PROJECT_ROOT`: absolute path to the project root
- `DEV_CMD`: dev server command (from intake.json or detected)
- `DURATION_SECONDS`: how long to monitor (default: 45)
- `PLATFORM`: win32 | linux | darwin

## Step 1: Resolve Dev Server Command

If `DEV_CMD` is provided in your context, use it directly.

Otherwise, detect it:

```bash
# Check intake.json first
cat ai/supervisor/intake.json 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('stack', {}).get('dev_cmd', ''))
" 2>/dev/null
```

If not in intake.json, probe project files (see Dev Server Detection section below).

If no command can be determined, write to LOG_FINDINGS.md:
```
# Log Analysis Findings
## Status: SKIPPED
**Reason**: Could not determine dev server command. Set `dev_cmd` in ai/supervisor/intake.json or create ai/supervisor/log-monitor-config.json with `{"dev_cmd": "..."}`.
```
Then exit with a non-critical warning.

## Step 2: Check for Custom Config

```bash
cat ai/supervisor/log-monitor-config.json 2>/dev/null
```

If found, read:
- `dev_cmd`: override the detected command
- `extra_patterns`: additional regex patterns to apply
- `severity_overrides`: change severity of specific pattern categories
- `max_anomalies`: cap on total anomalies captured (default: 100)
- `poll_interval_seconds`: how often to re-analyze (default: 5)

## Step 3: Start Dev Server

Ensure the output directories exist:
```bash
mkdir -p ai/context
```

Start the server, redirecting both stdout and stderr to the raw log file.
On Unix/Mac:
```bash
DEV_CMD 2>&1 | tee ai/context/raw_server.log &
SERVER_PID=$!
```

On Windows (win32 platform):
```bash
cmd /c "DEV_CMD > ai/context/raw_server.log 2>&1" &
```

Wait up to 10 seconds for the server to start. Check for startup confirmation
by scanning the first lines of raw_server.log for patterns like:
- `listening on`, `running on`, `started`, `ready`, `Server running`
- `Local:`, `http://localhost`, `vite`, `webpack compiled`

If the server does not start within 10 seconds, note this but continue
monitoring (it may be slow to boot).

## Step 4: Monitor Loop

Run the analysis loop for DURATION_SECONDS (default 45, longer for slow builds):

```
PASS = 0
while elapsed < DURATION_SECONDS:
  PASS++
  wait POLL_INTERVAL_SECONDS

  1. Read ai/context/raw_server.log (or tail last 500 lines)
  2. Apply all anomaly patterns (see pattern set below)
  3. Deduplicate: if identical message seen in previous pass, skip
  4. Categorize and score new findings
  5. Append to in-memory findings list
  6. Write updated LOG_FINDINGS.md
  7. If CRITICAL anomalies found: break early and report immediately
```

## Step 5: Write Findings

Write `ai/context/LOG_FINDINGS.md` after each analysis pass.

Format:

```markdown
# Log Analysis Findings

**Generated**: [ISO timestamp]
**Dev Server**: [command used]
**Duration**: [N] seconds monitored
**Log**: ai/context/raw_server.log

## Summary

| Category | Count | Severity |
|----------|-------|----------|
| Errors | N | CRITICAL |
| Unhandled Rejections | N | CRITICAL |
| Exceptions | N | HIGH |
| Stack Traces | N | HIGH |
| Port Conflicts | N | CRITICAL |
| Module Not Found | N | HIGH |
| Fatal/Crashes | N | CRITICAL |
| Deprecation Warnings | N | LOW |
| Permission Errors | N | MEDIUM |
| Memory/OOM | N | CRITICAL |
| Connection Errors | N | MEDIUM |
| Warnings | N | LOW |

**Highest severity**: [CRITICAL|HIGH|MEDIUM|LOW|NONE]
**Total anomalies**: N (capped at 100)

## Findings

### [CATEGORY] — [count] occurrences

#### Line [N]: [first ~80 chars of line]
```
[full line content]
```
*Context (±2 lines)*:
```
[line N-2]
[line N-1]
> [line N]   ← anomaly
[line N+1]
[line N+2]
```
Timestamp: [extracted timestamp or "unknown"]

---

## Recommendations

[Generated based on finding categories — see logic below]

## Status
[CRITICAL_FINDINGS | WARNINGS_ONLY | CLEAN | SKIPPED | SERVER_NOT_STARTED]
```

## Step 6: Return Summary

Return a concise summary to the orchestrator:

```
LOG_MONITOR REPORT:
  Status: [CRITICAL_FINDINGS | WARNINGS_ONLY | CLEAN | SKIPPED]
  Server started: [yes/no]
  Duration: [N]s monitored
  Findings file: ai/context/LOG_FINDINGS.md

  [If CRITICAL_FINDINGS]:
  TOP ISSUES:
  - [category]: [short description] (line N)
  - [category]: [short description] (line N)

  ACTION REQUIRED: Implementer should read ai/context/LOG_FINDINGS.md
  and fix the critical runtime errors before marking task complete.
```

## Dev Server Detection

If `DEV_CMD` is not provided, detect it in this order:

### 1. Check intake.json
```bash
python3 -c "
import json, sys
try:
    d = json.load(open('ai/supervisor/intake.json'))
    print(d.get('stack', {}).get('dev_cmd', ''))
except: pass
"
```

### 2. Check package.json (Node.js projects)
```bash
python3 -c "
import json
try:
    s = json.load(open('package.json')).get('scripts', {})
    for key in ['dev', 'start', 'serve', 'preview']:
        if key in s:
            print(s[key])
            break
except: pass
"
```

### 3. Check Python project files
- `app.py` exists → `python app.py`
- `manage.py` exists (Django) → `python manage.py runserver`
- `pyproject.toml` with `[tool.poetry.scripts]` → check for `start` or `serve` entry
- `Makefile` with `run:` or `serve:` target → `make run` or `make serve`
- If `uvicorn` in requirements/pyproject → `uvicorn app:app --reload`
- If `flask` in requirements/pyproject → `flask run`
- If `fastapi` in requirements/pyproject → `uvicorn main:app --reload`
- `gunicorn` → `gunicorn app:app`

### 4. Check other runtimes
- `Cargo.toml` → `cargo run`
- `go.mod` + `main.go` exists → `go run .`
- `Gemfile` + `config/application.rb` (Rails) → `rails server`
- `mix.exs` (Elixir/Phoenix) → `mix phx.server`
- `build.gradle` or `pom.xml` + `src/main/java/` → `./mvnw spring-boot:run` or `./gradlew bootRun`
- `Makefile` with `run:` → `make run`

### 5. Give up gracefully
If no command found after all checks, log to `LOG_FINDINGS.md` with SKIPPED status
and return `LOG_MONITOR REPORT: Status: SKIPPED — dev command not detected`.

## Anomaly Detection Patterns

(See the main pattern set defined in the anomaly detection section of this document.
These are embedded directly in the agent's analysis loop.)

## Anomaly Categorization Logic

After scanning each line, assign:

```python
CATEGORY_PRIORITY = {
    'port_conflict':     (1, 'CRITICAL'),
    'oom':               (1, 'CRITICAL'),
    'segfault':          (1, 'CRITICAL'),
    'unhandled_rejection': (2, 'CRITICAL'),
    'fatal':             (2, 'CRITICAL'),
    'error':             (3, 'HIGH'),
    'exception':         (3, 'HIGH'),
    'module_not_found':  (3, 'HIGH'),
    'stack_trace':       (4, 'HIGH'),    # grouped with parent error
    'permission':        (5, 'MEDIUM'),
    'connection_error':  (5, 'MEDIUM'),
    'timeout':           (5, 'MEDIUM'),
    'deprecation':       (6, 'LOW'),
    'warning':           (7, 'LOW'),
}
```

Stack trace lines (lines matching `^\s+at ` or `^\s+File "`) are attached
to the preceding error/exception as context, not counted as separate anomalies.

## Recommendation Generation

Based on categories found, append to LOG_FINDINGS.md:

| Finding | Recommendation |
|---------|---------------|
| `port_conflict` | "Port already in use. Kill the existing process: `lsof -i :<PORT>` or change the port in config." |
| `module_not_found` | "Missing module — run `npm install` / `pip install -r requirements.txt`. Check import path." |
| `unhandled_rejection` | "Unhandled Promise rejection — add `.catch()` or `try/catch` to async code at the indicated location." |
| `oom` | "Out of memory — check for memory leaks, increase `--max-old-space-size`, or reduce parallel work." |
| `segfault` | "Native module crash — check Node.js version compatibility with native addons, rebuild with `npm rebuild`." |
| `permission` | "Permission denied — check file/directory permissions or whether the process needs elevated privileges." |
| `deprecation` (count > 5) | "Many deprecation warnings — address before upgrading framework versions to avoid breaking changes." |
| `fatal` | "Fatal error detected — server likely crashed. Review full stack trace in raw_server.log." |
| `connection_error` | "Connection refused/timeout — check that all required services (DB, Redis, etc.) are running." |
| `error` (count == 0) | "No errors detected. Server appears healthy." |

## Deduplication Rules

- Exact duplicate lines (same content): keep first occurrence, note count
- Same error message at different line numbers: group under one entry, list line numbers
- Stack trace frames: attach to parent error, don't list as separate anomalies
- Repeated deprecation warnings (same message): count occurrences, show once with count

## Cap Rules (inherited from OpenClaw)

- Total anomalies in report: max 100
- Per category in display: max 20
- Raw log: no cap (write everything to raw_server.log)
- If cap reached, note "... and N more (see raw_server.log)"
```

---

## 7. Dev Server Detection

The detection logic (described in Section 6 above) works in priority order. Here is the full decision table with all cases:

### Node.js / JavaScript / TypeScript

| Condition | Inferred command |
|---|---|
| `package.json` has `scripts.dev` | value of `scripts.dev` |
| `package.json` has `scripts.start` | value of `scripts.start` |
| `package.json` has `scripts.serve` | value of `scripts.serve` |
| `package.json` has `scripts.preview` | value of `scripts.preview` |
| `next.config.js` or `next.config.ts` exists | `npx next dev` |
| `vite.config.ts` or `vite.config.js` exists | `npx vite` |
| `nuxt.config.ts` exists | `npx nuxt dev` |
| `remix.config.js` exists | `npx remix dev` |
| `astro.config.mjs` exists | `npx astro dev` |
| `svelte.config.js` exists | `npx vite dev` |

### Python

| Condition | Inferred command |
|---|---|
| `manage.py` exists + `django` in requirements | `python manage.py runserver` |
| `app.py` exists + `flask` in deps | `flask run` |
| `main.py` exists + `fastapi` in deps | `uvicorn main:app --reload` |
| `app.py` exists + `fastapi` in deps | `uvicorn app:app --reload` |
| `pyproject.toml` has `[tool.poetry.scripts]` with `start` | `poetry run start` |
| Standalone `app.py` | `python app.py` |
| `Makefile` has `run:` target | `make run` |
| `Makefile` has `serve:` target | `make serve` |

### Other Runtimes

| Condition | Inferred command |
|---|---|
| `Cargo.toml` exists | `cargo run` |
| `go.mod` + `main.go` | `go run .` |
| `Gemfile` + `config/application.rb` | `bundle exec rails server` |
| `mix.exs` + `lib/` dir | `mix phx.server` |
| `pom.xml` + `src/main/java/` | `./mvnw spring-boot:run` |
| `build.gradle` + `src/main/java/` | `./gradlew bootRun` |
| `Procfile` with `web:` line | value of `web:` line |
| `docker-compose.yml` + no native dev cmd | `docker compose up` |

### Precedence

1. `ai/supervisor/log-monitor-config.json` → `dev_cmd` field (highest priority)
2. `ai/supervisor/intake.json` → `stack.dev_cmd` field
3. `package.json` scripts (in order: `dev`, `start`, `serve`, `preview`)
4. Framework-specific config file detection
5. Runtime-specific fallbacks (Cargo, go.mod, etc.)
6. `Procfile`
7. `docker-compose.yml`
8. No command found → SKIPPED

---

## 8. Anomaly Detection Patterns

These patterns are applied line-by-line to the raw log. The agent implements this in Python (spawned via `Bash`) or directly in shell pipeline with grep. The Python implementation is preferred for accuracy on multi-byte content and context extraction.

### Complete Regex Pattern Set

```python
import re

PATTERNS = {

    # ── CRITICAL ──────────────────────────────────────────────────────────────

    'port_conflict': [
        re.compile(r'EADDRINUSE', re.IGNORECASE),
        re.compile(r'address already in use', re.IGNORECASE),
        re.compile(r'port \d+ is already in use', re.IGNORECASE),
        re.compile(r'bind: address already in use', re.IGNORECASE),
        re.compile(r'Only one usage of each socket address', re.IGNORECASE),  # Windows
    ],

    'oom': [
        re.compile(r'FATAL ERROR:.*heap limit', re.IGNORECASE),
        re.compile(r'JavaScript heap out of memory', re.IGNORECASE),
        re.compile(r'Reached heap limit Allocation failed', re.IGNORECASE),
        re.compile(r'Cannot allocate memory', re.IGNORECASE),
        re.compile(r'MemoryError', re.IGNORECASE),
        re.compile(r'OOMKilled', re.IGNORECASE),
        re.compile(r'out of memory', re.IGNORECASE),
        re.compile(r'Killed\s*$'),  # Linux OOM killer
    ],

    'segfault': [
        re.compile(r'Segmentation fault', re.IGNORECASE),
        re.compile(r'segfault', re.IGNORECASE),
        re.compile(r'SIGSEGV', re.IGNORECASE),
        re.compile(r'core dumped', re.IGNORECASE),
        re.compile(r'Aborted \(core dumped\)', re.IGNORECASE),
        re.compile(r'SIGABRT', re.IGNORECASE),
        re.compile(r'Bus error', re.IGNORECASE),
    ],

    'unhandled_rejection': [
        re.compile(r'UnhandledPromiseRejection', re.IGNORECASE),
        re.compile(r'UnhandledPromiseRejectionWarning', re.IGNORECASE),
        re.compile(r'unhandledRejection', re.IGNORECASE),
        re.compile(r'Unhandled promise rejection', re.IGNORECASE),
        re.compile(r'\(node:\d+\) UnhandledPromise', re.IGNORECASE),
    ],

    'fatal': [
        re.compile(r'\bFATAL\b'),
        re.compile(r'\bfatal\b', re.IGNORECASE),
        re.compile(r'Fatal error', re.IGNORECASE),
        re.compile(r'FATAL ERROR:', re.IGNORECASE),
        re.compile(r'Panic:', re.IGNORECASE),          # Go/Rust panics
        re.compile(r'panic:', re.IGNORECASE),
        re.compile(r'thread .* panicked', re.IGNORECASE),  # Rust
        re.compile(r'Process exited with code [1-9]'),
    ],

    # ── HIGH ──────────────────────────────────────────────────────────────────

    'error': [
        re.compile(r'\bERROR\b'),
        re.compile(r'\bError\b'),
        re.compile(r'\berror\b'),
        re.compile(r'Error:'),
        re.compile(r'\[error\]', re.IGNORECASE),
        re.compile(r'✗ error', re.IGNORECASE),
        re.compile(r'TypeError:', re.IGNORECASE),
        re.compile(r'ReferenceError:', re.IGNORECASE),
        re.compile(r'SyntaxError:', re.IGNORECASE),
        re.compile(r'RangeError:', re.IGNORECASE),
        re.compile(r'EvalError:', re.IGNORECASE),
        re.compile(r'URIError:', re.IGNORECASE),
        re.compile(r'SystemError:', re.IGNORECASE),
        re.compile(r'errno \d+', re.IGNORECASE),
        re.compile(r'HTTP 5\d\d'),               # 5xx server errors
        re.compile(r'status 5\d\d', re.IGNORECASE),
        re.compile(r'raise \w+Error'),            # Python: raise SomeError
        re.compile(r'Traceback \(most recent call last\)'),  # Python traceback start
    ],

    'exception': [
        re.compile(r'\bException\b'),
        re.compile(r'\bexception\b'),
        re.compile(r'Exception:'),
        re.compile(r'Caused by:', re.IGNORECASE),           # Java/JVM
        re.compile(r'java\.lang\.\w+Exception'),
        re.compile(r'org\.\w+\.\w+Exception'),
        re.compile(r'System\..*Exception'),                  # .NET
        re.compile(r'\w+Exception: ', re.IGNORECASE),
        re.compile(r'caught exception', re.IGNORECASE),
        re.compile(r'uncaught exception', re.IGNORECASE),
    ],

    'module_not_found': [
        re.compile(r"Cannot find module '", re.IGNORECASE),
        re.compile(r"Module not found: Error: Can't resolve"),
        re.compile(r'ModuleNotFoundError:', re.IGNORECASE),
        re.compile(r'ImportError:', re.IGNORECASE),
        re.compile(r"No module named '", re.IGNORECASE),
        re.compile(r'Cannot resolve module', re.IGNORECASE),
        re.compile(r'Failed to resolve import', re.IGNORECASE),
        re.compile(r'ERR_MODULE_NOT_FOUND', re.IGNORECASE),
        re.compile(r'ERR_CANNOT_FIND_MODULE', re.IGNORECASE),
        re.compile(r'require\(\) failed', re.IGNORECASE),
        re.compile(r"Require stack:"),
    ],

    'stack_trace': [
        re.compile(r'^\s+at\s+\w'),                 # JS/Node: "    at functionName"
        re.compile(r'^\s+at\s+new\s+\w'),           # JS constructor
        re.compile(r'^\s+at\s+<anonymous>'),
        re.compile(r'^\s+File ".*", line \d+'),      # Python traceback frame
        re.compile(r'^\s+in \w+ \(.*\.py:\d+\)'),   # Python alt format
        re.compile(r'^\t+at '),                       # Go stack frame
        re.compile(r'^\s+\d+:\s+0x[0-9a-f]+'),      # Rust panic frame
        re.compile(r'^\s+#\d+\s+0x[0-9a-f]+'),      # GDB-style frame
        re.compile(r'^\s+\w+\.\w+\(.*\.java:\d+\)'), # Java stack frame
    ],

    # ── MEDIUM ────────────────────────────────────────────────────────────────

    'permission': [
        re.compile(r'EACCES', re.IGNORECASE),
        re.compile(r'EPERM', re.IGNORECASE),
        re.compile(r'Permission denied', re.IGNORECASE),
        re.compile(r'Access denied', re.IGNORECASE),
        re.compile(r'Operation not permitted', re.IGNORECASE),
        re.compile(r'Insufficient privileges', re.IGNORECASE),
        re.compile(r'FORBIDDEN', re.IGNORECASE),
        re.compile(r'PermissionError:', re.IGNORECASE),   # Python
        re.compile(r'HTTP 40[13]'),                        # 401, 403
    ],

    'connection_error': [
        re.compile(r'ECONNREFUSED', re.IGNORECASE),
        re.compile(r'ECONNRESET', re.IGNORECASE),
        re.compile(r'ENOTFOUND', re.IGNORECASE),
        re.compile(r'ETIMEDOUT', re.IGNORECASE),
        re.compile(r'EHOSTUNREACH', re.IGNORECASE),
        re.compile(r'Connection refused', re.IGNORECASE),
        re.compile(r'Connection reset', re.IGNORECASE),
        re.compile(r'Connection timed out', re.IGNORECASE),
        re.compile(r'failed to connect', re.IGNORECASE),
        re.compile(r'could not connect to', re.IGNORECASE),
        re.compile(r'getaddrinfo ENOTFOUND', re.IGNORECASE),
        re.compile(r'socket hang up', re.IGNORECASE),
        re.compile(r'Network unreachable', re.IGNORECASE),
        re.compile(r'broken pipe', re.IGNORECASE),
        re.compile(r'ECONNABORTED', re.IGNORECASE),
    ],

    'timeout': [
        re.compile(r'timed? ?out', re.IGNORECASE),
        re.compile(r'TimeoutError', re.IGNORECASE),
        re.compile(r'DEADLINE_EXCEEDED', re.IGNORECASE),
        re.compile(r'request timeout', re.IGNORECASE),
        re.compile(r'gateway timeout', re.IGNORECASE),
        re.compile(r'504', re.IGNORECASE),
    ],

    # ── LOW ───────────────────────────────────────────────────────────────────

    'deprecation': [
        re.compile(r'DeprecationWarning:', re.IGNORECASE),
        re.compile(r'ExperimentalWarning:', re.IGNORECASE),
        re.compile(r'is deprecated', re.IGNORECASE),
        re.compile(r'has been deprecated', re.IGNORECASE),
        re.compile(r'will be removed in', re.IGNORECASE),
        re.compile(r'deprecated since', re.IGNORECASE),
        re.compile(r'\[DEP\d+\]'),                          # Node.js DEP codes
        re.compile(r'Future\w*Warning:', re.IGNORECASE),    # Python FutureWarning
        re.compile(r'PendingDeprecation', re.IGNORECASE),
        re.compile(r'use .* instead', re.IGNORECASE),
    ],

    'warning': [
        re.compile(r'\bWARN\b'),
        re.compile(r'\bWARNING\b'),
        re.compile(r'\bwarning\b', re.IGNORECASE),
        re.compile(r'\[warn\]', re.IGNORECASE),
        re.compile(r'⚠'),
        re.compile(r'WARN:'),
        re.compile(r'UserWarning:', re.IGNORECASE),         # Python
        re.compile(r'RuntimeWarning:', re.IGNORECASE),
        re.compile(r'SyntaxWarning:', re.IGNORECASE),
        re.compile(r'ResourceWarning:', re.IGNORECASE),
    ],
}

# Lines that match these are excluded from analysis (noise patterns)
NOISE_PATTERNS = [
    re.compile(r'^\s*$'),                        # blank lines
    re.compile(r'^  \[vite\] hmr update'),       # Vite HMR success updates
    re.compile(r'^\[HMR\] connected'),
    re.compile(r'webpack compiled successfully'),
    re.compile(r'✓ \d+ modules transformed'),    # Vite build info
    re.compile(r'ready in \d+ms', re.IGNORECASE),
    re.compile(r'Local:\s+http://localhost'),
    re.compile(r'Network:\s+http://'),
    re.compile(r'^\s*info\s+', re.IGNORECASE),   # generic [info] lines
    re.compile(r'GET /'),                         # HTTP access log lines
    re.compile(r'POST /'),
    re.compile(r'PUT /'),
    re.compile(r'DELETE /'),
    re.compile(r'\d{3} \d+ms'),                  # Express/fastify access logs
]

# Timestamp extraction patterns (in priority order)
TIMESTAMP_PATTERNS = [
    re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?'),
    re.compile(r'\d{2}:\d{2}:\d{2}(?:\.\d+)?'),
    re.compile(r'\[\d{4}-\d{2}-\d{2}\]'),
    re.compile(r'\d+\.\d{3}'),                   # seconds.ms (some loggers)
    re.compile(r'\[\d{10,13}\]'),                # Unix timestamp
]
```

### Pattern Application Order

For each log line:

1. Check NOISE_PATTERNS first — if matched, skip line entirely
2. Check CRITICAL patterns: `port_conflict`, `oom`, `segfault`, `unhandled_rejection`, `fatal`
3. If CRITICAL match: capture immediately, flag for early exit if needed
4. Check HIGH patterns: `error`, `exception`, `module_not_found`
5. Check `stack_trace`: if matched AND previous non-trace line was an error/exception, attach as context
6. Check MEDIUM patterns: `permission`, `connection_error`, `timeout`
7. Check LOW patterns: `deprecation`, `warning`
8. Extract timestamp from matched line
9. Capture ±2 lines of context around the matched line
10. Deduplicate against previously captured findings

### Early Exit Conditions

Break the monitoring loop early (before DURATION_SECONDS elapses) if:

- A `port_conflict` pattern matches → server cannot start, no point continuing
- A `segfault` or `oom` pattern matches → process has crashed
- An `unhandled_rejection` with a stack trace matches on the first analysis pass → critical runtime error right at startup

Early exit does NOT mean failure — it means "we found something important, report it now."

---

## 9. Real-time vs Batch Analysis

### Why Batch (Not Pure Streaming)

Claude Code agents invoke tools sequentially. True streaming (processing each line as it arrives) would require a tight Bash loop that continuously reads the log and re-runs analysis — expensive in tool calls. Instead:

**Batch polling with tail**: The agent runs the dev server in the background, sleeps for `POLL_INTERVAL_SECONDS`, then reads the log file and analyzes the new content since the last read position.

This is identical to OpenClaw's approach (the worker polled; the sentinel analyzed the whole file each time), but the Claude Code version tracks the last-read line number to avoid re-processing.

### Implementation Pattern

```bash
# Start server in background
DEV_CMD >> ai/context/raw_server.log 2>&1 &
SERVER_PID=$!

# Analysis: Python script does all the pattern matching
# Called every POLL_INTERVAL seconds via shell loop:
python3 /tmp/log_sentinel_pass.py \
    --log ai/context/raw_server.log \
    --last-line "$LAST_LINE" \
    --output ai/context/LOG_FINDINGS.md \
    --pass "$PASS_NUM"
```

The Python sentinel script (written to `/tmp/log_sentinel_pass.py` by the agent during Step 3) maintains state in a JSON sidecar file (`ai/context/.log_sentinel_state.json`) with:

```json
{
  "last_line": 0,
  "findings": [],
  "pass_count": 0,
  "started_at": "ISO timestamp",
  "server_pid": 12345
}
```

### Analysis Pass Structure

Each pass:
1. Read `raw_server.log` from line `last_line` to EOF
2. Apply patterns to new lines only
3. Merge new findings with existing findings (dedup)
4. Sort all findings by severity then line number
5. Write complete `LOG_FINDINGS.md` (full overwrite, not append)
6. Update `last_line` in state file
7. Return: `{new_findings: N, total_findings: N, highest_severity: "CRITICAL"|...}`

### Duration Guidelines

| Scenario | Recommended DURATION_SECONDS |
|---|---|
| Fast Vite/Next.js dev server | 30 |
| Django / Rails (slower startup) | 60 |
| Docker-compose with multiple services | 90 |
| Java Spring Boot (slow JVM startup) | 120 |
| Default (unknown stack) | 45 |

The `/go` orchestrator passes the duration based on the detected stack in `intake.json`. If unknown, use 45.

---

## 10. Sidecar Integration

### Changes to `~/.claude/commands/go.md`

The following changes are required in `go.md`. Add a new section to **Phase 5e** that explicitly covers the log-monitor sidecar. The existing Phase 5e content (general sidecar rules) remains unchanged — this adds a concrete trigger rule.

#### Addition to Phase 5e (insert after the "Sidecar rules" block):

```markdown
### Log Monitor Sidecar (automatic)

When the task involves any of the following, automatically spawn the log-monitor
as a background sidecar alongside the main implementation work:

- Task type is `fix` or `build` AND intake.json has a `dev_cmd`
- Task description mentions: "runtime", "server", "dev server", "crashes", "browser",
  "page load", "frontend", "hot reload", "production build", "deploy"
- Task modifies files that affect server startup: `app.py`, `server.ts`, `index.ts`,
  `main.go`, `Cargo.toml`, framework config files (vite.config, next.config, etc.)

Spawn it:
```
Agent(log-monitor, background):
  PROJECT_ROOT: [absolute path]
  DEV_CMD: [from intake.json stack.dev_cmd, or "auto-detect"]
  DURATION_SECONDS: [30-120 based on detected stack]
  PLATFORM: [win32|linux|darwin]
```

The log-monitor runs concurrently with the implementer's Ralph loop. It is a sidecar
(non-blocking). The main pipeline does NOT wait for it.

At Phase 6, after the implementer completes:
1. Check if log-monitor has completed (it will have written LOG_FINDINGS.md)
2. Read ai/context/LOG_FINDINGS.md
3. If `Status: CRITICAL_FINDINGS`:
   → Spawn a second implementer with the findings as context:
   ```
   The log-monitor found critical runtime errors while the dev server was running.
   Read ai/context/LOG_FINDINGS.md for details.
   Fix the runtime errors listed there, then re-run tests.
   ```
   → This is NOT a full Ralph loop restart — it is a targeted fix pass (MAX_ITERATIONS: 3)
4. If `Status: WARNINGS_ONLY`:
   → Include warnings in the final summary but do NOT re-run the implementer
5. If `Status: CLEAN` or `SKIPPED`:
   → Note in summary: "Runtime log: clean" or "Runtime log: not monitored"
```

#### Modified Phase 6 summary format:

Add to the summary template in Phase 6:

```markdown
- Runtime log: [CRITICAL_FINDINGS (N issues) | WARNINGS_ONLY | CLEAN | SKIPPED]
  [If CRITICAL: "→ Spawned fix pass for runtime errors"]
```

### Exact diff to go.md (Phase 5e section)

The current Phase 5e ends at the "Sidecar vs Wave sub-task" paragraph. Add the following immediately after that paragraph, before Phase 5d:

```
### 5e-ii: Log Monitor Sidecar (Automatic Dev Server Watcher)

**Trigger condition**: Spawn automatically when ALL of the following are true:
1. Task type is `build` or `fix` (not research/review/discover)
2. Any of these signals:
   - `intake.json` has a non-empty `stack.dev_cmd`
   - Task touches server entrypoints (app.py, server.ts, main.go, index.ts)
   - Task touches framework config (vite.config.*, next.config.*, webpack.config.*)
   - Task description contains runtime/server/crash/browser/frontend/deploy keywords

**Spawn**:
```
Agent(log-monitor, sonnet, run_in_background: true):
  context:
    PROJECT_ROOT: [cwd]
    DEV_CMD: [from intake.json or "auto-detect"]
    DURATION_SECONDS: [30 for vite/next, 60 for django/rails, 120 for java, 45 default]
    PLATFORM: [detected platform]
  tools: [Bash, Read, Write, Glob, Grep]
```

**Important**: The log-monitor does NOT need to complete before the implementer
finishes. It runs independently. Its output (LOG_FINDINGS.md) is consumed at
Phase 6 during integration.

**At Phase 6**: If LOG_FINDINGS.md has `Status: CRITICAL_FINDINGS`, spawn a
targeted fix pass (implementer, MAX_ITERATIONS: 3) with the findings as input.
This is the "runtime fix loop" — separate from the test-fix loop.
```

---

## 11. Feedback Protocol

### File-Based Communication

The log-monitor writes to `ai/context/LOG_FINDINGS.md`. This is the sole communication channel. No special IPC, no shared memory, no event bus.

**Why file-based**: Files are the universal substrate for Claude Code agent communication. Any agent can read any file at any time. The orchestrator polls the file at Phase 6. The implementer can be given the file path directly as context. Future agents (e.g., a test reporter) can also read it.

### Machine-Readable Status Line

The last line of `LOG_FINDINGS.md` is always:

```
## Status
CRITICAL_FINDINGS
```

or one of: `WARNINGS_ONLY`, `CLEAN`, `SKIPPED`, `SERVER_NOT_STARTED`

This allows the orchestrator to parse the status with a single grep without reading the full file:

```bash
tail -1 ai/context/LOG_FINDINGS.md
# or
grep "^## Status" -A1 ai/context/LOG_FINDINGS.md | tail -1
```

### Orchestrator Decision Tree at Phase 6

```
Read ai/context/LOG_FINDINGS.md
├── Status: CRITICAL_FINDINGS
│   ├── Parse top issues (first 5 findings by severity)
│   ├── Spawn: Agent(implementer, MAX_ITERATIONS: 3)
│   │   Context: "Fix the runtime errors in ai/context/LOG_FINDINGS.md"
│   └── After fix pass: note in final summary
├── Status: WARNINGS_ONLY
│   ├── Include warnings in summary
│   └── Do NOT re-run implementer (warnings don't block)
├── Status: CLEAN
│   └── Note: "Runtime log: clean"
├── Status: SERVER_NOT_STARTED
│   ├── Note: "Dev server failed to start — check ai/context/raw_server.log"
│   └── Do NOT block pipeline
└── File missing / Status: SKIPPED
    └── Note: "Runtime log not monitored"
```

### Implementer Context Injection (for the runtime fix pass)

When spawning the fix-pass implementer after CRITICAL_FINDINGS, inject:

```
You are fixing runtime errors found by the log-monitor agent.

Read the findings at: ai/context/LOG_FINDINGS.md
Raw logs are at: ai/context/raw_server.log

Focus ONLY on the issues listed under CRITICAL or HIGH severity.
Do not change unrelated code.
After fixing, the orchestrator will verify by running tests.
You do NOT need to restart the dev server — the log-monitor handles that.

MAX_ITERATIONS: 3
SUCCESS_CRITERIA: All CRITICAL findings from LOG_FINDINGS.md are resolved
TEST_COMMAND: [from intake.json]
```

### No Blocking of Main Pipeline

The log-monitor sidecar is always `run_in_background: true`. The Ralph loop (implementer) for the main task is NOT gated on the log-monitor. The log-monitor produces an independent, asynchronous report.

The only time the log-monitor output gates something is at Phase 6 (integration), after the main implementation work is already done. This means:

- A slow-starting server (Java, Rails) does not delay the test runner
- A project with no detectable dev server does not break `/go`
- Log monitor crashes are non-fatal (`LOG_FINDINGS.md` not written → treated as SKIPPED)

---

## 12. Implementation Plan

### Step 1: Create the agent file

Create `~/.claude/agents/log-monitor.md` with the content from Section 6 of this document.

This is the only file needed for the agent to be discoverable and callable by the harness.

### Step 2: Update go.md

In `~/.claude/commands/go.md`, add the Phase 5e-ii block (Section 10 of this document) after the existing "Sidecar vs Wave sub-task" paragraph.

Add the runtime log status line to the Phase 6 summary template.

### Step 3: Test with a known-broken project

Create a minimal test project (see Section 13) with an intentional runtime error. Run `/go fix the broken thing` and verify the log-monitor fires, captures the error, and the implementer's fix pass resolves it.

### Step 4: Validate on real projects

Run `/go [any build task]` on the `physical-capability-cloud` project:
- `dev_cmd` in intake.json: `pnpm dev`
- Expected: log-monitor starts `pnpm dev`, watches for Vite/Fastify errors
- Expected: 30-second monitoring window (Vite is fast)

### Step 5: Add platform-specific validation

On Windows (current platform): verify that the Bash background process pattern works.
The Windows-safe pattern is:

```bash
nohup DEV_CMD > ai/context/raw_server.log 2>&1 &
```

or for cmd.exe-based commands:

```bash
cmd /c "start /B DEV_CMD > ai/context/raw_server.log 2>&1"
```

Test that `raw_server.log` is written before the first analysis pass.

### Step 6: Wire to intake.json

Ensure `/intake` writes `dev_cmd` into `stack.dev_cmd`. Currently the intake command already does this (it reads `package.json` scripts and writes `dev_cmd`). Verify the field name matches what log-monitor reads.

The intake.json field is `stack.dev_cmd` (a string). The log-monitor reads it as:

```python
import json
data = json.load(open('ai/supervisor/intake.json'))
dev_cmd = data.get('stack', {}).get('dev_cmd', '')
```

---

## 13. Testing Plan

### Test 1: Basic Node.js error capture

Setup:
```bash
mkdir /tmp/test-log-monitor && cd /tmp/test-log-monitor
npm init -y
```

Create `server.js`:
```javascript
const http = require('http');
// Intentional: unhandled rejection
Promise.reject(new Error('test unhandled rejection'));
const server = http.createServer((req, res) => res.end('ok'));
server.listen(3001);
```

Add to `package.json` scripts: `"dev": "node server.js"`

Create `ai/supervisor/intake.json`:
```json
{"stack": {"dev_cmd": "node server.js"}}
```

Run log-monitor agent manually with `DURATION_SECONDS: 15`.

Expected `LOG_FINDINGS.md`:
- Status: `CRITICAL_FINDINGS`
- Category: `unhandled_rejection`
- Line content contains "test unhandled rejection"
- Recommendation: "Unhandled Promise rejection — add `.catch()`..."

### Test 2: Port conflict detection

Setup: Start any server on port 3000. Then create a project with `dev_cmd: "node -e \"require('http').createServer().listen(3000)\""`.

Expected:
- Status: `CRITICAL_FINDINGS`
- Category: `port_conflict`
- Recommendation: "Port already in use. Kill the existing process..."

### Test 3: Module not found

```javascript
// server.js
require('./nonexistent-module');
```

Expected:
- Status: `CRITICAL_FINDINGS`
- Category: `module_not_found`
- Pattern: `Cannot find module './nonexistent-module'`

### Test 4: Python Django startup

Setup:
```bash
mkdir /tmp/test-django && cd /tmp/test-django
pip install django
django-admin startproject testproject .
# Break it: delete a required file
rm testproject/settings.py
```

Expected:
- Status: `CRITICAL_FINDINGS`
- Category: `error` or `module_not_found`
- Contains Django startup traceback

### Test 5: Clean server (no errors)

A working `pnpm dev` on `physical-capability-cloud`.

Expected:
- Status: `CLEAN`
- Summary: 0 anomalies
- `raw_server.log` contains Vite startup output

### Test 6: Unknown dev command

A project with no `package.json`, no `app.py`, no `manage.py`, no `Cargo.toml`, no intake.json `dev_cmd`.

Expected:
- Status: `SKIPPED`
- Message: "Could not determine dev server command"
- Does NOT crash the pipeline

### Test 7: Integration with /go sidecar spawn

1. Create a project with an intentional unhandled rejection in the server
2. Run `/go add a feature to this server`
3. Verify:
   - Implementer runs Ralph loop (builds the feature)
   - Log-monitor runs in background (captures the unhandled rejection)
   - At Phase 6: LOG_FINDINGS.md has CRITICAL_FINDINGS
   - /go spawns a fix pass for the runtime error
   - Fix pass resolves the unhandled rejection
   - Final summary includes "Runtime log: CRITICAL_FINDINGS → fix pass applied"

### Test 8: Sidecar timing (non-blocking)

Verify that the implementer's test results arrive at Phase 6 independently of
the log-monitor. If the log-monitor takes 45 seconds but the implementer finishes
in 20 seconds, Phase 6 should wait for the sidecar before finalizing — but the
implementer should not have been blocked.

Check the Phase 6 `agent_outputs` list: implementer result appears first (earlier
completion), log-monitor result appears second.

---

## 14. Example Scenario

### Setup

Project: `physical-capability-cloud`, gateway package.

A developer adds a new Fastify route that accidentally introduces an unhandled promise rejection:

```typescript
// packages/gateway/src/routes/new-endpoint.ts
fastify.get('/api/new', async (request, reply) => {
  const data = await fetchFromDatabase(); // returns undefined sometimes
  return { result: data.items };          // TypeError when data is undefined
});
```

Tests pass because the test suite mocks `fetchFromDatabase` to always return valid data. The TypeError only manifests when the real server handles a request.

### Execution

User runs: `/go add the new endpoint and make sure it works`

**Phase 0**: Intake reads `package.json`, writes `ai/supervisor/intake.json` with `dev_cmd: "pnpm dev"`.

**Phase 1**: Task classified as `build`. Single sub-task, no decomposition needed.

**Phase 2**: Wheel-scout runs (build task gate). Finds no existing solution (custom endpoint). Recommends BUILD.

**Phase 3**: Parallel bootstrap — context hydrator reads gateway package structure, finds Fastify route patterns, builds 30-line context pack.

**Phase 5c**: Implementer spawns, implements the route, runs `pnpm --filter @pcc/gateway test`. Tests pass (mocked database). Implementer returns `DONE`.

**Phase 5e**: Log-monitor spawns in background (simultaneously with Phase 5c):
- Reads `intake.json`: `dev_cmd = "pnpm dev"`
- Detects platform: win32
- Runs: `pnpm dev >> ai/context/raw_server.log 2>&1 &`
- Waits 10 seconds for Vite + Fastify startup confirmation
- Detects "Server listening at http://localhost:3200" in log → server started
- Analysis pass 1 (at t=15s): no anomalies in startup output
- Analysis pass 2 (at t=20s): no new lines
- Analysis pass 3 (at t=25s): a background health check fires the `/api/new` endpoint with real data; `fetchFromDatabase` returns undefined; Node.js prints:

```
TypeError: Cannot read properties of undefined (reading 'items')
    at Object.<anonymous> (/packages/gateway/src/routes/new-endpoint.ts:4:26)
    at processTicksAndRejections (node:internal/process/task_queues:95:5)
(node:12345) UnhandledPromiseRejectionWarning: TypeError: Cannot read properties...
```

- Pattern match: `unhandled_rejection` (CRITICAL), `error` (HIGH), `stack_trace` (HIGH, attached)
- Writes `LOG_FINDINGS.md` with status `CRITICAL_FINDINGS`
- Returns to Phase 6 with: `Status: CRITICAL_FINDINGS, TOP ISSUES: unhandled_rejection at line 47`

**Phase 6**: Integration.

1. Implementer returned `DONE` → tests pass
2. Log-monitor returned `CRITICAL_FINDINGS`
3. Orchestrator reads `LOG_FINDINGS.md`, finds:

```
### UNHANDLED_REJECTION — 1 occurrence

#### Line 47: (node:12345) UnhandledPromiseRejectionWarning: TypeError: Cannot read...
```

4. Spawns fix-pass implementer (MAX_ITERATIONS: 3):

```
Critical runtime error found by log-monitor.

Read: ai/context/LOG_FINDINGS.md
Raw log: ai/context/raw_server.log

Issue: UnhandledPromiseRejectionWarning — TypeError: Cannot read properties of undefined
Location: packages/gateway/src/routes/new-endpoint.ts, line 4

Fix the null/undefined handling. The route at /api/new crashes when the database
returns undefined. Add a null check and return an appropriate error response.
```

5. Fix-pass implementer reads the error, updates the route:

```typescript
fastify.get('/api/new', async (request, reply) => {
  const data = await fetchFromDatabase();
  if (!data) {
    return reply.status(503).send({ error: 'Service temporarily unavailable' });
  }
  return { result: data.items };
});
```

6. Fix-pass runs tests → still green (mocks return valid data, null path is new code)
7. Fix-pass reports `DONE`

8. Orchestrator produces final summary:

```
Done. Here's what happened:
- Built: New /api/new endpoint in packages/gateway
- Tests: 47/47 passing
- Runtime log: CRITICAL_FINDINGS → fix pass applied (unhandled rejection in new route)
- Memory: Checkpointed to ai/memory/WORKING_MEMORY.md
```

---

## 15. Configuration

### Per-Project Config File

Create `ai/supervisor/log-monitor-config.json` to customize behavior:

```json
{
  "dev_cmd": "python manage.py runserver 0.0.0.0:8000",
  "duration_seconds": 60,
  "poll_interval_seconds": 8,
  "max_anomalies": 100,
  "max_per_category": 20,
  "platform_override": "linux",

  "extra_patterns": {
    "my_custom_error": [
      "MyAppException:",
      "BUSINESS_LOGIC_FAILURE"
    ]
  },

  "extra_noise": [
    "^Booting Puma",
    "^Puma starting in single mode",
    "^\\* Listening on"
  ],

  "severity_overrides": {
    "deprecation": "MEDIUM",
    "warning": "MEDIUM"
  },

  "early_exit_on": ["port_conflict", "oom", "segfault"],

  "report_path": "ai/context/LOG_FINDINGS.md",
  "raw_log_path": "ai/context/raw_server.log"
}
```

### Field Reference

| Field | Type | Default | Description |
|---|---|---|---|
| `dev_cmd` | string | auto-detect | Dev server command. Overrides all detection. |
| `duration_seconds` | number | 45 | Total monitoring window. |
| `poll_interval_seconds` | number | 5 | Seconds between analysis passes. |
| `max_anomalies` | number | 100 | Cap on total findings in report. |
| `max_per_category` | number | 20 | Cap per category in report display. |
| `platform_override` | string | auto | Force `win32`, `linux`, or `darwin`. |
| `extra_patterns` | object | `{}` | Custom category name → array of regex strings. |
| `extra_noise` | array | `[]` | Additional patterns to suppress (noise filter). |
| `severity_overrides` | object | `{}` | Override severity for built-in categories. |
| `early_exit_on` | array | `["port_conflict","oom","segfault"]` | Categories that trigger early exit. |
| `report_path` | string | `ai/context/LOG_FINDINGS.md` | Output report path. |
| `raw_log_path` | string | `ai/context/raw_server.log` | Raw log capture path. |

### Environment-Based Overrides

The log-monitor also respects environment variables (useful for CI):

| Env var | Equivalent config field |
|---|---|
| `LOG_MONITOR_CMD` | `dev_cmd` |
| `LOG_MONITOR_DURATION` | `duration_seconds` |
| `LOG_MONITOR_POLL` | `poll_interval_seconds` |
| `LOG_MONITOR_DISABLE` | Set to `1` to disable entirely |

### Disabling Per-Project

To disable the log-monitor for a specific project (e.g., a project with no server):

```json
// ai/supervisor/log-monitor-config.json
{ "dev_cmd": null }
```

Or set `LOG_MONITOR_DISABLE=1` in the project's `.env`.

### Custom Severity Example

A project where deprecation warnings are treated as blocking (e.g., approaching a major framework upgrade):

```json
{
  "severity_overrides": {
    "deprecation": "CRITICAL"
  }
}
```

This causes the orchestrator to spawn a fix pass for deprecation warnings, not just log them.

### Integrating with intake.json

The `/intake` command already detects `dev_cmd`. Ensure the field name in intake.json matches what log-monitor reads. If a project has a non-standard dev command that `/intake` doesn't detect, the recommended fix is to add it manually:

```bash
# After /intake, if dev_cmd is missing or wrong:
python3 -c "
import json
d = json.load(open('ai/supervisor/intake.json'))
d['stack']['dev_cmd'] = 'my-custom-server --port 8080'
json.dump(d, open('ai/supervisor/intake.json', 'w'), indent=2)
"
```

Or simply create `ai/supervisor/log-monitor-config.json` with the `dev_cmd` field, which takes precedence over intake.json.
