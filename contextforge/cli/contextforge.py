#!/usr/bin/env python3
"""
ContextForge CLI — analyze repos, generate skills/agents, manage memory, observe events.

Usage:
  python -m contextforge.cli.contextforge analyze <repo_path> [--output-dir <dir>]
  python -m contextforge.cli.contextforge generate <repo_path> [--output-dir <dir>]
  python -m contextforge.cli.contextforge memory submit <content> [--category rule]
  python -m contextforge.cli.contextforge memory list-pending
  python -m contextforge.cli.contextforge memory promote <entry_id>
  python -m contextforge.cli.contextforge memory reject <entry_id> [--reason <reason>]
  python -m contextforge.cli.contextforge vet <target_path>
  python -m contextforge.cli.contextforge ui [--port 8900]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure contextforge is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from contextforge.packages.events import CorrelationIDs, new_run_id
from contextforge.packages.events.emitter import EventEmitter


def cmd_analyze(args):
    """Analyze a repository and print results."""
    from contextforge.packages.analyzer import RepoAnalyzer

    correlation = CorrelationIDs(run_id=new_run_id())
    analyzer = RepoAnalyzer(args.repo_path, correlation=correlation)
    result = analyzer.analyze()

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        s = result.stack
        print(f"Repository: {result.repo_path}")
        print(f"Commit:     {result.source_commit}")
        print(f"Hash:       {result.analysis_hash}")
        print(f"Files:      {result.structure.total_files}")
        print(f"Languages:  {', '.join(f'{l} ({c})' for l, c in s.languages.items())}")
        print(f"Frameworks: {', '.join(s.frameworks) or 'none'}")
        print(f"Pkg mgrs:   {', '.join(s.package_managers) or 'none'}")
        print(f"Linters:    {', '.join(result.conventions.linters) or 'none'}")
        print(f"Tests:      {', '.join(result.conventions.test_frameworks) or 'none'}")
        print(f"Docker:     {'yes' if s.has_docker else 'no'}")
        print(f"CI:         {s.ci_system or 'none'}")

    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "analysis.json", "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"\nAnalysis saved to {out / 'analysis.json'}")


def cmd_generate(args):
    """Analyze repo and generate skills + agents."""
    from contextforge.packages.analyzer import RepoAnalyzer
    from contextforge.packages.generator import SkillGenerator, AgentGenerator
    from contextforge.packages.security.provenance import generate_sbom

    correlation = CorrelationIDs(run_id=new_run_id())
    output = Path(args.output_dir)

    # Analyze
    print(f"Analyzing {args.repo_path}...")
    analyzer = RepoAnalyzer(args.repo_path, correlation=correlation)
    result = analyzer.analyze()
    print(f"  {result.structure.total_files} files, {len(result.stack.languages)} languages")

    # Generate skills
    print(f"\nGenerating skills...")
    skill_gen = SkillGenerator(output / "skills", correlation=correlation)
    skills = skill_gen.generate_all(result)
    for s in skills:
        print(f"  Created: {s.name}")
        # Generate SBOM for each skill
        manifest_path = s / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            generate_sbom(s, manifest["id"], manifest["version"],
                         manifest.get("dependencies"))
            print(f"    + sbom.json")

    # Generate agents
    print(f"\nGenerating agents...")
    agent_gen = AgentGenerator(output / "agents", correlation=correlation)
    agents = agent_gen.generate_all(result)
    for a in agents:
        print(f"  Created: {a.name}")

    # Save analysis
    with open(output / "analysis.json", "w") as f:
        json.dump(result.to_dict(), f, indent=2)

    print(f"\nDone. Output: {output}")
    print(f"Run ID: {correlation.run_id}")


def cmd_memory(args):
    """Memory management commands."""
    from contextforge.packages.memory import MemoryManager

    workspace = Path(args.workspace)
    correlation = CorrelationIDs(run_id=new_run_id())
    mgr = MemoryManager(workspace, correlation=correlation)

    if args.memory_cmd == "submit":
        entry = mgr.submit(args.content, category=args.category, source="cli")
        print(f"Created pending entry: {entry.id}")
        print(f"  Category: {entry.category}")
        print(f"  Content:  {entry.content[:80]}...")

    elif args.memory_cmd == "list-pending":
        entries = mgr.list_pending()
        if not entries:
            print("No pending entries.")
        for e in entries:
            print(f"  [{e.id}] ({e.category}) {e.content[:60]}...")

    elif args.memory_cmd == "promote":
        entry = mgr.promote(args.entry_id, promoted_by="cli-user")
        print(f"Promoted: {entry.id}")

    elif args.memory_cmd == "reject":
        entry = mgr.reject(args.entry_id, rejected_by="cli-user", reason=args.reason or "")
        print(f"Rejected: {entry.id}")

    elif args.memory_cmd == "list-promoted":
        entries = mgr.list_promoted()
        if not entries:
            print("No promoted entries.")
        for e in entries:
            print(f"  [{e.id}] ({e.category}) {e.content[:60]}...")


def cmd_vet(args):
    """Run security vetting on a target."""
    from contextforge.packages.security import VettingPipeline

    correlation = CorrelationIDs(run_id=new_run_id())
    pipeline = VettingPipeline(correlation=correlation)
    result = pipeline.vet(args.target_path)

    print(f"Verdict: {result.verdict.upper()}")
    print(f"Duration: {result.duration_ms}ms")
    print(f"Scanners run: {', '.join(result.scanners_run) or 'none'}")
    print(f"Scanners skipped: {', '.join(result.scanners_skipped) or 'none'}")
    print(f"Findings: {len(result.findings)} ({result.critical_count} critical, {result.high_count} high)")

    if result.findings:
        print("\nFindings:")
        for f in result.findings:
            print(f"  [{f.severity.upper()}] {f.scanner}: {f.message}")
            if f.file:
                print(f"    File: {f.file}" + (f":{f.line}" if f.line else ""))

    if args.json:
        print(f"\n{json.dumps(result.to_dict(), indent=2)}")


def cmd_ui(args):
    """Start the observability UI."""
    from contextforge.packages.ui.server import run_server
    run_server(port=args.port, log_path=args.log_path)


def main():
    parser = argparse.ArgumentParser(
        prog="contextforge",
        description="ContextForge: workspace analysis, skill generation, memory, and observability",
    )
    sub = parser.add_subparsers(dest="command")

    # analyze
    p = sub.add_parser("analyze", help="Analyze a repository")
    p.add_argument("repo_path", help="Path to repository")
    p.add_argument("--output-dir", "-o", help="Save analysis to directory")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # generate
    p = sub.add_parser("generate", help="Analyze repo and generate skills + agents")
    p.add_argument("repo_path", help="Path to repository")
    p.add_argument("--output-dir", "-o", default=".contextforge", help="Output directory")

    # memory
    p = sub.add_parser("memory", help="Memory management")
    msub = p.add_subparsers(dest="memory_cmd")
    p.add_argument("--workspace", default=".", help="OpenClaw workspace path")

    ms = msub.add_parser("submit", help="Submit a pending memory entry")
    ms.add_argument("content", help="Memory content")
    ms.add_argument("--category", default="rule", choices=["rule", "correction", "learned", "observation"])

    msub.add_parser("list-pending", help="List pending entries")
    msub.add_parser("list-promoted", help="List promoted entries")

    mp = msub.add_parser("promote", help="Promote a pending entry")
    mp.add_argument("entry_id", help="Entry ID to promote")

    mr = msub.add_parser("reject", help="Reject a pending entry")
    mr.add_argument("entry_id", help="Entry ID to reject")
    mr.add_argument("--reason", default="", help="Rejection reason")

    # vet
    p = sub.add_parser("vet", help="Run security vetting")
    p.add_argument("target_path", help="Directory to vet")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # ui
    p = sub.add_parser("ui", help="Start observability UI")
    p.add_argument("--port", type=int, default=8900)
    p.add_argument("--log-path", default=None)

    args = parser.parse_args()

    if args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "generate":
        cmd_generate(args)
    elif args.command == "memory":
        cmd_memory(args)
    elif args.command == "vet":
        cmd_vet(args)
    elif args.command == "ui":
        cmd_ui(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
