#!/usr/bin/env python3
"""Test Codex bridge from container."""
import subprocess, json

r = subprocess.run(
    ["docker", "exec", "openclaw-kx9d-openclaw-1",
     "python3", "-c",
     "import urllib.request,ssl,json;"
     "ctx=ssl.create_default_context();"
     "ctx.check_hostname=False;"
     "ctx.verify_mode=ssl.CERT_NONE;"
     "body=json.dumps({'jsonrpc':'2.0','method':'tools/list','id':1}).encode();"
     "req=urllib.request.Request('https://172.18.0.1:8105/mcp',data=body,"
     "headers={'Content-Type':'application/json'},method='POST');"
     "r=urllib.request.urlopen(req,timeout=30,context=ctx);"
     "d=json.loads(r.read());"
     "tools=d.get('result',{}).get('tools',[]);"
     "print(f'{len(tools)} Codex tools available');"
     "[print(f'  - {t[\"name\"]}: {t[\"description\"][:70]}') for t in tools]"],
    capture_output=True, text=True, timeout=60)

print(r.stdout.strip() if r.stdout else "no stdout")
if r.stderr.strip():
    print(f"stderr: {r.stderr.strip()[:200]}")
print(f"exit: {r.returncode}")
