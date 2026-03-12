# Skill Router — OpenClaw Port

## 1. Overview

The Skill Router is Claude Code's fast capability-matching agent. It runs during
the parallel bootstrap phase of every `/go` invocation (Phase 3), scanning all
available capabilities and returning a structured routing decision before any work
begins.

The router serves three purposes:

1. **Prevent unnecessary skill loading** — loading a skill's full prompt into
   context costs tokens. The router's job is to identify which skills are actually
   needed so only those are loaded.

2. **Map tasks to capabilities** — the router knows the full catalog of installed
   plugins, global commands, built-in skills, MCP tools, and cron schedules. It
   maps each sub-task to the specific capability that should handle it.

3. **Flag missing capabilities** — if a task requires a tool that is not installed
   (e.g., the user asks to query Salesforce but no Salesforce MCP server is
   configured), the router flags this early so the supervisor can either install
   the tool (via the forger) or inform the user before wasting time.

The router runs on **haiku** (cheapest model) because it is purely a lookup/matching
task — no generation required, just classification against a known catalog.

**Output format**:
```json
{
  "SKILLS": ["forger_skill", "browser_skill"],
  "TOOLS": ["WebFetch", "Bash"],
  "COMMANDS": ["/forge", "/browse"],
  "INVOKE_VIA": "forger_skill for task-1; browser_skill for task-2",
  "MISSING": [],
  "REASON": "Task 1 requires MCP server generation. Task 2 requires web scraping."
}
```

---

## 2. Problem Statement

OpenClaw has no equivalent to the Skill Router. Currently:

- Every orchestrator session loads all available skill context (expensive)
- There is no mechanism to check whether required tools are installed before
  starting a task
- Missing capabilities are discovered mid-task when an agent tries to invoke a
  tool that does not exist
- There is no catalog of what capabilities exist — each agent must probe the
  filesystem manually
- Manual routing means the orchestrator must know about every available skill,
  creating a maintenance burden as the skill library grows

| Characteristic | Claude Code Skill Router | OpenClaw current |
|---|---|---|
| Skill loading | Lazy — load only what's needed | Eager — load everything |
| Capability catalog | Maintained by router | None |
| Missing tool detection | Phase 3 (before work starts) | Mid-task (expensive) |
| Model | Haiku (cheap, fast) | N/A |
| MCP tool awareness | Yes | No |
| Cron/scheduling awareness | Yes | No |
| Output format | Structured JSON | N/A |

The cost of loading 10 unnecessary skill files at ~2,000 tokens each is 20,000
tokens per invocation. On a project with 20 skills, every `/go` call loads ~40,000
tokens of skill context that will never be used. The Skill Router eliminates this
waste.

---

## 3. Source Analysis

### 3.1 The Skill Router Agent

In Claude Code, `skill-router.md` is a dedicated agent definition that runs on
haiku. Its context includes:

1. The task decomposition (from Phase 2)
2. A **capability catalog** — a compact list of all available skills, commands,
   tools, and MCP servers (generated fresh each run by scanning the filesystem)
3. Instructions to match tasks to capabilities and return structured JSON

The capability catalog is compiled by `context-hydrator` (haiku) before the
router runs. It scans:
- `~/.claude/skills/` — globally installed skills
- `.claude/skills/` — project-level skills
- The installed MCP server list (from `.mcp.json`)
- The built-in tool list (fixed: Read, Write, Edit, Bash, Glob, Grep, WebFetch, WebSearch, Agent)
- The cron configuration (if present)

The compiled catalog looks like:
```
INSTALLED SKILLS:
  forger — /forge <name> [url] — generates MCP server from API docs
  browser — /browse <task> — multi-step web interaction
  researcher — /research <topic> — deep research with deliberation
  checkpoint — /checkpoint — save session state

INSTALLED MCP TOOLS:
  stripe.createCharge(amount, currency, source)
  stripe.listCharges(limit, starting_after)
  github.createIssue(owner, repo, title, body)
  github.listPullRequests(owner, repo, state)

BUILT-IN TOOLS:
  Read, Write, Edit, Bash, Glob, Grep, WebFetch, WebSearch, Agent
```

