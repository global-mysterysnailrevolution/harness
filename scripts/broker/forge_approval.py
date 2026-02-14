#!/usr/bin/env python3
"""
MCP Forge Approval System
Implements hard safety gate: no new executable code without approval.

Vetting is mandatory: propose_server() triggers the vetting pipeline
and approve() blocks unless vetting has passed (or been overridden).
"""

import json
import hashlib
import sys
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime

# Import vetting engine (same package)
sys.path.insert(0, str(Path(__file__).parent))
try:
    from tool_vetting import run_vetting, VettingReport
except ImportError:
    run_vetting = None  # type: ignore
    VettingReport = None  # type: ignore


class ForgeApproval:
    """Manages approval workflow for new MCP server installations"""
    
    def __init__(self, approval_dir: Optional[Path] = None):
        self.approval_dir = approval_dir or Path.cwd() / "ai" / "supervisor" / "forge_approvals"
        self.approval_dir.mkdir(parents=True, exist_ok=True)
    
    def propose_server(
        self,
        server_name: str,
        source: str,  # "docker_image", "github_repo", "npm_package", "openapi"
        source_id: str,  # image name, repo URL, package name
        version: Optional[str] = None,
        digest: Optional[str] = None,
        tools: Optional[List[str]] = None,
        secrets_required: Optional[List[str]] = None,
        proposed_by: str = "system",
        source_path: Optional[str] = None,
    ) -> Dict:
        """
        Propose a new MCP server installation.
        If source_path is provided, vetting runs automatically.
        """
        
        proposal_id = hashlib.sha256(
            f"{server_name}:{source}:{source_id}:{version}".encode()
        ).hexdigest()[:16]
        
        proposal = {
            "id": proposal_id,
            "server_name": server_name,
            "source": source,
            "source_id": source_id,
            "version": version,
            "digest": digest,
            "tools": tools or [],
            "secrets_required": secrets_required or [],
            "status": "pending",
            "proposed_by": proposed_by,
            "proposed_at": datetime.now().isoformat(),
            "approved_by": None,
            "approved_at": None,
            "rejected_by": None,
            "rejected_at": None,
            "rejection_reason": None,
            "smoke_test_result": None,
            "risk_assessment": None,
            # Vetting fields
            "vetting_status": None,   # None | "running" | "pass" | "warn" | "fail"
            "vetting_verdict": None,
            "vetting_report_path": None,
            "source_path": source_path,
        }
        
        # Save proposal
        proposal_file = self.approval_dir / f"{proposal_id}.json"
        with open(proposal_file, 'w', encoding='utf-8') as f:
            json.dump(proposal, f, indent=2)
        
        # Auto-vet if source path provided and vetting engine available
        if source_path and run_vetting is not None:
            self.vet(proposal_id, source_path, is_image=(source == "docker_image"))
            # Reload to get updated vetting status
            proposal = self.get_proposal(proposal_id) or proposal
        
        return proposal
    
    def vet(
        self,
        proposal_id: str,
        target: Optional[str] = None,
        is_image: bool = False,
    ) -> Optional[Dict]:
        """
        Run vetting pipeline on a proposal. Updates proposal with results.
        Returns vetting report dict, or None if vetting engine not available.
        """
        if run_vetting is None:
            return None
        
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            return None
        
        vet_target = target or proposal.get("source_path") or proposal.get("source_id", "")
        if not vet_target:
            return None
        
        # Mark as running
        proposal["vetting_status"] = "running"
        self._save_proposal(proposal)
        
        # Run vetting
        report = run_vetting(
            target=vet_target,
            proposal_id=proposal_id,
            is_image=is_image,
        )
        artifacts = report.save(self.approval_dir)
        
        # Update proposal
        proposal["vetting_status"] = report.verdict
        proposal["vetting_verdict"] = {
            "verdict": report.verdict,
            "reasons": report.verdict_reasons,
            "summary": report.summary_counts(),
        }
        proposal["vetting_report_path"] = artifacts.get("report")
        
        # Auto-reject on fail
        if report.verdict == "fail":
            proposal["status"] = "rejected"
            proposal["rejected_by"] = "vetting_pipeline"
            proposal["rejected_at"] = datetime.now().isoformat()
            proposal["rejection_reason"] = "; ".join(report.verdict_reasons)
        
        self._save_proposal(proposal)
        return report.to_dict()
    
    def _save_proposal(self, proposal: Dict):
        """Save proposal to disk."""
        proposal_file = self.approval_dir / f"{proposal['id']}.json"
        with open(proposal_file, 'w', encoding='utf-8') as f:
            json.dump(proposal, f, indent=2)
    
    def get_proposal(self, proposal_id: str) -> Optional[Dict]:
        """Get proposal by ID"""
        proposal_file = self.approval_dir / f"{proposal_id}.json"
        if not proposal_file.exists():
            return None
        
        with open(proposal_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def list_pending(self) -> List[Dict]:
        """List all pending proposals"""
        pending = []
        for proposal_file in self.approval_dir.glob("*.json"):
            with open(proposal_file, 'r', encoding='utf-8') as f:
                proposal = json.load(f)
                if proposal.get("status") == "pending":
                    pending.append(proposal)
        return sorted(pending, key=lambda x: x.get("proposed_at", ""))
    
    def approve(
        self,
        proposal_id: str,
        approved_by: str,
        smoke_test_result: Optional[Dict] = None,
        risk_assessment: Optional[str] = None,
        override_vetting: bool = False,
    ) -> Dict:
        """
        Approve a proposal (requires human action).
        Blocks if vetting hasn't run or failed, unless override_vetting=True.
        Returns dict with status and any error message.
        """
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            return {"ok": False, "error": "Proposal not found"}
        
        if proposal["status"] != "pending":
            return {"ok": False, "error": f"Proposal status is '{proposal['status']}', not 'pending'"}
        
        # Gate: require vetting to have passed (or warn with override)
        vetting_status = proposal.get("vetting_status")
        if vetting_status is None and not override_vetting:
            return {
                "ok": False,
                "error": "Vetting has not been run. Use 'vet' command first, or pass override_vetting=True.",
            }
        if vetting_status == "fail" and not override_vetting:
            return {
                "ok": False,
                "error": f"Vetting FAILED: {proposal.get('vetting_verdict', {}).get('reasons', [])}. "
                         "Fix issues and re-vet, or pass override_vetting=True with justification.",
            }
        
        proposal["status"] = "approved"
        proposal["approved_by"] = approved_by
        proposal["approved_at"] = datetime.now().isoformat()
        proposal["smoke_test_result"] = smoke_test_result
        proposal["risk_assessment"] = risk_assessment
        if override_vetting and vetting_status in (None, "fail"):
            proposal["vetting_override"] = {
                "overridden_by": approved_by,
                "at": datetime.now().isoformat(),
                "original_status": vetting_status,
            }
        
        self._save_proposal(proposal)
        return {"ok": True, "proposal_id": proposal_id, "vetting_status": vetting_status}
    
    def reject(
        self,
        proposal_id: str,
        rejected_by: str,
        reason: str
    ) -> bool:
        """Reject a proposal"""
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            return False
        
        if proposal["status"] != "pending":
            return False
        
        proposal["status"] = "rejected"
        proposal["rejected_by"] = rejected_by
        proposal["rejected_at"] = datetime.now().isoformat()
        proposal["rejection_reason"] = reason
        
        self._save_proposal(proposal)
        return True
    
    def is_approved(self, server_name: str, source: str, source_id: str, version: Optional[str] = None) -> bool:
        """Check if a server installation is approved"""
        # Check for exact match
        for proposal_file in self.approval_dir.glob("*.json"):
            with open(proposal_file, 'r', encoding='utf-8') as f:
                proposal = json.load(f)
                if (proposal.get("status") == "approved" and
                    proposal.get("server_name") == server_name and
                    proposal.get("source") == source and
                    proposal.get("source_id") == source_id and
                    (version is None or proposal.get("version") == version)):
                    return True
        return False
