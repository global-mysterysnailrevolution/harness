---
description: Security-scan a directory (MCP server or tool) before approving it for use
allowed_tools: ["Bash", "Read", "Write", "Glob", "Grep"]
---

# /vet — Tool Vetting Pipeline

Runs Gate A security scanning on a proposed MCP server or tool directory before it is
approved for use. Spawns the `vet-scanner` agent to run 7 scanners with graceful
degradation, evaluates findings against policy, and writes a report to
`ai/supervisor/forge_approvals/`.

## Usage

```
/vet <path-to-directory>
```

## Examples

```
/vet ./mcp-servers/petstore-mcp/
/vet ~/generated/stripe-mcp
/vet .
```

## What Happens

1. Load policy from `~/.claude/plugins/vetting-policy.json` (or project override)
2. Generate a report ID: `vet_{YYYYMMDD}_{HHMMSS}_{basename}`
3. Spawn `vet-scanner` agent with the target path and policy
4. Agent runs 7 scanners (skipping unavailable ones gracefully)
5. Agent evaluates findings against policy thresholds
6. Agent writes three files to `ai/supervisor/forge_approvals/`:
   - `{id}_VETTING.md` — human-readable report
   - `{id}_FINDINGS.json` — machine-readable findings
   - `{id}_SBOM.json` — CycloneDX SBOM (if Trivy ran)
7. Return verdict and summary to user

## Verdicts

- **[PASS]**: All findings within policy thresholds. Safe to activate.
- **[WARN]**: High-severity findings or injection signals present, but within thresholds. Review recommended before activation.
- **[FAIL]**: Malware detected, critical vulnerabilities exceed limit, or thresholds exceeded. Do NOT activate.

## Instructions

The target path is: $ARGUMENTS

Steps:
1. Resolve the absolute path of: $ARGUMENTS
2. Check that the directory exists. If not, report an error and stop.
3. Generate report ID using current timestamp and the basename of the target path.
4. Ensure `ai/supervisor/forge_approvals/` exists (create if needed).
5. Read policy from `~/.claude/plugins/vetting-policy.json`. If missing, use built-in defaults.
6. Spawn the `vet-scanner` agent, passing:
   - `target_path`: absolute path of target
   - `report_id`: generated ID
   - `report_dir`: absolute path to `ai/supervisor/forge_approvals/`
   - `policy`: the loaded policy JSON
7. Wait for agent to complete and return verdict.
8. Print verdict summary to user:
   ```
   Vetting complete: [VERDICT]
   Report: ai/supervisor/forge_approvals/{id}_VETTING.md
   Counts: {critical} critical, {high} high, {medium} medium, {low} low
   ```
9. If FAIL: print rejection reasons and advise NOT to activate.
10. If WARN: print warning reasons and ask user to review report before activating.
11. If PASS: confirm safe to activate.
````
