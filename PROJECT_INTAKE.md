# Project Intake Guide

## Overview

Before any agent swarm spins up, collect project requirements via the **Project Intake** phase. This ensures:

- Clear test requirements and boundaries
- Proper agent role configuration
- Budget and stopping conditions defined
- Security policies (code changes, forge) set upfront

## Intake Process

### 1. Run Intake Collection

```bash
python scripts/supervisor/project_intake.py collect
```

This creates `ai/supervisor/project.yaml` with a template structure.

### 2. Fill In Requirements

Edit `ai/supervisor/project.yaml`:

```yaml
target:
  urls:
    - "https://example.com"
    - "https://staging.example.com"
  auth_method: "api_key"
  auth_config:
    header: "X-API-Key"
    secret_name: "api_key"
  environments: ["staging", "prod"]

test_requirements:
  depth: "regression"  # smoke, regression, visual_diff
  allowed_domains:
    - "example.com"
    - "api.example.com"
  blocked_domains:
    - "ads.example.com"
  test_suite_path: "tests/"
  test_command: "npm test"

code_changes:
  allowed: true
  repo_path: "/path/to/repo"
  test_command: "npm test"
  build_command: "npm run build"

secrets:
  required:
    - "api_key"
    - "database_url"
  storage: "env"
  scope: "per_tool"

budget:
  max_tokens: 2000000
  max_api_calls: 2000
  max_cost_usd: 20.0
  max_time_seconds: 7200

stopping_conditions:
  - "all_tests_pass"
  - "budget_exceeded"
  - "max_iterations_reached"

agent_roles:
  wheel_scout:
    enabled: true
    required_for_build: true
  web_runner:
    enabled: true
    tools: ["browser", "screenshot", "console"]
  judge:
    enabled: true
    tools: ["image", "read", "compare"]
  fixer:
    enabled: true  # Only if code_changes.allowed
    tools: ["write", "read", "git", "exec"]

forge_policy:
  allow_new_servers: false
  approval_required: true
  allowed_sources: []  # Empty = no dynamic forge
```

### 3. Validate Intake

```bash
python scripts/supervisor/project_intake.py validate
```

Checks for:
- Required fields present
- Valid configuration values
- Consistency (e.g., fixer only if code changes allowed)

### 4. Generate Supervisor Config

```bash
python scripts/supervisor/project_intake.py generate
```

Creates `ai/supervisor/supervisor_config.json` from intake data.

## Intake Fields

### Target Configuration

- **urls**: List of URLs to test
- **auth_method**: Authentication type (`none`, `basic`, `oauth`, `api_key`)
- **auth_config**: Auth-specific settings
- **environments**: Environment names

### Test Requirements

- **depth**: Test depth (`smoke`, `regression`, `visual_diff`)
- **allowed_domains**: Domains allowed for testing
- **blocked_domains**: Domains to block
- **test_suite_path**: Path to test files
- **test_command**: Command to run tests

### Code Changes

- **allowed**: Whether code changes are permitted
- **repo_path**: Path to code repository
- **test_command**: Command to run tests after changes
- **build_command**: Command to build after changes

### Secrets

- **required**: List of secret names needed
- **storage**: Where secrets stored (`env`, `vault`, `file`)
- **scope**: Secret scope (`global`, `per_tool`)

### Budget

- **max_tokens**: Maximum tokens per run
- **max_api_calls**: Maximum API calls
- **max_cost_usd**: Maximum cost in USD
- **max_time_seconds**: Maximum execution time

### Stopping Conditions

List of conditions that stop execution:
- `all_tests_pass`
- `budget_exceeded`
- `max_iterations_reached`
- `error_threshold_exceeded`

### Agent Roles

Configuration for each agent role:
- **enabled**: Whether role is active
- **required_for_build**: Whether role must complete before building
- **tools**: List of tools allowed for role

### Forge Policy

- **allow_new_servers**: Whether new MCP servers can be installed
- **approval_required**: Whether approval is required
- **allowed_sources**: Allowed sources (`docker_hub`, `github`, `npm`)

## Integration with Supervisor

The supervisor uses intake data to:

1. **Configure agent roles**: Enable/disable roles based on intake
2. **Set tool allowlists**: Restrict tools per role
3. **Enforce budget**: Use intake budget limits
4. **Gate forge operations**: Check forge policy before allowing new servers
5. **Validate code changes**: Only allow if `code_changes.allowed` is true

## Example Workflow

```bash
# 1. Collect intake
python scripts/supervisor/project_intake.py collect

# 2. Edit project.yaml with requirements
vim ai/supervisor/project.yaml

# 3. Validate
python scripts/supervisor/project_intake.py validate

# 4. Generate supervisor config
python scripts/supervisor/project_intake.py generate

# 5. Start supervisor (uses generated config)
python scripts/supervisor/supervisor.py start
```

## References

- [Supervisor README](./SUPERVISOR_README.md)
- [Security Hardening](./SECURITY_HARDENING.md)
- [VPS Deployment](./VPS_DEPLOYMENT.md)
