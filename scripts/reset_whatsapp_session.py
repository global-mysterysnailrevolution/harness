#!/usr/bin/env python3
"""
Reset WhatsApp/OpenClaw session to fix context overflow.
Creates a new sessionId so the next message starts fresh.
"""
import json
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

CONTAINER = "openclaw-kx9d-openclaw-1"
SESSIONS_FILE = "/data/.openclaw/agents/main/sessions/sessions.json"
SESSIONS_DIR = "/data/.openclaw/agents/main/sessions"
BACKUP_DIR = Path("/opt/harness/whatsapp-transcripts")

def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    print("=== Reset WhatsApp Session (Fresh Start) ===\n")

    # 1. Fetch sessions.json
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "cat", SESSIONS_FILE],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        print("Error: could not read sessions")
        return 1

    data = json.loads(result.stdout)
    backup = BACKUP_DIR / f"sessions_reset_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    backup.write_text(result.stdout)
    print(f"1. Backed up to {backup}")

    # 2. For each session, assign new sessionId (fresh transcript)
    new_ids = {}
    for skey, entry in data.items():
        if isinstance(entry, dict) and "sessionId" in entry:
            old_id = entry["sessionId"]
            new_id = str(uuid.uuid4())
            entry["sessionId"] = new_id
            entry["updatedAt"] = int(datetime.now().timestamp() * 1000)
            # Clear token counters
            for k in ("contextTokens", "inputTokens", "outputTokens", "totalTokens"):
                if k in entry:
                    entry[k] = 0
            new_ids[skey] = (old_id, new_id)
            print(f"   {skey}: {old_id[:8]}... -> {new_id[:8]}...")

    # 3. Write back
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "sh", "-c", f"cat > {SESSIONS_FILE}"],
        input=json.dumps(data, indent=2), text=True, check=True, timeout=10
    )
    print("\n2. Session IDs reset")

    # 4. Restart OpenClaw
    subprocess.run(["docker", "restart", CONTAINER], check=True, timeout=30)
    print("3. OpenClaw restarted\nDone. Next message will start fresh.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
