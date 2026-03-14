const http = require('http');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const PORT = 3457;
const TRACE_DIR = __dirname;
const EVENTS_FILE = path.join(TRACE_DIR, 'events.jsonl');
const SESSIONS_FILE = path.join(TRACE_DIR, 'sessions.json');
const DASHBOARD_FILE = path.join(TRACE_DIR, 'dashboard.html');
const MAX_EVENTS_BYTES = 50 * 1024 * 1024; // 50MB rotation threshold

if (!fs.existsSync(EVENTS_FILE)) fs.writeFileSync(EVENTS_FILE, '');
if (!fs.existsSync(SESSIONS_FILE)) fs.writeFileSync(SESSIONS_FILE, '{}');

const clients = new Set();

// Token cost estimates per tool (rough, based on typical usage)
const TOKEN_ESTIMATES = {
  Agent: { input: 15000, output: 5000 },
  Read: { input: 500, output: 2000 },
  Write: { input: 2000, output: 100 },
  Edit: { input: 2000, output: 100 },
  Bash: { input: 500, output: 1000 },
  Glob: { input: 200, output: 500 },
  Grep: { input: 300, output: 1000 },
  WebFetch: { input: 500, output: 3000 },
  WebSearch: { input: 300, output: 2000 },
  Skill: { input: 5000, output: 2000 },
  CronCreate: { input: 300, output: 100 },
  default: { input: 500, output: 500 },
};

// Model cost per 1M tokens (approximate)
const MODEL_COSTS = {
  haiku: { input: 0.25, output: 1.25 },
  sonnet: { input: 3.0, output: 15.0 },
  opus: { input: 15.0, output: 75.0 },
  default: { input: 3.0, output: 15.0 }, // assume sonnet
};

// Watch events file
let lastSize = fs.statSync(EVENTS_FILE).size;
setInterval(() => {
  try {
    const stat = fs.statSync(EVENTS_FILE);
    // Rotate if too large
    if (stat.size > MAX_EVENTS_BYTES) {
      const rotated = EVENTS_FILE + '.' + Date.now() + '.bak';
      fs.renameSync(EVENTS_FILE, rotated);
      fs.writeFileSync(EVENTS_FILE, '');
      lastSize = 0;
      return;
    }
    if (stat.size > lastSize) {
      const stream = fs.createReadStream(EVENTS_FILE, { start: lastSize, encoding: 'utf8' });
      let buf = '';
      stream.on('data', chunk => buf += chunk);
      stream.on('end', () => {
        lastSize = stat.size;
        for (const line of buf.split('\n').filter(Boolean)) {
          // Update session registry
          try {
            const ev = JSON.parse(line);
            updateSessionRegistry(ev);
          } catch {}
          for (const client of clients) client.write(`data: ${line}\n\n`);
        }
      });
    } else if (stat.size < lastSize) {
      lastSize = 0;
    }
  } catch {}
}, 250);

// Session registry — persistent, enriched
function updateSessionRegistry(ev) {
  try {
    const reg = JSON.parse(fs.readFileSync(SESSIONS_FILE, 'utf8'));
    const sid = ev.sid || 'unknown';
    if (!reg[sid]) {
      reg[sid] = {
        sid,
        cwd: ev.cwd || 'unknown',
        project: ev.project || basename(ev.cwd || ''),
        label: null, // user can set a custom label
        first_seen: ev.ts,
        last_seen: ev.ts,
        event_count: 0,
        tool_counts: {},
        est_tokens: { input: 0, output: 0 },
        est_cost_usd: 0,
        errors: 0,
      };
    }
    const s = reg[sid];
    s.last_seen = ev.ts;
    s.event_count++;
    if (ev.cwd && ev.cwd !== 'unknown') {
      s.cwd = ev.cwd;
      s.project = ev.project || basename(ev.cwd);
    }
    // Track tool usage
    const tool = ev.tool || ev.event?.tool_name || 'unknown';
    s.tool_counts[tool] = (s.tool_counts[tool] || 0) + 1;
    // Estimate tokens/cost on post events
    if (ev.phase === 'post') {
      const est = TOKEN_ESTIMATES[tool] || TOKEN_ESTIMATES.default;
      s.est_tokens.input += est.input;
      s.est_tokens.output += est.output;
      const cost = MODEL_COSTS.default;
      s.est_cost_usd += (est.input * cost.input + est.output * cost.output) / 1_000_000;
      s.est_cost_usd = Math.round(s.est_cost_usd * 10000) / 10000;
    }
    if (ev.has_error) s.errors++;
    fs.writeFileSync(SESSIONS_FILE, JSON.stringify(reg, null, 2));
  } catch {}
}

