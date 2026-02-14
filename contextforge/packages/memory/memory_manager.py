"""
Durable Memory Manager — pending-to-promoted workflow.

Memory entries go through states:
  pending -> promoted (approved by human)
  pending -> rejected (blocked by human)

This prevents prompt injection from becoming permanent rules.
Integrates with OpenClaw's compaction/memory-flush system.

Storage:
  memory/pending/     - entries awaiting approval
  memory/promoted/    - approved durable memory
  memory/rejected/    - rejected entries (kept for audit)
  MEMORY.md           - compiled promoted rules (auto-generated)
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from contextforge.packages.events import emit_event, CorrelationIDs


class MemoryStatus(str, Enum):
    PENDING = "pending"
    PROMOTED = "promoted"
    REJECTED = "rejected"


@dataclass
class MemoryEntry:
    """A single memory entry with approval tracking."""
    id: str
    content: str
    category: str  # rule, correction, learned, observation
    source: str  # session_id or "compaction_flush" or "manual"
    status: MemoryStatus = MemoryStatus.PENDING
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    promoted_at: Optional[str] = None
    promoted_by: Optional[str] = None
    rejected_at: Optional[str] = None
    rejected_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    correlation_run_id: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryEntry":
        d = d.copy()
        d["status"] = MemoryStatus(d.get("status", "pending"))
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class MemoryManager:
    """Manages the pending-to-promoted memory workflow."""

    def __init__(self, workspace_path: str | Path, correlation: Optional[CorrelationIDs] = None):
        self.workspace = Path(workspace_path)
        self.pending_dir = self.workspace / "memory" / "pending"
        self.promoted_dir = self.workspace / "memory" / "promoted"
        self.rejected_dir = self.workspace / "memory" / "rejected"
        self.memory_md = self.workspace / "MEMORY.md"
        self.correlation = correlation or CorrelationIDs()

        # Ensure directories exist
        for d in [self.pending_dir, self.promoted_dir, self.rejected_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def submit(self, content: str, category: str = "rule",
               source: str = "manual") -> MemoryEntry:
        """Submit a new memory entry to pending queue."""
        import uuid
        entry = MemoryEntry(
            id=str(uuid.uuid4())[:8],
            content=content,
            category=category,
            source=source,
            correlation_run_id=self.correlation.run_id,
        )
        self._save_entry(entry)

        emit_event("memory.pending_created", "memory", self.correlation,
                   payload={"entry_id": entry.id, "category": category, "source": source})

        return entry

    def promote(self, entry_id: str, promoted_by: str = "human") -> MemoryEntry:
        """Promote a pending entry to durable memory."""
        entry = self._load_entry(entry_id, MemoryStatus.PENDING)
        if entry is None:
            raise ValueError(f"No pending entry found with id: {entry_id}")

        entry.status = MemoryStatus.PROMOTED
        entry.promoted_at = datetime.now(timezone.utc).isoformat()
        entry.promoted_by = promoted_by

        # Move from pending to promoted
        self._delete_entry(entry_id, MemoryStatus.PENDING)
        self._save_entry(entry)

        # Recompile MEMORY.md
        self._compile_memory_md()

        emit_event("memory.promoted", "memory", self.correlation,
                   payload={"entry_id": entry_id, "promoted_by": promoted_by})

        return entry

    def reject(self, entry_id: str, rejected_by: str = "human",
               reason: str = "") -> MemoryEntry:
        """Reject a pending entry."""
        entry = self._load_entry(entry_id, MemoryStatus.PENDING)
        if entry is None:
            raise ValueError(f"No pending entry found with id: {entry_id}")

        entry.status = MemoryStatus.REJECTED
        entry.rejected_at = datetime.now(timezone.utc).isoformat()
        entry.rejected_by = rejected_by
        entry.rejection_reason = reason

        self._delete_entry(entry_id, MemoryStatus.PENDING)
        self._save_entry(entry)

        emit_event("memory.rejected", "memory", self.correlation,
                   payload={"entry_id": entry_id, "rejected_by": rejected_by, "reason": reason})

        return entry

    def list_pending(self) -> list[MemoryEntry]:
        """List all pending memory entries."""
        return self._list_entries(MemoryStatus.PENDING)

    def list_promoted(self) -> list[MemoryEntry]:
        """List all promoted memory entries."""
        return self._list_entries(MemoryStatus.PROMOTED)

    def ingest_compaction_flush(self, flush_content: str) -> list[MemoryEntry]:
        """
        Parse a compaction flush (from OpenClaw's memoryFlush) and create
        pending entries for each rule/correction/learning found.
        """
        entries = []
        for line in flush_content.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            category = "observation"
            if line.upper().startswith("RULE:"):
                category = "rule"
                line = line[5:].strip()
            elif line.upper().startswith("CORRECTION:"):
                category = "correction"
                line = line[11:].strip()
            elif line.upper().startswith("LEARNED:"):
                category = "learned"
                line = line[8:].strip()

            if line:
                entries.append(self.submit(line, category=category, source="compaction_flush"))

        return entries

    def _compile_memory_md(self) -> None:
        """Recompile MEMORY.md from all promoted entries."""
        entries = self.list_promoted()

        header = (
            "# Durable Memory\n\n"
            "<!-- Auto-compiled by ContextForge MemoryManager -->\n"
            f"<!-- Last compiled: {datetime.now(timezone.utc).isoformat()} -->\n"
            f"<!-- Entries: {len(entries)} -->\n\n"
        )

        sections: dict[str, list[str]] = {}
        for e in entries:
            cat = e.category.title()
            if cat not in sections:
                sections[cat] = []
            sections[cat].append(f"- {e.content} *(promoted {e.promoted_at}, by {e.promoted_by})*")

        body = ""
        for cat in sorted(sections.keys()):
            body += f"## {cat}s\n\n"
            body += "\n".join(sections[cat]) + "\n\n"

        with open(self.memory_md, "w", encoding="utf-8") as f:
            f.write(header + body)

    # ── Storage helpers ─────────────────────────────────────────────────

    def _dir_for_status(self, status: MemoryStatus) -> Path:
        return {
            MemoryStatus.PENDING: self.pending_dir,
            MemoryStatus.PROMOTED: self.promoted_dir,
            MemoryStatus.REJECTED: self.rejected_dir,
        }[status]

    def _save_entry(self, entry: MemoryEntry) -> None:
        d = self._dir_for_status(entry.status)
        with open(d / f"{entry.id}.json", "w", encoding="utf-8") as f:
            json.dump(entry.to_dict(), f, indent=2)

    def _load_entry(self, entry_id: str, status: MemoryStatus) -> Optional[MemoryEntry]:
        path = self._dir_for_status(status) / f"{entry_id}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return MemoryEntry.from_dict(json.load(f))

    def _delete_entry(self, entry_id: str, status: MemoryStatus) -> None:
        path = self._dir_for_status(status) / f"{entry_id}.json"
        if path.exists():
            path.unlink()

    def _list_entries(self, status: MemoryStatus) -> list[MemoryEntry]:
        d = self._dir_for_status(status)
        entries = []
        for f in sorted(d.glob("*.json")):
            try:
                with open(f) as fh:
                    entries.append(MemoryEntry.from_dict(json.load(fh)))
            except (json.JSONDecodeError, KeyError):
                pass
        return entries
