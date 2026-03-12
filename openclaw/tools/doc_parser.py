"""
Detect and parse API documentation into a normalized endpoint list.
Handles: OpenAPI 2.x, OpenAPI 3.x, GraphQL introspection, HTML/Markdown REST docs.
"""

import json
import re
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
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
    params: list = field(default_factory=list)
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


def parse_openapi(content: str) -> list:
    data = json.loads(content)
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


def parse_graphql(content: str) -> list:
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


def parse_html_docs(content: str, llm_extract_fn=None) -> list:
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

        # Try to find a surrounding heading (200 chars before match)
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


def parse_docs(content: str, url: str, llm_extract_fn=None) -> list:
    """Top-level parser -- auto-detects doc type and delegates."""
    doc_type = detect_doc_type(content, url)
    if doc_type == "openapi":
        return parse_openapi(content)
    elif doc_type == "graphql":
        return parse_graphql(content)
    else:
        return parse_html_docs(content, llm_extract_fn)


def _endpoint_to_dict(ep: Endpoint) -> dict:
    return {
        "method": ep.method,
        "path": ep.path,
        "operation_id": ep.operation_id,
        "summary": ep.summary,
        "auth_required": ep.auth_required,
        "params": [
            {
                "name": p.name,
                "location": p.location,
                "type": p.type,
                "required": p.required,
                "description": p.description
            }
            for p in ep.params
        ]
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse API documentation into endpoint list")
    parser.add_argument("--url", required=True, help="Documentation URL (used for type detection)")
    parser.add_argument("--content-file", help="File containing doc content (if not fetching live)")
    parser.add_argument("--output", default="/tmp/forge-endpoints.json", help="Output JSON file")
    args = parser.parse_args()

    if args.content_file and Path(args.content_file).exists():
        content = Path(args.content_file).read_text(encoding="utf-8", errors="replace")
    else:
        print(f"Content file not found: {args.content_file}", file=sys.stderr)
        sys.exit(1)

    endpoints = parse_docs(content, args.url)
    output_data = [_endpoint_to_dict(ep) for ep in endpoints]

    Path(args.output).write_text(json.dumps(output_data, indent=2))
    print(f"Parsed {len(endpoints)} endpoints -> {args.output}")
