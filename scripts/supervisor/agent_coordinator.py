#!/usr/bin/env python3
"""
Agent Coordinator
Manages agent lifecycle and coordination
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

class AgentCoordinator:
    """Coordinates agent spawning and lifecycle"""
    
    def __init__(self, repo_path: Path, state_dir: Path):
        self.repo_path = repo_path
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.agents_file = state_dir / "agents.json"
        self._load_agents()
    
    def _load_agents(self):
        """Load agent states"""
        if self.agents_file.exists():
            try:
                with open(self.agents_file, 'r', encoding='utf-8') as f:
                    self.agents = json.load(f)
            except:
                self.agents = {}
        else:
            self.agents = {}
    
    def _save_agents(self):
        """Save agent states"""
        with open(self.agents_file, 'w', encoding='utf-8') as f:
            json.dump(self.agents, f, indent=2)
    
    def spawn_agent(self, agent_id: str, agent_type: str, agent_config: Dict,
                   specialized_context: Optional[Path] = None) -> bool:
        """
        Spawn an agent with given configuration
        
        Returns True if spawned successfully
        """
        # Build spawn command based on platform
        # This is a placeholder - actual implementation would use platform-specific APIs
        
        agent_state = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "config": agent_config,
            "spawned_at": datetime.now().isoformat(),
            "status": "spawning",
            "specialized_context": str(specialized_context) if specialized_context else None
        }
        
        self.agents[agent_id] = agent_state
        self._save_agents()
        
        # Platform-specific spawning would happen here
        # For now, just log
        print(f"[Agent Coordinator] Spawning agent: {agent_id}")
        print(f"  Type: {agent_type}")
        print(f"  Role: {agent_config.get('role', 'unknown')}")
        if specialized_context:
            print(f"  Context: {specialized_context}")
        
        return True
    
    def get_agent_status(self, agent_id: str) -> Optional[Dict]:
        """Get status of an agent"""
        return self.agents.get(agent_id)
    
    def list_agents(self, task_id: Optional[str] = None) -> List[Dict]:
        """List all agents, optionally filtered by task"""
        agents = list(self.agents.values())
        
        if task_id:
            # Filter by task_id if agents have task association
            agents = [a for a in agents if a.get("task_id") == task_id]
        
        return agents
    
    def terminate_agent(self, agent_id: str):
        """Terminate an agent"""
        if agent_id in self.agents:
            self.agents[agent_id]["status"] = "terminated"
            self.agents[agent_id]["terminated_at"] = datetime.now().isoformat()
            self._save_agents()
    
    def send_message(self, agent_id: str, message: str) -> bool:
        """Send message to an agent"""
        if agent_id not in self.agents:
            return False
        
        # Platform-specific message sending
        # For now, just log
        print(f"[Agent Coordinator] Sending message to {agent_id}: {message[:50]}...")
        return True
