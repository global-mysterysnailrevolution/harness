#!/usr/bin/env python3
"""
WhatsApp monitor HTTP API.

Exposes:
- GET  /api/whatsapp/messages - List recent messages from OpenClaw WhatsApp
- GET  /api/whatsapp/feed      - Raw feed (for polling)
- POST /api/whatsapp/execute   - Submit a command for execution (from portal)
- GET  /api/whatsapp/pending   - List pending execute commands
- POST /api/whatsapp/sync      - Trigger sync from OpenClaw sessions

Run standalone or mount routes into broker_http_server.
"""
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request

# Paths
TRANSCRIPTS_DIR = Path(os.environ.get("WHATSAPP_TRANSCRIPTS_DIR", "/opt/harness/whatsapp-transcripts"))
FEED_FILE = TRANSCRIPTS_DIR / "message_feed.json"
EXECUTE_QUEUE_FILE = TRANSCRIPTS_DIR / "execute_queue.json"
MONITOR_SCRIPT = Path(__file__).resolve().parent / "whatsapp_monitor.py"

app = Flask(__name__)


def load_json(path: Path, default):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return default


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_sync() -> dict:
    """Run whatsapp_monitor sync and return feed."""
    try:
        result = subprocess.run(
            [os.environ.get("PYTHON", "python3"), str(MONITOR_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(MONITOR_SCRIPT.parent),
        )
        if result.returncode == 0:
            return load_json(FEED_FILE, {"messages": [], "last_sync": None})
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return load_json(FEED_FILE, {"messages": [], "last_sync": None})


@app.route("/api/whatsapp/messages", methods=["GET"])
def get_messages():
    """List recent WhatsApp messages (from feed)."""
    limit = request.args.get("limit", 50, type=int)
    limit = min(max(limit, 1), 200)
    feed = load_json(FEED_FILE, {"messages": []})
    messages = feed.get("messages", [])[-limit:]
    return jsonify({
        "messages": messages,
        "count": len(messages),
        "last_sync": feed.get("last_sync"),
    })


@app.route("/api/whatsapp/feed", methods=["GET"])
def get_feed():
    """Raw feed (for polling clients)."""
    feed = load_json(FEED_FILE, {"messages": [], "last_sync": None})
    return jsonify(feed)


@app.route("/api/whatsapp/sync", methods=["POST"])
def trigger_sync():
    """Trigger sync from OpenClaw sessions."""
    feed = run_sync()
    return jsonify({
        "ok": True,
        "message_count": len(feed.get("messages", [])),
        "last_sync": feed.get("last_sync"),
    })


@app.route("/api/whatsapp/execute", methods=["POST"])
def submit_execute():
    """
    Submit a command for execution (from portal).
    Body: { "command": "do something", "source": "portal" }
    """
    data = request.get_json() or {}
    command = data.get("command") or data.get("text", "").strip()
    if not command:
        return jsonify({"error": "command or text required"}), 400
    queue = load_json(EXECUTE_QUEUE_FILE, {"pending": []})
    entry = {
        "id": datetime.utcnow().strftime("%Y%m%d_%H%M%S") + "_" + str(len(queue.get("pending", []))),
        "command": command,
        "source": data.get("source", "portal"),
        "status": "pending",
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    queue.setdefault("pending", []).append(entry)
    save_json(EXECUTE_QUEUE_FILE, queue)
    return jsonify({"ok": True, "id": entry["id"], "status": "pending"})


@app.route("/api/whatsapp/pending", methods=["GET"])
def list_pending():
    """List pending execute commands."""
    queue = load_json(EXECUTE_QUEUE_FILE, {"pending": []})
    return jsonify({"pending": queue.get("pending", [])})


@app.route("/api/whatsapp/health", methods=["GET"])
def health():
    """Health check."""
    return jsonify({"ok": True, "service": "whatsapp-monitor"})


@app.route("/", methods=["GET"])
def portal():
    """Simple portal to view messages and submit execute commands."""
    html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>WhatsApp Monitor</title>
<style>
body{font-family:system-ui;max-width:800px;margin:2em auto;padding:1em;background:#1a1a1a;color:#eee}
h1{color:#0af}a{color:#0af}button{background:#0af;color:#000;border:none;padding:8px 16px;cursor:pointer;border-radius:4px}
button:hover{background:#09e}input,textarea{width:100%;padding:8px;margin:4px 0;background:#333;border:1px solid #555;color:#fff;border-radius:4px}
.messages{border:1px solid #444;border-radius:8px;padding:1em;margin:1em 0;max-height:400px;overflow-y:auto}
.msg{margin:6px 0;padding:6px;background:#252525;border-radius:4px;font-size:0.9em}
.role{color:#0af;font-weight:bold}
</style>
</head>
<body>
<h1>WhatsApp Monitor</h1>
<p><a href="/api/whatsapp/messages">API: messages</a> | <a href="/api/whatsapp/pending">pending</a></p>
<h2>Submit command</h2>
<form id="exec" onsubmit="return submitCmd(event)">
<input type="text" name="command" placeholder="Command to execute (e.g. search for X)" required>
<button type="submit">Execute</button>
</form>
<p id="exec-result"></p>
<h2>Recent messages</h2>
<button onclick="syncThenLoad()">Sync & Refresh</button>
<button onclick="loadMessages()">Refresh only</button>
<div class="messages" id="msgs">Loading...</div>
<script>
async function syncThenLoad(){
  document.getElementById('msgs').textContent='Syncing...';
  await fetch('/api/whatsapp/sync',{method:'POST'});
  await loadMessages();
}
async function loadMessages(){
  document.getElementById('msgs').textContent='Loading...';
  const r=await fetch('/api/whatsapp/messages');
  const d=await r.json();
  const msgs=d.messages||[];
  document.getElementById('msgs').innerHTML=msgs.length?msgs.slice(-30).reverse().map(m=>
    '<div class="msg"><span class="role">'+m.role+'</span>: '+String(m.content||'').slice(0,200)+'</div>'
  ).join(''):'<p>No messages. Run sync first.</p>';
}
async function submitCmd(e){
  e.preventDefault();
  const cmd=e.target.command.value;
  const r=await fetch('/api/whatsapp/execute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:cmd})});
  const d=await r.json();
  document.getElementById('exec-result').textContent=d.ok?'Queued: '+d.id:'Error: '+(d.error||'unknown');
  e.target.command.value='';
  return false;
}
loadMessages();
setInterval(loadMessages,15000);
</script>
</body>
</html>"""
    from flask import Response
    return Response(html, mimetype="text/html")


def create_app():
    return app


if __name__ == "__main__":
    port = int(os.environ.get("WHATSAPP_MONITOR_PORT", 8001))
    host = os.environ.get("WHATSAPP_MONITOR_HOST", "127.0.0.1")
    print(f"WhatsApp monitor API: http://{host}:{port}")
    print("  GET  /api/whatsapp/messages  - List messages")
    print("  POST /api/whatsapp/execute   - Submit command")
    print("  GET  /api/whatsapp/pending   - Pending commands")
    print("  POST /api/whatsapp/sync      - Trigger sync")
    app.run(host=host, port=port, debug=False, threaded=True)
