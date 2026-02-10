#!/usr/bin/env python3
"""
Gemini Context Builder
Builds specialized context for Gemini multi-agent system
"""

import os
import json
from pathlib import Path
from typing import Dict, Optional

# Gemini API integration would go here
# For now, this is a wrapper around the context hydrator

def build_context_for_gemini_agent(agent_id: str, agent_role: str, 
                                   task_description: str, repo_path: Path) -> Path:
    """Build specialized context for Gemini agent"""
    import sys
    sys.path.append(str(repo_path / "scripts" / "broker"))
    from context_hydrator import ContextHydrator
    
    hydrator = ContextHydrator(repo_path)
    
    context_file = hydrator.build_specialized_context(
        agent_id=agent_id,
        task_description=task_description,
        agent_role=agent_role,
        existing_context={
            "repo_map": str(repo_path / "ai/context/REPO_MAP.md"),
            "context_pack": str(repo_path / "ai/context/CONTEXT_PACK.md")
        }
    )
    
    return context_file

def inject_context_via_function_calling(context_file: Path) -> Dict:
    """
    Prepare context for injection via Gemini function calling
    
    Returns context dict ready for Gemini API
    """
    context_content = context_file.read_text(encoding='utf-8')
    
    # Gemini function calling format
    return {
        "function": "set_context",
        "parameters": {
            "context": context_content,
            "source": str(context_file)
        }
    }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Gemini context builder")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--agent-role", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--format", choices=["file", "function"], default="file")
    
    args = parser.parse_args()
    
    repo_path = Path(args.repo).resolve()
    context_file = build_context_for_gemini_agent(
        args.agent_id,
        args.agent_role,
        args.task,
        repo_path
    )
    
    if args.format == "function":
        context_data = inject_context_via_function_calling(context_file)
        print(json.dumps(context_data, indent=2))
    else:
        print(str(context_file))
