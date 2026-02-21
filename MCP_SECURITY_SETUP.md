# MCP Security Lockdown (HTTPS + Auth + Firewall)

One-time setup to secure your MCP bridges with HTTPS, Bearer auth, and firewall rules.

## What You Need From Me

| Item | Required? | Notes |
|------|-----------|-------|
| **Domain for Let's Encrypt** | Optional | If you have a domain pointing to the VPS, we can use real certs. Otherwise we use self-signed. |
| **SSH access** | Yes | To run scripts on the VPS |
| **Root/sudo** | Yes | For firewall (ufw) |

**Self-signed certs** work out of the box. Node/OpenClaw may reject them by default (see "Self-signed certs" below).

---

## Step 1: Generate Certs and Token

```bash
ssh root@100.124.123.68
cd /opt/harness/scripts
chmod +x generate_mcp_certs.sh
./generate_mcp_certs.sh
```

This creates:
- `/opt/harness/.mcp/certs/key.pem` and `cert.pem`
- Adds `MCP_BEARER_TOKEN`, `MCP_HTTPS_KEY`, `MCP_HTTPS_CERT`, `MCP_BIND` to `/opt/harness/.env`

**Save the Bearer token** printed at the end — you may need it for manual config.

---

## Step 2: Add to .gitignore

Ensure secrets are not committed:

```bash
echo ".mcp/" >> /opt/harness/.gitignore
echo ".env" >> /opt/harness/.gitignore
```

---

## Step 3: Apply Firewall Rules

```bash
chmod +x setup_mcp_firewall.sh
sudo ./setup_mcp_firewall.sh
```

This restricts MCP ports 8101–8104 to:
- Docker bridge (172.17.0.0/16)
- Localhost (127.0.0.1)

---

## Step 4: Run MCP Bridges with Security

```bash
# Load .env and start bridges
./run_mcp_servers.sh
```

Bridges will:
- Use HTTPS (from certs in .env)
- Require Bearer token except from localhost/Docker (exempt)
- Bind to 0.0.0.0 so Docker can reach them

---

## Step 5: Patch OpenClaw Config

```bash
python3 /opt/harness/patch_openclaw_mcp_plugin.py /docker/openclaw-kx9d/data/.openclaw/openclaw.json
docker restart openclaw-kx9d-openclaw-1
```

**Self-signed certs:** OpenClaw may reject them. If MCP tools fail:

```bash
# Add to OpenClaw container/env (temporary workaround)
NODE_TLS_REJECT_UNAUTHORIZED=0
```

Or use Let's Encrypt for a trusted cert (see below).

---

## Self-Signed vs Let's Encrypt

| Option | Pros | Cons |
|--------|------|------|
| **Self-signed** | No domain, no setup | Clients may reject; need `NODE_TLS_REJECT_UNAUTHORIZED=0` |
| **Let's Encrypt** | Trusted cert, no warnings | Requires domain pointing to VPS |

**Let's Encrypt:** If you have `mcp.yourdomain.com` → VPS:

```bash
# Install certbot
apt install certbot
certbot certonly --standalone -d mcp.yourdomain.com

# Update .env
MCP_HTTPS_KEY=/etc/letsencrypt/live/mcp.yourdomain.com/privkey.pem
MCP_HTTPS_CERT=/etc/letsencrypt/live/mcp.yourdomain.com/fullchain.pem
```

Then restart the bridges.

---

## Security Summary

| Layer | What |
|-------|------|
| **HTTPS** | TLS encryption for MCP traffic |
| **Bearer auth** | Required for non-localhost; exempt for Docker bridge |
| **Firewall** | Only Docker + localhost can reach ports |
| **Filesystem** | Restricted to `/opt/harness/ai` only |
| **Tokens** | GitHub/other uses least-privilege scopes |

---

## Docker Bridge IP

The default Docker bridge IP is `172.17.0.1`. If your setup differs:

```bash
docker network inspect bridge | grep Gateway
```

Use that IP in the OpenClaw MCP config and patch script.

---

## OpenClaw Container: Trust Self-Signed Cert

If OpenClaw rejects the self-signed cert, add to the container:

**Option A — Trust the cert (recommended):** Copy cert into container and set:
```bash
NODE_EXTRA_CA_CERTS=/path/to/cert.pem
```

**Option B — Disable verification (quick fix):**
```bash
NODE_TLS_REJECT_UNAUTHORIZED=0
```

For Docker, add to your compose/run:
```yaml
environment:
  - NODE_TLS_REJECT_UNAUTHORIZED=0
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `UNABLE_TO_VERIFY_LEAF_SIGNATURE` | Self-signed cert rejected; use options above |
| `401 Unauthorized` | Bearer token missing or wrong; check Docker is using 172.17.x (allowlist) |
| `ECONNREFUSED` | Bridges not running; firewall blocking; or wrong IP (use 172.17.0.1 for Docker) |
| `ai/` not found | Run `mkdir -p /opt/harness/ai` |
