# Test Writer Agent: Porting Guide (OpenClaw to Claude Code)

**Status**: Implementation reference
**Target files**: `~/.claude/agents/test-writer.md`, `~/.claude/commands/go.md` (Phase 5 modification)
**Source system**: OpenClaw `.claude/agents/test-writer.md` + `scripts/compilers/test_plan_compiler.py` + `scripts/workers/test_writer.ps1`

---

## 1. Overview

The test-writer agent is a dedicated Claude Code subagent that writes tests for new or modified source code. It runs as a **Phase 5 sidecar** inside the `/go` pipeline — spawned in the background at the same time as the implementer so that test files are written in parallel with feature code, not after.

The agent:
- Detects the project's test framework from `intake.json` or by scanning project files directly
- Reads the source files the implementer produces or modifies
- Identifies public API surface (exported functions, classes, route handlers, React components, etc.)
- Studies existing test files in the project to match style and structure
- Writes the corresponding test file(s) into the correct test directory
- Runs the new tests to verify they pass (or reports what failed)
- Writes a `TEST_PLAN.md` and `COVERAGE_NOTES.md` to `ai/tests/`

The agent is **test-file only**. It never modifies source files. This keeps it safe to run alongside the implementer without merge conflicts.

---

## 2. Problem Statement

### The coverage gap

The current `/go` pipeline has a Ralph-loop implementer (`~/.claude/agents/implementer.md`) that iterates on implementation until tests pass. But it only runs **existing** tests. It does not write new tests for new code.

The practical result: every new feature, endpoint, utility function, or component that enters the codebase through `/go` has zero test coverage unless the user explicitly asks for it. This is the gap.

### Why this matters in practice

Consider a typical `/go` invocation:

```
/go add a POST /api/shipments endpoint that validates payload with Zod and stores to the DB
```

The implementer runs. It creates `routes/shipments.ts`, validates the schema, writes a handler, and runs the existing test suite. The existing tests pass because they do not touch `shipments.ts`. The pipeline reports DONE. The new endpoint has no tests.

The only path to coverage today is a second `/go` invocation explicitly asking for tests, or a human noticing the gap.

### What OpenClaw does differently

OpenClaw's `test_writer.ps1` worker runs in parallel with feature implementation via PowerShell background jobs. It detects the active framework, appends an activity log entry, and calls `test_plan_compiler.py` to regenerate `TEST_PLAN.md`. The OpenClaw approach is file-system coordination: the worker watches for non-test source file edits as a trigger signal.

The limitation is that OpenClaw's worker is a **plan generator**, not a **test writer**. It produces a structured TODO list in `TEST_PLAN.md` but does not write actual test code. The real test writing was left to a follow-on agent call.

### What the Claude Code port does better

The Claude Code port skips the intermediate plan and goes straight to writing test code. The agent:
1. Receives the list of new/modified source files from the implementer's plan
2. Reads those files and the existing test patterns
3. Writes actual test code — not a plan
4. Runs the tests
5. Writes `TEST_PLAN.md` and `COVERAGE_NOTES.md` as byproducts of what it already did

This collapses the two-step (plan then write) pattern into one step that produces both tests and documentation.

---

## 3. Source Analysis

### 3.1 OpenClaw agent definition (`.claude/agents/test-writer.md`)

The OpenClaw agent definition is brief. It describes responsibilities but contains no execution logic:

```
Responsibilities:
- Detect test framework from repository
- Identify test conventions and patterns
- Write unit tests alongside implementation
- Write integration tests
- Maintain TEST_PLAN.md and COVERAGE_NOTES.md
- Run fast test subsets when possible

Trigger:
- Runs automatically when feature implementation detected
- Detection: feature branch, PRD file, or non-test source file edits
- Runs in parallel with main feature implementation
```

The agent depends on `scripts/compilers/test_plan_compiler.py` for plan generation. The actual test-writing logic was expected to be executed by a separate agent invocation using the plan as input.

Key extraction: the **trigger condition** (non-test source file edit) and the **output contract** (`TEST_PLAN.md`, `COVERAGE_NOTES.md`, actual test files in repo test dirs).

### 3.2 Test plan compiler (`scripts/compilers/test_plan_compiler.py`)

The compiler generates a structured Markdown plan from a raw log file. Relevant logic:

- **Framework branching**: separate notes for jest (`describe`/`it`, `__tests__` dirs), pytest (fixtures, `tests/` dir), mocha (assertion libraries). This is the framework-specific guidance the test-writer agent needs.
- **Coverage targets**: unit >80%, integration >60%, e2e critical paths only. These are the canonical targets to carry forward.
- **Section structure**: Unit Tests / Integration Tests / End-to-End Tests with checklist items. This structure maps directly to how the agent should organize its work.

The compiler's framework detection (`jest`, `pytest`, `mocha`, `unknown`) is thin — it receives the framework as a CLI argument from the worker. The detection logic lives in the worker.

### 3.3 Worker script (`scripts/workers/test_writer.ps1`)

This is where the framework detection logic lives. It checks in order:

1. `package.json` devDependencies: `jest` then `mocha` then `vitest`
2. `pytest.ini` or `test_*.py` files
3. `Cargo.toml`

Additional patterns extracted for the Claude Code port:
- **Lock file coordination**: `ai/_locks/test_writer.lock` prevents concurrent runs. In Claude Code the isolation is structural (test-writer writes only test files), but the lock concept informs the single-sidecar-per-run design.
- **Log file**: `ai/tests/raw_test_plan.log` as append-only audit trail. Preserved.
- **Coverage notes**: a quick Markdown file noting framework, test dir, and current coverage status.

---

## 4. Target Architecture

### Agent role in the harness

