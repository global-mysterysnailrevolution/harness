#!/usr/bin/env python3
"""
Context Hydrator
Builds specialized context packs for sub-agents
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from doc_fetcher import DocFetcher
from repo_cloner import RepoCloner

class ContextHydrator:
    """Hydrates specialized context for sub-agents"""
    
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.doc_fetcher = DocFetcher(repo_path / "ai/research/docs_cache")
        self.repo_cloner = RepoCloner(repo_path / "ai/vendor")
        self.specialized_dir = repo_path / "ai/context/specialized"
        self.specialized_dir.mkdir(parents=True, exist_ok=True)
    
    def analyze_requirements(self, task_description: str, agent_role: str) -> Dict:
        """Analyze task to determine context requirements"""
        requirements = {
            "languages": [],
            "frameworks": [],
            "github_repos": [],
            "search_queries": [],
            "documentation_needs": []
        }
        
        # Detect languages (simple keyword matching - could use NLP)
        language_keywords = {
            "python": ["python", "py", "django", "flask"],
            "javascript": ["javascript", "js", "node", "react", "vue"],
            "typescript": ["typescript", "ts", "angular"],
            "rust": ["rust", "cargo"],
            "go": ["go", "golang"],
            "java": ["java", "spring"],
        }
        
        task_lower = task_description.lower()
        for lang, keywords in language_keywords.items():
            if any(keyword in task_lower for keyword in keywords):
                requirements["languages"].append(lang)
        
        # Detect frameworks
        framework_keywords = {
            "react": ["react"],
            "vue": ["vue"],
            "django": ["django"],
            "flask": ["flask"],
            "express": ["express"],
            "next": ["next"],
        }
        
        for framework, keywords in framework_keywords.items():
            if any(keyword in task_lower for keyword in keywords):
                requirements["frameworks"].append(framework)
        
        # Add role-specific requirements
        if agent_role == "web-runner":
            requirements["search_queries"].append("browser automation testing")
        elif agent_role == "judge":
            requirements["search_queries"].append("test evaluation visual diff")
        elif agent_role == "fixer":
            requirements["search_queries"].append("code debugging patterns")
        
        return requirements
    
    def fetch_documentation(self, requirements: Dict) -> Dict:
        """Fetch all required documentation"""
        return self.doc_fetcher.fetch_all_for_agent(requirements)
    
    def clone_reference_repos(self, requirements: Dict, ask_first: bool = True) -> List[Path]:
        """Clone reference repositories if needed"""
        cloned_repos = []
        
        for repo_url in requirements.get("github_repos", []):
            repo_path = self.repo_cloner.clone_repo(repo_url, ask_first=ask_first)
            if repo_path:
                cloned_repos.append(repo_path)
        
        return cloned_repos
    
    def build_specialized_context(self, agent_id: str, task_description: str,
                                 agent_role: str, existing_context: Optional[Dict] = None) -> Path:
        """
        Build specialized context pack for an agent
        
        Returns path to generated context file
        """
        # Analyze requirements
        requirements = self.analyze_requirements(task_description, agent_role)
        
        # Fetch documentation
        docs = self.fetch_documentation(requirements)
        
        # Clone reference repos
        cloned_repos = self.clone_reference_repos(requirements, ask_first=True)
        
        # Extract code examples from cloned repos
        code_examples = {}
        for repo_path in cloned_repos:
            # Extract relevant patterns
            patterns = ["*.py", "*.js", "*.ts", "*.rs", "*.go"]
            examples = self.repo_cloner.extract_relevant_code(repo_path, patterns)
            code_examples.update(examples)
            
            # Build reference index
            index = self.repo_cloner.build_reference_index(repo_path)
            code_examples[f"_index_{repo_path.name}"] = [json.dumps(index, indent=2)]
        
        # Load existing context if provided
        repo_map = ""
        context_pack = ""
        if existing_context:
            repo_map_path = existing_context.get("repo_map")
            if repo_map_path and Path(repo_map_path).exists():
                repo_map = Path(repo_map_path).read_text(encoding='utf-8')
            
            context_pack_path = existing_context.get("context_pack")
            if context_pack_path and Path(context_pack_path).exists():
                context_pack = Path(context_pack_path).read_text(encoding='utf-8')
        
        # Build specialized context
        context_content = f"""# Specialized Context: {agent_id}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Agent Role
{agent_role}

## Task Description
{task_description}

## Requirements Analysis
- Languages: {', '.join(requirements['languages']) if requirements['languages'] else 'None detected'}
- Frameworks: {', '.join(requirements['frameworks']) if requirements['frameworks'] else 'None detected'}
- Reference Repos: {len(cloned_repos)} cloned

## Documentation

### Language Documentation
"""
        
        for lang_doc in docs.get("language_docs", []):
            context_content += f"- {lang_doc.get('language', 'Unknown')}: {lang_doc.get('url', '')}\n"
        
        context_content += "\n### Framework Documentation\n"
        for framework_doc in docs.get("framework_docs", []):
            context_content += f"- {framework_doc.get('framework', 'Unknown')}: {framework_doc.get('url', '')}\n"
        
        context_content += "\n### GitHub Documentation\n"
        for github_doc in docs.get("github_docs", []):
            context_content += f"- {github_doc.get('repo', 'Unknown')}: {github_doc.get('readme_url', '')}\n"
        
        context_content += "\n## Code Examples\n\n"
        for file_path, lines in list(code_examples.items())[:10]:  # Limit examples
            context_content += f"### {file_path}\n\n```\n"
            context_content += "\n".join(lines[:50])  # Limit lines per file
            context_content += "\n```\n\n"
        
        if repo_map:
            context_content += "\n## Repository Structure\n\n"
            context_content += repo_map[:1000]  # Limit size
            context_content += "\n"
        
        if context_pack:
            context_content += "\n## Existing Context\n\n"
            context_content += context_pack[:1000]  # Limit size
            context_content += "\n"
        
        # Write specialized context
        context_file = self.specialized_dir / f"{agent_id}_CONTEXT.md"
        context_file.write_text(context_content, encoding='utf-8')
        
        print(f"✓ Generated specialized context: {context_file}")
        return context_file