function getAllEvents() {
  try {
    return fs.readFileSync(EVENTS_FILE, 'utf8')
      .split('\n').filter(Boolean)
      .map(l => { try { return JSON.parse(l); } catch { return null; } })
      .filter(Boolean);
  } catch { return []; }
}

function getSessions() {
  try {
    const reg = JSON.parse(fs.readFileSync(SESSIONS_FILE, 'utf8'));
    const sessions = Object.values(reg);
    const now = Date.now();
    for (const s of sessions) {
      s.active = (now - new Date(s.last_seen).getTime()) < 60000;
    }
    // Also detect running claude processes
    try {
      for (const proc of detectClaudeProcesses()) {
        if (!reg[proc.pid]) {
          sessions.push({
            sid: proc.pid, cwd: proc.cwd || '', project: 'Claude (no events yet)',
            label: null, first_seen: new Date().toISOString(),
            last_seen: new Date().toISOString(), event_count: 0,
            tool_counts: {}, est_tokens: { input: 0, output: 0 },
            est_cost_usd: 0, errors: 0, active: true,
          });
        }
      }
    } catch {}
    return sessions.sort((a, b) => new Date(b.last_seen) - new Date(a.last_seen));
  } catch { return []; }
}

function detectClaudeProcesses() {
  // Only show sessions we've seen actual events from — no process guessing
  return [];
}

function buildTree(events) {
  const spans = [], stacks = {};
  for (const ev of events) {
    const sid = ev.sid || 'unknown';
    if (!stacks[sid]) stacks[sid] = [];
    const stack = stacks[sid];
    const toolName = ev.tool || ev.event?.tool_name || 'unknown';
    const toolInput = ev.event?.tool_input || ev.event?.input || {};

    if (ev.phase === 'pre') {
      const span = {
        id: ev.ts + '-' + toolName + '-' + Math.random().toString(36).slice(2, 6),
        sid, tool: toolName, label: getLabel(toolName, toolInput),
        start: ev.ts, end: null,
        parent: stack.length > 0 ? stack[stack.length - 1].id : null,
        children: [], status: 'active', depth: stack.length,
        input_summary: summarize(toolInput),
        output_summary: null,
        project: ev.project || '',
      };
      if (stack.length > 0) stack[stack.length - 1].children.push(span.id);
      spans.push(span);
      if (toolName === 'Agent' || toolName === 'Skill') stack.push(span);
    } else if (ev.phase === 'post') {
      for (let i = spans.length - 1; i >= 0; i--) {
        if (spans[i].tool === toolName && spans[i].status === 'active' && spans[i].sid === sid) {
          spans[i].end = ev.ts;
          spans[i].status = ev.has_error ? 'error' : 'complete';
          spans[i].output_summary = summarize(ev.event?.tool_output || ev.event?.output || '');
          spans[i].duration_ms = new Date(ev.ts) - new Date(spans[i].start);
          if ((toolName === 'Agent' || toolName === 'Skill') && stack.length) stack.pop();
          break;
        }
      }
    }
  }
  return spans;
}

function getLabel(tool, input) {
  if (tool === 'Agent') return input?.description?.slice(0, 80) || input?.prompt?.slice(0, 80) || 'Agent';
  if (tool === 'Skill') return '/' + (input?.skill || 'skill');
  if (tool === 'Bash') return '$ ' + (input?.command || '').slice(0, 60);
  if (tool === 'Read') return 'Read: ' + basename(input?.file_path || '');
  if (tool === 'Write') return 'Write: ' + basename(input?.file_path || '');
  if (tool === 'Edit') return 'Edit: ' + basename(input?.file_path || '');
  if (tool === 'Glob') return 'Glob: ' + (input?.pattern || '').slice(0, 40);
  if (tool === 'Grep') return 'Grep: ' + (input?.pattern || '').slice(0, 40);
  if (tool === 'WebFetch') return 'Fetch: ' + (input?.url || '').slice(0, 50);
  if (tool === 'WebSearch') return 'Search: ' + (input?.query || '').slice(0, 40);
  if (tool === 'CronCreate') return 'Cron: ' + (input?.cron || '');
  if (tool === 'TaskCreate') return 'Task: ' + (input?.description || '').slice(0, 40);
  if (tool === 'ToolSearch') return 'ToolSearch: ' + (input?.query || '').slice(0, 40);
  return tool;
}

function basename(p) { return p ? path.basename(String(p).replace(/\\/g, '/')) : ''; }
function summarize(obj) {
  if (!obj) return '';
  if (typeof obj === 'string') return obj.slice(0, 400);
  try { return JSON.stringify(obj).slice(0, 400); } catch { return ''; }
}

