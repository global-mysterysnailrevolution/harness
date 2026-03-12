"""
Parses test output into structured failure records.
Used by the Ralph Loop to detect blocked conditions and analyze error patterns.
"""

import json
import re
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FailureRecord:
    name: str
    error_type: str   # "syntax" | "import" | "assertion" | "type" | "timeout" | "runtime"
    error_message: str
    file: str
    line: int
    signature: str    # normalized error fingerprint for BLOCKED detection


def classify_error_type(error_message: str) -> str:
    """Classify an error message into a category."""
    msg_lower = error_message.lower()

    if "syntaxerror" in msg_lower or "syntax error" in msg_lower:
        return "syntax"
    elif "importerror" in msg_lower or "modulenotfounderror" in msg_lower or "cannot import" in msg_lower:
        return "import"
    elif "assertionerror" in msg_lower or "assert " in msg_lower:
        return "assertion"
    elif "typeerror" in msg_lower or "attributeerror" in msg_lower:
        return "type"
    elif "timeout" in msg_lower or "timed out" in msg_lower:
        return "timeout"
    else:
        return "runtime"


def make_signature(error_message: str) -> str:
    """
    Create a normalized signature for error deduplication.
    Strips line numbers, memory addresses, and variable values
    to produce a stable fingerprint.
    """
    # Remove line numbers like "line 42" or ":42:"
    sig = re.sub(r'line \d+', 'line N', error_message)
    sig = re.sub(r':\d+:', ':N:', sig)
    # Remove memory addresses like 0x7f1234abcd
    sig = re.sub(r'0x[0-9a-fA-F]+', '0xADDR', sig)
    # Remove specific numeric values in assertions like "201 != 200"
    sig = re.sub(r'\b\d+\b', 'NUM', sig)
    # Truncate to first 200 chars for comparison
    return sig[:200].strip()


def analyze_failures(test_result: dict) -> dict:
    """
    Analyze a test result dict (from test_runner.py output) and produce
    a structured failure analysis.

    Returns:
    {
      "failure_records": [...],
      "error_types": {"syntax": 2, "import": 1, ...},
      "root_causes": [...],
      "consecutive_same_error": bool,
      "signatures": [...]
    }
    """
    failures = test_result.get("failures", [])
    records = []
    signatures = []
    error_type_counts = {}

    for f in failures:
        error_msg = f.get("error", "")
        error_type = classify_error_type(error_msg)
        sig = make_signature(error_msg)

        record = FailureRecord(
            name=f.get("name", "unknown"),
            error_type=error_type,
            error_message=error_msg,
            file=f.get("file", ""),
            line=f.get("line", 0),
            signature=sig
        )
        records.append(record)
        signatures.append(sig)
        error_type_counts[error_type] = error_type_counts.get(error_type, 0) + 1

    # Group failures by signature to identify shared root causes
    sig_groups: dict = {}
    for record in records:
        if record.signature not in sig_groups:
            sig_groups[record.signature] = []
        sig_groups[record.signature].append(record.name)

    root_causes = []
    for sig, test_names in sig_groups.items():
        if len(test_names) > 1:
            root_causes.append({
                "signature": sig,
                "affects_tests": test_names,
                "count": len(test_names),
                "likely_single_fix": True
            })
        else:
            root_causes.append({
                "signature": sig,
                "affects_tests": test_names,
                "count": 1,
                "likely_single_fix": False
            })

    return {
        "failure_records": [
            {
                "name": r.name,
                "error_type": r.error_type,
                "error_message": r.error_message[:300],
                "file": r.file,
                "line": r.line,
                "signature": r.signature
            }
            for r in records
        ],
        "error_types": error_type_counts,
        "root_causes": root_causes,
        "signatures": signatures,
        "total_failures": len(records)
    }


def detect_blocked(
    loop_history: list,
    blocked_threshold: int = 3
) -> dict:
    """
    Detect if the implementer is BLOCKED (same error on consecutive iterations).

    loop_history: list of {"iteration": N, "failure_signatures": [...]}

    Returns: {"blocked": bool, "blocking_signature": str | None, "consecutive_count": int}
    """
    if len(loop_history) < blocked_threshold:
        return {"blocked": False, "blocking_signature": None, "consecutive_count": 0}

    # Take the last `blocked_threshold` iterations
    recent = loop_history[-blocked_threshold:]

    # Check if any signature appears in all recent iterations
    if not all(h.get("failure_signatures") for h in recent):
        return {"blocked": False, "blocking_signature": None, "consecutive_count": 0}

    # Build sets of signatures per iteration
    sig_sets = [set(h["failure_signatures"]) for h in recent]

    # Find signatures present in ALL recent iterations
    common_sigs = sig_sets[0]
    for s in sig_sets[1:]:
        common_sigs = common_sigs & s

    if common_sigs:
        blocking_sig = next(iter(common_sigs))
        return {
            "blocked": True,
            "blocking_signature": blocking_sig,
            "consecutive_count": blocked_threshold
        }

    return {"blocked": False, "blocking_signature": None, "consecutive_count": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze test failures into structured records")
    parser.add_argument("--test-result", required=True, help="Path to test_runner.py JSON output")
    parser.add_argument("--loop-history", help="Path to loop state JSON (for BLOCKED detection)")
    parser.add_argument("--blocked-threshold", type=int, default=3)
    parser.add_argument("--output", help="Write analysis to file instead of stdout")
    args = parser.parse_args()

    test_result = json.loads(Path(args.test_result).read_text())
    analysis = analyze_failures(test_result)

    if args.loop_history and Path(args.loop_history).exists():
        loop_state = json.loads(Path(args.loop_history).read_text())
        history = loop_state.get("history", [])
        blocked_result = detect_blocked(history, args.blocked_threshold)
        analysis["blocked_detection"] = blocked_result

    output_json = json.dumps(analysis, indent=2)

    if args.output:
        Path(args.output).write_text(output_json)
    else:
        print(output_json)
