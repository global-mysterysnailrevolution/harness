---
name: intake
description: >
  Pre-swarm project intake. Scans the project to understand stack, conventions,
  test setup, memory state, and available tools before any orchestration begins.
  Run this once per project. Results cached in ai/supervisor/intake.json.
---

# Project Intake: /intake

Quick project assessment that feeds into all future orchestration for this project.

## Process

### Step 1: Detect Project Basics

```bash
# Stack detection
ls package.json pyproject.toml Cargo.toml go.mod pom.xml 2>/dev/null
git remote -v 2>/dev/null
git branch --show-current 2>/dev/null
```

Read the primary config file (package.json, pyproject.toml, etc.) to extract:
- Project name
- Dependencies / stack
- Scripts (build, test, dev, lint)
- Monorepo? (workspaces, turborepo, nx)

### Step 2: Detect Conventions

Quick scan for:
- **TypeScript config**: tsconfig.json → strict? module system?
- **Linter**: .eslintrc*, biome.json, prettier config
- **Test framework**: jest, vitest, pytest, mocha, cargo test
- **CI**: .github/workflows/, .gitlab-ci.yml, Jenkinsfile
- **Docker**: Dockerfile, docker-compose.yml
- **Env files**: .env.example, .env.local (note: don't read .env values)

### Step 3: Check Memory State

- Existing `ai/memory/WORKING_MEMORY.md`?
- Existing `ai/memory/DECISIONS.md`?
- Existing `.claude/projects/*/memory/MEMORY.md`?
- Existing `ai/research/landscape-*.md` reports?

### Step 4: Check Available Tools

- `.mcp.json` or MCP config in settings?
- Project-level `.claude/` with agents/commands/skills?
- Any hooks configured?

### Step 5: Write Intake

Create `ai/supervisor/` directory if needed. Write `ai/supervisor/intake.json`:

```json
{
  "project": "[name]",
  "root": "[absolute path]",
  "stack": {
    "languages": ["typescript", "solidity"],
    "frameworks": ["react", "fastify", "foundry"],
    "package_manager": "pnpm",
    "monorepo": true,
    "test_framework": "vitest",
    "test_cmd": "pnpm test",
    "build_cmd": "pnpm build",
    "dev_cmd": "pnpm dev"
  },
  "conventions": {
    "strict_typescript": true,
    "module_system": "NodeNext",
    "linter": "eslint",
    "formatter": "prettier"
  },
  "memory": {
    "has_working_memory": false,
    "has_decisions": false,
    "has_project_memory": true,
    "landscape_reports": []
  },
  "tools": {
    "mcp_servers": [],
    "project_agents": [],
    "project_commands": [],
    "hooks": []
  },
  "intake_time": "[ISO timestamp]"
}
```

### Step 6: Report

```
Project: [name] ([stack summary])
Structure: [monorepo? packages?]
Test: [framework + command]
Memory: [restored / fresh]
Tools: [N MCP servers, M agents, K commands]
Ready for /go
```
