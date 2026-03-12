# Wave Execution — OpenClaw Port

## 1. Overview

Wave Execution is Claude Code's parallel task processing model. When the supervisor
receives a multi-step request (via `/go`), it does not execute tasks sequentially.
Instead it:

1. Decomposes the request into discrete tasks
2. Builds a dependency graph (which tasks must complete before others can start)
3. Topologically sorts the graph into execution "waves"
4. Runs all tasks within the same wave as parallel agents, each in an isolated Git
   worktree so they cannot conflict on the same files
5. Feeds each wave's outputs as context into the next wave

The result is that independent subtasks run concurrently while dependent tasks wait
for their prerequisites. A 5-step task with 3 independent steps and 2 serial
dependencies might complete in 2 wave cycles instead of 5 sequential cycles.

Example decomposition of "build a REST API with tests and documentation":

```
Wave 1 (parallel): [scaffold-project] [design-api-schema] [setup-test-framework]
Wave 2 (parallel): [implement-endpoints] [write-tests]        ← both need Wave 1
Wave 3 (serial):   [generate-docs]                            ← needs Wave 2 output
```

---

## 2. Problem Statement

OpenClaw's orchestrator (`orchestrator_prompt.md`) processes tasks sequentially
through a single chain:

```
Task 1 → complete → Task 2 → complete → Task 3 → complete → done
```

This creates two problems:

**Problem 1: Unnecessary latency.** When tasks are independent (scaffold + design +
setup), they still run one at a time. Each task waits for the previous one even
though it does not need its output.

**Problem 2: No conflict isolation.** When tasks do run (even sequentially), they
share the same workspace. One task's in-progress file writes can be partially
visible to the next task if anything goes wrong.

For a complex `/go` request like "migrate this Python 2 app to Python 3, add type
annotations, write tests, and update the CI config", sequential execution takes
~4x longer than necessary and risks file conflicts between tasks.

| Characteristic | Claude Code Wave Execution | OpenClaw current |
|---|---|---|
| Execution model | Parallel within waves | Sequential |
| Conflict protection | Worktree isolation per agent | Shared workspace |
| Dependency tracking | Explicit DAG | Implicit (order = dependency) |
| Wave output forwarding | Structured context pass | N/A |
| Latency | O(critical path length) | O(total task count) |

---

## 3. Source Analysis

### 3.1 Wave Execution in Claude Code

Wave execution is orchestrated in the supervisor's `/go` pipeline at Phase 5c.
The supervisor prompt includes this logic:

**Phase 5a: Decompose**

The supervisor asks itself: "What are the discrete, independently verifiable tasks
needed to complete this request?" Each task must have:
- A clear deliverable (a file, a test result, a decision)
- A defined input set (what it needs to start)
- A defined output set (what it produces)

**Phase 5b: Build dependency graph**

For each pair of tasks (A, B), ask: "Does B require any output from A to start?"
If yes, add edge A → B. If no, they can run in the same wave.

The graph is represented as an adjacency list in the supervisor's context:

```json
{
  "tasks": {
    "scaffold": {"inputs": [], "outputs": ["src/", "package.json"]},
    "design-schema": {"inputs": [], "outputs": ["schema.ts"]},
    "implement": {"inputs": ["src/", "schema.ts"], "outputs": ["src/api/"]},
    "test": {"inputs": ["src/api/"], "outputs": ["test-results.json"]},
    "docs": {"inputs": ["src/api/", "test-results.json"], "outputs": ["docs/"]}
  },
  "edges": [
    ["scaffold", "implement"],
    ["design-schema", "implement"],
    ["implement", "test"],
    ["implement", "docs"],
    ["test", "docs"]
  ]
}
```

**Phase 5c: Topological sort into waves**

Kahn's algorithm: tasks with no remaining prerequisites form the next wave.

```
Wave 1: scaffold, design-schema          (no prerequisites)
Wave 2: implement                        (needs scaffold + design-schema)
Wave 3: test                             (needs implement)
Wave 4: docs                             (needs implement + test)
```

**Phase 5d: Execute waves**

