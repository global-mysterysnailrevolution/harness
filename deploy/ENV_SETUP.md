# Environment Variables Setup

## Location: VPS Only

All environment variables should be set **on the VPS**, not on your local PC.

## Current Setup

### 1. .env File (Recommended)

Created at: /opt/harness/.env

`env
TOOLHIVE_GATEWAY_URL=http://127.0.0.1:8080
WEAVE_PROJECT=globalmysterysnailrevolution/tool-broker
# WANDB_API_KEY=your-key-here
`

The broker service is configured to load this file automatically.

### 2. Systemd Services

Both services load environment from:
- /opt/harness/.env (via EnvironmentFile)
- Additional env vars in service file

### 3. Setting WANDB_API_KEY

**Option A: Add to .env file (recommended)**
`ash
ssh root@100.124.123.68
cd /opt/harness
echo 'WANDB_API_KEY=your-actual-key-here' >> .env
systemctl restart harness-broker
`

**Option B: Set in systemd service**
`ash
# Edit service file
nano /etc/systemd/system/harness-broker.service
# Add: Environment=" WANDB_API_KEY=your-key\
systemctl daemon-reload
systemctl restart harness-broker
`

**Option C: Export for testing**
`ash
export WANDB_API_KEY=your-key
python3 scripts/broker/tool_broker.py search --query test
`

## Why VPS Only?

- The broker HTTP service runs on the VPS
- ToolHive runs on the VPS
- Weave traces are generated on the VPS
- Your local PC just connects via SSH/Tailscale

## Testing

`ash
# SSH into VPS
ssh root@100.124.123.68

# Check env vars are loaded
cd /opt/harness
source .env # Loads vars for current session
echo \

# Test broker
python3 scripts/broker/tool_broker.py search --query test
`

## Security Note

Never commit .env file to git. It's already in .gitignore.
