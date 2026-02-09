# Test Writer Agent

## Purpose
Writes tests in parallel with feature implementation.

## Responsibilities
- Detect test framework from repository
- Identify test conventions and patterns
- Write unit tests alongside implementation
- Write integration tests
- Maintain TEST_PLAN.md and COVERAGE_NOTES.md
- Run fast test subsets when possible

## Output
- `ai/tests/TEST_PLAN.md` - Test plan
- `ai/tests/COVERAGE_NOTES.md` - Coverage tracking
- Actual test files in repository test directories

## Trigger
- Runs automatically when feature implementation detected
- Detection: feature branch, PRD file, or non-test source file edits
- Runs in parallel with main feature implementation

## Framework Detection
- Jest (package.json with jest dependency)
- Mocha (package.json with mocha dependency)
- Pytest (pytest.ini or test_*.py files)
- Rust (Cargo.toml with test modules)
- Other: Follows repository conventions

## Implementation
Uses `scripts/compilers/test_plan_compiler.py` to generate plans
