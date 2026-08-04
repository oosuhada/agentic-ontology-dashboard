from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Sequence

from ..postgresql_pool import pooled_tenant_connection
from ..postgresql_repositories import is_postgresql


ALLOWED_DERIVED_MEASURES = {
    "power_w",
    "temperature_gap_k",
    "overstrain_load",
}


class PredictiveMaintenanceRuntimeRepository:
    """RLS-scoped reads over immutable predictive-maintenance facts."""

    def __init__(
        self,
        database_url: str,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        if not is_postgresql(normalized):
            raise ValueError("predictive-maintenance replay requires PostgreSQL")
        self.database_url = normalized
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("runtime repository clock must return a timezone-aware datetime")
        return value

    def _connection(self, organization_id: str, project_id: str):
        return pooled_tenant_connection(
            self.database_url,
            organization_id,
            project_id=project_id,
        )

    def resolve_version(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str | None,
    ) -> dict[str, Any]:
        clauses = [
            "v.organization_id=%s",
            "v.project_id=%s",
            "v.workspace_id=%s",
            "EXISTS (SELECT 1 FROM pm_assets a WHERE a.dataset_version_id=v.id)",
        ]
        parameters: list[Any] = [organization_id, project_id, workspace_id]
        if dataset_version_id:
            clauses.append("v.id=%s")
            parameters.append(dataset_version_id)
        query = f"""
            SELECT v.*,d.display_name AS dataset_name,d.source_type,
                   COALESCE(g.status,'unavailable') AS graph_status,
                   COALESCE(g.record_count,0) AS graph_record_count,
                   g.last_error AS graph_last_error,
                   g.provider_run_id AS graph_provider_run_id,
                   (SELECT COUNT(*) FROM pm_result_artifacts r
                    WHERE r.dataset_version_id=v.id) AS result_artifact_count,
                   (SELECT COUNT(*) FROM pm_prediction_timeline t
                    WHERE t.dataset_version_id=v.id) AS prediction_timeline_count
            FROM dataset_versions v
            JOIN datasets d ON d.id=v.dataset_id
            LEFT JOIN store_projections g
              ON g.dataset_version_id=v.id AND g.store_kind='graph'
            WHERE {' AND '.join(clauses)}
            ORDER BY v.version_number DESC
            LIMIT 1
        """
        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(query, parameters).fetchone()
        if row is None:
            raise KeyError(dataset_version_id or "latest predictive-maintenance Dataset Version")
        return dict(row)

    def role_checksums(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_version_id: str,
    ) -> dict[str, str]:
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                """
                SELECT role,checksum_sha256 FROM dataset_files
                WHERE dataset_version_id=%s AND role IS NOT NULL
                ORDER BY role
                """,
                (dataset_version_id,),
            ).fetchall()
        return {str(row["role"]): str(row["checksum_sha256"]) for row in rows}

    def latest_result_rows(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
        asset_id: str | None,
        site_id: str | None,
        cell_id: str | None,
        asset_type: str | None,
        status_grade: str | None,
        offset: int,
        limit: int,
    ) -> tuple[str, int, list[dict[str, Any]]]:
        filters = [
            "a.dataset_version_id=%s",
            "a.organization_id=%s",
            "a.project_id=%s",
            "a.workspace_id=%s",
        ]
        parameters: list[Any] = [
            dataset_version_id,
            organization_id,
            project_id,
            workspace_id,
        ]
        for column, value in (
            ("a.asset_id", asset_id),
            ("a.site_id", site_id),
            ("a.cell_id", cell_id),
            ("a.asset_type", asset_type),
        ):
            if value:
                filters.append(f"{column}=%s")
                parameters.append(value)

        with self._connection(organization_id, project_id) as connection:
            artifact_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM pm_result_artifacts WHERE dataset_version_id=%s",
                    (dataset_version_id,),
                ).fetchone()["count"]
            )
            if artifact_count:
                if status_grade:
                    filters.append("r.status_grade=%s")
                    parameters.append(status_grade)
                where = " AND ".join(filters)
                total = int(
                    connection.execute(
                        f"""
                        SELECT COUNT(*) AS count
                        FROM pm_result_artifacts r
                        JOIN pm_assets a
                          ON a.dataset_version_id=r.dataset_version_id
                         AND a.asset_id=r.asset_id
                        WHERE {where}
                        """,
                        parameters,
                    ).fetchone()["count"]
                )
                rows = connection.execute(
                    f"""
                    SELECT r.*,a.site_id,a.cell_id,p.payload_json AS prediction_result_payload,
                           p.created_at AS prediction_result_created_at
                    FROM pm_result_artifacts r
                    JOIN pm_assets a
                      ON a.dataset_version_id=r.dataset_version_id
                     AND a.asset_id=r.asset_id
                    JOIN prediction_results p ON p.prediction_id=r.prediction_result_id
                    WHERE {where}
                    ORDER BY r.failure_probability DESC,r.asset_id
                    OFFSET %s LIMIT %s
                    """,
                    (*parameters, offset, limit),
                ).fetchall()
                return "result_artifact", total, [dict(row) for row in rows]

            if status_grade:
                filters.append("s.status=%s")
                parameters.append(status_grade)
            where = " AND ".join(filters)
            total = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*) AS count
                    FROM pm_prediction_snapshots s
                    JOIN pm_assets a
                      ON a.dataset_version_id=s.dataset_version_id
                     AND a.asset_id=s.asset_id
                    WHERE {where}
                    """,
                    parameters,
                ).fetchone()["count"]
            )
            rows = connection.execute(
                f"""
                SELECT s.*,a.site_id,a.cell_id,p.payload_json AS prediction_result_payload,
                       p.created_at AS prediction_result_created_at,
                       COALESCE(
                         jsonb_agg(
                           jsonb_build_object(
                             'rank',f.rank,'feature',f.feature,
                             'feature_value',f.feature_value,
                             'signed_contribution',f.signed_contribution,
                             'absolute_contribution',f.absolute_contribution,
                             'direction',f.direction,
                             'explanation_method',f.explanation_method,
                             'source_type',f.source_type
                           ) ORDER BY f.rank
                         ) FILTER (WHERE f.rank IS NOT NULL), '[]'::jsonb
                       ) AS top_factors
                FROM pm_prediction_snapshots s
                JOIN pm_assets a
                  ON a.dataset_version_id=s.dataset_version_id
                 AND a.asset_id=s.asset_id
                JOIN prediction_results p ON p.prediction_id=s.prediction_result_id
                LEFT JOIN pm_prediction_factors f
                  ON f.dataset_version_id=s.dataset_version_id
                 AND f.prediction_id=s.prediction_id
                WHERE {where}
                GROUP BY s.dataset_version_id,s.prediction_id,a.site_id,a.cell_id,
                         p.payload_json,p.created_at
                ORDER BY s.failure_probability DESC,s.asset_id
                OFFSET %s LIMIT %s
                """,
                (*parameters, offset, limit),
            ).fetchall()
        return "prediction_snapshot_compatibility", total, [dict(row) for row in rows]

    def snapshot_drilldown(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
        prediction_id: str,
    ) -> dict[str, Any] | None:
        with self._connection(organization_id, project_id) as connection:
            snapshot = connection.execute(
                """
                SELECT * FROM pm_prediction_snapshots
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                  AND dataset_version_id=%s AND prediction_id=%s
                """,
                (
                    organization_id,
                    project_id,
                    workspace_id,
                    dataset_version_id,
                    prediction_id,
                ),
            ).fetchone()
            if snapshot is None:
                return None
            factors = connection.execute(
                """
                SELECT rank,feature,feature_value,signed_contribution,
                       absolute_contribution,direction,explanation_method,source_type
                FROM pm_prediction_factors
                WHERE dataset_version_id=%s AND prediction_id=%s
                ORDER BY rank
                """,
                (dataset_version_id, prediction_id),
            ).fetchall()
        return {**dict(snapshot), "factors": [dict(row) for row in factors]}

    def timeline_rows(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
        asset_id: str | None,
        start: datetime | None,
        end: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        filters = [
            "organization_id=%s",
            "project_id=%s",
            "workspace_id=%s",
            "dataset_version_id=%s",
        ]
        parameters: list[Any] = [
            organization_id,
            project_id,
            workspace_id,
            dataset_version_id,
        ]
        if asset_id:
            filters.append("asset_id=%s")
            parameters.append(asset_id)
        if start:
            filters.append("observed_at>=%s")
            parameters.append(start)
        if end:
            filters.append("observed_at<=%s")
            parameters.append(end)
        where = " AND ".join(filters)
        with self._connection(organization_id, project_id) as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) AS count FROM pm_prediction_timeline WHERE {where}",
                    parameters,
                ).fetchone()["count"]
            )
            rows = connection.execute(
                f"""
                SELECT prediction_id,asset_id,asset_type,observed_at,
                       prediction_horizon_hours,failure_probability,status,top_factors,
                       model_version,feature_scope,source_type,source_sha256
                FROM pm_prediction_timeline
                WHERE {where}
                ORDER BY observed_at,asset_id
                OFFSET %s LIMIT %s
                """,
                (*parameters, offset, limit),
            ).fetchall()
        return total, [dict(row) for row in rows]

    @staticmethod
    def _observation_filters(
        *,
        start: datetime,
        end: datetime,
        asset_id: str | None,
        site_id: str | None,
        cell_id: str | None,
    ) -> tuple[list[str], list[Any]]:
        clauses = ["observed_at >= %s", "observed_at <= %s"]
        parameters: list[Any] = [start, end]
        for column, value in (
            ("asset_id", asset_id),
            ("site_id", site_id),
            ("cell_id", cell_id),
        ):
            if value:
                clauses.append(f"{column}=%s")
                parameters.append(value)
        return clauses, parameters

    def observation_rows(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
        start: datetime,
        end: datetime,
        asset_id: str | None,
        site_id: str | None,
        cell_id: str | None,
        asset_type: str | None,
        grain: str,
        derived_measures: set[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        invalid = derived_measures - ALLOWED_DERIVED_MEASURES
        if invalid:
            raise ValueError(f"unsupported derived measures: {sorted(invalid)}")
        base_clauses, base_parameters = self._observation_filters(
            start=start,
            end=end,
            asset_id=asset_id,
            site_id=site_id,
            cell_id=cell_id,
        )
        scope = [
            "organization_id=%s",
            "project_id=%s",
            "workspace_id=%s",
            "dataset_version_id=%s",
            *base_clauses,
        ]
        parameters: list[Any] = [
            organization_id,
            project_id,
            workspace_id,
            dataset_version_id,
            *base_parameters,
        ]
        where = " AND ".join(scope)
        include_compressor = asset_type in {None, "compressor"}
        include_cnc = asset_type in {None, "cnc"}
        selects: list[str] = []
        query_parameters: list[Any] = []

        if grain in {"raw", "10m"}:
            if include_compressor:
                selects.append(
                    f"""
                    SELECT observed_at,asset_id,'compressor'::text AS asset_type,
                           site_id,cell_id,is_operating,operating_state,source_sha256,
                           jsonb_build_object(
                             'voltage_raw',voltage_raw,'rotation_raw',rotation_raw,
                             'pressure_raw',pressure_raw,'vibration_raw',vibration_raw,
                             'relative_vibration_z',relative_vibration_z,
                             'relative_vibration_zone',relative_vibration_zone
                           ) AS measurements,
                           '{{}}'::jsonb AS derived_measures
                    FROM pm_compressor_observations WHERE {where}
                    """
                )
                query_parameters.extend(parameters)
            if include_cnc:
                derived_parts: list[str] = []
                if "power_w" in derived_measures:
                    derived_parts.extend(
                        [
                            "'power_w'",
                            "torque_nm * rotational_speed_rpm * 2 * pi() / 60",
                        ]
                    )
                if "temperature_gap_k" in derived_measures:
                    derived_parts.extend(
                        ["'temperature_gap_k'", "process_temperature_k - air_temperature_k"]
                    )
                if "overstrain_load" in derived_measures:
                    derived_parts.extend(["'overstrain_load'", "tool_wear_min * torque_nm"])
                derived_sql = (
                    f"jsonb_build_object({','.join(derived_parts)})"
                    if derived_parts
                    else "'{}'::jsonb"
                )
                selects.append(
                    f"""
                    SELECT observed_at,asset_id,'cnc'::text AS asset_type,
                           site_id,cell_id,is_operating,operating_state,source_sha256,
                           jsonb_build_object(
                             'product_type',product_type,
                             'air_temperature_k',air_temperature_k,
                             'process_temperature_k',process_temperature_k,
                             'rotational_speed_rpm',rotational_speed_rpm,
                             'torque_nm',torque_nm,'tool_wear_min',tool_wear_min
                           ) AS measurements,
                           {derived_sql} AS derived_measures
                    FROM pm_cnc_observations WHERE {where}
                    """
                )
                query_parameters.extend(parameters)
        else:
            bucket = "date_bin(INTERVAL '1 hour',observed_at,TIMESTAMPTZ '1970-01-01 00:00:00+00')"
            if include_compressor:
                selects.append(
                    f"""
                    SELECT {bucket} AS observed_at,asset_id,'compressor'::text AS asset_type,
                           site_id,cell_id,bool_or(is_operating) AS is_operating,
                           'aggregated_1h'::text AS operating_state,min(source_sha256) AS source_sha256,
                           jsonb_build_object(
                             'voltage_raw',avg(voltage_raw),'rotation_raw',avg(rotation_raw),
                             'pressure_raw',avg(pressure_raw),'vibration_raw',avg(vibration_raw),
                             'relative_vibration_z',avg(relative_vibration_z)
                           ) AS measurements,
                           '{{}}'::jsonb AS derived_measures
                    FROM pm_compressor_observations WHERE {where}
                    GROUP BY {bucket},asset_id,site_id,cell_id
                    """
                )
                query_parameters.extend(parameters)
            if include_cnc:
                derived_parts = []
                if "power_w" in derived_measures:
                    derived_parts.extend(
                        [
                            "'power_w'",
                            "avg(torque_nm * rotational_speed_rpm * 2 * pi() / 60)",
                        ]
                    )
                if "temperature_gap_k" in derived_measures:
                    derived_parts.extend(
                        ["'temperature_gap_k'", "avg(process_temperature_k - air_temperature_k)"]
                    )
                if "overstrain_load" in derived_measures:
                    derived_parts.extend(["'overstrain_load'", "avg(tool_wear_min * torque_nm)"])
                derived_sql = (
                    f"jsonb_build_object({','.join(derived_parts)})"
                    if derived_parts
                    else "'{}'::jsonb"
                )
                selects.append(
                    f"""
                    SELECT {bucket} AS observed_at,asset_id,'cnc'::text AS asset_type,
                           site_id,cell_id,bool_or(is_operating) AS is_operating,
                           'aggregated_1h'::text AS operating_state,min(source_sha256) AS source_sha256,
                           jsonb_build_object(
                             'product_type',min(product_type),
                             'air_temperature_k',avg(air_temperature_k),
                             'process_temperature_k',avg(process_temperature_k),
                             'rotational_speed_rpm',avg(rotational_speed_rpm),
                             'torque_nm',avg(torque_nm),'tool_wear_min',avg(tool_wear_min)
                           ) AS measurements,
                           {derived_sql} AS derived_measures
                    FROM pm_cnc_observations WHERE {where}
                    GROUP BY {bucket},asset_id,site_id,cell_id
                    """
                )
                query_parameters.extend(parameters)
        if not selects:
            return []
        sql = " UNION ALL ".join(selects)
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                f"SELECT * FROM ({sql}) rows ORDER BY observed_at,asset_id LIMIT %s",
                (*query_parameters, limit + 1),
            ).fetchall()
        return [dict(row) for row in rows]

    def nearest_timeline_rows(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
        at_or_before: datetime,
        asset_ids: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        filters = [
            "organization_id=%s",
            "project_id=%s",
            "workspace_id=%s",
            "dataset_version_id=%s",
            "observed_at<=%s",
        ]
        parameters: list[Any] = [
            organization_id,
            project_id,
            workspace_id,
            dataset_version_id,
            at_or_before,
        ]
        if asset_ids:
            filters.append("asset_id=ANY(%s)")
            parameters.append(list(asset_ids))
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT ON (asset_id)
                       prediction_id,asset_id,asset_type,observed_at,
                       prediction_horizon_hours,failure_probability,status,top_factors,
                       model_version,feature_scope,source_type,source_sha256
                FROM pm_prediction_timeline
                WHERE {' AND '.join(filters)}
                ORDER BY asset_id,observed_at DESC
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def observation_bounds(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
    ) -> tuple[datetime, datetime]:
        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                """
                SELECT min(observed_at) AS dataset_start,max(observed_at) AS dataset_end
                FROM (
                  SELECT observed_at FROM pm_compressor_observations
                  WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                    AND dataset_version_id=%s
                  UNION ALL
                  SELECT observed_at FROM pm_cnc_observations
                  WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                    AND dataset_version_id=%s
                ) observations
                """,
                (
                    organization_id,
                    project_id,
                    workspace_id,
                    dataset_version_id,
                    organization_id,
                    project_id,
                    workspace_id,
                    dataset_version_id,
                ),
            ).fetchone()
        if row is None or row["dataset_start"] is None or row["dataset_end"] is None:
            raise ValueError("Dataset Version has no canonical sensor observations")
        return row["dataset_start"], row["dataset_end"]

    def nearest_sensor_time(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
        at_or_before: datetime,
    ) -> datetime:
        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                """
                SELECT max(observed_at) AS observed_at FROM (
                  SELECT observed_at FROM pm_compressor_observations
                  WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                    AND dataset_version_id=%s AND observed_at<=%s
                  UNION ALL
                  SELECT observed_at FROM pm_cnc_observations
                  WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                    AND dataset_version_id=%s AND observed_at<=%s
                ) observations
                """,
                (
                    organization_id,
                    project_id,
                    workspace_id,
                    dataset_version_id,
                    at_or_before,
                    organization_id,
                    project_id,
                    workspace_id,
                    dataset_version_id,
                    at_or_before,
                ),
            ).fetchone()
        if row is None or row["observed_at"] is None:
            raise ValueError("requested time is before the first canonical observation")
        return row["observed_at"]

    def observations_at(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
        observed_at: datetime,
    ) -> list[dict[str, Any]]:
        return self.observation_rows(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=dataset_version_id,
            start=observed_at,
            end=observed_at,
            asset_id=None,
            site_id=None,
            cell_id=None,
            asset_type=None,
            grain="raw",
            derived_measures=ALLOWED_DERIVED_MEASURES,
            limit=200,
        )

    def latest_artifact_references(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
    ) -> list[dict[str, Any]]:
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                """
                SELECT artifact_id,asset_id,observed_at,prediction_id,prediction_result_id,
                       status_grade,failure_probability,model_version,schema_version,source_sha256
                FROM pm_result_artifacts
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                  AND dataset_version_id=%s
                ORDER BY asset_id
                """,
                (organization_id, project_id, workspace_id, dataset_version_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_session(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_id: str,
        dataset_version_id: str,
        created_by: str,
        dataset_start: datetime,
        dataset_end: datetime,
        start_time: datetime,
        speed: float,
    ) -> dict[str, Any]:
        session_id = f"pm-replay-{uuid.uuid4()}"
        now = self._now()
        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                """
                INSERT INTO pm_replay_sessions(
                    id,organization_id,project_id,workspace_id,dataset_id,dataset_version_id,
                    created_by,state,simulation_time,dataset_start,dataset_end,
                    source_freshness_at,speed_minutes_per_second,sequence,last_advanced_at,
                    created_at,updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,'running',%s,%s,%s,%s,%s,1,%s,%s,%s)
                RETURNING *
                """,
                (
                    session_id,
                    organization_id,
                    project_id,
                    workspace_id,
                    dataset_id,
                    dataset_version_id,
                    created_by,
                    start_time,
                    dataset_start,
                    dataset_end,
                    dataset_end,
                    speed,
                    now,
                    now,
                    now,
                ),
            ).fetchone()
        return dict(row)

    def session(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        session_id: str,
        advance: bool = True,
    ) -> dict[str, Any]:
        now = self._now()
        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                """
                SELECT * FROM pm_replay_sessions
                WHERE id=%s AND organization_id=%s AND project_id=%s AND workspace_id=%s
                FOR UPDATE
                """,
                (session_id, organization_id, project_id, workspace_id),
            ).fetchone()
            if row is None:
                raise KeyError(session_id)
            data = dict(row)
            if advance and data["state"] == "running" and data["last_advanced_at"]:
                elapsed_seconds = max(
                    0.0,
                    (now - data["last_advanced_at"]).total_seconds(),
                )
                advanced = data["simulation_time"] + timedelta(
                    minutes=float(data["speed_minutes_per_second"]) * elapsed_seconds
                )
                state = "running"
                if advanced >= data["dataset_end"]:
                    advanced = data["dataset_end"]
                    state = "completed"
                if advanced != data["simulation_time"] or state != data["state"]:
                    row = connection.execute(
                        """
                        UPDATE pm_replay_sessions
                        SET simulation_time=%s,state=%s,sequence=sequence+1,
                            last_advanced_at=%s,updated_at=%s
                        WHERE id=%s
                        RETURNING *
                        """,
                        (advanced, state, now, now, session_id),
                    ).fetchone()
                    return dict(row)
            if data["state"] == "running":
                row = connection.execute(
                    """
                    UPDATE pm_replay_sessions SET last_advanced_at=%s,updated_at=%s
                    WHERE id=%s RETURNING *
                    """,
                    (now, now, session_id),
                ).fetchone()
                return dict(row)
        return data

    def update_session(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        session_id: str,
        action: str,
        time_value: datetime | None = None,
        speed: float | None = None,
    ) -> dict[str, Any]:
        current = self.session(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            session_id=session_id,
            advance=True,
        )
        now = self._now()
        state = current["state"]
        simulation_time = current["simulation_time"]
        next_speed = float(current["speed_minutes_per_second"])
        if action == "pause":
            if state == "running":
                state = "paused"
        elif action == "resume":
            if state == "completed":
                raise ValueError("simulation completed; seek or reset before resume")
            state = "running"
        elif action == "reset":
            simulation_time = current["dataset_start"]
            state = "stopped"
        elif action == "seek":
            if time_value is None:
                raise ValueError("seek requires time")
            if time_value < current["dataset_start"] or time_value > current["dataset_end"]:
                raise ValueError("seek time must be inside Dataset Version observation bounds")
            simulation_time = self.nearest_sensor_time(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                dataset_version_id=current["dataset_version_id"],
                at_or_before=time_value,
            )
            if state == "completed":
                state = "paused"
        elif action == "speed":
            if speed is None:
                raise ValueError("speed action requires speed_minutes_per_second")
            next_speed = speed
        else:
            raise ValueError(f"unsupported replay action: {action}")
        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                """
                UPDATE pm_replay_sessions
                SET state=%s,simulation_time=%s,speed_minutes_per_second=%s,
                    sequence=sequence+1,last_advanced_at=%s,updated_at=%s
                WHERE id=%s AND organization_id=%s AND project_id=%s AND workspace_id=%s
                RETURNING *
                """,
                (
                    state,
                    simulation_time,
                    next_speed,
                    now if state == "running" else None,
                    now,
                    session_id,
                    organization_id,
                    project_id,
                    workspace_id,
                ),
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return dict(row)
