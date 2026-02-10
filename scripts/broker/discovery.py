#!/usr/bin/env python3
"""
Tool Discovery Module
Discovers available MCP tools from configured servers
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
import subprocess

class ToolDiscovery:
    """Discovers tools from MCP servers"""
    
    def __init__(self, mcp_config_path: Optional[Path] = None):
        self.mcp_config_path = mcp_config_path or self._find_mcp_config()
        self.tools_cache: Dict[str, List[Dict]] = {}
    
    def _find_mcp_config(self) -> Optional[Path]:
        """Find MCP configuration file"""
        # Check common locations
        config_locations = [
            Path.home() / ".cursor" / "User" / "settings.json",
            Path.home() / ".config" / "cursor" / "settings.json",
            Path.cwd() / ".cursor" / "mcp.json",
        ]
        
        for loc in config_locations:
            if loc.exists():
                return loc
        
        return None
    
    def discover_tools_from_mcp_servers(self) -> Dict[str, List[Dict]]:
        """Discover all tools from configured MCP servers"""
        if not self.mcp_config_path or not self.mcp_config_path.exists():
            return {}
        
        try:
            with open(self.mcp_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"Error reading MCP config: {e}")
            return {}
        
        mcp_servers = config.get("mcp", {}).get("servers", {})
        if not mcp_servers:
            mcp_servers = config.get("mcp.servers", {})
        
        all_tools = {}
        
        for server_name, server_config in mcp_servers.items():
            tools = self._list_tools_from_server(server_name, server_config)
            if tools:
                all_tools[server_name] = tools
        
        self.tools_cache = all_tools
        return all_tools
    
    def _list_tools_from_server(self, server_name: str, server_config: Dict) -> List[Dict]:
        """List tools from a specific MCP server"""
        # Try to use MCP SDK if available
        try:
            # This would use actual MCP client in production
            # For now, return empty list - will be implemented with actual MCP client
            return []
        except Exception as e:
            print(f"Error listing tools from {server_name}: {e}")
            return []
    
    def search_tools(self, query: str, tags: Optional[List[str]] = None, 
                    allow_servers: Optional[List[str]] = None,
                    max_results: int = 10) -> List[Dict]:
        """Search for tools matching query"""
        if not self.tools_cache:
            self.discover_tools_from_mcp_servers()
        
        results = []
        query_lower = query.lower()
        
        for server_name, tools in self.tools_cache.items():
            if allow_servers and server_name not in allow_servers:
                continue
            
            for tool in tools:
                tool_name = tool.get("name", "").lower()
                tool_desc = tool.get("description", "").lower()
                
                if query_lower in tool_name or query_lower in tool_desc:
                    results.append({
                        "tool_id": f"{server_name}:{tool.get('name', '')}",
                        "name": tool.get("name", ""),
                        "short_desc": tool.get("description", "")[:100],
                        "server": server_name,
                        "confidence": self._calculate_confidence(query, tool),
                        "schema": tool
                    })
        
        # Sort by confidence
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results[:max_results]
    
    def _calculate_confidence(self, query: str, tool: Dict) -> float:
        """Calculate confidence score for tool match"""
        query_lower = query.lower()
        tool_name = tool.get("name", "").lower()
        tool_desc = tool.get("description", "").lower()
        
        confidence = 0.0
        
        # Exact name match
        if query_lower == tool_name:
            confidence += 1.0
        # Name contains query
        elif query_lower in tool_name:
            confidence += 0.8
        # Description contains query
        elif query_lower in tool_desc:
            confidence += 0.5
        
        return confidence
    
    def get_tool_schema(self, tool_id: str) -> Optional[Dict]:
        """Get full schema for a specific tool"""
        server_name, tool_name = tool_id.split(":", 1) if ":" in tool_id else (None, tool_id)
        
        if not self.tools_cache:
            self.discover_tools_from_mcp_servers()
        
        if server_name and server_name in self.tools_cache:
            for tool in self.tools_cache[server_name]:
                if tool.get("name") == tool_name:
                    return tool
        
        # Search all servers
        for tools in self.tools_cache.values():
            for tool in tools:
                if tool.get("name") == tool_name:
                    return tool
        
        return None
