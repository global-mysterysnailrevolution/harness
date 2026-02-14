#!/usr/bin/env python3
"""
MCP Tool Broker
Provides unified tool access with discovery, allowlisting, and on-demand hydration.
Includes Gate B runtime policy: action classification, dangerous action gate, audit log.
"""

import json
import argparse
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import sys
sys.path.insert(0, str(Path(__file__).parent))

from discovery import ToolDiscovery
from allowlist_manager import AllowlistManager
from security_policy import SecurityPolicy
from forge_approval import ForgeApproval

# ---------------------------------------------------------------------------
# Action classification
# ---------------------------------------------------------------------------

# tool_id patterns -> action class
_ACTION_PATTERNS: Dict[str, List[str]] = {
    "read": ["search", "list", "get", "describe", "read", "query", "fetch", "find"],
    "write": ["write", "create", "update", "delete", "put", "patch", "remove", "move", "rename"],
    "network": ["http", "curl", "fetch", "request", "download", "upload", "send", "post"],
    "credential": ["auth", "token", "secret", "key", "password", "credential", "login", "oauth"],
    "exec": ["exec", "run", "shell", "command", "spawn", "evaluate", "interpret", "compile"],
}

# Actions that require interactive approval (configurable in security_policy.json)
_DANGEROUS_ACTIONS = {"exec", "credential", "network"}


def classify_action(tool_id: str, args: Dict[str, Any]) -> str:
    """Classify a tool call into an action category."""
    combined = f"{tool_id} {json.dumps(args)}".lower()
    scores: Dict[str, int] = {}
    for action_class, keywords in _ACTION_PATTERNS.items():
        scores[action_class] = sum(1 for kw in keywords if kw in combined)
    if not any(scores.values()):
        return "read"  # default safe
    return max(scores, key=lambda k: scores[k])


# ---------------------------------------------------------------------------
# Audit logger
# ---------------------------------------------------------------------------

_AUDIT_LOG_PATH = Path(os.environ.get("HARNESS_DIR", Path.cwd())) / "ai" / "supervisor" / "audit_log.jsonl"


