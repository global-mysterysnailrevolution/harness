# Implementation Bridger Agent

## Purpose
Bridges research findings and repository structure into a concrete implementation plan.

## Responsibilities
- Combine REPO_MAP.md and FEATURE_RESEARCH.md
- Create concrete plan for THIS repository
- Identify specific files to modify
- List insertion points
- Generate CONTEXT_PACK.md with actionable plan

## Output
- `ai/context/CONTEXT_PACK.md` - Complete context pack with implementation plan

## Trigger
- Runs after repo-scout and web-researcher complete
- Part of context priming workflow

## Implementation
Uses `scripts/compilers/build_context_pack.py` to compile from multiple sources

## Integration
Called by context priming worker: `scripts/workers/context_priming.ps1`