For each wave:
1. Create a Git worktree for each task: `git worktree add .worktrees/{task-id} HEAD`
2. Spawn an implementer agent per task, pointing it at its worktree
3. Each agent has read access to the main workspace (for context) and write access
   only to its worktree
4. Wait for all agents in the wave to complete
5. Merge worktrees back to main: `git merge .worktrees/{task-id}/{branch}`
6. Pass the merged state + each agent's output summary as context to the next wave

**Wave output format** (each agent writes to a shared output file):

```json
{
  "task_id": "scaffold",
  "wave": 1,
  "status": "complete",
  "outputs": ["src/", "package.json", "tsconfig.json"],
  "summary": "Initialized TypeScript project with Fastify. Entry point: src/index.ts",
  "errors": []
}
```

### 3.2 Worktree Isolation

Git worktrees give each agent a separate checked-out working directory on disk.
Agent A writing `src/api/users.ts` in its worktree does not touch Agent B's
worktree. After both complete, merge conflicts are explicit and resolvable rather
than silent data races.

The `isolation: "worktree"` parameter on the `Agent` tool in Claude Code triggers
this behavior automatically.

### 3.3 Cross-Wave Context Forwarding

At the end of each wave, the supervisor collects all wave output summaries and
constructs a "wave context pack" that is prepended to every agent prompt in the
next wave:

```
== Wave 1 Outputs ==
scaffold: TypeScript project initialized. src/index.ts is the entry point.
  Created files: src/, package.json, tsconfig.json, .eslintrc
design-schema: API schema complete. 5 resources: User, Post, Comment, Tag, Session.
  Created files: schema.ts, types.ts
```

Agents in Wave 2 receive this context and know exactly what their predecessors
produced without having to scan the filesystem.

---

## 4. Target Architecture

OpenClaw cannot use Git worktrees natively (no `isolation: "worktree"` parameter)
and has no native parallel agent spawning. The port requires:

1. **`wave_planner_skill.md`** — decomposes tasks into waves (runs on haiku)
2. **`wave_executor.py`** — Python tool that runs wave sessions in parallel using
   Python's `concurrent.futures`
3. **Workspace isolation** via temporary directories (not Git worktrees — see
   adaptation strategy)
4. **Wave output collection** via structured JSON files in `.openclaw/waves/`
5. **Orchestrator additions** — wave-aware task dispatch in `orchestrator_prompt.md`

### 4.1 Architecture Diagram

```
Supervisor receives: "/go migrate python app, add types, write tests, update CI"
         │
         ▼
wave_planner_skill.md (haiku — fast)
  ─ Decomposes into tasks
  ─ Builds dependency graph
  ─ Topological sort → wave assignments
  ─ Writes .openclaw/waves/plan-{ts}.json
         │
         ▼
.openclaw/waves/plan-{ts}.json
{
  "waves": [
    {"id": 1, "tasks": ["scaffold", "audit-types"]},
    {"id": 2, "tasks": ["migrate-syntax", "add-type-annotations"]},
    {"id": 3, "tasks": ["write-tests"]},
    {"id": 4, "tasks": ["update-ci"]}
  ]
}
         │
         ▼
wave_executor.py
  Wave 1: spawn 2 parallel sessions → wait → collect outputs
  Wave 2: spawn 2 parallel sessions (with Wave 1 context) → wait → collect
  Wave 3: spawn 1 session → wait → collect
  Wave 4: spawn 1 session → done
         │
         ▼
Supervisor collects all outputs, synthesizes final response
```

---

## 5. File Layout

```
openclaw/
├── wave_planner_skill.md          # NEW — task decomposition + DAG + wave assignment
├── tools/
│   └── wave_executor.py           # NEW — parallel session runner
├── supervisor_config.json         # MODIFY — enable wave execution
└── agent_profiles.json            # MODIFY — add wave_planner profile

.openclaw/waves/
├── plan-{ts}.json                 # RUNTIME — wave plan (from planner)
├── wave-{ts}-{wave_num}-{task_id}.json  # RUNTIME — per-task status
└── wave-{ts}-context-{wave_num}.json    # RUNTIME — context pack for next wave
```

