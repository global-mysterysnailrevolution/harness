#!/usr/bin/env python3
"""Verify all components work from inside the OpenClaw container."""
import subprocess
import sys
import json

CONTAINER = "openclaw-kx9d-openclaw-1"

def docker_exec(cmd, timeout=30):
    full_cmd = ["docker", "exec", CONTAINER] + cmd
    try:
        r = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)

checks = []

# 1. Python3 available
rc, out, err = docker_exec(["python3", "--version"])
checks.append(("Python3", rc == 0, out or err))

# 2. MCP Bridge reachable (HTTPS, no cert verification)
rc, out, err = docker_exec([
    "python3", "-c",
    "import urllib.request,ssl,json;"
    "ctx=ssl.create_default_context();"
    "ctx.check_hostname=False;"
    "ctx.verify_mode=ssl.CERT_NONE;"
    "r=urllib.request.urlopen(urllib.request.Request("
    "'https://172.18.0.1:8101/mcp',"
    "data=json.dumps({'jsonrpc':'2.0','method':'tools/list','id':1}).encode(),"
    "headers={'Content-Type':'application/json'},method='POST'),"
    "timeout=10,context=ctx);"
    "d=json.loads(r.read());"
    "tools=d.get('result',{}).get('tools',[]);"
    "print(f'{len(tools)} tools available')"
])
checks.append(("MCP Bridge (filesystem:8101)", rc == 0, out or err))

# 3. Memory knowledge graph bridge
rc, out, err = docker_exec([
    "python3", "-c",
    "import urllib.request,ssl,json;"
    "ctx=ssl.create_default_context();"
    "ctx.check_hostname=False;"
    "ctx.verify_mode=ssl.CERT_NONE;"
    "r=urllib.request.urlopen(urllib.request.Request("
    "'https://172.18.0.1:8104/mcp',"
    "data=json.dumps({'jsonrpc':'2.0','method':'tools/list','id':1}).encode(),"
    "headers={'Content-Type':'application/json'},method='POST'),"
    "timeout=10,context=ctx);"
    "d=json.loads(r.read());"
    "tools=d.get('result',{}).get('tools',[]);"
    "print(f'{len(tools)} tools available')"
])
checks.append(("MCP Bridge (memory:8104)", rc == 0, out or err))

# 4. Tool broker accessible
rc, out, err = docker_exec(["ls", "/data/harness/scripts/broker/tool_broker.py"])
checks.append(("Tool Broker file exists", rc == 0, out or err))

# 5. ContextForge importable
rc, out, err = docker_exec([
    "python3", "-c",
    "import sys; sys.path.insert(0, '/data/harness');"
    "from contextforge.packages.analyzer import RepoAnalyzer;"
    "from contextforge.packages.memory import MemoryManager;"
    "print('All imports OK')"
])
checks.append(("ContextForge imports", rc == 0, out or err))

# 6. ContextForge Analyzer works
rc, out, err = docker_exec([
    "python3", "-c",
    "import sys; sys.path.insert(0, '/data/harness');"
    "from contextforge.packages.analyzer import RepoAnalyzer;"
    "a = RepoAnalyzer('/data/harness');"
    "r = a.analyze();"
    "print(f'{r.structure.total_files} files, {len(r.stack.languages)} langs')"
], timeout=60)
checks.append(("ContextForge Analyzer", rc == 0, out or err))

# 7. Memory manager workspace
rc, out, err = docker_exec(["ls", "/data/.openclaw/memory/pending"])
checks.append(("Memory dirs exist", rc == 0, "dirs present"))

# 8. MEMORY.md
rc, out, err = docker_exec(["head", "-3", "/data/.openclaw/MEMORY.md"])
checks.append(("MEMORY.md", rc == 0, out or err))

# 9. AGENTS.md has new sections
rc, out, err = docker_exec([
    "python3", "-c",
    "content = open('/data/.openclaw/workspace/AGENTS.md').read();"
    "sections = ['MCP Tool Bridges', 'Tool Broker', 'ContextForge Memory', 'ContextForge Analyzer'];"
    "found = [s for s in sections if s in content];"
    "print(f'{len(found)}/{len(sections)} sections found: {found}')"
])
checks.append(("AGENTS.md sections", rc == 0 and "4/4" in out, out or err))

# 10. openclaw.json has mcpServers
rc, out, err = docker_exec([
    "python3", "-c",
    "import json;"
    "c = json.loads(open('/data/.openclaw/openclaw.json').read());"
    "servers = c.get('mcpServers', {});"
    "print(f'{len(servers)} MCP servers configured: {list(servers.keys())}')"
])
checks.append(("openclaw.json mcpServers", rc == 0, out or err))

# Print results
print("=" * 60)
print("Container Wiring Verification")
print("=" * 60)
ok = 0
for name, passed, detail in checks:
    status = "PASS" if passed else "FAIL"
    if passed:
        ok += 1
    print(f"  [{status}] {name}: {detail[:80]}")

print(f"\n  {ok}/{len(checks)} checks passed")
sys.exit(0 if ok == len(checks) else 1)
