#!/usr/bin/env python3
"""
Self-Update Tool for OpenClaw
Propose, validate, and apply configuration changes to the VPS host
through a secure desired-state pipeline.

Usage:
    python3 self_update_tool.py <operation> [--args '<json>'] [--dry-run] [--approve <id>]

Operations:
    propose     Write files to config_desired/ + generate manifest.json
    diff        Show what would change (current vs proposed)
    validate    Dry-run validation without applying
    apply       Trigger sudo openclaw_apply_config (requires approval)
    rollback    Trigger rollback to last backup (requires approval)
    status      Show current pending/applied/rolled-back state
    history     List recent applied changes
"""

import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HARNESS_ROOT = Path(os.environ.get("HARNESS_ROOT", Path(__file__).resolve().parent.parent.parent))
DESIRED_DIR = HARNESS_ROOT / "config_desired"
BACKUP_ROOT = HARNESS_ROOT / "config_backups"
APPLIED_ROOT = HARNESS_ROOT / "config_applied"
AUDIT_LOG = HARNESS_ROOT / "ai" / "supervisor" / "self_update_audit.jsonl"
PENDING_APPROVALS = HARNESS_ROOT / "ai" / "supervisor" / "pending_approvals.json"
APPLY_SCRIPT = "/usr/local/sbin/openclaw_apply_config"

# SSH config for reaching the host from inside the container
SSH_KEY = HARNESS_ROOT / "secrets" / "openclaw-bot.key"
HOST_GATEWAY = os.environ.get("SELF_UPDATE_HOST", "172.18.0.1")
SSH_USER = "openclaw-bot"

# ---------------------------------------------------------------------------
# Whitelisted destinations (must match the apply script's whitelist)
# ---------------------------------------------------------------------------
ALLOWED_PREFIXES = [
    "/opt/harness/igfetch/",
    "/opt/harness/openclaw/",
    "/opt/harness/scripts/",
    "/opt/harness/adapters/",
    "/opt/harness/ai/supervisor/",
    "/opt/harness/config_desired/",
    "/opt/harness/secrets/",
]

ALLOWED_EXACT = [
    "/etc/systemd/system/igfetch.service",
    "/docker/openclaw-kx9d/docker-compose.yml",
]

DESTRUCTIVE_OPS = {"apply", "rollback"}
APPROVAL_TTL_MINUTES = 30


# ===================================================================
# Audit log
# ===================================================================

def audit(operation: str, params: Dict, result: Any, dry_run: bool = False):
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "op": operation,
        "params": params,
        "dry_run": dry_run,
        "result_summary": _summarize(result),
    }
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _summarize(result: Any) -> str:
    if isinstance(result, dict) and "error" in result:
        return f"error: {result['error']}"
    if isinstance(result, dict) and "status" in result:
        return f"status={result['status']}"
    return "ok"


# ===================================================================
# Approval gate (shared with proxmox_tool)
# ===================================================================

def _load_approvals() -> Dict:
    if PENDING_APPROVALS.exists():
        with open(PENDING_APPROVALS, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"pending": [], "completed": []}


def _save_approvals(data: Dict):
    PENDING_APPROVALS.parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_APPROVALS, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def request_approval(operation: str, params: Dict) -> Dict:
    approval_id = hashlib.sha256(
        f"self_update:{operation}:{json.dumps(params, sort_keys=True)}:{datetime.utcnow().isoformat()}".encode()
    ).hexdigest()[:12]

    approval = {
        "id": approval_id,
        "tool": "self_update",
        "operation": operation,
        "params": params,
        "status": "pending",
        "requested_at": datetime.utcnow().isoformat() + "Z",
        "expires_at": (datetime.utcnow() + timedelta(minutes=APPROVAL_TTL_MINUTES)).isoformat() + "Z",
    }

    data = _load_approvals()
    data["pending"].append(approval)
    _save_approvals(data)

    return {
        "approval_required": True,
        "approval_id": approval_id,
        "operation": operation,
        "params": params,
        "message": (
            f"Self-update operation '{operation}' requires user approval. "
            f"Send the diff summary on WhatsApp and ask the user to confirm. "
            f"Then re-run with --approve {approval_id}"
        ),
        "expires_at": approval["expires_at"],
    }


def check_approval(approval_id: str) -> Optional[Dict]:
    data = _load_approvals()
    for entry in data["pending"]:
        if entry["id"] == approval_id:
            expires = datetime.fromisoformat(entry["expires_at"].rstrip("Z"))
            if datetime.utcnow() > expires:
                entry["status"] = "expired"
                _save_approvals(data)
                return None
            return entry
    return None


