#!/usr/bin/env python3
"""
Tool Vetting Engine
Runs security scanners on proposed MCP servers/tools before approval.

Scanners (all gracefully degrade if not installed):
  - Trivy: filesystem/image vuln + misconfig + SBOM
  - Gitleaks: hardcoded secrets in repos
  - ClamAV (clamscan): malware in archives/binaries
  - npm audit / pip-audit: language-specific SCA
  - Semgrep: static analysis
  - Prompt injection detection: scans docs/READMEs for LLM manipulation patterns

Usage:
  python tool_vetting.py vet --source /path/to/server --proposal-id abc123
  python tool_vetting.py vet --image mcr.microsoft.com/playwright --proposal-id abc123
  python tool_vetting.py report --proposal-id abc123
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", Path.cwd()))
APPROVALS_DIR = HARNESS_DIR / "ai" / "supervisor" / "forge_approvals"
VETTING_POLICY_PATH = HARNESS_DIR / "ai" / "supervisor" / "vetting_policy.json"

DEFAULT_POLICY = {
    "max_critical": 0,
    "max_high": 2,
    "max_medium": 10,
    "max_secrets": 0,
    "max_malware": 0,
    "max_injection_signals": 1,
    "auto_reject_on_malware": True,
    "auto_reject_on_critical": True,
    "scanners_enabled": {
        "trivy": True,
        "gitleaks": True,
        "clamav": True,
        "npm_audit": True,
        "pip_audit": True,
        "semgrep": True,
        "prompt_injection": True,
    },
}

# LLM Guard for prompt injection detection (pip install llm-guard)
# Falls back to lightweight regex heuristics if llm-guard not installed.
_LLM_GUARD_AVAILABLE = False
_llm_guard_scanner = None
try:
    from llm_guard.input_scanners import PromptInjection
    from llm_guard.input_scanners.prompt_injection import MatchType
    _LLM_GUARD_AVAILABLE = True
except ImportError:
    pass

# Lightweight fallback patterns (used only when LLM Guard is not installed)
_FALLBACK_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.I),
    re.compile(r"disregard\s+(all\s+)?prior\s+(instructions?|context)", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.I),
    re.compile(r"system\s*:\s*you\s+are", re.I),
    re.compile(r"(send|exfiltrate|transmit|post)\s+.*(secret|token|key|password|credential)", re.I),
    re.compile(r"<!--.*?(ignore|override|system|instruction).*?-->", re.I | re.S),
    re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]{3,}"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_policy() -> dict:
    if VETTING_POLICY_PATH.exists():
        try:
            return json.loads(VETTING_POLICY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_POLICY


def _cmd_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 300) -> Tuple[int, str, str]:
    """Run command, return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, "", f"Timed out after {timeout}s"


# ---------------------------------------------------------------------------
# Individual Scanners
# ---------------------------------------------------------------------------

