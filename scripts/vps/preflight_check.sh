#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# preflight_check.sh
#
# Verifies that all critical OpenClaw settings are active and the agent
# is operating in a healthy state. Catches silent degradation before it
# causes "the agent forgot everything" bugs.
#
# Run on the VPS host:
#   bash /opt/harness/scripts/vps/preflight_check.sh
#
# Run via cron (recommended every 30 minutes):
#   */30 * * * * root bash /opt/harness/scripts/vps/preflight_check.sh >> /var/log/harness-preflight.log 2>&1
#
# Exit codes:
#   0 = all checks pass
#   1 = one or more checks failed (degraded state)
#   2 = cannot read config (error)
# ---------------------------------------------------------------------------

set -uo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OPENCLAW_CONFIG="/docker/openclaw-kx9d/data/.openclaw/openclaw.json"
AGENTS_MD="/docker/openclaw-kx9d/data/.openclaw/workspace/AGENTS.md"
MEMORY_DIR="/docker/openclaw-kx9d/data/.openclaw/workspace/memory"
HARNESS_ROOT="/opt/harness"
CONTAINER_NAME="openclaw-kx9d-openclaw-1"
LOG_PREFIX="[preflight $(date -u +%Y-%m-%dT%H:%M:%SZ)]"

# How many consecutive failures before alerting
ALERT_THRESHOLD=2
FAIL_COUNTER_FILE="/tmp/preflight_fail_count"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
issues=()
warnings=()

check_pass() {
    echo "$LOG_PREFIX  OK: $1"
}

check_fail() {
    echo "$LOG_PREFIX  FAIL: $1"
    issues+=("$1")
}

check_warn() {
    echo "$LOG_PREFIX  WARN: $1"
    warnings+=("$1")
}

