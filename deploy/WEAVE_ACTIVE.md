# âœ… Weave Tracing Active

## Status

Weave tracing is now **ACTIVE** and working!

## Configuration

- **WANDB_API_KEY**: Set in /opt/harness/.env
- **WEAVE_PROJECT**: globalmysterysnailrevolution/tool-broker
- **Broker Service**: Automatically loads env vars and initializes Weave

## View Traces

Dashboard: https://wandb.ai/globalmysterysnailrevolution/tool-broker

All broker operations are automatically traced:
- search_tools
- describe_tool
- call_tool
- load_tools

## Test It

`ash
# SSH into VPS
ssh root@100.124.123.68

# Run broker operations (automatically traced)
cd /opt/harness
python3 scripts/broker/tool_broker.py search --query  browser
python3 scripts/broker/tool_broker.py describe --tool-id test:tool
`

Traces will appear in Weave dashboard automatically.

## Security

- Secrets are automatically redacted from traces
- API keys never logged
- Only operation metadata and results (redacted) are traced
