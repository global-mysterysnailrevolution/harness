#!/usr/bin/env python3
"""
Deterministic Repo Map Compiler
Generates REPO_MAP.md from repository analysis
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set

def detect_stack(repo_path: Path) -> Dict[str, any]:
    """Detect programming language and framework stack"""
    stack = {
        "type": "unknown",
        "languages": [],
        "frameworks": [],
        "package_manager": None
    }
    
    # Check for package.json (Node.js)
    if (repo_path / "package.json").exists():
        stack["type"] = "nodejs"
        stack["languages"].append("javascript")
        stack["package_manager"] = "npm"
        try:
            with open(repo_path / "package.json") as f:
                pkg = json.load(f)
                if "dependencies" in pkg:
                    deps = list(pkg["dependencies"].keys())
                    if "react" in deps:
                        stack["frameworks"].append("react")
                    if "express" in deps:
                        stack["frameworks"].append("express")
                    if "next" in deps:
                        stack["frameworks"].append("next")
        except:
            pass
    
    # Check for requirements.txt (Python)
    elif (repo_path / "requirements.txt").exists():
        stack["type"] = "python"
        stack["languages"].append("python")
        stack["package_manager"] = "pip"
    
    # Check for Cargo.toml (Rust)
    elif (repo_path / "Cargo.toml").exists():
        stack["type"] = "rust"
        stack["languages"].append("rust")
        stack["package_manager"] = "cargo"
    
    # Check for go.mod (Go)
    elif (repo_path / "go.mod").exists():
        stack["type"] = "go"
        stack["languages"].append("go")
        stack["package_manager"] = "go"
    
    return stack

def find_insertion_points(repo_path: Path) -> List[Dict[str, str]]:
    """Find common insertion points for code"""
    insertion_points = []
    
    common_dirs = [
        "src", "lib", "app", "components", "pages", "routes",
        "scripts", "workers", "handlers", "controllers", "services"
    ]
    
    for dir_name in common_dirs:
        dir_path = repo_path / dir_name
        if dir_path.exists() and dir_path.is_dir():
            insertion_points.append({
                "path": dir_name,
                "type": "directory",
                "description": f"Code directory: {dir_name}"
            })
    
    # Check for test directories
    test_dirs = ["tests", "test", "__tests__", "spec"]
    for test_dir in test_dirs:
        test_path = repo_path / test_dir
        if test_path.exists():
            insertion_points.append({
                "path": test_dir,
                "type": "test_directory",
                "description": f"Test directory: {test_dir}"
            })
    
    return insertion_points

def generate_repo_map(repo_path: Path, output_path: Path):
    """Generate REPO_MAP.md"""
    stack = detect_stack(repo_path)
    insertion_points = find_insertion_points(repo_path)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    content = f"""# Repository Map
Generated: {timestamp}

## Stack
- Type: {stack['type']}
- Languages: {', '.join(stack['languages']) if stack['languages'] else 'Unknown'}
- Frameworks: {', '.join(stack['frameworks']) if stack['frameworks'] else 'None detected'}
- Package Manager: {stack['package_manager'] or 'Unknown'}

## Architecture
- Repository Type: {'Code repository' if stack['type'] != 'unknown' else 'Documentation repository'}
- Structure: Detected from file system

## Insertion Points

"""
    
    if insertion_points:
        for point in insertion_points:
            content += f"### {point['path']}\n"
            content += f"- Type: {point['type']}\n"
            content += f"- Description: {point['description']}\n\n"
    else:
        content += "No common insertion points detected. Repository may be empty or use non-standard structure.\n\n"
    
    content += """## Status
- ✅ Repository structure mapped
- ✅ Insertion points identified
- ✅ Stack detected

## Notes
This map is generated deterministically from repository contents.
Update manually if structure changes significantly.
"""
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ Generated: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Build repository map")
    parser.add_argument("--output", default="ai/context/REPO_MAP.md", help="Output file path")
    parser.add_argument("--repo", default=".", help="Repository root path")
    
    args = parser.parse_args()
    
    repo_path = Path(args.repo).resolve()
    output_path = repo_path / args.output
    
    generate_repo_map(repo_path, output_path)

if __name__ == "__main__":
    main()
