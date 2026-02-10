#!/usr/bin/env python3
"""
Allowlist Manager
Manages per-agent tool allowlists for security and token reduction
"""

import json
from pathlib import Path
from typing import Dict, List, Set, Optional

class AllowlistManager:
    """Manages tool allowlists per agent"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("ai/supervisor/allowlists.json")
        self.allowlists: Dict[str, Dict] = {}
        self.load_allowlists()
    
    def load_allowlists(self):
        """Load allowlists from config file"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.allowlists = json.load(f)
            except Exception as e:
                print(f"Error loading allowlists: {e}")
                self.allowlists = {}
        else:
            # Create default structure
            self.allowlists = {
                "default": {
                    "allow": [],
                    "deny": [],
                    "servers": []
                }
            }
            self.save_allowlists()
    
    def save_allowlists(self):
        """Save allowlists to config file"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.allowlists, f, indent=2)
    
    def get_allowed_tools(self, agent_id: str) -> Set[str]:
        """Get set of allowed tool IDs for an agent"""
        agent_config = self.allowlists.get(agent_id, {})
        default_config = self.allowlists.get("default", {})
        
        # Merge agent-specific and default configs
        allowed = set(agent_config.get("allow", []) + default_config.get("allow", []))
        denied = set(agent_config.get("deny", []) + default_config.get("deny", []))
        
        # Deny takes precedence
        allowed -= denied
        
        return allowed
    
    def get_allowed_servers(self, agent_id: str) -> List[str]:
        """Get list of allowed MCP servers for an agent"""
        agent_config = self.allowlists.get(agent_id, {})
        default_config = self.allowlists.get("default", {})
        
        agent_servers = agent_config.get("servers", [])
        default_servers = default_config.get("servers", [])
        
        # If agent has explicit servers, use those; otherwise use default
        if agent_servers:
            return agent_servers
        return default_servers
    
    def is_tool_allowed(self, agent_id: str, tool_id: str) -> bool:
        """Check if a tool is allowed for an agent"""
        allowed_tools = self.get_allowed_tools(agent_id)
        
        # Check exact match
        if tool_id in allowed_tools:
            return True
        
        # Check pattern matches (e.g., "github:*" allows all GitHub tools)
        for pattern in allowed_tools:
            if "*" in pattern:
                prefix = pattern.replace("*", "")
                if tool_id.startswith(prefix):
                    return True
        
        return False
    
    def set_agent_allowlist(self, agent_id: str, allow: List[str], 
                           deny: Optional[List[str]] = None,
                           servers: Optional[List[str]] = None):
        """Set allowlist for a specific agent"""
        if agent_id not in self.allowlists:
            self.allowlists[agent_id] = {}
        
        self.allowlists[agent_id]["allow"] = allow
        if deny is not None:
            self.allowlists[agent_id]["deny"] = deny
        if servers is not None:
            self.allowlists[agent_id]["servers"] = servers
        
        self.save_allowlists()
    
    def filter_tools_by_allowlist(self, agent_id: str, tools: List[Dict]) -> List[Dict]:
        """Filter tools list based on agent allowlist"""
        allowed_tools = self.get_allowed_tools(agent_id)
        allowed_servers = self.get_allowed_servers(agent_id)
        
        filtered = []
        
        for tool in tools:
            tool_id = tool.get("tool_id", "")
            server = tool.get("server", "")
            
            # Check server allowlist
            if allowed_servers and server not in allowed_servers:
                continue
            
            # Check tool allowlist
            if self.is_tool_allowed(agent_id, tool_id):
                filtered.append(tool)
        
        return filtered