def consume_approval(approval_id: str) -> Optional[Dict]:
    data = _load_approvals()
    for i, entry in enumerate(data["pending"]):
        if entry["id"] == approval_id:
            entry["status"] = "consumed"
            entry["consumed_at"] = datetime.utcnow().isoformat() + "Z"
            data["completed"].append(data["pending"].pop(i))
            _save_approvals(data)
            return entry
    return None


# ===================================================================
# Path validation
# ===================================================================

def is_path_allowed(dest: str) -> bool:
    dest = os.path.realpath(dest)

    for exact in ALLOWED_EXACT:
        if dest == exact:
            return True

    for prefix in ALLOWED_PREFIXES:
        if dest.startswith(prefix):
            return True

    return False


# ===================================================================
# Operations
# ===================================================================

def op_propose(params: Dict) -> Dict:
    """
    Write proposed files to config_desired/ and generate manifest.json.

    Expected params:
    {
        "description": "What and why",
        "changes": [
            {
                "source": "relative/path/in/desired",
                "dest": "/absolute/path/on/host",
                "content": "file content as string",
                "owner": "user:group",  (optional, default root:root)
                "mode": "0644",         (optional)
                "restart": "service"    (optional)
            }
        ],
        "health_checks": [
            {"type": "http", "url": "http://...", "expect": 200},
            {"type": "systemd", "service": "svcname", "expect": "active"}
        ]
    }
    """
    description = params.get("description", "(no description)")
    changes = params.get("changes", [])
    health_checks = params.get("health_checks", [])

    if not changes:
        return {"error": "No changes provided"}

    # Validate all dest paths
    for change in changes:
        dest = change.get("dest", "")
        if not is_path_allowed(dest):
            return {"error": f"Destination not whitelisted: {dest}"}
        if not change.get("source"):
            return {"error": "Each change must have a 'source' relative path"}
        if not change.get("content") and change.get("content") != "":
            return {"error": f"Change for {dest} missing 'content'"}

    # Clear any stale desired state
    if DESIRED_DIR.exists():
        for item in DESIRED_DIR.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

    DESIRED_DIR.mkdir(parents=True, exist_ok=True)

    # Write proposed files
    written = []
    for change in changes:
        src_rel = change["source"]
        src_path = DESIRED_DIR / src_rel
        src_path.parent.mkdir(parents=True, exist_ok=True)
        src_path.write_text(change["content"], encoding="utf-8")
        written.append(src_rel)

    # Build manifest (strip 'content' from changes to keep manifest readable)
    manifest_changes = []
    for change in changes:
        mc = {
            "source": change["source"],
            "dest": change["dest"],
        }
        if change.get("owner"):
            mc["owner"] = change["owner"]
        if change.get("mode"):
            mc["mode"] = change["mode"]
        if change.get("restart"):
            mc["restart"] = change["restart"]
        manifest_changes.append(mc)

    manifest = {
        "description": description,
        "proposed_by": "openclaw",
        "proposed_at": datetime.utcnow().isoformat() + "Z",
        "changes": manifest_changes,
        "health_checks": health_checks,
        "status": "pending_approval",
    }

    manifest_path = DESIRED_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "status": "proposed",
        "description": description,
        "files_written": written,
        "manifest": str(manifest_path),
        "num_changes": len(changes),
        "message": "Proposal written. Run 'diff' to preview, then 'apply' (with approval) to deploy.",
    }


def op_diff(params: Dict) -> Dict:
    """Show a unified diff of proposed vs current files."""
    manifest_path = DESIRED_DIR / "manifest.json"
    if not manifest_path.exists():
        return {"error": "No pending proposal. Run 'propose' first."}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    diffs = []

    for change in manifest.get("changes", []):
        src_path = DESIRED_DIR / change["source"]
        dest_path = Path(change["dest"])

        proposed = src_path.read_text(encoding="utf-8").splitlines(keepends=True) if src_path.exists() else []
        current = dest_path.read_text(encoding="utf-8").splitlines(keepends=True) if dest_path.exists() else []

        diff_lines = list(difflib.unified_diff(
            current, proposed,
            fromfile=f"current: {change['dest']}",
            tofile=f"proposed: {change['source']}",
            lineterm="",
        ))

        diffs.append({
            "dest": change["dest"],
            "source": change["source"],
            "is_new": not dest_path.exists(),
            "diff": "\n".join(diff_lines) if diff_lines else "(no changes)",
            "restart": change.get("restart", ""),
        })

    return {
        "status": "diff",
        "description": manifest.get("description", ""),
        "diffs": diffs,
        "num_changes": len(diffs),
    }


