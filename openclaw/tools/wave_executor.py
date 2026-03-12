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
    outputs: list
    summary: str
    errors: list = field(default_factory=list)
    workspace_path: Optional[str] = None


class WaveExecutor:
    def __init__(
        self,
        plan_file: str,
        project_root: str,
        openclaw_dir: str = ".openclaw",
        max_parallel: int = 4,
        skill_runner_cmd: Optional[list] = None
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
        self.all_results: dict = {}
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
        task_ids: list,
        wave_num: int,
        context_pack: dict
    ) -> dict:
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
            # No specific inputs declared -- copy entire project
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
                        print(f"[WaveExecutor] Potential conflict on {rel_path} -- review needed")
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    def _build_context_pack(self, wave_num: int, results: dict) -> dict:
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
