# Ralph Loop — OpenClaw Port

## 1. Overview

The Ralph Loop is Claude Code's iterative implementation pattern. Every implementer
agent in the Claude Code harness operates in a test-driven feedback loop rather
than making a single implementation pass.

The loop is named after the principle that "Ralph always tests his work." The
structure is:

```
implement → test → analyze failures → fix → retest → ... → done
```

Key properties of the Ralph Loop:

- **Failures are data**, not termination conditions. A failing test tells the
  implementer exactly what to fix next.
- **Max iterations are task-complexity-dependent**: trivial tasks (2 iterations),
  standard tasks (5 iterations), complex tasks (7 iterations).
- **PARTIAL results chain**: if the implementer achieves partial success (some
  tests pass, some fail) and reaches max iterations, the partial result is
  forwarded to a second implementer that starts from a working baseline.
- **BLOCKED results escalate**: if the implementer cannot make progress (same error
  on multiple consecutive iterations), it escalates to the user with a precise
  problem statement, not a vague "I couldn't do this."

The Ralph Loop is not a special mode — it is embedded in every implementer agent
prompt in the Claude Code harness. No implementer is allowed to make a single pass
and declare completion without running tests.

---

## 2. Problem Statement

OpenClaw's `builder_agent` (and any implementer skill) is single-pass:

1. Receive task
2. Write code
3. Report done

There is no testing step, no failure analysis, and no retry mechanism. The result:

- Generated code is not verified to work
- Syntax errors and logic bugs are reported as "complete" tasks
- The user must manually run tests and iterate
- There is no mechanism to distinguish "this needs one more fix" from "this is
  genuinely blocked"
- Partial implementations are not forwarded — they are either accepted or rejected
  wholesale

| Characteristic | Claude Code Ralph Loop | OpenClaw current |
|---|---|---|
| Test execution | Automatic after each implementation | None |
| Failure analysis | Structured per-iteration | None |
| Retry budget | 2-7 iterations | 1 attempt |
| PARTIAL result handling | Chains to second implementer | None |
| BLOCKED escalation | Explicit with problem statement | Vague failure |
| Complexity-aware budget | Yes | N/A |

The impact is significant: a 5-iteration Ralph Loop on a moderately complex task
typically reaches a working solution that a single-pass agent would produce broken
code for. The difference is not model capability — it is feedback integration.

---

## 3. Source Analysis

### 3.1 Ralph Loop Structure in Claude Code

Every implementer agent prompt in Claude Code contains a section structured like this:

```
## Implementation Loop

You MUST follow this loop. You are NOT allowed to declare a task complete
without running tests and seeing them pass.

### Loop Structure

Iteration 1:
  1. Read and understand the task fully.
  2. Implement the complete solution (or a reasonable first attempt).
  3. Run the test suite.
  4. Read ALL failures carefully.

Iterations 2-N:
  1. Analyze the failures from the previous iteration.
  2. Identify the root cause of each failure.
  3. Fix the root cause (not just the symptom).
  4. Re-run the tests.
  5. If all tests pass: declare COMPLETE.

### Exit Conditions

COMPLETE: All tests pass. Write result with status "complete".
PARTIAL: Some tests pass. Max iterations reached. Write result with status "partial".
  Include: which tests pass, which fail, what would be needed to fix the failures.
BLOCKED: Same test fails on 3+ consecutive iterations with no progress.
  Write result with status "blocked".
  Include: the exact error, what you tried, what you suspect the root cause is.

### Failure Analysis Protocol

For each failing test:
1. What is the error type? (syntax, import, assertion, timeout, type error)
2. Which line of YOUR code caused it?
3. Is this the root cause or a symptom of a deeper issue?
4. What is the minimal fix?

Never fix symptoms without understanding root causes. One root cause may explain
multiple test failures — fix the root cause, not each failure individually.
```

### 3.2 Complexity Classification

The implementer classifies task complexity before starting the loop to set the
appropriate iteration budget:

| Classification | Budget | Criteria |
|---|---|---|
| trivial | 2 | Single function, no external deps, <50 lines |
| standard | 5 | Multiple functions, some integration, 50-200 lines |
| complex | 7 | Cross-module, external services, >200 lines or architectural changes |

