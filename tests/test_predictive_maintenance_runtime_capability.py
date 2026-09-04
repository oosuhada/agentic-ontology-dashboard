from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import dependencies


def test_predictive_maintenance_runtime_reports_postgresql_capability(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    dependencies.get_predictive_maintenance_runtime_service.cache_clear()
    monkeypatch.setattr(
        dependencies,
        "database_target",
        lambda: str(tmp_path / "ontology-dashboard.sqlite3"),
    )
    monkeypatch.setattr(dependencies, "migrate", lambda _target: ())

    try:
        with pytest.raises(HTTPException) as captured:
            dependencies.get_predictive_maintenance_runtime_service()
    finally:
        dependencies.get_predictive_maintenance_runtime_service.cache_clear()

    assert captured.value.status_code == 503
    assert "requires PostgreSQL" in str(captured.value.detail)
