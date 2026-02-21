#!/usr/bin/env python3
"""
MCP server exposing harness execute requests to Cursor.

Tools:
  - list_execute_requests: List pending and recent execute requests (from WhatsApp/portal)
  - get_execute_request: Get details of a specific request by ID

Use when running on VPS: set WHATSAPP_TRANSCRIPTS_DIR and HOOK_OUTPUT_DIR.
Use when running locally: point those env vars at a synced folder.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import click
import mcp.types as types
from mcp.server import Server

TRANSCRIPTS_DIR = Path(os.environ.get("WHATSAPP_TRANSCRIPTS_DIR", "/opt/harness/whatsapp-transcripts"))
EXECUTE_QUEUE_FILE = TRANSCRIPTS_DIR / "execute_queue.json"
PROCESSED_DIR = TRANSCRIPTS_DIR / "processed"
HOOK_OUTPUT_DIR = Path(os.environ.get("HOOK_OUTPUT_DIR", "/opt/harness/ai/execute_requests"))


def _load_queue() -> dict:
    if EXECUTE_QUEUE_FILE.exists():
        try:
            with open(EXECUTE_QUEUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"pending": []}


def _load_hook_outputs(limit: int = 20) -> list[dict]:
    """Load recent execute requests from HOOK_OUTPUT_DIR."""
    if not HOOK_OUTPUT_DIR.exists():
        return []
    files = sorted(HOOK_OUTPUT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    results = []
    for p in files[:limit]:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["_id"] = p.stem
                results.append(data)
        except (json.JSONDecodeError, OSError):
            pass
    return results


def _get_single_request(req_id: str) -> dict | None:
    """Get one request by ID from hook output or processed."""
    for base in (HOOK_OUTPUT_DIR, PROCESSED_DIR):
        p = base / f"{req_id}.json"
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
    return None


def create_server() -> Server:
    app = Server("harness-execute-requests")

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="list_execute_requests",
                title="List Execute Requests",
                description="List pending and recent execute requests from the harness (WhatsApp/portal commands queued for Cursor or broker).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Max recent completed requests to include (default 10)",
                        },
                    },
                },
            ),
            types.Tool(
                name="get_execute_request",
                title="Get Execute Request",
                description="Get details of a specific execute request by ID.",
                inputSchema={
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Request ID (e.g. from list_execute_requests)",
                        },
                    },
                },
            ),
        ]

    @app.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any]
    ) -> list[types.TextContent]:
        if name == "list_execute_requests":
            queue = _load_queue()
            pending = queue.get("pending", [])
            limit = arguments.get("limit", 10)
            recent = _load_hook_outputs(limit=int(limit))
            payload = {
                "pending": [{"id": e.get("id"), "command": e.get("command"), "source": e.get("source")} for e in pending],
                "pending_count": len(pending),
                "recent_completed": recent,
            }
            text = json.dumps(payload, indent=2, ensure_ascii=False)
            return [types.TextContent(type="text", text=text)]

        if name == "get_execute_request":
            req_id = arguments.get("id")
            if not req_id:
                return [types.TextContent(type="text", text='{"error": "Missing required argument: id"}')]
            data = _get_single_request(req_id)
            if data is None:
                return [types.TextContent(type="text", text=f'{{"error": "Request not found: {req_id}"}}')]
            text = json.dumps(data, indent=2, ensure_ascii=False)
            return [types.TextContent(type="text", text=text)]

        return [types.TextContent(type="text", text=f'{{"error": "Unknown tool: {name}"}}')]

    return app


@click.command()
@click.option("--port", default=8002, help="Port for SSE server")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="stdio for local Cursor, sse for remote (VPS)",
)
def main(port: int, transport: str) -> None:
    app = create_server()

    if transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import Response
        from starlette.routing import Mount, Route

        import uvicorn

        sse = SseServerTransport("/messages/")

        async def handle_sse(request: Request):
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await app.run(streams[0], streams[1], app.create_initialization_options())
            return Response()

        starlette_app = Starlette(
            debug=False,
            routes=[
                Route("/sse", endpoint=handle_sse, methods=["GET"]),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )

        host = os.getenv("MCP_LISTEN_HOST", "0.0.0.0")
        print(f"[MCP] Harness execute requests server on http://{host}:{port}/sse", flush=True)
        uvicorn.run(starlette_app, host=host, port=port)
    else:
        import anyio
        from mcp.server.stdio import stdio_server

        async def arun():
            async with stdio_server() as (read_stream, write_stream):
                await app.run(
                    read_stream,
                    write_stream,
                    app.create_initialization_options(),
                )

        anyio.run(arun)


if __name__ == "__main__":
    main()
