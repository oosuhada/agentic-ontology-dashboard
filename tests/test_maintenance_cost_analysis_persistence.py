from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cost_analysis_migrations_preserve_identity_scope_and_append_only_boundary() -> None:
    sqlite_sql = (
        ROOT
        / "systems"
        / "backend"
        / "migrations"
        / "sqlite"
        / "0035_maintenance_cost_analyses.sql"
    ).read_text(encoding="utf-8")
    postgresql_sql = (
        ROOT
        / "systems"
        / "backend"
        / "migrations"
        / "postgresql"
        / "0037_maintenance_cost_analyses.sql"
    ).read_text(encoding="utf-8")

    for sql in (sqlite_sql, postgresql_sql):
        assert "closed_loop_maintenance_cost_analyses" in sql
        assert "CHECK(asset_id=equipment_id)" in sql
        assert "inspection_result_id" in sql
        assert "request_idempotency_key" in sql
        assert "result_json" in sql

    assert "ENABLE ROW LEVEL SECURITY" in postgresql_sql
    assert "current_setting('app.organization_id'" in postgresql_sql
    assert "current_setting('app.project_id'" in postgresql_sql
    assert "FOR SELECT" in postgresql_sql
    assert "FOR INSERT" in postgresql_sql
    assert "BEFORE UPDATE OR DELETE" in postgresql_sql
    assert "reject_maintenance_cost_analysis_mutation" in postgresql_sql
    assert "BEFORE UPDATE ON closed_loop_maintenance_cost_analyses" in sqlite_sql
    assert "BEFORE DELETE ON closed_loop_maintenance_cost_analyses" in sqlite_sql
    assert "snapshots are append-only" in sqlite_sql