### 3.2 Router Decision Logic

The router is a classifier, not a generator. It looks at each task in the
decomposition and asks:

1. Is there an installed skill that handles this exact task pattern?
   → Use that skill
2. Is there an MCP tool that directly provides this capability?
   → Use that MCP tool
3. Is there a built-in tool sufficient for this?
   → Use the built-in tool
4. Does the task require multiple capabilities?
   → List all required; let the assigned agent load what it needs
5. Is a required capability not installed?
   → Flag as MISSING; let the supervisor decide whether to install it or inform user

### 3.3 Speed Requirement

The router runs in parallel with other Phase 3 bootstrap tasks (context hydration,
wheel-scout gate check). It must complete in under 5 seconds — this is why haiku
is used, not sonnet. The catalog is pre-compiled (not generated inline), so the
router only needs to do classification against a static list.

---

## 4. Target Architecture

OpenClaw's Skill Router port consists of:

1. **`skill_router_skill.md`** — the router prompt (runs on haiku)
2. **`tools/capability_catalog.py`** — scans the filesystem and builds the
   capability catalog that the router uses
3. **`tools/router_dispatcher.py`** — reads router output and sets up the
   session context (loads only the needed skills)
4. **Config additions** — catalog scan paths, router model setting

### 4.1 Architecture Diagram

```
/go "build a stripe checkout flow and write tests"
         │
         ▼
Phase 3 (parallel bootstrap):
  ┌─────────────────────────────────────────────────────┐
  │ capability_catalog.py scans:                        │
  │   openclaw/skills/*.md → skill list                 │
  │   .mcp.json → MCP tool list                         │
  │   openclaw/cron.json → scheduled tasks              │
  │   agent_profiles.json → agent roles                 │
  │                                                     │
  │   → writes .openclaw/catalog-{ts}.json              │
  └─────────────────────────────────────────────────────┘
         │
         ▼
skill_router_skill.md (haiku model)
  ─ Reads .openclaw/catalog-{ts}.json
  ─ Reads task decomposition
  ─ For each task: classify → match to capability
  ─ Writes .openclaw/routing-{ts}.json
         │
         ▼
.openclaw/routing-{ts}.json:
{
  "SKILLS": ["implementer_skill"],
  "TOOLS": ["Bash", "Read", "Write"],
  "COMMANDS": [],
  "MCP_TOOLS": ["stripe.createPaymentIntent"],
  "MISSING": [],
  "per_task": {
    "task-1": {"skill": "implementer_skill", "tools": ["Write", "Bash"]},
    "task-2": {"skill": "implementer_skill", "tools": ["Read", "Write", "Bash"]}
  }
}
         │
         ▼
router_dispatcher.py
  ─ Reads routing JSON
  ─ Loads ONLY the skills listed in "SKILLS"
  ─ Configures agent profiles for the session
  ─ Returns loaded skill context (< 20,000 tokens vs. 80,000+ for full load)
```

---

## 5. File Layout

```
openclaw/
├── skill_router_skill.md          # NEW — router prompt (haiku)
├── tools/
│   ├── capability_catalog.py      # NEW — filesystem scanner
│   └── router_dispatcher.py       # NEW — loads selected skills
├── supervisor_config.json         # MODIFY — router settings
└── agent_profiles.json            # MODIFY — add router profile

.openclaw/
├── catalog-{ts}.json              # RUNTIME — compiled capability catalog
└── routing-{ts}.json              # RUNTIME — router output
```

---

## 6. Adaptation Strategy

### 6.1 No Built-in Skill Registry

Claude Code maintains an internal registry of all skills that the router can
reference. OpenClaw has no central registry.

**Adaptation**: `capability_catalog.py` is the registry builder. It scans the
`openclaw/` directory for all `.md` files, extracts their first-line title and
trigger pattern (a structured header comment in each skill), and writes a compact
catalog JSON. Each skill file should have a header comment:

