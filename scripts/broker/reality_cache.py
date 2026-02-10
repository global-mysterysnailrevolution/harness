#!/usr/bin/env python3
"""
Reality Cache Manager
Caches landscape reports to avoid re-researching similar problems
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timedelta

class RealityCache:
    """Manages cached landscape reports"""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path("ai/research/landscape_reports")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_age_days = 30  # Reports older than 30 days are stale
    
    def _generate_cache_key(self, problem_statement: str, constraints: Dict) -> str:
        """Generate cache key from problem signature"""
        # Create deterministic key from problem + constraints
        key_data = {
            "problem": problem_statement.lower().strip(),
            "constraints": json.dumps(constraints, sort_keys=True)
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]
    
    def get_cached_report(self, problem_statement: str, constraints: Dict) -> Optional[Dict]:
        """Get cached landscape report if available and fresh"""
        cache_key = self._generate_cache_key(problem_statement, constraints)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            # Check age
            generated = cached_data.get("generated", "")
            if generated:
                try:
                    generated_date = datetime.fromisoformat(generated.replace("Z", "+00:00"))
                    age = datetime.now() - generated_date.replace(tzinfo=None)
                    if age > timedelta(days=self.max_age_days):
                        print(f"Cache entry expired (age: {age.days} days)")
                        return None
                except:
                    pass
            
            print(f"Using cached landscape report: {cache_key}")
            return cached_data.get("report")
        
        except Exception as e:
            print(f"Error reading cache: {e}")
            return None
    
    def cache_report(self, problem_statement: str, constraints: Dict, report: Dict):
        """Cache a landscape report"""
        cache_key = self._generate_cache_key(problem_statement, constraints)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        cache_data = {
            "cache_key": cache_key,
            "generated": datetime.now().isoformat(),
            "problem_statement": problem_statement,
            "constraints": constraints,
            "report": report
        }
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            print(f"Cached landscape report: {cache_key}")
        except Exception as e:
            print(f"Error caching report: {e}")
    
    def list_cached_reports(self) -> List[Dict]:
        """List all cached reports with metadata"""
        reports = []
        
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                reports.append({
                    "cache_key": data.get("cache_key", cache_file.stem),
                    "generated": data.get("generated", ""),
                    "problem_statement": data.get("problem_statement", "")[:100],
                    "recommended_path": data.get("report", {}).get("recommended_path", "unknown")
                })
            except:
                continue
        
        return sorted(reports, key=lambda x: x.get("generated", ""), reverse=True)
    
    def clear_stale_cache(self, max_age_days: Optional[int] = None):
        """Remove stale cache entries"""
        if max_age_days is None:
            max_age_days = self.max_age_days
        
        removed = 0
        cutoff = datetime.now() - timedelta(days=max_age_days)
        
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                generated = data.get("generated", "")
                if generated:
                    generated_date = datetime.fromisoformat(generated.replace("Z", "+00:00"))
                    if generated_date.replace(tzinfo=None) < cutoff:
                        cache_file.unlink()
                        removed += 1
            except:
                continue
        
        print(f"Removed {removed} stale cache entries")
        return removed

def main():
    """CLI for cache management"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Reality cache manager")
    parser.add_argument("command", choices=["list", "clear"], help="Command to execute")
    parser.add_argument("--max-age", type=int, default=30, help="Max age in days for clear command")
    
    args = parser.parse_args()
    
    cache = RealityCache()
    
    if args.command == "list":
        reports = cache.list_cached_reports()
        print(f"\nCached Reports ({len(reports)}):")
        for r in reports:
            print(f"  {r['cache_key']}: {r['recommended_path']} ({r['generated']})")
    
    elif args.command == "clear":
        removed = cache.clear_stale_cache(args.max_age)
        print(f"Cleared {removed} stale entries")

if __name__ == "__main__":
    main()
