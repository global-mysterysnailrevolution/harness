---
name: forge
description: >
  Auto-generate an MCP server from any API documentation URL or tool name.
  Produces a complete, installable MCP server package that exposes all capabilities
  as MCP tools. Use: /forge <tool-name> [docs-url]
---

# Tool Forge: /forge

Generate an MCP server from API docs. Adapted from the HackForge tool-forge engine.

## Input

`$ARGUMENTS` should be: `<tool-name> [docs-url]`
- If no URL given, search for "{tool-name} API documentation" first
- If a URL is given, fetch and parse it

## Step 1: Discover API Surface

1. Fetch the docs URL with WebFetch
2. Look for OpenAPI/Swagger spec links (common paths: `/openapi.json`, `/swagger.json`, `/api-docs`)
3. If machine-readable spec found, parse endpoints from it
4. Otherwise, extract endpoints from the human-readable docs

Extract for each endpoint:
- HTTP method + path
- Description
- Parameters (query, path, body) with types
- Auth method (header name, format)
- Response shape

## Step 2: Design MCP Tools

Map endpoints to MCP tools:
- Group related CRUD endpoints into single tools with an `action` param
- Name tools: `{tool}_{action}` (snake_case)
- Keep tool count manageable (aim for 5-15 tools max)
- Write clear descriptions (Claude will read these to decide when to use each tool)

## Step 3: Generate MCP Server

Create a Python MCP server package:

```
mcp-servers/{tool}-mcp/
├── pyproject.toml           # with [project.scripts] entry point
├── README.md                # usage instructions
└── src/{tool}_mcp/
    ├── __init__.py
    ├── server.py            # FastMCP server with @mcp.tool() decorators
    └── client.py            # httpx async client for the API
```

Requirements:
- Use `fastmcp` for the server framework
- Use `httpx.AsyncClient` for HTTP calls
- Use `pydantic` for input/output models
- Read API key from env var `{TOOL_UPPER}_API_KEY`
- Include error handling (return error dicts, never crash)
- Include retry logic for 429/5xx responses

## Step 4: Generate Config

Output the MCP config block for the user to add:

For Claude Code (`.mcp.json` or settings):
```json
{
  "mcpServers": {
    "{tool}": {
      "command": "uvx",
      "args": ["--from", "./mcp-servers/{tool}-mcp", "{tool}-mcp"],
      "env": {
        "{TOOL_UPPER}_API_KEY": "your-key-here"
      }
    }
  }
}
```

## Step 5: Validate

1. Check syntax: `python -c "import ast; ast.parse(open('server.py').read())"`
2. Check imports resolve
3. If API key available in env, make one test call
4. Report: tools generated, estimated token cost per call, any issues

## Output Summary

```
Forged: {tool} MCP Server
Tools: [N] tools from [M] endpoints
Files: mcp-servers/{tool}-mcp/ (ready to install)
Config: [show the JSON block to add]
Next: Add your API key and run `uvx mcp-servers/{tool}-mcp`
```
