#!/usr/bin/env python3
"""Add a number to OpenClaw WhatsApp allowFrom. Usage: python3 add_whatsapp_number.py +15551234567"""
import json
import sys
from pathlib import Path

CONFIG = Path("/docker/openclaw-kx9d/data/.openclaw/openclaw.json")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 add_whatsapp_number.py +15551234567")
        return 1
    num = sys.argv[1].lstrip("+").replace("-", "").replace(" ", "")
    if not num.isdigit():
        print("Invalid number")
        return 1
    data = json.loads(CONFIG.read_text())
    wa = data["channels"]["whatsapp"]
    allow = set(str(n).replace("+", "").replace("-", "").replace(" ", "") for n in wa.get("allowFrom", []))
    allow.add(num)
    wa["allowFrom"] = sorted(allow)
    CONFIG.write_text(json.dumps(data, indent=2))
    print("Added. allowFrom:", wa["allowFrom"])
    print("Run: docker restart openclaw-kx9d-openclaw-1")
    return 0

if __name__ == "__main__":
    sys.exit(main())