### 3.3 PARTIAL Result Chaining

When an implementer reaches max iterations with partial success, it writes a
structured handoff:

```json
{
  "status": "partial",
  "passing_tests": ["test_create_user", "test_get_user"],
  "failing_tests": ["test_delete_user", "test_update_user"],
  "handoff_context": {
    "what_works": "User creation and retrieval are fully implemented in src/users.ts",
    "what_is_broken": "Delete and update routes return 404 — router.delete() is not registered",
    "likely_fix": "Add router.delete('/:id', ...) and router.put('/:id', ...) in src/routes/users.ts"
  },
  "files_modified": ["src/users.ts", "src/routes/users.ts"]
}
```

The supervisor reads this handoff and spawns a second implementer with the partial
result as its starting context. The second implementer does not start from scratch —
it reads the handoff and focuses only on the failing cases.

### 3.4 BLOCKED Escalation

When the same test fails on 3 consecutive iterations with identical or very similar
errors, the implementer flags the task as BLOCKED:

```json
{
  "status": "blocked",
  "blocked_on": "Cannot resolve circular import between src/db.ts and src/models.ts",
  "iterations_attempted": 3,
  "error_history": [
    {"iteration": 1, "error": "SyntaxError: Cannot use import statement in a module"},
    {"iteration": 2, "error": "SyntaxError: Cannot use import statement in a module"},
    {"iteration": 3, "error": "SyntaxError: Cannot use import statement in a module"}
  ],
  "hypothesis": "The tsconfig.json may have conflicting module settings",
  "suggested_user_action": "Check tsconfig.json moduleResolution setting"
}
```

The supervisor receives a BLOCKED result and escalates to the user with the precise
problem statement, not a generic "the implementer failed."

---

## 4. Target Architecture

OpenClaw's implementer skill needs a Ralph Loop wrapper that:

1. Wraps the existing single-pass behavior in an iteration harness
2. Detects test results and classifies them
3. Maintains an iteration state file so the session can resume after interruption
4. Produces structured COMPLETE/PARTIAL/BLOCKED exit states
5. Supports handoff to a second implementer on PARTIAL

The port consists of:

1. **`ralph_loop_skill.md`** — the core iteration harness prompt
2. **`tools/test_runner.py`** — normalized test execution across different test
   frameworks (pytest, vitest, jest, go test, cargo test)
3. **`tools/failure_analyzer.py`** — parses test output into structured failure
   records
4. Modifications to `implementer_skill.md` to embed the Ralph Loop

### 4.1 Architecture Diagram

```
Task assigned to implementer
         │
         ▼
ralph_loop_skill.md
  ─ Classify complexity → set max_iterations
  ─ Write iteration state to .openclaw/tasks/{task_id}-loop.json
         │
         ▼
  Loop iteration N:
  ┌──────────────────────────────────────────────────┐
  │ 1. Implement (or fix from previous iteration)    │
  │ 2. Run tests via test_runner.py                  │
  │ 3. Parse results via failure_analyzer.py         │
  │ 4. Check exit conditions:                        │
  │    - All pass → COMPLETE                         │
  │    - N = max_iterations and some fail → PARTIAL  │
  │    - Same error 3x → BLOCKED                     │
  │ 5. Update loop state file                        │
  └──────────────────────────────────────────────────┘
         │
         ▼
  Exit: COMPLETE | PARTIAL | BLOCKED
         │
         ▼
  Write result to .openclaw/tasks/{task_id}-result.json
         │
  If PARTIAL → Supervisor spawns second implementer with handoff context
  If BLOCKED → Supervisor escalates to user with blocked report
```

---

## 5. File Layout

```
openclaw/
├── ralph_loop_skill.md            # NEW — iteration harness (to be embedded in implementer)
├── tools/
│   ├── test_runner.py             # NEW — multi-framework test executor
│   └── failure_analyzer.py        # NEW — parse test output into failure records
├── implementer_skill.md           # MODIFY — embed ralph_loop_skill content
├── supervisor_config.json         # MODIFY — enable ralph loop, set iteration budgets
└── agent_profiles.json            # MODIFY — add loop parameters to implementer profile

.openclaw/tasks/
└── {task_id}-loop.json            # RUNTIME — iteration state
```

