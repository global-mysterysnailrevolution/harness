#!/usr/bin/env python3
"""Test the Codex MCP bridge."""
import urllib.request
import ssl
import json

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Test initialize
print("=== Initialize ===")
body = json.dumps({
    "jsonrpc": "2.0",
    "method": "initialize",
    "id": 1,
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"}
    }
}).encode()

try:
    req = urllib.request.Request(
        "https://127.0.0.1:8105/mcp",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    r = urllib.request.urlopen(req, timeout=30, context=ctx)
    resp = json.loads(r.read().decode())
    server_info = resp.get("result", {}).get("serverInfo", {})
    print(f"  Server: {server_info.get('name', '?')} v{server_info.get('version', '?')}")
    print(f"  Capabilities: {list(resp.get('result', {}).get('capabilities', {}).keys())}")
except Exception as e:
    print(f"  FAIL: {e}")

# Test tools/list
print("\n=== Tools ===")
body = json.dumps({
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 2,
}).encode()

try:
    req = urllib.request.Request(
        "https://127.0.0.1:8105/mcp",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    r = urllib.request.urlopen(req, timeout=30, context=ctx)
    resp = json.loads(r.read().decode())
    tools = resp.get("result", {}).get("tools", [])
    print(f"  {len(tools)} tools available:")
    for t in tools:
        print(f"    - {t.get('name', '?')}: {t.get('description', '?')[:80]}")
except Exception as e:
    print(f"  FAIL: {e}")

# Test from container
print("\n=== Container Access ===")
import subprocess
try:
    r = subprocess.run(
        ["docker", "exec", "openclaw-kx9d-openclaw-1",
         "python3", "-c",
         "import urllib.request,ssl,json;"
         "ctx=ssl.create_default_context();"
         "ctx.check_hostname=False;"
         "ctx.verify_mode=ssl.CERT_NONE;"
         "r=urllib.request.urlopen(urllib.request.Request("
         "'https://172.18.0.1:8105/mcp',"
         "data=json.dumps({'jsonrpc':'2.0','method':'tools/list','id':1}).encode(),"
         "headers={'Content-Type':'application/json'},method='POST'),"
         "timeout=30,context=ctx);"
         "d=json.loads(r.read());"
         "tools=d.get('result',{}).get('tools',[]);"
         "print(f'{len(tools)} tools from container')"],
        capture_output=True, text=True, timeout=45)
    print(f"  {r.stdout.strip()}")
    if r.stderr.strip():
        print(f"  stderr: {r.stderr.strip()[:200]}")
except Exception as e:
    print(f"  FAIL: {e}")
