"""
Spawns a sub-agent session and waits for its result.
The Agent tool equivalent for OpenClaw.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import shutil
from pathlib import Path
from datetime import datetime

MAX_POLL_SECONDS = 300
POLL_INTERVAL_SECONDS = 2


def spawn_and_wait(
    skill: str,
    task: str,
    context: dict,
    parent_id: str,
    openclaw_dir: str = "openclaw",
    chain_depth: int = 0,
    max_depth: int = 3,
    output_file: str = None
) -> dict:
    """
    Spawn a sub-agent session and wait for its result.

    Returns: {"status": "complete|failed|timeout|depth_limit", "result": {...}, "error": str}
    """
    if chain_depth >= max_depth:
        return {
            "status": "depth_limit",
            "result": None,
            "error": f"Chain depth limit ({max_depth}) reached. Cannot spawn {skill}."
        }

    ts = int(datetime.now().timestamp())
    task_id = f"chain-{parent_id}-{skill.replace('_skill','')}-{ts}"
    tasks_dir = Path(".openclaw/tasks")
    tasks_dir.mkdir(parents=True, exist_ok=True)

    task_file = tasks_dir / f"{task_id}.json"
    result_file = tasks_dir / f"{task_id}-result.json"

    # Write task file for sub-agent
    task_data = {
        "task_id": task_id,
        "skill": skill,
        "goal": task,
        "context": context,
        "parent_id": parent_id,
        "chain_depth": chain_depth + 1,
        "max_chain_depth": max_depth,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    task_file.write_text(json.dumps(task_data, indent=2))

    # Build the command to run the sub-agent session
    runner_cmd = _find_runner_cmd(openclaw_dir)
    if not runner_cmd:
        return {
            "status": "failed",
            "result": None,
            "error": "OpenClaw session runner not found. Check installation."
        }

    cmd = runner_cmd + [
        "--skill", skill,
        "--task", str(task_file),
        "--output", str(result_file),
        "--chain-depth", str(chain_depth + 1)
    ]

    # Start sub-agent as subprocess (non-blocking)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Poll for result file
    start = time.time()
    while time.time() - start < MAX_POLL_SECONDS:
        if result_file.exists():
            try:
                result_data = json.loads(result_file.read_text())
                status = result_data.get("status", "complete")
                return {"status": status, "result": result_data, "error": ""}
            except json.JSONDecodeError:
                pass  # File not fully written yet, keep polling

        if proc.poll() is not None:
            # Process exited -- check if result file was written
            if result_file.exists():
                try:
                    result_data = json.loads(result_file.read_text())
                    return {
                        "status": result_data.get("status", "complete"),
                        "result": result_data,
                        "error": ""
                    }
                except json.JSONDecodeError:
                    pass
            stderr = proc.stderr.read() if proc.stderr else ""
            return {
                "status": "failed",
                "result": None,
                "error": f"Sub-agent exited without result. stderr: {stderr[:500]}"
            }

        time.sleep(POLL_INTERVAL_SECONDS)

    # Timeout
    proc.kill()
    return {
        "status": "timeout",
        "result": None,
        "error": f"Sub-agent {skill} timed out after {MAX_POLL_SECONDS}s"
    }


def _find_runner_cmd(openclaw_dir: str) -> list:
    """Find the OpenClaw session runner command."""
    candidates = [
        ["openclaw", "run"],
        ["python", "-m", "openclaw.runner"],
        [os.path.join(openclaw_dir, "runner.py")],
    ]
    for cmd in candidates:
        if shutil.which(cmd[0]):
            return cmd
    return None


def main():
    parser = argparse.ArgumentParser(description="Spawn and wait for a sub-agent session")
    parser.add_argument("--skill", required=True, help="Skill name to invoke")
    parser.add_argument("--task", required=True, help="Task description")
    parser.add_argument("--context", default="{}", help="JSON context to pass to sub-agent")
    parser.add_argument("--parent-id", required=True, help="Parent task ID (for lineage tracking)")
    parser.add_argument("--chain-depth", type=int, default=0, help="Current chain depth")
    parser.add_argument("--max-depth", type=int, default=3, help="Maximum chain depth")
    parser.add_argument("--openclaw-dir", default="openclaw")
    parser.add_argument("--output", help="Write result to file instead of stdout")
    args = parser.parse_args()

    context = json.loads(args.context)
    result = spawn_and_wait(
        skill=args.skill,
        task=args.task,
        context=context,
        parent_id=args.parent_id,
        openclaw_dir=args.openclaw_dir,
        chain_depth=args.chain_depth,
        max_depth=args.max_depth
    )

    result_json = json.dumps(result, indent=2)

    if args.output:
        Path(args.output).write_text(result_json)
    else:
        print(result_json)

    sys.exit(0 if result["status"] in ("complete", "partial") else 1)


if __name__ == "__main__":
    main()
