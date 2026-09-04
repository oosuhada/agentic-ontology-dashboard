from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sqlite_repair_reopens_active_legacy_assignment_and_clears_terminal_sentinel() -> None:
    repair_sql = (
        ROOT
        / "systems"
        / "backend"
        / "migrations"
        / "sqlite"
        / "0044_repair_legacy_inspection_assignment.sql"
    ).read_text(encoding="utf-8")

    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE closed_loop_work_orders(
          organization_id text,
          project_id text,
          workspace_id text,
          event_id text,
          equipment_id text,
          work_order_id text PRIMARY KEY,
          work_type text,
          status text,
          assigned_to text,
          assigned_at text,
          updated_at text
        );
        CREATE TABLE closed_loop_activities(
          activity_id text PRIMARY KEY,
          organization_id text,
          project_id text,
          workspace_id text,
          event_id text,
          equipment_id text,
          work_order_id text,
          aggregate_type text,
          aggregate_id text,
          activity_type text,
          actor_user_id text,
          actor_display_name text,
          before_status text,
          after_status text,
          timeline_order integer,
          payload_json text,
          created_at text
        );
        """
    )
    connection.executemany(
        "INSERT INTO closed_loop_work_orders VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "org",
                "project",
                "workspace",
                "EVT-1",
                "CNC-1",
                "WO-ACTIVE",
                "inspection",
                "in_progress",
                "legacy-unassigned",
                "2026-09-01T00:00:00Z",
                "2026-09-01T00:00:00Z",
            ),
            (
                "org",
                "project",
                "workspace",
                "EVT-2",
                "CNC-2",
                "WO-COMPLETE",
                "inspection",
                "completed",
                "legacy-unassigned",
                "2026-09-01T00:00:00Z",
                "2026-09-01T00:00:00Z",
            ),
        ],
    )

    connection.executescript(repair_sql)

    active = connection.execute(
        "SELECT status,assigned_to,assigned_at FROM closed_loop_work_orders WHERE work_order_id='WO-ACTIVE'"
    ).fetchone()
    terminal = connection.execute(
        "SELECT status,assigned_to,assigned_at FROM closed_loop_work_orders WHERE work_order_id='WO-COMPLETE'"
    ).fetchone()
    compensation = connection.execute(
        "SELECT activity_type,before_status,after_status FROM closed_loop_activities WHERE work_order_id='WO-ACTIVE'"
    ).fetchone()

    assert active == ("requested", None, None)
    assert terminal == ("completed", None, None)
    assert compensation == (
        "work_order.reverted_to_requested",
        "in_progress",
        "requested",
    )


def test_postgresql_repair_preserves_the_same_assignment_contract() -> None:
    repair_sql = (
        ROOT
        / "systems"
        / "backend"
        / "migrations"
        / "postgresql"
        / "0046_repair_legacy_inspection_assignment.sql"
    ).read_text(encoding="utf-8")

    assert "work_order.reverted_to_requested" in repair_sql
    assert "status = 'requested'" in repair_sql
    assert "assigned_to = NULL" in repair_sql
    assert "status IN ('completed', 'blocked', 'failed', 'cancelled')" in repair_sql
    assert "assigned_to = 'legacy-unassigned'" in repair_sql