The test-writer is a **sidecar agent** — non-blocking, runs in the background while the main implementer executes. It is spawned at the start of Phase 5c, receives the implementer's planned output via its context pack, and completes independently.

```
Phase 5c execution (build task):

  Agent(implementer, worktree): Ralph loop               <- main pipeline
  Agent(test-writer, background): write tests            <- sidecar (this agent)
    -> runs_in_background: true
    -> does NOT block implementer
    -> does NOT modify source files (only test files)
    -> completes when tests are written and verified

  Main pipeline waits for implementer (DONE/PARTIAL/BLOCKED)
  At Phase 6: fold in test-writer results
```

### Information flow

The test-writer needs to know:
1. Which source files the implementer is creating or modifying
2. What test framework the project uses
3. Where test files live (test directory conventions)
4. What existing tests look like (style, structure, assertion patterns)

This information is passed via a context pack assembled inline before the sidecar is spawned. The implementer's planned changes (from the planning agent in Phase 5c) are included in this context pack.

### Output contract

The test-writer agent produces:
- One or more test files written directly to the project's test directory
- `ai/tests/TEST_PLAN.md` — what tests were written and why
- `ai/tests/COVERAGE_NOTES.md` — framework, test dir, coverage status
- A structured report (same format as the implementer) returned to the supervisor

### Isolation contract

The test-writer MUST NOT:
- Write to any source file (only `*.test.*`, `*_test.*`, `*.spec.*`, or files inside `tests/`, `__tests__/`, `spec/` directories)
- Modify build configuration
- Install new dependencies
- Change the test runner configuration

These restrictions are stated explicitly in the agent prompt and enforced via self-policing. The agent prompt includes a hard stop: "If you find yourself about to write to any other path, stop and skip it."

---

## 5. File Layout

Files to **create**:

```
~/.claude/agents/test-writer.md          <- new agent definition (Section 6)
```

Files to **modify**:

```
~/.claude/commands/go.md                  <- add test-writer sidecar to Phase 5c (Section 9)
~/.claude/CLAUDE.md                       <- add test-writer row to agents table (Section 11)
```

Files the agent produces at runtime (per project):

```
{project}/ai/tests/TEST_PLAN.md           <- generated test plan
{project}/ai/tests/COVERAGE_NOTES.md      <- coverage status
{project}/ai/tests/raw_test_plan.log      <- append-only audit log
{project}/**/*.test.ts                    <- (or .test.js, _test.py, etc.)
{project}/**/tests/*.py                   <- (pytest convention)
{project}/**/__tests__/*.ts               <- (jest __tests__ convention)
```

---

## 6. Agent Definition

Complete content of `~/.claude/agents/test-writer.md`:

```markdown
---
name: test-writer
description: >
  Writes tests in parallel with feature implementation. Reads new/modified source
  files from the implementer's plan, detects project test framework, studies
  existing test patterns, and writes matching test files. Runs tests to verify
  they pass. Writes TEST_PLAN.md and COVERAGE_NOTES.md. Sidecar agent — never
  modifies source files, only test files.
tools: [Read, Write, Bash, Glob, Grep]
model: sonnet
---

# Test Writer Agent

You write tests for new code in parallel with the implementer.
You run as a sidecar — non-blocking, test files only.

## Your Single Constraint

**You MUST NOT modify any source file.**

You write ONLY:
- Files matching `*.test.ts`, `*.test.js`, `*.test.tsx`, `*.spec.ts`, `*.spec.js`
- Files matching `*_test.py`, `test_*.py`
- Files inside `tests/`, `__tests__/`, `spec/`, `test/` directories
- `ai/tests/TEST_PLAN.md`
- `ai/tests/COVERAGE_NOTES.md`
- `ai/tests/raw_test_plan.log`

If you find yourself about to write to any other path, stop and skip it.

## Process

### Step 1: Orient (read your context pack)

Your context pack contains:
- `FRAMEWORK`: the detected test framework (jest / vitest / pytest / mocha / rust / unknown)
- `SOURCE_FILES`: list of new or modified source files from the implementer's plan
- `TEST_DIR`: detected test directory (e.g., `tests/`, `__tests__/`, `src/__tests__/`)
- `TEST_CMD`: the command to run tests (from intake.json)
- `PROJECT_ROOT`: absolute path to the project root

If any of these are missing, detect them yourself (Step 2).

### Step 2: Framework Detection (if not in context pack)

Run these checks in order:

```bash
# JavaScript/TypeScript
cat package.json 2>/dev/null | grep -E '"jest"|"vitest"|"mocha"|"jasmine"'

# Python
ls pytest.ini setup.cfg pyproject.toml 2>/dev/null
find . -name "test_*.py" -maxdepth 3 | head -5

# Rust
cat Cargo.toml 2>/dev/null | grep -A 10 "dev-dependencies"

# Go
find . -name "*_test.go" -maxdepth 3 | head -5
```

Framework priority (if multiple signals):
1. vitest — if `vitest` in package.json devDependencies or scripts
2. jest — if `jest` in devDependencies (and not vitest)
3. pytest — if pytest.ini, pyproject.toml with pytest config, or test_*.py files
4. mocha — if `mocha` in devDependencies
5. rust — if Cargo.toml exists
6. go test — if *_test.go files found
7. unknown — read existing test files and mimic them exactly

### Step 3: Find Existing Test Patterns

Before writing any tests, study how the project's existing tests are structured.

```bash
find . -name "*.test.ts" -o -name "*.test.js" -o -name "test_*.py" \
  -o -name "*_test.go" -o -name "*.spec.ts" 2>/dev/null \
  | grep -v node_modules | grep -v dist | head -5