```markdown
<!-- SKILL: forger | TRIGGER: /forge {name} [url] | DESC: Generate MCP server from API docs -->
```

If no header comment is present, the catalog uses the filename as the skill name
and no trigger pattern.

### 6.2 MCP Server Discovery

Claude Code reads from the Claude app's internal MCP configuration. OpenClaw
reads `.mcp.json` in the project root.

**Adaptation**: `capability_catalog.py` reads `.mcp.json` and lists each server
with its declared tools. If the MCP server has a `tools` array in its config,
those are listed. If not, the server name is listed with `"tools": "unknown"`.

### 6.3 Model Pinning

The router MUST run on haiku. In OpenClaw, model selection is controlled by
`supervisor_config.json`. The `skill_router` entry in `model_routing` pins haiku.

### 6.4 Parallel Bootstrap

Claude Code runs the router in parallel with other Phase 3 tasks using the `Agent`
tool. OpenClaw adaptation: the orchestrator starts the catalog build + router
session in a background thread while other Phase 3 work happens (e.g., reading
project structure). The router result is checked before Phase 4 begins.

---

## 7. Implementation Plan

### Step 1: Add header comments to all existing skills

For each existing skill file in `openclaw/`, add a header comment on line 1:

```markdown
<!-- SKILL: {skill_name} | TRIGGER: {trigger_pattern} | DESC: {one_line_description} -->
```

Example additions:
- `harness_skill.md`: `<!-- SKILL: harness | TRIGGER: /go {task} | DESC: Full autonomous pipeline -->`
- `web_adapter_skill.md`: `<!-- SKILL: web_adapter | TRIGGER: WebFetch {url} | DESC: Fetch web page content -->`
- `model_routing_skill.md`: `<!-- SKILL: model_routing | TRIGGER: internal | DESC: Route tasks to optimal model -->`

### Step 2: Create `capability_catalog.py`

```python
# openclaw/tools/capability_catalog.py
"""
Scans the OpenClaw workspace and builds a compact capability catalog.
Output written to .openclaw/catalog-{timestamp}.json.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

SKILL_HEADER_PATTERN = re.compile(
    r'<!--\s*SKILL:\s*(?P<name>\S+)\s*\|\s*TRIGGER:\s*(?P<trigger>[^|]+?)\s*\|\s*DESC:\s*(?P<desc>.+?)\s*-->'
)

def scan_skills(openclaw_dir: str) -> list[dict]:
    """Scan all .md files in the openclaw directory for skill definitions."""
    skills = []
    skills_path = Path(openclaw_dir)

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
            # No header — infer from filename
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

def scan_mcp_tools(project_root: str) -> list[dict]:
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

def scan_agent_profiles(openclaw_dir: str) -> list[dict]:
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

def scan_cron(openclaw_dir: str) -> list[dict]:
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
        lines.append("  (none installed — use /forge to generate MCP servers)")

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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--openclaw-dir", default="openclaw")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    catalog = build_catalog(args.openclaw_dir, args.project_root)
    save_catalog(catalog, args.output)
    print(f"Catalog written to {args.output}")
    print(f"  Skills: {len(catalog['skills'])}")
    print(f"  MCP tools: {len(catalog['mcp_tools'])}")
    print(f"  Built-in tools: {len(catalog['builtin_tools'])}")
```

### Step 3: Create `router_dispatcher.py`

```python
# openclaw/tools/router_dispatcher.py
"""
Reads skill router output and loads only the selected skills.
Returns a context-optimized skill bundle for the current session.
"""

import json
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
    for skill_name in routing.get("SKILLS", []):
        # Find the skill file
        skill_file = Path(openclaw_dir) / f"{skill_name}.md"
        if not skill_file.exists():
            # Try with _skill suffix
            skill_file = Path(openclaw_dir) / f"{skill_name}_skill.md"

        if skill_file.exists():
            skill_contexts[skill_name] = skill_file.read_text()
        else:
            routing.setdefault("MISSING", []).append(skill_name)

    return {
        "skill_contexts": skill_contexts,
        "active_tools": routing.get("TOOLS", []),
        "active_mcp_tools": routing.get("MCP_TOOLS", []),
        "missing_capabilities": routing.get("MISSING", []),
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--routing", required=True, help="Path to routing JSON")
    parser.add_argument("--openclaw-dir", default="openclaw")
    parser.add_argument("--output", help="Write bundle to file instead of stdout")
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
```

