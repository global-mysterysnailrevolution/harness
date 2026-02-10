#!/usr/bin/env python3
"""
Security Policy Enforcement
Implements capability-scoped access, rate limits, argument validation, and log redaction
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
import os

class SecurityPolicy:
    """Enforces security policies at broker boundary"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path.cwd() / "ai" / "supervisor" / "security_policy.json"
        self.rate_limits: Dict[str, Dict] = {}
        self.argument_patterns: Dict[str, List[str]] = {}
        self.blocked_patterns: Set[str] = set()
        self.secret_patterns: List[re.Pattern] = [
            re.compile(r'(?i)(password|secret|token|key|api[_-]?key|auth[_-]?token)\s*[:=]\s*["\']?([^"\'\s]+)'),
            re.compile(r'(?i)(bearer|basic)\s+([a-zA-Z0-9+/=]+)'),
        ]
        self.load_config()
    
    def load_config(self):
        """Load security policy configuration"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.rate_limits = config.get("rate_limits", {})
                    self.argument_patterns = config.get("argument_patterns", {})
                    self.blocked_patterns = set(config.get("blocked_patterns", []))
            except Exception as e:
                print(f"Warning: Could not load security policy: {e}")
    
    def check_rate_limit(self, agent_id: str, tool_id: str) -> tuple[bool, Optional[str]]:
        """Check if agent has exceeded rate limit for tool"""
        key = f"{agent_id}:{tool_id}"
        limit_config = self.rate_limits.get(agent_id, {}).get(tool_id, {})
        
        if not limit_config:
            return True, None
        
        max_calls = limit_config.get("max_calls", 1000)
        window_seconds = limit_config.get("window_seconds", 3600)
        
        # Load call history
        history_file = Path.cwd() / "ai" / "supervisor" / "call_history.json"
        history = {}
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except:
                pass
        
        # Get calls in window
        now = datetime.now()
        calls = history.get(key, [])
        recent_calls = [
            dt for dt in calls
            if (now - datetime.fromisoformat(dt)).total_seconds() < window_seconds
        ]
        
        if len(recent_calls) >= max_calls:
            return False, f"Rate limit exceeded: {len(recent_calls)}/{max_calls} calls in {window_seconds}s"
        
        # Record call
        recent_calls.append(now.isoformat())
        history[key] = recent_calls[-max_calls:]  # Keep only recent calls
        
        # Save history
        history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2)
        
        return True, None
    
    def validate_arguments(self, tool_id: str, args: Dict[str, Any], agent_id: str) -> tuple[bool, Optional[str]]:
        """Validate tool arguments against security patterns"""
        # Check blocked patterns
        args_str = json.dumps(args, sort_keys=True)
        for pattern in self.blocked_patterns:
            if re.search(pattern, args_str, re.IGNORECASE):
                return False, f"Blocked pattern detected: {pattern}"
        
        # Check tool-specific patterns
        tool_patterns = self.argument_patterns.get(tool_id, [])
        for pattern in tool_patterns:
            if pattern.startswith("block:"):
                blocked = pattern[6:]
                if blocked in args_str.lower():
                    return False, f"Blocked argument pattern: {blocked}"
        
        # Block shell injection patterns
        dangerous = ["shell=true", "eval(", "exec(", "__import__", "subprocess"]
        for danger in dangerous:
            if danger.lower() in args_str.lower():
                return False, f"Dangerous pattern detected: {danger}"
        
        # Block file paths outside workspace
        workspace = Path.cwd()
        for key, value in args.items():
            if isinstance(value, str) and ("/" in value or "\\" in value):
                # Check if it's a file path
                if not value.startswith(str(workspace)):
                    # Allow relative paths within workspace
                    if not (value.startswith("./") or value.startswith("ai/") or value.startswith("scripts/")):
                        return False, f"File path outside workspace: {key}={value}"
        
        return True, None
    
    def redact_secrets(self, text: str) -> str:
        """Redact secrets from text before logging"""
        redacted = text
        for pattern in self.secret_patterns:
            redacted = pattern.sub(r'\1: [REDACTED]', redacted)
        return redacted
    
    def check_budget(self, agent_id: str, estimated_cost: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Check if agent has exceeded budget"""
        budget_file = Path.cwd() / "ai" / "supervisor" / "budgets.json"
        budgets = {}
        if budget_file.exists():
            try:
                with open(budget_file, 'r', encoding='utf-8') as f:
                    budgets = json.load(f)
            except:
                pass
        
        agent_budget = budgets.get(agent_id, {})
        max_tokens = agent_budget.get("max_tokens", 1000000)
        max_api_calls = agent_budget.get("max_api_calls", 1000)
        max_cost = agent_budget.get("max_cost_usd", 10.0)
        
        # Load usage
        usage_file = Path.cwd() / "ai" / "supervisor" / "usage.json"
        usage = {}
        if usage_file.exists():
            try:
                with open(usage_file, 'r', encoding='utf-8') as f:
                    usage = json.load(f)
            except:
                pass
        
        agent_usage = usage.get(agent_id, {
            "tokens": 0,
            "api_calls": 0,
            "cost_usd": 0.0
        })
        
        # Check limits
        if agent_usage["tokens"] + estimated_cost.get("tokens", 0) > max_tokens:
            return False, f"Token budget exceeded: {agent_usage['tokens']}/{max_tokens}"
        
        if agent_usage["api_calls"] + 1 > max_api_calls:
            return False, f"API call budget exceeded: {agent_usage['api_calls']}/{max_api_calls}"
        
        if agent_usage["cost_usd"] + estimated_cost.get("cost_usd", 0) > max_cost:
            return False, f"Cost budget exceeded: ${agent_usage['cost_usd']:.2f}/${max_cost:.2f}"
        
        return True, None
