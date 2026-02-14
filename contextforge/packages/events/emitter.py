"""Event emitter — writes structured events to JSONL log and optional callbacks."""
from __future__ import annotations
import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from .models import Event, CorrelationIDs

# Default log location
DEFAULT_LOG_PATH = os.environ.get(
    "CONTEXTFORGE_EVENT_LOG",
    str(Path(__file__).resolve().parents[3] / "ai" / "supervisor" / "contextforge_events.jsonl"),
)


def new_run_id() -> str:
    return str(uuid.uuid4())


def new_trace_id() -> str:
    return str(uuid.uuid4())


class EventEmitter:
    """Emits structured events to JSONL file and optional listeners."""

    def __init__(self, log_path: Optional[str] = None):
        self.log_path = Path(log_path or DEFAULT_LOG_PATH)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._listeners: list[Callable[[Event], None]] = []

    def add_listener(self, fn: Callable[[Event], None]) -> None:
        self._listeners.append(fn)

    def emit(
        self,
        event_type: str,
        component: str,
        correlation: CorrelationIDs,
        payload: Optional[dict[str, Any]] = None,
        severity: str = "info",
        agent_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error: Optional[dict] = None,
    ) -> Event:
        event = Event(
            event_type=event_type,
            component=component,
            correlation=correlation,
            payload=payload or {},
            severity=severity,
            agent_id=agent_id,
            duration_ms=duration_ms,
            error=error,
        )
        # Write to JSONL
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

        # Notify listeners
        for fn in self._listeners:
            try:
                fn(event)
            except Exception:
                pass  # listeners must not break the emitter

        return event


# Module-level singleton
_default_emitter: Optional[EventEmitter] = None


def get_emitter() -> EventEmitter:
    global _default_emitter
    if _default_emitter is None:
        _default_emitter = EventEmitter()
    return _default_emitter


def emit_event(
    event_type: str,
    component: str,
    correlation: CorrelationIDs,
    **kwargs,
) -> Event:
    """Convenience function using the default emitter."""
    return get_emitter().emit(event_type, component, correlation, **kwargs)
