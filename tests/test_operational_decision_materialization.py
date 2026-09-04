from datetime import timedelta

import pytest

from app.operations.operational_decision_brief import (
    DecisionBriefRole,
    compose_operational_decision_brief,
)
from app.operations.operational_decision_materialization import (
    create_decision_handoff_package,
    materialize_operational_brief,
)
from app.operations.operational_impact_simulation import ImpactOption
from test_operational_decision_brief import RETRIEVED_AT, run_for_role


def completed_result():
    request, result = run_for_role(DecisionBriefRole.PROCESS_MANAGER, ready=True)
    brief = compose_operational_decision_brief(request=request, result=result)
    return request, result, brief


def test_materialization_is_deterministic_and_version_keyed() -> None:
    request, result, brief = completed_result()
    first = materialize_operational_brief(
        request=request,
        result=result,
        brief=brief,
        stored_at=RETRIEVED_AT + timedelta(seconds=4),
    )
    second = materialize_operational_brief(
        request=request,
        result=result,
        brief=brief,
        stored_at=RETRIEVED_AT + timedelta(seconds=8),
    )

    assert first.snapshot_id == second.snapshot_id
    assert first.context_version_hash == result.context_version_hash
    assert first.context_version_set == result.context_version_set
    assert first.brief.recommendation is None


def test_materialization_rejects_failed_temporal_revalidation() -> None:
    request, result, brief = completed_result()
    invalid = result.model_copy(
        update={
            "temporal_validation": {
                "valid": False,
                "mismatches": [{"domain": "production"}],
            }
        }
    )

    with pytest.raises(ValueError, match="temporal validation"):
        materialize_operational_brief(
            request=request,
            result=invalid,
            brief=brief,
            stored_at=RETRIEVED_AT + timedelta(seconds=4),
        )


def test_handoff_requires_human_selection_and_creates_no_command() -> None:
    request, result, brief = completed_result()
    snapshot = materialize_operational_brief(
        request=request,
        result=result,
        brief=brief,
        stored_at=RETRIEVED_AT + timedelta(seconds=4),
    )
    handoff = create_decision_handoff_package(
        request=request,
        result=result,
        brief_snapshot=snapshot,
        selected_option=ImpactOption.PLANNED_MAINTENANCE,
        selected_by="USER-001",
        selected_at=RETRIEVED_AT + timedelta(minutes=5),
    )

    assert handoff.selected_by == "USER-001"
    assert handoff.selected_option is ImpactOption.PLANNED_MAINTENANCE
    assert handoff.command_created is False
    assert handoff.context_version_set == result.context_version_set
    assert handoff.simulation_result_id.startswith("OSIM-")


def test_handoff_rejects_tampered_context_version_hash() -> None:
    request, result, brief = completed_result()
    snapshot = materialize_operational_brief(
        request=request,
        result=result,
        brief=brief,
        stored_at=RETRIEVED_AT + timedelta(seconds=4),
    ).model_copy(update={"context_version_hash": "tampered"})

    with pytest.raises(ValueError, match="version hash mismatch"):
        create_decision_handoff_package(
            request=request,
            result=result,
            brief_snapshot=snapshot,
            selected_option=ImpactOption.STOP_NOW,
            selected_by="USER-001",
            selected_at=RETRIEVED_AT + timedelta(minutes=5),
        )
