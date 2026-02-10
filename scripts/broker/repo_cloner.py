#!/usr/bin/env python3
"""
Repository Cloner
Dynamically clones reference repositories for sub-agent context
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import shutil

class RepoCloner:
    """Manages dynamic repository cloning"""
    
    def __init__(self, vendor_dir: Optional[Path] = None, max_age_days: int = 7):
        self.vendor_dir = vendor_dir or Path("ai/vendor")
        self.vendor_dir.mkdir(parents=True, exist_ok=True)
        self.max_age_days = max_age_days
        self.usage_log = self.vendor_dir / ".usage_log.json"
        self._load_usage_log()
    
    def _load_usage_log(self):
        """Load repository usage log"""
        if self.usage_log.exists():
            try:
                with open(self.usage_log, 'r', encoding='utf-8') as f:
                    self.usage_data = json.load(f)
            except:
                self.usage_data = {}
        else:
            self.usage_data = {}
    
    def _save_usage_log(self):
        """Save repository usage log"""
        with open(self.usage_log, 'w', encoding='utf-8') as f:
            json.dump(self.usage_data, f, indent=2)
    
    def _get_repo_path(self, repo_url: str) -> Path:
        """Get local path for a repository"""
        # Convert URL to safe directory name
        repo_name = repo_url.replace("https://github.com/", "").replace("https://", "").replace("/", "_").replace(".git", "")
        return self.vendor_dir / repo_name
    
    def clone_repo(self, repo_url: str, ask_first: bool = True) -> Optional[Path]:
        """
        Clone a repository if not already present
        
        Returns path to cloned repo, or None if declined
        """
        repo_path = self._get_repo_path(repo_url)
        
        # Check if already cloned
        if repo_path.exists() and (repo_path / ".git").exists():
            # Update usage
            self.usage_data[str(repo_path)] = {
                "last_used": datetime.now().isoformat(),
                "url": repo_url
            }
            self._save_usage_log()
            print(f"Repository already cloned: {repo_path}")
            return repo_path
        
        # Check repo size if asking first
        if ask_first:
            # Would check repo size via GitHub API
            # For now, always ask for large repos
            print(f"Repository would be cloned: {repo_url}")
            print(f"Location: {repo_path}")
            response = input("Clone this repository? (y/N): ")
            if response.lower() != 'y':
                return None
        
        # Clone repository
        try:
            print(f"Cloning {repo_url}...")
            subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(repo_path)],
                check=True,
                capture_output=True
            )
            
            # Log usage
            self.usage_data[str(repo_path)] = {
                "cloned": datetime.now().isoformat(),
                "last_used": datetime.now().isoformat(),
                "url": repo_url
            }
            self._save_usage_log()
            
            print(f"✓ Cloned to {repo_path}")
            return repo_path
        
        except subprocess.CalledProcessError as e:
            print(f"Error cloning repository: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None
    
    def extract_relevant_code(self, repo_path: Path, patterns: List[str]) -> Dict[str, List[str]]:
        """
        Extract relevant code examples from cloned repository
        
        Returns dict mapping file paths to code snippets
        """
        if not repo_path.exists():
            return {}
        
        extracted = {}
        
        for pattern in patterns:
            # Search for files matching pattern
            for file_path in repo_path.rglob(pattern):
                if file_path.is_file():
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                        # Extract relevant snippets (first 500 lines)
                        lines = content.split('\n')[:500]
                        relative_path = file_path.relative_to(repo_path)
                        extracted[str(relative_path)] = lines
                    except:
                        continue
        
        return extracted
    
    def build_reference_index(self, repo_path: Path) -> Dict:
        """Build index of repository structure and key files"""
        if not repo_path.exists():
            return {}
        
        index = {
            "repo_path": str(repo_path),
            "structure": {},
            "key_files": [],
            "languages": [],
            "frameworks": []
        }
        
        # Analyze structure
        for item in repo_path.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                index["structure"][item.name] = "directory"
            elif item.is_file():
                index["structure"][item.name] = "file"
        
        # Find key files (README, package.json, etc.)
        key_patterns = ["README*", "package.json", "requirements.txt", "Cargo.toml", "go.mod"]
        for pattern in key_patterns:
            for file_path in repo_path.rglob(pattern):
                if file_path.is_file():
                    index["key_files"].append(str(file_path.relative_to(repo_path)))
        
        return index
    
    def cleanup_unused_repos(self):
        """Remove repositories that haven't been used recently"""
        cutoff = datetime.now() - timedelta(days=self.max_age_days)
        removed = 0
        
        for repo_path_str, usage_info in list(self.usage_data.items()):
            repo_path = Path(repo_path_str)
            last_used_str = usage_info.get("last_used", "")
            
            if last_used_str:
                try:
                    last_used = datetime.fromisoformat(last_used_str)
                    if last_used < cutoff:
                        if repo_path.exists():
                            print(f"Removing unused repo: {repo_path}")
                            shutil.rmtree(repo_path)
                            removed += 1
                        del self.usage_data[repo_path_str]
                except:
                    continue
        
        if removed > 0:
            self._save_usage_log()
            print(f"Removed {removed} unused repositories")
        
        return removed
    
    def list_cloned_repos(self) -> List[Dict]:
        """List all cloned repositories with metadata"""
        repos = []
        
        for repo_path_str, usage_info in self.usage_data.items():
            repo_path = Path(repo_path_str)
            if repo_path.exists():
                repos.append({
                    "path": str(repo_path),
                    "url": usage_info.get("url", ""),
                    "cloned": usage_info.get("cloned", ""),
                    "last_used": usage_info.get("last_used", "")
                })
        
        return repos
