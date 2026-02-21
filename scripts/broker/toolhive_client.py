#!/usr/bin/env python3
"""
ToolHive Client Adapter
Provides robust client for ToolHive gateway with endpoint discovery
"""

import os
import json
from typing import Dict, List, Optional, Any
from pathlib import Path

class ToolHiveClient:
    """Client for interacting with ToolHive gateway"""
    
    def __init__(self, gateway_url: Optional[str] = None):
        self.gateway_url = gateway_url or os.getenv("TOOLHIVE_GATEWAY_URL")
        self.endpoints: Dict[str, str] = {}
        self._discover_endpoints()
    
    def _discover_endpoints(self):
        """Discover available ToolHive endpoints"""
        if not self.gateway_url:
            return
        
        # Try common endpoints from TOOLHIVE_INTEGRATION.md
        common_endpoints = [
            ("health", "/health"),
            ("servers", "/api/servers"),
            ("tools", "/api/tools"),
            ("openapi", "/openapi.json"),
        ]
        
        try:
            import requests
            
            for name, path in common_endpoints:
                try:
                    url = f"{self.gateway_url.rstrip('/')}{path}"
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        self.endpoints[name] = path
                        print(f"Discovered ToolHive endpoint: {name} -> {path}")
                except Exception:
                    pass
            
            # If openapi.json exists, parse it for all available endpoints
            if "openapi" in self.endpoints:
                try:
                    url = f"{self.gateway_url.rstrip('/')}/openapi.json"
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        openapi = response.json()
                        paths = openapi.get("paths", {})
                        print(f"ToolHive OpenAPI has {len(paths)} endpoints:")
                        for path in list(paths.keys())[:10]:  # Print first 10
                            print(f"  {path}")
                except Exception as e:
                    print(f"Failed to parse OpenAPI: {e}")
        except ImportError:
            print("Warning: requests not installed. Install with: pip install requests")
        except Exception as e:
            print(f"ToolHive endpoint discovery failed: {e}")
    
    def is_available(self) -> bool:
        """Check if ToolHive is available"""
        if not self.gateway_url:
            return False
        
        return "health" in self.endpoints
    
    def list_servers(self) -> List[Dict]:
        """List registered MCP servers"""
        if "servers" not in self.endpoints:
            print("Warning: /api/servers endpoint not available")
            return []
        
        try:
            import requests
            url = f"{self.gateway_url.rstrip('/')}{self.endpoints['servers']}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Handle different response formats
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get("servers", [])
                return []
            else:
                print(f"ToolHive list_servers returned {response.status_code}")
                return []
        except Exception as e:
            print(f"Failed to list ToolHive servers: {e}")
            return []
    
    def list_tools(self, server_name: Optional[str] = None) -> List[Dict]:
        """List tools from ToolHive (optionally filtered by server)"""
        if "tools" not in self.endpoints:
            print("Warning: /api/tools endpoint not available")
            return []
        
        try:
            import requests
            url = f"{self.gateway_url.rstrip('/')}{self.endpoints['tools']}"
            params = {}
            if server_name:
                params["server"] = server_name
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Handle different response formats
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    # ToolHive might return {servers: {server_name: {tools: [...]}}}
                    if "servers" in data:
                        all_tools = []
                        for server, server_data in data["servers"].items():
                            if server_name and server != server_name:
                                continue
                            tools = server_data.get("tools", [])
                            # Add server prefix to tool IDs
                            for tool in tools:
                                tool["tool_id"] = f"{server}:{tool.get('name', '')}"
                            all_tools.extend(tools)
                        return all_tools
                    return data.get("tools", [])
                return []
            else:
                print(f"ToolHive list_tools returned {response.status_code}")
                return []
        except Exception as e:
            print(f"Failed to list ToolHive tools: {e}")
            return []
    
    def call_tool(self, tool_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool via ToolHive"""
        if "tools" not in self.endpoints:
            return {"error": "ToolHive tools endpoint not available"}
        
        try:
            import requests
            # Try /api/tools/call or /api/call
            call_endpoints = ["/api/tools/call", "/api/call", "/call"]
            
            for endpoint in call_endpoints:
                try:
                    url = f"{self.gateway_url.rstrip('/')}{endpoint}"
                    payload = {
                        "tool_id": tool_id,
                        "args": args
                    }
                    response = requests.post(url, json=payload, timeout=30)
                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 404:
                        continue  # Try next endpoint
                    else:
                        return {"error": f"ToolHive call returned {response.status_code}", "details": response.text}
                except requests.exceptions.RequestException:
                    continue
            
            return {"error": "No working ToolHive call endpoint found"}
        except Exception as e:
            return {"error": f"Failed to call tool via ToolHive: {e}"}
    
    def register_server(self, name: str, command: str, args: List[str], env: Optional[Dict] = None) -> bool:
        """Register a new MCP server with ToolHive"""
        if "servers" not in self.endpoints:
            print("Warning: /api/servers endpoint not available for registration")
            return False
        
        try:
            import requests
            url = f"{self.gateway_url.rstrip('/')}{self.endpoints['servers']}"
            payload = {
                "name": name,
                "command": command,
                "args": args or [],
                "env": env or {}
            }
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code in [200, 201]:
                print(f"Successfully registered MCP server: {name}")
                return True
            else:
                print(f"Failed to register server: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Failed to register ToolHive server: {e}")
            return False