---

## 8. Configuration

### `skill_router_skill.md` (complete file)

```markdown
<!-- SKILL: skill_router | TRIGGER: internal | DESC: Fast capability matching for task routing -->

# Skill Router

You are the OpenClaw Skill Router. You run on the haiku model and your job is
ONLY classification — matching tasks to capabilities. You do NOT implement
anything. You do NOT explain anything at length.

## Input

You receive two inputs:
1. The task decomposition (a list of subtasks to complete)
2. The capability catalog (skills, MCP tools, built-in tools available)

## Your Job

For each subtask, answer: "Which capability handles this?"

Priority order:
1. Installed skill that has this as its explicit trigger → use that skill
2. MCP tool that directly provides this API capability → use that MCP tool
3. Built-in tool sufficient for this → use built-in
4. Multiple capabilities needed → list all
5. Required capability not installed → add to MISSING

## Output Format

Output ONLY valid JSON. No prose. No explanation outside the JSON.

```json
{
  "SKILLS": ["list of skill names that will be needed"],
  "TOOLS": ["list of built-in tool names that will be needed"],
  "COMMANDS": ["list of slash commands to invoke"],
  "MCP_TOOLS": ["list of mcp tool names like 'stripe.createCharge'"],
  "MISSING": ["capabilities required but not installed"],
  "INVOKE_VIA": "brief routing summary e.g. 'forger for task-1; browser for task-2'",
  "REASON": "one sentence explaining the routing decisions",
  "per_task": {
    "task-id-1": {
      "skill": "skill_name or null",
      "tools": ["tool1", "tool2"],
      "mcp_tools": []
    }
  }
}
```

## Rules

- If a task can be done with a built-in tool (Read, Write, Bash), do NOT recommend
  loading a full skill. Skills have overhead.
- If a skill's trigger exactly matches the task type, always prefer it over
  improvising with built-in tools.
- List only what is genuinely needed. Do not add tools "just in case."
- If you are uncertain between two skills, list both.
- If a capability is in MISSING, do not list it in SKILLS — it cannot be loaded.
- Maximum 5 SKILLS listed. If more seem needed, pick the most relevant 5.
- Maximum 10 TOOLS listed.
- Complete in under 1,000 output tokens.
```

### `supervisor_config.json` additions

```json
{
  "skill_router": {
    "enabled": true,
    "model": "claude-haiku-3-5",
    "catalog_builder": "openclaw/tools/capability_catalog.py",
    "dispatcher": "openclaw/tools/router_dispatcher.py",
    "catalog_ttl_seconds": 300,
    "max_skills_to_load": 5,
    "run_in_parallel": true,
    "phase": 3,
    "catalog_output_pattern": ".openclaw/catalog-{ts}.json",
    "routing_output_pattern": ".openclaw/routing-{ts}.json"
  }
}
```

### `agent_profiles.json` additions

```json
{
  "skill_router": {
    "description": "Fast capability matching — haiku model only",
    "model": "claude-haiku-3-5",
    "allowed_tools": ["Read"],
    "max_tokens": 1024,
    "output_format": "json",
    "temperature": 0.0
  }
}
```

### Skill Header Template

Add to every new skill file as line 1:

```markdown
<!-- SKILL: {skill_name} | TRIGGER: {trigger_pattern} | DESC: {one_line_description} -->
```

