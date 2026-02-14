#!/usr/bin/env python3
"""
WhatsApp message monitor for OpenClaw.
Polls OpenClaw session data, extracts messages, maintains local feed for setup trigger.
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

OPENCLAW_CONTAINER = os.environ.get("OPENCLAW_CONTAINER", "openclaw-kx9d-openclaw-1")
SESSIONS_FILE = os.environ.get("OPENCLAW_SESSIONS_FILE", "/data/.openclaw/agents/main/sessions/sessions.json")
TRANSCRIPTS_DIR = Path(os.environ.get("WHATSAPP_TRANSCRIPTS_DIR", "/opt/harness/whatsapp-transcripts"))
FEED_FILE = TRANSCRIPTS_DIR / "message_feed.json"
DOCKER_CMD = os.environ.get("DOCKER_CMD", "docker")


def get_sessions_via_docker():
    try:
        result = subprocess.run(
            [DOCKER_CMD, "exec", OPENCLAW_CONTAINER, "cat", SESSIONS_FILE],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def extract_messages(sessions):
    messages = []
    for session_id, data in (sessions or {}).items():
        if not isinstance(data, dict):
            continue
        for key in ("messages", "history", "messagesHistory"):
            arr = data.get(key)
            if isinstance(arr, list):
                for i, m in enumerate(arr):
                    if isinstance(m, dict):
                        messages.append({
                            "session_id": session_id, "index": i,
                            "role": m.get("role", m.get("type", "unknown")),
                            "content": m.get("content", m.get("text", str(m))),
                            "ts": m.get("timestamp", m.get("ts", "")),
                        })
    return messages


def load_feed():
    if FEED_FILE.exists():
        try:
            return json.loads(FEED_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"messages": [], "last_updated": None, "last_sync": None}


def save_feed(feed):
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    feed["last_updated"] = datetime.utcnow().isoformat() + "Z"
    FEED_FILE.write_text(json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8")


def sync():
    feed = load_feed()
    sessions = get_sessions_via_docker()
    if not sessions:
        return feed
    msgs = extract_messages(sessions)
    seen = {(m["session_id"], m["index"]) for m in feed.get("messages", [])}
    for m in msgs:
        if (m["session_id"], m["index"]) not in seen:
            seen.add((m["session_id"], m["index"]))
            feed.setdefault("messages", []).append(m)
    feed["messages"] = feed["messages"][-500:]
    feed["last_sync"] = datetime.utcnow().isoformat() + "Z"
    save_feed(feed)
    return feed


if __name__ == "__main__":
    feed = sync()
    print(f"Synced {len(feed.get('messages', []))} messages")