def _audit_log(entry: Dict[str, Any]):
    """Append a structured entry to the audit log (JSONL)."""
    _AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry["timestamp"] = datetime.now().isoformat()
    with open(_AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class ToolBroker:
    """Main tool broker implementation"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.discovery = ToolDiscovery()
        self.allowlist_manager = AllowlistManager()
        self.security_policy = SecurityPolicy()
        self.forge_approval = ForgeApproval()
        self.tool_schemas_cache: Dict[str, Dict] = {}
        self.config_path = config_path
    
    def search_tools(self, query: str, tags: Optional[List[str]] = None,
                    allow_servers: Optional[List[str]] = None,
                    max_results: int = 10,
                    agent_id: Optional[str] = None) -> List[Dict]:
        """
        Search for tools matching query
        
        Returns list of tool metadata (not full schemas to save tokens)
        """
        # Discover tools if not cached
        if not self.discovery.tools_cache:
            self.discovery.discover_tools_from_mcp_servers()
        
        # Apply server allowlist if agent specified
        if agent_id:
            agent_servers = self.allowlist_manager.get_allowed_servers(agent_id)
            if agent_servers:
                allow_servers = agent_servers
        
        # Search tools
        results = self.discovery.search_tools(
            query=query,
            tags=tags,
            allow_servers=allow_servers,
            max_results=max_results
        )
        
        # Filter by agent allowlist
        if agent_id:
            results = self.allowlist_manager.filter_tools_by_allowlist(agent_id, results)
        
        # Return lightweight metadata (no full schemas)
        return [{
            "tool_id": r["tool_id"],
            "name": r["name"],
            "short_desc": r["short_desc"],
            "server": r["server"],
            "confidence": r["confidence"]
        } for r in results]
    
    def describe_tool(self, tool_id: str, agent_id: Optional[str] = None) -> Optional[Dict]:
        """
        Get full schema and description for a tool
        
        Returns full tool schema with examples
        """
        # Check allowlist
        if agent_id and not self.allowlist_manager.is_tool_allowed(agent_id, tool_id):
            return None
        
        # Check cache first
        if tool_id in self.tool_schemas_cache:
            return self.tool_schemas_cache[tool_id]
        
        # Get from discovery
        schema = self.discovery.get_tool_schema(tool_id)
        if schema:
            self.tool_schemas_cache[tool_id] = schema
        
        return schema
    
    def call_tool(self, tool_id: str, args: Dict[str, Any],
                  agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Call a tool via proxy (avoids schema injection).
        
        Gate B runtime policy:
          1. Allowlist check
          2. Action classification (read/write/network/credential/exec)
          3. Dangerous action gate (requires approval for exec/credential/network)
          4. Security policy checks (rate limit, argument validation, budget)
          5. Route: MCPJungle -> ToolHive -> direct MCP (first available)
          6. Audit log every call
        
        Returns tool result (with secrets redacted).
        """
        aid = agent_id or "default"
        action_class = classify_action(tool_id, args)
        args_hash = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()[:12]

        # --- 1. Allowlist ---
        if agent_id and not self.allowlist_manager.is_tool_allowed(agent_id, tool_id):
            security_config = Path("ai/supervisor/security_policy.json")
            approval_required = True
            if security_config.exists():
                try:
                    with open(security_config, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        approval_required = config.get("tool_approval_required", True)
                except Exception:
                    pass
            
            if approval_required:
                _audit_log({"event": "call_blocked", "reason": "allowlist", "tool_id": tool_id,
                            "agent_id": aid, "action_class": action_class})
                return self.allowlist_manager.request_approval(agent_id, tool_id, args)
            else:
                _audit_log({"event": "call_blocked", "reason": "allowlist_no_approval", "tool_id": tool_id,
                            "agent_id": aid, "action_class": action_class})
                return {"error": "Tool not allowed for this agent", "tool_id": tool_id}

        # --- 2. Dangerous action gate ---
        dangerous_actions = _DANGEROUS_ACTIONS
        # Load overrides from security_policy if available
        try:
            sp = Path("ai/supervisor/security_policy.json")
            if sp.exists():
                sp_data = json.loads(sp.read_text(encoding="utf-8"))
                custom = sp_data.get("dangerous_action_classes")
                if custom:
                    dangerous_actions = set(custom)
        except Exception:
            pass

        if action_class in dangerous_actions:
            _audit_log({"event": "dangerous_action", "tool_id": tool_id, "agent_id": aid,
                        "action_class": action_class, "args_hash": args_hash})
            # In interactive mode this would prompt; for now, log and continue.
            # Future: integrate with approval workflow for blocking.

        # --- 3. Security policy checks ---
        allowed, error = self.security_policy.check_rate_limit(aid, tool_id)
        if not allowed:
            _audit_log({"event": "call_blocked", "reason": "rate_limit", "tool_id": tool_id, "agent_id": aid})
            return {"error": error, "tool_id": tool_id}
        
        allowed, error = self.security_policy.validate_arguments(tool_id, args, aid)
        if not allowed:
            _audit_log({"event": "call_blocked", "reason": "argument_validation", "tool_id": tool_id,
                        "agent_id": aid, "detail": error})
            return {"error": error, "tool_id": tool_id}
        
        allowed, error = self.security_policy.check_budget(aid, {"tokens": 0, "cost_usd": 0})
        if not allowed:
            _audit_log({"event": "call_blocked", "reason": "budget", "tool_id": tool_id, "agent_id": aid})
            return {"error": error, "tool_id": tool_id}
        
        # --- 4. Resolve tool schema ---
        schema = self.describe_tool(tool_id, agent_id)
        if not schema:
            return {"error": "Tool not found", "tool_id": tool_id}
        
        server_name = tool_id.split(":")[0] if ":" in tool_id else "unknown"

        # --- 5. Route call: MCPJungle -> ToolHive -> direct MCP ---
        result_dict = self._route_call(tool_id, args, agent_id, server_name)

        # --- 6. Audit log ---
        _audit_log({
            "event": "call_tool",
            "tool_id": tool_id,
            "agent_id": aid,
            "action_class": action_class,
            "args_hash": args_hash,
            "server": server_name,
            "status": "error" if "error" in result_dict else "ok",
        })
        
        return result_dict

    def _route_call(self, tool_id: str, args: Dict, agent_id: Optional[str], server_name: str) -> Dict:
        """Try gateways in order: MCPJungle -> ToolHive -> direct MCP."""

        # --- MCPJungle gateway ---
        mcpjungle_url = os.getenv("MCPJUNGLE_GATEWAY_URL")
        if mcpjungle_url:
            try:
                import requests
                response = requests.post(
                    f"{mcpjungle_url}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {"name": tool_id, "arguments": args},
                        "id": 1,
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                if response.status_code == 200:
                    return self._redact({"tool_id": tool_id, "server": server_name,
                                         "result": response.json(), "gateway": "mcpjungle"})
            except Exception as e:
                print(f"MCPJungle call failed: {e}, trying next gateway")

        # --- ToolHive gateway ---
        toolhive_gateway = os.getenv("TOOLHIVE_GATEWAY_URL")
        if toolhive_gateway:
            try:
                import requests
                response = requests.post(
                    f"{toolhive_gateway}/api/tools/call",
                    json={"tool_id": tool_id, "args": args, "agent_id": agent_id},
                    timeout=30,
                )
                if response.status_code == 200:
                    return self._redact({"tool_id": tool_id, "server": server_name,
                                         "result": response.json(), "gateway": "toolhive"})
            except Exception as e:
                print(f"ToolHive call failed: {e}, falling back to direct MCP")

        # --- Direct MCP ---
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            server_config = self.discovery._get_server_config(server_name)
            if not server_config:
                return {"error": "Server config not found", "server": server_name}

            command = server_config.get("command")
            if not command:
                return {"error": "Server command not configured", "server": server_name}

            server_params = StdioServerParameters(
                command=command,
                args=server_config.get("args", []),
                env=server_config.get("env", {}),
            )

            async def _call():
                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        name = tool_id.split(":")[1] if ":" in tool_id else tool_id
                        result = await session.call_tool(name, args)
                        return result.content[0].text if result.content else result

            import asyncio
            result = asyncio.run(_call())
            return self._redact({"tool_id": tool_id, "server": server_name,
                                 "result": result, "gateway": "direct_mcp"})
        except ImportError:
            return {"error": "MCP SDK not installed. Install with: pip install mcp",
                    "tool_id": tool_id, "note": "MCPJungle or ToolHive gateway recommended"}
        except Exception as e:
            return {"error": f"MCP call failed: {str(e)}",
                    "tool_id": tool_id, "server": server_name}

    def _redact(self, result: Dict) -> Dict:
        """Redact secrets from result before returning."""
        if self.security_policy:
            result_str = json.dumps(result)
            result_str = self.security_policy.redact_secrets(result_str)
            return json.loads(result_str)
        return result
    
    def load_tools(self, tool_ids: List[str], agent_id: Optional[str] = None) -> List[Dict]:
        """
        Load full tool schemas for direct tool calling
        
        Returns list of full MCP tool definitions
        """
        tools = []
        
        for tool_id in tool_ids:
            # Check allowlist
            if agent_id and not self.allowlist_manager.is_tool_allowed(agent_id, tool_id):
                continue
            
            schema = self.describe_tool(tool_id, agent_id)
            if schema:
                tools.append(schema)
        
        return tools

def main():
    """CLI interface for tool broker"""
    parser = argparse.ArgumentParser(description="MCP Tool Broker")
    parser.add_argument("command", choices=[
        "search", "describe", "call", "load",
        "pending", "approve", "reject",
        "propose", "vet",
    ], help="Command to execute")
    parser.add_argument("--query", help="Search query (for search command)")
    parser.add_argument("--tool-id", help="Tool ID (for describe/call/load commands)")
    parser.add_argument("--args", help="Tool arguments as JSON (for call command)")
    parser.add_argument("--tool-ids", help="Comma-separated tool IDs (for load command)")
    parser.add_argument("--agent-id", help="Agent ID for allowlist filtering")
    parser.add_argument("--max-results", type=int, default=10, help="Max results for search")
    parser.add_argument("--reason", help="Rejection reason (for reject command)")
    parser.add_argument("--server-name", help="Server name (for propose command)")
    parser.add_argument("--source", help="Source type: docker_image, github_repo, npm_package, openapi")
    parser.add_argument("--source-id", help="Source identifier (image, URL, package name)")
    parser.add_argument("--source-path", help="Local path to source code (for propose/vet)")
    parser.add_argument("--proposal-id", help="Proposal ID (for vet command)")
    parser.add_argument("--override-vetting", action="store_true", help="Override vetting gate on approve")
    
    args = parser.parse_args()
    
    broker = ToolBroker()
    
    if args.command == "search":
        if not args.query:
            print("Error: --query required for search command")
            return
        
        results = broker.search_tools(
            query=args.query,
            max_results=args.max_results,
            agent_id=args.agent_id
        )
        print(json.dumps(results, indent=2))
    
    elif args.command == "describe":
        if not args.tool_id:
            print("Error: --tool-id required for describe command")
            return
        
        schema = broker.describe_tool(args.tool_id, args.agent_id)
        if schema:
            print(json.dumps(schema, indent=2))
        else:
            print(f"Tool not found: {args.tool_id}")
    
    elif args.command == "call":
        if not args.tool_id:
            print("Error: --tool-id required for call command")
            return
        
        tool_args = {}
        if args.args:
            tool_args = json.loads(args.args)
        
        result = broker.call_tool(args.tool_id, tool_args, args.agent_id)
        print(json.dumps(result, indent=2))
    
    elif args.command == "load":
        if not args.tool_ids:
            print("Error: --tool-ids required for load command")
            return
        
        tool_ids = [tid.strip() for tid in args.tool_ids.split(",")]
        tools = broker.load_tools(tool_ids, args.agent_id)
        print(json.dumps(tools, indent=2))
    
    elif args.command == "pending":
        pending = broker.allowlist_manager.get_pending_approvals()
        if pending:
            print(json.dumps(pending, indent=2))
        else:
            print(json.dumps([], indent=2))
    
    elif args.command == "approve":
        if not args.tool_id:
            print("Error: --tool-id (used as request-id/proposal-id) required for approve command")
            return
        
        # Try forge approval first (for proposals), then allowlist approval
        result = broker.forge_approval.approve(
            args.tool_id, approved_by=args.agent_id or "cli",
            override_vetting=args.override_vetting,
        )
        if result.get("ok"):
            print(json.dumps(result, indent=2))
        else:
            # Fallback to allowlist approval
            success = broker.allowlist_manager.approve_request(args.tool_id)
            if success:
                print(json.dumps({"status": "approved", "request_id": args.tool_id}, indent=2))
            else:
                print(json.dumps(result, indent=2))
    
    elif args.command == "reject":
        if not args.tool_id:
            print("Error: --tool-id (used as request-id/proposal-id) required for reject command")
            return
        
        reason = args.reason or "Rejected by user"
        # Try forge rejection first, then allowlist
        success = broker.forge_approval.reject(args.tool_id, rejected_by=args.agent_id or "cli", reason=reason)
        if not success:
            success = broker.allowlist_manager.reject_request(args.tool_id, reason)
        
        if success:
            print(json.dumps({"status": "rejected", "request_id": args.tool_id, "reason": reason}, indent=2))
        else:
            print(json.dumps({"error": "Request not found or already processed", "request_id": args.tool_id}, indent=2))
    
    elif args.command == "propose":
        if not args.server_name or not args.source or not args.source_id:
            print("Error: --server-name, --source, --source-id required for propose command")
            return
        proposal = broker.forge_approval.propose_server(
            server_name=args.server_name,
            source=args.source,
            source_id=args.source_id,
            proposed_by=args.agent_id or "cli",
            source_path=args.source_path,
        )
        print(json.dumps(proposal, indent=2))
    
    elif args.command == "vet":
        pid = args.proposal_id or args.tool_id
        if not pid:
            print("Error: --proposal-id required for vet command")
            return
        result = broker.forge_approval.vet(pid, target=args.source_path)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps({"error": "Vetting failed or engine not available"}, indent=2))

if __name__ == "__main__":
    main()