// Build agent-centric view: agents with their tool calls
function buildAgentView(events) {
  const agents = [];
  const agentStack = [];
  let agentIdCounter = 0;

  for (const ev of events) {
    const toolName = ev.tool || ev.event?.tool_name || 'unknown';
    const toolInput = ev.event?.tool_input || ev.event?.input || {};

    if (ev.phase === 'pre') {
      if (toolName === 'Agent' || toolName === 'Skill') {
        const agentId = 'agent-' + (agentIdCounter++);
        const agent = {
          id: agentId,
          name: extractAgentName(toolInput),
          description: (toolInput.description || toolInput.prompt || '').slice(0, 300),
          status: 'running',
          start: ev.ts,
          end: null,
          duration_ms: null,
          tool_calls: [],
          sid: ev.sid || 'unknown',
          parent_id: agentStack.length > 0 ? agentStack[agentStack.length - 1].id : null,
        };
        agents.push(agent);
        agentStack.push(agent);
      } else {
        // Tool call — attach to current agent or top-level
        const currentAgent = agentStack.length > 0 ? agentStack[agentStack.length - 1] : null;
        const tc = {
          tool: toolName,
          input_summary: getToolInputSummary(toolName, toolInput),
          output_summary: null,
          status: 'running',
          ts: ev.ts,
          end_ts: null,
          duration_ms: null,
          has_error: false,
        };
        if (currentAgent) {
          currentAgent.tool_calls.push(tc);
        }
      }
    } else if (ev.phase === 'post') {
      if (toolName === 'Agent' || toolName === 'Skill') {
        // Close the most recent matching agent
        for (let i = agentStack.length - 1; i >= 0; i--) {
          const agent = agentStack[i];
          if (agent.status === 'running') {
            agent.end = ev.ts;
            agent.status = ev.has_error ? 'error' : 'completed';
            agent.duration_ms = new Date(ev.ts) - new Date(agent.start);
            agentStack.splice(i, 1);
            break;
          }
        }
      } else {
        // Close the most recent matching tool call in the current agent
        const currentAgent = agentStack.length > 0 ? agentStack[agentStack.length - 1] : null;
        if (currentAgent) {
          for (let i = currentAgent.tool_calls.length - 1; i >= 0; i--) {
            const tc = currentAgent.tool_calls[i];
            if (tc.tool === toolName && tc.status === 'running') {
              tc.end_ts = ev.ts;
              tc.status = ev.has_error ? 'error' : 'complete';
              tc.has_error = !!ev.has_error;
              tc.duration_ms = new Date(ev.ts) - new Date(tc.ts);
              const output = ev.event?.tool_output || ev.event?.output || '';
              tc.output_summary = typeof output === 'string' ? output.slice(0, 300) : JSON.stringify(output).slice(0, 300);
              break;
            }
          }
        }
      }
    }
  }

  return agents;
}

function extractAgentName(input) {
  const desc = (input.description || input.prompt || '').toLowerCase();
  // Try to extract agent role names from description
  const rolePatterns = [
    'wheel-scout', 'wheel scout', 'implementer', 'researcher', 'context-hydrator',
    'context hydrator', 'skill-router', 'skill router', 'tool-broker', 'tool broker',
    'memory-scribe', 'memory scribe', 'forger', 'browser', 'vet-scanner', 'vet scanner',
    'test-writer', 'test writer', 'log-monitor', 'log monitor', 'supervisor',
  ];
  for (const role of rolePatterns) {
    if (desc.includes(role)) return role.replace(/ /g, '-');
  }
  return (input.description || input.prompt || 'Agent').slice(0, 50);
}

function getToolInputSummary(tool, input) {
  if (tool === 'Read') return input.file_path || '';
  if (tool === 'Write') return input.file_path || '';
  if (tool === 'Edit') return (input.file_path || '') + (input.old_string ? ' (edit)' : '');
  if (tool === 'Bash') return '$ ' + (input.command || '').slice(0, 120);
  if (tool === 'Glob') return 'pattern: ' + (input.pattern || '');
  if (tool === 'Grep') return 'pattern: ' + (input.pattern || '').slice(0, 80);
  if (tool === 'WebFetch') return input.url || '';
  if (tool === 'WebSearch') return 'query: ' + (input.query || '').slice(0, 80);
  if (tool === 'Agent') return (input.description || input.prompt || '').slice(0, 80);
  if (tool === 'Skill') return '/' + (input.skill || 'skill');
  return JSON.stringify(input).slice(0, 120);
}

