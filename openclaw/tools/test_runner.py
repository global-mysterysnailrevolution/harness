"""
Multi-framework test runner. Auto-detects framework and returns structured results.
"""

import subprocess
import os
import json
import re
import time
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TestResult:
    framework: str
    passed: int
    failed: int
    errors: int
    skipped: int
    total: int
    duration_seconds: float
    failures: list  # [{name, error, file, line}]
    raw_output: str


def detect_framework(project_root: str) -> tuple:
    """Returns (framework_name, command_args)."""
    root = Path(project_root)

    # pytest
    if (root / "pytest.ini").exists() or (root / "conftest.py").exists():
        return "pytest", ["python", "-m", "pytest", "--tb=short", "-q", "--no-header"]

    if (root / "pyproject.toml").exists():
        content = (root / "pyproject.toml").read_text()
        if "[tool.pytest" in content:
            return "pytest", ["python", "-m", "pytest", "--tb=short", "-q", "--no-header"]

    # vitest
    for cfg in ["vitest.config.ts", "vitest.config.js", "vitest.config.mts"]:
        if (root / cfg).exists():
            return "vitest", ["npx", "vitest", "run", "--reporter=verbose"]

    # jest
    for cfg in ["jest.config.js", "jest.config.ts", "jest.config.mjs"]:
        if (root / cfg).exists():
            return "jest", ["npx", "jest", "--no-coverage", "--verbose"]

    # go test
    if (root / "go.mod").exists():
        return "go", ["go", "test", "./...", "-v", "-count=1"]

    # cargo test
    if (root / "Cargo.toml").exists():
        return "cargo", ["cargo", "test", "--", "--nocapture"]

    # package.json test script
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            test_script = pkg.get("scripts", {}).get("test", "")
            if test_script and test_script != "echo \"Error: no test specified\"":
                return "npm", ["npm", "test", "--", "--no-coverage"]
        except Exception:
            pass

    # Python unittest fallback
    if list(root.glob("**/test_*.py")):
        return "pytest", ["python", "-m", "pytest", "--tb=short", "-q"]

    return "unknown", []


def run_tests(project_root: str, test_path: Optional[str] = None) -> TestResult:
    """Run tests and return structured results."""
    framework, cmd = detect_framework(project_root)

    if framework == "unknown":
        return TestResult(
            framework="unknown", passed=0, failed=0, errors=0,
            skipped=0, total=0, duration_seconds=0.0,
            failures=[{"name": "no_test_framework", "error": "No test framework detected",
                       "file": "", "line": 0}],
            raw_output=""
        )

    if test_path:
        cmd = list(cmd)  # copy
        cmd.append(test_path)

    start = time.time()

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=120
        )
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return TestResult(
            framework=framework, passed=0, failed=0, errors=1,
            skipped=0, total=0, duration_seconds=duration,
            failures=[{"name": "timeout", "error": "Test suite timed out after 120s",
                       "file": "", "line": 0}],
            raw_output=""
        )

    duration = time.time() - start
    output = proc.stdout + proc.stderr

    return _parse_output(framework, output, duration)


def _parse_output(framework: str, output: str, duration: float) -> TestResult:
    if framework == "pytest":
        return _parse_pytest(output, duration)
    elif framework in ("vitest", "jest"):
        return _parse_jest_vitest(output, duration)
    elif framework == "go":
        return _parse_go(output, duration)
    elif framework == "cargo":
        return _parse_cargo(output, duration)
    else:
        # Generic: look for "N passed", "N failed" patterns
        return _parse_generic(output, duration, framework)


def _parse_pytest(output: str, duration: float) -> TestResult:
    failures = []
    passed = failed = errors = skipped = 0

    # Summary line: "5 passed, 2 failed, 1 error in 0.45s"
    summary = re.search(r'(\d+) passed', output)
    if summary:
        passed = int(summary.group(1))
    fail_match = re.search(r'(\d+) failed', output)
    if fail_match:
        failed = int(fail_match.group(1))
    err_match = re.search(r'(\d+) error', output)
    if err_match:
        errors = int(err_match.group(1))
    skip_match = re.search(r'(\d+) skipped', output)
    if skip_match:
        skipped = int(skip_match.group(1))

    # Parse individual failures
    for match in re.finditer(
        r'FAILED ([\w/._:-]+) - (.+?)(?=\nFAILED|\nERROR|\n\n|\Z)',
        output,
        re.DOTALL
    ):
        test_id = match.group(1)
        error_msg = match.group(2).strip()[:500]
        file_part = test_id.split("::")[0] if "::" in test_id else ""
        failures.append({
            "name": test_id,
            "error": error_msg,
            "file": file_part,
            "line": 0
        })

    return TestResult(
        framework="pytest",
        passed=passed, failed=failed + errors, errors=errors,
        skipped=skipped, total=passed + failed + errors + skipped,
        duration_seconds=duration, failures=failures, raw_output=output
    )


