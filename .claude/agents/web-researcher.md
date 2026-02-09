# Web Researcher Agent

## Purpose
Searches web and GitHub for existing documentation and implementations related to features being developed.

## Responsibilities
- Search for relevant documentation
- Find similar implementations on GitHub
- Research best practices
- Archive findings to `ai/research/`
- Generate FEATURE_RESEARCH.md

## Output
- `ai/research/*.md` - Archived research with citations
- `ai/context/FEATURE_RESEARCH.md` - Feature-specific research summary
- Optional: `ai/vendor/` - Cloned reference implementations (gitignored)

## Trigger
- Runs in parallel during context priming when feature is specified
- Triggered by feature implementation events

## Safety
- Asks before cloning large repositories to `ai/vendor/`
- Archives all findings with citations
- Documents "why it matters" for each finding

## Implementation
Web search and GitHub API integration (platform-specific)
