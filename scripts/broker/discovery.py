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
        # Priority order: harness-native registry first (VPS-friendly)
        config_locations = [
            # Harness-native registry (VPS-friendly, not Cursor-dependent)
            Path.cwd() / "ai" / "supervisor" / "mcp.servers.json",
            # Cursor configs (fallback for local development)
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
        # Discovery order (as per mcp.servers.json config):
        # 1. ToolHive gateway (if configured)
        # 2. Harness-native mcp.servers.json (VPS-friendly)
        # 3. Cursor configs (fallback for local dev)
        # 4. Tool registry cache
        
        # Method 1: Try ToolHive gateway first if configured
        toolhive_gateway = os.getenv("TOOLHIVE_GATEWAY_URL")
        if toolhive_gateway:
            try:
                import requests
                response = requests.get(
                    f"{toolhive_gateway}/api/tools",
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    # ToolHive returns tools grouped by server
                    all_tools = {}
                    for server_name, tools in data.get("servers", {}).items():
                        all_tools[server_name] = tools.get("tools", [])
                    self.tools_cache = all_tools
                    return all_tools
            except Exception as e:
                print(f"ToolHive gateway discovery failed: {e}, falling back to direct MCP")
        
        # Method 2: Harness-native mcp.servers.json (VPS-friendly)
        harness_registry = Path.cwd() / "ai" / "supervisor" / "mcp.servers.json"
        if harness_registry.exists():
            try:
                with open(harness_registry, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                mcp_servers = config.get("servers", {})
                all_tools = {}
                
                for server_name, server_config in mcp_servers.items():
                    # Skip disabled servers
                    if not server_config.get("enabled", True):
                        continue
                    
                    tools = self._list_tools_from_server(server_name, server_config)
                    if tools:
                        all_tools[server_name] = tools
                
                if all_tools:
                    self.tools_cache = all_tools
                    return all_tools
            except Exception as e:
                print(f"Error reading harness registry: {e}")
        
        # Method 3: Fallback to Cursor configs (for local development)
        if self.mcp_config_path and self.mcp_config_path.exists():
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
            
            if all_tools:
                self.tools_cache = all_tools
                return all_tools
        
        # Method 4: Check tool registry cache
        try:
            cache_path = Path.cwd() / "ai" / "supervisor" / "tool_registry.json"
            if cache_path.exists():
                with open(cache_path, 'r', encoding='utf-8') as f:
                    registry = json.load(f)
                    if registry.get("servers"):
                        self.tools_cache = registry["servers"]
                        return registry["servers"]
        except Exception as e:
            print(f"Cache lookup failed: {e}")
        
        # No tools discovered
        return {}
    
    def _get_server_config(self, server_name: str) -> Optional[Dict]:
        """Get server configuration by name"""
        if not self.mcp_config_path or not self.mcp_config_path.exists():
            return None
        
        try:
            with open(self.mcp_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            mcp_servers = config.get("mcp", {}).get("servers", {})
            if not mcp_servers:
                mcp_servers = config.get("mcp.servers", {})
            
            return mcp_servers.get(server_name)
        except Exception:
            return None
    
    def _list_tools_from_server(self, server_name: str, server_config: Dict) -> List[Dict]:
        """List tools from a specific MCP server"""
        # Try multiple methods to discover tools
        
        # Method 1: Use MCP SDK if available
        try:
            import mcp
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            
            # Extract command and args from config
            command = server_config.get("command")
            args = server_config.get("args", [])
            env = server_config.get("env", {})
            
            if command:
                # Create server parameters
                server_params = StdioServerParameters(
                    command=command,
                    args=args or [],
                    env=env or {}
                )
                
                # Connect and list tools
                async def _get_tools():
                    async with stdio_client(server_params) as (read, write):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            result = await session.list_tools()
                            return result.tools
                
                # Run async function
                import asyncio
                tools = asyncio.run(_get_tools())
                return [tool.model_dump() if hasattr(tool, 'model_dump') else dict(tool) for tool in tools]
        except ImportError:
            # MCP SDK not available, try alternative methods
            pass
        except Exception as e:
            print(f"MCP SDK method failed for {server_name}: {e}")
        
        # Method 2: Try ToolHive gateway if configured
        try:
            toolhive_gateway = server_config.get("toolhive_gateway")
            if toolhive_gateway:
                import requests
                response = requests.get(
                    f"{toolhive_gateway}/api/tools",
                    params={"server": server_name},
                    timeout=5
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("tools", [])
        except Exception as e:
            print(f"ToolHive gateway method failed for {server_name}: {e}")
        
        # Method 3: Try MCP stdio via subprocess (fallback)
        try:
            command = server_config.get("command")
            if command:
                # Use npx @modelcontextprotocol/cli if available
                import shutil
                if shutil.which("npx"):
                    result = subprocess.run(
                        ["npx", "-y", "@modelcontextprotocol/cli", "list-tools", "--server", command],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        import json
                        return json.loads(result.stdout)
        except Exception as e:
            print(f"Subprocess method failed for {server_name}: {e}")
        
        # Method 4: Check for cached tool registry
        try:
            cache_path = Path.cwd() / "ai" / "supervisor" / "tool_registry.json"
            if cache_path.exists():
                with open(cache_path, 'r', encoding='utf-8') as f:
                    registry = json.load(f)
                    if server_name in registry:
                        return registry[server_name].get("tools", [])
        except Exception as e:
            print(f"Cache lookup failed for {server_name}: {e}")
        
        # Return empty if all methods fail
        print(f"Warning: Could not discover tools from {server_name}. Install MCP SDK: pip install mcp")
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
