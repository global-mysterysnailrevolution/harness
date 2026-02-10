#!/usr/bin/env python3
"""
Budget Tracker
Tracks token usage, API calls, and time for tasks
"""

import json
import time
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

class BudgetTracker:
    """Tracks budgets for tasks and agents"""
    
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.usage_file = state_dir / "usage.json"
        self._load_usage()
    
    def _load_usage(self):
        """Load usage data"""
        if self.usage_file.exists():
            try:
                with open(self.usage_file, 'r', encoding='utf-8') as f:
                    self.usage = json.load(f)
            except:
                self.usage = {}
        else:
            self.usage = {}
    
    def _save_usage(self):
        """Save usage data"""
        with open(self.usage_file, 'w', encoding='utf-8') as f:
            json.dump(self.usage, f, indent=2)
    
    def start_task(self, task_id: str):
        """Start tracking a task"""
        if task_id not in self.usage:
            self.usage[task_id] = {
                "started_at": datetime.now().isoformat(),
                "tokens": 0,
                "api_calls": 0,
                "time_seconds": 0,
                "agents": {}
            }
        else:
            self.usage[task_id]["started_at"] = datetime.now().isoformat()
        
        self._save_usage()
    
    def record_tokens(self, task_id: str, agent_id: str, tokens: int):
        """Record token usage"""
        if task_id not in self.usage:
            self.start_task(task_id)
        
        if agent_id not in self.usage[task_id]["agents"]:
            self.usage[task_id]["agents"][agent_id] = {
                "tokens": 0,
                "api_calls": 0
            }
        
        self.usage[task_id]["tokens"] = self.usage[task_id].get("tokens", 0) + tokens
        self.usage[task_id]["agents"][agent_id]["tokens"] += tokens
        self._save_usage()
    
    def record_api_call(self, task_id: str, agent_id: str):
        """Record API call"""
        if task_id not in self.usage:
            self.start_task(task_id)
        
        if agent_id not in self.usage[task_id]["agents"]:
            self.usage[task_id]["agents"][agent_id] = {
                "tokens": 0,
                "api_calls": 0
            }
        
        self.usage[task_id]["api_calls"] = self.usage[task_id].get("api_calls", 0) + 1
        self.usage[task_id]["agents"][agent_id]["api_calls"] += 1
        self._save_usage()
    
    def update_time(self, task_id: str):
        """Update elapsed time for task"""
        if task_id not in self.usage:
            return
        
        started_at_str = self.usage[task_id].get("started_at", "")
        if started_at_str:
            try:
                started_at = datetime.fromisoformat(started_at_str)
                elapsed = (datetime.now() - started_at).total_seconds()
                self.usage[task_id]["time_seconds"] = elapsed
                self._save_usage()
            except:
                pass
    
    def get_usage(self, task_id: str) -> Dict:
        """Get current usage for a task"""
        self.update_time(task_id)
        return self.usage.get(task_id, {
            "tokens": 0,
            "api_calls": 0,
            "time_seconds": 0,
            "agents": {}
        })
    
    def get_agent_usage(self, task_id: str, agent_id: str) -> Dict:
        """Get usage for a specific agent"""
        task_usage = self.get_usage(task_id)
        return task_usage.get("agents", {}).get(agent_id, {
            "tokens": 0,
            "api_calls": 0
        })
    
    def finish_task(self, task_id: str):
        """Mark task as finished"""
        if task_id in self.usage:
            self.update_time(task_id)
            self.usage[task_id]["finished_at"] = datetime.now().isoformat()
            self._save_usage()
