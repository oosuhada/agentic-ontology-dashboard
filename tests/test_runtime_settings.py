from __future__ import annotations

from pathlib import Path

import pytest
from starlette.requests import Request

from app.dependencies import client_ip
from app.common.runtime_settings import (
    allowed_origin_regex,
    allowed_origins,
    project_root,
)
from app.infra.db.settings import database_location
from app.infra.observability.runtime_validation import validate_runtime_environment


def test_explicit_allowed_origin_regex_supports_preview_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ONTOLOGY_DASHBOARD_ALLOWED_ORIGIN_REGEX",
        r"^https://.*\.vercel\.app$",
    )
    assert allowed_origin_regex() == r"^https://.*\.vercel\.app$"


def test_project_root_prefers_explicit_runtime_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_ROOT", "/legacy/should-not-win")
    assert project_root() == tmp_path.resolve()


def test_project_root_accepts_legacy_runtime_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_PROJECT_ROOT", raising=False)
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_ROOT", str(tmp_path))
    assert project_root() == tmp_path.resolve()


def test_development_defaults_to_canonical_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_DB", raising=False)
    monkeypatch.delenv("FACTORY_SIGNAL_DB", raising=False)
    assert database_location(tmp_path) == str(tmp_path / "data" / "local" / "ontology_dashboard.db")


def test_legacy_database_key_remains_temporarily_compatible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_DB", raising=False)
    monkeypatch.setenv("FACTORY_SIGNAL_DB", str(tmp_path / "legacy.db"))
    with pytest.warns(DeprecationWarning):
        assert database_location(tmp_path) == str(tmp_path / "legacy.db")


def test_production_rejects_demo_seed_missing_origin_and_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SEED_DEMO_ACCOUNTS", "1")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_DB", str(tmp_path / "production.db"))
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_ALLOW_PRODUCTION_SQLITE", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        validate_runtime_environment(tmp_path)

    message = str(exc_info.value)
    assert "SEED_DEMO_ACCOUNTS" in message
    assert "ONTOLOGY_DASHBOARD_ALLOWED_ORIGINS" in message
    assert "SQLite-only" in message


def test_production_allows_only_explicit_single_instance_sqlite_pilot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SEED_DEMO_ACCOUNTS", "0")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_ALLOWED_ORIGINS", "https://dashboard.example.com")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_DB", str(tmp_path / "pilot.db"))
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_ALLOW_PRODUCTION_SQLITE", "1")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("FACTORY_SIGNAL_DB", raising=False)

    validate_runtime_environment(tmp_path)
    assert allowed_origins() == ["https://dashboard.example.com"]


def test_forwarded_ip_is_used_only_for_trusted_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_TRUST_PROXY_HEADERS", "1")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_TRUSTED_PROXIES", "10.0.0.0/8")
    trusted = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"203.0.113.7")],
            "client": ("10.1.2.3", 1234),
            "scheme": "https",
            "server": ("testserver", 443),
            "query_string": b"",
        }
    )
    assert client_ip(trusted) == "203.0.113.7"

    untrusted = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"203.0.113.8")],
            "client": ("192.0.2.10", 1234),
            "scheme": "https",
            "server": ("testserver", 443),
            "query_string": b"",
        }
    )
    assert client_ip(untrusted) == "192.0.2.10"


def test_production_accepts_postgresql_runtime_with_required_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SEED_DEMO_ACCOUNTS", "0")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_ALLOWED_ORIGINS", "https://dashboard.example.com")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_DATABASE_URL", "postgresql://user:password@db/ontology")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_DB", raising=False)

    validate_runtime_environment(tmp_path)
