from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.operations.operational_context_contract import (
    FreshnessMetadata,
    FreshnessState,
    OperationalContextEnvelope,
    OperationalContextStatus,
    OperationalRequestIdentity,
    OperationalScope,
    classify_freshness,
    context_version_set,
    context_version_set_hash,
    require_matching_scope,
)


NOW = datetime(2026, 9, 2, 10, 1, 3, tzinfo=timezone.utc)
UPDATED = datetime(2026, 9, 2, 10, 1, 0, tzinfo=timezone.utc)
AS_OF = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)


def identity() -> OperationalRequestIdentity:
    return OperationalRequestIdentity(
        organization_id="ORG-001",
        project_id="PROJECT-001",
        workspace_id="WORKSPACE-001",
        asset_id="CNC-02",
        evidence_snapshot_id="ARTIFACT-001",
        decision_as_of=AS_OF,
    )


def scope(**overrides: str) -> OperationalScope:
    values = {
        "organization_id": "ORG-001",
        "project_id": "PROJECT-001",
        "workspace_id": "WORKSPACE-001",
        "asset_id": "CNC-02",
    }
    values.update(overrides)
    return OperationalScope(**values)


def available(owner: str = "inventory", version: str = "inventory-42") -> OperationalContextEnvelope:
    return OperationalContextEnvelope(
        owner_domain=owner,
        scope=scope(),
        status=OperationalContextStatus.AVAILABLE,
        source_version=version,
        source_updated_at=UPDATED,
        retrieved_at=NOW,
        as_of=AS_OF,
        freshness=FreshnessMetadata(
            policy_version=f"{owner}-freshness-v1",
            max_age_seconds=60,
            state=FreshnessState.FRESH,
        ),
        source_refs=(f"{owner}:{version}",),
        data={"available_quantity": 1},
    )


def test_available_context_preserves_fixed_scope_and_version() -> None:
    result = available()

    require_matching_scope(identity(), result)

    assert result.scope.workspace_id == "WORKSPACE-001"
    assert result.source_version == "inventory-42"
    assert result.data == {"available_quantity": 1}


def test_scope_mismatch_fails_closed() -> None:
    result = available().model_copy(update={"scope": scope(workspace_id="OTHER")})

    with pytest.raises(ValueError, match="scope mismatch"):
        require_matching_scope(identity(), result)


def test_non_available_context_cannot_smuggle_domain_values() -> None:
    with pytest.raises(ValidationError, match="must not carry domain data"):
        OperationalContextEnvelope(
            owner_domain="inventory",
            scope=scope(),
            status=OperationalContextStatus.NOT_CONNECTED,
            retrieved_at=NOW,
            as_of=AS_OF,
            freshness=FreshnessMetadata(
                policy_version="inventory-freshness-v1",
                max_age_seconds=60,
                state=FreshnessState.UNKNOWN,
            ),
            data={"available_quantity": 0},
            limitations=("WMS connection is unavailable",),
        )


def test_available_context_requires_version_timestamp_and_fresh_state() -> None:
    with pytest.raises(ValidationError, match="requires source_version"):
        OperationalContextEnvelope(
            owner_domain="inventory",
            scope=scope(),
            status=OperationalContextStatus.AVAILABLE,
            retrieved_at=NOW,
            as_of=AS_OF,
            freshness=FreshnessMetadata(
                policy_version="inventory-freshness-v1",
                max_age_seconds=60,
                state=FreshnessState.FRESH,
            ),
        )


def test_stale_status_and_freshness_must_agree() -> None:
    payload = available().model_dump()
    payload["freshness"] = {
        "policy_version": "inventory-freshness-v1",
        "max_age_seconds": 1,
        "state": FreshnessState.STALE,
    }

    with pytest.raises(ValidationError, match="available context requires fresh"):
        OperationalContextEnvelope.model_validate(payload)


def test_freshness_is_deterministic_and_missing_time_remains_unknown() -> None:
    assert (
        classify_freshness(
            source_updated_at=UPDATED,
            retrieved_at=NOW,
            max_age_seconds=3,
        )
        is FreshnessState.FRESH
    )
    assert (
        classify_freshness(
            source_updated_at=UPDATED,
            retrieved_at=NOW,
            max_age_seconds=2,
        )
        is FreshnessState.STALE
    )
    assert (
        classify_freshness(
            source_updated_at=None,
            retrieved_at=NOW,
            max_age_seconds=60,
        )
        is FreshnessState.UNKNOWN
    )


def test_naive_or_future_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        classify_freshness(
            source_updated_at=None,
            retrieved_at=datetime(2026, 9, 2, 10, 1, 3),
            max_age_seconds=60,
        )

    with pytest.raises(ValueError, match="must not be after"):
        classify_freshness(
            source_updated_at=datetime(2026, 9, 2, 10, 2, tzinfo=timezone.utc),
            retrieved_at=NOW,
            max_age_seconds=60,
        )


def test_context_version_set_and_hash_are_order_independent() -> None:
    production = available("production", "plan-17")
    inventory = available("inventory", "inventory-43")
    missing = OperationalContextEnvelope(
        owner_domain="workforce",
        scope=scope(),
        status=OperationalContextStatus.NOT_CONNECTED,
        retrieved_at=NOW,
        as_of=AS_OF,
        freshness=FreshnessMetadata(
            policy_version="workforce-freshness-v1",
            max_age_seconds=60,
            state=FreshnessState.UNKNOWN,
        ),
        limitations=("workforce source is not connected",),
    )

    left = context_version_set(
        {"production": production, "inventory": inventory, "workforce": missing}
    )
    right = context_version_set(
        {"workforce": missing, "inventory": inventory, "production": production}
    )

    assert left == {"inventory": "inventory-43", "production": "plan-17"}
    assert context_version_set_hash(left) == context_version_set_hash(right)


def test_context_map_key_must_match_owner() -> None:
    with pytest.raises(ValueError, match="must match owner_domain"):
        context_version_set({"production": available("inventory", "inventory-43")})
