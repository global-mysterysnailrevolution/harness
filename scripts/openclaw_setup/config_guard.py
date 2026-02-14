#!/usr/bin/env python3
"""
OpenClaw Config Guard — validates and safely writes openclaw.json changes.

Prevents the class of bug where a bad config entry (e.g. referencing a
non-existent plugin) crashes the OpenClaw gateway and kills WhatsApp.

Usage:
    from config_guard import ConfigGuard

    guard = ConfigGuard(config_path, environment="vps")
    ok, errors = guard.validate(proposed_config)
    if ok:
        guard.safe_write(proposed_config)

CLI:
    python config_guard.py validate /path/to/openclaw.json
    python config_guard.py validate --proposed /path/to/proposed.json /path/to/openclaw.json
    python config_guard.py health-check [--container openclaw-kx9d-openclaw-1]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class ConfigGuard:
    """Wraps openclaw.json modifications with validation, backup, and rollback."""

    # Known valid plugin IDs from OpenClaw 2026.2.x bundled extensions.
    # Updated by querying `openclaw plugins list` when possible.
    KNOWN_PLUGIN_IDS = {
        "bluebubbles", "copilot-proxy", "diagnostics-otel", "discord",
        "feishu", "google-antigravity-auth", "google-gemini-cli-auth",
        "googlechat", "imessage", "line", "llm-task", "lobster", "matrix",
        "mattermost", "memory-core", "memory-lancedb", "minimax-portal-auth",
        "msteams", "nextcloud-talk", "nostr", "open-prose",
        "qwen-portal-auth", "signal", "slack", "telegram", "tlon", "twitch",
        "voice-call", "whatsapp", "zalo", "zalouser",
    }

    # Keys that should never be overwritten during merge (user-specific data)
    PRESERVE_KEYS = {
        "channels", "gateway.auth", "gateway.remote", "meta", "wizard",
        "identity", "gateway.controlUi",
    }

    def __init__(
        self,
        config_path: str | Path,
        environment: str = "auto",
        container_name: str = "openclaw-kx9d-openclaw-1",
        docker_cmd: str = "docker",
    ):
        self.config_path = Path(config_path)
        self.container_name = container_name
        self.docker_cmd = docker_cmd

        if environment == "auto":
            self.environment = "vps" if "/docker/" in str(config_path) else "local"
        else:
            self.environment = environment

    # ── Validation ──────────────────────────────────────────────────────

    def validate(self, config: dict) -> tuple[bool, list[str]]:
        """Validate a proposed config dict. Returns (ok, list_of_errors)."""
        errors: list[str] = []

        # 1. Check JSON structure basics
        if not isinstance(config, dict):
            errors.append("Config must be a JSON object (dict)")
            return False, errors

        # 2. Validate plugin entries reference known plugin IDs
        known = self._get_known_plugins()
        plugin_entries = config.get("plugins", {}).get("entries", {})
        for plugin_id in plugin_entries:
            if plugin_id not in known:
                errors.append(
                    f"plugins.entries['{plugin_id}']: unknown plugin ID. "
                    f"This WILL crash the gateway. Known IDs: {sorted(known)[:10]}..."
                )

        # 3. Check for obviously bad values
        gateway = config.get("gateway", {})
        mode = gateway.get("mode")
        if mode and mode not in ("local", "cloud", "hybrid"):
            errors.append(f"gateway.mode='{mode}' is not valid (use: local, cloud, hybrid)")

        bind = gateway.get("bind")
        if bind and bind not in ("loopback", "lan", "all"):
            errors.append(f"gateway.bind='{bind}' is not valid (use: loopback, lan, all)")

        # 4. Check compaction mode
        compaction = config.get("agents", {}).get("defaults", {}).get("compaction", {})
        comp_mode = compaction.get("mode")
        if comp_mode and comp_mode not in ("safeguard", "aggressive", "none"):
            errors.append(f"compaction.mode='{comp_mode}' is not valid (use: safeguard, aggressive, none)")

        # 5. Warn about known-bad compaction keys (caused a crash before)
        for bad_key in ("reserveTokens", "keepRecentTokens"):
            if bad_key in compaction:
                errors.append(
                    f"compaction.{bad_key} is not a valid OpenClaw key and will cause a crash. Remove it."
                )

        # 6. Check tool profile
        tools = config.get("tools", {})
        profile = tools.get("profile")
        if profile and profile not in ("full", "coding", "messaging", "minimal"):
            errors.append(f"tools.profile='{profile}' is not valid (use: full, coding, messaging, minimal)")

        # 7. Check model references have provider prefix
        model_cfg = config.get("agents", {}).get("defaults", {}).get("model", {})
        primary = model_cfg.get("primary", "")
        if primary and "/" not in primary and primary not in self._get_model_aliases(config):
            errors.append(
                f"agents.defaults.model.primary='{primary}' should use provider/model format "
                f"(e.g. 'openai/gpt-5.2') or be a defined alias"
            )

        return len(errors) == 0, errors

    def _get_model_aliases(self, config: dict) -> set[str]:
        """Extract defined model aliases from config."""
        aliases = set()
        models = config.get("agents", {}).get("defaults", {}).get("models", {})
        for model_id, model_cfg in models.items():
            if isinstance(model_cfg, dict) and "alias" in model_cfg:
                aliases.add(model_cfg["alias"])
        return aliases

    def _get_known_plugins(self) -> set[str]:
        """Get known plugin IDs. Tries live query, falls back to hardcoded list."""
        try:
            if self.environment == "vps":
                result = subprocess.run(
                    [self.docker_cmd, "exec", self.container_name,
                     "openclaw", "plugins", "list", "--json"],
                    capture_output=True, text=True, timeout=30,
                )
            else:
                result = subprocess.run(
                    ["openclaw", "plugins", "list", "--json"],
                    capture_output=True, text=True, timeout=30,
                )

            if result.returncode == 0 and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    if isinstance(data, list):
                        live_ids = {p.get("id", "") for p in data if isinstance(p, dict)}
                        if live_ids:
                            return live_ids | self.KNOWN_PLUGIN_IDS
                except json.JSONDecodeError:
                    pass
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        return self.KNOWN_PLUGIN_IDS

    # ── Backup ──────────────────────────────────────────────────────────

    def backup(self) -> Path:
        """Create a timestamped backup of the current config."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.config_path.with_suffix(f".json.guard-bak.{timestamp}")
        shutil.copy2(self.config_path, backup_path)
        print(f"[ConfigGuard] Backup: {backup_path}")
        return backup_path

    # ── Safe Write ──────────────────────────────────────────────────────

    def safe_write(self, config: dict, skip_health_check: bool = False) -> tuple[bool, str]:
        """
        Validate, backup, write, and optionally health-check.
        Returns (success, message).
        """
        # 1. Validate
        ok, errors = self.validate(config)
        if not ok:
            return False, f"Validation failed:\n" + "\n".join(f"  - {e}" for e in errors)

        # 2. Backup
        backup_path = self.backup()

        # 3. Write
        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)
            print(f"[ConfigGuard] Written: {self.config_path}")
        except Exception as e:
            # Restore from backup
            shutil.copy2(backup_path, self.config_path)
            return False, f"Write failed, restored backup: {e}"

        # 4. Health check (optional)
        if not skip_health_check:
            healthy, msg = self.health_check()
            if not healthy:
                # Rollback
                print(f"[ConfigGuard] ROLLING BACK: {msg}")
                shutil.copy2(backup_path, self.config_path)
                print(f"[ConfigGuard] Restored: {backup_path}")
                return False, f"Health check failed, rolled back: {msg}"

        return True, f"Config written successfully (backup: {backup_path})"

    # ── Health Check ────────────────────────────────────────────────────

    def health_check(self, timeout_seconds: int = 30) -> tuple[bool, str]:
        """
        Check if OpenClaw stays healthy after a config change.
        VPS: checks Docker container status.
        Local: checks if gateway process is running.
        """
        if self.environment == "vps":
            return self._health_check_docker(timeout_seconds)
        else:
            return self._health_check_local(timeout_seconds)

    def _health_check_docker(self, timeout_seconds: int) -> tuple[bool, str]:
        """Check Docker container health after restart."""
        print(f"[ConfigGuard] Restarting container {self.container_name}...")
        try:
            subprocess.run(
                [self.docker_cmd, "restart", self.container_name],
                capture_output=True, text=True, timeout=60,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return False, f"Failed to restart container: {e}"

        # Poll container status for timeout_seconds
        print(f"[ConfigGuard] Monitoring container for {timeout_seconds}s...")
        start = time.time()
        last_status = ""

        while time.time() - start < timeout_seconds:
            time.sleep(3)
            try:
                result = subprocess.run(
                    [self.docker_cmd, "inspect", "--format",
                     "{{.State.Status}}:{{.State.Running}}",
                     self.container_name],
                    capture_output=True, text=True, timeout=10,
                )
                last_status = result.stdout.strip()

                if "running:true" not in last_status:
                    return False, f"Container stopped (status: {last_status})"

                # Check logs for fatal errors
                log_result = subprocess.run(
                    [self.docker_cmd, "logs", "--tail", "10", "--since",
                     f"{int(time.time() - start)}s", self.container_name],
                    capture_output=True, text=True, timeout=10,
                )
                logs = log_result.stdout + log_result.stderr
                if "plugin not found" in logs.lower():
                    return False, f"Plugin error detected in logs: {logs[-200:]}"
                if "config invalid" in logs.lower():
                    return False, f"Config invalid detected in logs: {logs[-200:]}"

            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Check if listening
        try:
            result = subprocess.run(
                [self.docker_cmd, "logs", "--tail", "20", self.container_name],
                capture_output=True, text=True, timeout=10,
            )
            logs = result.stdout + result.stderr
            if "listening" in logs.lower() or "gateway" in logs.lower():
                print("[ConfigGuard] Container healthy and listening")
                return True, "Container healthy"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return True, f"Container still running after {timeout_seconds}s (status: {last_status})"

    def _health_check_local(self, timeout_seconds: int) -> tuple[bool, str]:
        """Check local gateway health."""
        try:
            result = subprocess.run(
                ["openclaw", "gateway", "status"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                return True, "Gateway running"
            return False, f"Gateway status check failed: {result.stderr}"
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return False, f"Cannot check gateway status: {e}"

    # ── Rollback ────────────────────────────────────────────────────────

    def rollback(self, backup_path: Optional[str | Path] = None) -> bool:
        """Rollback to the most recent backup."""
        if backup_path:
            bp = Path(backup_path)
        else:
            # Find most recent guard backup
            backups = sorted(
                self.config_path.parent.glob("openclaw.json.guard-bak.*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not backups:
                print("[ConfigGuard] No backups found")
                return False
            bp = backups[0]

        if not bp.exists():
            print(f"[ConfigGuard] Backup not found: {bp}")
            return False

        shutil.copy2(bp, self.config_path)
        print(f"[ConfigGuard] Rolled back to: {bp}")
        return True

    # ── Merge Helper ────────────────────────────────────────────────────

    @staticmethod
    def deep_merge(base: dict, overlay: dict, preserve_keys: set[str] | None = None) -> dict:
        """
        Deep-merge overlay into base. Keys in preserve_keys are not overwritten.
        Supports dotted preserve keys like "gateway.auth".
        """
        if preserve_keys is None:
            preserve_keys = set()

        result = base.copy()
        for key, value in overlay.items():
            # Check if this key (or dotted parent) should be preserved
            if key in preserve_keys:
                continue

            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Check dotted children
                child_preserves = {
                    k.split(".", 1)[1]
                    for k in preserve_keys
                    if k.startswith(f"{key}.")
                }
                result[key] = ConfigGuard.deep_merge(result[key], value, child_preserves)
            else:
                result[key] = value

        return result


# ── CLI ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="OpenClaw Config Guard")
    sub = parser.add_subparsers(dest="command")

    # validate
    val_p = sub.add_parser("validate", help="Validate an openclaw.json file")
    val_p.add_argument("config_path", type=Path, help="Path to openclaw.json")
    val_p.add_argument("--proposed", type=Path, help="Proposed config to validate instead")
    val_p.add_argument("--environment", default="auto", choices=["auto", "vps", "local"])
    val_p.add_argument("--container", default="openclaw-kx9d-openclaw-1")

    # health-check
    hc_p = sub.add_parser("health-check", help="Check OpenClaw health")
    hc_p.add_argument("--config-path", type=Path, default=None)
    hc_p.add_argument("--container", default="openclaw-kx9d-openclaw-1")
    hc_p.add_argument("--environment", default="vps", choices=["vps", "local"])
    hc_p.add_argument("--timeout", type=int, default=30)

    # rollback
    rb_p = sub.add_parser("rollback", help="Rollback to most recent backup")
    rb_p.add_argument("config_path", type=Path, help="Path to openclaw.json")
    rb_p.add_argument("--backup", type=Path, help="Specific backup to restore")

    args = parser.parse_args()

    if args.command == "validate":
        guard = ConfigGuard(args.config_path, args.environment, args.container)
        if args.proposed:
            with open(args.proposed) as f:
                config = json.load(f)
        else:
            with open(args.config_path) as f:
                config = json.load(f)
        ok, errors = guard.validate(config)
        if ok:
            print("[ConfigGuard] Config is valid")
            return 0
        else:
            print("[ConfigGuard] Config has errors:")
            for e in errors:
                print(f"  - {e}")
            return 1

    elif args.command == "health-check":
        config_path = args.config_path or Path("/docker/openclaw-kx9d/data/.openclaw/openclaw.json")
        guard = ConfigGuard(config_path, args.environment, args.container)
        ok, msg = guard.health_check(args.timeout)
        print(f"[ConfigGuard] {'HEALTHY' if ok else 'UNHEALTHY'}: {msg}")
        return 0 if ok else 1

    elif args.command == "rollback":
        guard = ConfigGuard(args.config_path)
        return 0 if guard.rollback(args.backup) else 1

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
