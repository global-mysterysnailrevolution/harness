#!/usr/bin/env python3
"""
Proxmox VM Management Tool
Narrow, audited interface for OpenClaw to manage Proxmox VMs.
All operations go through the Proxmox REST API -- no raw SSH.

Usage:
    python3 proxmox_tool.py <operation> [--args '<json>'] [--dry-run] [--approve <id>]

Operations:
    list_vms        List all VMs on the node
    get_vm          Get details for a single VM
    create_vm       Create a new VM
    clone_template  Clone an existing VM/template
    start_vm        Start a VM
    stop_vm         Stop a VM  (requires approval)
    set_resources   Update CPU / RAM / disk on a VM
    delete_vm       Delete a VM (requires approval)
"""

import argparse
import json
import os
import ssl
import sys
import hashlib
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HARNESS_ROOT = Path(os.environ.get("HARNESS_ROOT", Path(__file__).resolve().parent.parent.parent))
AUDIT_LOG = HARNESS_ROOT / "ai" / "supervisor" / "proxmox_audit.jsonl"
PENDING_APPROVALS = HARNESS_ROOT / "ai" / "supervisor" / "pending_approvals.json"

# ---------------------------------------------------------------------------
# Quotas (override via env vars)
# ---------------------------------------------------------------------------
QUOTAS = {
    "max_cpu_per_vm": int(os.environ.get("PROXMOX_MAX_CPU", "16")),
    "max_ram_mb_per_vm": int(os.environ.get("PROXMOX_MAX_RAM_MB", "32768")),
    "max_disk_gb_per_vm": int(os.environ.get("PROXMOX_MAX_DISK_GB", "500")),
    "max_vms_total": int(os.environ.get("PROXMOX_MAX_VMS", "50")),
}

DESTRUCTIVE_OPS = {"delete_vm", "stop_vm"}
APPROVAL_TTL_MINUTES = 30


# ===================================================================
# Proxmox REST client (stdlib-only, no third-party deps)
# ===================================================================

class ProxmoxClient:
    """Minimal Proxmox REST API client."""

    def __init__(self):
        self.host = os.environ.get("PROXMOX_HOST", "")
        self.port = int(os.environ.get("PROXMOX_PORT", "8006"))
        self.token_id = os.environ.get("PROXMOX_TOKEN_ID", "")
        self.token_secret = os.environ.get("PROXMOX_TOKEN_SECRET", "")
        self.verify_ssl = os.environ.get("PROXMOX_VERIFY_SSL", "false").lower() == "true"
        self.node = os.environ.get("PROXMOX_NODE", "pve")

        if not all([self.host, self.token_id, self.token_secret]):
            raise EnvironmentError(
                "Set PROXMOX_HOST, PROXMOX_TOKEN_ID, and PROXMOX_TOKEN_SECRET"
            )

    @property
    def _base(self) -> str:
        return f"https://{self.host}:{self.port}/api2/json"

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"PVEAPIToken={self.token_id}={self.token_secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    @property
    def _ssl_ctx(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        if not self.verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Any:
        url = f"{self._base}{path}"
        body = urllib.parse.urlencode(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=self._headers, method=method)
        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx) as resp:
                payload = json.loads(resp.read().decode())
                return payload.get("data", payload)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode() if exc.fp else ""
            raise RuntimeError(f"Proxmox API {method} {path} -> {exc.code}: {err_body}") from exc

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, data: Optional[Dict] = None) -> Any:
        return self._request("POST", path, data)

    def put(self, path: str, data: Optional[Dict] = None) -> Any:
        return self._request("PUT", path, data)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)


# ===================================================================
# Audit log
# ===================================================================

def audit(operation: str, params: Dict, result: Any, dry_run: bool = False):
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "op": operation,
        "params": params,
        "dry_run": dry_run,
        "result_summary": _summarize(result),
    }
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _summarize(result: Any) -> str:
    if isinstance(result, dict) and "error" in result:
        return f"error: {result['error']}"
    if isinstance(result, dict) and "vmid" in result:
        return f"vmid={result['vmid']}"
    if isinstance(result, list):
        return f"{len(result)} items"
    return "ok"


# ===================================================================
# Approval gate for destructive operations
# ===================================================================

def _load_approvals() -> Dict:
    if PENDING_APPROVALS.exists():
        with open(PENDING_APPROVALS, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"pending": [], "completed": []}


