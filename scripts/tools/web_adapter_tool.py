#!/usr/bin/env python3
"""
Web Adapter Tool
Loads and executes site adapter definitions from harness/adapters/.

Adapters capture API request patterns so the agent can replay multi-step
web workflows via HTTP instead of driving a browser.

Usage:
    python3 web_adapter_tool.py <operation> [--args '<json>']

Operations:
    list_adapters      List all adapter files
    execute_adapter    Execute an adapter with provided variables
    validate_adapter   Dry-run schema check on an adapter file
"""

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


HARNESS_ROOT = Path(os.environ.get("HARNESS_ROOT", Path(__file__).resolve().parent.parent.parent))
ADAPTERS_DIR = HARNESS_ROOT / "adapters"

# Max response body to capture per step (prevent runaway memory)
MAX_RESPONSE_BYTES = 512_000  # 500KB


# ===================================================================
# Adapter schema
# ===================================================================

ADAPTER_SCHEMA = {
    "required_fields": ["site", "description", "steps"],
    "step_required": ["method", "url"],
    "allowed_methods": {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"},
    "auth_types": {"none", "bearer_token", "session_cookie", "api_key", "basic"},
}


def _validate_adapter(adapter: Dict) -> List[str]:
    """Return list of validation errors (empty = valid)."""
    errors = []

    for field in ADAPTER_SCHEMA["required_fields"]:
        if field not in adapter:
            errors.append(f"Missing required field: {field}")

    steps = adapter.get("steps", [])
    if not isinstance(steps, list) or len(steps) == 0:
        errors.append("'steps' must be a non-empty list")
        return errors

    for i, step in enumerate(steps):
        for field in ADAPTER_SCHEMA["step_required"]:
            if field not in step:
                errors.append(f"Step {i}: missing '{field}'")
        method = step.get("method", "").upper()
        if method and method not in ADAPTER_SCHEMA["allowed_methods"]:
            errors.append(f"Step {i}: invalid method '{method}'")

    auth = adapter.get("auth", {})
    auth_type = auth.get("type", "none")
    if auth_type not in ADAPTER_SCHEMA["auth_types"]:
        errors.append(f"Unknown auth type: '{auth_type}'")

    return errors


# ===================================================================
# Template variable interpolation
# ===================================================================

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _interpolate(value: Any, context: Dict[str, str]) -> Any:
    """Recursively replace {{var}} placeholders in strings/dicts/lists."""
    if isinstance(value, str):
        def _replace(m):
            key = m.group(1)
            if key not in context:
                raise ValueError(f"Unresolved variable: {{{{{key}}}}}")
            return context[key]
        return _VAR_PATTERN.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: _interpolate(v, context) for k, v in value.items()}
    elif isinstance(value, list):
        return [_interpolate(item, context) for item in value]
    return value


# ===================================================================
# HTTP execution engine
# ===================================================================

def _resolve_auth(auth: Dict, context: Dict[str, str]) -> Dict[str, str]:
    """Resolve auth config into HTTP headers."""
    auth_type = auth.get("type", "none")
    headers: Dict[str, str] = {}

    if auth_type == "none":
        pass
    elif auth_type == "bearer_token":
        env_var = auth.get("source_env", "")
        token = os.environ.get(env_var, context.get(env_var, ""))
        if not token:
            raise ValueError(f"Auth: env var '{env_var}' is empty. Set it before running.")
        headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "api_key":
        env_var = auth.get("source_env", "")
        header_name = auth.get("header", "X-API-Key")
        token = os.environ.get(env_var, context.get(env_var, ""))
        if not token:
            raise ValueError(f"Auth: env var '{env_var}' is empty.")
        headers[header_name] = token
    elif auth_type == "session_cookie":
        env_var = auth.get("source_env", "")
        cookie = os.environ.get(env_var, context.get(env_var, ""))
        if not cookie:
            raise ValueError(f"Auth: env var '{env_var}' is empty.")
        headers["Cookie"] = cookie
    elif auth_type == "basic":
        import base64
        user_env = auth.get("user_env", "")
        pass_env = auth.get("pass_env", "")
        user = os.environ.get(user_env, "")
        pw = os.environ.get(pass_env, "")
        cred = base64.b64encode(f"{user}:{pw}".encode()).decode()
        headers["Authorization"] = f"Basic {cred}"

    return headers


