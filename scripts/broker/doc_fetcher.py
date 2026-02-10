#!/usr/bin/env python3
"""
Documentation Fetcher
Fetches documentation on-demand for sub-agent specialization
"""

import json
import requests
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse
import subprocess

class DocFetcher:
    """Fetches documentation from various sources"""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path("ai/research/docs_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Agent-Harness/1.0'
        })
    
    def fetch_language_docs(self, language: str) -> Optional[Dict]:
        """Fetch official language documentation"""
        doc_urls = {
            "python": "https://docs.python.org/3/",
            "javascript": "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
            "typescript": "https://www.typescriptlang.org/docs/",
            "rust": "https://doc.rust-lang.org/",
            "go": "https://go.dev/doc/",
            "java": "https://docs.oracle.com/javase/",
            "cpp": "https://en.cppreference.com/",
            "csharp": "https://learn.microsoft.com/en-us/dotnet/",
        }
        
        if language.lower() not in doc_urls:
            return None
        
        url = doc_urls[language.lower()]
        cache_file = self.cache_dir / f"{language}_docs.json"
        
        # Check cache
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        
        # Fetch (simplified - would use actual doc scraping in production)
        doc_data = {
            "language": language,
            "url": url,
            "fetched": False,
            "note": "Implement actual documentation scraping"
        }
        
        # Cache
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(doc_data, f, indent=2)
        
        return doc_data
    
    def fetch_framework_docs(self, framework: str) -> Optional[Dict]:
        """Fetch framework documentation"""
        doc_urls = {
            "react": "https://react.dev/",
            "vue": "https://vuejs.org/",
            "angular": "https://angular.io/docs",
            "django": "https://docs.djangoproject.com/",
            "flask": "https://flask.palletsprojects.com/",
            "express": "https://expressjs.com/",
            "next": "https://nextjs.org/docs",
            "spring": "https://spring.io/docs",
        }
        
        if framework.lower() not in doc_urls:
            return None
        
        url = doc_urls[framework.lower()]
        cache_file = self.cache_dir / f"{framework}_docs.json"
        
        # Check cache
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        
        doc_data = {
            "framework": framework,
            "url": url,
            "fetched": False,
            "note": "Implement actual documentation scraping"
        }
        
        # Cache
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(doc_data, f, indent=2)
        
        return doc_data
    
    def fetch_github_docs(self, repo_owner: str, repo_name: str) -> Optional[Dict]:
        """Fetch documentation from GitHub repository"""
        # Use GitHub API or web scraping
        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/readme"
        
        cache_file = self.cache_dir / f"{repo_owner}_{repo_name}_docs.json"
        
        # Check cache
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        
        try:
            response = self.session.get(api_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                doc_data = {
                    "repo": f"{repo_owner}/{repo_name}",
                    "readme_url": data.get("html_url", ""),
                    "content": data.get("content", ""),
                    "fetched": True
                }
                
                # Cache
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(doc_data, f, indent=2)
                
                return doc_data
        except Exception as e:
            print(f"Error fetching GitHub docs: {e}")
        
        return None
    
    def search_web_docs(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search web for documentation"""
        # Would use web search API (Google, Bing, etc.)
        # For now, return placeholder
        return [
            {
                "title": f"Documentation: {query}",
                "url": f"https://example.com/docs/{query}",
                "snippet": f"Documentation about {query}",
                "source": "web_search"
            }
        ]
    
    def fetch_all_for_agent(self, requirements: Dict) -> Dict:
        """Fetch all documentation needed for an agent"""
        docs = {
            "language_docs": [],
            "framework_docs": [],
            "github_docs": [],
            "web_docs": []
        }
        
        # Language documentation
        if "languages" in requirements:
            for lang in requirements["languages"]:
                lang_doc = self.fetch_language_docs(lang)
                if lang_doc:
                    docs["language_docs"].append(lang_doc)
        
        # Framework documentation
        if "frameworks" in requirements:
            for framework in requirements["frameworks"]:
                framework_doc = self.fetch_framework_docs(framework)
                if framework_doc:
                    docs["framework_docs"].append(framework_doc)
        
        # GitHub documentation
        if "github_repos" in requirements:
            for repo in requirements["github_repos"]:
                if "/" in repo:
                    owner, name = repo.split("/", 1)
                    github_doc = self.fetch_github_docs(owner, name)
                    if github_doc:
                        docs["github_docs"].append(github_doc)
        
        # Web search for additional docs
        if "search_queries" in requirements:
            for query in requirements["search_queries"]:
                web_docs = self.search_web_docs(query)
                docs["web_docs"].extend(web_docs)
        
        return docs
