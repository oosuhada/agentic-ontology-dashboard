from __future__ import annotations

from pathlib import Path

import pytest

from ontology_dashboard.migrations import migrate
from ontology_dashboard.ontology_primitives import (
    ActionPreviewRequest,
    FunctionExecutionRequest,
    OntologyPrimitiveRepository,
)


ORG = "org-ontology-demo"
PROJECT = "manufacturing-demo-project"
ACTOR = "user-manager"


def repository(tmp_path: Path) -> OntologyPrimitiveRepository:
    database = tmp_path / "phase27.db"
    migrate(str(database))
    result = OntologyPrimitiveRepository(database)
    result.ensure_samples(ORG, PROJECT, ACTOR)
    return result


def test_asset_interface_is_domain_neutral_and_implemented_by_two_object_types(tmp_path: Path) -> None:
    snapshot = repository(tmp_path).snapshot(ORG, PROJECT)
    asset = next(item for item in snapshot.interfaces if item.id == "asset")
    assert asset.status == "published"
    assert asset.property_contract == {
        "asset_id": "str",
        "display_name": "str",
        "risk_score": "float",
    }
    assert {item["object_type_id"] for item in asset.implementations} == {
        "equipment",
        "compressor",
    }


def test_action_preview_uses_registry_schema_for_positive_and_negative_validation(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    valid = repo.preview_action(
        ORG,
        PROJECT,
        ActionPreviewRequest(
            action_id="request-asset-inspection",
            object_ids=("equipment:M-001", "compressor:C-01"),
            parameters={"priority": "high", "due_date": "2026-08-10"},
            reason="High risk assets require review",
        ),
        ACTOR,
    )
    assert valid.valid is True
    assert valid.target_count == 2
    assert valid.approval_required is True

    invalid = repo.preview_action(
        ORG,
        PROJECT,
        ActionPreviewRequest(
            action_id="request-asset-inspection",
            object_ids=("equipment:M-001",),
            parameters={"priority": "urgent"},
            reason="Validate generated form parity",
        ),
        ACTOR,
    )
    assert invalid.valid is False
    assert set(invalid.validation_errors) == {"missing:due_date", "enum:priority"}


def test_governed_function_is_deterministic_and_rejects_schema_mismatch(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    request = FunctionExecutionRequest(
        function_id="asset-risk-metric",
        inputs={"failure_probability": 0.8, "criticality": 1.0},
    )
    first = repo.execute_function(ORG, PROJECT, request, ACTOR)
    second = repo.execute_function(ORG, PROJECT, request, ACTOR)
    assert first.output == second.output == {"risk_score": 0.8, "band": "high"}
    assert first.runtime_checksum == second.runtime_checksum

    with pytest.raises(ValueError, match="input schema mismatch"):
        repo.execute_function(
            ORG,
            PROJECT,
            FunctionExecutionRequest(
                function_id="asset-risk-metric",
                inputs={"failure_probability": 0.8, "criticality": 1.0, "code": "print(1)"},
            ),
            ACTOR,
        )


def test_repository_is_project_scoped(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    repo.ensure_samples(ORG, "other-project", ACTOR)
    assert repo.snapshot(ORG, PROJECT).interfaces
    assert repo.snapshot(ORG, "other-project").interfaces
    assert all(
        item.id == "asset" for item in repo.snapshot(ORG, "other-project").interfaces
    )

