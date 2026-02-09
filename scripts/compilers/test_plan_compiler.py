#!/usr/bin/env python3
"""
Test Plan Compiler
Generates TEST_PLAN.md from test analysis
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

def generate_test_plan(log_path: Path, output_path: Path, framework: str):
    """Generate test plan from raw test log"""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Read raw log if exists
    test_info = []
    if log_path.exists():
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip() and not line.startswith('==='):
                    test_info.append(line.strip())
    
    content = f"""# Test Plan
Generated: {timestamp}

## Framework
{framework}

## Test Strategy

### Unit Tests
- [ ] Core functionality tests
- [ ] Edge case handling
- [ ] Error handling
- [ ] Input validation

### Integration Tests
- [ ] Component integration
- [ ] API integration
- [ ] Database integration (if applicable)
- [ ] External service integration (if applicable)

### End-to-End Tests
- [ ] User workflows
- [ ] Critical paths
- [ ] Error scenarios

## Test Coverage Goals
- Unit test coverage: >80%
- Integration test coverage: >60%
- E2E test coverage: Critical paths only

## Test Implementation Notes

"""
    
    if test_info:
        content += "### Recent Test Activity\n\n"
        for info in test_info[-20:]:  # Last 20 entries
            content += f"- {info}\n"
    else:
        content += "No test activity recorded yet.\n"
    
    content += f"""

## Framework-Specific Notes

"""
    
    if framework == "jest":
        content += "- Use `describe` and `it` blocks\n"
        content += "- Place tests in `__tests__` or `.test.js` files\n"
        content += "- Use `expect()` for assertions\n"
    elif framework == "pytest":
        content += "- Use `pytest` fixtures for setup\n"
        content += "- Place tests in `tests/` directory\n"
        content += "- Use `assert` statements\n"
    elif framework == "mocha":
        content += "- Use `describe` and `it` blocks\n"
        content += "- Use assertion library (chai, etc.)\n"
    else:
        content += f"- Framework: {framework}\n"
        content += "- Follow framework conventions\n"
    
    content += f"""

## Status
- Test plan: Generated
- Implementation: Pending
- Coverage: Not yet measured

## Last Updated
{timestamp}
"""
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ Generated: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Test plan compiler")
    parser.add_argument("--input", required=True, help="Input test log")
    parser.add_argument("--output", default="ai/tests/TEST_PLAN.md", help="Output file path")
    parser.add_argument("--framework", default="unknown", help="Test framework")
    parser.add_argument("--repo", default=".", help="Repository root path")
    
    args = parser.parse_args()
    
    repo_path = Path(args.repo).resolve()
    input_path = Path(args.input).resolve()
    output_path = repo_path / args.output
    
    generate_test_plan(input_path, output_path, args.framework)

if __name__ == "__main__":
    main()
