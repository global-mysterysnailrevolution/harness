# Forger Agent — OpenClaw Port

## 1. Overview

The Forger Agent in Claude Code is a fully autonomous MCP server generator. Given a tool name and an optional documentation URL, it:

1. Fetches API documentation (OpenAPI spec, REST reference, or plain HTML docs)
2. Parses all available endpoints, their parameters, request/response shapes, and authentication requirements
3. Generates a complete, installable FastMCP server package under `mcp-servers/{name}-mcp/`
4. Validates the generated code by attempting a dry-run import check
5. Outputs a ready-to-use `.mcp.json` configuration snippet

The entire workflow requires zero user interaction beyond the initial `/forge` invocation. The agent handles ambiguity internally — if the docs URL is not provided, it searches for official API documentation automatically.

Invocation in Claude Code:

```
/forge stripe https://stripe.com/docs/api
/forge github  # agent finds docs via WebSearch
/forge notion https://developers.notion.com/reference
```

Claude Code's `tool_forge.py` is a limited precursor that only handles well-formed OpenAPI JSON. The Forger Agent handles OpenAPI 2/3, plain REST reference pages, GraphQL introspection endpoints, and partially-structured HTML documentation.

---

## 2. Problem Statement

OpenClaw's current `tool_forge.py` script:

- Accepts only a `--spec-url` pointing to a valid OpenAPI 3.x JSON document
- Performs no discovery — the user must already know and provide the exact spec URL
- Generates a thin wrapper with no error handling, no authentication scaffolding, and no type coercion
- Does not validate the output
- Has no concept of a skill invocation path — it is a standalone script, not an integrated workflow

This leaves a significant capability gap:

| Capability | Claude Code Forger | OpenClaw tool_forge.py |
|---|---|---|
| Auto-discover docs | Yes (WebSearch) | No |
| Parse OpenAPI 2/3 | Yes | OpenAPI 3 only |
| Parse HTML REST docs | Yes | No |
| Parse GraphQL introspection | Yes | No |
| Generate auth scaffolding | Yes | No |
| Validate generated code | Yes (import check) | No |
| Output .mcp.json config | Yes | No |
| Integrated skill invocation | Yes (/forge) | No (CLI only) |

Porting the Forger Agent fills this gap and gives OpenClaw users a first-class tool-generation capability.

---

## 3. Source Analysis

### 3.1 Claude Code Forger Flow

The Claude Code forger is defined in the `agents/forger.md` prompt. The supervisor dispatches to it during `/go` when a build task is detected that requires a new external tool. It can also be invoked directly via the `/forge` slash command.

**Phase 1: Discovery**

If no docs URL is provided, the agent executes:
```
WebSearch("{tool_name} API documentation official reference")
WebSearch("{tool_name} OpenAPI spec swagger.json")
```

It ranks results by: official domain > GitHub > npm/PyPI > third-party. It picks the top candidate and proceeds.

**Phase 2: Fetch and Parse**

The agent fetches the docs URL with `WebFetch`. It then inspects the content to determine the doc type:

- If Content-Type is `application/json` and contains `"openapi"` or `"swagger"` key → OpenAPI
- If content contains `{"data":{"__schema":` → GraphQL introspection
- Otherwise → HTML/Markdown REST docs

For OpenAPI, the agent reads the `paths` object and extracts each endpoint's method, path, operationId, parameters, requestBody, and response schemas.

For HTML/Markdown docs, the agent uses a structured extraction prompt on the fetched text to identify endpoint patterns like `POST /v1/charges` with parameter tables.

For GraphQL, the agent reads the introspection result's `types` and `queryType`/`mutationType` fields to build tool definitions.

**Phase 3: Code Generation**

The agent generates:

```
mcp-servers/{name}-mcp/
├── __init__.py
├── server.py          # FastMCP server with all tools
├── auth.py            # API key / OAuth2 client credentials scaffolding
├── models.py          # Pydantic models for request/response types
├── pyproject.toml     # package metadata + dependencies
└── README.md          # usage + config instructions
```

The `server.py` uses FastMCP's `@mcp.tool()` decorator pattern:

```python
from fastmcp import FastMCP
from .auth import get_headers
import httpx

mcp = FastMCP("{name}")

@mcp.tool()
async def create_charge(amount: int, currency: str, source: str) -> dict:
    """Create a new charge. amount in cents."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.stripe.com/v1/charges",
            headers=get_headers(),
            data={"amount": amount, "currency": currency, "source": source}
        )
        r.raise_for_status()
        return r.json()
```

