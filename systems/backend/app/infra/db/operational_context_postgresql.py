"""PostgreSQL-backed, scope-bound operational context snapshot reader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.infra.db.postgresql_compat import postgres_repository_connection
from app.operations.operational_context_contract import (
    FreshnessMetadata,
    FreshnessState,
    OperationalContextEnvelope,
    OperationalContextStatus,
    OperationalRequestIdentity,
    OperationalScope,
    classify_freshness,
)


@dataclass(frozen=True)
class PostgreSQLOperationalContextReadPort:
    """Read only versioned context explicitly connected to one asset and time."""

    database_url: str
    owner_domain: str
    freshness_policy_version: str
    max_age_seconds: int

    def lookup(
        self,
        *,
        identity: OperationalRequestIdentity,
        retrieved_at: datetime,
    ) -> OperationalContextEnvelope:
        with postgres_repository_connection(
            self.database_url,
            organization_id=identity.organization_id,
            project_id=identity.project_id,
        ) as connection:
            row = connection.execute(
                """
                SELECT source_version, source_updated_at, source_ref, payload_json
                FROM operational_context_snapshots
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
                    identity.decision_as_of,
                    identity.decision_as_of,
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
                    "No scope-bound operational snapshot is connected for this domain.",
                ),
            )

        source_updated_at = row["source_updated_at"]
        if isinstance(source_updated_at, str):
            source_updated_at = datetime.fromisoformat(
                source_updated_at.replace("Z", "+00:00")
            )
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
            payload = row["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            if not isinstance(payload, dict):
                raise ValueError("operational context payload must be an object")
            data = payload
        else:
            limitations = (
                "Operational snapshot exceeded the configured freshness policy; values withheld.",
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
