"""
Reads skill router output and loads only the selected skills.
Returns a context-optimized skill bundle for the current session.
"""

import json
import argparse
from pathlib import Path


def load_selected_skills(
    routing_file: str,
    openclaw_dir: str
) -> dict:
    """
    Reads the routing JSON and loads only the skill files that were selected.
    Returns:
      {
        "skill_contexts": {"skill_name": "full skill content"},
        "active_tools": ["Read", "Write", ...],
        "active_mcp_tools": ["stripe.createCharge", ...],
        "missing_capabilities": ["salesforce_mcp"]
      }
    """
    routing = json.loads(Path(routing_file).read_text())

    skill_contexts = {}
    missing = list(routing.get("MISSING", []))

    for skill_name in routing.get("SKILLS", []):
        # Find the skill file
        skill_file = Path(openclaw_dir) / f"{skill_name}.md"
        if not skill_file.exists():
            # Try with _skill suffix
            skill_file = Path(openclaw_dir) / f"{skill_name}_skill.md"

        if skill_file.exists():
            skill_contexts[skill_name] = skill_file.read_text()
        else:
            missing.append(skill_name)

    return {
        "skill_contexts": skill_contexts,
        "active_tools": routing.get("TOOLS", []),
        "active_mcp_tools": routing.get("MCP_TOOLS", []),
        "missing_capabilities": missing,
        "per_task_routing": routing.get("per_task", {}),
        "invoke_via": routing.get("INVOKE_VIA", ""),
        "reason": routing.get("REASON", "")
    }


def render_skill_bundle(bundle: dict) -> str:
    """
    Render the selected skills as a single context string
    for injection into the orchestrator session.
    """
    parts = []

    if bundle["missing_capabilities"]:
        parts.append("## MISSING CAPABILITIES")
        parts.append("The following required capabilities are not installed:")
        for missing in bundle["missing_capabilities"]:
            parts.append(f"  - {missing}")
        parts.append("Use /forge to generate missing MCP servers.")
        parts.append("")

    for skill_name, content in bundle["skill_contexts"].items():
        parts.append(f"## Loaded Skill: {skill_name}")
        parts.append(content)
        parts.append("")

    return "\n".join(parts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load selected skills from router output")
    parser.add_argument("--routing", required=True,
                        help="Path to routing JSON from skill_router")
    parser.add_argument("--openclaw-dir", default="openclaw",
                        help="Path to openclaw skills directory")
    parser.add_argument("--output",
                        help="Write bundle to file instead of stdout")
    args = parser.parse_args()

    bundle = load_selected_skills(args.routing, args.openclaw_dir)

    if bundle["missing_capabilities"]:
        print(f"WARNING: Missing capabilities: {bundle['missing_capabilities']}")

    rendered = render_skill_bundle(bundle)

    if args.output:
        Path(args.output).write_text(rendered)
        print(f"Skill bundle written to {args.output}")
        print(f"  Loaded skills: {list(bundle['skill_contexts'].keys())}")
        print(f"  Active tools: {bundle['active_tools']}")
        token_estimate = len(rendered) // 4  # rough estimate
        print(f"  Estimated tokens: ~{token_estimate:,}")
    else:
        print(rendered)
