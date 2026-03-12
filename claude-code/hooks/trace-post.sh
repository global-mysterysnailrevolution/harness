#!/usr/bin/env bash
# trace-post.sh — Audit log writer for Claude Code
# Runs after every tool call. Appends one JSONL entry to the audit log.
#
# Environment variables consumed:
#   CLAUDE_TOOL_NAME      — tool identifier (e.g., Bash, Read, mcp__github__create_issue)
#   CLAUDE_TOOL_INPUT     — JSON string of tool arguments
#   CLAUDE_TOOL_OUTPUT    — JSON string of tool result
#   CLAUDE_SESSION_ID     — session identifier (optional)
#   CLAUDE_AGENT_ID       — agent identifier (optional, harness convention)
#   CLAUDE_TOOL_STATUS    — "ok" or "error" (optional, defaults to inferring from output)
#   CLAUDE_TOOL_ERROR     — error message if status is error (optional)
#   CLAUDE_AUDIT_LOG      — override log file path (optional)
#   CLAUDE_AUDIT_DISABLED — set to 1 to disable logging entirely

set -euo pipefail

# ── 0. Disabled check ─────────────────────────────────────────────────────────
[[ "${CLAUDE_AUDIT_DISABLED:-0}" == "1" ]] && exit 0

# ── 1. Resolve paths ──────────────────────────────────────────────────────────
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
    if python3 -c "import sys,json; d=json.loads(sys.argv[1]); sys.exit(0 if 'error' not in d else 1)" "$TOOL_OUTPUT" 2>/dev/null; then
      STATUS="ok"
    else
      STATUS="error"
      ERROR_MSG="$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); print(str(d.get('error','unknown error'))[:200])" "$TOOL_OUTPUT" 2>/dev/null || echo "parse error")"
    fi
  fi
fi

# ── 6. Compute args hash (SHA256 of sorted JSON input) ────────────────────────
ARGS_HASH="$(python3 -c "
import sys, json, hashlib
try:
    data = json.loads(sys.argv[1])
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    print(hashlib.sha256(canonical.encode('utf-8')).hexdigest())
except Exception:
    print(hashlib.sha256(sys.argv[1].encode('utf-8', errors='replace')).hexdigest())
" "$TOOL_INPUT" 2>/dev/null || printf '%064d' 0)"

# ── 7. Classify action ────────────────────────────────────────────────────────
# Authoritative native tool overrides (no scoring needed for known tools)
case "$TOOL_ID" in
  Bash)                    ACTION_CLASS="exec" ;;
  Read|Glob|Grep)          ACTION_CLASS="read" ;;
  Edit|Write)              ACTION_CLASS="write" ;;
  WebFetch|WebSearch)      ACTION_CLASS="network" ;;
  Skill)                   ACTION_CLASS="read" ;;
  Task)                    ACTION_CLASS="exec" ;;
  TodoRead|TodoWrite)      ACTION_CLASS="read" ;;
  mcp__chrome-devtools__*) ACTION_CLASS="network" ;;
  mcp__github__*create*|mcp__github__*update*|mcp__github__*delete*|\
mcp__github__*merge*|mcp__github__*push*|mcp__github__*fork*)
    ACTION_CLASS="write" ;;
  mcp__github__*get*|mcp__github__*list*|mcp__github__*search*)
    ACTION_CLASS="read" ;;
  mcp__*__*authenticate*|mcp__*__*login*|mcp__*__*token*)
    ACTION_CLASS="credential" ;;
  mcp__*__*exec*|mcp__*__run_*|mcp__*__*evaluate*)
    ACTION_CLASS="exec" ;;
  *)
    # Keyword scoring fallback — combined string of tool name + input lowercased
    COMBINED="${TOOL_ID,,} $(echo "$TOOL_INPUT" | tr '[:upper:]' '[:lower:]' | tr -d '\n')"
    R=0; W=0; N=0; C=0; E=0

    # Read keywords (fetch scores both read and network)
    for kw in search list get describe read query find; do
      [[ "$COMBINED" == *"$kw"* ]] && R=$((R+1))
    done
    [[ "$COMBINED" == *"fetch"* ]] && R=$((R+1)) && N=$((N+1))

    # Write keywords
    for kw in write create update delete put patch remove move rename; do
      [[ "$COMBINED" == *"$kw"* ]] && W=$((W+1))
    done

    # Network keywords
    for kw in http curl request download upload send post; do
      [[ "$COMBINED" == *"$kw"* ]] && N=$((N+1))
    done

    # Credential keywords
    for kw in auth token secret key password credential login oauth; do
      [[ "$COMBINED" == *"$kw"* ]] && C=$((C+1))
    done

    # Exec keywords
    for kw in exec run shell command spawn evaluate interpret compile; do
      [[ "$COMBINED" == *"$kw"* ]] && E=$((E+1))
    done

    # Find max (tie-breaks in priority order: read > write > network > credential > exec)
    BEST="read"
    BEST_SCORE=0
    for pair in "read $R" "write $W" "network $N" "credential $C" "exec $E"; do
      cls="${pair%% *}"
      score="${pair##* }"
      if [[ "$score" -gt "$BEST_SCORE" ]]; then
        BEST_SCORE="$score"
        BEST="$cls"
      fi
    done
    ACTION_CLASS="$BEST"
    ;;
