#!/usr/bin/env python3
"""
MCP Tool Broker
Provides unified tool access with discovery, allowlisting, and on-demand hydration
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from discovery import ToolDiscovery
from allowlist_manager import AllowlistManager
from security_policy import SecurityPolicy
from forge_approval import ForgeApproval

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
        Call a tool via proxy (avoids schema injection)
        
        Returns tool result (with secrets redacted)
        """
        # Check allowlist
        if agent_id and not self.allowlist_manager.is_tool_allowed(agent_id, tool_id):
            return {
                "error": "Tool not allowed for this agent",
                "tool_id": tool_id
            }
        
        # Security policy checks
        # 1. Rate limit
        allowed, error = self.security_policy.check_rate_limit(agent_id or "default", tool_id)
        if not allowed:
            return {"error": error, "tool_id": tool_id}
        
        # 2. Argument validation
        allowed, error = self.security_policy.validate_arguments(tool_id, args, agent_id or "default")
        if not allowed:
            return {"error": error, "tool_id": tool_id}
        
        # 3. Budget check
        allowed, error = self.security_policy.check_budget(agent_id or "default", {"tokens": 0, "cost_usd": 0})
        if not allowed:
            return {"error": error, "tool_id": tool_id}
        
        # Get tool schema to determine server
        schema = self.describe_tool(tool_id, agent_id)
        if not schema:
            return {
                "error": "Tool not found",
                "tool_id": tool_id
            }
        
        # Extract server from tool_id
        server_name = tool_id.split(":")[0] if ":" in tool_id else "unknown"
        
        # Try ToolHive gateway first if configured
        toolhive_gateway = os.getenv("TOOLHIVE_GATEWAY_URL")
        if toolhive_gateway:
            try:
                import requests
                response = requests.post(
                    f"{toolhive_gateway}/api/tools/call",
                    json={
                        "tool_id": tool_id,
                        "args": args,
                        "agent_id": agent_id
                    },
                    timeout=30
                )
                if response.status_code == 200:
                    result = response.json()
                    # Redact secrets before returning
                    if self.security_policy:
                        result_str = json.dumps(result)
                        result_str = self.security_policy.redact_secrets(result_str)
                        result = json.loads(result_str)
                    return result
            except Exception as e:
                print(f"ToolHive gateway call failed: {e}, falling back to direct MCP")
        
        # Fallback: Direct MCP client call
        try:
            import mcp
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            
            # Get server config from discovery
            server_config = self.discovery._get_server_config(server_name)
            if not server_config:
                return {
                    "error": "Server config not found",
                    "server": server_name
                }
            
            # Create server parameters
            command = server_config.get("command")
            if not command:
                return {
                    "error": "Server command not configured",
                    "server": server_name
                }
            
            server_params = StdioServerParameters(
                command=command,
                args=server_config.get("args", []),
                env=server_config.get("env", {})
            )
            
            # Call tool via MCP
            async def _call_tool():
                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tool_name = tool_id.split(":")[1] if ":" in tool_id else tool_id
                        result = await session.call_tool(tool_name, args)
                        return result.content[0].text if result.content else result
        
            import asyncio
            result = asyncio.run(_call_tool())
            result_dict = {
                "tool_id": tool_id,
                "server": server_name,
                "result": result
            }
            # Redact secrets before returning
            if self.security_policy:
                result_str = json.dumps(result_dict)
                result_str = self.security_policy.redact_secrets(result_str)
                result_dict = json.loads(result_str)
            return result_dict
        except ImportError:
            return {
                "error": "MCP SDK not installed. Install with: pip install mcp",
                "tool_id": tool_id,
                "note": "ToolHive gateway recommended for production"
            }
        except Exception as e:
            return {
                "error": f"MCP call failed: {str(e)}",
                "tool_id": tool_id,
                "server": server_name
            }
    
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
    parser.add_argument("command", choices=["search", "describe", "call", "load"],
                       help="Command to execute")
    parser.add_argument("--query", help="Search query (for search command)")
    parser.add_argument("--tool-id", help="Tool ID (for describe/call/load commands)")
    parser.add_argument("--args", help="Tool arguments as JSON (for call command)")
    parser.add_argument("--tool-ids", help="Comma-separated tool IDs (for load command)")
    parser.add_argument("--agent-id", help="Agent ID for allowlist filtering")
    parser.add_argument("--max-results", type=int, default=10, help="Max results for search")
    
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

if __name__ == "__main__":
    main()
