#!/usr/bin/env python3
"""
Project Intake System
Collects project requirements before swarm spins up
"""

import json
import yaml
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime

class ProjectIntake:
    """Collects and validates project requirements"""
    
    def __init__(self, intake_file: Optional[Path] = None):
        self.intake_file = intake_file or Path.cwd() / "ai" / "supervisor" / "project.yaml"
        self.intake_file.parent.mkdir(parents=True, exist_ok=True)
    
    def collect_intake(self) -> Dict:
        """
        Collect project intake information
        
        Returns intake data structure
        """
        intake = {
            "version": "1.0",
            "collected_at": datetime.now().isoformat(),
            "target": {
                "urls": [],  # Target URLs to test
                "auth_method": None,  # "none", "basic", "oauth", "api_key"
                "auth_config": {},  # Auth-specific config
                "environments": []  # ["dev", "staging", "prod"]
            },
            "test_requirements": {
                "depth": "smoke",  # "smoke", "regression", "visual_diff"
                "allowed_domains": [],
                "blocked_domains": [],
                "test_suite_path": None,
                "test_command": None
            },
            "code_changes": {
                "allowed": False,
                "repo_path": None,
                "test_command": None,
                "build_command": None
            },
            "secrets": {
                "required": [],  # List of secret names
                "storage": "env",  # "env", "vault", "file"
                "scope": "per_tool"  # "global", "per_tool"
            },
            "budget": {
                "max_tokens": 1000000,
                "max_api_calls": 1000,
                "max_cost_usd": 10.0,
                "max_time_seconds": 3600
            },
            "stopping_conditions": [
                "all_tests_pass",
                "budget_exceeded",
                "max_iterations_reached"
            ],
            "agent_roles": {
                "wheel_scout": {
                    "enabled": True,
                    "required_for_build": True
                },
                "web_runner": {
                    "enabled": True,
                    "tools": ["browser", "screenshot", "console"]
                },
                "judge": {
                    "enabled": True,
                    "tools": ["image", "read", "compare"]
                },
                "fixer": {
                    "enabled": False,  # Only if code_changes.allowed
                    "tools": ["write", "read", "git", "exec"]
                }
            },
            "forge_policy": {
                "allow_new_servers": False,  # Requires approval
                "approval_required": True,
                "allowed_sources": []  # ["docker_hub", "github", "npm"]
            }
        }
        
        return intake
    
    def save_intake(self, intake: Dict):
        """Save intake to YAML file"""
        with open(self.intake_file, 'w', encoding='utf-8') as f:
            yaml.dump(intake, f, default_flow_style=False, sort_keys=False)
    
    def load_intake(self) -> Optional[Dict]:
        """Load intake from file"""
        if not self.intake_file.exists():
            return None
        
        try:
            with open(self.intake_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading intake: {e}")
            return None
    
    def validate_intake(self, intake: Dict) -> tuple[bool, Optional[str]]:
        """Validate intake data"""
        # Check required fields
        if not intake.get("target", {}).get("urls"):
            return False, "Target URLs required"
        
        # Validate code changes policy
        code_changes = intake.get("code_changes", {})
        if code_changes.get("allowed") and not code_changes.get("repo_path"):
            return False, "Repo path required if code changes allowed"
        
        # Validate secrets
        secrets = intake.get("secrets", {})
        if secrets.get("required") and not secrets.get("storage"):
            return False, "Secret storage method required"
        
        # Validate forge policy
        forge = intake.get("forge_policy", {})
        if forge.get("allow_new_servers") and not forge.get("allowed_sources"):
            return False, "Allowed sources required if forge enabled"
        
        return True, None
    
    def generate_supervisor_config(self, intake: Dict) -> Dict:
        """Generate supervisor config from intake"""
        config = {
            "version": "1.0",
            "project_intake": intake,
            "supervisor": {
                "enabled": True,
                "tool_broker": {"enabled": True},
                "wheel_scout": {
                    "enabled": intake.get("agent_roles", {}).get("wheel_scout", {}).get("enabled", True),
                    "required_for_build": intake.get("agent_roles", {}).get("wheel_scout", {}).get("required_for_build", True)
                },
                "context_builder": {"enabled": True},
                "forge": {
                    "enabled": intake.get("forge_policy", {}).get("allow_new_servers", False),
                    "approval_required": intake.get("forge_policy", {}).get("approval_required", True)
                }
            },
            "budget": intake.get("budget", {}),
            "stopping_conditions": intake.get("stopping_conditions", [])
        }
        
        return config

def main():
    """CLI interface for project intake"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Project Intake System")
    parser.add_argument("command", choices=["collect", "validate", "generate"],
                       help="Command to execute")
    parser.add_argument("--input", help="Input file (for validate/generate)")
    parser.add_argument("--output", help="Output file")
    
    args = parser.parse_args()
    
    intake_system = ProjectIntake()
    
    if args.command == "collect":
        intake = intake_system.collect_intake()
        output_file = Path(args.output) if args.output else intake_system.intake_file
        intake_system.save_intake(intake)
        print(f"Intake saved to {output_file}")
        print("\nEdit the file to fill in project requirements:")
        print(f"  - Target URLs")
        print(f"  - Test requirements")
        print(f"  - Code change policy")
        print(f"  - Secrets needed")
        print(f"  - Budget limits")
    
    elif args.command == "validate":
        input_file = Path(args.input) if args.input else intake_system.intake_file
        intake_system.intake_file = input_file
        intake = intake_system.load_intake()
        if not intake:
            print("Error: Could not load intake file")
            return
        
        valid, error = intake_system.validate_intake(intake)
        if valid:
            print("✓ Intake validation passed")
        else:
            print(f"✗ Intake validation failed: {error}")
    
    elif args.command == "generate":
        input_file = Path(args.input) if args.input else intake_system.intake_file
        intake_system.intake_file = input_file
        intake = intake_system.load_intake()
        if not intake:
            print("Error: Could not load intake file")
            return
        
        config = intake_system.generate_supervisor_config(intake)
        output_file = Path(args.output) if args.output else Path.cwd() / "ai" / "supervisor" / "supervisor_config.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        print(f"✓ Supervisor config generated: {output_file}")

if __name__ == "__main__":
    main()
