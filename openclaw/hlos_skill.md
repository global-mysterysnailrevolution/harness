# HLOS — Agent Identity, Wallet & Capability Provisioning

HLOS is your agent's identity and credential layer. Use it to provision external capabilities (SMS, databases, APIs) without managing vendor accounts or touching raw credentials. You host and run — HLOS handles auth, billing, and routing.

**Active when:** a user asks you to send SMS, provision infrastructure, manage API keys, check wallet balance, or acquire any external service capability.

---

## How HLOS Works

Your agent calls HLOS via MCP. HLOS provisions the capability, charges the wallet, and returns a confirmation — never raw credentials.

```
You (agent) → HLOS MCP → HLOS Cloud → Vendor (Twilio, MongoDB, etc.)
                                     ↑ credentials stay here forever
```

The MCP server runs at `https://172.18.0.1:8106/mcp` (accessible from this container).

---

## Available MCP Tools

These tools are available directly via the HLOS MCP connection:

### Identity & Wallet
- **`hlos_whoami`** — Show authenticated agent identity and account info
- **`hlos_wallet_balance`** — Check current wallet balance and recent transactions
- **`hlos_capabilities_list`** — List all available capability providers with pricing

### Secrets Management (never see values)
- **`hlos_secrets_list`** — List secret names and metadata in a space (no values exposed)
- **`hlos_secrets_check`** — Check if a specific secret exists
- **`hlos_secrets_suggest`** — Analyze context and suggest which secrets are needed
- **`hlos_secrets_health`** — Check health of secrets (rotation status, exposure risk)
- **`hlos_secrets_create`** — Queue a new secret for user approval (user sets the value)

### Capability Provisioning
- **`hlos_capability_request`** — Request a capability (SMS number, database, API access)
- **`hlos_capability_status`** — Check status of a provisioned capability
- **`hlos_run`** — Run a command with secrets injected (nothing written to disk)

---

## CLI Reference (exec when MCP unavailable)

Fall back to CLI if MCP tools aren't responding:

```bash
# Auth (interactive - user must do this once)
hlos login
hlos whoami

# Wallet
hlos wallet balance

# Secrets (values never printed unless explicitly requested)
hlos secrets list
hlos secrets set MY_API_KEY          # prompts for value
hlos secrets get MY_API_KEY          # retrieves value
hlos secrets delete MY_API_KEY

# Spaces (projects/environments)
hlos spaces list
hlos spaces create my-project
hlos spaces use my-project

# Sync
hlos pull                            # writes to .env.local
hlos push                            # pushes local .env to vault
hlos run -- node app.js             # injects secrets at runtime

# Health
hlos health                          # check rotation/exposure status
hlos audit                           # access logs
```

---

## Common Scenarios

### "Send me an SMS"
```
1. hlos_capabilities_list → find SMS provider (Twilio)
2. hlos_wallet_balance → confirm funds
3. hlos_capability_request → { capability: "sms", message: "...", to: "+1..." }
```

### "Set up a database for my project"
```
1. hlos_capabilities_list → find DB options (Neon Postgres, MongoDB Atlas)
2. hlos_capability_request → { capability: "neon_postgres", name: "my-db" }
3. Return connection info to user (HLOS provisions and bills the wallet)
```

### "Check if my API keys are set up"
```
1. hlos_secrets_list → show all secret names
2. hlos_secrets_health → flag any expired/exposed keys
3. hlos_secrets_suggest → recommend anything missing for their stack
```

### "Manage credentials securely"
```
1. hlos_secrets_create → queue request (user approves + sets value in dashboard)
2. hlos_run -- <command> → inject secrets at runtime without writing to disk
```

---

## Authentication

HLOS requires a one-time login per machine. The session persists in the system keychain.

**User must run on the VPS host:**
```bash
hlos login
# Opens browser OAuth → stored in keychain → all future CLI/MCP calls use it
```

**Check auth status:**
```bash
hlos whoami
```

**Wallet funding:** https://hlos.ai/signup → add payment method → credits appear in wallet

---

## Security Model

- Agents receive **confirmations**, never credentials
- The STAAMP Protocol isolates credentials at the HLOS layer
- Your agent (and this container) never touches raw API keys via HLOS
- All capability usage is logged with cryptographic receipts
- Spending limits configurable per agent in the HLOS dashboard

---

## Setup Status

**Required before first use:**
1. [ ] Account created at https://hlos.ai/signup
2. [ ] `hlos login` run on VPS host
3. [ ] Wallet funded (for paid capabilities like SMS, databases)
4. [ ] MCP bridge confirmed running: `curl https://172.18.0.1:8106/health`

**Installed:** `@hlos/cli` v0.1.0, `@hlos/staamp-mcp` (global on VPS host)
**Bridge port:** 8106 (HTTPS, accessible from container at 172.18.0.1:8106)