**Phase 4: Validation**

The agent runs:
```bash
cd mcp-servers/{name}-mcp && python -c "import server; print('OK')"
```

If this fails, it reads the error, patches the specific issue, and retries up to 3 times.

**Phase 5: Config Output**

The agent writes the `.mcp.json` entry:

```json
{
  "mcpServers": {
    "{name}": {
      "command": "python",
      "args": ["-m", "mcp-servers.{name}-mcp.server"],
      "env": {
        "{NAME}_API_KEY": ""
      }
    }
  }
}
```

### 3.2 Key Agent Capabilities Used

- `WebFetch` — fetch docs URL
- `WebSearch` — discover docs if URL not provided
- `Read`, `Write`, `Edit` — file operations for generated code
- `Bash` — validation step (`python -c "import ..."`)
- `Glob`, `Grep` — inspect existing mcp-servers/ for conflicts

### 3.3 Model Selection

The forger runs on `sonnet` (not haiku) because:
- Parsing heterogeneous doc formats requires strong reasoning
- Code generation quality matters — the output is production-installed
- The task is bounded (one invocation per tool), so cost is acceptable

---

## 4. Target Architecture

OpenClaw does not have a native `Agent` tool or model-routing API. Porting the Forger requires translating the agent into:

1. **A Forger skill** (`openclaw/forger_skill.md`) — the orchestration prompt
2. **A Python tool generator** (`openclaw/tools/forger_tool.py`) — replaces the inline bash/write operations
3. **A doc parser module** (`openclaw/tools/doc_parser.py`) — handles OpenAPI, HTML, GraphQL
4. **Config additions** to `supervisor_config.json` and `agent_profiles.json`

The skill is invoked when the user runs `/forge` or when the supervisor detects a "need new MCP tool" intent during task planning.

OpenClaw agents communicate through shared workspace files. The Forger writes intermediate state to `.openclaw/tasks/forge-{name}-{timestamp}.json` so the supervisor can track progress and inject the final config snippet into the session context.

### 4.1 Architecture Diagram

```
User: /forge stripe https://stripe.com/docs/api
         │
         ▼
  orchestrator_prompt.md
  ─ detects ForgeIntent
  ─ dispatches to forger_skill.md
         │
         ▼
  forger_skill.md (OpenClaw session, sonnet model)
  ─ Phase 1: Discovery (WebFetch/WebSearch)
  ─ Phase 2: Parse (doc_parser.py)
  ─ Phase 3: Generate (forger_tool.py)
  ─ Phase 4: Validate (bash)
  ─ Phase 5: Config (write .mcp.json snippet)
         │
         ▼
  .openclaw/tasks/forge-stripe-{ts}.json
  {status, output_path, config_snippet, errors}
         │
         ▼
  orchestrator reads result, surfaces to user
```

---

## 5. File Layout

Files to create or modify in the OpenClaw workspace:

```
openclaw/
├── forger_skill.md                    # NEW — main skill prompt
├── tools/
│   ├── forger_tool.py                 # NEW — code generator
│   └── doc_parser.py                  # NEW — doc type detection + extraction
├── supervisor_config.json             # MODIFY — add forger gate + tool allowlist
└── agent_profiles.json                # MODIFY — add forger profile

.openclaw/tasks/
└── forge-{name}-{timestamp}.json      # RUNTIME — task state file

mcp-servers/                           # OUTPUT — generated servers land here
└── {name}-mcp/
    ├── __init__.py
    ├── server.py
    ├── auth.py
    ├── models.py
    ├── pyproject.toml
    └── README.md
```

---

## 6. Adaptation Strategy

### 6.1 No Native Agent Tool

Claude Code's forger runs as a spawned sub-agent with its own context window. OpenClaw does not have this primitive.

**Adaptation**: The forger skill runs as a dedicated OpenClaw session with the `forger` agent profile. The orchestrator launches it as a subprocess via the session runner with a task-scoped workspace. The session reads and writes to `.openclaw/tasks/forge-{name}-{ts}.json` for state handoff.

### 6.2 No Inline Model Selection

