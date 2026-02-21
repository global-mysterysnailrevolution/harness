#!/usr/bin/env python3
"""
Clear AND truncate session history to fix context window overflow.
Keeps only last N messages per session, clears skillsSnapshot.prompt.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CONTAINER = "openclaw-kx9d-openclaw-1"
SESSIONS_FILE = "/data/.openclaw/agents/main/sessions/sessions.json"
BACKUP_DIR = Path("/opt/harness/whatsapp-transcripts")
MAX_MESSAGES = 10  # Keep only last 10 messages per session

def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    print("=== Clear + Truncate Session History ===\n")

    # 1. Fetch current sessions
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "cat", SESSIONS_FILE],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        print("Error: could not read sessions")
        return 1

    data = json.loads(result.stdout)
    backup_file = BACKUP_DIR / f"sessions_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    backup_file.write_text(result.stdout)
    print(f"1. Backed up to {backup_file}")

    # 2. Truncate each session
    for sid, session in data.items():
        if not isinstance(session, dict):
            continue
        # Clear skillsSnapshot prompt
        if "skillsSnapshot" in session and isinstance(session["skillsSnapshot"], dict):
            session["skillsSnapshot"]["prompt"] = ""
        # Truncate messages/history
        for key in ("messages", "history", "messagesHistory"):
            arr = session.get(key)
            if isinstance(arr, list) and len(arr) > MAX_MESSAGES:
                session[key] = arr[-MAX_MESSAGES:]
                print(f"   Session {sid[:30]}...: truncated {len(arr)} -> {MAX_MESSAGES} messages")

    # 3. Write back
    cleared = json.dumps(data, indent=2)
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "sh", "-c", f"cat > {SESSIONS_FILE}"],
        input=cleared, text=True, check=True, timeout=10
    )
    print("\n2. Session history truncated and cleared")

    # 4. Restart
    subprocess.run(["docker", "restart", CONTAINER], check=True, timeout=30)
    print("3. OpenClaw restarted\nDone.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
