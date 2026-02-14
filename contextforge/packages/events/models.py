"""Event data models."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional
import uuid


@dataclass
class CorrelationIDs:
    """Correlation IDs for end-to-end traceability."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: Optional[str] = None
    parent_id: Optional[str] = None
    change_id: Optional[str] = None
    artifact_id: Optional[str] = None

    def child(self, artifact_id: Optional[str] = None) -> "CorrelationIDs":
        """Create a child correlation with a new trace_id."""
        return CorrelationIDs(
            run_id=self.run_id,
            trace_id=str(uuid.uuid4()),
            parent_id=self.trace_id or self.run_id,
            change_id=self.change_id,
            artifact_id=artifact_id or self.artifact_id,
        )

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Event:
    """A single structured event."""
    event_type: str
    component: str
    correlation: CorrelationIDs
    payload: dict[str, Any] = field(default_factory=dict)
    severity: str = "info"
    agent_id: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[dict] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        d = {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "correlation": self.correlation.to_dict(),
            "component": self.component,
            "severity": self.severity,
            "payload": self.payload,
        }
        if self.agent_id:
            d["agent_id"] = self.agent_id
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        if self.error:
            d["error"] = self.error
        return d