class ScanResult:
    """Result from a single scanner."""

    def __init__(self, scanner: str, available: bool = True):
        self.scanner = scanner
        self.available = available
        self.findings: List[Dict[str, Any]] = []
        self.raw_output: str = ""
        self.error: str = ""
        self.duration_ms: int = 0

    def add_finding(self, severity: str, title: str, detail: str = "", location: str = ""):
        self.findings.append({
            "severity": severity.lower(),
            "title": title,
            "detail": detail,
            "location": location,
        })

    def to_dict(self) -> dict:
        return {
            "scanner": self.scanner,
            "available": self.available,
            "finding_count": len(self.findings),
            "findings": self.findings,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


def scan_trivy(target: str, is_image: bool = False) -> ScanResult:
    """Run Trivy filesystem or image scan."""
    res = ScanResult("trivy", _cmd_exists("trivy"))
    if not res.available:
        return res
    start = datetime.now()
    mode = "image" if is_image else "fs"
    rc, stdout, stderr = _run(
        ["trivy", mode, "--format", "json", "--severity", "CRITICAL,HIGH,MEDIUM", target]
    )
    res.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
    res.raw_output = stdout[:50000]
    if rc < 0:
        res.error = stderr
        return res
    try:
        data = json.loads(stdout)
        for result in data.get("Results", []):
            for vuln in result.get("Vulnerabilities", []):
                res.add_finding(
                    severity=vuln.get("Severity", "UNKNOWN"),
                    title=f'{vuln.get("VulnerabilityID", "?")} in {vuln.get("PkgName", "?")}',
                    detail=vuln.get("Title", ""),
                    location=result.get("Target", ""),
                )
            for misconfig in result.get("Misconfigurations", []):
                res.add_finding(
                    severity=misconfig.get("Severity", "UNKNOWN"),
                    title=misconfig.get("Title", "Misconfiguration"),
                    detail=misconfig.get("Message", ""),
                    location=result.get("Target", ""),
                )
    except json.JSONDecodeError:
        res.error = "Failed to parse Trivy JSON output"
    return res


def scan_trivy_sbom(target: str) -> Tuple[ScanResult, dict]:
    """Generate SBOM with Trivy."""
    res = ScanResult("trivy_sbom", _cmd_exists("trivy"))
    sbom = {}
    if not res.available:
        return res, sbom
    start = datetime.now()
    rc, stdout, stderr = _run(
        ["trivy", "fs", "--format", "cyclonedx", target]
    )
    res.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
    if rc < 0:
        res.error = stderr
        return res, sbom
    try:
        sbom = json.loads(stdout)
    except json.JSONDecodeError:
        res.error = "Failed to parse SBOM"
    return res, sbom


def scan_gitleaks(target: str) -> ScanResult:
    """Run Gitleaks secrets scan."""
    res = ScanResult("gitleaks", _cmd_exists("gitleaks"))
    if not res.available:
        return res
    start = datetime.now()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        report_path = tmp.name
    try:
        rc, stdout, stderr = _run(
            ["gitleaks", "detect", "--source", target, "--report-format", "json",
             "--report-path", report_path, "--no-git"]
        )
        res.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
        if Path(report_path).exists():
            try:
                findings = json.loads(Path(report_path).read_text())
                for f in (findings if isinstance(findings, list) else []):
                    res.add_finding(
                        severity="high",
                        title=f"Secret: {f.get('RuleID', 'unknown')}",
                        detail=f.get("Description", ""),
                        location=f.get("File", ""),
                    )
            except json.JSONDecodeError:
                pass
        res.raw_output = stdout[:10000]
    finally:
        try:
            os.unlink(report_path)
        except OSError:
            pass
    return res


def scan_clamav(target: str) -> ScanResult:
    """Run ClamAV scan."""
    res = ScanResult("clamav", _cmd_exists("clamscan"))
    if not res.available:
        return res
    start = datetime.now()
    rc, stdout, stderr = _run(
        ["clamscan", "-r", "--no-summary", target], timeout=600
    )
    res.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
    res.raw_output = stdout[:10000]
    if rc == 1:  # virus found
        for line in stdout.splitlines():
            if "FOUND" in line:
                parts = line.split(":")
                location = parts[0].strip() if len(parts) > 1 else ""
                virus = parts[1].strip().replace(" FOUND", "") if len(parts) > 1 else line
                res.add_finding(
                    severity="critical",
                    title=f"Malware: {virus}",
                    detail=line.strip(),
                    location=location,
                )
    elif rc < 0:
        res.error = stderr
    return res


def scan_npm_audit(target: str) -> ScanResult:
    """Run npm audit if package.json exists."""
    pkg = Path(target) / "package.json"
    res = ScanResult("npm_audit", pkg.exists() and _cmd_exists("npm"))
    if not res.available:
        return res
    start = datetime.now()
    rc, stdout, stderr = _run(
        ["npm", "audit", "--json"], cwd=target
    )
    res.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
    res.raw_output = stdout[:30000]
    try:
        data = json.loads(stdout)
        for name, advisory in data.get("vulnerabilities", {}).items():
            res.add_finding(
                severity=advisory.get("severity", "unknown"),
                title=f'{name}@{advisory.get("range", "?")}',
                detail=advisory.get("title", ""),
                location="package.json",
            )
    except json.JSONDecodeError:
        pass
    return res


def scan_pip_audit(target: str) -> ScanResult:
    """Run pip-audit if requirements.txt exists."""
    reqs = Path(target) / "requirements.txt"
    res = ScanResult("pip_audit", reqs.exists() and _cmd_exists("pip-audit"))
    if not res.available:
        return res
    start = datetime.now()
    rc, stdout, stderr = _run(
        ["pip-audit", "-r", str(reqs), "--format", "json"], cwd=target
    )
    res.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
    res.raw_output = stdout[:30000]
    try:
        data = json.loads(stdout)
        for vuln in data.get("dependencies", []):
            for v in vuln.get("vulns", []):
                res.add_finding(
                    severity="high",
                    title=f'{vuln.get("name", "?")} {v.get("id", "")}',
                    detail=v.get("description", ""),
                    location="requirements.txt",
                )
    except json.JSONDecodeError:
        pass
    return res


def scan_semgrep(target: str) -> ScanResult:
    """Run Semgrep with auto config."""
    res = ScanResult("semgrep", _cmd_exists("semgrep"))
    if not res.available:
        return res
    start = datetime.now()
    rc, stdout, stderr = _run(
        ["semgrep", "--config", "auto", "--json", "--quiet", target], timeout=600
    )
    res.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
    res.raw_output = stdout[:50000]
    try:
        data = json.loads(stdout)
        for finding in data.get("results", []):
            sev = finding.get("extra", {}).get("severity", "WARNING")
            sev_map = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}
            res.add_finding(
                severity=sev_map.get(sev, "medium"),
                title=finding.get("check_id", "unknown"),
                detail=finding.get("extra", {}).get("message", ""),
                location=f'{finding.get("path", "")}:{finding.get("start", {}).get("line", "")}',
            )
    except json.JSONDecodeError:
        pass
    return res


