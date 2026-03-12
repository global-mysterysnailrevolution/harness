#!/bin/bash
# PreToolUse hook — logs trace event with rich session identity
input=$(cat)
ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
sid="${CLAUDE_SESSION_ID:-${PPID:-unknown}}"
cwd="${PWD:-unknown}"
tracedir="$HOME/.claude/trace"
mkdir -p "$tracedir"

# Extract project name from cwd for labeling
project=$(basename "$cwd" 2>/dev/null || echo "unknown")

# Extract tool name for quick stats
tool=$(echo "$input" | grep -o '"tool_name":"[^"]*"' | head -1 | cut -d'"' -f4)

# Register/update session in sessions.json (lightweight, no jq needed)
sessfile="$tracedir/sessions.json"
if [ ! -f "$sessfile" ]; then echo '{}' > "$sessfile"; fi

# Log the event with enriched metadata
echo "{\"phase\":\"pre\",\"ts\":\"$ts\",\"sid\":\"$sid\",\"cwd\":\"$cwd\",\"project\":\"$project\",\"tool\":\"$tool\",\"event\":$input}" >> "$tracedir/events.jsonl"

# Allow the tool to proceed
echo '{"decision":"allow"}'