```

Read 1-2 of those files. Extract:
- Import style (named imports, relative paths, barrel files, .js extension required or not)
- Test structure (describe/it nesting depth, fixture patterns)
- Assertion style (expect().toBe vs assert.equal vs assertEquals)
- Setup/teardown patterns (beforeEach, setUp, #[setup])
- Mock patterns (vi.mock, jest.mock, unittest.mock)
- How test data is organized (inline fixtures, factory functions, separate fixtures file)
- File naming convention (colocated with source vs separate tests/ dir)

This is the style you MUST match. Do not invent new patterns.

### Step 4: Read the Source Files

For each file in SOURCE_FILES:

1. Read the file
2. Extract all public API surface:
   - TypeScript: `export function`, `export const`, `export class` with public methods, `export default`
   - Express/Fastify: route handlers (HTTP method, path, request body schema, response shape)
   - React: component props interface, rendered output, event handlers
   - Python: module-level functions, classes, and their public methods
   - Rust: `pub fn`, `pub struct`, `pub impl` methods
3. Note: input types, return types, error conditions, edge cases
4. Note: existing JSDoc/docstrings describing expected behavior

For each exported item, formulate:
- The "happy path" test: valid inputs, expected output
- At least one error/edge case: invalid input, empty input, error thrown
- For async functions: resolved value AND rejection cases
- For React components: renders without crashing AND key interaction (click/input/submit)
- For routes: 2xx success + 400 bad request + 404/403 as applicable

### Step 5: Determine Test File Path

For each source file, determine test file path based on where existing tests live:

**Colocated** (test next to source):
```
src/utils/hash.ts     -> src/utils/hash.test.ts
src/routes/users.ts   -> src/routes/users.test.ts
```

**Separate tests/ directory**:
```
src/utils/hash.ts     -> tests/utils/hash.test.ts
lib/payments.py       -> tests/test_payments.py
```

**Jest __tests__ pattern**:
```
src/components/Card.tsx -> src/components/__tests__/Card.test.tsx
```

Use the same pattern the project already uses. Check where existing test files live relative to their source files to determine which pattern applies.

### Step 6: Write the Tests

Match the project's existing style exactly. Do not introduce new patterns.

**TypeScript/JavaScript (Jest or Vitest) example:**
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { functionName } from '../path/to/source.js'

describe('functionName', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should return expected value given valid input', () => {
    const result = functionName(validInput)
    expect(result).toEqual(expectedOutput)
  })

  it('should throw given invalid input', () => {
    expect(() => functionName(invalidInput)).toThrow()
  })
})
```

**pytest example:**
```python
import pytest
from module.path import function_name

class TestFunctionName:
    def test_returns_expected_value_given_valid_input(self):
        result = function_name(valid_input)
        assert result == expected

    def test_raises_value_error_given_invalid_input(self):
        with pytest.raises(ValueError):
            function_name(invalid_input)
```

**Rust inline test example:**
```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_function_name_happy_path() {
        let result = function_name(valid_input);
        assert_eq!(result, expected);
    }

    #[test]
    fn test_function_name_returns_error_on_invalid() {
        assert!(function_name(invalid_input).is_err());
    }
}
```

**HTTP route handler example:**
```typescript
describe('POST /api/endpoint', () => {
  it('should return 201 with created resource given valid body', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/endpoint',
      payload: validBody,
    })
    expect(response.statusCode).toBe(201)
    expect(response.json()).toMatchObject({ id: expect.any(String) })
  })

  it('should return 400 given missing required fields', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/endpoint',
      payload: {},
    })
    expect(response.statusCode).toBe(400)
  })
})
```

### Step 7: Run the Tests

After writing each test file:

```bash
cd {PROJECT_ROOT}
{TEST_CMD} {relative_path_to_test_file} 2>&1
```

Examples:
- `pnpm vitest run src/utils/hash.test.ts`
- `pnpm jest tests/utils/hash.test.js`
- `pytest tests/test_payments.py -v`
- `cargo test -- test_function_name`

Read the output. If tests fail:

1. **Test authoring error** (wrong import, wrong mock, wrong assertion syntax): fix the test, rerun. Up to 3 self-correction attempts.
2. **Genuine source bug** (test correctly describes expected behavior but source does not match): do NOT fix the source. Mark the test as skip with a comment: `// TODO: source bug — {description}`. Report PARTIAL with bug description in the report.
3. **Import or type error**: verify import paths match the exact style found in existing tests. Fix imports and rerun.

Never claim tests pass without running them and reading the output.

### Step 8: Write ai/tests/TEST_PLAN.md

```markdown
# Test Plan
**Generated**: {ISO timestamp}
**Framework**: {framework}
**Triggered by**: /go — feature implementation sidecar

## Source Files Covered
- {path}: exports {list of tested items}, test file: {test path}

## Tests Written

### Unit Tests
- [ ] {TestSuite} > {test name} — {what it verifies}

### Integration Tests
- [ ] {suite} > {test name} — {what it verifies}

### Skipped
- E2E tests: deferred (requires running server + browser)
- {any other skipped coverage with reason}

## Coverage Summary
- Functions with tests: {N} / {total exported functions}
- Routes with tests: {N} / {total routes}
- Estimated coverage of new code: {rough %}

## Coverage Goals
- Unit test coverage: >80%
- Integration test coverage: >60%
- E2E: critical paths only (not auto-generated)

## Known Gaps
{public API not tested and why — e.g., "requires live DB", "requires external service"}

## Test Run Results
Pass: {N} / {N}  OR  Fail: {list failures with brief analysis}
```

### Step 9: Write ai/tests/COVERAGE_NOTES.md