def _get_llm_guard_scanner():
    """Lazy-init the LLM Guard scanner (model loads once, reused)."""
    global _llm_guard_scanner
    if _llm_guard_scanner is None and _LLM_GUARD_AVAILABLE:
        _llm_guard_scanner = PromptInjection(threshold=0.5, match_type=MatchType.FULL)
    return _llm_guard_scanner


def _collect_doc_files(target: str) -> list[Path]:
    """Collect doc/source files worth scanning for injection."""
    target_path = Path(target)
    doc_extensions = {".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml"}
    doc_names = {"readme", "description", "instructions", "help", "about", "config"}
    files: list[Path] = []

    if target_path.is_file():
        return [target_path]

    for f in target_path.rglob("*"):
        if not f.is_file() or f.stat().st_size > 500_000:
            continue
        if f.suffix.lower() in doc_extensions or f.stem.lower() in doc_names:
            files.append(f)
        elif f.suffix.lower() in (".py", ".js", ".ts", ".mjs", ".cjs"):
            files.append(f)

    return files[:200]  # cap


def scan_prompt_injection(target: str) -> ScanResult:
    """
    Scan docs/READMEs/tool descriptions for prompt injection.
    Uses LLM Guard's fine-tuned DeBERTa model when available.
    Falls back to lightweight regex heuristics otherwise.
    """
    scanner = _get_llm_guard_scanner()
    using_llm_guard = scanner is not None
    res = ScanResult("prompt_injection", available=True)
    if using_llm_guard:
        res.raw_output = "backend: llm-guard (DeBERTa v3 prompt-injection-v2)"
    else:
        res.raw_output = "backend: regex fallback (install llm-guard for better detection)"

    start = datetime.now()
    files_to_scan = _collect_doc_files(target)
    target_path = Path(target)

    for fpath in files_to_scan:
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel = str(fpath.relative_to(target_path)) if target_path.is_dir() else fpath.name

        if using_llm_guard:
            # LLM Guard: scan each file (or chunks for large files)
            chunks = [content] if len(content) < 4000 else [
                content[i:i + 4000] for i in range(0, len(content), 3500)
            ]
            for ci, chunk in enumerate(chunks):
                _, is_valid, risk_score = scanner.scan(chunk)
                if not is_valid:
                    # Find approximate line number for the chunk
                    offset = ci * 3500
                    line_num = content[:offset].count("\n") + 1 if offset > 0 else 1
                    snippet = chunk[:120].replace("\n", " ")
                    res.add_finding(
                        severity="high",
                        title=f"Prompt injection detected (score: {risk_score:.2f})",
                        detail=f"...{snippet}...",
                        location=f"{rel}:{line_num}",
                    )
        else:
            # Regex fallback
            for pattern in _FALLBACK_INJECTION_PATTERNS:
                for match in pattern.finditer(content):
                    pos = match.start()
                    line_num = content[:pos].count("\n") + 1
                    snippet = content[max(0, pos - 40):pos + len(match.group()) + 40].replace("\n", " ")
                    res.add_finding(
                        severity="high",
                        title=f"Prompt injection signal: {pattern.pattern[:60]}",
                        detail=f"...{snippet}...",
                        location=f"{rel}:{line_num}",
                    )

    res.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
    return res


# ---------------------------------------------------------------------------
# Vetting Pipeline
# ---------------------------------------------------------------------------

