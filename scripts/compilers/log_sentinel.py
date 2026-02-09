#!/usr/bin/env python3
"""
Log Sentinel Compiler
Processes server logs and generates LOG_FINDINGS.md
"""

import os
import sys
import argparse
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict

def analyze_logs(log_path: Path) -> Dict[str, any]:
    """Analyze logs for anomalies"""
    anomalies = []
    error_count = 0
    warning_count = 0
    fatal_count = 0
    
    error_patterns = [
        (r'error|Error|ERROR', 'error'),
        (r'exception|Exception|EXCEPTION', 'exception'),
        (r'fatal|Fatal|FATAL', 'fatal'),
        (r'stack trace|Stack Trace', 'stack_trace'),
        (r'warning|Warning|WARNING', 'warning')
    ]
    
    if not log_path.exists():
        return {
            'anomalies': [],
            'error_count': 0,
            'warning_count': 0,
            'fatal_count': 0,
            'total_lines': 0
        }
    
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines, 1):
        for pattern, category in error_patterns:
            if re.search(pattern, line):
                if category == 'error':
                    error_count += 1
                elif category == 'warning':
                    warning_count += 1
                elif category == 'fatal':
                    fatal_count += 1
                
                anomalies.append({
                    'line_number': i,
                    'category': category,
                    'content': line.strip()[:200],  # Limit length
                    'timestamp': extract_timestamp(line)
                })
    
    return {
        'anomalies': anomalies[-100:],  # Last 100 anomalies
        'error_count': error_count,
        'warning_count': warning_count,
        'fatal_count': fatal_count,
        'total_lines': len(lines)
    }

def extract_timestamp(line: str) -> str:
    """Extract timestamp from log line"""
    # Common timestamp patterns
    patterns = [
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',
        r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})',
        r'\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return match.group(1)
    
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def generate_findings(data: Dict, output_path: Path):
    """Generate LOG_FINDINGS.md"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    content = f"""# Log Findings
Generated: {timestamp}

## Summary
- Total lines analyzed: {data['total_lines']}
- Errors detected: {data['error_count']}
- Warnings detected: {data['warning_count']}
- Fatal errors: {data['fatal_count']}
- Total anomalies: {len(data['anomalies'])}

## Anomalies

"""
    
    if data['anomalies']:
        # Group by category
        by_category = {}
        for anomaly in data['anomalies']:
            cat = anomaly['category']
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(anomaly)
        
        for category, items in by_category.items():
            content += f"### {category.upper()}\n\n"
            for item in items[:20]:  # Limit per category
                content += f"**Line {item['line_number']}** ({item['timestamp']}):\n"
                content += f"```\n{item['content']}\n```\n\n"
            if len(items) > 20:
                content += f"*... {len(items) - 20} more {category} entries*\n\n"
    else:
        content += "No anomalies detected.\n\n"
    
    content += f"""## Recommendations

"""
    
    if data['error_count'] > 0:
        content += "1. **Review errors**: Check error messages above for root causes\n"
        content += "2. **Check dependencies**: Verify all dependencies are installed\n"
        content += "3. **Review configuration**: Check environment variables and config files\n\n"
    
    if data['fatal_count'] > 0:
        content += "⚠️ **Fatal errors detected**: Server may not be running correctly\n\n"
    
    if data['warning_count'] > 10:
        content += "⚠️ **High warning count**: Review warnings for potential issues\n\n"
    
    if len(data['anomalies']) == 0:
        content += "✅ No issues detected. Server appears to be running normally.\n\n"
    
    content += f"""
## Notes
- Log analysis is performed automatically by the harness
- Review `ai/context/raw_server.log` for complete log history
- Anomalies are detected using pattern matching

## Last Updated
{timestamp}
"""
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ Generated: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Log sentinel compiler")
    parser.add_argument("--input", required=True, help="Input log file")
    parser.add_argument("--output", default="ai/context/LOG_FINDINGS.md", help="Output file path")
    parser.add_argument("--repo", default=".", help="Repository root path")
    
    args = parser.parse_args()
    
    repo_path = Path(args.repo).resolve()
    input_path = Path(args.input).resolve()
    output_path = repo_path / args.output
    
    data = analyze_logs(input_path)
    generate_findings(data, output_path)

if __name__ == "__main__":
    main()