json_val() {
    # Extract a value from JSON using python3 (always available)
    local json_file="$1"
    local query="$2"
    python3 -c "
import json, sys
try:
    d = json.load(open('$json_file'))
    val = $query
    print(val if val is not None else '')
except Exception as e:
    print('')
" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

echo "$LOG_PREFIX === OpenClaw Preflight Check ==="

# --- Check 1: Config file exists and is valid JSON ---
if [[ ! -f "$OPENCLAW_CONFIG" ]]; then
    echo "$LOG_PREFIX  ERROR: Config not found at $OPENCLAW_CONFIG"
    exit 2
fi

python3 -c "import json; json.load(open('$OPENCLAW_CONFIG'))" 2>/dev/null
if [[ $? -ne 0 ]]; then
    echo "$LOG_PREFIX  ERROR: Config is not valid JSON"
    exit 2
fi
check_pass "Config file exists and is valid JSON"

# --- Check 2: Memory flush enabled ---
MF_ENABLED=$(json_val "$OPENCLAW_CONFIG" "d.get('agents',{}).get('defaults',{}).get('compaction',{}).get('memoryFlush',{}).get('enabled',False)")
if [[ "$MF_ENABLED" == "True" ]]; then
    check_pass "Memory flush enabled"
else
    check_fail "Memory flush is DISABLED (compaction.memoryFlush.enabled != true)"
fi

# --- Check 3: Session memory enabled ---
SM_ENABLED=$(json_val "$OPENCLAW_CONFIG" "d.get('agents',{}).get('defaults',{}).get('memorySearch',{}).get('experimental',{}).get('sessionMemory',False)")
if [[ "$SM_ENABLED" == "True" ]]; then
    check_pass "Session memory enabled"
else
    check_fail "Session memory is DISABLED (memorySearch.experimental.sessionMemory != true)"
fi

# --- Check 4: Hybrid search enabled ---
HS_ENABLED=$(json_val "$OPENCLAW_CONFIG" "d.get('agents',{}).get('defaults',{}).get('memorySearch',{}).get('query',{}).get('hybrid',{}).get('enabled',False)")
if [[ "$HS_ENABLED" == "True" ]]; then
    check_pass "Hybrid search enabled"
else
    check_fail "Hybrid search is DISABLED (memorySearch.query.hybrid.enabled != true)"
fi

# --- Check 5: Memory search sources include sessions ---
SOURCES=$(json_val "$OPENCLAW_CONFIG" "d.get('agents',{}).get('defaults',{}).get('memorySearch',{}).get('sources',[])")
if echo "$SOURCES" | grep -q "sessions"; then
    check_pass "Memory search sources include 'sessions'"
else
    check_fail "Memory search sources do NOT include 'sessions' (found: $SOURCES)"
fi

# --- Check 6: Compaction mode is safeguard ---
COMP_MODE=$(json_val "$OPENCLAW_CONFIG" "d.get('agents',{}).get('defaults',{}).get('compaction',{}).get('mode','')")
if [[ "$COMP_MODE" == "safeguard" ]]; then
    check_pass "Compaction mode = safeguard"
else
    check_warn "Compaction mode = '$COMP_MODE' (expected 'safeguard')"
fi

# --- Check 7: Internal hooks enabled ---
HOOKS_ENABLED=$(json_val "$OPENCLAW_CONFIG" "d.get('hooks',{}).get('internal',{}).get('enabled',False)")
if [[ "$HOOKS_ENABLED" == "True" ]]; then
    check_pass "Internal hooks enabled"
else
    check_fail "Internal hooks DISABLED (hooks.internal.enabled != true)"
fi

# --- Check 8: AGENTS.md exists and has learning loop ---
if [[ -f "$AGENTS_MD" ]]; then
    check_pass "AGENTS.md exists"
    if grep -qi "learning loop\|self-update\|model routing" "$AGENTS_MD" 2>/dev/null; then
        check_pass "AGENTS.md contains skill references"
    else
        check_warn "AGENTS.md may be missing skill references (no 'learning loop', 'self-update', or 'model routing' found)"
    fi
else
    check_fail "AGENTS.md not found at $AGENTS_MD"
fi

# --- Check 9: Memory directory exists ---
if [[ -d "$MEMORY_DIR" ]]; then
    check_pass "Memory directory exists"
else
    check_warn "Memory directory not found at $MEMORY_DIR (will be created on first flush)"
fi

# --- Check 10: Container is running ---
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "$CONTAINER_NAME"; then
    check_pass "Container '$CONTAINER_NAME' is running"
else
    check_fail "Container '$CONTAINER_NAME' is NOT running"
fi

# --- Check 11: Key tools accessible ---
for tool in "scripts/tools/self_update_tool.py" "scripts/tools/proxmox_tool.py" "openclaw/self_update_skill.md" "openclaw/model_routing_skill.md"; do
    if [[ -f "$HARNESS_ROOT/$tool" ]]; then
        check_pass "Tool accessible: $tool"
    else
        check_warn "Tool not found: $HARNESS_ROOT/$tool"
    fi
done

# --- Check 12: SSH gateway for self-update ---
if [[ -f "/usr/local/sbin/openclaw_ssh_gateway" ]]; then
    check_pass "Self-update SSH gateway installed"
else
    check_warn "Self-update SSH gateway not installed (run install_self_update.sh)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
TOTAL_ISSUES=${#issues[@]}
TOTAL_WARNINGS=${#warnings[@]}

if (( TOTAL_ISSUES == 0 )); then
    echo "$LOG_PREFIX === PASS ($TOTAL_WARNINGS warnings) ==="
    # Reset fail counter
    echo "0" > "$FAIL_COUNTER_FILE" 2>/dev/null || true

    # Output JSON for programmatic consumption
    python3 -c "
import json
print(json.dumps({
    'status': 'ok',
    'issues': [],
    'warnings': $(python3 -c "import json; print(json.dumps([$(printf '"%s",' "${warnings[@]}" | sed 's/,$//')]))" 2>/dev/null || echo '[]'),
    'checks_passed': True
}))
" 2>/dev/null || echo '{"status":"ok","checks_passed":true}'

    exit 0
else
    echo "$LOG_PREFIX === FAIL ($TOTAL_ISSUES issues, $TOTAL_WARNINGS warnings) ==="
    for issue in "${issues[@]}"; do
        echo "$LOG_PREFIX  - $issue"
    done

    # Track consecutive failures
    PREV_COUNT=0
    if [[ -f "$FAIL_COUNTER_FILE" ]]; then
        PREV_COUNT=$(cat "$FAIL_COUNTER_FILE" 2>/dev/null || echo 0)
    fi
    NEW_COUNT=$((PREV_COUNT + 1))
    echo "$NEW_COUNT" > "$FAIL_COUNTER_FILE" 2>/dev/null || true

    # Output JSON
    python3 -c "
import json
print(json.dumps({
    'status': 'degraded',
    'issues': $(python3 -c "import json; print(json.dumps([$(printf '"%s",' "${issues[@]}" | sed 's/,$//')]))" 2>/dev/null || echo '[]'),
    'warnings': $(python3 -c "import json; print(json.dumps([$(printf '"%s",' "${warnings[@]}" | sed 's/,$//')]))" 2>/dev/null || echo '[]'),
    'checks_passed': False,
    'consecutive_failures': $NEW_COUNT
}))
" 2>/dev/null || echo '{"status":"degraded","checks_passed":false}'

    exit 1
fi