```markdown
# Coverage Notes
**Updated**: {ISO timestamp}
**Framework**: {framework}
**Test directory**: {test_dir}

## Current Session
- New tests written: {N files}
- Test run status: {PASS / PARTIAL / FAIL}

## Framework Notes
{e.g., "vitest globals must be in vitest.config.ts", "pytest fixtures defined in conftest.py"}

## Bugs Surfaced
{bugs found while writing tests — source file path and description of expected vs actual behavior}

## Pending Coverage
{what still needs tests that was not written this run, and why}
```

### Step 10: Append to ai/tests/raw_test_plan.log

```
=== Test Writer Run: {ISO timestamp} ===
Framework: {framework}
Source files: {comma-separated list}
Tests written: {comma-separated list of test file paths}
Result: PASS {N}/{N} | PARTIAL {N}/{N} | FAIL {N}/{N}
```

## Reporting Format

Return this to the supervisor when done:

```
## Test Writer Report

**Status**: DONE / PARTIAL / BLOCKED
**Framework**: {framework}
**Tests written**: {N files}
  - {path/to/test.ts}: {N tests, covers: functionA, functionB}
  - {path/to/test.ts}: {N tests, covers: routeHandler, validation}
**Test run**: {N} / {N} passing
**Bugs surfaced**: {N} (see COVERAGE_NOTES.md for details)
**Remaining gaps**: {any untested public API with reason}
```

## Anti-Patterns

- Testing unexported/internal functions — test the public API only
- Mocking everything — use real implementations for unit-testable code
- Writing tests that always pass regardless of code behavior (tautological tests)
- Fixing source code bugs found while writing tests — note them, let the implementer fix
- Writing to source files — if you notice this about to happen, stop immediately
- Inventing new test patterns when existing patterns exist in the project — match what is there
- Writing tests without running them — always run and verify
- Claiming tests pass without reading output — read every line of test output
```

---

## 7. Framework Detection

The test-writer detects frameworks in a two-pass process. Pass one reads from the context pack (intake.json already did this work). Pass two is live detection if the context pack is missing or incomplete.

### Detection from intake.json

The `/intake` command writes `ai/supervisor/intake.json` with `stack.test_framework` and `stack.test_cmd`. When these exist, the test-writer reads them directly — no re-detection needed.

```json
{
  "stack": {
    "test_framework": "vitest",
    "test_cmd": "pnpm --workspace-concurrency=1 -r test"
  }
}
```

### Live detection (intake.json absent or stale)

The agent runs a targeted scan. Detection signal priority:

| Signal | Framework | Test dir convention |
|--------|-----------|-------------------|
| `devDependencies.vitest` in package.json | vitest | colocated `.test.ts` or `src/__tests__/` |
| `devDependencies.jest` in package.json | jest | `__tests__/` dirs or colocated `.test.js` |
| `devDependencies.mocha` in package.json | mocha | `test/` directory, `.js` files |
| `pytest.ini` OR `pyproject.toml [tool.pytest...]` | pytest | `tests/` directory, `test_*.py` |
| `Cargo.toml` present | rust | inline `#[cfg(test)]` modules OR `tests/` dir |
| `*_test.go` files present | go test | colocated `_test.go` files |
| None of the above | unknown | read existing test files, mimic exactly |

**Monorepo handling**: In pnpm workspaces, turborepo, or nx monorepos, detect per-package. Check the `package.json` of the package containing the source file, not the root `package.json`. Place test files within the same package's test directory.

### Per-framework import path resolution

| Framework | Module resolution | Test import style |
|-----------|------------------|------------------|
| vitest (NodeNext) | NodeNext | `import { x } from '../bar.js'` (with .js ext) |
| vitest (bundler) | bundler | `import { x } from '../utils/bar'` (no ext) |
| jest (CJS) | CommonJS | `const { x } = require('../bar')` |
| pytest | Python imports | `from module.bar import x` |
| rust | crate-relative | `use super::*` |
| go | package paths | `import "project/pkg/foo"` |

Detect which resolution is active by reading one existing test file's import statements and matching that style exactly.

---

## 8. Test Generation Strategy

### 8.1 What to test

The rule: if it is exported (public), it gets tests. Scan for:

**TypeScript/JavaScript:**
```typescript
export function name(...)            // -> unit test
export const name = (...)            // -> unit test
export class Name { public m() {} } // -> tests for each public method
export default function(...)         // -> unit test
app.get('/path', handler)            // -> route integration test
app.post('/path', { schema }, handler) // -> route integration test
export function ComponentName(props) // -> component render + interaction test
```

**Python:**
```python
def function_name(...)               # -> unit test
class ClassName:
    def public_method(self, ...)     # -> unit test per public method
@app.route('/path', methods=['GET']) # -> route integration test
@router.post('/path')                # -> route integration test
```

**Rust:**
```rust
pub fn function_name(...)            // -> unit test (inline cfg(test))
impl Name { pub fn method(...) }     // -> unit tests for public methods
```

### 8.2 Minimum tests per item

Coverage targets carried forward from OpenClaw's `test_plan_compiler.py`:

| Item type | Minimum tests |
|-----------|--------------|
| Pure function (sync) | 2: happy path + 1 edge case |
| Pure function (async) | 3: resolved value + rejection + timeout if applicable |
| Class method | 2 per public method: happy path + error condition |
| HTTP route handler | 3: success (200/201) + 400 bad request + 404/403 as applicable |
| React component | 2: renders without crashing + key interaction |
| Utility with enum inputs | 1 per enum variant with distinct behavior |

These are minimums. Add tests for obvious edge cases: empty array, null, zero, negative numbers, strings with special characters.

### 8.3 Handling files not yet written by the implementer

The test-writer is spawned with the implementer's **planned** source files, not completed output. Both agents run in parallel.

If a planned source file does not exist when the test-writer tries to read it:
1. Wait up to 30 seconds (check every 5s: `ls {file_path}`)
2. If file appears: read it and proceed
3. If file does not appear after 30s: skip it, note in report as "Skipped — source file not available during sidecar run"

