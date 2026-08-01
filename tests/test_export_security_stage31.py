from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from ontology_dashboard.dashboard_service import DashboardService
from ontology_dashboard.identity import CSRF_COOKIE, SESSION_COOKIE, IdentityService
from ontology_dashboard.main import (
    app,
    get_identity_service,
    get_rate_limiter,
    get_service,
)
from ontology_dashboard.security import InMemoryRateLimiter, RateLimitExceeded, RateLimitRule
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService as FactorySignalService

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "manufacturing-demo"


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "stage31.db"


@pytest.fixture()
def identity(database_path: Path) -> IdentityService:
    return IdentityService(database_path, app_env="test", seed_demo=True)


@pytest.fixture()
def service(database_path: Path) -> FactorySignalService:
    return FactorySignalService(ROOT, database_path=database_path)


@pytest.fixture()
def client(identity: IdentityService, service: FactorySignalService):
    get_rate_limiter().clear()
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_rate_limiter().clear()


def login(
    client: TestClient,
    email: str,
    password: str,
    *,
    user_agent: str = "stage31-test-client",
) -> dict[str, Any]:
    response = client.post(
        "/api/auth/login",
        headers={"User-Agent": user_agent},
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def csrf_headers(client: TestClient, *, user_agent: str = "stage31-test-client") -> dict[str, str]:
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token, "User-Agent": user_agent}


