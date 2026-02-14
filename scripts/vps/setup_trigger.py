#!/usr/bin/env python3
"""
Check for setup prompts and run setup_all.sh automatically.
Run via cron every minute: * * * * * cd /opt/harness && python3 scripts/vps/setup_trigger.py

Looks for setup triggers in:
1. execute_queue.json (from portal /api/whatsapp/execute)
2. message_feed.json (from WhatsApp monitor sync)
3. setup_requests/ (files written by OpenClaw skill or webhook)

When found: extracts token, runs setup_all.sh, marks as processed.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", "/opt/harness"))
TRANSCRIPTS_DIR = Path(os.environ.get("WHATSAPP_TRANSCRIPTS_DIR", str(HARNESS_DIR / "whatsapp-transcripts")))
EXECUTE_QUEUE = TRANSCRIPTS_DIR / "execute_queue.json"
FEED_FILE = TRANSCRIPTS_DIR / "message_feed.json"
SETUP_REQUESTS_DIR = HARNESS_DIR / "ai" / "setup_requests"
PROCESSED_FILE = HARNESS_DIR / "ai" / "setup_processed.json"
SETUP_SCRIPT = HARNESS_DIR / "scripts" / "vps" / "setup_all.sh"
SETUP_FLAG = HARNESS_DIR / "ai" / "setup_complete.flag"

TOKEN_PATTERN = re.compile(
    r"(sk-ant-[a-zA-Z0-9\-]+|sk-proj-[a-zA-Z0-9\-]+|sk-[a-zA-Z0-9\-]{20,})"
)
# First-time: any of these triggers setup
SETUP_KEYWORDS = ("set up", "setup", "configure", "configure harness", "openclaw token", "harness token")
# Force: run even if setup was already done
FORCE_KEYWORDS = ("reconfigure", "force setup", "run setup", "run setup again", "re-run setup")


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return default


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def extract_token(text: str) -> str | None:
    m = TOKEN_PATTERN.search(text)
    return m.group(1) if m else None


def is_setup_trigger(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in SETUP_KEYWORDS)


def should_run_setup(text: str) -> bool:
    """Run setup only if: (1) first time (no flag), or (2) explicit force keywords."""
    t = text.lower().strip()
    if any(kw in t for kw in FORCE_KEYWORDS):
        return True
    if not SETUP_FLAG.exists():
        return any(kw in t for kw in SETUP_KEYWORDS)
    return False


def run_setup(token: str = "", force: bool = False) -> bool:
    if not SETUP_SCRIPT.exists():
        return False
    try:
        cmd = [str(SETUP_SCRIPT)]
        if token:
            cmd.extend(["--token", token])
        if force:
            cmd.append("--force")
        result = subprocess.run(
            cmd,
            cwd=str(HARNESS_DIR),
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "HARNESS_DIR": str(HARNESS_DIR)},
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def process_execute_queue() -> str | None:
    queue = load_json(EXECUTE_QUEUE, {"pending": []})
    pending = queue.get("pending", [])
    for i, entry in enumerate(pending):
        cmd = (entry.get("command") or entry.get("text") or "").strip()
        if not should_run_setup(cmd):
            continue
        token = extract_token(cmd)
        force = any(kw in cmd.lower() for kw in FORCE_KEYWORDS)
        if run_setup(token or "", force=force):
            pending.pop(i)
            queue["pending"] = pending
            save_json(EXECUTE_QUEUE, queue)
            return entry.get("id", "exec")
    return None


def process_feed() -> str | None:
    feed = load_json(FEED_FILE, {"messages": []})
    processed = set(load_json(PROCESSED_FILE, {}).get("ids", []))
    messages = feed.get("messages", [])
    for m in reversed(messages):
        content = (m.get("content") or "").strip()
        if not should_run_setup(content):
            continue
        msg_id = f"{m.get('session_id','')}_{m.get('index',0)}"
        if msg_id in processed:
            continue
        token = extract_token(content)
        force = any(kw in content.lower() for kw in FORCE_KEYWORDS)
        if run_setup(token or "", force=force):
            processed.add(msg_id)
            save_json(PROCESSED_FILE, {"ids": list(processed)})
            return msg_id
    return None


def process_setup_requests_dir() -> str | None:
    SETUP_REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
    for f in sorted(SETUP_REQUESTS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            token = data.get("token", "") or extract_token(data.get("message", ""))
            force = data.get("force", False)
            if run_setup(token, force=force):
                f.unlink()
                return f.stem
        except (json.JSONDecodeError, OSError):
            f.unlink()
    return None


def run_monitor_sync() -> None:
    """Run WhatsApp monitor sync to get fresh messages."""
    monitor = HARNESS_DIR / "scripts" / "whatsapp_monitor.py"
    if monitor.exists():
        try:
            subprocess.run(
                [sys.executable, str(monitor)],
                cwd=str(HARNESS_DIR),
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass


def main() -> int:
    run_monitor_sync()
    processed = process_execute_queue()
    if processed:
        print(f"[setup_trigger] Processed execute queue: {processed}")
        return 0
    processed = process_feed()
    if processed:
        print(f"[setup_trigger] Processed feed message: {processed}")
        return 0
    processed = process_setup_requests_dir()
    if processed:
        print(f"[setup_trigger] Processed setup request: {processed}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