In practice the implementer writes files quickly in iteration 1 before running its full test suite. The 30-second window is almost always sufficient.

### 8.4 Matching the project's test fingerprint

Before writing anything, extract the test fingerprint from 1-2 existing test files:

```
FINGERPRINT example (PCC / vitest / NodeNext):
- import_style: named imports from '../path.js' with .js extension
- nesting: describe > it (1 level, sometimes describe > describe > it)
- assertion_style: expect(x).toBe(y) for primitives, expect(x).toEqual(y) for objects
- mock_pattern: vi.mock('../module.js', () => ({ fn: vi.fn() }))
- fixture_pattern: const fixture = { ... } at describe scope
- async_style: async/await throughout
- teardown: beforeEach(() => { vi.clearAllMocks() })
```

Every test file written for this project must match this fingerprint. If the project uses `.toStrictEqual`, use `.toStrictEqual` — not `.toEqual`. If nesting is two levels deep, use two levels. Never introduce patterns not already present.

---

## 9. Sidecar Integration

### 9.1 Where to insert in go.md

The test-writer sidecar is spawned at the **start of Phase 5c** — immediately after the planning agent produces the implementation plan, simultaneously with the implementer. Both agents run concurrently.

### 9.2 Exact changes to `~/.claude/commands/go.md`

#### Change 1: Phase 5c — Single sub-task block

**Find** (approximately lines 256-272 in current go.md):

```
#### Single sub-task (no decomposition)
```
Agent(Plan): Design implementation using hydrated context + landscape report
  -> Define: files to change, test command, success criteria

Agent(implementer): Ralph loop execution
  -> MAX_ITERATIONS: 2 (trivial) / 5 (standard) / 7 (complex)
  -> TEST_COMMAND: from intake.json or plan
  -> SUCCESS_CRITERIA: specific measurable condition
  -> Loop: implement -> test -> analyze -> fix -> retest
  -> Returns: implementation report (DONE/PARTIAL/BLOCKED)

If PARTIAL/BLOCKED:
  -> BLOCKED on external dep -> AskUserQuestion to escalate
  -> PARTIAL with failures -> spawn second implementer with failure context (chained Ralph)
  -> PARTIAL but close -> fix remaining directly
```
```

**Replace with:**

```
#### Single sub-task (no decomposition)
```
Agent(Plan): Design implementation using hydrated context + landscape report
  -> Define: files to change, test command, success criteria
  -> Returns: PLAN with fields: files_to_create, files_to_modify, test_command

Agent(implementer): Ralph loop execution              -+  spawn SIMULTANEOUSLY
Agent(test-writer, background): write tests           -+  (run_in_background: true)

Implementer:
  -> MAX_ITERATIONS: 2 (trivial) / 5 (standard) / 7 (complex)
  -> TEST_COMMAND: from intake.json or plan
  -> SUCCESS_CRITERIA: specific measurable condition
  -> Loop: implement -> test -> analyze -> fix -> retest
  -> Returns: implementation report (DONE/PARTIAL/BLOCKED)
  -> NOTE: a test-writer sidecar is running in parallel.
     Do NOT write test files unless the sidecar is reported BLOCKED at Phase 6.
     Focus on implementing source code and making existing tests pass.

Test-writer sidecar (run_in_background: true):
  -> Context pack includes: FRAMEWORK, SOURCE_FILES (from plan),
     TEST_DIR, TEST_CMD, PROJECT_ROOT, path to one existing test file
  -> Reads new/modified source files (waits up to 30s if not yet written)
  -> Studies existing test patterns from the example file
  -> Writes matching test files to the correct test directory
  -> Runs tests, self-corrects authoring errors (up to 3 retries per file)
  -> Marks as skip (not deletes) any test that reveals a source bug
  -> Writes ai/tests/TEST_PLAN.md and ai/tests/COVERAGE_NOTES.md
  -> Returns: test writer report (DONE/PARTIAL/BLOCKED)
  -> If sidecar fails or BLOCKED: non-fatal, noted in Phase 6

If implementer returns PARTIAL/BLOCKED:
  -> BLOCKED on external dep -> AskUserQuestion to escalate
  -> PARTIAL with failures -> spawn second implementer with failure context (chained Ralph)
  -> PARTIAL but close -> fix remaining directly
```
```

#### Change 2: Phase 5c — Multi sub-task wave execution (EXECUTE WAVE block)

**Find** the "EXECUTE WAVE" block (approximately lines 283-293):

```
  2. EXECUTE WAVE: Spawn all sub-tasks in this wave as PARALLEL agents
     -> Each gets its own implementer (Ralph loop) or researcher as appropriate
     -> Each runs in isolation (worktree for build tasks to avoid conflicts)
     -> All launched in a SINGLE message (parallel Agent calls)

     Agent(implementer, worktree): sub-task A  --+
     Agent(implementer, worktree): sub-task B  +-  parallel (same wave)
     Agent(implementer, worktree): sub-task C  --+
```

**Replace with:**

```
  2. EXECUTE WAVE: Spawn all sub-tasks in this wave as PARALLEL agents
     -> Each build sub-task gets its own implementer (Ralph loop)
     -> Each build sub-task also gets a test-writer sidecar (background)
     -> Each runs in isolation (worktree for build tasks to avoid conflicts)
     -> All launched in a SINGLE message (parallel Agent calls)

     Agent(implementer, worktree): sub-task A               -+
     Agent(test-writer, background): tests for sub-task A   |   parallel (same wave)
     Agent(implementer, worktree): sub-task B               |
     Agent(test-writer, background): tests for sub-task B   -+

     Budget note: 2 test-writer sidecars per wave is within the 3-sidecar budget.
     If a wave has 2+ implementers AND Phase 5e sidecars are also running,
     defer non-critical Phase 5e sidecars to after the wave completes.
```