class VettingReport:
    """Aggregated report from all scanners."""

    def __init__(self, proposal_id: str, target: str):
        self.proposal_id = proposal_id
        self.target = target
        self.scanner_results: List[ScanResult] = []
        self.sbom: dict = {}
        self.started_at = datetime.now().isoformat()
        self.finished_at: str = ""
        self.verdict: str = "pending"  # pass | fail | warn
        self.verdict_reasons: List[str] = []

    def add_result(self, result: ScanResult):
        self.scanner_results.append(result)

    def evaluate(self, policy: dict) -> str:
        """Evaluate all findings against policy thresholds. Returns verdict."""
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        secrets = 0
        malware = 0
        injections = 0

        for sr in self.scanner_results:
            for f in sr.findings:
                sev = f["severity"]
                counts[sev] = counts.get(sev, 0) + 1
                if sr.scanner == "gitleaks":
                    secrets += 1
                if sr.scanner == "clamav" and sev == "critical":
                    malware += 1
                if sr.scanner == "prompt_injection":
                    injections += 1

        reasons = []
        if policy.get("auto_reject_on_malware") and malware > 0:
            reasons.append(f"Malware detected: {malware}")
        if policy.get("auto_reject_on_critical") and counts["critical"] > policy.get("max_critical", 0):
            reasons.append(f'Critical vulns: {counts["critical"]} (max {policy.get("max_critical", 0)})')
        if counts["high"] > policy.get("max_high", 2):
            reasons.append(f'High vulns: {counts["high"]} (max {policy.get("max_high", 2)})')
        if counts["medium"] > policy.get("max_medium", 10):
            reasons.append(f'Medium vulns: {counts["medium"]} (max {policy.get("max_medium", 10)})')
        if secrets > policy.get("max_secrets", 0):
            reasons.append(f"Secrets found: {secrets} (max {policy.get('max_secrets', 0)})")
        if injections > policy.get("max_injection_signals", 1):
            reasons.append(f"Injection signals: {injections} (max {policy.get('max_injection_signals', 1)})")

        self.verdict_reasons = reasons
        if any("Malware" in r for r in reasons):
            self.verdict = "fail"
        elif len(reasons) > 0:
            self.verdict = "fail"
        elif counts["high"] > 0 or injections > 0:
            self.verdict = "warn"
        else:
            self.verdict = "pass"

        self.finished_at = datetime.now().isoformat()
        return self.verdict

    def summary_counts(self) -> dict:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0}
        for sr in self.scanner_results:
            for f in sr.findings:
                counts[f["severity"]] = counts.get(f["severity"], 0) + 1
                counts["total"] += 1
        return counts

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "target": self.target,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "verdict": self.verdict,
            "verdict_reasons": self.verdict_reasons,
            "summary": self.summary_counts(),
            "scanners": [sr.to_dict() for sr in self.scanner_results],
        }

    def to_markdown(self) -> str:
        counts = self.summary_counts()
        badge = {"pass": "[PASS]", "warn": "[WARN]", "fail": "[FAIL]"}.get(self.verdict, "[???]")
        lines = [
            f"# Tool Vetting Report {badge}",
            f"",
            f"**Proposal:** `{self.proposal_id}`",
            f"**Target:** `{self.target}`",
            f"**Date:** {self.started_at[:19]}",
            f"**Verdict:** {self.verdict.upper()}",
            f"",
        ]
        if self.verdict_reasons:
            lines.append("## Rejection Reasons")
            lines.append("")
            for r in self.verdict_reasons:
                lines.append(f"- {r}")
            lines.append("")

        lines.append("## Summary")
        lines.append("")
        lines.append(f"| Severity | Count |")
        lines.append(f"|----------|-------|")
        for sev in ["critical", "high", "medium", "low"]:
            lines.append(f"| {sev.title()} | {counts.get(sev, 0)} |")
        lines.append(f"| **Total** | **{counts['total']}** |")
        lines.append("")

        for sr in self.scanner_results:
            status = "available" if sr.available else "not installed"
            lines.append(f"## {sr.scanner} ({status})")
            lines.append("")
            if not sr.available:
                lines.append(f"*Scanner not installed - skipped*")
                lines.append("")
                continue
            if sr.error:
                lines.append(f"**Error:** {sr.error}")
                lines.append("")
            lines.append(f"Findings: {len(sr.findings)} | Duration: {sr.duration_ms}ms")
            lines.append("")
            if sr.findings:
                lines.append("| Severity | Title | Location |")
                lines.append("|----------|-------|----------|")
                for f in sr.findings[:50]:  # cap display
                    title = f["title"][:80]
                    loc = f["location"][:60]
                    lines.append(f'| {f["severity"]} | {title} | {loc} |')
                if len(sr.findings) > 50:
                    lines.append(f"| ... | *{len(sr.findings) - 50} more* | ... |")
                lines.append("")

        return "\n".join(lines)

    def save(self, output_dir: Optional[Path] = None):
        """Save report artifacts to forge_approvals directory."""
        out = output_dir or APPROVALS_DIR
        out.mkdir(parents=True, exist_ok=True)

        # JSON findings
        findings_path = out / f"{self.proposal_id}_FINDINGS.json"
        findings_path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

        # Markdown report
        report_path = out / f"{self.proposal_id}_VETTING.md"
        report_path.write_text(self.to_markdown(), encoding="utf-8")

        # SBOM (if generated)
        if self.sbom:
            sbom_path = out / f"{self.proposal_id}_SBOM.json"
            sbom_path.write_text(json.dumps(self.sbom, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "findings": str(findings_path),
            "report": str(report_path),
            "sbom": str(out / f"{self.proposal_id}_SBOM.json") if self.sbom else None,
        }


def run_vetting(
    target: str,
    proposal_id: str,
    is_image: bool = False,
    policy: Optional[dict] = None,
) -> VettingReport:
    """
    Run full vetting pipeline on a target (filesystem path or container image).
    Returns VettingReport with verdict.
    """
    pol = policy or _load_policy()
    enabled = pol.get("scanners_enabled", DEFAULT_POLICY["scanners_enabled"])
    report = VettingReport(proposal_id, target)

    # --- Trivy vuln scan ---
    if enabled.get("trivy", True):
        report.add_result(scan_trivy(target, is_image=is_image))

    # --- Trivy SBOM ---
    if enabled.get("trivy", True) and not is_image:
        sbom_result, sbom_data = scan_trivy_sbom(target)
        report.add_result(sbom_result)
        report.sbom = sbom_data

    # --- Gitleaks ---
    if enabled.get("gitleaks", True) and not is_image:
        report.add_result(scan_gitleaks(target))

    # --- ClamAV ---
    if enabled.get("clamav", True) and not is_image:
        report.add_result(scan_clamav(target))

    # --- npm audit ---
    if enabled.get("npm_audit", True) and not is_image:
        report.add_result(scan_npm_audit(target))

    # --- pip-audit ---
    if enabled.get("pip_audit", True) and not is_image:
        report.add_result(scan_pip_audit(target))

    # --- Semgrep ---
    if enabled.get("semgrep", True) and not is_image:
        report.add_result(scan_semgrep(target))

    # --- Prompt injection scan ---
    if enabled.get("prompt_injection", True) and not is_image:
        report.add_result(scan_prompt_injection(target))

    # --- Evaluate ---
    report.evaluate(pol)
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Tool Vetting Engine")
    sub = parser.add_subparsers(dest="command")

    vet_p = sub.add_parser("vet", help="Run vetting on a target")
    vet_p.add_argument("--source", required=True, help="Filesystem path or container image")
    vet_p.add_argument("--proposal-id", required=True, help="Forge proposal ID")
    vet_p.add_argument("--image", action="store_true", help="Target is a container image")
    vet_p.add_argument("--output-dir", help="Output directory (default: forge_approvals)")
    vet_p.add_argument("--json", action="store_true", help="Output JSON to stdout")

    report_p = sub.add_parser("report", help="View existing vetting report")
    report_p.add_argument("--proposal-id", required=True, help="Forge proposal ID")

    args = parser.parse_args()

    if args.command == "vet":
        report = run_vetting(
            target=args.source,
            proposal_id=args.proposal_id,
            is_image=args.image,
        )
        out_dir = Path(args.output_dir) if args.output_dir else None
        paths = report.save(out_dir)

        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(report.to_markdown())
            print(f"\nArtifacts saved:")
            for k, v in paths.items():
                if v:
                    print(f"  {k}: {v}")

        sys.exit(0 if report.verdict != "fail" else 1)

    elif args.command == "report":
        findings_path = APPROVALS_DIR / f"{args.proposal_id}_FINDINGS.json"
        report_path = APPROVALS_DIR / f"{args.proposal_id}_VETTING.md"

        if report_path.exists():
            print(report_path.read_text(encoding="utf-8"))
        elif findings_path.exists():
            print(findings_path.read_text(encoding="utf-8"))
        else:
            print(f"No vetting report found for proposal {args.proposal_id}")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
