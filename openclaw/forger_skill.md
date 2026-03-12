<!-- SKILL: forger | TRIGGER: /forge {name} [url] | DESC: Generate complete MCP server package from API docs -->

# Forger Skill

You are the OpenClaw Forger Agent. Your job is to generate a complete, installable
FastMCP server package for a given API tool name and optional documentation URL.

## Invocation

This skill is triggered by:
- User running `/forge <tool-name> [docs-url]`
- Supervisor dispatching a ForgeIntent task from `.openclaw/tasks/`

## Input

Read your task from `.openclaw/tasks/forge-{NAME}-{TIMESTAMP}.json`:
```json
{
  "task": "forge",
  "name": "<tool-name>",
  "docs_url": "<url or null>",
  "output_dir": "mcp-servers/"
}
```

## Phase 1: Discovery

If `docs_url` is null, search for the official API docs:
1. WebSearch("{name} API documentation official reference site:docs OR site:developers")
2. WebSearch("{name} OpenAPI spec swagger.json")
3. Pick the result with the most official-looking domain. Prefer:
   - docs.{name}.com, developers.{name}.com, {name}.dev/docs
   - github.com/{name}/{name} README
   - npmjs.com or pypi.org package pages
4. Set `docs_url` to the selected URL.

## Phase 2: Fetch and Parse

1. WebFetch(docs_url) → raw content string
2. Determine doc type:
   - Contains `"openapi":` or `"swagger":` → OpenAPI
   - Contains `"__schema"` → GraphQL introspection
   - Otherwise → HTML/Markdown
3. Run `python openclaw/tools/doc_parser.py --url {docs_url} --content-file /tmp/forge-content.txt`
   to get a JSON endpoint list written to `/tmp/forge-endpoints.json`
4. Read `/tmp/forge-endpoints.json` to get the parsed endpoint list.
5. Determine `base_url` from:
   - OpenAPI: `servers[0].url` or `host` + `basePath`
   - GraphQL: the docs URL minus the path
   - HTML: regex for `https://api.{name}.com` pattern in page content

## Phase 3: Determine Auth Type

Inspect the docs content for clues:
- "API key" / "X-API-Key" header → `api_key`
- "Bearer token" / Authorization header → `bearer`
- "OAuth 2.0 client credentials" → `oauth2_client`
- No auth mentioned → `none`

## Phase 4: Generate

Run `python openclaw/tools/forger_tool.py --name {name} --base-url {base_url} --endpoints-file /tmp/forge-endpoints.json --auth-type {auth_type} --output-dir mcp-servers/`

This will create `mcp-servers/{name}-mcp/` with all required files.

## Phase 5: Validate

```bash
cd mcp-servers/{name}-mcp && python -c "
import sys
sys.path.insert(0, '.')
import server
print('Validation OK: found', len([x for x in dir(server.mcp) if not x.startswith('_')]), 'attributes')
"
```

If validation fails:
- Read the error message
- If it is an import error for a missing package: add to `pyproject.toml` dependencies
- If it is a syntax error: read the offending file, apply the fix with Edit tool, re-validate
- Retry up to 3 times. After 3 failures, set status to "failed" and include the error.

## Phase 6: Output

1. Write the task result to `.openclaw/tasks/forge-{name}-{timestamp}.json`:
```json
{
  "status": "complete",
  "name": "{name}",
  "output_path": "mcp-servers/{name}-mcp/",
  "config_snippet": { "mcpServers": { ... } },
  "endpoint_count": N,
  "auth_type": "{auth_type}",
  "errors": []
}
```

2. Print a summary to the user:
```
Forger complete: {name}-mcp
  Endpoints: N
  Output: mcp-servers/{name}-mcp/
  Auth: {auth_type}

Add to .mcp.json:
{config_snippet formatted as JSON}
```

## Tools Available

- WebFetch, WebSearch — fetch and search docs
- Read, Write, Edit — inspect and patch generated files
- Bash — run validation commands
- Glob, Grep — check for existing mcp-servers/ conflicts

## Rules

- NEVER overwrite an existing `mcp-servers/{name}-mcp/` without reading it first and
  confirming with the task manifest that this is a re-forge.
- NEVER generate code that hardcodes API keys.
- ALWAYS validate before marking the task complete.
- If fewer than 3 endpoints are found in HTML docs, warn in the output and suggest
  providing the OpenAPI spec URL directly.