def _save_approvals(data: Dict):
    PENDING_APPROVALS.parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_APPROVALS, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def request_approval(operation: str, params: Dict) -> Dict:
    """Create a pending approval request. Returns the approval object."""
    approval_id = hashlib.sha256(
        f"{operation}:{json.dumps(params, sort_keys=True)}:{datetime.utcnow().isoformat()}".encode()
    ).hexdigest()[:12]

    approval = {
        "id": approval_id,
        "operation": operation,
        "params": params,
        "status": "pending",
        "requested_at": datetime.utcnow().isoformat() + "Z",
        "expires_at": (datetime.utcnow() + timedelta(minutes=APPROVAL_TTL_MINUTES)).isoformat() + "Z",
    }

    data = _load_approvals()
    data["pending"].append(approval)
    _save_approvals(data)

    return {
        "approval_required": True,
        "approval_id": approval_id,
        "operation": operation,
        "params": params,
        "message": (
            f"Destructive operation '{operation}' requires approval. "
            f"Ask the user to confirm, then re-run with --approve {approval_id}"
        ),
        "expires_at": approval["expires_at"],
    }


def check_approval(approval_id: str) -> Optional[Dict]:
    """Check if an approval ID exists and is still valid."""
    data = _load_approvals()
    for entry in data["pending"]:
        if entry["id"] == approval_id:
            expires = datetime.fromisoformat(entry["expires_at"].rstrip("Z"))
            if datetime.utcnow() > expires:
                entry["status"] = "expired"
                _save_approvals(data)
                return None
            return entry
    return None


def consume_approval(approval_id: str) -> Optional[Dict]:
    """Mark an approval as consumed (used). Returns the approval or None."""
    data = _load_approvals()
    for i, entry in enumerate(data["pending"]):
        if entry["id"] == approval_id:
            entry["status"] = "consumed"
            entry["consumed_at"] = datetime.utcnow().isoformat() + "Z"
            data["completed"].append(data["pending"].pop(i))
            _save_approvals(data)
            return entry
    return None


# ===================================================================
# Quota enforcement
# ===================================================================

def enforce_quotas(params: Dict, existing_vms: Optional[List] = None):
    """Raise ValueError if params exceed quotas."""
    cpu = params.get("cores") or params.get("cpu", 0)
    if cpu and int(cpu) > QUOTAS["max_cpu_per_vm"]:
        raise ValueError(f"CPU {cpu} exceeds max {QUOTAS['max_cpu_per_vm']}")

    ram = params.get("memory", 0)
    if ram and int(ram) > QUOTAS["max_ram_mb_per_vm"]:
        raise ValueError(f"RAM {ram}MB exceeds max {QUOTAS['max_ram_mb_per_vm']}MB")

    disk_gb = params.get("disk_gb", 0)
    if disk_gb and int(disk_gb) > QUOTAS["max_disk_gb_per_vm"]:
        raise ValueError(f"Disk {disk_gb}GB exceeds max {QUOTAS['max_disk_gb_per_vm']}GB")

    if existing_vms is not None and len(existing_vms) >= QUOTAS["max_vms_total"]:
        raise ValueError(f"VM count {len(existing_vms)} reached max {QUOTAS['max_vms_total']}")


# ===================================================================
# VM Operations
# ===================================================================

def list_vms(px: ProxmoxClient, params: Dict) -> List[Dict]:
    vms = px.get(f"/nodes/{px.node}/qemu")
    result = []
    for vm in vms:
        result.append({
            "vmid": vm.get("vmid"),
            "name": vm.get("name", ""),
            "status": vm.get("status"),
            "cpu": vm.get("cpus"),
            "maxmem_mb": round(vm.get("maxmem", 0) / 1048576),
            "maxdisk_gb": round(vm.get("maxdisk", 0) / 1073741824, 1),
            "uptime": vm.get("uptime", 0),
            "template": bool(vm.get("template", 0)),
        })
    return sorted(result, key=lambda v: v["vmid"])