Retroactively add to existing skills:
- `harness_skill.md`: `<!-- SKILL: harness | TRIGGER: /go {task} | DESC: Full autonomous pipeline with gate/hydrate/build/test/checkpoint -->`
- `web_adapter_skill.md`: `<!-- SKILL: web_adapter | TRIGGER: WebFetch {url} | DESC: Fetch and process web page content -->`
- `model_routing_skill.md`: `<!-- SKILL: model_routing | TRIGGER: internal | DESC: Route tasks to optimal model based on complexity -->`
- `forger_skill.md`: `<!-- SKILL: forger | TRIGGER: /forge {name} [url] | DESC: Generate complete MCP server package from API docs -->`
- `browser_skill.md`: `<!-- SKILL: browser | TRIGGER: /browse {task} | DESC: Multi-step web automation with playwright-cli -->`
- `chrome_skill.md`: `<!-- SKILL: chrome | TRIGGER: /chrome {task} | DESC: Authenticated browsing via Chrome DevTools MCP -->`

---

## 9. Integration Points

### Orchestrator Prompt Addition

Add to `orchestrator_prompt.md` in the Phase 3 section:

```markdown
## Phase 3: Skill Routing (Parallel Bootstrap)

Run these steps in parallel (start all, wait for all):

### 3a: Build Capability Catalog
```bash
python openclaw/tools/capability_catalog.py \
  --openclaw-dir openclaw \
  --project-root . \
  --output .openclaw/catalog-{TIMESTAMP}.json
```

### 3b: Run Skill Router (after 3a completes)
Dispatch `skill_router_skill.md` session with:
- Input: the task decomposition from Phase 2
- Input: the catalog from `.openclaw/catalog-{TIMESTAMP}.json`
- Model: claude-haiku-3-5
- Output: `.openclaw/routing-{TIMESTAMP}.json`

### 3c: Load Selected Skills
```bash
python openclaw/tools/router_dispatcher.py \
  --routing .openclaw/routing-{TIMESTAMP}.json \
  --openclaw-dir openclaw \
  --output .openclaw/skill-bundle-{TIMESTAMP}.md
```

### 3d: Check for Missing Capabilities
Read the routing JSON's `MISSING` array.
If non-empty:
- For each missing capability that can be forged (it's an API/MCP tool):
  - Offer to run `/forge {missing_tool}` automatically
  - Add to Phase 4's task queue
- For capabilities that cannot be forged (e.g., system hardware access):
  - Inform the user and ask how to proceed

### Phase 4+ Context Injection
Every Phase 4+ agent session receives the contents of
`.openclaw/skill-bundle-{TIMESTAMP}.md` as prefixed context.
This ensures only the routed skills are in context, not the full skill library.
```

### Token Savings Calculation

Add a log entry to the orchestrator after Phase 3:

```
Skill Router result:
  Catalog: {N} skills, {M} MCP tools, {P} built-in tools
  Selected: {skills list}
  Estimated context loaded: ~{X} tokens
  Estimated context saved vs. full load: ~{Y} tokens ({Z}% reduction)
```

---

## 10. Testing Plan

### Unit Tests

```python
# tests/test_capability_catalog.py
import json
import pytest
from pathlib import Path
from openclaw.tools.capability_catalog import scan_skills, scan_mcp_tools, build_catalog

def test_scan_skills_with_header(tmp_path):
    skill_file = tmp_path / "forger_skill.md"
    skill_file.write_text(
        "<!-- SKILL: forger | TRIGGER: /forge {name} [url] | DESC: Generate MCP server -->\n\n# Forger"
    )
    skills = scan_skills(str(tmp_path))
    assert len(skills) == 1
    assert skills[0]["name"] == "forger"
    assert skills[0]["trigger"] == "/forge {name} [url]"
    assert "Generate MCP server" in skills[0]["description"]

def test_scan_skills_without_header(tmp_path):
    skill_file = tmp_path / "my_custom_skill.md"
    skill_file.write_text("# My Custom Skill\nDoes something.")
    skills = scan_skills(str(tmp_path))
    assert len(skills) == 1
    assert skills[0]["name"] == "my-custom"
    assert skills[0].get("no_header") == True

def test_scan_mcp_tools(tmp_path):
    mcp_file = tmp_path / ".mcp.json"
    mcp_file.write_text(json.dumps({
        "mcpServers": {
            "stripe": {
                "command": "python",
                "args": ["-m", "stripe_mcp.server"],
                "tools": [
                    {"name": "createCharge", "description": "Create a charge"},
                    {"name": "listCharges", "description": "List charges"}
                ]
            }
        }
    }))
    tools = scan_mcp_tools(str(tmp_path))
    assert len(tools) == 2
    assert tools[0]["name"] == "stripe.createCharge"

def test_compact_text_renders(tmp_path):
    catalog = build_catalog(str(tmp_path), str(tmp_path))
    assert "CAPABILITY CATALOG" in catalog["compact_text"]
    assert "BUILT-IN TOOLS" in catalog["compact_text"]
    assert "Read" in catalog["compact_text"]
```