def op_validate(params: Dict) -> Dict:
    """Dry-run validation: check paths, file types, sizes, content syntax."""
    manifest_path = DESIRED_DIR / "manifest.json"
    if not manifest_path.exists():
        return {"error": "No pending proposal. Run 'propose' first."}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    issues = []

    for change in manifest.get("changes", []):
        src_path = DESIRED_DIR / change["source"]
        dest = change["dest"]

        # Check source exists
        if not src_path.exists():
            issues.append(f"Source missing: {change['source']}")
            continue

        # Check dest whitelisted
        if not is_path_allowed(dest):
            issues.append(f"Destination not whitelisted: {dest}")

        # Check file size
        size = src_path.stat().st_size
        if size > 1048576:
            issues.append(f"File too large: {change['source']} ({size} bytes)")

        # JSON validation
        if dest.endswith(".json"):
            try:
                json.loads(src_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                issues.append(f"Invalid JSON in {change['source']}: {e}")

        # Python syntax
        if dest.endswith(".py"):
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(src_path)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                issues.append(f"Python syntax error in {change['source']}: {result.stderr.strip()}")

        # Bash syntax
        if dest.endswith(".sh"):
            result = subprocess.run(
                ["bash", "-n", str(src_path)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                issues.append(f"Bash syntax error in {change['source']}: {result.stderr.strip()}")

    if issues:
        return {"status": "validation_failed", "issues": issues}
    return {"status": "validation_ok", "num_changes": len(manifest.get("changes", []))}


def _ssh_to_host(command: str, timeout: int = 120) -> Dict:
    """Execute a command on the VPS host via SSH as openclaw-bot."""
    if not SSH_KEY.exists():
        return {"error": f"SSH key not found: {SSH_KEY}. Run install_self_update.sh first."}

    ssh_cmd = [
        "ssh",
        "-i", str(SSH_KEY),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=10",
        f"{SSH_USER}@{HOST_GATEWAY}",
        command,
    ]

    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True, text=True, timeout=timeout,
        )
        output = result.stdout.strip()
        stderr = result.stderr.strip()

        # Try to parse the last line as JSON
        lines = output.strip().split("\n")
        last_line = lines[-1] if lines else ""
        try:
            result_json = json.loads(last_line)
        except (json.JSONDecodeError, IndexError):
            result_json = {}

        return {
            "exit_code": result.returncode,
            "stdout": output,
            "stderr": stderr,
            "result_json": result_json,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"SSH command timed out after {timeout} seconds"}
    except FileNotFoundError:
        return {"error": "ssh client not found. Install openssh-client."}
    except Exception as exc:
        return {"error": f"SSH command failed: {exc}"}


def op_apply(params: Dict, approve_id: Optional[str] = None) -> Dict:
    """Trigger the apply script on the host via SSH. Requires approval."""
    manifest_path = DESIRED_DIR / "manifest.json"
    if not manifest_path.exists():
        return {"error": "No pending proposal. Run 'propose' first."}

    # Approval gate
    if not approve_id:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return request_approval("apply", {
            "description": manifest.get("description", ""),
            "num_changes": len(manifest.get("changes", [])),
        })

    approval = check_approval(approve_id)
    if not approval:
        return {"error": f"Approval '{approve_id}' not found or expired."}
    consume_approval(approve_id)

    # SSH to host and trigger apply
    ssh_result = _ssh_to_host("apply")

    if "error" in ssh_result:
        return ssh_result

    if ssh_result["exit_code"] == 0:
        return {
            "status": "applied",
            "result": ssh_result.get("result_json", {}),
            "log": ssh_result.get("stdout", ""),
        }
    else:
        return {
            "status": "apply_failed",
            "exit_code": ssh_result["exit_code"],
            "stdout": ssh_result.get("stdout", ""),
            "stderr": ssh_result.get("stderr", ""),
        }


def op_rollback(params: Dict, approve_id: Optional[str] = None) -> Dict:
    """Roll back to the most recent backup via SSH to host."""
    if not BACKUP_ROOT.exists():
        return {"error": "No backups found"}

    backups = sorted(
        [d for d in BACKUP_ROOT.iterdir() if d.is_dir() and d.name[0:2] == "20"],
        reverse=True,
    )
    if not backups:
        return {"error": "No backup directories found"}

    latest = backups[0]

    # Approval gate
    if not approve_id:
        return request_approval("rollback", {
            "backup": str(latest),
            "backup_time": latest.name,
        })

    approval = check_approval(approve_id)
    if not approval:
        return {"error": f"Approval '{approve_id}' not found or expired."}
    consume_approval(approve_id)

    # SSH to host and trigger rollback
    ssh_result = _ssh_to_host("rollback")

    if "error" in ssh_result:
        return ssh_result

    if ssh_result["exit_code"] == 0:
        return {
            "status": "rolled_back",
            "result": ssh_result.get("result_json", {}),
            "log": ssh_result.get("stdout", ""),
        }
    else:
        return {
            "status": "rollback_failed",
            "exit_code": ssh_result["exit_code"],
            "stdout": ssh_result.get("stdout", ""),
            "stderr": ssh_result.get("stderr", ""),
        }


def op_status(params: Dict) -> Dict:
    """Show current state: pending proposals, last applied, last backup."""
    result: Dict[str, Any] = {}

    # Pending proposal
    manifest_path = DESIRED_DIR / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result["pending_proposal"] = {
            "description": manifest.get("description", ""),
            "proposed_at": manifest.get("proposed_at", ""),
            "num_changes": len(manifest.get("changes", [])),
            "status": manifest.get("status", "unknown"),
        }
    else:
        result["pending_proposal"] = None

    # Last applied
    if APPLIED_ROOT.exists():
        applied = sorted(
            [d for d in APPLIED_ROOT.iterdir() if d.is_dir()],
            reverse=True,
        )
        if applied:
            latest = applied[0]
            mf = latest / "manifest.json"
            if mf.exists():
                m = json.loads(mf.read_text(encoding="utf-8"))
                result["last_applied"] = {
                    "directory": str(latest),
                    "description": m.get("description", ""),
                    "applied_at": latest.name,
                    "num_changes": len(m.get("changes", [])),
                }
            else:
                result["last_applied"] = {"directory": str(latest), "applied_at": latest.name}
        else:
            result["last_applied"] = None
    else:
        result["last_applied"] = None

    # Last backup
    if BACKUP_ROOT.exists():
        backups = sorted(
            [d for d in BACKUP_ROOT.iterdir() if d.is_dir() and d.name[0:2] == "20"],
            reverse=True,
        )
        if backups:
            result["last_backup"] = {
                "directory": str(backups[0]),
                "backup_time": backups[0].name,
            }
            result["total_backups"] = len(backups)
        else:
            result["last_backup"] = None
            result["total_backups"] = 0
    else:
        result["last_backup"] = None
        result["total_backups"] = 0

    # Pending approvals for self_update
    approvals = _load_approvals()
    su_pending = [a for a in approvals.get("pending", []) if a.get("tool") == "self_update"]
    result["pending_approvals"] = len(su_pending)

    return result


def op_history(params: Dict) -> Dict:
    """List recent applied changes."""
    limit = params.get("limit", 10)

    entries = []
    if APPLIED_ROOT.exists():
        applied = sorted(
            [d for d in APPLIED_ROOT.iterdir() if d.is_dir()],
            reverse=True,
        )
        for adir in applied[:limit]:
            entry: Dict[str, Any] = {
                "directory": adir.name,
                "failed": adir.name.endswith("-FAILED"),
            }
            mf = adir / "manifest.json"
            if mf.exists():
                try:
                    m = json.loads(mf.read_text(encoding="utf-8"))
                    entry["description"] = m.get("description", "")
                    entry["proposed_at"] = m.get("proposed_at", "")
                    entry["num_changes"] = len(m.get("changes", []))
                except Exception:
                    pass
            entries.append(entry)

    return {"history": entries, "total": len(entries)}


# ===================================================================
# Operation dispatcher
# ===================================================================

OPERATIONS = {
    "propose": op_propose,
    "diff": op_diff,
    "validate": op_validate,
    "apply": op_apply,
    "rollback": op_rollback,
    "status": op_status,
    "history": op_history,
}


def run(operation: str, params: Dict, dry_run: bool = False, approve_id: Optional[str] = None) -> Dict:
    if operation not in OPERATIONS:
        return {"error": f"Unknown operation: {operation}. Valid: {sorted(OPERATIONS.keys())}"}

    if dry_run:
        result = {
            "dry_run": True,
            "operation": operation,
            "params": params,
            "destructive": operation in DESTRUCTIVE_OPS,
        }
        audit(operation, params, result, dry_run=True)
        return result

    # Destructive ops use the approval gate built into their functions
    if operation in DESTRUCTIVE_OPS:
        fn = OPERATIONS[operation]
        result = fn(params, approve_id=approve_id)
    else:
        fn = OPERATIONS[operation]
        result = fn(params)

    audit(operation, params, result)
    return result


# ===================================================================
# CLI
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="OpenClaw Self-Update Tool")
    parser.add_argument("operation", choices=sorted(OPERATIONS.keys()),
                        help="Operation to perform")
    parser.add_argument("--args", default="{}", help="JSON parameters")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    parser.add_argument("--approve", default=None, help="Approval ID for destructive ops")
    args = parser.parse_args()

    try:
        params = json.loads(args.args)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid JSON in --args: {exc}"}))
        sys.exit(1)

    result = run(args.operation, params, dry_run=args.dry_run, approve_id=args.approve)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
