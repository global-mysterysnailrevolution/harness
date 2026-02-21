# Weave Tracing - Fixed

## Issue Found

Weave was getting: " Personal entities are disabled please log to a different team\

## Solution

Changed project name from globalmysterysnailrevolution/tool-broker to ool-broker (simple project name, not team/project format)

## Current Configuration

- **WANDB_API_KEY**: Set in /opt/harness/.env
- **WEAVE_PROJECT**: ool-broker (simple name)
- **Broker Service**: Restarted and loading env vars

## View Traces

Dashboard: https://wandb.ai/tool-broker

Or check your default Weave dashboard.

## Test

`ash
ssh root@100.124.123.68
cd /opt/harness
source venv/bin/activate
export WANDB_API_KEY=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
python3 scripts/broker/tool_broker.py search --query test
`

Traces should now appear in Weave!