### Router Accuracy Test

```python
# tests/test_skill_router.py

CATALOG_WITH_FORGER = """
SKILLS:
  forger | trigger: /forge {name} [url] | Generate MCP server from API docs
  browser | trigger: /browse {task} | Multi-step web automation

BUILT-IN TOOLS:
  Read | Read file contents
  Write | Write file contents
  Bash | Run bash commands
  WebFetch | Fetch web page content
"""

TASK_DECOMPOSITION_FORGE = """
Task 1: Generate a Stripe MCP server from the Stripe API docs
Task 2: Run the test suite after installation
"""

# Expected routing: SKILLS = ["forger"], TOOLS = ["Bash"]
# Test by running skill_router_skill.md with haiku and checking output matches expectation
```

### Token Savings Benchmark

```python
def test_token_savings():
    # Load all skills (baseline)
    all_skill_files = list(Path("openclaw").glob("*.md"))
    total_tokens = sum(len(f.read_text()) // 4 for f in all_skill_files)

    # Run router for a simple task
    # Load only selected skills
    # Compare
    # Assert: selected tokens < 30% of total tokens for a simple task
    pass
```

---

## 11. Example Usage

**User**: `/go build a GitHub issue tracker CLI that uses the GitHub API`

**Phase 3a: Catalog built** (0.3 seconds):
```json
{
  "skills": [
    {"name": "forger", "trigger": "/forge {name} [url]"},
    {"name": "browser", "trigger": "/browse {task}"},
    {"name": "harness", "trigger": "/go {task}"},
    {"name": "researcher", "trigger": "/research {topic}"}
  ],
  "mcp_tools": [],
  "builtin_tools": [...]
}
```

**Phase 3b: Router runs** on haiku (1.2 seconds):

Input tasks:
1. Set up TypeScript CLI project scaffold
2. Integrate GitHub REST API (list issues, create issue, close issue)
3. Write command-line argument parsing
4. Write tests

Router output:
```json
{
  "SKILLS": ["forger"],
  "TOOLS": ["Bash", "Read", "Write", "Edit"],
  "COMMANDS": ["/forge github"],
  "MCP_TOOLS": [],
  "MISSING": [],
  "INVOKE_VIA": "forger for task-2 (GitHub API integration); implementer for tasks 1,3,4",
  "REASON": "GitHub MCP server not installed — forger can generate it from GitHub API docs. Remaining tasks are standard implementation.",
  "per_task": {
    "task-1": {"skill": null, "tools": ["Bash", "Write"]},
    "task-2": {"skill": "forger", "tools": []},
    "task-3": {"skill": null, "tools": ["Read", "Write", "Edit"]},
    "task-4": {"skill": null, "tools": ["Read", "Write", "Bash"]}
  }
}
```

**Phase 3c: Skill bundle assembled**:
- `forger_skill.md` loaded: ~3,200 tokens
- Built-in tools listed: no loading overhead
- Total: ~3,200 tokens loaded

**Vs. baseline** (loading all 8 skill files): ~28,000 tokens

**Token savings**: ~87% reduction in Phase 3+ context overhead.

**Phase 4+**:
- Supervisor adds GitHub MCP generation as Wave 1, Task 2 (parallel with scaffold)
- After Wave 1 complete, `github` MCP tools become available for Wave 2+ tasks
