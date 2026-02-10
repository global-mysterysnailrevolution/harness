# Hostinger VPS Hardening Guide

## Pre-Deployment Security Checklist

Before deploying the harness on Hostinger VPS, complete these hardening steps.

## 1. Hostinger Firewall Configuration

### Default-Deny Inbound

Configure Hostinger firewall to default-deny inbound, allowing only what's needed:

**Required ports:**
- `80/443` - Web traffic (if exposing OpenClaw UI publicly)
- `22` - SSH (if needed)

**Block everything else by default.**

### Control UI Access

Keep OpenClaw Control UI private:
- **Option A**: localhost-only (recommended)
- **Option B**: Behind reverse proxy with authentication
- **Option C**: VPN/tunnel access only

**Never expose Control UI publicly without authentication.**

## 2. File Permissions Hardening

### OpenClaw Config Files

Set restrictive permissions on OpenClaw configuration and credential files:

```bash
# OpenClaw config directory
chmod 700 ~/.openclaw
chmod 600 ~/.openclaw/*.json
chmod 600 ~/.openclaw/*.yaml

# Credential files
chmod 600 ~/.openclaw/credentials/*
chmod 600 ~/.openclaw/secrets/*
```

### Harness Files

```bash
# Supervisor configs (may contain secrets)
chmod 600 ai/supervisor/allowlists.json
chmod 600 ai/supervisor/security_policy.json
chmod 600 ai/supervisor/mcp.servers.json

# State files (sensitive data)
chmod 600 ai/supervisor/state.json
chmod 600 ai/supervisor/task_queue.json
```

## 3. Disable Insecure Auth

### OpenClaw Gateway Configuration

Edit OpenClaw gateway config to disable insecure authentication:

```yaml
gateway:
  controlUi:
    allowInsecureAuth: false  # Require secure auth
    bindAddress: "127.0.0.1"  # localhost only
    port: 8080
```

Or via environment variable:
```bash
export OPENCLAW_GATEWAY_CONTROL_UI_ALLOW_INSECURE_AUTH=false
export OPENCLAW_GATEWAY_CONTROL_UI_BIND_ADDRESS=127.0.0.1
```

## 4. ToolHive Localhost Binding

### Docker Compose

ToolHive should bind to localhost only (already configured in `docker-compose.yml`):

```yaml
ports:
  - "127.0.0.1:8080:8080"  # localhost only
```

### Verify Binding

```bash
# Check ToolHive is only listening on localhost
netstat -tlnp | grep 8080
# Should show: 127.0.0.1:8080, not 0.0.0.0:8080
```

## 5. Network Isolation

### Docker Network

Use private Docker network for harness services:

```yaml
networks:
  harness-network:
    driver: bridge
    internal: false  # Set to true for complete isolation (no internet)
```

### Firewall Rules (iptables/ufw)

```bash
# Allow only localhost connections to ToolHive
sudo ufw allow from 127.0.0.1 to any port 8080
sudo ufw deny 8080

# Allow only localhost connections to broker (if HTTP service)
sudo ufw allow from 127.0.0.1 to any port 8000
sudo ufw deny 8000
```

## 6. Secrets Management

### Environment Variables

Store secrets in environment variables, not files:

```bash
# Use Hostinger's environment variable system
# Or create .env file with restricted permissions
chmod 600 .env
```

### Secret Injection

Broker injects secrets at call time only:
- Never written to `ai/` directory
- Never logged (redacted)
- Scoped per tool/container

## 7. Process Isolation

### OpenClaw Sandboxing

Enable OpenClaw's per-session Docker sandboxing:

```yaml
sessions:
  sandbox:
    enabled: true
    type: docker
    network: harness-network
```

### ToolHive Containers

All MCP servers run in separate containers:
- Read-only filesystem where possible
- No host Docker socket access
- Network isolation

## 8. Monitoring & Logging

### Log Retention

Configure log rotation to prevent disk fill:

```bash
# Add to /etc/logrotate.d/harness
/var/log/harness/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

### Audit Logging

Enable audit logging for:
- Tool calls
- Forge approvals
- Secret access
- Agent spawns

## 9. Backup & Recovery

### Regular Backups

```bash
# Backup harness state (not secrets)
tar -czf harness-backup-$(date +%Y%m%d).tar.gz \
  ai/supervisor/state.json \
  ai/supervisor/task_queue.json \
  ai/supervisor/allowlists.json \
  ai/supervisor/mcp.servers.json
```

### Recovery Plan

Document recovery procedures:
- How to restore from backup
- How to revoke compromised credentials
- How to isolate compromised agents

## 10. Verification Checklist

After hardening, verify:

- [ ] Firewall blocks all unnecessary ports
- [ ] Control UI not publicly accessible
- [ ] File permissions restrictive (600/700)
- [ ] Insecure auth disabled
- [ ] ToolHive bound to localhost only
- [ ] Secrets not in files/repo
- [ ] Log rotation configured
- [ ] Backup procedure tested

## Quick Setup Script

```bash
#!/bin/bash
# Quick hardening script for Hostinger VPS

# 1. Set file permissions
chmod 700 ~/.openclaw
chmod 600 ~/.openclaw/*.json
chmod 600 ai/supervisor/*.json

# 2. Configure firewall (ufw)
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp  # SSH
sudo ufw allow 80/tcp  # HTTP (if needed)
sudo ufw allow 443/tcp # HTTPS (if needed)
sudo ufw enable

# 3. Bind ToolHive to localhost
# (Already in docker-compose.yml)

# 4. Disable insecure auth
export OPENCLAW_GATEWAY_CONTROL_UI_ALLOW_INSECURE_AUTH=false

echo "Hardening complete. Review HOSTINGER_HARDENING.md for full checklist."
```

## References

- [OpenClaw Security Docs](https://docs.openclaw.ai/gateway/security)
- [Hostinger OpenClaw Security Checklist](https://www.hostinger.com/tutorials/openclaw-security)
- [ToolHive Security](https://docs.stacklok.com/toolhive/)