---

## 6. Adaptation Strategy

### 6.1 No Git Worktrees

Claude Code uses `git worktree add` to give each parallel agent an isolated
filesystem. OpenClaw does not have this mechanism.

**Adaptation**: Use copy-on-write directories. Before spawning a wave, `wave_executor.py`
copies the current project state to `.openclaw/workspaces/{task-id}/`. Each
session operates on its copy. After the wave completes, a merge step applies each
task's changes back to the main workspace.

This is less efficient than Git worktrees (copies vs. hard links) but functionally
equivalent for correctness. For large repos, the executor only copies files
relevant to the task's declared `input_paths` rather than the entire workspace.

**Merge conflict resolution**: If two tasks in the same wave modify the same file
(this should not happen if the DAG is correct), the wave_executor detects the
conflict, marks one task's change as "pending review", and continues. The
orchestrator surfaces the conflict to the user.

### 6.2 No Native Parallel Agent Spawning

Claude Code uses the `Agent` tool to spawn parallel agents. OpenClaw uses session
files.

**Adaptation**: `wave_executor.py` uses Python `concurrent.futures.ThreadPoolExecutor`
to run multiple OpenClaw sessions in parallel. Each session reads from its task
file and writes to its output file. The executor waits for all futures to complete
before starting the next wave.

```python
with ThreadPoolExecutor(max_workers=max_parallel) as executor:
    futures = {
        executor.submit(run_task_session, task_id, workspace_path, context_pack): task_id
        for task_id in wave_tasks
    }
    for future in as_completed(futures):
        task_id = futures[future]
        result = future.result()
        wave_outputs[task_id] = result
```

### 6.3 Context Pack Construction

Claude Code's supervisor builds context packs inline in its own reasoning.
OpenClaw adaptation: after each wave completes, `wave_executor.py` reads all
task output files and constructs a JSON context pack. Each subsequent wave's
task files include the context pack path so agent sessions can load it.

### 6.4 Wave Size Limits

Claude Code runs waves with whatever parallelism the task graph requires.
OpenClaw caps parallel sessions at `max_parallel_agents` (default: 4) from
`supervisor_config.json` to prevent resource exhaustion. If a wave has more
tasks than the cap, tasks are batched within the wave.

---

## 7. Implementation Plan

### Step 1: Create `wave_planner_skill.md`

Full content in Section 8.

### Step 2: Create `wave_executor.py`

