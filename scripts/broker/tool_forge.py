#!/usr/bin/env python3
"""
Tool Forge: OpenAPI -> MCP Server generation + vetting + approval pipeline.

Uses openapi-mcp-generator (npm) to generate MCP servers from OpenAPI specs,
then runs the vetting pipeline and proposes for approval.

Usage:
  python tool_forge.py --spec https://petstore3.swagger.io/api/v3/openapi.json --name petstore
  python tool_forge.py --spec ./my-api.yaml --name my-api --base-url https://api.example.com
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from forge_approval import ForgeApproval

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", Path.cwd()))
QUARANTINE_DIR = HARNESS_DIR / "ai" / "quarantine"


def _cmd_exists(name: str) -> bool:
    return shutil.which(name) is not None


def generate_mcp_server(
    spec_path: str,
    server_name: str,
    output_dir: Optional[Path] = None,
    base_url: Optional[str] = None,
    transport: str = "stdio",
) -> Path:
    """
    Generate an MCP server from an OpenAPI spec using openapi-mcp-generator.
    Returns path to the generated project directory.
    """
    if not _cmd_exists("openapi-mcp-generator") and not _cmd_exists("npx"):
        raise RuntimeError(
            "openapi-mcp-generator not found. Install with: npm install -g openapi-mcp-generator"
        )

    out = output_dir or QUARANTINE_DIR / server_name
    out.mkdir(parents=True, exist_ok=True)

    cmd = ["openapi-mcp-generator" if _cmd_exists("openapi-mcp-generator") else "npx"]
    if not _cmd_exists("openapi-mcp-generator"):
        cmd.extend(["-y", "openapi-mcp-generator"])
    cmd.extend(["--input", spec_path, "--output", str(out), "--server-name", server_name])
    if base_url:
        cmd.extend(["--base-url", base_url])
    if transport:
        cmd.extend(["--transport", transport])
    cmd.append("--force")  # overwrite if exists

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"openapi-mcp-generator failed:\n{result.stderr}\n{result.stdout}")

    return out


def forge_from_openapi(
    spec_path: str,
    server_name: str,
    base_url: Optional[str] = None,
    transport: str = "stdio",
    proposed_by: str = "tool_forge",
) -> dict:
    """
    Full pipeline: generate MCP server -> vet -> propose for approval.
    Returns the proposal dict (with vetting results attached).
    """
    print(f"[forge] Generating MCP server '{server_name}' from {spec_path}...")
    output_dir = generate_mcp_server(
        spec_path=spec_path,
        server_name=server_name,
        base_url=base_url,
        transport=transport,
    )
    print(f"[forge] Generated at {output_dir}")

    # Install dependencies in quarantine (needed for npm audit)
    pkg_json = output_dir / "package.json"
    if pkg_json.exists() and _cmd_exists("npm"):
        print("[forge] Installing dependencies in quarantine...")
        subprocess.run(
            ["npm", "install", "--ignore-scripts"],  # --ignore-scripts for safety
            cwd=str(output_dir),
            capture_output=True,
            timeout=120,
        )

    # Propose (triggers vetting automatically via source_path)
    forge = ForgeApproval()
    proposal = forge.propose_server(
        server_name=server_name,
        source="openapi",
        source_id=spec_path,
        proposed_by=proposed_by,
        source_path=str(output_dir),
    )

    print(f"[forge] Proposal: {proposal['id']}")
    vetting = proposal.get("vetting_status")
    print(f"[forge] Vetting verdict: {vetting or 'not run'}")

    if vetting == "fail":
        print(f"[forge] AUTO-REJECTED: {proposal.get('rejection_reason', '')}")
        print(f"[forge] Review report: ai/supervisor/forge_approvals/{proposal['id']}_VETTING.md")
    elif vetting == "warn":
        print(f"[forge] WARNINGS found. Review before approving:")
        print(f"  python scripts/broker/tool_broker.py approve --tool-id {proposal['id']} --agent-id admin")
    elif vetting == "pass":
        print(f"[forge] Vetting PASSED. Approve with:")
        print(f"  python scripts/broker/tool_broker.py approve --tool-id {proposal['id']} --agent-id admin")
    else:
        print(f"[forge] Vetting not available. Review manually, then approve:")
        print(f"  python scripts/broker/tool_broker.py approve --tool-id {proposal['id']} --agent-id admin --override-vetting")

    return proposal


def main():
    parser = argparse.ArgumentParser(description="Tool Forge: OpenAPI -> MCP Server + Vetting")
    parser.add_argument("--spec", "-i", required=True, help="Path or URL to OpenAPI spec")
    parser.add_argument("--name", "-n", required=True, help="Server name")
    parser.add_argument("--base-url", "-b", help="Base URL for API requests")
    parser.add_argument("--transport", "-t", default="stdio", choices=["stdio", "web", "streamable-http"],
                        help="MCP transport mode (default: stdio)")
    parser.add_argument("--proposed-by", default="cli", help="Who proposed this")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()

    try:
        proposal = forge_from_openapi(
            spec_path=args.spec,
            server_name=args.name,
            base_url=args.base_url,
            transport=args.transport,
            proposed_by=args.proposed_by,
        )
        if args.json:
            print(json.dumps(proposal, indent=2))
    except RuntimeError as e:
        print(f"[forge] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
