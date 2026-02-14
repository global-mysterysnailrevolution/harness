"""
Lightweight observability UI server.

Serves a single-page app that:
- Streams events via SSE (Server-Sent Events)
- Displays an event timeline with filtering
- Provides drilldown into event payloads

Run: python -m contextforge.packages.ui.server [--port 8900] [--log-path path/to/events.jsonl]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
from typing import Optional

DEFAULT_PORT = 8900
DEFAULT_LOG = os.environ.get(
    "CONTEXTFORGE_EVENT_LOG",
    str(Path(__file__).resolve().parents[3] / "ai" / "supervisor" / "contextforge_events.jsonl"),
)


def _get_html() -> str:
    """Return the single-page UI HTML."""
    return r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ContextForge — Event Timeline</title>
<style>
  :root { --bg: #0d1117; --fg: #c9d1d9; --border: #30363d; --accent: #58a6ff;
          --green: #3fb950; --yellow: #d29922; --red: #f85149; --dim: #8b949e; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
         background: var(--bg); color: var(--fg); font-size: 14px; }
  header { background: #161b22; border-bottom: 1px solid var(--border); padding: 12px 20px;
           display: flex; align-items: center; gap: 16px; }
  header h1 { font-size: 18px; font-weight: 600; }
  header .status { font-size: 12px; color: var(--dim); }
  header .status.connected { color: var(--green); }
  .filters { background: #161b22; border-bottom: 1px solid var(--border); padding: 8px 20px;
             display: flex; gap: 12px; flex-wrap: wrap; }
  .filters input, .filters select { background: var(--bg); color: var(--fg); border: 1px solid var(--border);
    border-radius: 6px; padding: 4px 8px; font-size: 13px; }
  .filters input { width: 200px; }
  .timeline { padding: 12px 20px; max-width: 1200px; }
  .event { border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px;
           padding: 10px 14px; cursor: pointer; transition: border-color 0.15s; }
  .event:hover { border-color: var(--accent); }
  .event-header { display: flex; justify-content: space-between; align-items: center; }
  .event-type { font-weight: 600; font-family: monospace; font-size: 13px; }
  .event-time { color: var(--dim); font-size: 12px; font-family: monospace; }
  .event-meta { display: flex; gap: 8px; margin-top: 4px; font-size: 12px; color: var(--dim); }
  .badge { padding: 1px 6px; border-radius: 10px; font-size: 11px; font-weight: 600; }
  .badge.info { background: #1f6feb33; color: var(--accent); }
  .badge.warn { background: #d2992233; color: var(--yellow); }
  .badge.error, .badge.critical { background: #f8514933; color: var(--red); }
  .badge.debug { background: #30363d; color: var(--dim); }
  .drilldown { display: none; margin-top: 8px; padding: 8px; background: #161b22;
               border-radius: 6px; font-family: monospace; font-size: 12px;
               white-space: pre-wrap; max-height: 300px; overflow: auto; }
  .event.expanded .drilldown { display: block; }
  .counter { background: #161b22; border: 1px solid var(--border); border-radius: 6px;
             padding: 2px 8px; font-size: 12px; }
</style>
</head>
<body>
<header>
  <h1>ContextForge</h1>
  <span class="status" id="status">Connecting...</span>
  <span class="counter" id="counter">0 events</span>
</header>
<div class="filters">
  <input type="text" id="filter-text" placeholder="Filter by text..." />
  <select id="filter-component">
    <option value="">All components</option>
    <option value="analyzer">analyzer</option>
    <option value="generator">generator</option>
    <option value="memory">memory</option>
    <option value="security">security</option>
    <option value="broker">broker</option>
    <option value="config_guard">config_guard</option>
  </select>
  <select id="filter-severity">
    <option value="">All severities</option>
    <option value="debug">debug</option>
    <option value="info">info</option>
    <option value="warn">warn</option>
    <option value="error">error</option>
    <option value="critical">critical</option>
  </select>
  <input type="text" id="filter-run" placeholder="Run ID..." />
</div>
<div class="timeline" id="timeline"></div>
<script>
const timeline = document.getElementById('timeline');
const status = document.getElementById('status');
const counter = document.getElementById('counter');
const filterText = document.getElementById('filter-text');
const filterComp = document.getElementById('filter-component');
const filterSev = document.getElementById('filter-severity');
const filterRun = document.getElementById('filter-run');
let events = [];
let eventSource;

function connect() {
  eventSource = new EventSource('/events');
  eventSource.onopen = () => { status.textContent = 'Connected'; status.className = 'status connected'; };
  eventSource.onerror = () => { status.textContent = 'Disconnected'; status.className = 'status'; };
  eventSource.onmessage = (e) => {
    try {
      const evt = JSON.parse(e.data);
      events.unshift(evt);
      if (events.length > 1000) events.pop();
      counter.textContent = events.length + ' events';
      renderEvent(evt, true);
    } catch (err) {}
  };
}

function renderEvent(evt, prepend) {
  if (!matchesFilter(evt)) return;
  const div = document.createElement('div');
  div.className = 'event';
  div.onclick = () => div.classList.toggle('expanded');
  const sev = evt.severity || 'info';
  const ts = evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : '';
  const runId = (evt.correlation && evt.correlation.run_id) ? evt.correlation.run_id.slice(0,8) : '';
  div.innerHTML = `
    <div class="event-header">
      <span class="event-type">${esc(evt.event_type)}</span>
      <span class="event-time">${esc(ts)}</span>
    </div>
    <div class="event-meta">
      <span class="badge ${sev}">${sev}</span>
      <span>${esc(evt.component || '')}</span>
      ${runId ? '<span>run:' + esc(runId) + '</span>' : ''}
      ${evt.duration_ms ? '<span>' + evt.duration_ms + 'ms</span>' : ''}
    </div>
    <div class="drilldown">${esc(JSON.stringify(evt, null, 2))}</div>`;
  if (prepend) timeline.prepend(div); else timeline.appendChild(div);
}

function matchesFilter(evt) {
  const text = filterText.value.toLowerCase();
  const comp = filterComp.value;
  const sev = filterSev.value;
  const run = filterRun.value;
  if (text && !JSON.stringify(evt).toLowerCase().includes(text)) return false;
  if (comp && evt.component !== comp) return false;
  if (sev && evt.severity !== sev) return false;
  if (run && (!evt.correlation || !evt.correlation.run_id.startsWith(run))) return false;
  return true;
}

function rerender() {
  timeline.innerHTML = '';
  events.forEach(e => renderEvent(e, false));
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

[filterText, filterComp, filterSev, filterRun].forEach(el => el.addEventListener('input', rerender));

// Load existing events
fetch('/events/history').then(r => r.json()).then(data => {
  events = data.reverse();
  counter.textContent = events.length + ' events';
  events.forEach(e => renderEvent(e, false));
});

connect();
</script>
</body>
</html>"""


