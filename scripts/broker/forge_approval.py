#!/usr/bin/env python3
"""
MCP Forge Approval System
Implements hard safety gate: no new executable code without approval
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime

class ForgeApproval:
    """Manages approval workflow for new MCP server installations"""
    
    def __init__(self, approval_dir: Optional[Path] = None):
        self.approval_dir = approval_dir or Path.cwd() / "ai" / "supervisor" / "forge_approvals"
        self.approval_dir.mkdir(parents=True, exist_ok=True)
    
    def propose_server(
        self,
        server_name: str,
        source: str,  # "docker_image", "github_repo", "npm_package"
        source_id: str,  # image name, repo URL, package name
        version: Optional[str] = None,
        digest: Optional[str] = None,
        tools: Optional[List[str]] = None,
        secrets_required: Optional[List[str]] = None,
        proposed_by: str = "system"
    ) -> Dict:
        """Propose a new MCP server installation"""
        
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
            "risk_assessment": None
        }
        
        # Save proposal
        proposal_file = self.approval_dir / f"{proposal_id}.json"
        with open(proposal_file, 'w', encoding='utf-8') as f:
            json.dump(proposal, f, indent=2)
        
        return proposal
    
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
        risk_assessment: Optional[str] = None
    ) -> bool:
        """Approve a proposal (requires human action)"""
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            return False
        
        if proposal["status"] != "pending":
            return False
        
        proposal["status"] = "approved"
        proposal["approved_by"] = approved_by
        proposal["approved_at"] = datetime.now().isoformat()
        proposal["smoke_test_result"] = smoke_test_result
        proposal["risk_assessment"] = risk_assessment
        
        proposal_file = self.approval_dir / f"{proposal_id}.json"
        with open(proposal_file, 'w', encoding='utf-8') as f:
            json.dump(proposal, f, indent=2)
        
        return True
    
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
        
        proposal_file = self.approval_dir / f"{proposal_id}.json"
        with open(proposal_file, 'w', encoding='utf-8') as f:
            json.dump(proposal, f, indent=2)
        
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
