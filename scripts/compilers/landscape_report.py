#!/usr/bin/env python3
"""
Landscape Report Compiler
Compiles landscape research into structured JSON report
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

LANDSCAPE_REPORT_SCHEMA = {
    "type": "object",
    "required": ["problem_statement", "must_have_capabilities", "constraints", 
                "closest_existing_solutions", "recommended_path"],
    "properties": {
        "problem_statement": {"type": "string"},
        "must_have_capabilities": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "object"},
        "closest_existing_solutions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "type", "covers_percent"],
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["oss", "product", "paper"]},
                    "covers_percent": {"type": "number", "minimum": 0, "maximum": 100},
                    "why_it_fits": {"type": "string"},
                    "gaps": {"type": "array", "items": {"type": "string"}},
                    "links": {"type": "array", "items": {"type": "string"}}
                }
            },
            "minItems": 1
        },
        "state_of_the_art": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "what_is_new": {"type": "string"},
                    "why_relevant": {"type": "string"},
                    "links": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        "recommended_path": {"type": "string", "enum": ["adopt", "extend", "build"]},
        "reuse_plan": {
            "type": "object",
            "properties": {
                "base": {"type": "string"},
                "extensions": {"type": "array", "items": {"type": "string"}},
                "integration_steps": {"type": "array", "items": {"type": "string"}}
            }
        },
        "build_justification": {
            "type": "array",
            "items": {"type": "string"}
        },
        "risks": {"type": "array", "items": {"type": "string"}},
        "stop_conditions": {"type": "array", "items": {"type": "string"}}
    }
}

def validate_landscape_report(report: Dict) -> tuple[bool, List[str]]:
    """Validate landscape report against schema"""
    errors = []
    
    # Check required fields
    required = LANDSCAPE_REPORT_SCHEMA["required"]
    for field in required:
        if field not in report:
            errors.append(f"Missing required field: {field}")
    
    # Check recommended_path
    if "recommended_path" in report:
        if report["recommended_path"] not in ["adopt", "extend", "build"]:
            errors.append(f"Invalid recommended_path: {report['recommended_path']}")
    
    # Check closest_existing_solutions
    if "closest_existing_solutions" in report:
        solutions = report["closest_existing_solutions"]
        if len(solutions) < 1:
            errors.append("Must have at least 1 solution in closest_existing_solutions")
        
        for i, sol in enumerate(solutions):
            if "name" not in sol:
                errors.append(f"Solution {i} missing 'name'")
            if "type" not in sol:
                errors.append(f"Solution {i} missing 'type'")
            elif sol["type"] not in ["oss", "product", "paper"]:
                errors.append(f"Solution {i} has invalid type: {sol['type']}")
            if "covers_percent" not in sol:
                errors.append(f"Solution {i} missing 'covers_percent'")
            elif not (0 <= sol["covers_percent"] <= 100):
                errors.append(f"Solution {i} covers_percent must be 0-100")
    
    # Check build_justification requirement
    if report.get("recommended_path") == "build":
        if "build_justification" not in report or not report["build_justification"]:
            errors.append("build_justification required when recommended_path is 'build'")
        if len(report.get("closest_existing_solutions", [])) < 2:
            errors.append("Must analyze at least 2 existing solutions before recommending 'build'")
    
    return len(errors) == 0, errors

def compile_landscape_report(input_data: Dict, output_path: Path):
    """Compile landscape report from input data"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Add metadata
    report = {
        "generated": timestamp,
        **input_data
    }
    
    # Validate
    is_valid, errors = validate_landscape_report(report)
    
    if not is_valid:
        error_msg = "Landscape report validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)
    
    # Ensure minimum 3 solutions (if not build path)
    if report.get("recommended_path") != "build":
        solutions = report.get("closest_existing_solutions", [])
        if len(solutions) < 3:
            print(f"Warning: Only {len(solutions)} solutions found. Recommended: 3+")
    
    # Write report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Generated landscape report: {output_path}")
    print(f"  Recommended path: {report.get('recommended_path', 'unknown')}")
    print(f"  Solutions analyzed: {len(report.get('closest_existing_solutions', []))}")

def main():
    parser = argparse.ArgumentParser(description="Compile landscape report")
    parser.add_argument("--input", required=True, help="Input JSON file or raw JSON string")
    parser.add_argument("--output", default="ai/research/landscape_reports/landscape_report.json",
                       help="Output file path")
    parser.add_argument("--repo", default=".", help="Repository root path")
    
    args = parser.parse_args()
    
    repo_path = Path(args.repo).resolve()
    input_path = Path(args.input)
    output_path = repo_path / args.output
    
    # Parse input
    if input_path.exists():
        with open(input_path, 'r', encoding='utf-8') as f:
            input_data = json.load(f)
    else:
        # Try parsing as JSON string
        try:
            input_data = json.loads(args.input)
        except:
            raise ValueError(f"Input must be a file path or valid JSON string: {args.input}")
    
    compile_landscape_report(input_data, output_path)

if __name__ == "__main__":
    main()
