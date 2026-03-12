<!-- SKILL: ralph_loop | TRIGGER: internal | DESC: Iterative implementation harness with test-driven feedback loop -->

# Ralph Loop -- Iteration Harness

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
implementations to "fix later" -- write your best complete solution.

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
Failure: test_create_user -- AssertionError: 201 != 200
Root cause: Route returns 200 on create; test expects 201 (REST convention)
Fix: Change `return res.status(200).json(user)` to `return res.status(201).json(user)`
Related failures: None
```

## Step 4: Fix

Fix the root cause, not the symptom. If 3 tests fail due to a missing import,
add the import once -- do not make 3 separate fixes.

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
- Do not despair -- partial is progress

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
  thrashing -- step back and re-read the error more carefully).
- NEVER change the test to make it pass (unless the test itself is clearly wrong,
  in which case explain why in your analysis).
- If the test framework is not found, set status "blocked" with message
  "No test framework detected -- cannot verify implementation."