---

## 6. Adaptation Strategy

### 6.1 No Native Test Runner

Claude Code's implementer runs tests via `Bash` (e.g., `pnpm test`, `pytest`,
`cargo test`). OpenClaw agents also have `Bash` access, so the same approach works.

The `test_runner.py` wrapper adds framework auto-detection and output normalization,
so the ralph loop skill does not need to know which test command to run — it just
calls `test_runner.py` and gets a structured result.

### 6.2 Iteration State Persistence

Claude Code's implementer maintains loop state in its own context window (it is a
sub-agent with a fresh context per task). OpenClaw sessions also have dedicated
context, but for long-running tasks that might get interrupted, the loop state
should also be persisted to disk.

The loop state file (`.openclaw/tasks/{task_id}-loop.json`) records:
- Current iteration number
- Results of each previous iteration (pass/fail counts, error summaries)
- Files modified in each iteration
- Detected failure patterns (for BLOCKED detection)

This enables resumability: if a session is interrupted at iteration 3, it can be
restarted and it will pick up from where it left off.

### 6.3 Test Framework Detection

OpenClaw works across different project types. The `test_runner.py` auto-detects
the framework by scanning for config files:

| Framework | Detection | Command |
|---|---|---|
| pytest | `pytest.ini`, `pyproject.toml[tool.pytest]`, `setup.cfg[tool:pytest]` | `pytest --tb=short -q` |
| vitest | `vitest.config.ts/js`, package.json `"test": "vitest"` | `npx vitest run --reporter=verbose` |
| jest | `jest.config.js/ts`, package.json `"jest": {}` | `npx jest --no-coverage` |
| go test | `go.mod` present | `go test ./... -v` |
| cargo test | `Cargo.toml` present | `cargo test 2>&1` |
| mocha | `package.json "mocha"` | `npx mocha` |

If no test framework is detected, the test runner attempts to infer from the
`package.json` `"scripts"."test"` field.

### 6.4 PARTIAL Chaining Without Native Agent Tool

Claude Code chains to a second implementer by spawning a sub-agent with the
handoff context. OpenClaw adaptation: when a task exits with PARTIAL status, the
orchestrator:

1. Reads the `handoff_context` from the result file
2. Creates a new task file for the second implementer that includes
   `"continuation_of": "{original_task_id}"` and the full handoff context
3. Dispatches a new implementer session

The second implementer reads the `continuation_of` field, loads the handoff context,
and focuses its work on the failing cases.

---

## 7. Implementation Plan

### Step 1: Create `test_runner.py`

```python
# openclaw/tools/test_runner.py
"""
Multi-framework test runner. Auto-detects framework and returns structured results.
"""

import subprocess
import os
import json
import re
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
    failures: list[dict]  # [{name, error, file, line}]
    raw_output: str

def detect_framework(project_root: str) -> tuple[str, list[str]]:
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
        pkg = json.loads(pkg_json.read_text())
        test_script = pkg.get("scripts", {}).get("test", "")
        if test_script and test_script != "echo \"Error: no test specified\"":
            return "npm", ["npm", "test", "--", "--no-coverage"]

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
            failures=[{"name": "no_test_framework", "error": "No test framework detected", "file": "", "line": 0}],
            raw_output=""
        )

    if test_path:
        cmd.append(test_path)

    import time
    start = time.time()

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=project_root,
        timeout=120
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

    # Parse individual failures: "FAILED tests/test_foo.py::test_bar - AssertionError: ..."
    for match in re.finditer(r'FAILED ([\w/._:-]+) - (.+?)(?=\nFAILED|\nERROR|\n\n|\Z)', output, re.DOTALL):
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

    # Parse failures: "● TestSuite > test name" followed by error
    for match in re.finditer(r'● (.+?)\n\n(.+?)(?=\n● |\nTest Suites:|\Z)', output, re.DOTALL):
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
                failures.append({"name": test_name.group(1), "error": "", "file": "", "line": 0})

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
    import argparse, sys
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--test-path")
    parser.add_argument("--output-file")
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
```

### Step 2: Create `ralph_loop_skill.md`

Full content in Section 8.

### Step 3: Modify `implementer_skill.md`

