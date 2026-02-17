#!/usr/bin/env python3
"""
Context Pack Verifier

Checks a context pack for completeness and quality. Returns pass/fail
with a list of specific issues. Designed for the Ralph-style verify loop:
    build -> verify -> patch gaps -> verify -> done

Usage:
    python3 verify_context_pack.py <context-pack.md>
    python3 verify_context_pack.py context/harness.md --strict
    python3 verify_context_pack.py context/auth.md --json

Exit codes:
    0 = pass
    1 = fail (issues found)
    2 = error (bad input)
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Required sections (must exist, even if "N/A")
# ---------------------------------------------------------------------------
REQUIRED_SECTIONS = [
    "Goal",
    "Non-Goals",
    "Current State",
    "Architecture",
    "Interfaces",
    "Constraints",
    "Key Decisions",
    "How to Run",       # matches "How to Run / Test / Build" etc.
    "File Map",
    "External Dependencies",
    "Open Questions",
    "Next Actions",
]

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_sections(content: str, headings: List[str]) -> List[str]:
    """Check that all required sections exist."""
    issues = []
    for section in REQUIRED_SECTIONS:
        found = False
        for h in headings:
            if section.lower() in h.lower():
                found = True
                break
        if not found:
            issues.append(f"Missing required section: '{section}'")
    return issues


def check_placeholders(content: str) -> List[str]:
    """Check for unfilled placeholder markers."""
    issues = []
    placeholder_patterns = [
        (r"_[A-Z].*\._", "italic placeholder"),
        (r"\{[A-Z_]+\}", "template variable"),
    ]
    for pattern, desc in placeholder_patterns:
        matches = re.findall(pattern, content)
        if len(matches) > 3:
            issues.append(f"Too many unfilled placeholders ({len(matches)} {desc} markers found)")
    return issues


def check_file_paths(content: str, strict: bool = False) -> List[str]:
    """Check for concrete file paths (grounding)."""
    issues = []

    # Look for paths like `path/to/file.ext` or /absolute/path
    path_pattern = r'`[a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+`'
    paths = re.findall(path_pattern, content)

    # Also count paths in table cells
    table_path_pattern = r'\|\s*`[a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+`'
    table_paths = re.findall(table_path_pattern, content)

    total_paths = len(set(paths)) + len(set(table_paths))

    min_paths = 5 if strict else 3
    if total_paths < min_paths:
        issues.append(
            f"Too few concrete file paths ({total_paths} found, need at least {min_paths}). "
            "Context packs should reference specific files so agents know where to look."
        )
    return issues


def check_commands(content: str, strict: bool = False) -> List[str]:
    """Check for concrete commands (grounding)."""
    issues = []

    # Look for commands in code blocks
    code_blocks = re.findall(r'```(?:bash|sh)?\n(.*?)```', content, re.DOTALL)
    all_code = "\n".join(code_blocks)

    # Count non-comment, non-empty lines in code blocks
    command_lines = [
        line.strip() for line in all_code.split("\n")
        if line.strip() and not line.strip().startswith("#")
    ]

    min_cmds = 3 if strict else 1
    if len(command_lines) < min_cmds:
        issues.append(
            f"Too few concrete commands ({len(command_lines)} found, need at least {min_cmds}). "
            "Include how to install, run, and test."
        )
    return issues


def check_external_deps(content: str) -> List[str]:
    """Check that external dependencies are listed."""
    issues = []

    # Check the External Dependencies section has at least one real entry
    deps_match = re.search(
        r'##\s*External Dependencies(.*?)(?=\n##|\Z)',
        content, re.DOTALL
    )
    if deps_match:
        deps_section = deps_match.group(1)
        if "none detected" in deps_section.lower() or not re.search(r'\|.+\|.+\|.+\|', deps_section):
            # This is just a warning, not a hard fail -- some modules genuinely have no deps
            pass
    return issues


def check_contradictions(content: str) -> List[str]:
    """Basic contradiction detection via keyword analysis."""
    issues = []

    # Database contradictions
    databases = set()
    db_patterns = {
        "postgres": "PostgreSQL",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
        "mariadb": "MariaDB",
        "sqlite": "SQLite",
        "mongodb": "MongoDB",
        "dynamodb": "DynamoDB",
    }
    content_lower = content.lower()
    for pattern, db_name in db_patterns.items():
        if pattern in content_lower:
            databases.add(db_name)
    if len(databases) > 2:
        issues.append(
            f"Possible contradiction: multiple databases mentioned ({', '.join(databases)}). "
            "Clarify which is primary vs secondary."
        )

    # Runtime contradictions
    runtimes = set()
    for rt in ["node.js", "python", "go", "rust", "java", "ruby"]:
        if rt in content_lower:
            runtimes.add(rt)
    if len(runtimes) > 2:
        issues.append(
            f"Multiple runtimes mentioned ({', '.join(runtimes)}). "
            "This might be correct for a polyglot project -- verify."
        )

    return issues


def check_open_questions(content: str) -> List[str]:
    """Check that open questions are listed if there are placeholders."""
    issues = []

    # If there are unfilled sections, there should be open questions
    placeholder_count = len(re.findall(r'_[A-Z].*\._', content))
    oq_match = re.search(
        r'##\s*Open Questions(.*?)(?=\n##|\Z)',
        content, re.DOTALL
    )
    if oq_match:
        oq_section = oq_match.group(1).strip()
        has_questions = bool(re.search(r'^\s*[-*]\s*\S', oq_section, re.MULTILINE))
        if placeholder_count > 2 and not has_questions:
            issues.append(
                "Pack has unfilled sections but no open questions listed. "
                "Add open questions for anything uncertain."
            )
    return issues


def check_scope(content: str) -> List[str]:
    """Check that scope is declared."""
    issues = []
    if not re.search(r'>\s*Scope:', content):
        issues.append("Missing scope declaration. Add '> Scope: <path>' near the top.")
    return issues


def check_empty_tables(content: str) -> List[str]:
    """Check for tables with only empty/placeholder rows."""
    issues = []
    # Find tables where the data rows are all empty
    table_pattern = r'\|[^\n]+\|\n\|[-| ]+\|\n(\|[^\n]+\|\n*)*'
    tables = re.findall(table_pattern, content)
    empty_count = 0
    for table in tables:
        if table.strip():
            rows = [r for r in table.strip().split("\n") if r.strip()]
            if all("| |" in r or "| (none" in r or "| (no " in r for r in rows):
                empty_count += 1
    if empty_count > 2:
        issues.append(f"{empty_count} tables have only empty/placeholder rows. Fill them in.")
    return issues


# ---------------------------------------------------------------------------
# Main verifier
# ---------------------------------------------------------------------------

def verify(pack_path: Path, strict: bool = False) -> Tuple[bool, List[str]]:
    """
    Verify a context pack. Returns (passed, issues).
    """
    if not pack_path.exists():
        return False, [f"File not found: {pack_path}"]

    content = pack_path.read_text(encoding="utf-8")

    if len(content.strip()) < 100:
        return False, ["Context pack is nearly empty (< 100 chars)"]

    # Extract headings
    headings = re.findall(r'^#{1,3}\s+(.+)$', content, re.MULTILINE)

    # Run all checks
    issues = []
    issues.extend(check_scope(content))
    issues.extend(check_sections(content, headings))
    issues.extend(check_placeholders(content))
    issues.extend(check_file_paths(content, strict))
    issues.extend(check_commands(content, strict))
    issues.extend(check_external_deps(content))
    issues.extend(check_contradictions(content))
    issues.extend(check_open_questions(content))
    issues.extend(check_empty_tables(content))

    passed = len(issues) == 0
    return passed, issues


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Verify a context pack for completeness")
    parser.add_argument("pack", help="Path to the context pack .md file")
    parser.add_argument("--strict", action="store_true", help="Stricter thresholds")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    args = parser.parse_args()
    pack_path = Path(args.pack).resolve()

    passed, issues = verify(pack_path, strict=args.strict)

    if args.json_output:
        print(json.dumps({
            "file": str(pack_path),
            "passed": passed,
            "issues": issues,
            "issue_count": len(issues),
        }, indent=2))
    else:
        if passed:
            print(f"PASS: {pack_path.name}")
            print(f"  All checks passed.")
        else:
            print(f"FAIL: {pack_path.name} ({len(issues)} issues)")
            for i, issue in enumerate(issues, 1):
                print(f"  {i}. {issue}")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
