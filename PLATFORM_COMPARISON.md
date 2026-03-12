# Platform Comparison: OpenClaw vs Claude Code

Both platforms share the same harness philosophy (wheel-scout gates, context hydration, per-agent allowlists, memory checkpoints) but implement it differently based on platform capabilities.

## Feature Matrix

| Feature | OpenClaw | Claude Code |
|---------|----------|-------------|
| **Agent Spawning** | File-based communication, manual orchestration | Native Agent tool with model selection |
| **Deep Chaining** | Flat orchestrator (1 level) | 3+ level subagent chains |
| **Parallel Execution** | Sequential task processing | Wave execution (worktree-isolated parallelism) |
| **Wheel-Scout Gate** | Python GateEnforcer + gates.json | Agent-native (supervisor spawns wheel-scout) |
| **Context Hydration** | Python ContextHydrator + specialized compilers | Haiku agent builds 20-40 line packs |
| **Tool Broker** | Python broker with MCPJungle gateway | Haiku agent with meta-tool pattern |
| **Tool Vetting** | 7-scanner pipeline (Trivy, Gitleaks, ClamAV, Semgrep, LLM Guard, npm/pip audit) | Not yet implemented |
| **Audit Logging** | JSONL structured log with action classification | Not yet implemented |
| **Action Classification** | read/write/network/credential/exec categories | Not yet implemented |
| **Browser Automation** | web_adapter skill only | 4-tier stack (WebFetch -> playwright -> DevTools -> Chrome) |
| **Auth Escalation** | Manual | Auto-escalate to claude --chrome on login walls |
| **MCP Server Generation** | tool_forge.py (OpenAPI -> MCP) | Full forger agent (autonomous, any API docs) |
| **Implementation Loop** | Single-pass builder | Ralph Loop (implement -> test -> fix, max 2/5/7 iterations) |
| **Test Writing** | Parallel test-writer worker | Not yet (candidate for sidecar agent) |
| **Log Monitoring** | Background log sentinel worker | Not yet (candidate for sidecar agent) |
| **Memory System** | Pending-to-promoted (human approval required) | Auto-memory (MEMORY.md + topic files) |
| **ContextForge** | Full sidecar (analyzer, generator, memory, events, UI) | Not yet implemented |
| **SBOM Generation** | CycloneDX for vetted artifacts | Not yet implemented |
| **Deterministic Compilers** | Python/JS scripts for REPO_MAP, CONTEXT_PACK, etc. | Dynamic via agents (no static compilers) |
| **VPS Deployment** | Full (Hostinger, Docker, systemd, firewall) | N/A (runs locally) |
| **Cross-Platform** | OpenClaw, Cursor, Claude Code, Codex CLI, Gemini | Claude Code only |
| **Skill Router** | Manual routing | Haiku agent scans all capability sources |
| **Plugin Marketplace** | No | blocklist.json + known_marketplaces.json |
| **Budget Tracking** | Python BudgetTracker | Model-tier routing (haiku/sonnet/opus) |

## What to Port: OpenClaw -> Claude Code

### High Priority
1. **Tool Vetting Pipeline** - Security scanning before approving new MCP servers
2. **Audit Logging** - JSONL structured log for tool calls
3. **Action Classification** - Categorize tool calls as read/write/network/credential/exec

### Medium Priority
4. **Test Writer Agent** - Parallel test writing alongside implementation
5. **Log Monitor Agent** - Dev server log anomaly detection
6. **Self-Update Command** - Pull latest harness from GitHub
7. **ContextForge Analyzer** - Deterministic repo analysis

### Low Priority
8. **Deterministic Compilers** - Claude Code handles dynamically
9. **Pending-to-Promoted Memory** - Auto-memory works well
10. **File Locking** - Less needed with Claude Code execution model

## What to Port: Claude Code -> OpenClaw

### High Priority
1. **Forger Agent** - Full autonomous MCP server generation
2. **Browser Stack** - 4-tier automation with auth escalation
3. **Wave Execution** - Parallel task execution
4. **Ralph Loop** - Iterative implementation with failure-as-data

### Medium Priority
5. **Skill Router** - Fast capability matching
6. **Deep Chaining** - 3+ level agent spawning

## Shared Philosophy

Both platforms enforce:
- **Research before building** (Wheel-Scout gate)
- **Minimal context per agent** (Context Hydration)
- **Least privilege** (Per-Agent Allowlists)
- **Persistent memory** (Checkpoints survive session boundaries)
- **Budget awareness** (Cheap models for cheap tasks)
- **Failures are data** (Iterate, don't abandon)
