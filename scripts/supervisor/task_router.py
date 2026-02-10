#!/usr/bin/env python3
"""
Task Router
Classifies and routes tasks to appropriate agents
"""

import re
from typing import Dict, List, Optional, Tuple

class TaskRouter:
    """Routes tasks to appropriate agents"""
    
    # Intent patterns
    BUILD_PATTERNS = [
        r"\b(build|create|implement|develop|write|make)\s+(a|an|new|the)\s+",
        r"\b(architecture|system|framework|library|tool)\s+(for|to|that)",
        r"\b(design|plan)\s+(a|an|new|the)\s+",
    ]
    
    RESEARCH_PATTERNS = [
        r"\b(research|find|search|look\s+up|investigate)\s+",
        r"\b(what|how|where|when)\s+(is|are|does|do)\s+",
    ]
    
    TEST_PATTERNS = [
        r"\b(test|testing|verify|validate|check)\s+",
        r"\b(run|execute)\s+(tests?|test\s+suite)",
    ]
    
    FIX_PATTERNS = [
        r"\b(fix|repair|debug|resolve|solve)\s+",
        r"\b(error|bug|issue|problem)\s+(with|in)",
    ]
    
    def classify_intent(self, task_description: str) -> str:
        """Classify task intent"""
        task_lower = task_description.lower()
        
        # Check for build intent
        for pattern in self.BUILD_PATTERNS:
            if re.search(pattern, task_lower):
                return "build"
        
        # Check for research intent
        for pattern in self.RESEARCH_PATTERNS:
            if re.search(pattern, task_lower):
                return "research"
        
        # Check for test intent
        for pattern in self.TEST_PATTERNS:
            if re.search(pattern, task_lower):
                return "test"
        
        # Check for fix intent
        for pattern in self.FIX_PATTERNS:
            if re.search(pattern, task_lower):
                return "fix"
        
        return "general"
    
    def requires_wheel_scout(self, intent: str) -> bool:
        """Determine if task requires Wheel-Scout gate"""
        return intent == "build"
    
    def route_to_agent(self, task_description: str, intent: str) -> Tuple[str, Dict]:
        """
        Route task to appropriate agent
        
        Returns (agent_type, agent_config)
        """
        if intent == "build":
            return ("implementer", {
                "role": "implementer",
                "requires_wheel_scout": True,
                "tools": ["group:fs", "group:runtime"]
            })
        
        elif intent == "test":
            return ("test-runner", {
                "role": "test-runner",
                "requires_wheel_scout": False,
                "tools": ["browser", "group:fs"]
            })
        
        elif intent == "fix":
            return ("fixer", {
                "role": "fixer",
                "requires_wheel_scout": False,
                "tools": ["group:fs", "group:runtime"]
            })
        
        elif intent == "research":
            return ("researcher", {
                "role": "researcher",
                "requires_wheel_scout": False,
                "tools": ["web_search", "github_search"]
            })
        
        else:
            return ("general", {
                "role": "general",
                "requires_wheel_scout": False,
                "tools": []
            })
    
    def extract_constraints(self, task_description: str) -> Dict:
        """Extract constraints from task description"""
        constraints = {
            "budget": None,
            "latency": None,
            "security": None,
            "platform": None
        }
        
        # Simple keyword extraction (could use NLP)
        task_lower = task_description.lower()
        
        if "fast" in task_lower or "quick" in task_lower:
            constraints["latency"] = "low"
        if "secure" in task_lower or "security" in task_lower:
            constraints["security"] = "high"
        if "windows" in task_lower:
            constraints["platform"] = "windows"
        elif "linux" in task_lower:
            constraints["platform"] = "linux"
        
        return constraints