The ralph loop content replaces the existing "complete the task" instruction at
the bottom of `implementer_skill.md`. See Section 9 for the integration point.

---

## 8. Configuration

### `ralph_loop_skill.md` (complete file — embed in `implementer_skill.md`)

```markdown
# Ralph Loop — Iteration Harness

This section defines the mandatory iteration protocol for ALL implementation tasks.
You MUST follow this protocol. Single-pass implementation is not permitted.

## Step 0: Classify Complexity

Before writing any code, classify the task:

| Level | Budget | Criteria |
|-------|--------|----------|
| trivial | 2 | Single function, no external deps, <50 lines to write |
| standard | 5 | Multiple functions, some integration, 50-200 lines |
| complex | 7 | Cross-module, external services, >200 lines, architectural changes |

Write your classification and budget to the loop state file (see Loop State below).

## Step 1: First Implementation

Implement the complete solution on the first attempt. Do not hold back partial
implementations to "fix later" — write your best complete solution.

## Step 2: Run Tests

After EVERY implementation step (including the first), run:

```bash
python openclaw/tools/test_runner.py --root . --output-file /tmp/test-result-{ITERATION}.json
```

Read the result file. Never skip this step. Never declare completion without
seeing a passing test run.

## Step 3: Analyze Failures

For each entry in the `failures` array:

1. **Identify error type**: syntax | import | assertion | type | timeout | runtime
2. **Trace to your code**: which file and line in YOUR changes caused this?
3. **Find root cause**: is this the root cause or a symptom?
4. **Group related failures**: multiple failures may share one root cause

Write your analysis inline before writing any fix.

Example analysis:
```
Failure: test_create_user — AssertionError: 201 != 200
Root cause: Route returns 200 on create; test expects 201 (REST convention)
Fix: Change `return res.status(200).json(user)` to `return res.status(201).json(user)`
Related failures: None
```

## Step 4: Fix

Fix the root cause, not the symptom. If 3 tests fail due to a missing import,
add the import once — do not make 3 separate fixes.

Prefer minimal changes. The smallest fix that makes the test pass is the right fix.

## Step 5: Update Loop State

After each iteration, update `.openclaw/tasks/{TASK_ID}-loop.json`:

```json
{
  "task_id": "{task_id}",
  "complexity": "standard",
  "max_iterations": 5,
  "current_iteration": N,
  "history": [
    {
      "iteration": 1,
      "passed": 3,
      "failed": 2,
      "errors": 0,
      "failure_signatures": ["AssertionError: 201 != 200", "ImportError: cannot import 'x'"],
      "files_modified": ["src/routes/users.ts"]
    }
  ],
  "consecutive_same_error_count": 0,
  "status": "running"
}
```

## Step 6: Check Exit Conditions

After each test run:

**COMPLETE**: `failed == 0 and errors == 0`
- Set status "complete" in result file
- List all modified files

**BLOCKED**: Same failure signature appears in 3 consecutive iterations
- Set status "blocked"
- Include: exact error, what was tried, hypothesis about root cause

**PARTIAL**: `current_iteration == max_iterations and failed > 0 and passed > 0`
- Set status "partial"
- Include handoff context (see Handoff Format below)
- Do not despair — partial is progress

**FAILED**: `current_iteration == max_iterations and passed == 0`
- Set status "failed"
- Include: what was attempted, all errors encountered

## Handoff Format (for PARTIAL results)

```json
{
  "status": "partial",
  "passing_tests": ["list of passing test names"],
  "failing_tests": ["list of failing test names"],
  "handoff_context": {
    "what_works": "Describe what is working and why",
    "what_is_broken": "Describe exactly what is failing and the error",
    "likely_fix": "Your best hypothesis for what the next implementer should try",
    "relevant_files": ["files relevant to the fix"]
  },
  "files_modified": ["list of all files this agent modified"]
}
```

## Blocked Escalation Format

```json
{
  "status": "blocked",
  "blocked_on": "One-sentence description of the blocker",
  "iterations_attempted": N,
  "error_history": [
    {"iteration": 1, "error": "..."},
    {"iteration": 2, "error": "..."},
    {"iteration": 3, "error": "..."}
  ],
  "what_was_tried": ["attempt 1 description", "attempt 2 description"],
  "hypothesis": "What I think the root cause is",
  "suggested_user_action": "What the user would need to do to unblock this"
}
```

## Hard Rules

- NEVER declare COMPLETE without a passing test run.
- NEVER make more than 3 changes to the same file in one iteration (you are
  thrashing — step back and re-read the error more carefully).
- NEVER change the test to make it pass (unless the test itself is clearly wrong,
  in which case explain why in your analysis).
- If the test framework is not found, set status "blocked" with message
  "No test framework detected — cannot verify implementation."
```

