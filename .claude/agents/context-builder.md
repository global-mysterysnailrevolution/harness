# Context Builder Agent

## Purpose
Builds specialized context for sub-agents on-demand by fetching documentation, cloning reference repos, and compiling context packs tailored to each agent's role and task.

## Responsibilities
- Analyze sub-agent requirements (language, framework, project type)
- Fetch documentation on-demand from various sources
- Clone reference repositories dynamically
- Extract relevant code examples
- Build specialized context packs
- Integrate with existing REPO_MAP and CONTEXT_PACK
- Inject context into sub-agent before spawning

## Output
- `ai/context/specialized/{agent-id}_CONTEXT.md` - Specialized context pack per agent

## Trigger
- Runs before spawning any sub-agent
- Triggered by supervisor when sub-agent is needed
- Caches context (reuses if < 1 hour old)

## Context Building Process

1. **Requirement Analysis**
   - Detects required knowledge domains from task description
   - Identifies languages, frameworks, project types
   - Determines documentation and reference repo needs

2. **Documentation Fetching**
   - Language-specific docs (Python, JavaScript, Rust, etc.)
   - Framework documentation (React, Django, etc.)
   - GitHub repository READMEs
   - Web search for additional docs

3. **Repository Cloning**
   - Clones reference repos to `ai/vendor/{repo-name}/`
   - Asks before cloning large/unknown repos
   - Extracts relevant code examples
   - Builds reference index

4. **Context Compilation**
   - Combines documentation, code examples, repo structure
   - Integrates with existing REPO_MAP and CONTEXT_PACK
   - Creates specialized context pack
   - Limits size to prevent token bloat

## Integration

### With Supervisor
- Supervisor calls context builder before spawning sub-agent
- Context builder returns path to specialized context
- Supervisor injects context into sub-agent spawn command

### With Tool Broker
- Uses tool broker to discover documentation tools
- Calls web search, GitHub API via broker
- Respects tool allowlists

### With Repo Cloner
- Manages cloned repositories
- Cleans up unused repos periodically
- Tracks usage for optimization

## Caching Strategy

- Context cached for 1 hour (configurable)
- Reuses existing context if task/role unchanged
- Invalidates cache when requirements change
- Per-agent context files prevent conflicts

## Example Workflow

1. Supervisor: "Need web-runner agent for React testing"
2. Context Builder analyzes: needs React docs, testing frameworks
3. Fetches: React documentation, Jest docs, Playwright docs
4. Clones: Example React test repos (if needed)
5. Compiles: Specialized context with React + testing focus
6. Supervisor spawns web-runner with pre-hydrated context
7. Web-runner starts with all relevant docs/examples loaded

## Implementation

- Worker: `scripts/workers/context_builder.ps1`
- Compiler: `scripts/compilers/build_specialized_context.py/js`
- Doc Fetcher: `scripts/broker/doc_fetcher.py`
- Repo Cloner: `scripts/broker/repo_cloner.py`
- Hydrator: `scripts/broker/context_hydrator.py`

## Benefits

1. **On-Demand**: Only fetches what's needed, when needed
2. **Specialized**: Each agent gets context tailored to their role
3. **Efficient**: Caches to avoid redundant fetching
4. **Integrated**: Works with existing harness context system
5. **Safe**: Asks before cloning large repos

## Future Enhancements

- Intelligent code example extraction (not just first 500 lines)
- Semantic search in cloned repos
- Documentation summarization
- Multi-language support
- Framework-specific context templates
