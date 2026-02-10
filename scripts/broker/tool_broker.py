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

class ToolBroker:
    """Main tool broker implementation"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.discovery = ToolDiscovery()
        self.allowlist_manager = AllowlistManager()
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
        
        Returns tool result
        """
        # Check allowlist
        if agent_id and not self.allowlist_manager.is_tool_allowed(agent_id, tool_id):
            return {
                "error": "Tool not allowed for this agent",
                "tool_id": tool_id
            }
        
        # Get tool schema to determine server
        schema = self.describe_tool(tool_id, agent_id)
        if not schema:
            return {
                "error": "Tool not found",
                "tool_id": tool_id
            }
        
        # Extract server from tool_id
        server_name = tool_id.split(":")[0] if ":" in tool_id else "unknown"
        
        # In production, this would make actual MCP call
        # For now, return placeholder
        return {
            "tool_id": tool_id,
            "server": server_name,
            "args": args,
            "result": "Tool call would be executed here via MCP client",
            "note": "Implement actual MCP client integration"
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