### `supervisor_config.json` additions

```json
{
  "ralph_loop": {
    "enabled": true,
    "complexity_budgets": {
      "trivial": 2,
      "standard": 5,
      "complex": 7
    },
    "blocked_detection_threshold": 3,
    "partial_chaining_enabled": true,
    "max_chain_depth": 2,
    "test_runner": "openclaw/tools/test_runner.py"
  }
}
```

### `agent_profiles.json` additions to implementer

```json
{
  "implementer": {
    "description": "Ralph-loop implementer: implement → test → fix → repeat",
    "model": "claude-sonnet-4-5",
    "allowed_tools": [
      "Read",
      "Write",
      "Edit",
      "Bash",
      "Glob",
      "Grep"
    ],
    "bash_allowlist": [
      "python",
      "npx",
      "node",
      "npm",
      "pnpm",
      "go",
      "cargo",
      "pytest",
      "vitest",
      "jest",
      "cat",
      "ls",
      "mkdir",
      "touch"
    ],
    "ralph_loop": {
      "enabled": true,
      "state_file_pattern": ".openclaw/tasks/{task_id}-loop.json"
    }
  }
}
```

---

## 9. Integration Points

### `implementer_skill.md` Modification

Find the existing completion instruction in `implementer_skill.md` (the section
that says something like "When done, write the result to the task file") and
replace it with:

```markdown
## Completion Protocol

You MUST follow the Ralph Loop protocol defined in ralph_loop_skill.md.
The content of ralph_loop_skill.md is reproduced below and is MANDATORY.

[EMBED full content of ralph_loop_skill.md here]
```

The ralph loop is not a separate skill that is "called" — it is embedded directly
in the implementer prompt so it is always active.

### Orchestrator Prompt Addition

Add to `orchestrator_prompt.md`:

```markdown
## Handling Ralph Loop Results

After an implementer session completes, read its result file.

### If status == "complete":
- Surface the summary and modified files to the user.
- Continue with the next task in the plan.

### If status == "partial":
- Do NOT report this as a failure to the user yet.
- Read the `handoff_context` from the result file.
- Create a new task file for a second implementer:
  ```json
  {
    "task_id": "{original_task_id}-continuation",
    "continuation_of": "{original_task_id}",
    "goal": "{original goal}",
    "handoff": {handoff_context from partial result},
    "context": "This is a continuation. The previous implementer completed {passing_count}
                tests. Focus ONLY on the failing tests: {failing_tests}. The likely fix
                is: {likely_fix}. Start by reading {relevant_files}."
  }
  ```
- Dispatch the second implementer session.
- If the second implementer also returns "partial" or "failed": surface to user
  with full history from both implementers.

### If status == "blocked":
- Surface immediately to user with the blocked report.
- Do not retry automatically.
- Include the `suggested_user_action` in the message to the user.

### If status == "failed":
- Surface to user with error summary.
- Offer to retry with a different approach (user must confirm).
```

### Loop State File Location

All loop state files are stored at:
```
.openclaw/tasks/{task_id}-loop.json
```

The implementer creates this file on its first iteration and updates it after each
subsequent iteration. The orchestrator can read this file to report progress on
long-running tasks.

---

## 10. Testing Plan

### Unit Tests

