#!/usr/bin/env python3
"""
Context Pack Builder

Scans a project scope (repo root, subdirectory, or module) and generates
a structured CONTEXT.md from what it finds. Auto-populates file maps,
detected stack, entry points, and run commands. Leaves placeholders for
sections requiring human/agent input.

Usage:
    python3 build_context_pack.py --scope /path/to/project [--output context/project.md]
    python3 build_context_pack.py --scope /path/to/project/subdir --name "auth-module"
    python3 build_context_pack.py --scope . --name "harness"

The builder detects:
    - Package managers and dependencies (package.json, requirements.txt, etc.)
    - Entry points (main files, server files, CLI scripts)
    - Config files (Dockerfile, docker-compose, .env.example, etc.)
    - Test files and test commands
    - README content (goals, description)
    - Git info (remote URL, branch)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

# Key files to always include in the file map
KEY_FILE_PATTERNS = [
    "README.md", "README.rst", "README.txt",
    "package.json", "requirements.txt", "pyproject.toml", "Cargo.toml",
    "go.mod", "Gemfile", "pom.xml", "build.gradle",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".env.example", ".env.sample",
    "Makefile", "justfile", "Taskfile.yml",
    "tsconfig.json", "webpack.config.js", "vite.config.ts",
    ".github/workflows/*.yml", ".github/workflows/*.yaml",
]

# Patterns that suggest entry points
ENTRY_PATTERNS = [
    "server.*", "app.*", "main.*", "index.*", "cli.*",
    "manage.py", "wsgi.py", "asgi.py",
    "bin/*", "cmd/*",
]

# Patterns for test files
TEST_PATTERNS = [
    "test_*", "*_test.*", "*.test.*", "*.spec.*",
    "tests/*", "test/*", "__tests__/*", "spec/*",
]


def detect_stack(scope: Path) -> Dict[str, Any]:
    """Detect the technology stack from files present."""
    stack = {
        "languages": [],
        "frameworks": [],
        "package_manager": None,
        "runtime": None,
    }

    if (scope / "package.json").exists():
        stack["languages"].append("JavaScript/TypeScript")
        stack["package_manager"] = "npm"
        stack["runtime"] = "Node.js"
        try:
            pkg = json.loads((scope / "package.json").read_text(encoding="utf-8"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "react" in deps:
                stack["frameworks"].append("React")
            if "next" in deps:
                stack["frameworks"].append("Next.js")
            if "express" in deps:
                stack["frameworks"].append("Express")
            if "fastify" in deps:
                stack["frameworks"].append("Fastify")
            if "vue" in deps:
                stack["frameworks"].append("Vue")
            if "svelte" in deps or "@sveltejs/kit" in deps:
                stack["frameworks"].append("Svelte")
            if "typescript" in deps:
                stack["languages"] = ["TypeScript"]
        except Exception:
            pass

    if (scope / "requirements.txt").exists() or (scope / "pyproject.toml").exists():
        stack["languages"].append("Python")
        stack["package_manager"] = stack["package_manager"] or "pip"
        stack["runtime"] = stack["runtime"] or "Python"
        for req_file in ["requirements.txt", "pyproject.toml"]:
            p = scope / req_file
            if p.exists():
                content = p.read_text(encoding="utf-8", errors="ignore")
                if "django" in content.lower():
                    stack["frameworks"].append("Django")
                if "flask" in content.lower():
                    stack["frameworks"].append("Flask")
                if "fastapi" in content.lower():
                    stack["frameworks"].append("FastAPI")

    if (scope / "go.mod").exists():
        stack["languages"].append("Go")
        stack["runtime"] = stack["runtime"] or "Go"

    if (scope / "Cargo.toml").exists():
        stack["languages"].append("Rust")
        stack["runtime"] = stack["runtime"] or "Rust"

    if (scope / "Gemfile").exists():
        stack["languages"].append("Ruby")
        stack["frameworks"].append("Rails (likely)")

    return stack


def find_key_files(scope: Path, max_depth: int = 3) -> List[Tuple[str, str]]:
    """Find key files and describe their purpose."""
    files = []

    for root, dirs, filenames in os.walk(scope):
        rel_root = Path(root).relative_to(scope)
        depth = len(rel_root.parts)
        if depth > max_depth:
            dirs.clear()
            continue

        # Skip common junk directories
        dirs[:] = [d for d in dirs if d not in {
            "node_modules", ".git", "__pycache__", ".venv", "venv",
            ".next", "dist", "build", ".cache", ".tox", ".mypy_cache",
        }]

        for fname in filenames:
            rel_path = str(rel_root / fname) if str(rel_root) != "." else fname
            purpose = classify_file(fname, rel_path)
            if purpose:
                files.append((rel_path, purpose))

    return sorted(files, key=lambda x: x[0])


def classify_file(name: str, rel_path: str) -> Optional[str]:
    """Classify a file by its name/path. Returns a purpose string or None."""
    name_lower = name.lower()

    if name_lower in {"readme.md", "readme.rst", "readme.txt"}:
        return "Project documentation"
    if name_lower == "package.json":
        return "Node.js dependencies and scripts"
    if name_lower in {"requirements.txt", "pyproject.toml"}:
        return "Python dependencies"
    if name_lower in {"cargo.toml", "go.mod", "gemfile"}:
        return "Language dependencies"
    if name_lower in {"dockerfile", "dockerfile.dev", "dockerfile.prod"}:
        return "Container build definition"
    if name_lower in {"docker-compose.yml", "docker-compose.yaml"}:
        return "Container orchestration"
    if name_lower in {".env.example", ".env.sample"}:
        return "Environment variable template"
    if name_lower in {"makefile", "justfile", "taskfile.yml"}:
        return "Build/task automation"
    if name_lower in {"tsconfig.json"}:
        return "TypeScript configuration"
    if name_lower.endswith(".config.js") or name_lower.endswith(".config.ts"):
        return "Build/tool configuration"
    if name_lower in {".gitignore"}:
        return "Git ignore rules"

    # Entry points
    if re.match(r"(server|app|main|index|cli)\.(js|ts|py|go|rs)$", name_lower):
        return "Entry point"
    if name_lower in {"manage.py", "wsgi.py", "asgi.py"}:
        return "Entry point"

    # Test files
    if re.match(r"test_.*\.(py|js|ts)$", name_lower):
        return "Test file"
    if re.match(r".*\.(test|spec)\.(js|ts|py)$", name_lower):
        return "Test file"

    # CI/CD
    if ".github/workflows" in rel_path:
        return "CI/CD workflow"

    # Service/unit files
    if name_lower.endswith(".service"):
        return "Systemd service definition"

    # Skill/doc files (OpenClaw-specific)
    if name_lower.endswith("_skill.md") or name_lower.endswith("_skill.txt"):
        return "Agent skill definition"

    return None


def detect_run_commands(scope: Path, stack: Dict) -> Dict[str, str]:
    """Detect how to run, test, and build the project."""
    commands = {}

    # From package.json scripts
    pkg_path = scope / "package.json"
    if pkg_path.exists():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
            if "start" in scripts:
                commands["run"] = f"npm start  # {scripts['start']}"
            elif "dev" in scripts:
                commands["run"] = f"npm run dev  # {scripts['dev']}"
            if "test" in scripts:
                commands["test"] = f"npm test  # {scripts['test']}"
            if "build" in scripts:
                commands["build"] = f"npm run build  # {scripts['build']}"
            commands["install"] = "npm install"
        except Exception:
            pass

    # From Python
    if (scope / "requirements.txt").exists():
        commands.setdefault("install", "pip install -r requirements.txt")
    if (scope / "pyproject.toml").exists():
        commands.setdefault("install", "pip install -e .")
    if (scope / "manage.py").exists():
        commands.setdefault("run", "python manage.py runserver")
        commands.setdefault("test", "python manage.py test")
    if (scope / "pytest.ini").exists() or (scope / "pyproject.toml").exists():
        commands.setdefault("test", "pytest")

    # From Makefile
    if (scope / "Makefile").exists():
        try:
            content = (scope / "Makefile").read_text(encoding="utf-8", errors="ignore")
            for target in ["run", "start", "dev", "test", "build", "install"]:
                if re.search(rf"^{target}\s*:", content, re.MULTILINE):
                    commands.setdefault(target if target != "start" else "run", f"make {target}")
        except Exception:
            pass

    # Docker
    if (scope / "docker-compose.yml").exists() or (scope / "docker-compose.yaml").exists():
        commands.setdefault("run", "docker compose up")
        commands.setdefault("build", "docker compose build")
    elif (scope / "Dockerfile").exists():
        commands.setdefault("build", "docker build -t <name> .")
        commands.setdefault("run", "docker run <name>")

    return commands


def extract_readme_goal(scope: Path) -> str:
    """Try to extract a project goal/description from README."""
    for name in ["README.md", "README.rst", "README.txt"]:
        readme = scope / name
        if readme.exists():
            try:
                content = readme.read_text(encoding="utf-8", errors="ignore")
                lines = content.split("\n")
                # Find first non-heading, non-empty paragraph
                collecting = False
                paragraph = []
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        if paragraph:
                            break
                        collecting = True
                        continue
                    if collecting and stripped:
                        paragraph.append(stripped)
                    elif collecting and not stripped and paragraph:
                        break
                if paragraph:
                    return " ".join(paragraph)[:300]
            except Exception:
                pass
    return "_Describe the project goal in 1-3 sentences._"


def detect_external_deps(scope: Path) -> List[Tuple[str, str, str]]:
    """Detect external dependencies from config files."""
    deps = []

    # Docker compose services
    for compose_name in ["docker-compose.yml", "docker-compose.yaml"]:
        compose = scope / compose_name
        if compose.exists():
            try:
                content = compose.read_text(encoding="utf-8", errors="ignore")
                # Simple detection of common services
                if "postgres" in content.lower() or "postgresql" in content.lower():
                    deps.append(("PostgreSQL", "Database", "via Docker Compose"))
                if "mysql" in content.lower() or "mariadb" in content.lower():
                    deps.append(("MySQL/MariaDB", "Database", "via Docker Compose"))
                if "redis" in content.lower():
                    deps.append(("Redis", "Cache/Queue", "via Docker Compose"))
                if "rabbitmq" in content.lower():
                    deps.append(("RabbitMQ", "Message Queue", "via Docker Compose"))
                if "kafka" in content.lower():
                    deps.append(("Kafka", "Event Streaming", "via Docker Compose"))
                if "elasticsearch" in content.lower():
                    deps.append(("Elasticsearch", "Search Engine", "via Docker Compose"))
                if "mongo" in content.lower():
                    deps.append(("MongoDB", "Database", "via Docker Compose"))
            except Exception:
                pass

    # .env.example for API keys
    for env_name in [".env.example", ".env.sample"]:
        env_file = scope / env_name
        if env_file.exists():
            try:
                content = env_file.read_text(encoding="utf-8", errors="ignore")
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#") and "API_KEY" in line.upper():
                        key_name = line.split("=")[0].strip()
                        deps.append((key_name, "API Key", "Set in .env"))
                    if line and not line.startswith("#") and "DATABASE_URL" in line.upper():
                        deps.append(("Database", "Database", "Set in .env"))
            except Exception:
                pass

    return deps


def get_git_info(scope: Path) -> Dict[str, str]:
    """Get basic git info."""
    import subprocess
    info = {}
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=scope, timeout=5,
        )
        if result.returncode == 0:
            info["remote"] = result.stdout.strip()
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=scope, timeout=5,
        )
        if result.returncode == 0:
            info["branch"] = result.stdout.strip()
    except Exception:
        pass
    return info


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_context_pack(scope: Path, name: Optional[str] = None, output: Optional[Path] = None) -> str:
    """Build a context pack for the given scope."""

    scope = scope.resolve()
    if not scope.exists():
        print(f"ERROR: Scope path does not exist: {scope}", file=sys.stderr)
        sys.exit(1)

    scope_name = name or scope.name
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Detect everything
    stack = detect_stack(scope)
    key_files = find_key_files(scope)
    run_cmds = detect_run_commands(scope, stack)
    goal = extract_readme_goal(scope)
    ext_deps = detect_external_deps(scope)
    git_info = get_git_info(scope)

    # Build the pack
    lines = []
    lines.append(f"# Context Pack: {scope_name}")
    lines.append("")
    lines.append(f"> Generated: {timestamp}")
    lines.append(f"> Scope: `{scope}`")
    if git_info.get("remote"):
        lines.append(f"> Repo: {git_info['remote']}")
    if git_info.get("branch"):
        lines.append(f"> Branch: {git_info['branch']}")
    lines.append("")

    # Goal
    lines.append("## Goal")
    lines.append("")
    lines.append(goal)
    lines.append("")

    # Non-goals
    lines.append("## Non-Goals")
    lines.append("")
    lines.append("_Define what is explicitly NOT in scope._")
    lines.append("")

    # Current state
    lines.append("## Current State")
    lines.append("")
    stack_str = ", ".join(stack["languages"]) if stack["languages"] else "Unknown"
    fw_str = ", ".join(stack["frameworks"]) if stack["frameworks"] else "None detected"
    lines.append(f"**Stack:** {stack_str}")
    lines.append(f"**Frameworks:** {fw_str}")
    if stack["package_manager"]:
        lines.append(f"**Package Manager:** {stack['package_manager']}")
    if stack["runtime"]:
        lines.append(f"**Runtime:** {stack['runtime']}")
    lines.append("")

    # Architecture
    lines.append("## Architecture")
    lines.append("")
    lines.append("_Components and their responsibilities. Fill in after reviewing the codebase._")
    lines.append("")
    lines.append("| Component | Responsibility | Location |")
    lines.append("|-----------|---------------|----------|")
    lines.append("| | | |")
    lines.append("")

    # Interfaces
    lines.append("## Interfaces")
    lines.append("")
    lines.append("### APIs")
    lines.append("")
    lines.append("_List API endpoints, their methods, and purpose._")
    lines.append("")
    lines.append("### Events / Messages")
    lines.append("")
    lines.append("_List any event systems, message queues, or pub/sub topics._")
    lines.append("")
    lines.append("### Data Models")
    lines.append("")
    lines.append("_Key data structures, database schemas, or type definitions._")
    lines.append("")

    # Constraints
    lines.append("## Constraints")
    lines.append("")
    lines.append("_Technical, security, time, or business constraints._")
    lines.append("")
    lines.append("- ")
    lines.append("")

    # Key decisions
    lines.append("## Key Decisions")
    lines.append("")
    lines.append("| Decision | Rationale |")
    lines.append("|----------|-----------|")
    lines.append("| | |")
    lines.append("")

    # How to run/test/build
    lines.append("## How to Run / Test / Build")
    lines.append("")
    lines.append("```bash")
    if run_cmds.get("install"):
        lines.append(f"# Install dependencies")
        lines.append(run_cmds["install"])
        lines.append("")
    if run_cmds.get("run"):
        lines.append(f"# Run")
        lines.append(run_cmds["run"])
        lines.append("")
    if run_cmds.get("test"):
        lines.append(f"# Test")
        lines.append(run_cmds["test"])
        lines.append("")
    if run_cmds.get("build"):
        lines.append(f"# Build")
        lines.append(run_cmds["build"])
        lines.append("")
    if not run_cmds:
        lines.append("# (no run commands detected -- fill in manually)")
        lines.append("")
    lines.append("```")
    lines.append("")

    # File map
    lines.append("## File Map")
    lines.append("")
    lines.append("| File | Purpose |")
    lines.append("|------|---------|")
    for path, purpose in key_files[:30]:
        lines.append(f"| `{path}` | {purpose} |")
    if len(key_files) > 30:
        lines.append(f"| ... | ({len(key_files) - 30} more files) |")
    if not key_files:
        lines.append("| (no key files detected) | |")
    lines.append("")

    # External dependencies
    lines.append("## External Dependencies")
    lines.append("")
    lines.append("| Dependency | Type | Notes |")
    lines.append("|------------|------|-------|")
    for dep_name, dep_type, dep_notes in ext_deps:
        lines.append(f"| {dep_name} | {dep_type} | {dep_notes} |")
    if not ext_deps:
        lines.append("| (none detected) | | |")
    lines.append("")

    # Open questions
    lines.append("## Open Questions / Risks")
    lines.append("")
    lines.append("_Anything uncertain. Better to list it than to guess._")
    lines.append("")
    lines.append("- ")
    lines.append("")

    # Next actions
    lines.append("## Next Actions")
    lines.append("")
    lines.append("1. Review and fill in placeholder sections above")
    lines.append("2. Run verifier: `python3 verify_context_pack.py <this-file>`")
    lines.append("3. Iterate until verifier passes")
    lines.append("")

    content = "\n".join(lines)

    # Write output
    if output is None:
        output = scope / "context" / f"{scope_name}.md"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")

    # Print summary
    print(json.dumps({
        "status": "ok",
        "output": str(output),
        "scope": str(scope),
        "name": scope_name,
        "stack": stack["languages"],
        "frameworks": stack["frameworks"],
        "key_files": len(key_files),
        "run_commands": len(run_cmds),
        "external_deps": len(ext_deps),
    }, indent=2))

    return str(output)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build a context pack for a project or module scope"
    )
    parser.add_argument("--scope", required=True, help="Path to the project or module to scan")
    parser.add_argument("--name", default=None, help="Name for the context pack (defaults to directory name)")
    parser.add_argument("--output", default=None, help="Output file path (defaults to context/<name>.md)")

    args = parser.parse_args()

    scope = Path(args.scope).resolve()
    output = Path(args.output).resolve() if args.output else None

    build_context_pack(scope, name=args.name, output=output)


if __name__ == "__main__":
    main()
