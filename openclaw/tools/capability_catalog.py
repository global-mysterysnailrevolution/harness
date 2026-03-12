"""
Scans the OpenClaw workspace and builds a compact capability catalog.
Output written to .openclaw/catalog-{timestamp}.json.
"""

import json
import os
import re
import time
import argparse
from pathlib import Path
from typing import Optional


SKILL_HEADER_PATTERN = re.compile(
    r'<!--\s*SKILL:\s*(?P<name>\S+)\s*\|\s*TRIGGER:\s*(?P<trigger>[^|]+?)\s*\|\s*DESC:\s*(?P<desc>.+?)\s*-->'
)


def scan_skills(openclaw_dir: str) -> list:
    """Scan all .md files in the openclaw directory for skill definitions."""
    skills = []
    skills_path = Path(openclaw_dir)

    if not skills_path.exists():
        return skills

    for md_file in sorted(skills_path.glob("*.md")):
        if md_file.name.startswith("_"):
            continue

        try:
            first_lines = md_file.read_text(encoding="utf-8")[:500]
        except Exception:
            continue

        match = SKILL_HEADER_PATTERN.search(first_lines)
        if match:
            skills.append({
                "name": match.group("name"),
                "trigger": match.group("trigger").strip(),
                "description": match.group("desc").strip(),
                "file": str(md_file),
                "type": "skill"
            })
        else:
            # No header -- infer from filename
            name = md_file.stem.replace("_skill", "").replace("_", "-")
            skills.append({
                "name": name,
                "trigger": f"/{name}",
                "description": f"Skill: {md_file.stem}",
                "file": str(md_file),
                "type": "skill",
                "no_header": True
            })

    return skills


def scan_mcp_tools(project_root: str) -> list:
    """Scan .mcp.json for installed MCP servers and their tools."""
    mcp_file = Path(project_root) / ".mcp.json"
    if not mcp_file.exists():
        return []

    try:
        config = json.loads(mcp_file.read_text())
    except Exception:
        return []

    tools = []
    for server_name, server_config in config.get("mcpServers", {}).items():
        declared_tools = server_config.get("tools", [])
        if declared_tools:
            for tool in declared_tools:
                tools.append({
                    "name": f"{server_name}.{tool['name']}",
                    "server": server_name,
                    "description": tool.get("description", ""),
                    "type": "mcp_tool"
                })
        else:
            tools.append({
                "name": server_name,
                "server": server_name,
                "description": f"MCP server: {server_name} (tools unknown until runtime)",
                "type": "mcp_server"
            })

    return tools


def scan_agent_profiles(openclaw_dir: str) -> list:
    """Read agent_profiles.json to list available agent roles."""
    profiles_file = Path(openclaw_dir) / "agent_profiles.json"
    if not profiles_file.exists():
        return []

    try:
        profiles = json.loads(profiles_file.read_text())
    except Exception:
        return []

    return [
        {
            "name": name,
            "description": profile.get("description", ""),
            "model": profile.get("model", "unknown"),
            "type": "agent_profile"
        }
        for name, profile in profiles.items()
    ]


def scan_cron(openclaw_dir: str) -> list:
    """Read cron.json for scheduled tasks."""
    cron_file = Path(openclaw_dir) / "cron.json"
    if not cron_file.exists():
        return []

    try:
        cron = json.loads(cron_file.read_text())
    except Exception:
        return []

    return [
        {
            "name": entry.get("name", f"cron-{i}"),
            "schedule": entry.get("schedule", ""),
            "skill": entry.get("skill", ""),
            "type": "cron"
        }
        for i, entry in enumerate(cron.get("tasks", []))
    ]


BUILTIN_TOOLS = [
    {"name": "Read", "description": "Read file contents", "type": "builtin"},
    {"name": "Write", "description": "Write file contents", "type": "builtin"},
    {"name": "Edit", "description": "Edit file with exact string replacement", "type": "builtin"},
    {"name": "Bash", "description": "Run bash commands", "type": "builtin"},
    {"name": "Glob", "description": "Find files by pattern", "type": "builtin"},
    {"name": "Grep", "description": "Search file contents by regex", "type": "builtin"},
    {"name": "WebFetch", "description": "Fetch web page content as text", "type": "builtin"},
    {"name": "WebSearch", "description": "Search the web for information", "type": "builtin"},
]


def build_catalog(openclaw_dir: str, project_root: str) -> dict:
    """Build the full capability catalog."""
    catalog = {
        "generated_at": time.time(),
        "openclaw_dir": openclaw_dir,
        "project_root": project_root,
        "skills": scan_skills(openclaw_dir),
        "mcp_tools": scan_mcp_tools(project_root),
        "agent_profiles": scan_agent_profiles(openclaw_dir),
        "cron": scan_cron(openclaw_dir),
        "builtin_tools": BUILTIN_TOOLS
    }

    # Compact text representation for the router prompt
    catalog["compact_text"] = _render_compact(catalog)
    return catalog


def _render_compact(catalog: dict) -> str:
    lines = ["=== CAPABILITY CATALOG ===", ""]

    lines.append("SKILLS:")
    for s in catalog["skills"]:
        trigger = s.get("trigger", "N/A")
        lines.append(f"  {s['name']} | trigger: {trigger} | {s['description']}")

    lines.append("")
    lines.append("MCP TOOLS:")
    if catalog["mcp_tools"]:
        for t in catalog["mcp_tools"]:
            lines.append(f"  {t['name']} | {t['description']}")
    else:
        lines.append("  (none installed -- use /forge to generate MCP servers)")

    lines.append("")
    lines.append("BUILT-IN TOOLS:")
    for t in catalog["builtin_tools"]:
        lines.append(f"  {t['name']} | {t['description']}")

    lines.append("")
    lines.append("AGENT PROFILES:")
    for p in catalog["agent_profiles"]:
        lines.append(f"  {p['name']} (model: {p['model']}) | {p['description']}")

    if catalog["cron"]:
        lines.append("")
        lines.append("SCHEDULED TASKS:")
        for c in catalog["cron"]:
            lines.append(f"  {c['name']} | {c['schedule']} | skill: {c['skill']}")

    return "\n".join(lines)


def save_catalog(catalog: dict, output_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(catalog, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build OpenClaw capability catalog")
    parser.add_argument("--openclaw-dir", default="openclaw",
                        help="Path to openclaw skills directory")
    parser.add_argument("--project-root", default=".",
                        help="Project root (for .mcp.json scanning)")
    parser.add_argument("--output", required=True,
                        help="Output path for catalog JSON")
    args = parser.parse_args()

    catalog = build_catalog(args.openclaw_dir, args.project_root)
    save_catalog(catalog, args.output)
    print(f"Catalog written to {args.output}")
    print(f"  Skills: {len(catalog['skills'])}")
    print(f"  MCP tools: {len(catalog['mcp_tools'])}")
    print(f"  Built-in tools: {len(catalog['builtin_tools'])}")
