# ContextForge

OpenClaw-native workspace analysis, skill generation, durable memory, and observability.

## Architecture

ContextForge runs as a **sidecar service** alongside OpenClaw, never as a plugin. OpenClaw boots and functions normally even if ContextForge is down (Boot Invariant).

```
contextforge/
  packages/
    analyzer/       # Deterministic repo analysis (languages, frameworks, conventions, security)
    generator/      # Skill + agent + doc generation with provenance headers
    memory/         # Pending-to-promoted durable memory workflow
    security/       # Vetting pipeline, SBOM generation, provenance
    events/         # Structured events with correlation IDs
    ui/             # Observability dashboard (SSE-based event timeline)
  specs/
    skill-pack.schema.json    # Canonical skill pack schema
    event.schema.json         # Event/audit schema
    agent-profile.schema.json # Agent profile schema
    LANDSCAPE_RESEARCH.md     # Survey of 15+ related projects
  cli/
    contextforge.py           # CLI entry point
  deploy/
    docker-compose.yml        # Sidecar deployment
  tests/
    acceptance/               # End-to-end acceptance tests
```

## Quick Start

```bash
# Analyze a repository
python -m contextforge.cli.contextforge analyze /path/to/repo

# Generate skills and agents
python -m contextforge.cli.contextforge generate /path/to/repo --output-dir .contextforge

# Memory management
python -m contextforge.cli.contextforge memory submit "Always use python3" --category rule
python -m contextforge.cli.contextforge memory list-pending
python -m contextforge.cli.contextforge memory promote <entry_id>

# Security vetting
python -m contextforge.cli.contextforge vet /path/to/target

# Start observability UI
python -m contextforge.cli.contextforge ui --port 8900
```

## Generated Artifacts

### Skills (v1)
| Skill | Trigger | Description |
|---|---|---|
| `project-overview` | Auto-loaded | Stack, structure, conventions, security notes |
| `test-runner` | "test", "verify" | Run and manage tests for detected frameworks |
| `deploy-checker` | "deploy", Dockerfile | Check Docker/CI configs for issues |
| `dependency-auditor` | "audit", "vulnerabilities" | Audit deps with pip-audit/npm audit |
| `code-conventions` | Auto-loaded | Linter/formatter conventions |

### Agents (v1)
| Agent | Role | Tools Allowed | Approval Required |
|---|---|---|---|
| `planner` | Decompose tasks | fs, memory | write, exec |
| `reviewer` | Code review | fs, memory | write, exec |
| `security-auditor` | Security scanning | fs, exec | write, network |

## Key Design Principles

1. **Sidecar, not plugin** - OpenClaw must never crash due to ContextForge.
2. **Spec-first** - All artifacts match formal JSON schemas with provenance.
3. **Deterministic gates** - Security decisions use scanners, not LLM reasoning.
4. **Quarantine everything** - New tools pass vetting before use.
5. **Secrets never in context** - Env vars only; aggressive redaction.
6. **Pending-to-promoted memory** - New rules require human approval.
7. **Correlation IDs everywhere** - End-to-end traceability via run_id/trace_id.
8. **Idempotent generation** - Same source = same output.

## Security

- All generated files include provenance headers (generator version, source commit, analysis hash)
- Every skill pack gets a CycloneDX SBOM
- Vetting pipeline integrates Gitleaks, Trivy, pip-audit, npm audit (graceful degradation if not installed)
- Memory entries require human approval before becoming durable rules
- Structured audit log with correlation IDs for forensics

## Requirements

- Python 3.10+
- No required external dependencies for core functionality
- Optional: gitleaks, trivy, pip-audit for vetting pipeline
- Optional: llm-guard for prompt injection detection (`pip install contextforge[vetting]`)