```python
# openclaw/tools/wave_executor.py
"""
Executes a wave plan from .openclaw/waves/plan-{ts}.json.
Runs tasks within each wave in parallel using ThreadPoolExecutor.
Handles workspace isolation via directory copies.
Constructs and forwards wave context packs.
"""

import json
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import uuid

@dataclass
class TaskResult:
    task_id: str
    wave: int
    status: str  # "complete" | "failed" | "partial"
    outputs: list[str]
    summary: str
    errors: list[str] = field(default_factory=list)
    workspace_path: Optional[str] = None

class WaveExecutor:
    def __init__(
        self,
        plan_file: str,
        project_root: str,
        openclaw_dir: str = ".openclaw",
        max_parallel: int = 4,
        skill_runner_cmd: Optional[list[str]] = None
    ):
        self.plan_file = plan_file
        self.project_root = Path(project_root)
        self.openclaw_dir = Path(openclaw_dir)
        self.max_parallel = max_parallel
        self.skill_runner_cmd = skill_runner_cmd or ["openclaw", "run"]
        self.waves_dir = self.openclaw_dir / "waves"
        self.workspaces_dir = self.openclaw_dir / "workspaces"
        self.waves_dir.mkdir(parents=True, exist_ok=True)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)

        with open(plan_file) as f:
            self.plan = json.load(f)

        self.plan_id = self.plan["plan_id"]
        self.all_results: dict[str, TaskResult] = {}
        self._lock = threading.Lock()

    def execute(self) -> dict:
        """Execute all waves in order. Returns summary of all results."""
        context_pack = {}

        for wave in self.plan["waves"]:
            wave_num = wave["id"]
            wave_tasks = wave["tasks"]

            print(f"[WaveExecutor] Starting Wave {wave_num}: {wave_tasks}")

            # Batch tasks if wave exceeds max_parallel
            batches = [
                wave_tasks[i:i + self.max_parallel]
                for i in range(0, len(wave_tasks), self.max_parallel)
            ]

            wave_results = {}
            for batch in batches:
                batch_results = self._execute_batch(batch, wave_num, context_pack)
                wave_results.update(batch_results)

            # Check for failures
            failed = [tid for tid, r in wave_results.items() if r.status == "failed"]
            if failed:
                print(f"[WaveExecutor] Wave {wave_num} had failures: {failed}")
                # Continue with partial results unless configured to stop on failure
                if self.plan.get("stop_on_wave_failure", False):
                    break

            # Build context pack for next wave
            context_pack = self._build_context_pack(wave_num, wave_results)
            self._save_context_pack(wave_num, context_pack)

            with self._lock:
                self.all_results.update(wave_results)

        return self._build_final_summary()

    def _execute_batch(
        self,
        task_ids: list[str],
        wave_num: int,
        context_pack: dict
    ) -> dict[str, TaskResult]:
        """Run a batch of tasks in parallel."""
        results = {}

        with ThreadPoolExecutor(max_workers=len(task_ids)) as executor:
            futures = {}
            for task_id in task_ids:
                workspace = self._create_workspace(task_id, wave_num)
                future = executor.submit(
                    self._run_task_session,
                    task_id,
                    wave_num,
                    workspace,
                    context_pack
                )
                futures[future] = task_id

            for future in as_completed(futures, timeout=600):
                tid = futures[future]
                try:
                    result = future.result()
                    results[tid] = result
                    if result.status == "complete":
                        self._apply_workspace_changes(tid, result.workspace_path)
                except Exception as e:
                    results[tid] = TaskResult(
                        task_id=tid,
                        wave=wave_num,
                        status="failed",
                        outputs=[],
                        summary="",
                        errors=[str(e)]
                    )

        return results

    def _create_workspace(self, task_id: str, wave_num: int) -> str:
        """
        Create an isolated workspace for a task.
        Copies only the files declared as inputs for this task.
        """
        workspace_path = self.workspaces_dir / f"wave{wave_num}-{task_id}"
        if workspace_path.exists():
            shutil.rmtree(workspace_path)

        # Find task definition to get input_paths
        task_def = self._find_task_def(task_id)
        input_paths = task_def.get("input_paths", [])

        workspace_path.mkdir(parents=True)

        if input_paths:
            for rel_path in input_paths:
                src = self.project_root / rel_path
                dst = workspace_path / rel_path
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                elif src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
        else:
            # No specific inputs declared — copy entire project
            # (exclude .git, .openclaw, node_modules, __pycache__)
            ignore = shutil.ignore_patterns(
                ".git", ".openclaw", "node_modules", "__pycache__",
                "*.pyc", ".venv", "venv"
            )
            shutil.copytree(self.project_root, workspace_path, ignore=ignore, dirs_exist_ok=True)

        return str(workspace_path)

    def _run_task_session(
        self,
        task_id: str,
        wave_num: int,
        workspace_path: str,
        context_pack: dict
    ) -> TaskResult:
        """Run a single task as an OpenClaw session."""
        task_def = self._find_task_def(task_id)
        task_file = self.waves_dir / f"{self.plan_id}-wave{wave_num}-{task_id}.json"

        # Write task file for the session
        task_data = {
            "task_id": task_id,
            "wave": wave_num,
            "plan_id": self.plan_id,
            "skill": task_def.get("skill", "implementer_skill"),
            "goal": task_def["goal"],
            "workspace_path": workspace_path,
            "output_paths": task_def.get("output_paths", []),
            "context_pack": context_pack,
            "status": "pending"
        }
        task_file.write_text(json.dumps(task_data, indent=2))

        # Run the session
        result_file = self.waves_dir / f"{self.plan_id}-wave{wave_num}-{task_id}-result.json"
        cmd = self.skill_runner_cmd + [
            "--skill", task_def.get("skill", "implementer_skill"),
            "--task", str(task_file),
            "--workspace", workspace_path,
            "--output", str(result_file)
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result_file.exists():
            result_data = json.loads(result_file.read_text())
            return TaskResult(
                task_id=task_id,
                wave=wave_num,
                status=result_data.get("status", "failed"),
                outputs=result_data.get("outputs", []),
                summary=result_data.get("summary", ""),
                errors=result_data.get("errors", []),
                workspace_path=workspace_path
            )
        else:
            return TaskResult(
                task_id=task_id,
                wave=wave_num,
                status="failed",
                outputs=[],
                summary="",
                errors=[f"No result file found. stderr: {proc.stderr[:500]}"],
                workspace_path=workspace_path
            )

    def _apply_workspace_changes(self, task_id: str, workspace_path: Optional[str]):
        """
        Apply a completed task's workspace changes back to the main project.
        Detects conflicts and logs them.
        """
        if not workspace_path:
            return

        task_def = self._find_task_def(task_id)
        output_paths = task_def.get("output_paths", [])

        for rel_path in output_paths:
            src = Path(workspace_path) / rel_path
            dst = self.project_root / rel_path

            if src.is_dir():
                if dst.exists() and not dst.is_dir():
                    print(f"[WaveExecutor] Conflict: {rel_path} is a file in main but dir in {task_id}")
                    continue
                shutil.copytree(src, dst, dirs_exist_ok=True)
            elif src.is_file():
                if dst.exists():
                    # Check if another task already wrote this file in this wave
                    if dst.stat().st_mtime > os.path.getmtime(workspace_path):
                        print(f"[WaveExecutor] Potential conflict on {rel_path} — review needed")
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    def _build_context_pack(self, wave_num: int, results: dict[str, TaskResult]) -> dict:
        """Build a context pack from wave results to pass to the next wave."""
        pack = {
            "wave": wave_num,
            "completed_tasks": {},
            "available_outputs": []
        }

        for task_id, result in results.items():
            if result.status in ("complete", "partial"):
                pack["completed_tasks"][task_id] = {
                    "status": result.status,
                    "summary": result.summary,
                    "outputs": result.outputs
                }
                pack["available_outputs"].extend(result.outputs)

        return pack

    def _save_context_pack(self, wave_num: int, context_pack: dict):
        pack_file = self.waves_dir / f"{self.plan_id}-context-wave{wave_num}.json"
        pack_file.write_text(json.dumps(context_pack, indent=2))

    def _find_task_def(self, task_id: str) -> dict:
        for wave in self.plan["waves"]:
            for task in wave.get("task_definitions", []):
                if task["id"] == task_id:
                    return task
        # Fallback: minimal task def
        return {"id": task_id, "goal": task_id, "input_paths": [], "output_paths": []}

    def _build_final_summary(self) -> dict:
        total = len(self.all_results)
        complete = sum(1 for r in self.all_results.values() if r.status == "complete")
        failed = sum(1 for r in self.all_results.values() if r.status == "failed")
        return {
            "plan_id": self.plan_id,
            "total_tasks": total,
            "complete": complete,
            "failed": failed,
            "partial": total - complete - failed,
            "tasks": {tid: {"status": r.status, "summary": r.summary, "errors": r.errors}
                      for tid, r in self.all_results.items()}
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Execute a wave plan")
    parser.add_argument("--plan", required=True, help="Path to plan JSON file")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    parser.add_argument("--max-parallel", type=int, default=4)
    args = parser.parse_args()

    executor = WaveExecutor(args.plan, args.project_root, max_parallel=args.max_parallel)
    summary = executor.execute()
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
```

