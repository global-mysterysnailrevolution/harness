# Proxmox VM Management Skill

Use this skill when the user asks you to create, manage, or inspect virtual machines on their Proxmox server.

## Tool

All operations go through the `proxmox_tool.py` CLI. **Never SSH into the Proxmox host directly.** Never use `qm` or `pvesh` yourself -- the tool handles everything via the Proxmox REST API.

```
python3 /data/harness/scripts/tools/proxmox_tool.py <operation> --args '<json>'
```

## Operations

### Safe (execute immediately)

| Operation        | Required params                 | Optional params                                                         |
| ---------------- | ------------------------------- | ----------------------------------------------------------------------- |
| `list_vms`       | (none)                          |                                                                         |
| `get_vm`         | `vmid`                          |                                                                         |
| `create_vm`      | `name`                          | `vmid`, `cores`, `sockets`, `memory`, `disk_gb`, `storage`, `ostype`, `iso`, `net_bridge`, `cloud_init`, `scsihw`, `start_on_create` |
| `clone_template` | `source_vmid`                   | `vmid`, `name`, `full_clone`, `storage`, `target_node`                  |
| `start_vm`       | `vmid`                          |                                                                         |
| `set_resources`  | `vmid` + at least one change    | `cores`, `sockets`, `memory`, `balloon`                                 |

### Destructive (require user approval)

| Operation   | Required params | Optional params     |
| ----------- | --------------- | ------------------- |
| `stop_vm`   | `vmid`          | `timeout`, `force`  |
| `delete_vm` | `vmid`          | `purge` (default true) |

When you call a destructive operation, the tool returns an `approval_id`. You **must** tell the user what you want to do and ask for confirmation. Once they say yes, re-run with `--approve <id>`.

### Dry-run

Add `--dry-run` to any operation to see what would happen without executing:

```
python3 proxmox_tool.py create_vm --args '{"name":"test","cores":2,"memory":4096}' --dry-run
```

## Cloud-init

To create a cloud-init VM, include a `cloud_init` object:

```json
{
  "name": "ubuntu-web",
  "cores": 4,
  "memory": 8192,
  "disk_gb": 50,
  "storage": "local-lvm",
  "cloud_init": {
    "user": "deploy",
    "sshkeys": "ssh-ed25519 AAAA... user@host",
    "ipconfig0": "ip=dhcp",
    "nameserver": "1.1.1.1"
  },
  "start_on_create": true
}
```

## Quotas

The tool enforces per-VM resource limits (configurable via env vars):

- Max CPU per VM: `PROXMOX_MAX_CPU` (default 16)
- Max RAM per VM: `PROXMOX_MAX_RAM_MB` (default 32768 MB)
- Max disk per VM: `PROXMOX_MAX_DISK_GB` (default 500 GB)
- Max total VMs: `PROXMOX_MAX_VMS` (default 50)

## Example workflows

### List all VMs
```
python3 proxmox_tool.py list_vms
```

### Create a VM from ISO
```
python3 proxmox_tool.py create_vm --args '{"name":"dev-server","cores":4,"memory":8192,"disk_gb":100,"iso":"local:iso/ubuntu-24.04-live-server-amd64.iso"}'
```

### Clone a template
```
python3 proxmox_tool.py clone_template --args '{"source_vmid":9000,"name":"web-prod-1"}'
```

### Stop a VM (approval flow)
```bash
# Step 1: request
python3 proxmox_tool.py stop_vm --args '{"vmid":105}'
# Output: {"approval_required": true, "approval_id": "abc123def456", ...}

# Step 2: after user says yes
python3 proxmox_tool.py stop_vm --args '{"vmid":105}' --approve abc123def456
```

### Delete a VM (approval flow)
```bash
python3 proxmox_tool.py delete_vm --args '{"vmid":105}' --dry-run
# Review output, then:
python3 proxmox_tool.py delete_vm --args '{"vmid":105}'
# Get approval_id, confirm with user, then:
python3 proxmox_tool.py delete_vm --args '{"vmid":105}' --approve <id>
```

## Safety rules

1. **Never bypass the tool.** Do not SSH into Proxmox or run `qm`/`pvesh` directly.
2. **Always dry-run first** for create, clone, and set_resources if the user hasn't specified exact params.
3. **Never auto-approve.** Destructive operations require explicit user confirmation.
4. **Respect quotas.** If a request exceeds limits, tell the user the quota and ask how to proceed.
5. **Idempotent creates.** If a VM with the same name or VMID already exists, the tool returns the existing VM instead of erroring.
6. **Audit trail.** Every operation is logged to `ai/supervisor/proxmox_audit.jsonl`.

## Credential setup

Credentials are loaded from environment variables. If they're missing, the tool will return a clear error. Direct the user to `harness/secrets/proxmox.env` to configure:

- `PROXMOX_HOST` -- IP or hostname of the Proxmox node
- `PROXMOX_PORT` -- API port (default 8006)
- `PROXMOX_TOKEN_ID` -- API token ID (e.g. `openclaw@pam!openclaw-token`)
- `PROXMOX_TOKEN_SECRET` -- API token secret (UUID)
- `PROXMOX_NODE` -- Node name (default `pve`)
- `PROXMOX_VERIFY_SSL` -- `true` or `false` (default `false`)
