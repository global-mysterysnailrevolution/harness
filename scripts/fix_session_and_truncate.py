#!/usr/bin/env python3
"""
Fix context overflow:
1. Remove sessionFile override (it points to OLD bloated transcript)
2. Create fresh transcript for new sessionId
3. Archive/delete the bloated transcript
"""
import json
import subprocess
import sys
from pathlib import Path

CONTAINER = "openclaw-kx9d-openclaw-1"
SESSIONS_FILE = "/data/.openclaw/agents/main/sessions/sessions.json"
SESSIONS_DIR = "/data/.openclaw/agents/main/sessions"
BACKUP_DIR = Path("/opt/harness/whatsapp-transcripts")

def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    print("=== Fix Session: Remove bloated transcript ===\n")

    # 1. Get sessions
    r = subprocess.run(
        ["docker", "exec", CONTAINER, "cat", SESSIONS_FILE],
        capture_output=True, text=True, timeout=10
    )
    if r.returncode != 0:
        print("Error reading sessions"); return 1

    data = json.loads(r.stdout)
    backup = BACKUP_DIR / "sessions_pre_fix.json"
    backup.write_text(r.stdout)
    print(f"1. Backed up to {backup}")

    # 2. For each session: remove sessionFile, ensure fresh sessionId
    for skey, entry in data.items():
        if not isinstance(entry, dict):
            continue
        # Remove sessionFile - forces use of default <sessionId>.jsonl
        if "sessionFile" in entry:
            old_file = entry.pop("sessionFile")
            print(f"   {skey}: removed sessionFile -> {old_file}")

        # Generate new sessionId to force fresh transcript
        import uuid
        entry["sessionId"] = str(uuid.uuid4())
        entry["updatedAt"] = 0  # will be updated on next message

    # 3. Write back
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "sh", "-c", f"cat > {SESSIONS_FILE}"],
        input=json.dumps(data, indent=2), text=True, check=True, timeout=10
    )
    print("\n2. Removed sessionFile, new sessionId")

    # 4. Archive the bloated transcript (don't delete - keep for backup)
    r2 = subprocess.run(
        ["docker", "exec", CONTAINER, "sh", "-c", f"mv {SESSIONS_DIR}/2751887a-8b78-48a3-8158-441180c4ea05.jsonl {SESSIONS_DIR}/2751887a-8b78-48a3-8158-441180c4ea05.jsonl.archived 2>/dev/null || true"],
        capture_output=True, timeout=5
    )
    print("3. Archived old transcript")

    # 5. Restart
    subprocess.run(["docker", "restart", CONTAINER], check=True, timeout=30)
    print("4. OpenClaw restarted\nDone. Next message starts with empty transcript.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
