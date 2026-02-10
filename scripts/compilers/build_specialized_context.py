#!/usr/bin/env python3
"""
Specialized Context Compiler
Compiles specialized context packs for sub-agents
"""

import argparse
from pathlib import Path
from context_hydrator import ContextHydrator

def main():
    parser = argparse.ArgumentParser(description="Build specialized context for agent")
    parser.add_argument("--agent-id", required=True, help="Agent ID")
    parser.add_argument("--task", required=True, help="Task description")
    parser.add_argument("--role", required=True, help="Agent role")
    parser.add_argument("--repo-map", help="Path to REPO_MAP.md")
    parser.add_argument("--context-pack", help="Path to CONTEXT_PACK.md")
    parser.add_argument("--repo", default=".", help="Repository root path")
    parser.add_argument("--output", help="Output file path (default: ai/context/specialized/{agent_id}_CONTEXT.md)")
    
    args = parser.parse_args()
    
    repo_path = Path(args.repo).resolve()
    hydrator = ContextHydrator(repo_path)
    
    existing_context = {}
    if args.repo_map:
        existing_context["repo_map"] = args.repo_map
    if args.context_pack:
        existing_context["context_pack"] = args.context_pack
    
    context_file = hydrator.build_specialized_context(
        agent_id=args.agent_id,
        task_description=args.task,
        agent_role=args.role,
        existing_context=existing_context if existing_context else None
    )
    
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        context_file.rename(output_path)
        print(f"✓ Moved to: {output_path}")
    else:
        print(f"✓ Generated: {context_file}")

if __name__ == "__main__":
    main()
