"""Runtime state snapshots returned by the control API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RunState:
    run_id: str
    status: str
    started_at: datetime
    current_observed_at: datetime
    source_kind: str = "simulation"
    simulation_session_id: str | None = None
    last_sequence: int = 0
    completed_at: datetime | None = None
    source_record_count: int = 0
    protocol_datavalue_count: int = 0
    canonical_observation_count: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "source_kind": self.source_kind,
            "simulation_session_id": self.simulation_session_id,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "current_observed_at": self.current_observed_at.isoformat(timespec="seconds"),
            "last_sequence": self.last_sequence,
            "completed_at": (
                self.completed_at.isoformat(timespec="seconds") if self.completed_at else None
            ),
            "source_record_count": self.source_record_count,
            "protocol_datavalue_count": self.protocol_datavalue_count,
            "canonical_observation_count": self.canonical_observation_count,
            "partial_failure_count": len(self.failures),
        }