---

## 8. Configuration

### `wave_planner_skill.md` (complete file)

```markdown
# Wave Planner Skill

You are the OpenClaw Wave Planner. Your job is to decompose a multi-step task
into a dependency graph and assign tasks to execution waves.

You run on haiku (fast, cheap). Your output is pure JSON — no prose.

## Input

You receive a task description as a plain string.

## Output

Write a wave plan to `.openclaw/waves/plan-{TIMESTAMP}.json`.

## Process

### Step 1: Identify Discrete Tasks

Break the request into the smallest tasks that:
- Have a clear, verifiable deliverable (a file, a test result, a config)
- Can be described in one sentence
- Can be assigned to a single implementer agent

Aim for 3-8 tasks for a typical request. Do not over-decompose.

### Step 2: Identify Dependencies

For each pair of tasks (A, B), ask: "Can B START without A's output?"
- If NO → B depends on A. Add edge A → B.
- If YES → they can run in the same wave.

### Step 3: Assign Waves (Kahn's Algorithm)

1. Start with all tasks that have no dependencies → Wave 1.
2. Remove Wave 1 tasks from the graph.
3. Tasks that now have no remaining dependencies → Wave 2.
4. Repeat until all tasks are assigned.

### Step 4: Assign Skills

For each task, pick the appropriate OpenClaw skill:
- Code implementation → `implementer_skill`
- Test writing → `implementer_skill` (with test-focused goal)
- Research/analysis → `researcher_skill`
- Documentation → `implementer_skill` (with doc-focused goal)
- Configuration changes → `implementer_skill`

### Step 5: Assign Input/Output Paths

For each task, list:
- `input_paths`: files/directories this task needs to READ
- `output_paths`: files/directories this task will CREATE or MODIFY

These are used for workspace isolation.

## Output Format

```json
{
  "plan_id": "wave-plan-{unix_timestamp}",
  "original_request": "...",
  "wave_count": N,
  "waves": [
    {
      "id": 1,
      "tasks": ["task-id-1", "task-id-2"],
      "task_definitions": [
        {
          "id": "task-id-1",
          "goal": "One-sentence description of what this task must accomplish",
          "skill": "implementer_skill",
          "input_paths": ["src/", "package.json"],
          "output_paths": ["src/utils/"],
          "depends_on": []
        },
        {
          "id": "task-id-2",
          "goal": "One-sentence description",
          "skill": "implementer_skill",
          "input_paths": [],
          "output_paths": ["tests/"],
          "depends_on": []
        }
      ]
    },
    {
      "id": 2,
      "tasks": ["task-id-3"],
      "task_definitions": [
        {
          "id": "task-id-3",
          "goal": "...",
          "skill": "implementer_skill",
          "input_paths": ["src/utils/", "tests/"],
          "output_paths": ["dist/"],
          "depends_on": ["task-id-1", "task-id-2"]
        }
      ]
    }
  ],
  "stop_on_wave_failure": false,
  "max_parallel": 4
}
```

## Rules

- Maximum 8 tasks per plan. If the request requires more, group related tasks.
- Never put a task in Wave N if any of its dependencies are also in Wave N.
- `input_paths` and `output_paths` for tasks in the SAME wave MUST NOT OVERLAP.
  Overlapping paths in the same wave would cause merge conflicts.
- If you cannot decompose cleanly (ambiguous dependencies), assign everything to
  Wave 1 sequentially rather than guessing at parallel safety.
- Output ONLY valid JSON. No explanatory text outside the JSON structure.
```

