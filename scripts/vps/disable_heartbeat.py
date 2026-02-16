#!/usr/bin/env python3
"""Disable heartbeat in OpenClaw config. Run on VPS."""
import json
p = "/docker/openclaw-kx9d/data/.openclaw/openclaw.json"
with open(p) as f:
    c = json.load(f)
a = c.get("agents", {})
d = a.get("defaults", {})
# OpenClaw expects object, not boolean. Use 1-year interval to effectively disable.
d["heartbeat"] = {"every": "576h"}  # 24 days — effectively off, under Node setTimeout max
a["defaults"] = d
c["agents"] = a
with open(p, "w") as f:
    json.dump(c, f, indent=2)
print("Heartbeat disabled")
