<!-- SKILL: deep_chain | TRIGGER: internal | DESC: Sub-agent spawning protocol for recursive task delegation -->

# Deep Chain Protocol

This section defines when and how to spawn sub-agent sessions. Load this section
when your task would benefit from recursive delegation.

## When to Spawn a Sub-Agent

Spawn a sub-agent when:
- The sub-task is well-defined and independent (has a clear input and output)
- Doing it inline would pollute your context with unrelated work
- A specialized skill would do it better (forger for MCP generation, browser for web scraping, researcher for deep research)
- The sub-task could run faster in isolation (no context overhead)

Do NOT spawn a sub-agent when:
- The task takes fewer than 10 steps
- You are already at chain depth 3 (check your task file's `chain_depth`)
- The sub-task directly modifies files you are also modifying (conflicts)
- The sub-task result would be too large to integrate cleanly

## How to Spawn a Sub-Agent

Use `chain_dispatcher.py` via Bash:

```bash
python openclaw/tools/chain_dispatcher.py \
  --skill {skill_name} \
  --task "{one sentence task description}" \
  --context '{JSON with relevant facts the sub-agent needs}' \
  --parent-id {your_task_id} \
  --chain-depth {your chain_depth from task file} \
  --output /tmp/chain-result-{skill_name}.json
```

Then read the result:
```bash
cat /tmp/chain-result-{skill_name}.json
```

## Delegation Patterns

### Pattern: Need a new API integration

When you need to call an API and there is no MCP tool installed for it:

```bash
python openclaw/tools/chain_dispatcher.py \
  --skill forger_skill \
  --task "Generate MCP server for the {API_NAME} API" \
  --context '{"api_name": "{API_NAME}", "docs_url": "{DOCS_URL_OR_NULL}"}' \
  --parent-id {TASK_ID} \
  --chain-depth {DEPTH} \
  --output /tmp/chain-forge-result.json
```

After this completes:
- Read `/tmp/chain-forge-result.json` to get the `config_snippet`
- The MCP server is now installed and available in the current session

### Pattern: Need to scrape or interact with a website

```bash
python openclaw/tools/chain_dispatcher.py \
  --skill browser_skill \
  --task "{describe what you need from the website}" \
  --context '{"start_url": "{URL}", "goal": "{goal}", "max_pages": 5}' \
  --parent-id {TASK_ID} \
  --chain-depth {DEPTH} \
  --output /tmp/chain-browser-result.json
```

### Pattern: Need deep research before implementing

```bash
python openclaw/tools/chain_dispatcher.py \
  --skill researcher_skill \
  --task "Research: {topic or question}" \
  --context '{"focus": "{what aspect to focus on}", "depth": "standard"}' \
  --parent-id {TASK_ID} \
  --chain-depth {DEPTH} \
  --output /tmp/chain-research-result.json
```

### Pattern: Need to run and analyze tests independently

```bash
python openclaw/tools/chain_dispatcher.py \
  --skill implementer_skill \
  --task "Run tests and fix failures in {file_or_module}" \
  --context '{"workspace_path": ".", "test_target": "{target}", "fix_failures": true}' \
  --parent-id {TASK_ID} \
  --chain-depth {DEPTH} \
  --output /tmp/chain-test-fix-result.json
```

## Result Integration

After a sub-agent completes, read its result and extract ONLY what you need.
Do not paste the full result into your context. Extract the key facts:

Good:
```
Sub-agent result: forger created github-mcp with 12 tools.
Config added to .mcp.json. Now I can use github.createIssue, github.listPullRequests.
```

Bad:
```
Sub-agent result: {"status": "complete", "path": "mcp-servers/github-mcp", ... [full 200-line JSON paste] ...}
```

## Depth Limit

If `chain_dispatcher.py` returns `{"status": "depth_limit"}`, do NOT retry.
Instead, perform the sub-task inline as best you can, note the limitation in your
result, and continue.

## Timeout Handling

If `chain_dispatcher.py` returns `{"status": "timeout"}`, record the failure and
continue with partial information. Do not block indefinitely waiting for a slow
sub-agent.