def get_vm(px: ProxmoxClient, params: Dict) -> Dict:
    vmid = params["vmid"]
    status = px.get(f"/nodes/{px.node}/qemu/{vmid}/status/current")
    config = px.get(f"/nodes/{px.node}/qemu/{vmid}/config")
    return {
        "vmid": vmid,
        "name": config.get("name", ""),
        "status": status.get("status"),
        "cpu": config.get("cores"),
        "sockets": config.get("sockets", 1),
        "memory_mb": config.get("memory"),
        "boot_disk": config.get("scsi0") or config.get("virtio0") or config.get("ide0", ""),
        "net0": config.get("net0", ""),
        "ostype": config.get("ostype", ""),
        "template": bool(config.get("template", 0)),
        "uptime": status.get("uptime", 0),
        "agent": config.get("agent", ""),
        "cloud_init": {
            "ciuser": config.get("ciuser", ""),
            "citype": config.get("citype", ""),
            "ipconfig0": config.get("ipconfig0", ""),
            "nameserver": config.get("nameserver", ""),
            "searchdomain": config.get("searchdomain", ""),
            "sshkeys": "(set)" if config.get("sshkeys") else "(not set)",
        },
    }


def create_vm(px: ProxmoxClient, params: Dict) -> Dict:
    enforce_quotas(params, existing_vms=px.get(f"/nodes/{px.node}/qemu"))

    vmid = params.get("vmid")
    if not vmid:
        vmid = _next_vmid(px)

    name = params.get("name", f"vm-{vmid}")

    existing = px.get(f"/nodes/{px.node}/qemu")
    for vm in existing:
        if str(vm.get("vmid")) == str(vmid):
            return {"vmid": vmid, "name": vm.get("name", ""), "status": "already_exists"}
        if vm.get("name") == name:
            return {"vmid": vm["vmid"], "name": name, "status": "already_exists"}

    create_params = {
        "vmid": vmid,
        "name": name,
        "cores": params.get("cores", 2),
        "sockets": params.get("sockets", 1),
        "memory": params.get("memory", 2048),
        "ostype": params.get("ostype", "l26"),
        "scsihw": params.get("scsihw", "virtio-scsi-single"),
    }

    storage = params.get("storage", "local-lvm")
    disk_gb = params.get("disk_gb", 32)
    create_params["scsi0"] = f"{storage}:{disk_gb}"

    if params.get("iso"):
        create_params["ide2"] = f"{params['iso']},media=cdrom"
    if params.get("net_bridge"):
        create_params["net0"] = f"virtio,bridge={params['net_bridge']}"
    else:
        create_params["net0"] = "virtio,bridge=vmbr0"

    if params.get("cloud_init"):
        ci = params["cloud_init"]
        if ci.get("user"):
            create_params["ciuser"] = ci["user"]
        if ci.get("password"):
            create_params["cipassword"] = ci["password"]
        if ci.get("sshkeys"):
            create_params["sshkeys"] = urllib.parse.quote(ci["sshkeys"], safe="")
        if ci.get("ipconfig0"):
            create_params["ipconfig0"] = ci["ipconfig0"]
        if ci.get("nameserver"):
            create_params["nameserver"] = ci["nameserver"]
        create_params["ide2"] = f"{storage}:cloudinit"

    if params.get("start_on_create"):
        create_params["start"] = 1

    px.post(f"/nodes/{px.node}/qemu", data=create_params)
    return {"vmid": vmid, "name": name, "status": "created", "params": create_params}


def clone_template(px: ProxmoxClient, params: Dict) -> Dict:
    source_vmid = params["source_vmid"]
    new_vmid = params.get("vmid") or _next_vmid(px)
    name = params.get("name", f"clone-{new_vmid}")

    enforce_quotas(params, existing_vms=px.get(f"/nodes/{px.node}/qemu"))

    clone_params: Dict[str, Any] = {
        "newid": new_vmid,
        "name": name,
    }
    if params.get("full_clone", True):
        clone_params["full"] = 1
    if params.get("storage"):
        clone_params["storage"] = params["storage"]
    if params.get("target_node"):
        clone_params["target"] = params["target_node"]

    px.post(f"/nodes/{px.node}/qemu/{source_vmid}/clone", data=clone_params)
    return {"vmid": new_vmid, "name": name, "cloned_from": source_vmid, "status": "cloning"}


def start_vm(px: ProxmoxClient, params: Dict) -> Dict:
    vmid = params["vmid"]
    px.post(f"/nodes/{px.node}/qemu/{vmid}/status/start")
    return {"vmid": vmid, "status": "starting"}


