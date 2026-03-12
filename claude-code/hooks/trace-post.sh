#!/bin/bash
# PostToolUse hook — logs trace event with output summary + error detection
input=$(cat)
ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
sid="${CLAUDE_SESSION_ID:-${PPID:-unknown}}"
cwd="${PWD:-unknown}"
project=$(basename "$cwd" 2>/dev/null || echo "unknown")
tool=$(echo "$input" | grep -o '"tool_name":"[^"]*"' | head -1 | cut -d'"' -f4)
tracedir="$HOME/.claude/trace"
mkdir -p "$tracedir"

# Detect errors in output (grep for common error patterns)
has_error=""
if echo "$input" | grep -qi '"error"'; then has_error=",\"has_error\":true"; fi

echo "{\"phase\":\"post\",\"ts\":\"$ts\",\"sid\":\"$sid\",\"cwd\":\"$cwd\",\"project\":\"$project\",\"tool\":\"$tool\"${has_error},\"event\":$input}" >> "$tracedir/events.jsonl"
