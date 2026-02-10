#!/bin/bash
# Agent Harness Template Bootstrap Installer (Linux/Mac)
# Installs the harness into the current directory

set -e

FORCE=false
SKIP_GIT=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE=true
            shift
            ;;
        --skip-git)
            SKIP_GIT=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

HARNESS_VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$(pwd)"

echo ""
echo "=== Agent Harness Template Bootstrap ==="
echo "Version: $HARNESS_VERSION"
echo "Target: $TARGET_DIR"
echo ""

# Check if harness already exists
if [ -f "$TARGET_DIR/ai/context/CONTEXT_PACK.md" ] && [ "$FORCE" != "true" ]; then
    echo "⚠️  Harness already exists in this directory!"
    read -p "Overwrite? (y/N) " response
    if [ "$response" != "y" ] && [ "$response" != "Y" ]; then
        echo "Aborted."
        exit 0
    fi
fi

# Check for Git
if command -v git &> /dev/null; then
    HAS_GIT=true
    echo "✓ Git detected"
else
    HAS_GIT=false
    echo "⚠️  Git not found - harness will work but version control recommended"
fi

# Create backup if needed
if [ "$SKIP_GIT" != "true" ] && [ "$HAS_GIT" = true ]; then
    if git status --porcelain 2>/dev/null | grep -q .; then
        echo ""
        echo "📦 Creating backup snapshot..."
        BACKUP_DIR="$TARGET_DIR/ai/_backups/$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$BACKUP_DIR"
        git status --porcelain | awk '{print $2}' | while read -r file; do
            if [ -f "$file" ]; then
                mkdir -p "$BACKUP_DIR/$(dirname "$file")"
                cp "$file" "$BACKUP_DIR/$file"
            fi
        done
        echo "✓ Backup created: $BACKUP_DIR"
    fi
fi

# Create directory structure
echo ""
echo "📁 Creating directory structure..."

DIRS=(
    "ai/context"
    "ai/context/specialized"
    "ai/memory"
    "ai/tests"
    "ai/research"
    "ai/research/landscape_reports"
    "ai/vendor"
    "ai/_backups"
    "ai/_locks"
    "ai/supervisor"
    "scripts/workers"
    "scripts/compilers"
    "scripts/hooks"
    "scripts/broker"
    "scripts/supervisor"
    ".cursor"
    ".claude/agents"
    ".claude/hooks"
    "openclaw"
    "gemini"
    ".openclaw/teams"
    ".openclaw/tasks"
    ".openclaw/inbox"
)

for dir in "${DIRS[@]}"; do
    mkdir -p "$TARGET_DIR/$dir"
    echo "  ✓ $dir"
done

# Create .gitkeep files for empty directories
GITKEEP_DIRS=(
    "ai/context/specialized"
    "ai/research/landscape_reports"
    "ai/vendor"
    "ai/_backups"
    "ai/_locks"
    ".openclaw/teams"
    ".openclaw/tasks"
    ".openclaw/inbox"
)

for dir in "${GITKEEP_DIRS[@]}"; do
    touch "$TARGET_DIR/$dir/.gitkeep"
done

# Create supervisor config files
echo ""
echo "⚙️  Creating supervisor configuration files..."

# Allowlists
if [ ! -f "$TARGET_DIR/ai/supervisor/allowlists.json" ]; then
    cat > "$TARGET_DIR/ai/supervisor/allowlists.json" << 'EOF'
{
  "version": "1.0",
  "default_allowlist": {
    "servers": [],
    "tools": []
  },
  "agent_profiles": {
    "orchestrator": {
      "servers": ["tool-broker"],
      "tools": ["search_tools", "describe_tool"]
    },
    "web-runner": {
      "servers": ["browser"],
      "tools": ["browser.*", "screenshot"]
    }
  }
}
EOF
    echo "  ✓ ai/supervisor/allowlists.json"
fi

# Gates
if [ ! -f "$TARGET_DIR/ai/supervisor/gates.json" ]; then
    cat > "$TARGET_DIR/ai/supervisor/gates.json" << 'EOF'
{
  "version": "1.0",
  "gates": {
    "wheel_scout": {
      "enabled": true,
      "required_for": ["build", "architecture", "system"],
      "timeout_seconds": 300
    },
    "budget": {
      "enabled": true,
      "max_tokens": 1000000,
      "max_api_calls": 1000
    }
  }
}
EOF
    echo "  ✓ ai/supervisor/gates.json"
fi

# MCP registry
if [ ! -f "$TARGET_DIR/ai/supervisor/mcp.servers.json" ]; then
    cat > "$TARGET_DIR/ai/supervisor/mcp.servers.json" << 'EOF'
{
  "version": "1.0",
  "description": "VPS-friendly MCP server registry",
  "servers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-playwright"],
      "enabled": true
    }
  }
}
EOF
    echo "  ✓ ai/supervisor/mcp.servers.json"
fi

# State files
if [ ! -f "$TARGET_DIR/ai/supervisor/state.json" ]; then
    cat > "$TARGET_DIR/ai/supervisor/state.json" << 'EOF'
{
  "version": "1.0",
  "current_task": null,
  "active_agents": [],
  "budget_used": {
    "tokens": 0,
    "api_calls": 0,
    "time_seconds": 0
  }
}
EOF
    echo "  ✓ ai/supervisor/state.json"
fi

if [ ! -f "$TARGET_DIR/ai/supervisor/task_queue.json" ]; then
    cat > "$TARGET_DIR/ai/supervisor/task_queue.json" << 'EOF'
{
  "version": "1.0",
  "pending": [],
  "in_progress": [],
  "completed": []
}
EOF
    echo "  ✓ ai/supervisor/task_queue.json"
fi

# Create platform integration files
echo ""
echo "🔌 Creating platform integrations..."

# Cursor hooks
if [ ! -f "$TARGET_DIR/.cursor/hooks.json" ]; then
    cat > "$TARGET_DIR/.cursor/hooks.json" << 'EOF'
{
  "version": "1.0",
  "hooks": [
    {
      "event": "file-watcher",
      "command": "scripts/hooks/file_watcher.ps1"
    }
  ]
}
EOF
    echo "  ✓ .cursor/hooks.json"
fi

# Claude settings
if [ ! -f "$TARGET_DIR/.claude/settings.json" ]; then
    cat > "$TARGET_DIR/.claude/settings.json" << 'EOF'
{
  "hooks": {
    "compaction": "scripts/compilers/memory_checkpoint.py",
    "rehydrate": "scripts/compilers/build_context_pack.py"
  },
  "supervisor": {
    "enabled": true
  }
}
EOF
    echo "  ✓ .claude/settings.json"
fi

echo ""
echo "✅ Harness installation complete!"
echo ""
echo "Next steps:"
echo "  1. Review HARNESS_README.md for usage instructions"
echo "  2. Configure platform-specific settings (see VPS_DEPLOYMENT.md)"
echo "  3. Configure tool broker allowlists in ai/supervisor/allowlists.json"
echo "  4. Run verification: bash scripts/verify_harness.sh (or pwsh scripts/verify_harness.ps1)"
echo ""
