# Repo Scout Agent

## Purpose
Maps repository structure, identifies insertion points, and documents architecture.

## Responsibilities
- Analyze repository structure
- Detect programming language and framework stack
- Identify common insertion points (src/, lib/, components/, etc.)
- Generate REPO_MAP.md
- Update when structure changes significantly

## Output
- `ai/context/REPO_MAP.md` - Repository structure map

## Trigger
- Always runs in parallel during context priming
- Runs when repository structure changes detected

## Implementation
Uses `scripts/compilers/build_repo_map.py` or `build_repo_map.js`

## Integration
Called by context priming worker: `scripts/workers/context_priming.ps1`
