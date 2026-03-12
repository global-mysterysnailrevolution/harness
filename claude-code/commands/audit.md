---
name: audit
description: >
  Query and analyze the Claude Code audit log. Read tool-calls.jsonl, filter by
  agent, tool, action class, status, or time range, and produce security summaries,
  timelines, loop detection, and per-agent breakdowns.
---

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
2. Parse each line as JSON. Skip blank lines and malformed lines (count them as warnings).
3. Apply any filters specified in the query.
4. Format the results as a clean markdown table or list.
5. Always show: total entries read, total matching, date range of the log.
6. For `summary`, produce a full breakdown table.
7. For `dangerous`, highlight the action_class and tool_id prominently.
8. For `loops`, group by args_hash and show the tool and repeat count.
9. For `classify`, run the scoring algorithm from action-policy.json on the given tool call.

## Output Format

### For filtered queries:
```
## Audit Results — [filter description]
Log range: 2026-03-10 → 2026-03-12 (847 total entries, 12 matching)

| Timestamp           | Event            | Tool          | Agent       | Class  | Status  |
|---------------------|------------------|---------------|-------------|--------|---------|
| 2026-03-12 14:23:01 | call_tool        | Bash          | implementer | exec   | ok      |
| 2026-03-12 14:23:05 | dangerous_action | Bash          | implementer | exec   | ok      |
```

### For `summary`:
```
## Audit Summary — Last Session (sess_abc123)
Period: 2026-03-12 14:20:01 → 2026-03-12 14:47:33 (47 calls, 27m 32s)

### By Event Type
| Event            | Count |
|------------------|-------|
| call_tool        | 44    |
| dangerous_action | 3     |
| call_blocked     | 0     |

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

### For `dangerous`:
```
## Dangerous Actions — Last Session
[N] dangerous action events found

| Timestamp           | Tool     | Agent       | Class      |
|---------------------|----------|-------------|------------|
| 2026-03-12 14:24:15 | Bash     | implementer | exec       |
| 2026-03-12 14:30:11 | WebFetch | wheel-scout | network    |
```

### For `loops`:
```
## Loop Detection — Repeated Identical Calls
[N] potential loops detected (same args_hash 3+ times)

| args_hash (first 12) | Tool  | Agent       | Repeat Count |
|----------------------|-------|-------------|--------------|
| a3f9e2b1c8d7         | Bash  | implementer | 5            |
```

### For `blocked`:
```
## Blocked Calls
[N] blocked calls found

| Timestamp           | Tool | Agent      | Reason    |
|---------------------|------|------------|-----------|
| 2026-03-12 14:25:44 | Bash | researcher | allowlist |
```

## Security Alerts

When running any query, flag these patterns as security concerns:
- Any entry with `action_class: credential` — credential exposure risk
- More than 10 `exec` events in a single session — unusual shell activity
- `status: blocked` with `reason: allowlist` — agent exceeded permissions
- `args_hash` repeating 5+ times for the same tool — likely infinite loop

State alerts clearly at the top of the output.

## Notes on the Log Format

- Each line is a JSON object (JSONL format — not a JSON array)
- UTF-8 encoding, LF line endings
- `args_hash` is SHA256 of the JSON-serialized tool arguments (secrets not logged)
- `dangerous: true` appears on both `call_tool` and `dangerous_action` entries for the same call
- Rotation events (`event: rotation`) are housekeeping — exclude from security summaries