Claude Code selects `sonnet` for the forger at the agent definition level. OpenClaw model routing is defined in `supervisor_config.json`.

**Adaptation**: Add a `forger` entry to `model_routing` in `supervisor_config.json` that pins `claude-sonnet-4-5` (or the configured sonnet variant). The `model_routing_skill.md` already handles model dispatch — just add the forger as a named route.

### 6.3 WebFetch and WebSearch

These tools exist in OpenClaw's web adapter (`web_adapter_skill.md`). The forger skill must declare them in its tool allowlist to use them.

**Adaptation**: Add `WebFetch` and `WebSearch` to the forger's `allowed_tools` in `agent_profiles.json`.

### 6.4 File Write Operations

Claude Code's forger uses `Write` and `Edit` tools directly. In OpenClaw, file writes from agent sessions go through the `forger_tool.py` which is called as a local tool from within the skill.

**Adaptation**: The forger skill invokes `forger_tool.py` via a structured tool call (OpenClaw's local tool protocol), passing the parsed endpoint list and the target directory. The Python tool handles all file creation.

### 6.5 Validation Step

Claude Code validates by running `python -c "import server"` inline. OpenClaw agents can run bash commands if `Bash` is in their tool allowlist.

**Adaptation**: Add `Bash` to the forger profile's `allowed_tools`. Limit the allowlist to read-only bash (no `rm`, no `git push`) by adding a `bash_allowlist` pattern filter in the profile.

---

## 7. Implementation Plan

### Step 1: Create `doc_parser.py`

```python
# openclaw/tools/doc_parser.py
"""
Detect and parse API documentation into a normalized endpoint list.
Handles: OpenAPI 2.x, OpenAPI 3.x, GraphQL introspection, HTML/Markdown REST docs.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class EndpointParam:
    name: str
    location: str  # "query" | "path" | "body" | "header"
    type: str      # "string" | "integer" | "boolean" | "object" | "array"
    required: bool
    description: str = ""

@dataclass
class Endpoint:
    method: str         # "GET" | "POST" | "PUT" | "DELETE" | "PATCH"
    path: str           # "/v1/charges"
    operation_id: str   # "createCharge"
    summary: str
    params: list[EndpointParam] = field(default_factory=list)
    body_schema: Optional[dict] = None
    response_schema: Optional[dict] = None
    auth_required: bool = True

def detect_doc_type(content: str, url: str) -> str:
    """Returns: 'openapi', 'graphql', 'html'"""
    try:
        data = json.loads(content)
        if "openapi" in data or "swagger" in data:
            return "openapi"
        if "data" in data and "__schema" in data.get("data", {}):
            return "graphql"
    except json.JSONDecodeError:
        pass
    return "html"

def parse_openapi(content: str) -> list[Endpoint]:
    data = json.loads(content)
    version = data.get("openapi", data.get("swagger", "2.0"))
    endpoints = []

    for path, methods in data.get("paths", {}).items():
        for method, op in methods.items():
            if method.upper() not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"):
                continue

            operation_id = op.get("operationId", "")
            if not operation_id:
                # generate from method + path
                parts = [p for p in path.split("/") if p and not p.startswith("{")]
                operation_id = method.lower() + "".join(p.capitalize() for p in parts[-2:])

            params = []
            for p in op.get("parameters", []):
                schema = p.get("schema", {})
                params.append(EndpointParam(
                    name=p["name"],
                    location=p.get("in", "query"),
                    type=schema.get("type", "string"),
                    required=p.get("required", False),
                    description=p.get("description", "")
                ))

            body_schema = None
            if "requestBody" in op:
                content_types = op["requestBody"].get("content", {})
                for ct in ("application/json", "application/x-www-form-urlencoded"):
                    if ct in content_types:
                        body_schema = content_types[ct].get("schema")
                        if body_schema and "properties" in body_schema:
                            for prop_name, prop_schema in body_schema["properties"].items():
                                required_props = body_schema.get("required", [])
                                params.append(EndpointParam(
                                    name=prop_name,
                                    location="body",
                                    type=prop_schema.get("type", "string"),
                                    required=prop_name in required_props,
                                    description=prop_schema.get("description", "")
                                ))
                        break

            # OpenAPI 2 requestBody (formData / body)
            for p in op.get("parameters", []):
                if p.get("in") in ("formData", "body"):
                    schema = p.get("schema", {})
                    if "properties" in schema:
                        for prop_name, prop_schema in schema["properties"].items():
                            params.append(EndpointParam(
                                name=prop_name,
                                location="body",
                                type=prop_schema.get("type", "string"),
                                required=prop_name in schema.get("required", []),
                                description=prop_schema.get("description", "")
                            ))

            endpoints.append(Endpoint(
                method=method.upper(),
                path=path,
                operation_id=operation_id,
                summary=op.get("summary", op.get("description", "")[:80]),
                params=[p for p in params if p.location != "formData"],
                body_schema=body_schema,
                auth_required=bool(op.get("security") or data.get("security"))
            ))

    return endpoints

def parse_graphql(content: str) -> list[Endpoint]:
    """Convert GraphQL mutations/queries into synthetic REST-style endpoints."""
    data = json.loads(content)
    schema = data.get("data", {}).get("__schema", {})
    endpoints = []

    for type_info in schema.get("types", []):
        if type_info["name"] in ("Query", "Mutation"):
            method = "POST" if type_info["name"] == "Mutation" else "GET"
            for field_info in type_info.get("fields", []):
                params = []
                for arg in field_info.get("args", []):
                    arg_type = arg.get("type", {})
                    while arg_type.get("ofType"):
                        arg_type = arg_type["ofType"]
                    params.append(EndpointParam(
                        name=arg["name"],
                        location="body",
                        type=arg_type.get("name", "string").lower(),
                        required=arg.get("type", {}).get("kind") == "NON_NULL",
                        description=arg.get("description", "")
                    ))
                endpoints.append(Endpoint(
                    method=method,
                    path=f"/graphql#{field_info['name']}",
                    operation_id=field_info["name"],
                    summary=field_info.get("description", "")[:80],
                    params=params,
                    auth_required=True
                ))

    return endpoints

def parse_html_docs(content: str, llm_extract_fn=None) -> list[Endpoint]:
    """
    Attempt regex-based extraction first.
    Falls back to llm_extract_fn(content) -> list[dict] if provided.
    """
    endpoints = []

    # Pattern: "GET /v1/resource" or "POST /api/v2/resource"
    pattern = re.compile(
        r'\b(GET|POST|PUT|DELETE|PATCH)\s+(/[\w/{}._-]+)',
        re.MULTILINE
    )

    seen = set()
    for match in pattern.finditer(content):
        method, path = match.group(1), match.group(2)
        key = f"{method}:{path}"
        if key in seen:
            continue
        seen.add(key)

        # Try to find a surrounding heading (50 chars before match)
        start = max(0, match.start() - 200)
        context = content[start:match.start()]
        heading_match = re.search(r'#+\s*(.+?)$|<h[1-4][^>]*>(.+?)</h[1-4]>', context, re.MULTILINE)
        summary = ""
        if heading_match:
            summary = (heading_match.group(1) or heading_match.group(2) or "").strip()[:80]

        parts = [p for p in path.split("/") if p and not p.startswith("{")]
        operation_id = method.lower() + "".join(p.capitalize() for p in parts[-2:])

        endpoints.append(Endpoint(
            method=method,
            path=path,
            operation_id=operation_id,
            summary=summary,
            params=[],
            auth_required=True
        ))

    if not endpoints and llm_extract_fn:
        raw = llm_extract_fn(content[:8000])  # pass truncated content
        for item in raw:
            endpoints.append(Endpoint(**item))

    return endpoints

def parse_docs(content: str, url: str, llm_extract_fn=None) -> list[Endpoint]:
    """Top-level parser — auto-detects doc type and delegates."""
    doc_type = detect_doc_type(content, url)
    if doc_type == "openapi":
        return parse_openapi(content)
    elif doc_type == "graphql":
        return parse_graphql(content)
    else:
        return parse_html_docs(content, llm_extract_fn)
```

### Step 2: Create `forger_tool.py`

```python
# openclaw/tools/forger_tool.py
"""
Generates a complete FastMCP server package from a parsed endpoint list.
Called by forger_skill.md after doc parsing is complete.
"""

import os
import json
import re
from pathlib import Path
from .doc_parser import Endpoint, EndpointParam

PYTHON_TYPE_MAP = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "object": "dict",
    "array": "list",
}

def _py_type(t: str) -> str:
    return PYTHON_TYPE_MAP.get(t, "str")

def _to_python_name(s: str) -> str:
    """Convert camelCase or PascalCase or hyphen-case to snake_case."""
    s = re.sub(r'[-\s]+', '_', s)
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s)
    s = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', s)
    return s.lower()

def generate_server(
    name: str,
    base_url: str,
    endpoints: list[Endpoint],
    auth_type: str,  # "api_key" | "bearer" | "oauth2_client" | "none"
    output_dir: str
) -> dict:
    """
    Generates the complete mcp-servers/{name}-mcp/ package.
    Returns {"success": bool, "path": str, "config_snippet": dict, "errors": list[str]}.
    """
    pkg_dir = Path(output_dir) / f"{name}-mcp"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    errors = []

    try:
        _write_init(pkg_dir)
        _write_auth(pkg_dir, name, auth_type)
        _write_models(pkg_dir, endpoints)
        _write_server(pkg_dir, name, base_url, endpoints, auth_type)
        _write_pyproject(pkg_dir, name)
        _write_readme(pkg_dir, name, base_url, auth_type)
    except Exception as e:
        errors.append(str(e))
        return {"success": False, "path": str(pkg_dir), "config_snippet": {}, "errors": errors}

    config_snippet = _build_config(name, auth_type)
    return {
        "success": True,
        "path": str(pkg_dir),
        "config_snippet": config_snippet,
        "errors": errors
    }

def _write_init(pkg_dir: Path):
    (pkg_dir / "__init__.py").write_text('"""Auto-generated MCP server."""\n')

def _write_auth(pkg_dir: Path, name: str, auth_type: str):
    env_var = f"{name.upper().replace('-','_')}_API_KEY"

    if auth_type == "api_key":
        content = f'''"""Authentication helpers."""
import os

def get_headers() -> dict:
    key = os.environ.get("{env_var}", "")
    if not key:
        raise ValueError("Missing environment variable: {env_var}")
    return {{"Authorization": f"Bearer {{key}}", "Content-Type": "application/json"}}

def get_api_key() -> str:
    key = os.environ.get("{env_var}", "")
    if not key:
        raise ValueError("Missing environment variable: {env_var}")
    return key
'''
    elif auth_type == "bearer":
        content = f'''"""Authentication helpers."""
import os

def get_headers() -> dict:
    token = os.environ.get("{env_var}", "")
    if not token:
        raise ValueError("Missing environment variable: {env_var}")
    return {{"Authorization": f"Bearer {{token}}", "Content-Type": "application/json"}}
'''
    elif auth_type == "oauth2_client":
        client_id_var = f"{name.upper().replace('-','_')}_CLIENT_ID"
        secret_var = f"{name.upper().replace('-','_')}_CLIENT_SECRET"
        token_url_var = f"{name.upper().replace('-','_')}_TOKEN_URL"
        content = f'''"""OAuth2 client credentials authentication."""
import os
import httpx

_token_cache: dict = {{}}

def get_access_token() -> str:
    import time
    if _token_cache.get("expires_at", 0) > time.time() + 60:
        return _token_cache["access_token"]

    r = httpx.post(
        os.environ["{token_url_var}"],
        data={{
            "grant_type": "client_credentials",
            "client_id": os.environ["{client_id_var}"],
            "client_secret": os.environ["{secret_var}"],
        }}
    )
    r.raise_for_status()
    data = r.json()
    import time
    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600)
    return data["access_token"]

def get_headers() -> dict:
    return {{"Authorization": f"Bearer {{get_access_token()}}", "Content-Type": "application/json"}}
'''
    else:  # none
        content = '''"""No authentication required."""

def get_headers() -> dict:
    return {"Content-Type": "application/json"}
'''

    (pkg_dir / "auth.py").write_text(content)

def _write_models(pkg_dir: Path, endpoints: list[Endpoint]):
    lines = [
        '"""Pydantic models for request/response types."""',
        "from pydantic import BaseModel",
        "from typing import Optional, Any",
        ""
    ]

    seen_models = set()
    for ep in endpoints:
        body_params = [p for p in ep.params if p.location == "body" and p.type == "object"]
        if body_params:
            model_name = "".join(w.capitalize() for w in ep.operation_id.split("_")) + "Request"
            if model_name not in seen_models:
                seen_models.add(model_name)
                lines.append(f"\nclass {model_name}(BaseModel):")
                for p in body_params:
                    py_type = _py_type(p.type)
                    if not p.required:
                        py_type = f"Optional[{py_type}]"
                    lines.append(f"    {_to_python_name(p.name)}: {py_type} = None")

    if len(lines) <= 4:
        lines.append("\n# No complex request bodies detected — models will be added as needed.")

    (pkg_dir / "models.py").write_text("\n".join(lines) + "\n")

def _write_server(pkg_dir: Path, name: str, base_url: str, endpoints: list[Endpoint], auth_type: str):
    lines = [
        f'"""FastMCP server for {name}. Auto-generated by OpenClaw Forger."""',
        "import httpx",
        "from fastmcp import FastMCP",
        "from .auth import get_headers",
        "",
        f'mcp = FastMCP("{name}")',
        ""
    ]

    for ep in endpoints:
        fn_name = _to_python_name(ep.operation_id)

        # Build parameter list
        required_params = [p for p in ep.params if p.required]
        optional_params = [p for p in ep.params if not p.required]

        sig_parts = []
        for p in required_params:
            py_type = _py_type(p.type)
            sig_parts.append(f"{_to_python_name(p.name)}: {py_type}")
        for p in optional_params:
            py_type = _py_type(p.type)
            sig_parts.append(f"{_to_python_name(p.name)}: {py_type} = None")

        sig = ", ".join(sig_parts) if sig_parts else ""

        # Build docstring
        doc_lines = [f'    """{ep.summary or ep.operation_id}']
        if ep.params:
            doc_lines.append("")
            doc_lines.append("    Args:")
            for p in ep.params:
                req_str = " (required)" if p.required else " (optional)"
                doc_lines.append(f"        {_to_python_name(p.name)}: {p.description or p.type}{req_str}")
        doc_lines.append('    """')

        # Build URL with path params substituted
        path_params = {p.name for p in ep.params if p.location == "path"}
        url_expr = f'f"{base_url}{ep.path}"'
        for pp in path_params:
            url_expr = url_expr.replace(f"{{{pp}}}", f"{{{_to_python_name(pp)}}}")

        # Build request kwargs
        query_params = [p for p in ep.params if p.location == "query"]
        body_params = [p for p in ep.params if p.location == "body"]

        lines.append("")
        lines.append("@mcp.tool()")
        lines.append(f"async def {fn_name}({sig}) -> dict:")
        lines.extend(doc_lines)
        lines.append("    async with httpx.AsyncClient(timeout=30.0) as client:")

        if query_params:
            qp_dict = "{" + ", ".join(
                f'"{p.name}": {_to_python_name(p.name)}' for p in query_params
            ) + "}"
            lines.append(f"        params = {{k: v for k, v in {qp_dict}.items() if v is not None}}")
            params_arg = ", params=params"
        else:
            params_arg = ""

        if body_params:
            bp_dict = "{" + ", ".join(
                f'"{p.name}": {_to_python_name(p.name)}' for p in body_params
            ) + "}"
            lines.append(f"        body = {{k: v for k, v in {bp_dict}.items() if v is not None}}")
            json_arg = ", json=body"
        else:
            json_arg = ""

        method = ep.method.lower()
        lines.append(
            f"        r = await client.{method}({url_expr}, headers=get_headers(){params_arg}{json_arg})"
        )
        lines.append("        r.raise_for_status()")
        lines.append("        return r.json()")

    lines.append("")
    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append("    mcp.run()")
    lines.append("")

    (pkg_dir / "server.py").write_text("\n".join(lines))

def _write_pyproject(pkg_dir: Path, name: str):
    content = f'''[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{name}-mcp"
version = "0.1.0"
description = "Auto-generated MCP server for {name}"
requires-python = ">=3.11"
dependencies = [
    "fastmcp>=0.9.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
]

[project.scripts]
{name}-mcp = "{name.replace("-","_")}_mcp.server:mcp.run"
'''
    (pkg_dir / "pyproject.toml").write_text(content)

def _write_readme(pkg_dir: Path, name: str, base_url: str, auth_type: str):
    env_var = f"{name.upper().replace('-','_')}_API_KEY"
    content = f'''# {name}-mcp

Auto-generated MCP server for the {name} API.

## Setup

```bash
pip install -e .
export {env_var}=your_key_here
```

## Usage

Add to your `.mcp.json`:

```json
{{
  "mcpServers": {{
    "{name}": {{
      "command": "python",
      "args": ["-m", "{name.replace("-","_")}_mcp.server"]
    }}
  }}
}}
```

## Base URL

`{base_url}`

## Authentication

Auth type: `{auth_type}`

## Generated by

OpenClaw Forger Agent
'''
    (pkg_dir / "README.md").write_text(content)

def _build_config(name: str, auth_type: str) -> dict:
    env_var = f"{name.upper().replace('-','_')}_API_KEY"
    return {
        "mcpServers": {
            name: {
                "command": "python",
                "args": ["-m", f"{name.replace('-','_')}_mcp.server"],
                "env": {
                    env_var: ""
                }
            }
        }
    }
```

### Step 3: Create `forger_skill.md`

Full skill file content is in Section 5.

### Step 4: Modify `supervisor_config.json`

Add the forger gate and model route (see Section 8).

### Step 5: Modify `agent_profiles.json`

Add the forger profile (see Section 8).

### Step 6: Integration test

Run `/forge httpbin https://httpbin.org/spec.json` and verify:
- `mcp-servers/httpbin-mcp/` is created
- All files are syntactically valid Python
- `python -c "import mcp-servers.httpbin-mcp.server"` succeeds (after `sys.path` adjustment)
- `.openclaw/tasks/forge-httpbin-*.json` contains `"status": "complete"`

---

## 8. Configuration

### `forger_skill.md` (complete file)

```markdown
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
```

### `supervisor_config.json` additions

```json
{
  "intent_gates": {
    "ForgeIntent": {
      "trigger_patterns": [
        "/forge ",
        "generate mcp server",
        "create mcp tool",
        "build api wrapper"
      ],
      "dispatches_to": "forger_skill",
      "model": "claude-sonnet-4-5",
      "max_tokens": 8192
    }
  },
  "model_routing": {
    "forger": "claude-sonnet-4-5"
  }
}
```

### `agent_profiles.json` additions

```json
{
  "forger": {
    "description": "Autonomous MCP server generator from API docs",
    "model": "claude-sonnet-4-5",
    "allowed_tools": [
      "WebFetch",
      "WebSearch",
      "Read",
      "Write",
      "Edit",
      "Bash",
      "Glob",
      "Grep"
    ],
    "bash_allowlist": [
      "python",
      "pip",
      "cat",
      "ls",
      "mkdir"
    ],
    "bash_denylist": [
      "rm -rf",
      "git push",
      "curl.*-o",
      "wget"
    ],
    "workspace_isolation": "task_scoped",
    "max_iterations": 3,
    "task_file_pattern": ".openclaw/tasks/forge-*-*.json"
  }
}
```

---

## 9. Integration Points

### Orchestrator Prompt Addition

Add to `orchestrator_prompt.md` in the intent detection section:

```markdown
## ForgeIntent

When the user message matches `/forge <name> [url]` or expresses intent to
generate an MCP server tool:

1. Create a task file at `.openclaw/tasks/forge-{name}-{timestamp}.json` with:
   ```json
   {"task": "forge", "name": "<name>", "docs_url": "<url or null>", "output_dir": "mcp-servers/"}
   ```
2. Dispatch the `forger_skill` session with the `forger` agent profile.
3. Monitor `.openclaw/tasks/forge-{name}-{timestamp}.json` for status changes.
4. When status is `"complete"`, read the `config_snippet` and surface it to the user.
5. When status is `"failed"`, surface the errors and suggest providing the OpenAPI spec URL directly.
```

### Task System Integration

The forger uses the standard OpenClaw task JSON format:

```
.openclaw/tasks/forge-{name}-{timestamp}.json
```

Task lifecycle states: `"pending"` → `"running"` → `"validating"` → `"complete"` | `"failed"`

The orchestrator polls this file (or uses a file watcher) to detect completion and inject the config snippet into the main session context.

### Web Adapter Integration

The forger skill uses `WebFetch` and `WebSearch` from `web_adapter_skill.md`. Ensure the forger session includes `web_adapter_skill.md` in its context or that these tools are available globally in the OpenClaw tool registry.

---

## 10. Testing Plan

### Unit Tests

```python
# tests/test_doc_parser.py

import pytest
from openclaw.tools.doc_parser import parse_openapi, parse_graphql, parse_html_docs, detect_doc_type

STRIPE_OPENAPI_STUB = json.dumps({
    "openapi": "3.0.0",
    "info": {"title": "Stripe", "version": "2023-10-16"},
    "servers": [{"url": "https://api.stripe.com"}],
    "paths": {
        "/v1/charges": {
            "post": {
                "operationId": "CreateCharge",
                "summary": "Create a charge",
                "requestBody": {
                    "content": {
                        "application/x-www-form-urlencoded": {
                            "schema": {
                                "type": "object",
                                "required": ["amount", "currency"],
                                "properties": {
                                    "amount": {"type": "integer"},
                                    "currency": {"type": "string"},
                                    "source": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
})

def test_detect_openapi():
    assert detect_doc_type(STRIPE_OPENAPI_STUB, "https://...") == "openapi"

def test_parse_openapi_endpoint_count():
    eps = parse_openapi(STRIPE_OPENAPI_STUB)
    assert len(eps) == 1
    assert eps[0].method == "POST"
    assert eps[0].path == "/v1/charges"

def test_parse_openapi_params():
    eps = parse_openapi(STRIPE_OPENAPI_STUB)
    param_names = {p.name for p in eps[0].params}
    assert "amount" in param_names
    assert "currency" in param_names

def test_html_regex_extraction():
    html = """
    ## Create Charge
    POST /v1/charges
    Creates a new charge object.

    ## List Charges
    GET /v1/charges
    """
    eps = parse_html_docs(html)
    assert len(eps) == 2
    methods = {ep.method for ep in eps}
    assert "POST" in methods
    assert "GET" in methods
```

### Integration Tests

```bash
# Test full forge flow with httpbin (public, no auth required)
python -m openclaw.tools.forger_tool \
  --name httpbin \
  --base-url https://httpbin.org \
  --endpoints-file tests/fixtures/httpbin-endpoints.json \
  --auth-type none \
  --output-dir /tmp/test-forge/

# Verify output
ls /tmp/test-forge/httpbin-mcp/
# Expected: __init__.py  auth.py  models.py  server.py  pyproject.toml  README.md

# Validate the generated server
cd /tmp/test-forge/httpbin-mcp && python -c "import server; print('OK')"
```

### End-to-End Skill Test

```bash
# Simulate /forge invocation through orchestrator
echo '{"task": "forge", "name": "httpbin", "docs_url": "https://httpbin.org/spec.json", "output_dir": "mcp-servers/"}' \
  > .openclaw/tasks/forge-httpbin-test.json

# Run forger skill session
openclaw run --skill forger_skill --task forge-httpbin-test --profile forger

# Check result
cat .openclaw/tasks/forge-httpbin-test.json | python -m json.tool
# Expected: "status": "complete"
```

---

## 11. Example Usage

**User**: `/forge notion https://developers.notion.com/reference`

**Orchestrator** creates `.openclaw/tasks/forge-notion-1741824000.json` and dispatches forger session.

**Forger Phase 1**: Fetches `https://developers.notion.com/reference` with WebFetch. Detects HTML docs.

**Forger Phase 2**: Runs `doc_parser.py` on content. Regex extraction finds:
- `POST /v1/pages`
- `GET /v1/pages/{page_id}`
- `PATCH /v1/pages/{page_id}`
- `POST /v1/databases`
- `GET /v1/databases/{database_id}`
- `POST /v1/databases/{database_id}/query`
- ... (14 total endpoints)

**Forger Phase 3**: Scans docs for "Bearer token" → auth type `bearer`. Base URL from page: `https://api.notion.com`.

**Forger Phase 4**: Runs `forger_tool.py`. Generates `mcp-servers/notion-mcp/` with 14 tools.

**Forger Phase 5**: Validates. `python -c "import server; print('OK')"` → passes on first attempt.

**Forger Phase 6**: Writes task result. Prints:

```
Forger complete: notion-mcp
  Endpoints: 14
  Output: mcp-servers/notion-mcp/
  Auth: bearer (NOTION_API_KEY env var)

Add to .mcp.json:
{
  "mcpServers": {
    "notion": {
      "command": "python",
      "args": ["-m", "notion_mcp.server"],
      "env": { "NOTION_API_KEY": "" }
    }
  }
}
```

Total elapsed: ~45 seconds. Zero user interaction required after the initial `/forge` command.