def _extract_values(body: Any, extract_map: Dict[str, str]) -> Dict[str, str]:
    """
    Extract values from a JSON response using simple dot/bracket notation.
    Supports: $.key, $.key.subkey, $.arr[0].field
    """
    extracted = {}
    if not isinstance(body, (dict, list)):
        return extracted

    for var_name, path in extract_map.items():
        path = path.lstrip("$").lstrip(".")
        current: Any = body
        try:
            for part in _split_path(path):
                if isinstance(part, int):
                    current = current[part]
                else:
                    current = current[part]
            extracted[var_name] = str(current)
        except (KeyError, IndexError, TypeError):
            extracted[var_name] = ""

    return extracted


def _split_path(path: str) -> List:
    """Split 'key.subkey[0].field' into ['key', 'subkey', 0, 'field']."""
    parts = []
    for segment in path.replace("]", "").split("."):
        if "[" in segment:
            key, idx = segment.split("[", 1)
            if key:
                parts.append(key)
            parts.append(int(idx))
        else:
            parts.append(segment)
    return parts


def _execute_step(step: Dict, context: Dict[str, str], auth_headers: Dict[str, str]) -> Dict:
    """Execute a single HTTP step. Returns response info + extracted values."""
    method = step["method"].upper()
    url = _interpolate(step["url"], context)

    headers = dict(auth_headers)
    if step.get("headers"):
        headers.update(_interpolate(step["headers"], context))

    body_data = None
    if step.get("body"):
        resolved_body = _interpolate(step["body"], context)
        if isinstance(resolved_body, dict):
            body_data = json.dumps(resolved_body).encode()
            headers.setdefault("Content-Type", "application/json")
        else:
            body_data = str(resolved_body).encode()

    # Build request
    req = urllib.request.Request(url, data=body_data, headers=headers, method=method)

    ctx = ssl.create_default_context()
    verify = os.environ.get("ADAPTER_VERIFY_SSL", "true").lower() == "true"
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES)
            status = resp.status
            resp_headers = dict(resp.getheaders())
    except urllib.error.HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES) if exc.fp else b""
        status = exc.code
        resp_headers = dict(exc.headers) if exc.headers else {}

    # Parse response
    try:
        resp_body = json.loads(raw.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        resp_body = raw.decode("utf-8", errors="replace")

    # Extract values for subsequent steps
    extracted = {}
    if step.get("extract") and isinstance(resp_body, (dict, list)):
        extracted = _extract_values(resp_body, step["extract"])
        context.update(extracted)

    return {
        "status": status,
        "extracted": extracted,
        "body_preview": str(resp_body)[:500] if resp_body else "",
    }


# ===================================================================
# Operations
# ===================================================================

def list_adapters(params: Dict) -> Dict:
    """List all adapter JSON files."""
    if not ADAPTERS_DIR.exists():
        return {"adapters": [], "directory": str(ADAPTERS_DIR)}

    adapters = []
    for f in sorted(ADAPTERS_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            adapters.append({
                "file": f.name,
                "site": data.get("site", ""),
                "description": data.get("description", ""),
                "steps": len(data.get("steps", [])),
                "auth_type": data.get("auth", {}).get("type", "none"),
            })
        except (json.JSONDecodeError, OSError):
            adapters.append({"file": f.name, "error": "invalid JSON"})

    return {"adapters": adapters, "directory": str(ADAPTERS_DIR)}


def execute_adapter(params: Dict) -> Dict:
    """Execute an adapter by name with provided variables."""
    adapter_name = params.get("adapter", "")
    if not adapter_name:
        return {"error": "Required: 'adapter' (filename without .json, or full filename)"}

    # Find adapter file
    if not adapter_name.endswith(".json"):
        adapter_name += ".json"
    adapter_path = ADAPTERS_DIR / adapter_name

    if not adapter_path.exists():
        available = [f.stem for f in ADAPTERS_DIR.glob("*.json")]
        return {"error": f"Adapter '{adapter_name}' not found. Available: {available}"}

    with open(adapter_path, "r", encoding="utf-8") as f:
        adapter = json.load(f)

    # Validate
    errors = _validate_adapter(adapter)
    if errors:
        return {"error": "Adapter validation failed", "details": errors}

    # Build execution context from provided vars
    context: Dict[str, str] = {}
    context.update(params.get("vars", {}))

    # Resolve auth
    auth = adapter.get("auth", {"type": "none"})
    try:
        auth_headers = _resolve_auth(auth, context)
    except ValueError as exc:
        return {"error": str(exc)}

    # Execute steps in order
    results = []
    for i, step in enumerate(adapter["steps"]):
        try:
            step_result = _execute_step(step, context, auth_headers)
            results.append({"step": i, "method": step["method"], "url": step["url"], **step_result})
            if step_result["status"] >= 400:
                return {
                    "error": f"Step {i} failed with HTTP {step_result['status']}",
                    "steps_completed": results,
                    "context": context,
                }
        except Exception as exc:
            return {
                "error": f"Step {i} error: {exc}",
                "steps_completed": results,
                "context": context,
            }

    return {
        "success": True,
        "adapter": adapter.get("site", adapter_name),
        "steps_completed": results,
        "final_context": context,
    }


def validate_adapter(params: Dict) -> Dict:
    """Validate an adapter file without executing it."""
    adapter_name = params.get("adapter", "")
    if not adapter_name:
        # Validate inline JSON
        adapter_data = params.get("adapter_json")
        if not adapter_data:
            return {"error": "Provide 'adapter' (filename) or 'adapter_json' (inline dict)"}
        errors = _validate_adapter(adapter_data)
        return {"valid": len(errors) == 0, "errors": errors}

    if not adapter_name.endswith(".json"):
        adapter_name += ".json"
    adapter_path = ADAPTERS_DIR / adapter_name

    if not adapter_path.exists():
        return {"error": f"Adapter file not found: {adapter_path}"}

    with open(adapter_path, "r", encoding="utf-8") as f:
        adapter = json.load(f)

    errors = _validate_adapter(adapter)

    # Also check that template vars are consistent
    all_vars = set()
    for step in adapter.get("steps", []):
        for val in _find_vars(step):
            all_vars.add(val)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "required_vars": sorted(all_vars),
        "steps": len(adapter.get("steps", [])),
        "auth_type": adapter.get("auth", {}).get("type", "none"),
    }


def _find_vars(obj: Any) -> List[str]:
    """Find all {{var}} references in a nested structure."""
    found = []
    if isinstance(obj, str):
        found.extend(_VAR_PATTERN.findall(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            found.extend(_find_vars(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_vars(item))
    return found


# ===================================================================
# Dispatcher + CLI
# ===================================================================

OPERATIONS = {
    "list_adapters": list_adapters,
    "execute_adapter": execute_adapter,
    "validate_adapter": validate_adapter,
}


def run(operation: str, params: Dict) -> Dict:
    if operation not in OPERATIONS:
        return {"error": f"Unknown operation: {operation}. Valid: {sorted(OPERATIONS.keys())}"}
    try:
        return OPERATIONS[operation](params)
    except Exception as exc:
        return {"error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description="Web Adapter Tool")
    parser.add_argument("operation", choices=sorted(OPERATIONS.keys()),
                        help="Operation to perform")
    parser.add_argument("--args", default="{}", help="JSON parameters")
    args = parser.parse_args()

    try:
        params = json.loads(args.args)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid JSON: {exc}"}))
        sys.exit(1)

    result = run(args.operation, params)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