def _parse_jest_vitest(output: str, duration: float) -> TestResult:
    failures = []
    passed = failed = skipped = 0

    # Jest/Vitest summary: "Tests: 2 failed, 5 passed, 7 total"
    tests_match = re.search(r'Tests:\s*(.*?)$', output, re.MULTILINE)
    if tests_match:
        line = tests_match.group(1)
        p = re.search(r'(\d+) passed', line)
        f = re.search(r'(\d+) failed', line)
        s = re.search(r'(\d+) skipped', line)
        if p: passed = int(p.group(1))
        if f: failed = int(f.group(1))
        if s: skipped = int(s.group(1))

    # Parse failures: "- TestSuite > test name" followed by error
    for match in re.finditer(
        r'- (.+?)\n\n(.+?)(?=\n- |\nTest Suites:|\Z)',
        output,
        re.DOTALL
    ):
        test_name = match.group(1).strip()
        error_msg = match.group(2).strip()[:500]
        failures.append({
            "name": test_name,
            "error": error_msg,
            "file": "",
            "line": 0
        })

    return TestResult(
        framework="vitest/jest",
        passed=passed, failed=failed, errors=0,
        skipped=skipped, total=passed + failed + skipped,
        duration_seconds=duration, failures=failures, raw_output=output
    )


def _parse_go(output: str, duration: float) -> TestResult:
    failures = []
    passed = failed = 0

    for line in output.split("\n"):
        if line.startswith("--- PASS"):
            passed += 1
        elif line.startswith("--- FAIL"):
            failed += 1
            test_name = re.search(r'--- FAIL: (\S+)', line)
            if test_name:
                failures.append({"name": test_name.group(1), "error": "",
                                  "file": "", "line": 0})

    return TestResult(
        framework="go", passed=passed, failed=failed, errors=0,
        skipped=0, total=passed + failed,
        duration_seconds=duration, failures=failures, raw_output=output
    )


def _parse_cargo(output: str, duration: float) -> TestResult:
    passed = failed = 0
    failures = []

    match = re.search(r'test result: \w+\. (\d+) passed; (\d+) failed', output)
    if match:
        passed = int(match.group(1))
        failed = int(match.group(2))

    for line in output.split("\n"):
        if "FAILED" in line and "test result" not in line:
            test_name = line.split("...")[0].strip() if "..." in line else line.strip()
            failures.append({"name": test_name, "error": "", "file": "", "line": 0})

    return TestResult(
        framework="cargo", passed=passed, failed=failed, errors=0,
        skipped=0, total=passed + failed,
        duration_seconds=duration, failures=failures, raw_output=output
    )


def _parse_generic(output: str, duration: float, framework: str) -> TestResult:
    passed = len(re.findall(r'\bpass(ed|ing)?\b', output, re.IGNORECASE))
    failed = len(re.findall(r'\bfail(ed|ing|ure)?\b', output, re.IGNORECASE))
    return TestResult(
        framework=framework, passed=passed, failed=failed, errors=0,
        skipped=0, total=passed + failed,
        duration_seconds=duration, failures=[], raw_output=output[:2000]
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-framework test runner")
    parser.add_argument("--root", required=True, help="Project root directory")
    parser.add_argument("--test-path", help="Specific test file or directory")
    parser.add_argument("--output-file", help="Write JSON results to file")
    args = parser.parse_args()

    result = run_tests(args.root, args.test_path)
    data = {
        "framework": result.framework,
        "passed": result.passed,
        "failed": result.failed,
        "errors": result.errors,
        "skipped": result.skipped,
        "total": result.total,
        "duration": result.duration_seconds,
        "failures": result.failures
    }

    if args.output_file:
        Path(args.output_file).write_text(json.dumps(data, indent=2))
    else:
        print(json.dumps(data, indent=2))

    sys.exit(0 if result.failed == 0 and result.errors == 0 else 1)
