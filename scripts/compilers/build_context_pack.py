#!/usr/bin/env python3
"""
Deterministic Context Pack Compiler
Generates CONTEXT_PACK.md from context artifacts
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

def compile_context_pack(repo_path: Path, output_path: Path, input_file: Path = None):
    """Compile context pack from various sources"""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Read REPO_MAP if exists
    repo_map = ""
    repo_map_path = repo_path / "ai/context/REPO_MAP.md"
    if repo_map_path.exists():
        with open(repo_map_path, 'r', encoding='utf-8') as f:
            repo_map = f.read()
    
    # Read feature research if exists
    feature_research = ""
    research_path = repo_path / "ai/context/FEATURE_RESEARCH.md"
    if research_path.exists():
        with open(research_path, 'r', encoding='utf-8') as f:
            feature_research = f.read()
    
    # Read input file if provided
    input_content = ""
    if input_file and input_file.exists():
        with open(input_file, 'r', encoding='utf-8') as f:
            input_content = f.read()
    
    content = f"""# Context Pack
Generated: {timestamp}

## Purpose
This context pack provides essential information for AI agents working with this repository.

## Repository Overview

**Stack**: Detected from repository structure
**Architecture**: See REPO_MAP.md for details

## Key Context

### Repository Structure
"""
    
    if repo_map:
        # Extract key info from repo map
        lines = repo_map.split('\n')
        in_stack = False
        for line in lines:
            if '## Stack' in line:
                in_stack = True
            if in_stack and line.strip() and not line.startswith('#'):
                content += f"{line}\n"
            if in_stack and line.startswith('##') and 'Stack' not in line:
                break
    else:
        content += "Repository structure not yet mapped. Run context priming.\n"
    
    content += "\n### Feature Research\n\n"
    
    if feature_research:
        content += feature_research[:1000]  # Limit size
        if len(feature_research) > 1000:
            content += "\n\n[... truncated - see FEATURE_RESEARCH.md for full content]\n"
    else:
        content += "No feature research available yet.\n"
    
    if input_content:
        content += "\n### Additional Context\n\n"
        content += input_content[:500]  # Limit size
    
    content += f"""

## Agent Guidelines

### Before Making Changes
1. ✅ Consult `ai/context/REPO_MAP.md` for structure
2. ✅ Review `ai/context/CONTEXT_PACK.md` for context (this file)
3. ✅ Check `ai/memory/WORKING_MEMORY.md` for recent state
4. ✅ Verify no locks in `ai/_locks/` for target files

### During Operations
- Use parallel workers when appropriate
- Follow safety gates for sensitive operations
- Checkpoint memory after significant changes

### After Operations
- Update `ai/memory/WORKING_MEMORY.md` with new state
- Run validation tests if applicable
- Document changes in appropriate context files

## Status
- ✅ Context pack ready
- ✅ Guidelines defined
- ✅ Safety gates documented

## Last Updated
{timestamp}
"""
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ Generated: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Build context pack")
    parser.add_argument("--output", default="ai/context/CONTEXT_PACK.md", help="Output file path")
    parser.add_argument("--input", help="Input file to include")
    parser.add_argument("--repo", default=".", help="Repository root path")
    
    args = parser.parse_args()
    
    repo_path = Path(args.repo).resolve()
    output_path = repo_path / args.output
    input_file = Path(args.input).resolve() if args.input else None
    
    compile_context_pack(repo_path, output_path, input_file)

if __name__ == "__main__":
    main()