#### Change 3: Phase 6 — Integration and Memory, item 4

**Find:**

```markdown
4. **If code written:** Run tests, summarize changes
```

**Replace with:**

```markdown
4. **If code written:** Run tests, summarize changes. Fold in test-writer sidecar report:
   -> List test files written and test pass counts
   -> If test-writer DONE: include "Tests: N/N passing — {test file(s)}" in summary
   -> If test-writer PARTIAL: note gaps and any skipped (source-bug) tests explicitly
   -> If test-writer surfaced bugs: flag them: "Test-writer surfaced N potential source bugs:
      {description} in {source file}. Review before merging."
   -> If test-writer failed or did not run: note "Test coverage: not generated (sidecar failed)"
      and suggest: "Run /go 'write tests for {file}' as a follow-up"
```

#### Change 4: Phase 5e — Sidecar Agents, "When to spawn" list

Add this clarifying bullet to the existing "When to spawn a sidecar" list:

```markdown
- A build task is executing — test-writer sidecars are auto-spawned in Phase 5c alongside
  every implementer. You do not spawn them manually here; they are part of the build pattern.
```

### 9.3 Context pack format for the test-writer sidecar

The supervisor assembles this inline (no separate hydrator spawn needed — information comes from the planning phase and intake.json):

```markdown
## Context Pack for test-writer

### Task
Write tests for: {one-line description of what the implementer is building}

### Framework
{value from intake.json stack.test_framework}

### Test Command
{intake.json stack.test_cmd — e.g., "pnpm vitest run" or "pytest"}

### Source Files (planned by implementer)
- {absolute_path}: {one-line description of what this file does/exports}
- {absolute_path}: {one-line description}

### Test Directory Convention
{e.g., "colocated .test.ts files next to source" or "tests/ directory at package root"}

### Project Root
{absolute path}

### Existing Test Example
{absolute path to one representative existing test file — for style/fingerprint reference}

### Module Resolution
{NodeNext / bundler / CommonJS — affects import path style (.js ext required or not)}

### Constraints
- Do NOT modify any source file
- Do NOT install new dependencies
- Match the import and assertion style of the existing test example exactly
```

---

## 10. Coordination Protocol

### 10.1 How test-writer and implementer avoid stepping on each other

The isolation is structural, not lock-based. The test-writer writes only to test file paths. The implementer writes only to source file paths. There is no file that both agents would ever touch simultaneously.

The one potential conflict: the implementer's Ralph loop prompt says "Write tests if missing. If there are no tests for your feature, write them first (TDD within the loop)." The coordination note added to the implementer's context in Phase 5c (Section 9.2, Change 1) addresses this directly:

> A test-writer sidecar is running in parallel. It will write test files for your new code. Do NOT write test files unless the sidecar is reported BLOCKED at Phase 6. Focus on implementing source code and making existing tests pass.

### 10.2 Narrow race: both agents write the same test file

There is a narrow timing window where both agents could create the same test file path. In practice this does not occur because:
- The implementer, given the coordination note, skips test file creation
- The test-writer acts on planned source files, which the implementer writes in iteration 1

If the race occurs (coordination note not processed):
- The implementer finds the test file exists and reads it to understand expected behavior
- The implementer does not overwrite it (it reads what tests exist before writing)
- This is correct behavior — the test-writer's output is treated as the authoritative test file

### 10.3 Cross-wave test quality improvement

In wave execution, each wave has its own test-writer sidecar. Wave 2's test-writer can read test files written by wave 1's sidecar as additional style examples. This progressively improves test quality across waves as the project accumulates more test files in the correct style.

The supervisor notes this opportunity in the wave 2 context pack: "Additional test examples from wave 1: {paths to new test files written by wave 1 test-writer}."

### 10.4 Source bugs surfaced by the test-writer

When the test-writer writes a test that correctly captures expected behavior and the source does not match, the test-writer:

1. Marks the test as skip with a comment: `// TODO: source bug — expected {X} but source returns {Y}`
2. Notes the bug in `ai/tests/COVERAGE_NOTES.md` under "Bugs Surfaced"
3. Returns PARTIAL status with the bug in its report

The supervisor surfaces this at Phase 6:

```
Test-writer surfaced 1 potential source bug:
  - {source_file}: expected {description of correct behavior}, source returns {actual}
  - Skipped test: {test_file}:{test_name}
  - Recommendation: have implementer review this before merging
```

This is a useful side effect — the test-writer acts as a second reviewer that can catch logic errors the implementer's own test assertions missed.

### 10.5 Lock file (legacy pattern, preserved for reference)

OpenClaw's worker used `ai/_locks/test_writer.lock` to prevent concurrent runs. In Claude Code, the sidecar pattern ensures only one test-writer runs per `/go` invocation. The lock file is not needed for the normal flow.

If the test-writer is ever invoked manually outside `/go`, it should write `ai/_locks/test_writer.lock` on start and delete it on finish, to prevent overlap with a simultaneously-running `/go` sidecar.

---

## 11. Implementation Plan

### Step 1: Create the agent file

Write `~/.claude/agents/test-writer.md` with the complete agent definition from Section 6.

This file is self-contained. It requires no new MCP servers, no new tool schemas, and no new installed packages. The tools it uses (Read, Write, Bash, Glob, Grep) are already available to all agents in the harness.

### Step 2: Apply the four go.md changes

Apply changes 1-4 from Section 9.2 to `~/.claude/commands/go.md`. All changes are additive. No existing behavior is removed. The implementer's Ralph loop is unchanged. The sidecar is purely supplementary.

