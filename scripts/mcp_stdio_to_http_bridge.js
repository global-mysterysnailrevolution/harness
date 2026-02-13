#!/usr/bin/env node
/**
 * MCP Stdio-to-HTTP Bridge (HTTPS + Bearer auth)
 *
 * Spawns a stdio MCP server and exposes it via HTTP/HTTPS at /mcp.
 * Supports: HTTPS (via certs), Bearer token auth, IP allowlisting.
 *
 * Env:
 *   MCP_PORT          - Port (default 8101)
 *   MCP_HTTPS_KEY     - Path to TLS key (enables HTTPS)
 *   MCP_HTTPS_CERT    - Path to TLS cert
 *   MCP_BEARER_TOKEN  - If set, require Bearer in Authorization header
 *   MCP_ALLOW_LOCAL   - If 1, allow 127.0.0.1 and 172.17.x without Bearer (default 1)
 *   MCP_BIND          - Bind address (default 127.0.0.1 for localhost; use 0.0.0.0 for Docker)
 *
 * Usage:
 *   node mcp_stdio_to_http_bridge.js --port 8101 -- npx -y @modelcontextprotocol/server-filesystem /path
 */

const { spawn } = require('child_process');
const http = require('http');
const https = require('https');
const fs = require('fs');

let PORT = parseInt(process.env.MCP_PORT || '8101', 10);
const SPLIT = process.argv.indexOf('--');
const ARGS = SPLIT >= 0 ? process.argv.slice(SPLIT + 1) : [];
const BEARER_TOKEN = process.env.MCP_BEARER_TOKEN || '';
const ALLOW_LOCAL_NO_AUTH = process.env.MCP_ALLOW_LOCAL !== '0';
const BIND = process.env.MCP_BIND || '127.0.0.1';
const HTTPS_KEY = process.env.MCP_HTTPS_KEY || '';
const HTTPS_CERT = process.env.MCP_HTTPS_CERT || '';

for (let i = 0; i < process.argv.length; i++) {
  if (process.argv[i] === '--port' && process.argv[i + 1]) {
    PORT = parseInt(process.argv[i + 1], 10);
    break;
  }
}

if (ARGS.length === 0) {
  console.error('Usage: node mcp_stdio_to_http_bridge.js [--port 8101] -- <cmd> [args...]');
  process.exit(1);
}

const execCmd = ARGS[0];
const execArgs = ARGS.slice(1);

function isAllowedWithoutAuth(remote) {
  if (!ALLOW_LOCAL_NO_AUTH || !BEARER_TOKEN) return false;
  return remote === '127.0.0.1' || remote === '::1' || remote === '::ffff:127.0.0.1' ||
    remote.startsWith('172.17.') || remote.startsWith('172.18.') || remote.startsWith('192.168.');
}

function checkAuth(req) {
  if (!BEARER_TOKEN) return true;
  const remote = req.socket.remoteAddress || '';
  if (isAllowedWithoutAuth(remote)) return true;
  const auth = req.headers.authorization || '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
  return token === BEARER_TOKEN && token.length > 0;
}

let proc = null;
let sessionId = null;

function spawnProcess() {
  if (proc) proc.kill();
  proc = spawn(execCmd, execArgs, {
    stdio: ['pipe', 'pipe', 'inherit'],
    env: { ...process.env },
  });

  let buffer = '';
  proc.stdout.on('data', (chunk) => {
    buffer += chunk.toString();
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (line.trim()) {
        try {
          const msg = JSON.parse(line);
          if (msg.id !== undefined && pending.has(msg.id)) {
            pending.get(msg.id)(msg);
            pending.delete(msg.id);
          }
        } catch (_) {}
      }
    }
  });

  proc.on('exit', (code) => {
    if (code !== 0 && code !== null) console.error(`[MCP] Process exited with code ${code}`);
    proc = null;
  });

  return proc;
}

const pending = new Map();
let nextId = 0;

function sendToStdio(msg) {
  return new Promise((resolve, reject) => {
    if (!proc || !proc.stdin.writable) spawnProcess();
    const id = msg.id ?? ++nextId;
    msg.id = id;
    pending.set(id, (res) => {
      if (res.error) reject(new Error(res.error.message || 'MCP error'));
      else resolve(res);
    });
    proc.stdin.write(JSON.stringify(msg) + '\n', (err) => {
      if (err) { pending.delete(id); reject(err); }
    });
    setTimeout(() => {
      if (pending.has(id)) {
        pending.delete(id);
        reject(new Error('MCP timeout'));
      }
    }, 60000);
  });
}

const protocol = (HTTPS_KEY && HTTPS_CERT) ? 'https' : 'http';

const handler = async (req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, mcp-session-id, Authorization',
    });
    res.end();
    return;
  }

  if (req.url !== '/mcp' && req.url !== '/mcp/') {
    res.writeHead(404);
    res.end('Not found');
    return;
  }

  if (!checkAuth(req)) {
    res.writeHead(401, { 'Content-Type': 'application/json', 'WWW-Authenticate': 'Bearer' });
    res.end(JSON.stringify({ error: 'Unauthorized', message: 'Missing or invalid Bearer token' }));
    return;
  }

  const sid = req.headers['mcp-session-id'] || sessionId;
  if (sid) sessionId = sid;

  if (req.method === 'GET' && req.headers.accept?.includes('text/event-stream')) {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    });
    res.write(`event: endpoint\ndata: {"url":"${protocol}://${req.headers.host || 'localhost'}/mcp"}\n\n`);
    res.end();
    return;
  }

  if (req.method !== 'POST') {
    res.writeHead(405);
    res.end('Method not allowed');
    return;
  }

  let body = '';
  for await (const chunk of req) body += chunk;
  let msg;
  try {
    msg = JSON.parse(body);
  } catch {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Invalid JSON' }));
    return;
  }

  try {
    if (!proc || !proc.stdin.writable) spawnProcess();
    const result = await sendToStdio(msg);
    res.writeHead(200, {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      ...(sessionId && { 'mcp-session-id': sessionId }),
    });
    res.end(JSON.stringify(result));
  } catch (err) {
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: err.message || 'Internal error' }));
  }
};

let server;
if (HTTPS_KEY && HTTPS_CERT) {
  try {
    const key = fs.readFileSync(HTTPS_KEY);
    const cert = fs.readFileSync(HTTPS_CERT);
    server = https.createServer({ key, cert }, handler);
  } catch (e) {
    console.error(`[MCP] Failed to load TLS certs: ${e.message}`);
    process.exit(1);
  }
} else {
  server = http.createServer(handler);
}

spawnProcess();
server.listen(PORT, BIND, () => {
  console.log(`[MCP] Bridge listening on ${protocol}://${BIND}:${PORT}/mcp`);
  console.log(`[MCP] Spawned: ${execCmd} ${execArgs.join(' ')}`);
  if (BEARER_TOKEN) console.log(`[MCP] Bearer auth enabled (local IPs exempt: ${ALLOW_LOCAL_NO_AUTH})`);
  if (protocol === 'https') console.log(`[MCP] HTTPS enabled`);
});