```python
# tests/test_test_runner.py

import json
import pytest
from openclaw.tools.test_runner import detect_framework, _parse_pytest, _parse_jest_vitest

def test_detect_pytest_from_ini(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests")
    framework, cmd = detect_framework(str(tmp_path))
    assert framework == "pytest"

def test_detect_vitest_from_config(tmp_path):
    (tmp_path / "vitest.config.ts").write_text("export default {}")
    framework, cmd = detect_framework(str(tmp_path))
    assert framework == "vitest"

PYTEST_OUTPUT_PASSING = """
collected 5 items

test_users.py::test_create PASSED
test_users.py::test_get PASSED
test_users.py::test_list PASSED
test_users.py::test_update PASSED
test_users.py::test_delete PASSED

5 passed in 0.23s
"""

PYTEST_OUTPUT_FAILING = """
FAILED tests/test_users.py::test_update - AssertionError: 200 != 204
FAILED tests/test_users.py::test_delete - AssertionError: 200 != 204

3 passed, 2 failed in 0.31s
"""

def test_parse_pytest_all_pass():
    result = _parse_pytest(PYTEST_OUTPUT_PASSING, 0.23)
    assert result.passed == 5
    assert result.failed == 0

def test_parse_pytest_failures():
    result = _parse_pytest(PYTEST_OUTPUT_FAILING, 0.31)
    assert result.passed == 3
    assert result.failed == 2
    assert len(result.failures) == 2
    assert "AssertionError" in result.failures[0]["error"]
```

### Ralph Loop Integration Test

```bash
# Create a task with a deliberately broken implementation
mkdir -p /tmp/ralph-test/tests
cat > /tmp/ralph-test/src/math.py << 'EOF'
def add(a, b):
    return a - b  # Bug: should be a + b
EOF

cat > /tmp/ralph-test/tests/test_math.py << 'EOF'
from src.math import add

def test_add():
    assert add(2, 3) == 5

def test_add_negative():
    assert add(-1, 1) == 0
EOF

# Create task file
cat > .openclaw/tasks/math-fix-test.json << 'EOF'
{
  "task_id": "math-fix-test",
  "goal": "Fix the add function in src/math.py so all tests pass",
  "workspace_path": "/tmp/ralph-test"
}
EOF

# Run implementer with ralph loop
openclaw run --skill implementer_skill --task math-fix-test --profile implementer

# Verify loop state
cat .openclaw/tasks/math-fix-test-loop.json | python -m json.tool
# Expected: shows iteration history, final status "complete", 2 passed

# Verify fix was applied
cat /tmp/ralph-test/src/math.py
# Expected: return a + b
```

### PARTIAL Chaining Test

```bash
# Create a task where 50% of tests are straightforward and 50% are tricky
# Set max_iterations to 2 (trivial budget) to force PARTIAL exit
# Verify orchestrator creates continuation task
# Verify second implementer picks up from handoff
```

---

## 11. Example Usage

**Task**: "Implement a rate limiter middleware for the Express server that allows
100 requests per minute per IP address, with tests."

**Iteration 1 (Implement)**:
- Writes `src/middleware/rate-limiter.ts` using `express-rate-limit`
- Runs tests: 4 tests, 2 pass, 2 fail

**Failure analysis**:
```
Failure 1: test_rate_limit_header — AssertionError: undefined != "100"
  Root cause: Not setting X-RateLimit-Limit response header
  Fix: Add headers: true to express-rate-limit config

Failure 2: test_rate_limit_ip — AssertionError: window not sliding
  Root cause: Using fixed window, not sliding window
  Fix: This is a more fundamental design issue
```

**Iteration 2 (Fix)**:
- Adds `headers: true` to rate limiter config
- Switches to sliding window implementation
- Runs tests: 4 tests, 3 pass, 1 fail

**Failure analysis**:
```
Failure 1: test_rate_limit_ip — still failing
  Error: "Too Many Requests" after 98 requests, not 100
  Root cause: Off-by-one in the window counter initialization
  Fix: Change `max: 99` to `max: 100` (was accidentally lowered in iteration 2)
```

**Iteration 3 (Fix)**:
- Corrects `max: 100`
- Runs tests: 4 tests, 4 pass, 0 fail

**Exit: COMPLETE**

Result written:
```json
{
  "status": "complete",
  "iterations_used": 3,
  "complexity": "standard",
  "tests_passed": 4,
  "files_modified": ["src/middleware/rate-limiter.ts"],
  "summary": "Rate limiter implemented with sliding window, 100 req/min/IP, X-RateLimit headers included."
}
```
