#!/usr/bin/env python3
"""
OpenClaw Skill Wrapper for Harness Tool Broker
Exposes tool broker functionality as OpenClaw skill commands (non-MCP integration)
"""

import json
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

# Path to tool broker script
BROKER_SCRIPT = Path(__file__).parent.parent / "scripts" / "broker" / "tool_broker.py"

def run_broker_command(command: str, **kwargs) -> Dict[str, Any]:
    """Run tool broker command and return JSON result"""
    try:
        # Build command
        cmd = ["python3", str(BROKER_SCRIPT), command]
        
        # Add arguments based on command
        if command == "search":
            if "query" in kwargs:
                cmd.extend(["--query", kwargs["query"]])
            if "max_results" in kwargs:
                cmd.extend(["--max-results", str(kwargs["max_results"])])
            if "agent_id" in kwargs:
                cmd.extend(["--agent-id", kwargs["agent_id"]])
        
        elif command == "describe":
            if "tool_id" in kwargs:
                cmd.extend(["--tool-id", kwargs["tool_id"]])
            if "agent_id" in kwargs:
                cmd.extend(["--agent-id", kwargs["agent_id"]])
        
        elif command == "call":
            if "tool_id" in kwargs:
                cmd.extend(["--tool-id", kwargs["tool_id"]])
            if "args" in kwargs:
                cmd.extend(["--args", json.dumps(kwargs["args"])])
            if "agent_id" in kwargs:
                cmd.extend(["--agent-id", kwargs["agent_id"]])
        
        elif command == "load":
            if "tool_ids" in kwargs:
                tool_ids_str = ",".join(kwargs["tool_ids"])
                cmd.extend(["--tool-ids", tool_ids_str])
            if "agent_id" in kwargs:
                cmd.extend(["--agent-id", kwargs["agent_id"]])
        
        # Execute
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return {
                "error": result.stderr or "Command failed",
                "exit_code": result.returncode
            }
        
        # Parse JSON output
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {
                "error": "Invalid JSON response",
                "output": result.stdout
            }
    
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out"}
    except Exception as e:
        return {"error": str(e)}


def handle_skill_command(command: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle OpenClaw skill command"""
    
    if command == "harness_search_tools":
        return run_broker_command(
            "search",
            query=args.get("query", ""),
            max_results=args.get("max_results", 10),
            agent_id=args.get("agent_id")
        )
    
    elif command == "harness_describe_tool":
        if "tool_id" not in args:
            return {"error": "tool_id required"}
        return run_broker_command(
            "describe",
            tool_id=args["tool_id"],
            agent_id=args.get("agent_id")
        )
    
    elif command == "harness_call_tool":
        if "tool_id" not in args or "args" not in args:
            return {"error": "tool_id and args required"}
        return run_broker_command(
            "call",
            tool_id=args["tool_id"],
            args=args["args"],
            agent_id=args.get("agent_id")
        )
    
    elif command == "harness_load_tools":
        if "tool_ids" not in args:
            return {"error": "tool_ids required"}
        return run_broker_command(
            "load",
            tool_ids=args["tool_ids"],
            agent_id=args.get("agent_id")
        )
    
    else:
        return {"error": f"Unknown command: {command}"}


def main():
    """CLI entry point for OpenClaw skill"""
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: harness_skill_wrapper.py <command> [args_json]"}))
        sys.exit(1)
    
    command = sys.argv[1]
    args = {}
    
    if len(sys.argv) > 2:
        try:
            args = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON args"}))
            sys.exit(1)
    
    result = handle_skill_command(command, args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
