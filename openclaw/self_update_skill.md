# Self-Update Skill

This skill defines how you propose, apply, and roll back changes to your own host infrastructure -- config files, service units, Docker compose, scripts, firewall rules, and harness tools.

**All changes go through a secure pipeline. You NEVER edit host files directly.**

## The Pipeline

```
propose -> diff -> WhatsApp approval -> apply -> health check -> (rollback on failure)
```

Every step is audited. Every apply creates a backup. Every failure auto-rolls-back.

## Tool Reference

All operations use the `self_update_tool.py` CLI:

```
python3 /data/harness/scripts/tools/self_update_tool.py <operation> [--args '<json>'] [--dry-run] [--approve <id>]
```

### Operations

| Operation  | Description                          | Requires Approval |
|------------|--------------------------------------|-------------------|
| `propose`  | Write proposed files + manifest      | No                |
| `diff`     | Show unified diff (current vs proposed) | No             |
| `validate` | Dry-run syntax/path validation       | No                |
| `apply`    | Deploy changes to host               | **Yes**           |
| `rollback` | Revert to last backup                | **Yes**           |
| `status`   | Show pending/applied/backup state    | No                |
| `history`  | List recent applied changes          | No                |

## Workflow

### Step 1: Propose changes

Write the files you want to change and their target destinations:

```json
{
  "description": "Fix igfetch video extraction for new Instagram CDN format",
  "changes": [
    {
      "source": "scripts/igfetch_server.js",
      "dest": "/opt/harness/igfetch/app/scripts/reels/igfetch_server.js",
      "content": "...file content here...",
      "owner": "igfetch:igfetch",
      "mode": "0755",
      "restart": "igfetch"
    }
  ],
  "health_checks": [
    {"type": "http", "url": "http://127.0.0.1:8787/health", "expect": 200},
    {"type": "systemd", "service": "igfetch", "expect": "active"}
  ]
}
```

The `source` is a relative path inside `config_desired/`. The tool creates the files for you from the `content` field.

### Step 2: Review the diff

Always run `diff` before applying:

```
python3 self_update_tool.py diff
```

This shows a unified diff for every file. Use this to compose the WhatsApp message.

### Step 3: Validate

Run `validate` to check for syntax errors, oversized files, and path issues without applying anything:

```
python3 self_update_tool.py validate
```

### Step 4: Get approval via WhatsApp

**MANDATORY.** Before applying, send a message to the user on WhatsApp:

> I'd like to update [component]. Here's what changes:
>
> **[description]**
>
> Files affected:
> - [dest1] (restart: [service])
> - [dest2]
>
> [Summarize the diff -- key changes, not the entire file]
>
> Health checks: [list checks]
>
> Reply "approve" to apply, or "no" to cancel.

Wait for the user to reply "approve", "yes", or "do it".

### Step 5: Apply

After receiving approval, run apply with the approval ID:

```
python3 self_update_tool.py apply --approve <approval_id>
```

The apply script will:
1. Validate all paths against the whitelist
2. Create a timestamped backup
3. Apply files atomically (write tmp -> validate -> mv)
4. Restart only the affected services
5. Run health checks
6. Auto-rollback if health checks fail

### Step 6: Report result

After apply completes, message the user:

- **Success:** "Applied successfully. [component] is healthy."
- **Rollback:** "Applied but health checks failed. Automatically rolled back to previous state. [details]"
- **Error:** "Apply failed: [error]. No changes were made."

## Whitelisted Destinations

You can ONLY write to these paths:

- `/opt/harness/igfetch/` -- igfetch app files
- `/opt/harness/openclaw/` -- skill files
- `/opt/harness/scripts/` -- harness scripts
- `/opt/harness/adapters/` -- web adapters
- `/opt/harness/ai/supervisor/` -- broker configs
- `/opt/harness/secrets/` -- secret configs
- `/etc/systemd/system/igfetch.service` -- igfetch unit (exact path)
- `/docker/openclaw-kx9d/docker-compose.yml` -- compose file (exact path)

Any path outside this list will be **rejected** by the apply script. Don't try.

## Allowed Service Restarts

- `igfetch` (systemd)
- `openclaw` (docker compose in `/docker/openclaw-kx9d/`)

## Safety Rules

1. **NEVER skip the WhatsApp approval step.** Even for "small" changes.
2. **NEVER apply without running diff first.** You need to know what's changing.
3. **NEVER propose binary files.** Only text files are allowed.
4. **NEVER exceed 1 MB per file.** The apply script rejects oversized files.
5. **Max 5 applies per hour.** Rate limiting is enforced by the apply script.
6. **Always include health checks** for any service you restart.
7. **One proposal at a time.** A new `propose` clears the previous proposal.
8. **If apply fails, don't retry blindly.** Investigate the error, fix the proposal, and re-propose.
9. **Always use `validate` before `apply`.** Catch syntax errors early.

## When to Self-Update

Use this pipeline when:

- You detect an issue (e.g., igfetch extraction broke because Instagram changed their API)
- The user asks for a new feature or fix
- A health check fails and you know how to fix it
- You need to update your own skills, tools, or configs

Do NOT use this pipeline for:
- Reading files (use regular file tools)
- Temporary debugging (use the shell)
- Changes that don't affect the host (e.g., conversation-only tasks)

## Rollback

If something goes wrong after apply:

```
python3 self_update_tool.py rollback --approve <approval_id>
```

This restores files from the most recent backup and restarts affected services. Rollback also requires approval.

## Checking State

At any time, run `status` to see:
- Whether there's a pending proposal
- What was last applied
- Available backups

Run `history` to see the last N applied changes (including failures).
