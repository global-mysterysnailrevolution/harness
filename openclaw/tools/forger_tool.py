"""
Generates a complete FastMCP server package from a parsed endpoint list.
Called by forger_skill.md after doc parsing is complete.
"""

import os
import json
import re
import argparse
from pathlib import Path
from typing import Optional


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
    endpoints: list,
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


def _write_models(pkg_dir: Path, endpoints: list):
    lines = [
        '"""Pydantic models for request/response types."""',
        "from pydantic import BaseModel",
        "from typing import Optional, Any",
        ""
    ]

    seen_models = set()
    for ep in endpoints:
        body_params = [p for p in ep.get("params", []) if p.get("location") == "body" and p.get("type") == "object"]
        if body_params:
            model_name = "".join(w.capitalize() for w in ep["operation_id"].split("_")) + "Request"
            if model_name not in seen_models:
                seen_models.add(model_name)
                lines.append(f"\nclass {model_name}(BaseModel):")
                for p in body_params:
                    py_type = _py_type(p.get("type", "string"))
                    if not p.get("required", False):
                        py_type = f"Optional[{py_type}]"
                    lines.append(f"    {_to_python_name(p['name'])}: {py_type} = None")

    if len(lines) <= 4:
        lines.append("\n# No complex request bodies detected -- models will be added as needed.")

    (pkg_dir / "models.py").write_text("\n".join(lines) + "\n")


def _write_server(pkg_dir: Path, name: str, base_url: str, endpoints: list, auth_type: str):
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
        fn_name = _to_python_name(ep["operation_id"])
        params = ep.get("params", [])

        # Build parameter list
        required_params = [p for p in params if p.get("required", False)]
        optional_params = [p for p in params if not p.get("required", False)]

        sig_parts = []
        for p in required_params:
            py_type = _py_type(p.get("type", "string"))
            sig_parts.append(f"{_to_python_name(p['name'])}: {py_type}")
        for p in optional_params:
            py_type = _py_type(p.get("type", "string"))
            sig_parts.append(f"{_to_python_name(p['name'])}: {py_type} = None")

        sig = ", ".join(sig_parts) if sig_parts else ""

        # Build docstring
        summary = ep.get("summary", ep["operation_id"])
        doc_lines = [f'    """{summary}']
        if params:
            doc_lines.append("")
            doc_lines.append("    Args:")
            for p in params:
                req_str = " (required)" if p.get("required") else " (optional)"
                doc_lines.append(f"        {_to_python_name(p['name'])}: {p.get('description', p.get('type', 'str'))}{req_str}")
        doc_lines.append('    """')

        # Build URL with path params substituted
        path_params = {p["name"] for p in params if p.get("location") == "path"}
        url_expr = f'f"{base_url}{ep["path"]}"'
        for pp in path_params:
            url_expr = url_expr.replace(f"{{{pp}}}", f"{{{_to_python_name(pp)}}}")

        # Build request kwargs
        query_params = [p for p in params if p.get("location") == "query"]
        body_params = [p for p in params if p.get("location") == "body"]

        lines.append("")
        lines.append("@mcp.tool()")
        lines.append(f"async def {fn_name}({sig}) -> dict:")
        lines.extend(doc_lines)
        lines.append("    async with httpx.AsyncClient(timeout=30.0) as client:")

        if query_params:
            qp_dict = "{" + ", ".join(
                f'"{p["name"]}": {_to_python_name(p["name"])}' for p in query_params
            ) + "}"
            lines.append(f"        params = {{k: v for k, v in {qp_dict}.items() if v is not None}}")
            params_arg = ", params=params"
        else:
            params_arg = ""

        if body_params:
            bp_dict = "{" + ", ".join(
                f'"{p["name"]}": {_to_python_name(p["name"])}' for p in body_params
            ) + "}"
            lines.append(f"        body = {{k: v for k, v in {bp_dict}.items() if v is not None}}")
            json_arg = ", json=body"
        else:
            json_arg = ""

        method = ep["method"].lower()
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate FastMCP server from endpoint list")
    parser.add_argument("--name", required=True, help="API/tool name (e.g. 'stripe')")
    parser.add_argument("--base-url", required=True, help="API base URL (e.g. 'https://api.stripe.com')")
    parser.add_argument("--endpoints-file", required=True, help="JSON file with parsed endpoints")
    parser.add_argument("--auth-type", default="api_key",
                        choices=["api_key", "bearer", "oauth2_client", "none"],
                        help="Authentication type")
    parser.add_argument("--output-dir", default="mcp-servers/", help="Output directory")
    args = parser.parse_args()

    with open(args.endpoints_file) as f:
        endpoints = json.load(f)

    result = generate_server(
        name=args.name,
        base_url=args.base_url,
        endpoints=endpoints,
        auth_type=args.auth_type,
        output_dir=args.output_dir
    )

    print(json.dumps(result, indent=2))

    if not result["success"]:
        import sys
        sys.exit(1)
