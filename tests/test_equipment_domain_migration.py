from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.equipment import (
    EquipmentCurrentStateQuery,
    EquipmentNotFoundError,
    EquipmentService,
    EquipmentStatePatchPort,
    EquipmentStateVersionConflictError,
    InvalidEquipmentStatePatchError,
    apply_state_patch,
    next_state_version,
)
from app.equipment.adapters import FixtureEquipmentRepository
from app.equipment.equipment_router import register_equipment_routes


RESET_TOOL_WEAR = {
    "tool_wear_min": {"operation": "reset", "value": 0, "unit": "min"}
}


def _service() -> EquipmentService:
    repository = FixtureEquipmentRepository(
        [
            ("project-a", {"equipment_id": "EQ-002", "display_name": "Second"}),
            ("project-a", {"equipment_id": "EQ-001", "display_name": "First old"}),
            (
                "project-a",
                {
                    "equipment_id": "EQ-001",
                    "display_name": "First",
                    "criticality": "high",
                },
            ),
            ("project-b", {"equipment_id": "EQ-001", "display_name": "Other project"}),
            (
                "manufacturing-demo-project",
                {"equipment_id": "EQ-001", "display_name": "First"},
            ),
            (
                "manufacturing-demo-project",
                {"equipment_id": "EQ-002", "display_name": "Second"},
            ),
        ]
    )
    return EquipmentService(repository)


def test_equipment_master_is_deduplicated_sorted_and_project_scoped() -> None:
    service = _service()

    rows = service.list_equipment("project-a")

    assert [row["equipment_id"] for row in rows] == ["EQ-001", "EQ-002"]
    assert rows[0]["display_name"] == "First"
    assert service.equipment("EQ-001", "project-b")["display_name"] == "Other project"
    with pytest.raises(EquipmentNotFoundError):
        service.equipment("UNKNOWN", "project-a")


def test_equipment_public_facade_exposes_service_and_ports() -> None:
    service = _service()
    query_port: EquipmentCurrentStateQuery = service
    patch_port: EquipmentStatePatchPort = service

    assert query_port.equipment_current_state("EQ-001", "project-a") is None
    assert patch_port.patch_equipment_state(
        "EQ-001",
        project_id="project-a",
        expected_state_version=None,
        state_patch=RESET_TOOL_WEAR,
    )["state_version"] == 1


def test_equipment_domain_exceptions_do_not_alias_builtin_lookup_or_validation_errors() -> None:
    assert not issubclass(EquipmentNotFoundError, KeyError)
    assert not issubclass(InvalidEquipmentStatePatchError, ValueError)


def test_equipment_state_patch_stores_state_not_command_syntax() -> None:
    service = _service()
    assert service.equipment_current_state("EQ-001", "project-a") is None

    first = service.patch_equipment_state(
        "EQ-001",
        project_id="project-a",
        expected_state_version=None,
        state_patch=RESET_TOOL_WEAR,
    )

    assert first == {
        "equipment_id": "EQ-001",
        "state_version": 1,
        "state": {"tool_wear_min": {"value": 0, "unit": "min"}},
    }
    assert "operation" not in first["state"]["tool_wear_min"]


def test_equipment_state_version_requires_exact_optimistic_match() -> None:
    service = _service()
    service.patch_equipment_state(
        "EQ-001",
        project_id="project-a",
        expected_state_version=None,
        state_patch=RESET_TOOL_WEAR,
    )
    second = service.patch_equipment_state(
        "EQ-001",
        project_id="project-a",
        expected_state_version=1,
        state_patch=RESET_TOOL_WEAR,
    )
    assert second["state_version"] == 2

    with pytest.raises(EquipmentStateVersionConflictError) as exc_info:
        service.patch_equipment_state(
            "EQ-001",
            project_id="project-a",
            expected_state_version=1,
            state_patch=RESET_TOOL_WEAR,
        )
    assert exc_info.value.expected == 1
    assert exc_info.value.actual == 2


def test_equipment_repository_compare_and_set_serializes_concurrent_writers() -> None:
    service = _service()
    service.patch_equipment_state(
        "EQ-001",
        project_id="project-a",
        expected_state_version=None,
        state_patch=RESET_TOOL_WEAR,
    )

    def attempt_patch() -> str:
        try:
            result = service.patch_equipment_state(
                "EQ-001",
                project_id="project-a",
                expected_state_version=1,
                state_patch=RESET_TOOL_WEAR,
            )
        except EquipmentStateVersionConflictError:
            return "conflict"
        return f"ok:{result['state_version']}"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(lambda _: attempt_patch(), range(2)))

    assert results == ["conflict", "ok:2"]
    assert service.equipment_current_state("EQ-001", "project-a")["state_version"] == 2


def test_equipment_patch_and_version_invariants_reject_invalid_inputs() -> None:
    assert next_state_version(None) == 1
    assert next_state_version(1) == 2
    with pytest.raises(ValueError, match="positive"):
        next_state_version(0)

    with pytest.raises(InvalidEquipmentStatePatchError):
        apply_state_patch(
            {},
            {"tool_wear_min": {"operation": "reset", "value": 1, "unit": "min"}},
        )
    with pytest.raises(InvalidEquipmentStatePatchError):
        apply_state_patch({}, {**RESET_TOOL_WEAR, "unexpected": True})


def test_equipment_router_preserves_existing_read_contract() -> None:
    service = _service()
    app = FastAPI()
    router = APIRouter(prefix="/api")

    register_equipment_routes(
        router,
        service_dependency=lambda: service,
        authorization_dependency=lambda: object(),
    )
    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/api/equipment")
        assert response.status_code == 200
        assert [item["equipment_id"] for item in response.json()["items"]] == [
            "EQ-001",
            "EQ-002",
        ]

        detail = client.get("/api/equipment/EQ-001")
        assert detail.status_code == 200
        assert detail.json()["display_name"] == "First"

        missing = client.get("/api/equipment/UNKNOWN")
        assert missing.status_code == 404
        assert missing.json() == {
            "error": {
                "code": "not_found",
                "message": "resource not found: UNKNOWN",
            }
        }
