#!/usr/bin/env python3
"""
Gate Enforcer
Enforces supervisor gates (Wheel-Scout, budget, etc.)
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

class GateEnforcer:
    """Enforces supervisor gates"""
    
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.gates_file = state_dir / "gates.json"
        self._load_gates()
    
    def _load_gates(self):
        """Load gate states"""
        if self.gates_file.exists():
            try:
                with open(self.gates_file, 'r', encoding='utf-8') as f:
                    self.gates = json.load(f)
            except:
                self.gates = {}
        else:
            self.gates = {}
    
    def _save_gates(self):
        """Save gate states"""
        with open(self.gates_file, 'w', encoding='utf-8') as f:
            json.dump(self.gates, f, indent=2)
    
    def check_wheel_scout_gate(self, task_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if Wheel-Scout gate is cleared for a task
        
        Returns (is_cleared, landscape_report_path)
        """
        gate_key = f"wheel_scout_{task_id}"
        
        if gate_key in self.gates:
            gate_state = self.gates[gate_key]
            if gate_state.get("cleared", False):
                report_path = gate_state.get("landscape_report")
                return True, report_path
        
        return False, None
    
    def clear_wheel_scout_gate(self, task_id: str, landscape_report_path: str):
        """Mark Wheel-Scout gate as cleared"""
        gate_key = f"wheel_scout_{task_id}"
        self.gates[gate_key] = {
            "cleared": True,
            "landscape_report": landscape_report_path,
            "cleared_at": json.dumps({})  # Would use datetime
        }
        self._save_gates()
    
    def check_budget_gate(self, task_id: str, current_usage: Dict) -> Tuple[bool, Optional[str]]:
        """
        Check if task is within budget
        
        Returns (within_budget, error_message)
        """
        budget_key = f"budget_{task_id}"
        
        if budget_key not in self.gates:
            # No budget set, allow
            return True, None
        
        budget = self.gates[budget_key]
        max_tokens = budget.get("max_tokens", float('inf'))
        max_api_calls = budget.get("max_api_calls", float('inf'))
        max_time_seconds = budget.get("max_time_seconds", float('inf'))
        
        if current_usage.get("tokens", 0) > max_tokens:
            return False, f"Token budget exceeded: {current_usage['tokens']}/{max_tokens}"
        
        if current_usage.get("api_calls", 0) > max_api_calls:
            return False, f"API call budget exceeded: {current_usage['api_calls']}/{max_api_calls}"
        
        if current_usage.get("time_seconds", 0) > max_time_seconds:
            return False, f"Time budget exceeded: {current_usage['time_seconds']}/{max_time_seconds}"
        
        return True, None
    
    def set_budget(self, task_id: str, budget: Dict):
        """Set budget for a task"""
        budget_key = f"budget_{task_id}"
        self.gates[budget_key] = budget
        self._save_gates()
    
    def check_compliance(self, agent_id: str, message: str, required_report: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Check if agent message complies with requirements
        
        Returns (is_compliant, error_message)
        """
        # Check if message references landscape report
        if required_report:
            report_keywords = ["landscape", "existing solution", "reuse", "extend", "adopt"]
            message_lower = message.lower()
            
            if not any(keyword in message_lower for keyword in report_keywords):
                return False, "Message must reference landscape report. Include section from closest_existing_solutions or request scout revision."
        
        return True, None
    
    def enforce_compliance(self, agent_id: str, message: str, required_report: Optional[str] = None) -> bool:
        """
        Enforce compliance - blocks non-compliant messages
        
        Returns True if compliant, False if blocked
        """
        is_compliant, error = self.check_compliance(agent_id, message, required_report)
        
        if not is_compliant:
            print(f"[Gate Enforcer] BLOCKED: {error}")
            print(f"[Gate Enforcer] Agent: {agent_id}")
            print(f"[Gate Enforcer] Message: {message[:100]}...")
            return False
        
        return True