// HTTP Server
const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT');

  // SSE
  if (url.pathname === '/events') {
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive' });
    clients.add(res);
    req.on('close', () => clients.delete(res));
    return;
  }

  // REST endpoints
  if (url.pathname === '/api/events') {
    const events = getAllEvents();
    const sid = url.searchParams.get('sid');
    const limit = parseInt(url.searchParams.get('limit') || '5000');
    let filtered = sid ? events.filter(e => e.sid === sid) : events;
    filtered = filtered.slice(-limit);
    json(res, filtered);
    return;
  }

  if (url.pathname === '/api/sessions') {
    json(res, getSessions());
    return;
  }

  // Label a session
  if (url.pathname === '/api/sessions/label' && req.method === 'PUT') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { sid, label } = JSON.parse(body);
        const reg = JSON.parse(fs.readFileSync(SESSIONS_FILE, 'utf8'));
        if (reg[sid]) { reg[sid].label = label; fs.writeFileSync(SESSIONS_FILE, JSON.stringify(reg, null, 2)); }
        json(res, { ok: true });
      } catch (e) { json(res, { error: e.message }, 400); }
    });
    return;
  }

  if (url.pathname === '/api/tree') {
    const events = getAllEvents();
    const sid = url.searchParams.get('sid');
    const filtered = sid ? events.filter(e => e.sid === sid) : events;
    json(res, buildTree(filtered));
    return;
  }

  if (url.pathname === '/api/stats') {
    const events = getAllEvents();
    const sid = url.searchParams.get('sid');
    const filtered = sid ? events.filter(e => e.sid === sid) : events;
    const tree = buildTree(filtered);
    const sessions = getSessions();
    const activeSessions = sessions.filter(s => s.active).length;
    const totalCost = sessions.reduce((sum, s) => sum + (s.est_cost_usd || 0), 0);
    const totalTokens = sessions.reduce((sum, s) => sum + (s.est_tokens?.input || 0) + (s.est_tokens?.output || 0), 0);
    const tools = {};
    for (const s of tree) tools[s.tool] = (tools[s.tool] || 0) + 1;
    json(res, {
      spans: tree.length,
      active_spans: tree.filter(s => s.status === 'active').length,
      complete: tree.filter(s => s.status === 'complete').length,
      errors: tree.filter(s => s.status === 'error').length,
      tools,
      event_count: filtered.length,
      sessions: sessions.length,
      active_sessions: activeSessions,
      est_cost_usd: Math.round(totalCost * 10000) / 10000,
      est_tokens: totalTokens,
      events_file_mb: Math.round(fs.statSync(EVENTS_FILE).size / 1024 / 1024 * 100) / 100,
    });
    return;
  }

  // Agents endpoint — events grouped by agent for a session
  if (url.pathname === '/api/agents') {
    const events = getAllEvents();
    const sid = url.searchParams.get('sid');
    const filtered = sid ? events.filter(e => e.sid === sid) : events;
    const agents = buildAgentView(filtered);
    json(res, agents);
    return;
  }

  if (url.pathname === '/api/clear' && req.method === 'POST') {
    fs.writeFileSync(EVENTS_FILE, '');
    fs.writeFileSync(SESSIONS_FILE, '{}');
    lastSize = 0;
    json(res, { ok: true });
    return;
  }

  // Dashboard
  if (url.pathname === '/' || url.pathname === '/dashboard') {
    try {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(fs.readFileSync(DASHBOARD_FILE, 'utf8'));
    } catch (e) {
      res.writeHead(500);
      res.end('Dashboard not found: ' + e.message);
    }
    return;
  }

  // Pipeline visualization
  if (url.pathname === '/pipeline') {
    try {
      const pipelineFile = path.join(TRACE_DIR, 'pipeline.html');
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(fs.readFileSync(pipelineFile, 'utf8'));
    } catch (e) {
      res.writeHead(500);
      res.end('Pipeline not found: ' + e.message);
    }
    return;
  }

  // Pipeline v2 - inline agent activity
  if (url.pathname === "/pipeline-v2") {
    try {
      const pipelineV2File = path.join(TRACE_DIR, "pipeline-v2.html");
      res.writeHead(200, { "Content-Type": "text/html" });
      res.end(fs.readFileSync(pipelineV2File, "utf8"));
    } catch (e) {
      res.writeHead(500);
      res.end("Pipeline v2 not found: " + e.message);
    }
    return;
  }

  res.writeHead(404);
  res.end('Not found');
});

function json(res, data, status = 200) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(data));
}

server.listen(PORT, () => {
  console.log(`\n  ◇ Claude Trace Dashboard: http://localhost:${PORT}\n`);
  console.log(`  Watching: ${EVENTS_FILE}`);
  console.log(`  Sessions: ${SESSIONS_FILE}\n`);
});

process.on('SIGINT', () => process.exit());