### Step 3: Update the CLAUDE.md agent table

Add this row to the agents table in `~/.claude/CLAUDE.md`:

```markdown
| test-writer | sonnet | Sidecar: writes tests for new code in parallel with implementer. Test files only. Non-blocking. |
```

### Step 4: Smoke test — single file utility

```
/go add a utility function that formats bytes to human-readable string (1024 -> "1 KB")
```

Expected outcome:
- Implementer creates `src/utils/bytes.ts` (or project-appropriate path)
- Test-writer creates `src/utils/bytes.test.ts` with tests: zero, 1 byte, 1023 bytes, 1 KB, 1 MB, 1 GB
- Phase 6 summary shows both implementer and test-writer reports
- `ai/tests/TEST_PLAN.md` and `ai/tests/COVERAGE_NOTES.md` exist
- Tests pass

### Step 5: Verify the coordination note

```
/go add a slug generation utility
```

Check: the implementer's report lists only source file creation. The test-writer's report lists the test file. No double-written test file. No test file in the implementer's change list.

### Step 6: Test multi-wave

```
/go add a POST /api/tags endpoint and update the tags list component to show new tags
```

Expected: wave 1 test-writer covers the API endpoint, wave 2 test-writer covers the component. Both reports in Phase 6 summary.

---

## 12. Testing Plan

### Scenario 1: TypeScript + vitest + NodeNext (pnpm monorepo)

**Project**: Physical Capability Cloud
**Task**: `/go add a capitalizeWords utility to @pcc/spec`

Verify:
- Framework detected from `packages/spec/package.json` (vitest)
- Test file placed colocated: `packages/spec/src/capitalizeWords.test.ts`
- Imports use `.js` extension (NodeNext module resolution)
- Tests cover: empty string, single word, multiple words, already-capitalized input
- `pnpm vitest run packages/spec/src/capitalizeWords.test.ts` passes
- TEST_PLAN.md written

### Scenario 2: Python + pytest

**Project**: Intention Engine or StereoRecon
**Task**: `/go add a cosine similarity function to the core module`

Verify:
- Framework detected from `pytest.ini` or `pyproject.toml`
- Test file in `tests/test_similarity.py`
- Class-based test structure matches existing project tests
- `pytest tests/test_similarity.py -v` passes

### Scenario 3: Missing intake.json

Run in a fresh project directory without `ai/supervisor/intake.json`.

Verify:
- Test-writer performs live detection (Step 2 of agent process)
- Framework correctly identified
- Proceeds to write tests normally
- Framework noted in TEST_PLAN.md under "Framework"

### Scenario 4: Source bug surfaced

Set up a function with a deliberate off-by-one error (e.g., paginate returns items starting at index+1 instead of index).

**Task**: `/go add a paginate(items, page, pageSize) utility`

Verify:
- Test-writer writes: `paginate([1,2,3,4,5], 2, 2)` should return `[3, 4]`
- If source has off-by-one, test fails
- Test marked as `it.skip` (or `@pytest.mark.skip`) with TODO comment
- Report shows PARTIAL with bug description
- Phase 6 flags: "Test-writer surfaced 1 potential source bug"

### Scenario 5: Fastify route handler

**Task**: `/go add a GET /api/metrics endpoint returning CPU and memory usage`

Verify:
- Test-writer identifies route handler export
- Writes Fastify inject-style tests matching existing route test pattern
- Tests: 200 with metrics object of correct shape
- Tests pass

### Verification checklist (apply to all scenarios)

- [ ] Test file created in the correct location (matching existing convention)
- [ ] Test imports match project's import style (extension, path depth, barrel or not)
- [ ] Assertions match project's assertion style (toBe vs toEqual vs toStrictEqual)
- [ ] Tests actually run — TEST_PLAN.md shows a pass count, not just a plan
- [ ] Implementer did NOT write test files (coordination note effective)
- [ ] Phase 6 summary includes test-writer report alongside implementer report
- [ ] `ai/tests/COVERAGE_NOTES.md` exists with framework, test dir, and status

---

## 13. Example Scenario: Walk-Through

### Setup

**Project**: Physical Capability Cloud
**Stack**: TypeScript (NodeNext), vitest, pnpm monorepo
**Existing test style**: `packages/gateway/src/routes/*.test.ts` colocated with routes, Fastify inject pattern, vi.mock for store dependencies, 1-level describe/it nesting

### Invocation

```
/go add a POST /api/protocols/fork endpoint to @pcc/gateway that accepts
a templateId and userId, creates a forked copy of the protocol template
with a new ID and forkedFrom field, and returns 201 with the new template
```

### Phase 0 — Intake

`ai/supervisor/intake.json` already exists. `test_framework: "vitest"`, `test_cmd: "pnpm --workspace-concurrency=1 -r test"`.

### Phase 1 — Task Assessment

Single sub-task. Category: build. Wheel-scout gate required.

### Phase 2 — Wheel-Scout Gate

Scout searches "protocol forking library", "template cloning npm typescript", "protocol fork github". Finds no existing library matching PCC's schema. Returns BUILD recommendation.

### Phase 3 — Parallel Bootstrap

Context-hydrator reads `protocols.ts`, `protocol.ts` (types), `protocols.test.ts` (style). Returns context pack with test fingerprint:

```
import_style: named imports from '../routes/protocols.js'
nesting: describe > it (1 level)
assertions: expect(response.statusCode).toBe(201)
inject: app.inject({ method, url, payload })
mocks: vi.mock('../lib/store.js', ...)
teardown: beforeEach(() => { vi.clearAllMocks() })
```

### Phase 5c — Execution