### `supervisor_config.json` additions

```json
{
  "wave_execution": {
    "enabled": true,
    "trigger_threshold": 3,
    "planner_skill": "wave_planner_skill",
    "planner_model": "claude-haiku-3-5",
    "executor": "openclaw/tools/wave_executor.py",
    "max_parallel_agents": 4,
    "workspace_isolation": "copy",
    "stop_on_wave_failure": false,
    "wave_timeout_seconds": 300
  }
}
```

### `agent_profiles.json` additions

```json
{
  "wave_planner": {
    "description": "Decomposes multi-step tasks into parallel wave execution plans",
    "model": "claude-haiku-3-5",
    "allowed_tools": ["Write"],
    "max_tokens": 2048,
    "output_format": "json",
    "temperature": 0.1
  }
}
```

---

## 9. Integration Points

### Orchestrator Prompt Addition

Add to `orchestrator_prompt.md` in the `/go` pipeline section:

```markdown
## Wave Execution (Phase 5)

When processing a `/go` request that involves 3 or more distinct implementation
tasks, use wave execution instead of sequential dispatch:

### Phase 5a: Check Wave Eligibility

Count the discrete implementable tasks in the request. If ≥ 3:
- Dispatch `wave_planner_skill` with the full task description (haiku model)
- Wait for `.openclaw/waves/plan-{ts}.json` to be written
- Read and validate the plan

If < 3 tasks: execute sequentially (no wave overhead needed).

### Phase 5b: Execute Waves

Run `python openclaw/tools/wave_executor.py --plan .openclaw/waves/plan-{ts}.json --project-root .`

Monitor stdout for wave completion messages. The executor is synchronous from
the orchestrator's perspective — it blocks until all waves complete.

### Phase 5c: Collect Results

After wave_executor.py completes, read the JSON summary from stdout.
Report to the user:
- Which tasks completed successfully
- Which tasks failed (with error summaries)
- Which files were created or modified

### Phase 5d: Handle Wave Failures

If any task fails:
1. Surface the failure to the user with the error message.
2. Offer to re-run the failed task in isolation (sequential fallback).
3. Do not re-run the entire wave.

## Sequential Fallback

Tasks can always be run sequentially if wave execution is inappropriate:
- The request explicitly asks for sequential execution
- The task involves only 1-2 implementers
- The task has strict ordering requirements that cannot be parallelized
- Wave execution is disabled in supervisor_config.json
```

