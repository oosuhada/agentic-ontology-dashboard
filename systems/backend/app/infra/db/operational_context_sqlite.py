"""SQLite-backed read-only operational context snapshot adapter."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.operations.operational_context_contract import (
    FreshnessMetadata,
    FreshnessState,
    OperationalContextEnvelope,
    OperationalContextStatus,
    OperationalRequestIdentity,
    OperationalScope,
    classify_freshness,
)


DataValidator = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class SqliteOperationalContextReadPort:
    """Read one owner-domain snapshot through a scope-bound, read-only query."""

    database_path: Path
    owner_domain: str
    freshness_policy_version: str
    max_age_seconds: int
    data_validator: DataValidator | None = None

    def lookup(
        self,
        *,
        identity: OperationalRequestIdentity,
        retrieved_at: datetime,
    ) -> OperationalContextEnvelope:
        uri = f"file:{self.database_path}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT source_version, source_updated_at, source_ref, payload_json
                FROM operational_context_snapshot
                WHERE owner_domain = ?
                  AND organization_id = ?
                  AND project_id = ?
                  AND workspace_id = ?
                  AND asset_id = ?
                  AND valid_from <= ?
                  AND valid_to > ?
                ORDER BY source_updated_at DESC, source_version DESC
                LIMIT 1
                """,
                (
                    self.owner_domain,
                    identity.organization_id,
                    identity.project_id,
                    identity.workspace_id,
                    identity.asset_id,
                    identity.decision_as_of.isoformat(),
                    identity.decision_as_of.isoformat(),
                ),
            ).fetchone()

        scope = OperationalScope(
            organization_id=identity.organization_id,
            project_id=identity.project_id,
            workspace_id=identity.workspace_id,
            asset_id=identity.asset_id,
        )
        if row is None:
            return OperationalContextEnvelope(
                owner_domain=self.owner_domain,
                scope=scope,
                status=OperationalContextStatus.NOT_CONNECTED,
                retrieved_at=retrieved_at,
                as_of=identity.decision_as_of,
                freshness=FreshnessMetadata(
                    policy_version=self.freshness_policy_version,
                    max_age_seconds=self.max_age_seconds,
                    state=FreshnessState.UNKNOWN,
                ),
                limitations=(
                    "No scope-bound versioned snapshot is connected for this domain.",
                ),
            )

        source_updated_at = datetime.fromisoformat(row["source_updated_at"])
        freshness = classify_freshness(
            source_updated_at=source_updated_at,
            retrieved_at=retrieved_at,
            max_age_seconds=self.max_age_seconds,
        )
        status = (
            OperationalContextStatus.AVAILABLE
            if freshness is FreshnessState.FRESH
            else OperationalContextStatus.STALE
        )
        data: dict[str, Any] = {}
        limitations: tuple[str, ...] = ()
        if status is OperationalContextStatus.AVAILABLE:
            raw = json.loads(row["payload_json"])
            if not isinstance(raw, dict):
                raise ValueError("operational context payload must be an object")
            data = self.data_validator(raw) if self.data_validator else raw
        else:
            limitations = (
                "Snapshot exceeded the configured freshness policy; values withheld.",
            )

        return OperationalContextEnvelope(
            owner_domain=self.owner_domain,
            scope=scope,
            status=status,
            source_version=str(row["source_version"]),
            source_updated_at=source_updated_at,
            retrieved_at=retrieved_at,
            as_of=identity.decision_as_of,
            freshness=FreshnessMetadata(
                policy_version=self.freshness_policy_version,
                max_age_seconds=self.max_age_seconds,
                state=freshness,
            ),
            source_refs=(str(row["source_ref"]),),
            data=data,
            limitations=limitations,
        )


OPERATIONAL_CONTEXT_SNAPSHOT_DDL = """
CREATE TABLE operational_context_snapshot (
    owner_domain TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_updated_at TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (
        owner_domain,
        organization_id,
        project_id,
        workspace_id,
        asset_id,
        source_version
    )
);

CREATE INDEX operational_context_snapshot_lookup_idx
ON operational_context_snapshot (
    owner_domain,
    organization_id,
    project_id,
    workspace_id,
    asset_id,
    valid_from,
    valid_to,
    source_updated_at
);
"""
