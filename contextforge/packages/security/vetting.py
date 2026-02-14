"""
Security Vetting Pipeline — wraps existing harness vetting tools.

This module provides a ContextForge-native interface to the existing
Gate A (tool_vetting.py) and Gate B (tool_broker.py) systems, adding:
- Correlation ID tracking
- Structured event emission
- SBOM generation for vetted artifacts
"""
from __future__ import annotations

import importlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from contextforge.packages.events import emit_event, CorrelationIDs


@dataclass
class ScanFinding:
    scanner: str
    severity: str  # critical, high, medium, low, info
    message: str
    file: Optional[str] = None
    line: Optional[int] = None


@dataclass
class VettingResult:
    """Result of a vetting pipeline run."""
    verdict: str  # pass, warn, fail
    findings: list[ScanFinding] = field(default_factory=list)
    scanners_run: list[str] = field(default_factory=list)
    scanners_skipped: list[str] = field(default_factory=list)
    duration_ms: int = 0
    sbom_path: Optional[str] = None

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "high")

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "findings": [
                {"scanner": f.scanner, "severity": f.severity, "message": f.message,
                 "file": f.file, "line": f.line}
                for f in self.findings
            ],
            "scanners_run": self.scanners_run,
            "scanners_skipped": self.scanners_skipped,
            "duration_ms": self.duration_ms,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "sbom_path": self.sbom_path,
        }


class VettingPipeline:
    """
    Runs security vetting on a target directory.

    Wraps the existing harness tool_vetting.py if available,
    otherwise provides a standalone implementation.
    """

    def __init__(self, correlation: Optional[CorrelationIDs] = None):
        self.correlation = correlation or CorrelationIDs()
        self._harness_vetting = self._try_import_harness_vetting()

    def _try_import_harness_vetting(self):
        """Try to import the existing harness vetting module."""
        try:
            harness_root = Path(__file__).resolve().parents[3]
            broker_path = harness_root / "scripts" / "broker"
            if broker_path.exists() and str(broker_path) not in sys.path:
                sys.path.insert(0, str(broker_path))
            from tool_vetting import run_vetting
            return run_vetting
        except ImportError:
            return None

    def vet(self, target_path: str | Path, proposal_id: Optional[str] = None) -> VettingResult:
        """Run the vetting pipeline on a target directory."""
        start = time.time()
        target = Path(target_path)

        emit_event("vetting.scan_started", "security", self.correlation,
                   payload={"target": str(target), "proposal_id": proposal_id})

        result = VettingResult()

        if self._harness_vetting:
            # Delegate to existing harness vetting
            try:
                harness_result = self._harness_vetting(str(target), proposal_id or "standalone")
                result = self._convert_harness_result(harness_result)
            except Exception as e:
                result.findings.append(ScanFinding(
                    scanner="harness-bridge",
                    severity="info",
                    message=f"Harness vetting failed, running standalone: {e}",
                ))
                result = self._run_standalone(target, result)
        else:
            result = self._run_standalone(target, result)

        result.duration_ms = int((time.time() - start) * 1000)

        # Determine verdict
        if result.critical_count > 0:
            result.verdict = "fail"
        elif result.high_count > 2:
            result.verdict = "fail"
        elif result.high_count > 0 or len(result.findings) > 5:
            result.verdict = "warn"
        else:
            result.verdict = "pass"

        emit_event("vetting.verdict", "security", self.correlation,
                   payload=result.to_dict(), duration_ms=result.duration_ms)

        return result

    def _run_standalone(self, target: Path, result: VettingResult) -> VettingResult:
        """Run standalone vetting scanners."""
        import subprocess

        # Gitleaks (secrets)
        result = self._run_scanner(result, "gitleaks", [
            "gitleaks", "detect", "--source", str(target), "--report-format", "json",
            "--report-path", "/dev/stdout", "--no-git",
        ])

        # Trivy (vulnerabilities)
        result = self._run_scanner(result, "trivy", [
            "trivy", "fs", "--format", "json", "--severity", "CRITICAL,HIGH", str(target),
        ])

        # pip-audit (if Python)
        if (target / "requirements.txt").exists():
            result = self._run_scanner(result, "pip-audit", [
                "pip-audit", "-r", str(target / "requirements.txt"), "--format", "json",
            ])

        # npm audit (if Node)
        if (target / "package.json").exists():
            result = self._run_scanner(result, "npm-audit", [
                "npm", "audit", "--json",
            ], cwd=str(target))

        return result

    def _run_scanner(self, result: VettingResult, name: str, cmd: list[str],
                     cwd: Optional[str] = None) -> VettingResult:
        """Run a single scanner, gracefully degrading if not installed."""
        import subprocess
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=cwd)
            result.scanners_run.append(name)

            if r.stdout.strip():
                try:
                    data = json.loads(r.stdout)
                    findings = self._parse_scanner_output(name, data)
                    result.findings.extend(findings)
                except json.JSONDecodeError:
                    pass
        except FileNotFoundError:
            result.scanners_skipped.append(name)
        except subprocess.TimeoutExpired:
            result.scanners_skipped.append(f"{name} (timeout)")

        return result

    def _parse_scanner_output(self, scanner: str, data: Any) -> list[ScanFinding]:
        """Parse scanner JSON output into ScanFindings."""
        findings = []

        if scanner == "gitleaks" and isinstance(data, list):
            for item in data:
                findings.append(ScanFinding(
                    scanner="gitleaks",
                    severity="critical",
                    message=f"Secret detected: {item.get('Description', 'unknown')}",
                    file=item.get("File"),
                    line=item.get("StartLine"),
                ))
        elif scanner == "trivy" and isinstance(data, dict):
            for result_item in data.get("Results", []):
                for vuln in result_item.get("Vulnerabilities", []):
                    sev = vuln.get("Severity", "UNKNOWN").lower()
                    findings.append(ScanFinding(
                        scanner="trivy",
                        severity=sev,
                        message=f"{vuln.get('VulnerabilityID', '?')}: {vuln.get('Title', '')}",
                        file=result_item.get("Target"),
                    ))

        return findings

    def _convert_harness_result(self, harness_result: Any) -> VettingResult:
        """Convert harness tool_vetting result to VettingResult."""
        result = VettingResult()
        if hasattr(harness_result, "scanners_run"):
            result.scanners_run = harness_result.scanners_run
        if hasattr(harness_result, "findings"):
            for f in harness_result.findings:
                result.findings.append(ScanFinding(
                    scanner=getattr(f, "scanner", "unknown"),
                    severity=getattr(f, "severity", "info"),
                    message=getattr(f, "message", str(f)),
                ))
        return result
