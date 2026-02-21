#!/usr/bin/env python3
"""
Execute hook: consume pending WhatsApp/portal commands and run them.

Options:
1. Call broker's tool API (e.g. search/call)
2. Write to a file that Cursor/Codex watches
3. Emit to a webhook

This script processes the execute queue and hands off to the broker.
"""
import json
import os
import sys
from pathlib import Path

import requests

TRANSCRIPTS_DIR = Path(os.environ.get("WHATSAPP_TRANSCRIPTS_DIR", "/opt/harness/whatsapp-transcripts"))
EXECUTE_QUEUE_FILE = TRANSCRIPTS_DIR / "execute_queue.json"
PROCESSED_DIR = TRANSCRIPTS_DIR / "processed"
BROKER_URL = os.environ.get("BROKER_URL", "http://127.0.0.1:8000")
HOOK_OUTPUT_DIR = Path(os.environ.get("HOOK_OUTPUT_DIR", "/opt/harness/ai/execute_requests"))


def load_queue() -> dict:
    if EXECUTE_QUEUE_FILE.exists():
        try:
            with open(EXECUTE_QUEUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"pending": []}


def save_queue(queue: dict) -> None:
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(EXECUTE_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)


def process_via_broker(command: str, entry_id: str) -> dict:
    """Try to execute via broker search -> call flow."""
    try:
        r = requests.post(
            f"{BROKER_URL}/api/tools/search",
            json={"query": command, "agent_id": "whatsapp-portal"},
            timeout=10,
        )
        if r.status_code != 200:
            return {"ok": False, "error": f"search returned {r.status_code}"}
        data = r.json()
        tools = data.get("tools", [])
        if not tools:
            return {"ok": False, "error": "no tools found", "note": "command queued for manual pick-up"}
        # For now, just record that we found tools - actual call needs approval
        return {"ok": True, "tools_found": len(tools), "note": "approval may be required"}
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}


def write_for_cursor(entry: dict, result: dict) -> None:
    """Write to a file Cursor/Codex can watch for new execute requests."""
    HOOK_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = HOOK_OUTPUT_DIR / f"{entry['id']}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "command": entry["command"],
            "source": entry.get("source", "portal"),
            "created_at": entry.get("created_at"),
            "processed_result": result,
        }, f, indent=2, ensure_ascii=False)


def process_one() -> bool:
    """Process one pending entry. Returns True if one was processed."""
    queue = load_queue()
    pending = queue.get("pending", [])
    if not pending:
        return False
    entry = pending.pop(0)
    entry["status"] = "processing"
    save_queue(queue)

    result = process_via_broker(entry["command"], entry["id"])
    entry["status"] = "done" if result.get("ok") else "failed"
    entry["result"] = result

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    processed_file = PROCESSED_DIR / f"{entry['id']}.json"
    with open(processed_file, "w", encoding="utf-8") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False)

    write_for_cursor(entry, result)
    return True


def main():
    n = 0
    while process_one():
        n += 1
    print(f"Processed {n} execute request(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
