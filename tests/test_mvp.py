from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from ontology_dashboard.dependencies import get_project_service
from ontology_dashboard.identity import CSRF_COOKIE, IdentityService
from ontology_dashboard.main import app, get_identity_service, get_service
from ontology_dashboard.projects import ProjectRepository, ProjectService
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService
from ontology_dashboard_manufacturing_ml import HeuristicPredictor, build_evidence_package, load_fixture
from ontology_dashboard_manufacturing_ml.contracts import FAILURE_MODE_COLUMNS, TARGET_COLUMN, assert_no_leakage, audit_fixture

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = sorted((ROOT / "data" / "fixtures").glob("GS-*.json"))


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "ontology_dashboard_test.db"


@pytest.fixture()
def service(database_path: Path) -> ManufacturingPredictiveMaintenanceService:
    return ManufacturingPredictiveMaintenanceService(ROOT, database_path=database_path)


@pytest.fixture()
def identity(database_path: Path) -> IdentityService:
    return IdentityService(database_path, app_env="test", seed_demo=True)


@pytest.fixture()
def projects(database_path: Path) -> ProjectService:
    return ProjectService(ProjectRepository(database_path))


def login_as(client: TestClient, email: str, password: str) -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["user"]


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token}


@pytest.fixture()
def client(
    service: ManufacturingPredictiveMaintenanceService,
    identity: IdentityService,
    projects: ProjectService,
):
    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_project_service] = lambda: projects
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_gold_fixtures_validate_and_match_expected_predictions() -> None:
    assert len(FIXTURES) == 8
    predictor = HeuristicPredictor()
    for path in FIXTURES:
        fixture = load_fixture(path)
        issues = audit_fixture(fixture)
        assert bool(issues) is (fixture["scenario_id"] == "GS-007")
        prediction = predictor.predict(fixture)
        expected = fixture["expected"]
        assert prediction.risk_band == expected["risk_band"]
        assert prediction.recommended_decision == expected["recommended_decision"]
        assert prediction.confidence == expected["confidence"]


def test_training_contract_rejects_failure_label_leakage() -> None:
    with pytest.raises(ValueError):
        assert_no_leakage([TARGET_COLUMN])
    for column in FAILURE_MODE_COLUMNS:
        with pytest.raises(ValueError):
            assert_no_leakage([column])
    assert_no_leakage(["Type", "Torque [Nm]"])


def test_evidence_packages_match_the_current_json_schema() -> None:
    schema = json.loads((ROOT / "schemas" / "evidence-package.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for path in FIXTURES:
        evidence = build_evidence_package(load_fixture(path))
        assert list(validator.iter_errors(evidence)) == []
        assert evidence["event_id"].startswith("EVT-GS-")


def test_only_current_mvp_routes_are_exposed() -> None:
    paths = set(app.openapi()["paths"])
    required = {
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/me",
        "/api/projects/{project_id}",
        "/api/projects/{project_id}/workspaces",
        "/api/projects/{project_id}/events",
        "/api/events/{event_id}/evidence",
        "/api/events/{event_id}/report",
        "/api/events/{event_id}/decision",
        "/api/events/{event_id}/notes",
        "/api/events/{event_id}/activity",
        "/api/projects/{project_id}/workspaces/{workspace_id}/predictive-maintenance/dashboard",
        "/api/projects/{project_id}/workspaces/{workspace_id}/predictive-maintenance/results/latest",
    }
    assert required.issubset(paths)
    retired = {
        "/api/auth/register",
        "/api/auth/public-blueprint-comparison",
        "/api/admin/overview",
        "/api/agent/query",
        "/api/analyses",
        "/api/ontology/registry",
        "/api/planner/layout",
    }
    assert paths.isdisjoint(retired)


def test_two_mvp_roles_login_and_receive_project_scope(client: TestClient) -> None:
    for email, password, expected_role in (
        ("manager@ontology.local", "Manager!2026", "process_manager"),
        ("engineer@ontology.local", "Engineer!2026", "process_engineer"),
    ):
        user = login_as(client, email, password)
        assert expected_role in user["roles"]
        assert "manufacturing-demo-project" in user["project_scopes"]
        assert "manufacturing-demo" in user["workspace_scopes"]
        assert client.get("/api/auth/me").status_code == 200
        assert client.post("/api/auth/logout", headers=csrf_headers(client)).status_code == 204


def test_project_workspace_and_gold_fallback_events_are_scoped(client: TestClient) -> None:
    login_as(client, "manager@ontology.local", "Manager!2026")
    project = client.get("/api/projects/manufacturing-demo-project")
    assert project.status_code == 200, project.text
    assert project.json()["default_workspace_id"] == "manufacturing-demo"
    workspaces = client.get("/api/projects/manufacturing-demo-project/workspaces")
    assert workspaces.status_code == 200
    assert [item["id"] for item in workspaces.json()["items"]] == ["manufacturing-demo"]
    events = client.get("/api/projects/manufacturing-demo-project/events")
    assert events.status_code == 200
    assert len(events.json()["items"]) == 8


def test_evidence_report_decision_note_and_activity_flow(client: TestClient) -> None:
    login_as(client, "engineer@ontology.local", "Engineer!2026")
    evidence = client.get("/api/events/EVT-GS-002/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["status"] == "warning"
    engineer_report = client.post(
        "/api/events/EVT-GS-002/report",
        json={"role": "engineer", "locale": "ko-KR", "use_llm": False},
    )
    assert engineer_report.status_code == 200
    assert engineer_report.json()["report"]["role"] == "engineer"
    assert client.post(
        "/api/events/EVT-GS-002/decision",
        headers=csrf_headers(client),
        json={"actor": "ignored", "decision": "request_inspection", "note": "권한 확인"},
    ).status_code == 403
    note = client.post(
        "/api/events/EVT-GS-002/notes",
        headers=csrf_headers(client),
        json={"actor": "ignored", "body": "공구 상태와 센서 연결을 확인했습니다."},
    )
    assert note.status_code == 200

    login_as(client, "manager@ontology.local", "Manager!2026")
    decision = client.post(
        "/api/events/EVT-GS-002/decision",
        headers=csrf_headers(client),
        json={"actor": "ignored", "decision": "request_inspection", "note": "다음 교대 전 점검"},
    )
    assert decision.status_code == 200
    activity = client.get("/api/events/EVT-GS-002/activity")
    assert activity.status_code == 200
    assert len(activity.json()["decisions"]) == 1
    assert len(activity.json()["notes"]) == 1


def test_retired_api_surfaces_return_not_found(client: TestClient) -> None:
    login_as(client, "manager@ontology.local", "Manager!2026")
    for method, path in (
        ("get", "/api/events"),
        ("post", "/api/events/EVT-GS-002/layout"),
        ("post", "/api/events/EVT-GS-002/follow-up"),
        ("get", "/api/admin/overview"),
        ("get", "/api/ontology/registry"),
    ):
        response = getattr(client, method)(path)
        assert response.status_code == 404
