"""
Thin wrapper for playwright-cli commands.
Normalizes output, handles retries, and provides a structured result format.
"""

import subprocess
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Optional


@dataclass
class PlaywrightResult:
    success: bool
    output: str       # snapshot text or command output
    error: str = ""
    screenshot_path: Optional[str] = None


def _run(args: list, timeout: int = 30) -> PlaywrightResult:
    """Run a playwright-cli command and return structured result."""
    if not shutil.which("playwright") and not shutil.which("npx"):
        return PlaywrightResult(
            False, "",
            "playwright-cli not found. Install with: npm install -g playwright"
        )

    cmd = ["npx", "playwright-cli"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode != 0:
            return PlaywrightResult(False, result.stdout, result.stderr)
        return PlaywrightResult(True, result.stdout)
    except subprocess.TimeoutExpired:
        return PlaywrightResult(False, "", f"Timeout after {timeout}s")
    except Exception as e:
        return PlaywrightResult(False, "", str(e))


def navigate(url: str, storage_state: Optional[str] = None) -> PlaywrightResult:
    """Open a URL and return an accessibility tree snapshot."""
    args = ["open", url, "--snapshot"]
    if storage_state and os.path.exists(storage_state):
        args += ["--load-storage", storage_state]
    return _run(args, timeout=45)


def click(selector: str) -> PlaywrightResult:
    """Click an element by CSS selector or accessible text."""
    return _run(["click", selector])


def fill(selector: str, value: str) -> PlaywrightResult:
    """Fill an input element."""
    return _run(["fill", selector, value])


def press_key(key: str) -> PlaywrightResult:
    """Press a keyboard key."""
    return _run(["press", key])


def wait_for(selector: str, timeout_ms: int = 5000) -> PlaywrightResult:
    """Wait for an element to appear."""
    return _run(["wait-for", selector, "--timeout", str(timeout_ms)])


def take_screenshot(output_path: str) -> PlaywrightResult:
    """Take a screenshot to a file."""
    result = _run(["screenshot", output_path], timeout=20)
    if result.success:
        result.screenshot_path = output_path
    return result


def save_auth_state(output_path: str) -> PlaywrightResult:
    """Save current browser authentication state."""
    return _run(["save-storage", output_path])


def evaluate(js_expression: str) -> PlaywrightResult:
    """Evaluate JavaScript in the current page context."""
    return _run(["evaluate", js_expression])


def check_login_wall(snapshot: str) -> bool:
    """
    Heuristic: does the snapshot look like a login page?
    Returns True if a login wall is detected.
    """
    login_signals = [
        "sign in", "log in", "login", "sign up",
        "email address", "password", "forgot password",
        "create account", "authentication required",
        "you must be logged in", "please log in"
    ]
    snapshot_lower = snapshot.lower()
    matches = sum(1 for signal in login_signals if signal in snapshot_lower)
    return matches >= 2


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Playwright-CLI wrapper")
    parser.add_argument("command", choices=["navigate", "click", "fill", "screenshot", "check-login"])
    parser.add_argument("--url", help="URL to navigate to")
    parser.add_argument("--selector", help="CSS selector")
    parser.add_argument("--value", help="Value to fill")
    parser.add_argument("--output", help="Output file for screenshot")
    parser.add_argument("--snapshot-file", help="Snapshot file to check for login wall")
    args = parser.parse_args()

    if args.command == "navigate":
        result = navigate(args.url)
    elif args.command == "click":
        result = click(args.selector)
    elif args.command == "fill":
        result = fill(args.selector, args.value)
    elif args.command == "screenshot":
        result = take_screenshot(args.output or "/tmp/screenshot.png")
    elif args.command == "check-login":
        snapshot = open(args.snapshot_file).read() if args.snapshot_file else ""
        is_login = check_login_wall(snapshot)
        print(json.dumps({"login_wall_detected": is_login}))
        sys.exit(0)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)

    output = {
        "success": result.success,
        "output": result.output[:2000] if result.output else "",
        "error": result.error
    }
    if result.screenshot_path:
        output["screenshot_path"] = result.screenshot_path

    print(json.dumps(output, indent=2))
    sys.exit(0 if result.success else 1)