def stop_vm(px: ProxmoxClient, params: Dict) -> Dict:
    vmid = params["vmid"]
    timeout = params.get("timeout", 60)
    if params.get("force"):
        px.post(f"/nodes/{px.node}/qemu/{vmid}/status/stop")
    else:
        px.post(f"/nodes/{px.node}/qemu/{vmid}/status/shutdown", data={"timeout": timeout})
    return {"vmid": vmid, "status": "stopping", "force": bool(params.get("force"))}


def set_resources(px: ProxmoxClient, params: Dict) -> Dict:
    vmid = params["vmid"]
    enforce_quotas(params)

    update: Dict[str, Any] = {}
    if "cores" in params:
        update["cores"] = params["cores"]
    if "sockets" in params:
        update["sockets"] = params["sockets"]
    if "memory" in params:
        update["memory"] = params["memory"]
    if "balloon" in params:
        update["balloon"] = params["balloon"]

    if not update:
        return {"vmid": vmid, "status": "no_changes"}

    px.put(f"/nodes/{px.node}/qemu/{vmid}/config", data=update)
    return {"vmid": vmid, "status": "updated", "changes": update}


def delete_vm(px: ProxmoxClient, params: Dict) -> Dict:
    vmid = params["vmid"]
    purge = params.get("purge", True)
    path = f"/nodes/{px.node}/qemu/{vmid}"
    if purge:
        path += "?purge=1&destroy-unreferenced-disks=1"
    px.delete(path)
    return {"vmid": vmid, "status": "deleted"}


def _next_vmid(px: ProxmoxClient) -> int:
    """Get next available VMID from the cluster."""
    return px.get("/cluster/nextid")


# ===================================================================
# Operation dispatcher
# ===================================================================

OPERATIONS = {
    "list_vms": list_vms,
    "get_vm": get_vm,
    "create_vm": create_vm,
    "clone_template": clone_template,
    "start_vm": start_vm,
    "stop_vm": stop_vm,
    "set_resources": set_resources,
    "delete_vm": delete_vm,
}

SAFE_OPS = set(OPERATIONS.keys()) - DESTRUCTIVE_OPS


def run(operation: str, params: Dict, dry_run: bool = False, approve_id: Optional[str] = None) -> Dict:
    """
    Main entry point.
    - Safe ops execute immediately.
    - Destructive ops require --approve <id> (unless --dry-run).
    """
    if operation not in OPERATIONS:
        return {"error": f"Unknown operation: {operation}. Valid: {sorted(OPERATIONS.keys())}"}

    # Dry-run: show what would happen
    if dry_run:
        result = {
            "dry_run": True,
            "operation": operation,
            "params": params,
            "destructive": operation in DESTRUCTIVE_OPS,
            "quotas": QUOTAS,
        }
        audit(operation, params, result, dry_run=True)
        return result

    # Destructive ops: approval gate
    if operation in DESTRUCTIVE_OPS:
        if not approve_id:
            result = request_approval(operation, params)
            audit(operation, params, result)
            return result

        approval = check_approval(approve_id)
        if not approval:
            return {"error": f"Approval '{approve_id}' not found or expired."}
        if approval["operation"] != operation:
            return {"error": f"Approval '{approve_id}' is for '{approval['operation']}', not '{operation}'."}

        consume_approval(approve_id)

    # Execute
    try:
        px = ProxmoxClient()
        result = OPERATIONS[operation](px, params)
        audit(operation, params, result)
        return result
    except EnvironmentError as exc:
        err = {"error": str(exc), "hint": "Check PROXMOX_* environment variables"}
        audit(operation, params, err)
        return err
    except Exception as exc:
        err = {"error": str(exc)}
        audit(operation, params, err)
        return err


# ===================================================================
# CLI
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="Proxmox VM Management Tool")
    parser.add_argument("operation", choices=sorted(OPERATIONS.keys()),
                        help="Operation to perform")
    parser.add_argument("--args", default="{}", help="JSON parameters")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    parser.add_argument("--approve", default=None, help="Approval ID for destructive ops")
    args = parser.parse_args()

    try:
        params = json.loads(args.args)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid JSON in --args: {exc}"}))
        sys.exit(1)

    result = run(args.operation, params, dry_run=args.dry_run, approve_id=args.approve)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
