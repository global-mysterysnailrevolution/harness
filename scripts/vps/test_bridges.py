#!/usr/bin/env python3
"""Test MCP bridges. Run on VPS."""
import urllib.request, ssl, json, sys

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

init_body = json.dumps({
    "jsonrpc": "2.0",
    "method": "initialize",
    "id": 1,
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"}
    }
}).encode()

tools_body = json.dumps({
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 2,
}).encode()

bridges = {
    "filesystem": 8101,
    "everything": 8102,
    "memory": 8104,
}

results = {}
for name, port in bridges.items():
    print(f"\n=== {name} (port {port}) ===")
    for host in ["127.0.0.1", "172.18.0.1"]:
        url = f"https://{host}:{port}/mcp"
        try:
            req = urllib.request.Request(url, data=init_body,
                headers={"Content-Type": "application/json"}, method="POST")
            r = urllib.request.urlopen(req, timeout=10, context=ctx)
            resp = json.loads(r.read().decode())
            server_name = resp.get("result", {}).get("serverInfo", {}).get("name", "?")
            print(f"  {host}: OK - server={server_name}")
            results[f"{name}@{host}"] = True
        except Exception as e:
            print(f"  {host}: FAIL - {e}")
            results[f"{name}@{host}"] = False

    # Also list tools
    url = f"https://127.0.0.1:{port}/mcp"
    try:
        req = urllib.request.Request(url, data=tools_body,
            headers={"Content-Type": "application/json"}, method="POST")
        r = urllib.request.urlopen(req, timeout=10, context=ctx)
        resp = json.loads(r.read().decode())
        tools = resp.get("result", {}).get("tools", [])
        print(f"  Tools ({len(tools)}): {', '.join(t.get('name','?') for t in tools[:5])}")
    except Exception as e:
        print(f"  Tools: FAIL - {e}")

# Test from container
print("\n=== Container test ===")
import subprocess
try:
    r = subprocess.run(
        ["docker", "exec", "openclaw-kx9d-openclaw-1",
         "python3", "-c",
         "import urllib.request,ssl,json;ctx=ssl.create_default_context();ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE;r=urllib.request.urlopen(urllib.request.Request('https://172.18.0.1:8101/mcp',data=json.dumps({'jsonrpc':'2.0','method':'initialize','id':1,'params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'t','version':'1'}}}).encode(),headers={'Content-Type':'application/json'},method='POST'),timeout=10,context=ctx);print('Container->8101: OK',r.read().decode()[:100])"],
        capture_output=True, text=True, timeout=30)
    print(f"  {r.stdout.strip()}")
    if r.stderr.strip():
        print(f"  stderr: {r.stderr.strip()[:200]}")
except Exception as e:
    print(f"  Container test failed: {e}")

ok = sum(1 for v in results.values() if v)
total = len(results)
print(f"\n=== Summary: {ok}/{total} passed ===")
sys.exit(0 if ok == total else 1)