### Task File Schema for Wave Tasks

```json
{
  "task_id": "wave-plan-{ts}-wave{N}-{task_id}",
  "wave": 1,
  "plan_id": "wave-plan-{ts}",
  "skill": "implementer_skill",
  "goal": "Implement the user authentication module",
  "workspace_path": ".openclaw/workspaces/wave1-auth/",
  "output_paths": ["src/auth/"],
  "context_pack": {
    "wave": 0,
    "completed_tasks": {},
    "available_outputs": []
  },
  "status": "pending | running | complete | failed | partial"
}
```

---

## 10. Testing Plan

### Unit Test: Wave Planner Output

```python
# tests/test_wave_planner.py

SIMPLE_REQUEST = "Add type annotations to the Python files and write pytest tests"
COMPLEX_REQUEST = """
Migrate this Express.js app to Fastify:
1. Replace Express imports with Fastify
2. Convert route handlers to Fastify syntax
3. Update middleware (cors, helmet, rate-limit)
4. Update test suite
5. Update README
"""

def test_planner_produces_valid_json():
    # Run wave_planner_skill with SIMPLE_REQUEST
    # Assert output is valid JSON
    # Assert waves array has at least 1 entry
    pass

def test_complex_request_uses_waves():
    # Run wave_planner_skill with COMPLEX_REQUEST
    # Assert wave_count >= 2 (docs/tests don't need to wait for everything)
    pass

def test_no_same_wave_dependency():
    # For any plan, verify no task in wave N depends on another task in wave N
    pass

def test_no_output_path_overlap_in_same_wave():
    # For any plan, verify tasks in same wave have non-overlapping output_paths
    pass
```

### Integration Test: Parallel Execution