class UIHandler(BaseHTTPRequestHandler):
    """HTTP handler for the observability UI."""

    log_path: str = DEFAULT_LOG

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_html()
        elif self.path == "/events":
            self._serve_sse()
        elif self.path == "/events/history":
            self._serve_history()
        elif self.path == "/health":
            self._serve_json({"status": "ok"})
        else:
            self.send_error(404)

    def _serve_html(self):
        content = _get_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_json(self, data):
        content = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_history(self):
        """Return last 200 events as JSON array."""
        events = []
        log_path = Path(self.log_path)
        if log_path.exists():
            try:
                lines = log_path.read_text(encoding="utf-8").strip().splitlines()
                for line in lines[-200:]:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            except OSError:
                pass
        self._serve_json(events)

    def _serve_sse(self):
        """Stream new events as Server-Sent Events."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        log_path = Path(self.log_path)

        # Start from end of file
        try:
            if log_path.exists():
                f = open(log_path, "r", encoding="utf-8")
                f.seek(0, 2)  # seek to end
            else:
                f = None

            while True:
                if f is None and log_path.exists():
                    f = open(log_path, "r", encoding="utf-8")
                    f.seek(0, 2)

                if f:
                    line = f.readline()
                    if line:
                        line = line.strip()
                        if line:
                            self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                            self.wfile.flush()
                    else:
                        time.sleep(0.5)
                else:
                    time.sleep(1)

        except (BrokenPipeError, ConnectionResetError):
            if f:
                f.close()

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def run_server(port: int = DEFAULT_PORT, log_path: str = DEFAULT_LOG):
    """Start the UI server."""
    UIHandler.log_path = log_path
    server = HTTPServer(("127.0.0.1", port), UIHandler)
    print(f"ContextForge UI: http://127.0.0.1:{port}")
    print(f"Events log: {log_path}")
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="ContextForge Observability UI")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--log-path", default=DEFAULT_LOG)
    args = parser.parse_args()
    run_server(args.port, args.log_path)


if __name__ == "__main__":
    main()
