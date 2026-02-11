#!/usr/bin/env python3
"""
Allowlist Manager
Manages per-agent tool allowlists for security and token reduction
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Optional
from datetime import datetime

class AllowlistManager:
    """Manages tool allowlists per agent"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("ai/supervisor/allowlists.json")
        self.pending_approvals_path = Path("ai/supervisor/pending_approvals.json")
        self.allowlists: Dict[str, Dict] = {}
        self.pending_approvals: Dict[str, Dict] = {}
        self.load_allowlists()
        self.load_pending_approvals()
    
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
    
    def load_pending_approvals(self):
        """Load pending approval requests"""
        if self.pending_approvals_path.exists():
            try:
                with open(self.pending_approvals_path, 'r', encoding='utf-8') as f:
                    self.pending_approvals = json.load(f)
            except Exception as e:
                print(f"Error loading pending approvals: {e}")
                self.pending_approvals = {}
        else:
            self.pending_approvals = {}
    
    def save_pending_approvals(self):
        """Save pending approval requests"""
        self.pending_approvals_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pending_approvals_path, 'w', encoding='utf-8') as f:
            json.dump(self.pending_approvals, f, indent=2)
    
    def request_approval(self, agent_id: str, tool_id: str, args: Optional[Dict] = None) -> Dict:
        """Request approval for a tool call"""
        request_id = hashlib.sha256(
            f"{agent_id}:{tool_id}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
        
        request = {
            "id": request_id,
            "agent_id": agent_id,
            "tool_id": tool_id,
            "args": args or {},
            "status": "pending",
            "requested_at": datetime.now().isoformat(),
            "approved_at": None,
            "rejected_at": None,
            "reason": None
        }
        
        self.pending_approvals[request_id] = request
        self.save_pending_approvals()
        
        return {
            "error": "approval_required",
            "request_id": request_id,
            "agent_id": agent_id,
            "tool_id": tool_id,
            "how_to_approve": f"python3 scripts/broker/tool_broker.py approve --request-id {request_id}",
            "summary": f"Agent '{agent_id}' wants to call tool '{tool_id}'"
        }
    
    def get_pending_approvals(self) -> List[Dict]:
        """Get all pending approval requests"""
        return [
            req for req in self.pending_approvals.values()
            if req.get("status") == "pending"
        ]
    
    def approve_request(self, request_id: str) -> bool:
        """Approve a pending request and add to allowlist"""
        if request_id not in self.pending_approvals:
            return False
        
        request = self.pending_approvals[request_id]
        if request["status"] != "pending":
            return False
        
        # Add to allowlist
        agent_id = request["agent_id"]
        tool_id = request["tool_id"]
        
        if agent_id not in self.allowlists:
            self.allowlists[agent_id] = {"allow": [], "deny": [], "servers": []}
        
        if tool_id not in self.allowlists[agent_id]["allow"]:
            self.allowlists[agent_id]["allow"].append(tool_id)
            self.save_allowlists()
        
        # Mark as approved
        request["status"] = "approved"
        request["approved_at"] = datetime.now().isoformat()
        self.save_pending_approvals()
        
        return True
    
    def reject_request(self, request_id: str, reason: str) -> bool:
        """Reject a pending request"""
        if request_id not in self.pending_approvals:
            return False
        
        request = self.pending_approvals[request_id]
        if request["status"] != "pending":
            return False
        
        request["status"] = "rejected"
        request["rejected_at"] = datetime.now().isoformat()
        request["reason"] = reason
        self.save_pending_approvals()
        
        return True
    
    def is_approval_required(self, agent_id: str, tool_id: str) -> bool:
        """Check if approval is required for a tool (not in allowlist)"""
        return not self.is_tool_allowed(agent_id, tool_id)
