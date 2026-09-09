"""Refresh persistent one-hour predictive-maintenance observation rollups."""

from __future__ import annotations

import argparse
import os
import time

from app.common.runtime_settings import project_root
from app.infra.db.migrations import migrate
from app.infra.db.postgresql_compat import postgres_repository_connection
from app.infra.db.settings import database_location


def _required(value: str | None, name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


def refresh_once(
    *,
    database: str,
    organization_id: str,
    project_id: str,
    workspace_id: str,
    history_hours: int,
) -> dict[str, int]:
    if not database.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ValueError("hourly observation rollups require PostgreSQL")
    migrate(database)
    cutoff_hours = max(24, history_hours)
    with postgres_repository_connection(
        database,
        organization_id=organization_id,
        project_id=project_id,
    ) as connection:
        compressor = connection.execute(
            """
            INSERT INTO pm_observation_hourly_rollups(
                organization_id,project_id,workspace_id,dataset_version_id,
                asset_id,asset_type,bucket_start,site_id,cell_id,is_operating,
                sample_count,source_sha256,measurements_json,derived_measures_json,refreshed_at
            )
            SELECT organization_id,project_id,workspace_id,dataset_version_id,
                   asset_id,'compressor',
                   date_bin(INTERVAL '1 hour',observed_at,TIMESTAMPTZ '1970-01-01 00:00:00+00'),
                   min(site_id),min(cell_id),bool_or(is_operating),count(*)::integer,
                   min(source_sha256),
                   jsonb_build_object(
                     'voltage_raw',avg(voltage_raw),'rotation_raw',avg(rotation_raw),
                     'pressure_raw',avg(pressure_raw),'vibration_raw',avg(vibration_raw),
                     'relative_vibration_z',avg(relative_vibration_z)
                   ),
                   '{}'::jsonb,now()
            FROM pm_compressor_observations
            WHERE organization_id=? AND project_id=? AND workspace_id=?
              AND observed_at>=now()-(? * INTERVAL '1 hour')
            GROUP BY organization_id,project_id,workspace_id,dataset_version_id,asset_id,
                     date_bin(INTERVAL '1 hour',observed_at,TIMESTAMPTZ '1970-01-01 00:00:00+00')
            ON CONFLICT(dataset_version_id,asset_id,asset_type,bucket_start) DO UPDATE SET
                site_id=excluded.site_id,cell_id=excluded.cell_id,
                is_operating=excluded.is_operating,sample_count=excluded.sample_count,
                source_sha256=excluded.source_sha256,
                measurements_json=excluded.measurements_json,
                derived_measures_json=excluded.derived_measures_json,
                refreshed_at=excluded.refreshed_at
            """,
            (organization_id, project_id, workspace_id, cutoff_hours),
        )
        cnc = connection.execute(
            """
            INSERT INTO pm_observation_hourly_rollups(
                organization_id,project_id,workspace_id,dataset_version_id,
                asset_id,asset_type,bucket_start,site_id,cell_id,is_operating,
                sample_count,source_sha256,measurements_json,derived_measures_json,refreshed_at
            )
            SELECT organization_id,project_id,workspace_id,dataset_version_id,
                   asset_id,'cnc',
                   date_bin(INTERVAL '1 hour',observed_at,TIMESTAMPTZ '1970-01-01 00:00:00+00'),
                   min(site_id),min(cell_id),bool_or(is_operating),count(*)::integer,
                   min(source_sha256),
                   jsonb_build_object(
                     'product_type',min(product_type),
                     'air_temperature_k',avg(air_temperature_k),
                     'process_temperature_k',avg(process_temperature_k),
                     'rotational_speed_rpm',avg(rotational_speed_rpm),
                     'torque_nm',avg(torque_nm),'tool_wear_min',avg(tool_wear_min)
                   ),
                   jsonb_build_object(
                     'power_w',avg(torque_nm * rotational_speed_rpm * 2 * pi() / 60),
                     'temperature_gap_k',avg(process_temperature_k-air_temperature_k),
                     'overstrain_load',avg(tool_wear_min*torque_nm)
                   ),now()
            FROM pm_cnc_observations
            WHERE organization_id=? AND project_id=? AND workspace_id=?
              AND observed_at>=now()-(? * INTERVAL '1 hour')
            GROUP BY organization_id,project_id,workspace_id,dataset_version_id,asset_id,
                     date_bin(INTERVAL '1 hour',observed_at,TIMESTAMPTZ '1970-01-01 00:00:00+00')
            ON CONFLICT(dataset_version_id,asset_id,asset_type,bucket_start) DO UPDATE SET
                site_id=excluded.site_id,cell_id=excluded.cell_id,
                is_operating=excluded.is_operating,sample_count=excluded.sample_count,
                source_sha256=excluded.source_sha256,
                measurements_json=excluded.measurements_json,
                derived_measures_json=excluded.derived_measures_json,
                refreshed_at=excluded.refreshed_at
            """,
            (organization_id, project_id, workspace_id, cutoff_hours),
        )
    return {
        "compressor_rows": max(0, int(getattr(compressor, "rowcount", 0) or 0)),
        "cnc_rows": max(0, int(getattr(cnc, "rowcount", 0) or 0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", default=os.getenv("ONTOLOGY_DASHBOARD_OUTBOX_ORGANIZATION_ID"))
    parser.add_argument("--project-id", default=os.getenv("ONTOLOGY_DASHBOARD_OUTBOX_PROJECT_ID"))
    parser.add_argument("--workspace-id", default=os.getenv("ONTOLOGY_DASHBOARD_WORKSPACE_ID", "manufacturing-demo"))
    parser.add_argument("--history-hours", type=int, default=90 * 24)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=900)
    args = parser.parse_args()
    database = database_location(project_root())
    organization_id = _required(args.organization_id, "organization_id")
    project_id = _required(args.project_id, "project_id")
    workspace_id = _required(args.workspace_id, "workspace_id")

    while True:
        result = refresh_once(
            database=database,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            history_hours=args.history_hours,
        )
        print(result, flush=True)
        if not args.watch:
            return 0
        time.sleep(max(60, args.interval_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