esac

# ── 8. Resolve server name ────────────────────────────────────────────────────
case "$TOOL_ID" in
  Bash|Read|Edit|Write|Glob|Grep|WebFetch|WebSearch|Skill|Task|TodoRead|TodoWrite)
    SERVER="native" ;;
  mcp__*__*)
    # Extract server: mcp__<server>__<tool> — server name may contain hyphens
    SERVER="$(echo "$TOOL_ID" | sed 's/^mcp__\([^_][^_]*\(-[^_][^_]*\)*\)__.*$/\1/' 2>/dev/null || echo "unknown")" ;;
  *)
    SERVER="unknown" ;;
esac

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

# ── 10. Check dangerous action set ────────────────────────────────────────────
DANGEROUS_CLASSES="exec credential network"
if [[ -f "$POLICY_FILE" ]]; then
  DANGEROUS_CLASSES="$(python3 -c "
import json
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

# ── 11. Get size metrics ───────────────────────────────────────────────────────
INPUT_SIZE="${#TOOL_INPUT}"
OUTPUT_SIZE="${#TOOL_OUTPUT}"

# ── 12. Get timestamp ─────────────────────────────────────────────────────────
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%S.000Z 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"

# ── 13. Write JSONL entries via Python (handles all JSON escaping correctly) ──
# Python is used to ensure correct escaping of arbitrary string values.
# Both entries (call_tool + optional dangerous_action) written in a single call.
python3 -c "
import sys, json

ts, tool_id, agent_id, action, args_hash, server, status, \
  session, is_dangerous_str, dur_str, error_msg, in_sz_str, out_sz_str = sys.argv[1:]

is_dangerous = is_dangerous_str == 'true'
dur          = int(dur_str) if dur_str else None
in_size      = int(in_sz_str) if in_sz_str else 0
out_size     = int(out_sz_str) if out_sz_str else 0

entry = {
    'timestamp':    ts,
    'event':        'call_tool',
    'tool_id':      tool_id,
    'agent_id':     agent_id,
    'action_class': action,
    'args_hash':    args_hash,
    'server':       server,
    'status':       status,
}
if session:
    entry['session_id'] = session
if dur is not None:
    entry['duration_ms'] = dur
if is_dangerous:
    entry['dangerous'] = True
if status == 'error' and error_msg:
    entry['error'] = error_msg
if in_size > 0:
    entry['tool_input_size'] = in_size
if out_size > 0:
    entry['tool_output_size'] = out_size

print(json.dumps(entry, ensure_ascii=False))

# Second entry for dangerous actions — allows simple grep audits
if is_dangerous:
    d = {
        'timestamp':    ts,
        'event':        'dangerous_action',
        'tool_id':      tool_id,
        'agent_id':     agent_id,
        'action_class': action,
        'args_hash':    args_hash,
        'server':       server,
        'status':       status,
        'dangerous':    True,
    }
    if session:
        d['session_id'] = session
    print(json.dumps(d, ensure_ascii=False))
" \
  "$TIMESTAMP" \
  "$TOOL_ID" \
  "$AGENT_ID" \
  "$ACTION_CLASS" \
  "$ARGS_HASH" \
  "$SERVER" \
  "$STATUS" \
  "${SESSION_ID:-}" \
  "$IS_DANGEROUS" \
  "${DURATION_MS:-}" \
  "${ERROR_MSG:-}" \
  "$INPUT_SIZE" \
  "$OUTPUT_SIZE" \
  >> "$AUDIT_LOG" 2>/dev/null || true

# ── 14. Rotation check (probabilistic — 1 in 50 calls to save overhead) ──────
RAND_CHECK=$((RANDOM % 50))
if [[ "$RAND_CHECK" -eq 0 ]] && [[ -x "$ROTATE_SCRIPT" ]]; then
  bash "$ROTATE_SCRIPT" 10000 30 &>/dev/null &
fi

exit 0
