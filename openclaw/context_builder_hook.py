#!/usr/bin/env python3
"""
OpenClaw Context Builder Hook
Pre-spawn hook that builds specialized context for agents
"""

import json
import sys
from pathlib import Path
from typing import Optional

def build_context_for_agent(agent_id: str, agent_role: str, task_description: str, 
                           repo_path: Path, workspace_path: Optional[Path] = None):
    """
    Build specialized context before spawning agent in OpenClaw.
    
    Writes context to workspace file (not injected via context_file parameter,
    since OpenClaw doesn't support that). Use sessions_send to point agent to file.
    """
    sys.path.append(str(repo_path / "scripts" / "broker"))
    from context_hydrator import ContextHydrator
    
    # Use workspace path if provided, otherwise use repo_path
    base_path = workspace_path or repo_path
    hydrator = ContextHydrator(base_path)
    
    # Load agent profile to get requirements
    profile_file = repo_path / "openclaw" / "agent_profiles.json"
    requirements = {}
    
    if profile_file.exists():
        with open(profile_file, 'r', encoding='utf-8') as f:
            profiles = json.load(f)
            agent_profile = profiles.get("profiles", {}).get(agent_role, {})
            context_config = agent_profile.get("context_builder", {})
            requirements = context_config.get("requirements", {})
    
    # Build specialized context
    context_file = hydrator.build_specialized_context(
        agent_id=agent_id,
        task_description=task_description,
        agent_role=agent_role,
        existing_context={
            "repo_map": str(base_path / "ai/context/REPO_MAP.md"),
            "context_pack": str(base_path / "ai/context/CONTEXT_PACK.md")
        }
    )
    
    return context_file

if __name__ == "__main__":
    # CLI interface
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenClaw context builder hook")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--agent-role", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--repo", default=".")
    
    args = parser.parse_args()
    
    repo_path = Path(args.repo).resolve()
    context_file = build_context_for_agent(
        args.agent_id,
        args.agent_role,
        args.task,
        repo_path
    )
    
    print(context_file)