```bash
# Create a test plan with 3 parallel tasks
cat > /tmp/test-wave-plan.json << 'EOF'
{
  "plan_id": "wave-plan-test",
  "original_request": "Test parallel execution",
  "wave_count": 1,
  "waves": [{
    "id": 1,
    "tasks": ["task-a", "task-b", "task-c"],
    "task_definitions": [
      {
        "id": "task-a",
        "goal": "Write 'task-a done' to /tmp/wave-test/a.txt",
        "skill": "implementer_skill",
        "input_paths": [],
        "output_paths": ["/tmp/wave-test/a.txt"],
        "depends_on": []
      },
      {
        "id": "task-b",
        "goal": "Write 'task-b done' to /tmp/wave-test/b.txt",
        "skill": "implementer_skill",
        "input_paths": [],
        "output_paths": ["/tmp/wave-test/b.txt"],
        "depends_on": []
      },
      {
        "id": "task-c",
        "goal": "Write 'task-c done' to /tmp/wave-test/c.txt",
        "skill": "implementer_skill",
        "input_paths": [],
        "output_paths": ["/tmp/wave-test/c.txt"],
        "depends_on": []
      }
    ]
  }],
  "stop_on_wave_failure": false,
  "max_parallel": 3
}
EOF

time python openclaw/tools/wave_executor.py \
  --plan /tmp/test-wave-plan.json \
  --project-root . \
  --max-parallel 3

# Should complete in approximately the time of ONE task, not THREE
# Verify all output files exist
ls /tmp/wave-test/
# Expected: a.txt  b.txt  c.txt
```

### Context Forwarding Test

```bash
# Verify Wave 2 tasks receive Wave 1 context pack
# Check .openclaw/waves/wave-plan-*-context-wave1.json exists after Wave 1
# Check task files for Wave 2 include the context_pack field populated
```

---

## 11. Example Usage

**User**: `/go Refactor the auth module: extract JWT utilities to a separate file, add TypeScript strict typing, write unit tests, and update the API docs`

**Orchestrator Phase 5a**: Counts tasks — 4 distinct tasks. Eligible for wave execution.

**Wave Planner** output (`.openclaw/waves/plan-1741824000.json`):

```json
{
  "plan_id": "wave-plan-1741824000",
  "wave_count": 3,
  "waves": [
    {
      "id": 1,
      "tasks": ["extract-jwt", "add-types"],
      "task_definitions": [
        {
          "id": "extract-jwt",
          "goal": "Extract JWT encode/decode/verify functions from src/auth/index.ts into src/auth/jwt.ts",
          "skill": "implementer_skill",
          "input_paths": ["src/auth/index.ts"],
          "output_paths": ["src/auth/jwt.ts"],
          "depends_on": []
        },
        {
          "id": "add-types",
          "goal": "Add TypeScript strict type annotations to src/auth/types.ts",
          "skill": "implementer_skill",
          "input_paths": ["src/auth/"],
          "output_paths": ["src/auth/types.ts"],
          "depends_on": []
        }
      ]
    },
    {
      "id": 2,
      "tasks": ["write-tests"],
      "task_definitions": [
        {
          "id": "write-tests",
          "goal": "Write vitest unit tests for src/auth/jwt.ts covering encode, decode, verify, and expiry edge cases",
          "skill": "implementer_skill",
          "input_paths": ["src/auth/jwt.ts", "src/auth/types.ts"],
          "output_paths": ["tests/auth/jwt.test.ts"],
          "depends_on": ["extract-jwt", "add-types"]
        }
      ]
    },
    {
      "id": 3,
      "tasks": ["update-docs"],
      "task_definitions": [
        {
          "id": "update-docs",
          "goal": "Update docs/api-auth.md to document the new jwt.ts module and its TypeScript types",
          "skill": "implementer_skill",
          "input_paths": ["src/auth/jwt.ts", "src/auth/types.ts", "tests/auth/jwt.test.ts", "docs/api-auth.md"],
          "output_paths": ["docs/api-auth.md"],
          "depends_on": ["write-tests"]
        }
      ]
    }
  ]
}
```

**Wave Executor**:
- Wave 1: Spawns `extract-jwt` and `add-types` in parallel. Both complete in ~40s (vs ~80s sequential).
- Wave 1 context pack forwarded to Wave 2: `{completed_tasks: {extract-jwt: {summary: "jwt.ts created with 3 exported functions"}, add-types: {summary: "types.ts updated with JWTPayload, JWTOptions interfaces"}}}`
- Wave 2: Spawns `write-tests` with context. Completes in ~60s.
- Wave 3: Spawns `update-docs` with full context chain. Completes in ~30s.

**Total elapsed**: ~2.2 minutes vs ~3.5 minutes sequential. 37% faster.
