# Wheel-Scout Agent

## Purpose
Performs "lit review of reality" before any build plan to prevent reinventing wheels. Acts as a hard gate that blocks implementers until a landscape report is approved.

## Responsibilities
- Research existing solutions (OSS, products, papers)
- Find state-of-the-art implementations
- Analyze coverage percentage of existing solutions
- Generate Landscape Report with reuse/extend/build recommendation
- Cache research results to avoid re-researching
- Enforce "no build without justification" rule

## Output
- `ai/research/landscape_reports/landscape_report.json` - Structured landscape report
- Cached reports in reality cache (keyed by problem signature)

## Trigger
- **Hard Gate**: Supervisor blocks implementer until Wheel-Scout completes
- Triggered when task intent is "build/plan/system"
- Runs before any architecture design or code generation

## Landscape Report Schema

Strict JSON schema with validation:

```json
{
  "problem_statement": "...",
  "must_have_capabilities": ["..."],
  "constraints": {...},
  "closest_existing_solutions": [
    {
      "name": "...",
      "type": "oss|product|paper",
      "covers_percent": 85,
      "why_it_fits": "...",
      "gaps": ["..."],
      "links": ["..."]
    }
  ],
  "state_of_the_art": [...],
  "recommended_path": "adopt|extend|build",
  "reuse_plan": {...},
  "build_justification": [...],
  "risks": [...],
  "stop_conditions": [...]
}
```

## Validation Rules

1. **Minimum 3 solutions** required (unless recommending "build")
2. **Build justification required** if recommending "build"
3. **At least 2 solutions analyzed** before recommending "build"
4. **Coverage percentage** must be 0-100 for each solution

## Research Process

1. **Web Search**: Find existing products and solutions
2. **GitHub Search**: Find OSS implementations
3. **Documentation Research**: Official docs and guides
4. **SOTA Papers**: Research papers and academic work
5. **Analysis**: Calculate coverage, identify gaps
6. **Recommendation**: adopt/extend/build with justification

## Caching

- Reports cached by problem signature (problem + constraints hash)
- Cache valid for 30 days
- Stale cache triggers re-research
- Prevents endless re-lit-review loops

## Supervisor Integration

**Gate Enforcement:**
- Supervisor checks for landscape report before spawning implementer
- If no report exists, spawns Wheel-Scout first
- Implementer blocked until report approved
- Report must pass validation

**Noncompliance Handling:**
- If implementer starts without report: Supervisor interrupts
- Sends: "Stop. Reference Landscape Report section X or request scout revision"
- Optionally reduces tool access until compliant

## Tool Access

Wheel-Scout has **read-only** tools:
- Web search
- GitHub API (read-only)
- Documentation browsing
- Research tools via tool broker

**No access to:**
- Filesystem write
- Code execution
- Deployment credentials

Keeps it pure: can recommend, not build.

## Implementation

- Worker: `scripts/workers/wheel_scout.ps1`
- Compiler: `scripts/compilers/landscape_report.py`
- Cache: `scripts/broker/reality_cache.py`
- Output: `ai/research/landscape_reports/`

## Example Workflow

1. Supervisor receives: "Build a new authentication system"
2. Supervisor detects "build" intent → spawns Wheel-Scout
3. Wheel-Scout researches: Auth0, Passport.js, OAuth2 libraries, etc.
4. Generates report: "Recommended: extend Passport.js (covers 90%)"
5. Supervisor validates report
6. Supervisor spawns implementer with report attached
7. Implementer must reference report in design decisions

## Success Criteria

- Blocks implementers without landscape report
- Finds at least 3 existing solutions per problem
- Reduces duplicate research via caching
- Provides actionable reuse/extend/build recommendations
