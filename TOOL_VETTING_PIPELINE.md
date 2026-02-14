# Tool Vetting Pipeline

The harness enforces two security gates on all tool/server usage:

- **Gate A** (vetting): scan proposed tools before approval
- **Gate B** (runtime): classify and audit every tool call at execution time

## Architecture

```
Agent proposes tool/server
  |
  v
forge_approval.propose_server()
  |
  v
[Quarantine workspace: no creds, limited network]
  |
  v
Gate A: Vetting Pipeline
  |-- Trivy (vulns + SBOM)
  |-- Gitleaks (secrets)
  |-- ClamAV (malware)
  |-- npm audit / pip-audit (SCA)
  |-- Semgrep (static analysis)
  |-- LLM Guard (prompt injection)
  |
  v
Vetting Report + SBOM + Findings
  |
  v
Verdict: PASS / WARN / FAIL
  |
  |-- FAIL --> auto-reject
  |-- WARN/PASS --> human reviews report
  |       |-- approve --> promote to MCPJungle
  |       |-- reject  --> done
  |
  v
MCPJungle Gateway (tool groups per agent)
  |
  v
Gate B: Runtime Policy (on every call_tool)
  |-- Allowlist check
  |-- Action classification (read/write/network/credential/exec)
  |-- Dangerous action gate
  |-- Audit log (JSONL)
  |
  v
Execute tool
```

## Quick Start

### 1. Install tools (VPS)

```bash
sudo bash scripts/vps/install_vetting_tools.sh
```

Installs: Trivy, Gitleaks, LLM Guard, pip-audit, Semgrep, openapi-mcp-generator, MCPJungle.

### 2. Propose a server

```bash
python3 scripts/broker/tool_broker.py propose \
  --server-name my-server \
  --source npm_package \
  --source-id @example/mcp-server \
  --source-path /path/to/downloaded/code
```

Vetting runs automatically. Results saved to `ai/supervisor/forge_approvals/<id>_VETTING.md`.

### 3. Review and approve

```bash
# View vetting report
python3 scripts/broker/tool_vetting.py report --proposal-id <id>

# Approve (only works if vetting passed or warned)
python3 scripts/broker/tool_broker.py approve --tool-id <id> --agent-id admin

# Override vetting (with justification)
python3 scripts/broker/tool_broker.py approve --tool-id <id> --agent-id admin --override-vetting
```

### 4. Forge from OpenAPI

```bash
python3 scripts/broker/tool_forge.py \
  --spec https://petstore3.swagger.io/api/v3/openapi.json \
  --name petstore
```

This generates an MCP server, vets it, and proposes for approval in one step.

## Scanners

All scanners gracefully degrade if not installed. The pipeline uses whatever is available.

| Scanner | What it checks | Install |
|---------|---------------|---------|
| **Trivy** | Vulnerabilities, misconfigs, SBOM | `apt install trivy` |
| **Gitleaks** | Hardcoded secrets | Binary from GitHub releases |
| **ClamAV** | Malware in archives/binaries | `apt install clamav` |
| **npm audit** | Node.js dependency vulns | Built into npm |
| **pip-audit** | Python dependency vulns | `pip install pip-audit` |
| **Semgrep** | Static analysis (community rules) | `pip install semgrep` |
| **LLM Guard** | Prompt injection in docs/READMEs | `pip install llm-guard` |

LLM Guard uses a fine-tuned DeBERTa model for prompt injection detection. Falls back to regex heuristics if not installed.

## Policy Configuration

Edit `ai/supervisor/vetting_policy.json`:

```json
{
  "max_critical": 0,
  "max_high": 2,
  "max_medium": 10,
  "max_secrets": 0,
  "max_malware": 0,
  "max_injection_signals": 1,
  "auto_reject_on_malware": true,
  "auto_reject_on_critical": true,
  "scanners_enabled": {
    "trivy": true,
    "gitleaks": true,
    "prompt_injection": true
  }
}
```

## Gate B: Runtime Policy

Every `call_tool()` through the broker:

1. **Classifies the action** as `read`, `write`, `network`, `credential`, or `exec`
2. **Flags dangerous actions** (exec, credential, network) in the audit log
3. **Logs to** `ai/supervisor/audit_log.jsonl` with tool_id, agent_id, action class, args hash, timestamp, result status

Configure in `ai/supervisor/security_policy.json` under `action_classification`.

## MCPJungle Gateway

MCPJungle replaces the custom MCP stdio-to-HTTP bridges with a proper gateway:

- Tool groups (per-agent tool subsets)
- Auth and access control
- Monitoring (OpenTelemetry, Prometheus)

```bash
# Start MCPJungle
docker compose -f deploy/docker-compose.mcpjungle.yml up -d

# Register servers
bash scripts/vps/register_mcp_servers.sh
```

The broker routes calls through MCPJungle when `MCPJUNGLE_GATEWAY_URL` is set.

## Artifacts

For each proposal, vetting generates:

- `<id>_VETTING.md` - Human-readable report with findings table
- `<id>_FINDINGS.json` - Machine-readable findings
- `<id>_SBOM.json` - Software Bill of Materials (CycloneDX)

All stored in `ai/supervisor/forge_approvals/`.

## CLI Reference

```bash
# Run vetting standalone
python3 scripts/broker/tool_vetting.py vet --source /path --proposal-id abc123

# View report
python3 scripts/broker/tool_vetting.py report --proposal-id abc123

# Forge from OpenAPI
python3 scripts/broker/tool_forge.py --spec URL --name server-name

# Propose server (auto-vets)
python3 scripts/broker/tool_broker.py propose --server-name X --source npm_package --source-id Y --source-path /path

# Re-vet existing proposal
python3 scripts/broker/tool_broker.py vet --proposal-id abc123 --source-path /path

# Approve / reject
python3 scripts/broker/tool_broker.py approve --tool-id abc123 --agent-id admin
python3 scripts/broker/tool_broker.py reject --tool-id abc123 --reason "Too many vulns"
```
