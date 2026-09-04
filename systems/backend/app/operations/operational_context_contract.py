"""Contracts for versioned read-only operational context.

These types keep request identity outside LLM/tool selection and make dynamic
context freshness explicit before later runtime domain ports are introduced.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OperationalContextStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_CONNECTED = "not_connected"
    STALE = "stale"
    UNAUTHORIZED = "unauthorized"
    FAILED = "failed"


class FreshnessState(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class OperationalRequestIdentity(FrozenModel):
    """Application-fixed identity that an agent or tool must not alter."""

    organization_id: str = Field(min_length=1, max_length=160)
    project_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)
    asset_id: str = Field(min_length=1, max_length=240)
    evidence_snapshot_id: str = Field(min_length=1, max_length=240)
    decision_as_of: datetime

    @model_validator(mode="after")
    def require_timezone(self) -> OperationalRequestIdentity:
        _require_aware(self.decision_as_of, "decision_as_of")
        return self


class OperationalScope(FrozenModel):
    organization_id: str = Field(min_length=1, max_length=160)
    project_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)
    asset_id: str = Field(min_length=1, max_length=240)


class FreshnessMetadata(FrozenModel):
    policy_version: str = Field(min_length=1, max_length=160)
    max_age_seconds: int = Field(ge=0)
    state: FreshnessState


class OperationalContextEnvelope(FrozenModel):
    """Bounded result returned by a read-only operational domain port."""

    owner_domain: str = Field(min_length=1, max_length=120)
    scope: OperationalScope
    status: OperationalContextStatus
    source_version: str | None = Field(default=None, max_length=240)
    source_updated_at: datetime | None = None
    retrieved_at: datetime
    as_of: datetime
    freshness: FreshnessMetadata
    source_refs: tuple[str, ...] = ()
    data: dict[str, Any] = Field(default_factory=dict)
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_envelope(self) -> OperationalContextEnvelope:
        _require_aware(self.retrieved_at, "retrieved_at")
        _require_aware(self.as_of, "as_of")
        if self.source_updated_at is not None:
            _require_aware(self.source_updated_at, "source_updated_at")
            if self.source_updated_at > self.retrieved_at:
                raise ValueError("source_updated_at must not be after retrieved_at")

        if self.status is OperationalContextStatus.AVAILABLE:
            if not self.source_version or self.source_updated_at is None:
                raise ValueError(
                    "available context requires source_version and source_updated_at"
                )
            if self.freshness.state is not FreshnessState.FRESH:
                raise ValueError("available context requires fresh freshness state")
        elif self.data:
            raise ValueError("non-available context must not carry domain data")

        if self.status is OperationalContextStatus.STALE:
            if self.freshness.state is not FreshnessState.STALE:
                raise ValueError("stale context requires stale freshness state")
        elif self.freshness.state is FreshnessState.STALE:
            raise ValueError("stale freshness requires stale context status")

        if any(not reference.strip() for reference in self.source_refs):
            raise ValueError("source_refs must not contain empty values")
        if any(not limitation.strip() for limitation in self.limitations):
            raise ValueError("limitations must not contain empty values")
        return self


def classify_freshness(
    *,
    source_updated_at: datetime | None,
    retrieved_at: datetime,
    max_age_seconds: int,
) -> FreshnessState:
    """Classify source freshness without inventing a value for missing metadata."""

    _require_aware(retrieved_at, "retrieved_at")
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    if source_updated_at is None:
        return FreshnessState.UNKNOWN

    _require_aware(source_updated_at, "source_updated_at")
    if source_updated_at > retrieved_at:
        raise ValueError("source_updated_at must not be after retrieved_at")
    age = retrieved_at - source_updated_at
    return (
        FreshnessState.FRESH
        if age <= timedelta(seconds=max_age_seconds)
        else FreshnessState.STALE
    )


def require_matching_scope(
    identity: OperationalRequestIdentity,
    envelope: OperationalContextEnvelope,
) -> None:
    """Reject cross-organization/project/workspace/asset tool results."""

    expected = (
        identity.organization_id,
        identity.project_id,
        identity.workspace_id,
        identity.asset_id,
    )
    actual = (
        envelope.scope.organization_id,
        envelope.scope.project_id,
        envelope.scope.workspace_id,
        envelope.scope.asset_id,
    )
    if actual != expected:
        raise ValueError("operational context scope mismatch")


def context_version_set(
    envelopes: Mapping[str, OperationalContextEnvelope],
) -> dict[str, str]:
    """Return stable owner-domain versions for reusable summary keys."""

    versions: dict[str, str] = {}
    for key, envelope in sorted(envelopes.items()):
        if key != envelope.owner_domain:
            raise ValueError("context map key must match owner_domain")
        if envelope.status is not OperationalContextStatus.AVAILABLE:
            continue
        if envelope.owner_domain in versions:
            raise ValueError("duplicate operational context owner_domain")
        assert envelope.source_version is not None
        versions[envelope.owner_domain] = envelope.source_version
    return versions


def context_version_set_hash(versions: Mapping[str, str]) -> str:
    canonical = json.dumps(
        dict(sorted(versions.items())),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    # Reject pathological tzinfo implementations with a non-stable UTC conversion.
    value.astimezone(timezone.utc)