Planning agent output:
```
files_to_create: packages/gateway/src/routes/protocols-fork.ts
files_to_modify: packages/gateway/src/server.ts
test_command: pnpm vitest run packages/gateway/src
```

**Implementer** and **test-writer sidecar** spawn simultaneously.

**Implementer (Ralph loop):**
- Iteration 1: writes `protocols-fork.ts` and registers the route in `server.ts`
- Runs `pnpm vitest run packages/gateway/src` — existing tests pass
- Reports DONE

**Test-writer sidecar:**

1. Reads context pack: framework vitest, source file `protocols-fork.ts`, existing test example `protocols.test.ts`
2. Waits ~15 seconds for `protocols-fork.ts` to appear. File appears.
3. Reads `protocols.test.ts`. Extracts fingerprint (matches context pack).
4. Reads `protocols-fork.ts`. Finds exported `forkProtocolHandler`. HTTP method: POST. Inputs: `templateId: string`, `userId: string`. Success: 201 + `ProtocolTemplate`. Errors: 404 (template not found), 400 (missing body fields).
5. Test file path: colocated — `packages/gateway/src/routes/protocols-fork.test.ts`
6. Writes test file:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { forkProtocolHandler } from '../routes/protocols-fork.js'
import * as protocolStore from '../lib/protocol-store.js'

vi.mock('../lib/protocol-store.js', () => ({
  getTemplate: vi.fn(),
  saveTemplate: vi.fn(),
}))

describe('forkProtocolHandler', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should return 201 with forked template given valid templateId and userId', async () => {
    const source = { id: 'pt_source', name: 'PCR Protocol', steps: [], forkedFrom: null }
    vi.mocked(protocolStore.getTemplate).mockResolvedValue(source)
    vi.mocked(protocolStore.saveTemplate).mockResolvedValue(undefined)

    const request = { body: { templateId: 'pt_source', userId: 'usr_1' } }
    const reply = { code: vi.fn().mockReturnThis(), send: vi.fn() }

    await forkProtocolHandler(request as any, reply as any)

    expect(reply.code).toHaveBeenCalledWith(201)
    expect(reply.send).toHaveBeenCalledWith(
      expect.objectContaining({ forkedFrom: 'pt_source' })
    )
  })

  it('should return 404 when templateId does not exist', async () => {
    vi.mocked(protocolStore.getTemplate).mockResolvedValue(null)
    const request = { body: { templateId: 'pt_missing', userId: 'usr_1' } }
    const reply = { code: vi.fn().mockReturnThis(), send: vi.fn() }
    await forkProtocolHandler(request as any, reply as any)
    expect(reply.code).toHaveBeenCalledWith(404)
  })

  it('should return 400 when required body fields are missing', async () => {
    const request = { body: { userId: 'usr_1' } }
    const reply = { code: vi.fn().mockReturnThis(), send: vi.fn() }
    await forkProtocolHandler(request as any, reply as any)
    expect(reply.code).toHaveBeenCalledWith(400)
  })
})
```

7. Runs `pnpm vitest run packages/gateway/src/routes/protocols-fork.test.ts`. 3/3 passing.
8-10. Writes TEST_PLAN.md, COVERAGE_NOTES.md, appends to log.

Report:
```
## Test Writer Report
Status: DONE
Framework: vitest
Tests written: 1 file
  - packages/gateway/src/routes/protocols-fork.test.ts: 3 tests,
    covers: forkProtocolHandler (201 success, 404 not found, 400 bad request)
Test run: 3 / 3 passing
Bugs surfaced: 0
Remaining gaps: none
```

### Phase 6 — Final Summary

```
Done. Here's what happened:
- Landscape: BUILD (no existing library matches PCC's ProtocolTemplate schema)
- Built: POST /api/protocols/fork in packages/gateway/src/routes/protocols-fork.ts
- Tests: 3/3 passing — protocols-fork.test.ts (201, 404, 400 cases)
- Bugs surfaced: 0
- Memory: Checkpointed to ai/memory/WORKING_MEMORY.md
```

---

## 14. Configuration

### Coverage targets

From OpenClaw's `test_plan_compiler.py`, these are the canonical targets:

| Coverage type | Target | Behavior when missed |
|--------------|--------|---------------------|
| Unit test coverage (new code) | >80% | Report gap in TEST_PLAN.md, continue |
| Integration test coverage (routes) | >60% | Report gap, continue |
| E2E coverage | Critical paths only | Always deferred, never auto-generated |

Targets are aspirational. The test-writer reports gaps but does not block the pipeline. Blocking on coverage would block all `/go` build tasks, which is not acceptable.

### Framework override

If `intake.json` has `test_framework_override`, the test-writer uses it instead of the auto-detected value. Useful when jest is installed as a transitive dependency but vitest is the actual test runner:

```json
{
  "stack": {
    "test_framework": "jest",
    "test_framework_override": "vitest"
  }
}
```

### Test directory convention override

```json
{
  "stack": {
    "test_dir_convention": "colocated"
  }
}
```

Valid values: `"colocated"`, `"tests_dir"`, `"__tests__"`, `"spec"`.

### Skip test-writer for a single run

Add `--no-tests` to the task description:

```
/go add a quick debug logging utility --no-tests
```

The supervisor checks for this flag in Phase 5c and skips spawning the test-writer sidecar.

### Disable globally

Set `test_writer_enabled: false` in `ai/supervisor/intake.json`:

```json
{
  "test_writer_enabled": false
}
```

### Sidecar timeout

The test-writer should complete within the duration of the implementer's Ralph loop (typically 2-5 minutes). If still running when Phase 6 begins, the supervisor waits up to 60 additional seconds. If pending after 60s, Phase 6 proceeds without the test results. The pending state is noted in the summary as: "Test coverage: sidecar still running — check `ai/tests/` when complete."
