#!/usr/bin/env python3
"""
Supervisor
Main supervisor logic for multi-agent orchestration
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Optional
from task_router import TaskRouter
from gate_enforcer import GateEnforcer
from budget_tracker import BudgetTracker
from agent_coordinator import AgentCoordinator
import sys
sys.path.append(str(Path(__file__).parent.parent / "broker"))
from context_hydrator import ContextHydrator

class Supervisor:
    """Main supervisor for multi-agent orchestration"""
    
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.state_dir = repo_path / "ai/supervisor"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        self.task_router = TaskRouter()
        self.gate_enforcer = GateEnforcer(self.state_dir)
        self.budget_tracker = BudgetTracker(self.state_dir)
        self.agent_coordinator = AgentCoordinator(repo_path, self.state_dir)
        self.context_hydrator = ContextHydrator(repo_path)
        
        self.task_queue_file = self.state_dir / "task_queue.json"
        self.state_file = self.state_dir / "state.json"
        self._load_state()
    
    def _load_state(self):
        """Load supervisor state"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
            except:
                self.state = {"tasks": {}}
        else:
            self.state = {"tasks": {}}
    
    def _save_state(self):
        """Save supervisor state"""
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2)
    
    def submit_task(self, task_description: str, task_id: Optional[str] = None) -> str:
        """Submit a new task"""
        if not task_id:
            task_id = f"task_{len(self.state['tasks']) + 1}"
        
        # Classify intent
        intent = self.task_router.classify_intent(task_description)
        constraints = self.task_router.extract_constraints(task_description)
        
        # Route to agent
        agent_type, agent_config = self.task_router.route_to_agent(task_description, intent)
        
        # Check if Wheel-Scout gate needed
        requires_wheel_scout = self.task_router.requires_wheel_scout(intent)
        
        task_state = {
            "task_id": task_id,
            "description": task_description,
            "intent": intent,
            "constraints": constraints,
            "agent_type": agent_type,
            "agent_config": agent_config,
            "requires_wheel_scout": requires_wheel_scout,
            "status": "pending",
            "created_at": json.dumps({})  # Would use datetime
        }
        
        self.state["tasks"][task_id] = task_state
        self._save_state()
        
        # Start budget tracking
        self.budget_tracker.start_task(task_id)
        
        return task_id
    
    def process_task(self, task_id: str) -> bool:
        """Process a task through the supervisor workflow"""
        if task_id not in self.state["tasks"]:
            print(f"Task not found: {task_id}")
            return False
        
        task = self.state["tasks"][task_id]
        task["status"] = "processing"
        self._save_state()
        
        # Step 1: Check Wheel-Scout gate
        if task["requires_wheel_scout"]:
            is_cleared, report_path = self.gate_enforcer.check_wheel_scout_gate(task_id)
            
            if not is_cleared:
                print(f"[Supervisor] Wheel-Scout gate not cleared for {task_id}")
                print(f"[Supervisor] Spawning Wheel-Scout...")
                
                # Spawn Wheel-Scout
                # In production, this would use platform-specific spawning
                print(f"[Supervisor] Wheel-Scout would be spawned here")
                print(f"[Supervisor] Waiting for landscape report...")
                
                # For now, assume gate is cleared (would wait for actual report)
                # In production: wait for Wheel-Scout to complete and clear gate
                return False
        
        # Step 2: Build specialized context
        print(f"[Supervisor] Building specialized context for agent...")
        specialized_context = self.context_hydrator.build_specialized_context(
            agent_id=f"{task_id}_agent",
            task_description=task["description"],
            agent_role=task["agent_config"]["role"],
            existing_context={
                "repo_map": str(self.repo_path / "ai/context/REPO_MAP.md"),
                "context_pack": str(self.repo_path / "ai/context/CONTEXT_PACK.md")
            }
        )
        
        # Step 3: Spawn agent
        print(f"[Supervisor] Spawning agent: {task['agent_type']}")
        success = self.agent_coordinator.spawn_agent(
            agent_id=f"{task_id}_agent",
            agent_type=task["agent_type"],
            agent_config=task["agent_config"],
            specialized_context=specialized_context
        )
        
        if success:
            task["status"] = "running"
            task["agent_id"] = f"{task_id}_agent"
            self._save_state()
            return True
        
        return False
    
    def check_budget(self, task_id: str) -> tuple[bool, Optional[str]]:
        """Check if task is within budget"""
        usage = self.budget_tracker.get_usage(task_id)
        return self.gate_enforcer.check_budget_gate(task_id, usage)
    
    def finish_task(self, task_id: str):
        """Mark task as finished"""
        if task_id in self.state["tasks"]:
            self.state["tasks"][task_id]["status"] = "finished"
            self.budget_tracker.finish_task(task_id)
            self._save_state()

def main():
    """CLI interface for supervisor"""
    parser = argparse.ArgumentParser(description="Multi-Agent Supervisor")
    parser.add_argument("command", choices=["submit", "process", "status", "list"],
                       help="Command to execute")
    parser.add_argument("--task", help="Task description (for submit)")
    parser.add_argument("--task-id", help="Task ID (for process/status)")
    parser.add_argument("--repo", default=".", help="Repository root path")
    
    args = parser.parse_args()
    
    repo_path = Path(args.repo).resolve()
    supervisor = Supervisor(repo_path)
    
    if args.command == "submit":
        if not args.task:
            print("Error: --task required for submit command")
            return
        
        task_id = supervisor.submit_task(args.task)
        print(f"Task submitted: {task_id}")
    
    elif args.command == "process":
        if not args.task_id:
            print("Error: --task-id required for process command")
            return
        
        success = supervisor.process_task(args.task_id)
        if success:
            print(f"Task {args.task_id} processing started")
        else:
            print(f"Task {args.task_id} processing failed or waiting for gates")
    
    elif args.command == "status":
        if not args.task_id:
            print("Error: --task-id required for status command")
            return
        
        if args.task_id in supervisor.state["tasks"]:
            task = supervisor.state["tasks"][args.task_id]
            usage = supervisor.budget_tracker.get_usage(args.task_id)
            print(f"Task: {args.task_id}")
            print(f"  Status: {task['status']}")
            print(f"  Intent: {task['intent']}")
            print(f"  Usage: {usage['tokens']} tokens, {usage['api_calls']} API calls")
        else:
            print(f"Task not found: {args.task_id}")
    
    elif args.command == "list":
        tasks = supervisor.state["tasks"]
        print(f"\nTasks ({len(tasks)}):")
        for task_id, task in tasks.items():
            print(f"  {task_id}: {task['status']} - {task['description'][:50]}...")

if __name__ == "__main__":
    main()
