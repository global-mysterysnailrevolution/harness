#!/usr/bin/env python3
"""
Setup trigger HTTP API. Run on VPS; call via POST to trigger full setup.
Usage: python3 setup_trigger_server.py [--port 8003]
Requires: pip install flask

POST /trigger  Body: {"token": "sk-xxx"} or {"message": "set up. Token: sk-xxx"}
GET  /health   Liveness
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    from flask import Flask, jsonify, request
except ImportError:
    print("Install Flask: pip install flask", file=sys.stderr)
    sys.exit(1)

HARNESS_DIR = Path(__file__).resolve().parent.parent.parent
SETUP_SCRIPT = HARNESS_DIR / "scripts" / "vps" / "setup_all.sh"
TOKEN_PATTERN = re.compile(r"(sk-ant-[a-zA-Z0-9\-]+|sk-proj-[a-zA-Z0-9\-]+|sk-[a-zA-Z0-9\-]{20,})")

app = Flask(__name__)


def run_setup(token: str = "") -> bool:
    if not SETUP_SCRIPT.exists():
        return False
    try:
        cmd = [str(SETUP_SCRIPT)]
        if token:
            cmd.extend(["--token", token])
        result = subprocess.run(
            cmd,
            cwd=str(HARNESS_DIR),
            capture_output=True,
            text=True,
            timeout=120,
            env={**__import__("os").environ, "HARNESS_DIR": str(HARNESS_DIR)},
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


@app.route("/trigger", methods=["POST"])
@app.route("/api/setup/trigger", methods=["POST"])
def trigger():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()
    if not token and data.get("message"):
        m = TOKEN_PATTERN.search(data["message"])
        token = m.group(1) if m else ""
    ok = run_setup(token)
    return jsonify({"ok": ok, "message": "Setup completed" if ok else "Setup failed"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
