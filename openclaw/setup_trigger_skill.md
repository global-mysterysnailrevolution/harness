# Setup Trigger Skill

When the user says "set up", "configure harness", or "setup openclaw" and includes a token, call the setup webhook.

## Trigger phrases
- "Set up everything"
- "Configure harness"
- "Setup OpenClaw"
- "Configure with token: sk-xxx"

## Action
POST to `http://172.18.0.1:8003/trigger` with:
```json
{"message": "<user's full message>"}
```

Or extract token and send:
```json
{"token": "sk-xxx"}
```

## Prerequisites
- Setup trigger server running on VPS: `python3 scripts/vps/setup_trigger_server.py --port 8003`
- Or systemd: `harness-setup-trigger.service`
- OpenClaw container must be able to reach host (172.18.0.1)

## Skill implementation
The agent should use its fetch/HTTP tool to POST when it detects a setup request with token.
If no fetch tool, the agent can instruct the user to use the portal or run: 
`curl -X POST http://YOUR_VPS:8003/trigger -H "Content-Type: application/json" -d '{"token":"sk-xxx"}'`