def validate_export_contract(payload: dict[str, Any]) -> None:
    schema = json.loads((ROOT / "schemas" / "export.schema.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert errors == [], "\n".join(error.message for error in errors)


def test_json_csv_pdf_exports_create_checkpoints_and_hashes(client: TestClient, tmp_path: Path) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    json_export = client.post(
        "/api/exports",
        headers=csrf_headers(client),
        json={"workspace_id": WORKSPACE, "scope": "dashboard", "format": "json"},
    )
    assert json_export.status_code == 200, json_export.text
    assert json_export.headers["content-type"].startswith("application/json")
    assert json_export.headers["content-disposition"].endswith('.json"')
    assert json_export.headers["x-content-sha256"] == hashlib.sha256(json_export.content).hexdigest()
    payload = json.loads(json_export.content)
    validate_export_contract(payload)
    assert payload["scope"] == "dashboard"
    assert payload["content"]["role_code"] == "process_manager"

    csv_export = client.post(
        "/api/exports",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "scope": "event",
            "event_id": "EVT-GS-002",
            "format": "csv",
        },
    )
    assert csv_export.status_code == 200, csv_export.text
    assert csv_export.headers["content-type"].startswith("text/csv")
    assert csv_export.content.startswith(b"\xef\xbb\xbfpath,value")
    assert b"content.evidence.status" in csv_export.content

    pdf_export = client.post(
        "/api/exports",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "scope": "event",
            "event_id": "EVT-GS-002",
            "format": "pdf",
            "title": "공구 마모 사건 감사 Export",
        },
    )
    assert pdf_export.status_code == 200, pdf_export.text
    assert pdf_export.headers["content-type"] == "application/pdf"
    assert pdf_export.content.startswith(b"%PDF-")
    assert len(pdf_export.content) > 4000
    assert pdf_export.headers["x-content-sha256"] == hashlib.sha256(pdf_export.content).hexdigest()
    if shutil.which("pdftotext"):
        pdf_path = tmp_path / "event-export.pdf"
        text_path = tmp_path / "event-export.txt"
        pdf_path.write_bytes(pdf_export.content)
        subprocess.run(
            ["pdftotext", "-enc", "UTF-8", str(pdf_path), str(text_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        extracted = text_path.read_text(encoding="utf-8")
        assert "공구 마모 사건 감사 Export" in extracted
        assert "EVT-GS-002" in extracted
        assert "박지민" in extracted

    checkpoints = client.get(
        "/api/exports/checkpoints",
        headers={"User-Agent": "stage31-test-client"},
        params={"workspace_id": WORKSPACE},
    )
    assert checkpoints.status_code == 200
    validate_export_contract(checkpoints.json())
    items = checkpoints.json()["items"]
    assert len(items) == 3
    assert {item["format"] for item in items} == {"json", "csv", "pdf"}
    assert all(len(item["snapshot_hash"]) == 64 for item in items)
    assert all(len(item["content_hash"]) == 64 for item in items)


def test_export_checkpoints_are_user_isolated_but_admin_can_review_all(
    client: TestClient,
) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    manager_checkpoint = client.post(
        "/api/exports",
        headers=csrf_headers(client),
        json={"workspace_id": WORKSPACE, "scope": "dashboard", "format": "json"},
    ).headers["x-export-checkpoint-id"]

    client.post("/api/auth/logout", headers=csrf_headers(client))
    login(client, "engineer@ontology.local", "Engineer!2026")
    engineer_checkpoint = client.post(
        "/api/exports",
        headers=csrf_headers(client),
        json={"workspace_id": WORKSPACE, "scope": "dashboard", "format": "json"},
    ).headers["x-export-checkpoint-id"]
    engineer_items = client.get(
        "/api/exports/checkpoints",
        headers={"User-Agent": "stage31-test-client"},
        params={"workspace_id": WORKSPACE},
    ).json()["items"]
    assert {item["id"] for item in engineer_items} == {engineer_checkpoint}

    client.post("/api/auth/logout", headers=csrf_headers(client))
    login(client, "admin@ontology.local", "OntologyAdmin!2026")
    admin_items = client.get(
        "/api/exports/checkpoints",
        headers={"User-Agent": "stage31-test-client"},
        params={"workspace_id": WORKSPACE},
    ).json()["items"]
    assert {manager_checkpoint, engineer_checkpoint}.issubset({item["id"] for item in admin_items})


def test_session_rotation_invalidates_old_token_and_tracks_active_session(
    client: TestClient,
) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    old_token = client.cookies.get(SESSION_COOKIE)
    old_csrf = client.cookies.get(CSRF_COOKIE)
    assert old_token and old_csrf
    before = client.get(
        "/api/auth/sessions",
        headers={"User-Agent": "stage31-test-client"},
    )
    assert before.status_code == 200
    assert len(before.json()["items"]) == 1
    assert before.json()["items"][0]["current"] is True

    refreshed = client.post(
        "/api/auth/refresh",
        headers={"X-CSRF-Token": old_csrf, "User-Agent": "stage31-test-client"},
    )
    assert refreshed.status_code == 200, refreshed.text
    new_token = client.cookies.get(SESSION_COOKIE)
    assert new_token and new_token != old_token
    assert client.cookies.get(CSRF_COOKIE) != old_csrf

    with TestClient(app) as stale_client:
        stale_client.cookies.set(SESSION_COOKIE, old_token)
        stale = stale_client.get(
            "/api/auth/me",
            headers={"User-Agent": "stage31-test-client"},
        )
        assert stale.status_code == 401

    after = client.get(
        "/api/auth/sessions",
        headers={"User-Agent": "stage31-test-client"},
    ).json()["items"]
    assert len(after) == 1
    assert after[0]["current"] is True
    assert after[0]["rotated_from"] is not None


def test_session_user_agent_binding_and_idle_timeout(
    client: TestClient,
    database_path: Path,
) -> None:
    login(client, "quality@ontology.local", "Quality!2026", user_agent="bound-agent")
    mismatch = client.get("/api/auth/me", headers={"User-Agent": "different-agent"})
    assert mismatch.status_code == 401
    assert mismatch.json()["error"]["code"] == "session_client_mismatch"

    client.cookies.clear()
    login(client, "quality@ontology.local", "Quality!2026", user_agent="bound-agent")
    token = client.cookies.get(SESSION_COOKIE)
    assert token
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    old = (datetime.now(timezone.utc) - timedelta(minutes=61)).isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE sessions SET last_seen_at=? WHERE token_hash=?",
            (old, token_hash),
        )
    expired = client.get("/api/auth/me", headers={"User-Agent": "bound-agent"})
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "session_idle_timeout"


def test_revoke_other_sessions_preserves_current_session(
    identity: IdentityService,
    service: FactorySignalService,
) -> None:
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: service
    get_rate_limiter().clear()
    with TestClient(app) as first, TestClient(app) as second:
        login(first, "engineer@ontology.local", "Engineer!2026", user_agent="first-agent")
        login(second, "engineer@ontology.local", "Engineer!2026", user_agent="second-agent")
        revoked = first.delete(
            "/api/auth/sessions/others",
            headers=csrf_headers(first, user_agent="first-agent"),
        )
        assert revoked.status_code == 200
        assert revoked.json()["revoked"] == 1
        assert first.get("/api/auth/me", headers={"User-Agent": "first-agent"}).status_code == 200
        assert second.get("/api/auth/me", headers={"User-Agent": "second-agent"}).status_code == 401
    app.dependency_overrides.clear()


def test_rate_limiter_and_security_headers(client: TestClient) -> None:
    limiter = InMemoryRateLimiter()
    rule = RateLimitRule(limit=2, window_seconds=60)
    limiter.check(bucket="test", subject="subject", rule=rule)
    limiter.check(bucket="test", subject="subject", rule=rule)
    with pytest.raises(RateLimitExceeded):
        limiter.check(bucket="test", subject="subject", rule=rule)

    for _ in range(12):
        denied = client.post(
            "/api/auth/login",
            headers={"User-Agent": "rate-agent"},
            json={"email": "manager@ontology.local", "password": "wrong-password"},
        )
        assert denied.status_code == 401
    limited = client.post(
        "/api/auth/login",
        headers={"User-Agent": "rate-agent"},
        json={"email": "manager@ontology.local", "password": "wrong-password"},
    )
    assert limited.status_code == 429
    assert limited.headers["retry-after"]
    assert limited.json()["error"]["code"] == "rate_limit_exceeded"

    health = client.get("/health")
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert health.headers["referrer-policy"] == "no-referrer"
    assert health.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"


def test_permission_regression_matrix_for_planner_export_admin_and_fde(
    client: TestClient,
) -> None:
    accounts = [
        ("admin@ontology.local", "OntologyAdmin!2026", "tenant_admin"),
        ("executive@ontology.local", "Executive!2026", "executive_viewer"),
        ("manager@ontology.local", "Manager!2026", "process_manager"),
        ("engineer@ontology.local", "Engineer!2026", "process_engineer"),
        ("technician@ontology.local", "Technician!2026", "maintenance_technician"),
        ("quality@ontology.local", "Quality!2026", "quality_auditor"),
        ("datascientist@ontology.local", "DataScience!2026", "ml_validator"),
        ("fde@ontology.local", "FDE!2026", "fde"),
    ]
    for email, password, role in accounts:
        client.cookies.clear()
        user = login(client, email, password)
        assert "exports.create" in user["permissions"]
        assert "planner.object_query" in user["permissions"]
        draft = client.post(
            "/api/planner/dashboard-drafts",
            headers=csrf_headers(client),
            json={
                "workspace_id": WORKSPACE,
                "target_role": "process_manager",
                "goal": "권한 회귀 테스트",
                "use_llm": False,
            },
        )
        if role in {"tenant_admin", "fde"}:
            assert draft.status_code == 200, draft.text
        else:
            assert draft.status_code == 403
        admin = client.get("/api/admin/overview", headers={"User-Agent": "stage31-test-client"})
        assert admin.status_code == (200 if role == "tenant_admin" else 403)
        if role == "fde":
            direct_publish = client.post(
                "/api/dashboard-templates/process_manager/publish",
                headers=csrf_headers(client),
                json={
                    "workspace_id": WORKSPACE,
                    "display_name": "denied",
                    "tabs": draft.json()["tabs"],
                    "parameter_definitions": draft.json()["parameter_definitions"],
                },
            )
            assert direct_publish.status_code == 403


def test_dashboard_with_ten_boards_meets_performance_budget(
    identity: IdentityService,
    service: FactorySignalService,
) -> None:
    user = next(
        item
        for item in identity.repository.list_users()
        if item["email"] == "engineer@ontology.local"
    )
    principal = identity.repository.principal(user["id"])
    dashboards = DashboardService(str(service.repository.path))
    resolved = dashboards.resolve(principal=principal, workspace_id=WORKSPACE)
    board_count = sum(len(tab.boards) for tab in resolved.tabs)
    assert board_count >= 10

    durations: list[float] = []
    for _ in range(120):
        started = time.perf_counter()
        result = dashboards.resolve(principal=principal, workspace_id=WORKSPACE)
        durations.append((time.perf_counter() - started) * 1000)
        assert sum(len(tab.boards) for tab in result.tabs) >= 10
    durations.sort()
    p95 = durations[int(len(durations) * 0.95) - 1]
    assert mean(durations) < 30
    assert p95 < 60
