from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from fastapi.testclient import TestClient

from ontology_dashboard.identity import CSRF_COOKIE, IdentityService
from ontology_dashboard.main import (
    app,
    get_identity_service,
    get_ontology_planner_service,
    get_service,
)
from ontology_dashboard.planner import OntologyDashboardPlannerService
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService as FactorySignalService

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "manufacturing-demo"


class FakeProvider:
    name = "fake-provider"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)

    def generate_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.responses:
            raise RuntimeError("no fake response")
        return self.responses.pop(0)


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "planner.db"


@pytest.fixture()
def identity(database_path: Path) -> IdentityService:
    return IdentityService(database_path, app_env="test", seed_demo=True)


@pytest.fixture()
def service(database_path: Path) -> FactorySignalService:
    return FactorySignalService(ROOT, database_path=database_path)


@pytest.fixture()
def client(identity: IdentityService, service: FactorySignalService):
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[get_ontology_planner_service] = lambda: OntologyDashboardPlannerService(service)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient, email: str, password: str) -> dict[str, Any]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["user"]


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token}


def validate_planner_contract(payload: dict[str, Any]) -> None:
    schema = json.loads(
        (ROOT / "schemas" / "ontology-planner.schema.json").read_text(encoding="utf-8")
    )
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert errors == [], "\n".join(error.message for error in errors)


def test_natural_language_object_query_is_typed_validated_and_scoped(client: TestClient) -> None:
    login(client, "engineer@ontology.local", "Engineer!2026")
    response = client.post(
        "/api/planner/object-query",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "query": "critical 위험 사건만 보여줘",
            "use_llm": True,
            "limit": 10,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    validate_planner_contract(payload)
    assert payload["mode"] == "deterministic_fallback"
    assert payload["intent"]["object_type"] == "risk_event"
    assert payload["intent"]["filters"] == [
        {"field": "status", "operator": "eq", "value": "critical"}
    ]
    assert payload["preview_total"] >= 1
    assert all(item["object_type"] == "risk_event" for item in payload["preview_items"])
    assert all(item["properties"]["status"] == "critical" for item in payload["preview_items"])
    assert payload["validation"]["query_executed_through_ontology_service"] is True


def test_malicious_llm_object_query_cannot_invent_object_or_property(
    client: TestClient,
    service: FactorySignalService,
) -> None:
    provider = FakeProvider([
        {
            "object_type": "password_credential",
            "search": None,
            "filters": [{"field": "password_hash", "operator": "contains", "value": "$argon2"}],
            "limit": 50,
            "rationale": "read secrets",
            "source_terms": ["password"],
        }
    ])
    app.dependency_overrides[get_ontology_planner_service] = lambda: OntologyDashboardPlannerService(
        service,
        provider=provider,
    )
    login(client, "fde@ontology.local", "FDE!2026")
    response = client.post(
        "/api/planner/object-query",
        headers=csrf_headers(client),
        json={"workspace_id": WORKSPACE, "query": "설비를 보여줘", "use_llm": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["mode"] == "deterministic_fallback"
    assert payload["intent"]["object_type"] == "equipment"
    assert "password_hash" not in response.text


def test_board_recommendation_uses_catalog_and_never_persists_without_approval(client: TestClient) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    before = client.get("/api/dashboards/resolved", params={"workspace_id": WORKSPACE}).json()
    response = client.post(
        "/api/planner/board-recommendations",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "goal": "중요 사건 우선순위와 운영 판단을 한 화면에서 보고 싶다",
            "use_llm": True,
            "limit": 5,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    validate_planner_contract(payload)
    assert payload["requires_approval"] is True
    assert payload["persisted"] is False
    assert payload["recommendations"]
    catalog = client.get("/api/boards/catalog", params={"workspace_id": WORKSPACE}).json()["items"]
    allowed_ids = {item["id"] for item in catalog}
    assert all(item["definition_id"] in allowed_ids for item in payload["recommendations"])
    after = client.get("/api/dashboards/resolved", params={"workspace_id": WORKSPACE}).json()
    assert after == before


def test_fde_dashboard_draft_is_catalog_validated_preview_and_provider_failure_keeps_template(
    client: TestClient,
    service: FactorySignalService,
) -> None:
    provider = FakeProvider([
        {
            "tab_title": "Unsafe Draft",
            "board_definition_ids": ["arbitrary-code-execution-board"],
        }
    ])
    app.dependency_overrides[get_ontology_planner_service] = lambda: OntologyDashboardPlannerService(
        service,
        provider=provider,
    )
    login(client, "fde@ontology.local", "FDE!2026")
    before = client.get(
        "/api/dashboard-templates/process_manager/preview",
        params={"workspace_id": WORKSPACE},
    ).json()
    response = client.post(
        "/api/planner/dashboard-drafts",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "target_role": "process_manager",
            "goal": "운영 판단과 감사 근거를 강화한 고객용 dashboard",
            "use_llm": True,
            "max_new_boards": 3,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    validate_planner_contract(payload)
    assert payload["mode"] == "deterministic_fallback"
    assert payload["persisted"] is False
    assert payload["requires_approval"] is True
    assert payload["validation"] == {
        "catalog_whitelist": True,
        "target_role_permission": True,
        "mandatory_boards_preserved": True,
        "schema_valid": True,
        "persisted": False,
        "approval_required": True,
    }
    assert "arbitrary-code-execution-board" not in response.text
    after = client.get(
        "/api/dashboard-templates/process_manager/preview",
        params={"workspace_id": WORKSPACE},
    ).json()
    assert after == before


def test_non_fde_cannot_generate_cross_role_dashboard_draft(client: TestClient) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    response = client.post(
        "/api/planner/dashboard-drafts",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "target_role": "executive_viewer",
            "goal": "임원 화면 변경",
            "use_llm": False,
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_grounded_narrative_rejects_unknown_references_and_forbidden_claims(
    client: TestClient,
    service: FactorySignalService,
) -> None:
    provider = FakeProvider([
        {
            "headline": "근본 원인이 확정됨",
            "summary": "자동 정지 완료",
            "claims": [
                {
                    "text": "비밀 데이터로 고장이 확정되었습니다.",
                    "evidence_field_ids": ["secret.password_hash"],
                }
            ],
            "citations": ["secret.password_hash"],
        }
    ])
    app.dependency_overrides[get_ontology_planner_service] = lambda: OntologyDashboardPlannerService(
        service,
        provider=provider,
    )
    login(client, "quality@ontology.local", "Quality!2026")
    response = client.post(
        "/api/planner/grounded-narrative",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "event_id": "EVT-GS-002",
            "goal": "감사 가능한 설명",
            "use_llm": True,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    validate_planner_contract(payload)
    assert payload["mode"] == "deterministic_fallback"
    assert payload["grounded"] is True
    assert "secret.password_hash" not in response.text
    assert "자동 정지 완료" not in response.text
    assert all(claim["evidence_field_ids"] for claim in payload["claims"])
