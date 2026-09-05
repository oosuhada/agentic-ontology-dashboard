from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Sequence

from app.infra.db.pool import pooled_tenant_connection
from app.infra.db.settings import is_postgresql_url
from app.diagnosis.ports import ALLOWED_DERIVED_MEASURES


class PredictiveMaintenanceRuntimeRepository:
    """RLS-scoped reads over immutable predictive-maintenance facts."""

    def __init__(
        self,
        database_url: str,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        if not is_postgresql_url(normalized):
            raise ValueError("predictive-maintenance replay requires PostgreSQL")
        self.database_url = normalized
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("runtime repository clock must return a timezone-aware datetime")
        return value

    def clock_now(self) -> datetime:
        return self._now()

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
                   COALESCE(rel.status,'unavailable') AS relational_status,
                   COALESCE(rel.record_count,0) AS relational_record_count,
                   COALESCE(g.status,'unavailable') AS graph_status,
                   COALESCE(g.record_count,0) AS graph_record_count,
                   g.last_error AS graph_last_error,
                   g.provider_run_id AS graph_provider_run_id,
                   COALESCE(g.attempt_count,0) AS graph_attempt_count,
                   g.updated_at AS graph_updated_at,
                   (SELECT COUNT(*) FROM pm_result_artifacts r
                    WHERE r.dataset_version_id=v.id) AS result_artifact_count,
                   (SELECT COUNT(*) FROM pm_prediction_timeline t
                    WHERE t.dataset_version_id=v.id) AS prediction_timeline_count,
                   COALESCE(
                     (SELECT string_agg(DISTINCT r.model_version, ', ' ORDER BY r.model_version)
                      FROM pm_result_artifacts r WHERE r.dataset_version_id=v.id),
                     (SELECT s.model_version FROM pm_prediction_snapshots s
                      WHERE s.dataset_version_id=v.id ORDER BY s.observed_at DESC LIMIT 1)
                   ) AS runtime_model_version,
                   (SELECT r.schema_version FROM pm_result_artifacts r
                    WHERE r.dataset_version_id=v.id ORDER BY r.observed_at DESC LIMIT 1)
                     AS result_artifact_schema_version,
                   (SELECT r.prediction_task FROM pm_result_artifacts r
                    WHERE r.dataset_version_id=v.id ORDER BY r.observed_at DESC LIMIT 1)
                     AS runtime_prediction_task,
                   (SELECT MAX(r.observed_at) FROM pm_result_artifacts r
                    WHERE r.dataset_version_id=v.id) AS latest_result_observed_at
            FROM dataset_versions v
            JOIN datasets d ON d.id=v.dataset_id
            LEFT JOIN store_projections rel
              ON rel.dataset_version_id=v.id AND rel.store_kind='relational'
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

    def latest_wall_clock_live_version(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        """Return the freshest wall-clock live Dataset Version for Operations.

        Explicit user Dataset selections remain useful for replay and analysis,
        but a live monitoring surface needs a stable way to follow the newest
        generator-backed runtime Dataset Version without silently inheriting an
        old pinned selection.
        """

        cutoff = self._now() + timedelta(minutes=5)
        query = """
            SELECT v.*,d.display_name AS dataset_name,d.source_type,
                   (SELECT MAX(r.observed_at) FROM pm_result_artifacts r
                    WHERE r.organization_id=v.organization_id
                      AND r.project_id=v.project_id
                      AND r.workspace_id=v.workspace_id
                      AND r.dataset_version_id=v.id
                      AND r.model_version<>'presentation-live-v1') AS latest_result_observed_at,
                   (SELECT COUNT(*) FROM pm_result_artifacts r
                    WHERE r.organization_id=v.organization_id
                      AND r.project_id=v.project_id
                      AND r.workspace_id=v.workspace_id
                      AND r.dataset_version_id=v.id
                      AND r.model_version<>'presentation-live-v1') AS result_artifact_count
            FROM dataset_versions v
            JOIN datasets d ON d.id=v.dataset_id
            WHERE v.organization_id=%s
              AND v.project_id=%s
              AND v.workspace_id=%s
              AND v.status='published'
              AND v.source_version='gen-data-wall-clock-live-v2'
              AND EXISTS (
                SELECT 1 FROM pm_assets a
                WHERE a.organization_id=v.organization_id
                  AND a.project_id=v.project_id
                  AND a.workspace_id=v.workspace_id
                  AND a.dataset_version_id=v.id
              )
              AND EXISTS (
                SELECT 1 FROM pm_result_artifacts r
                WHERE r.organization_id=v.organization_id
                  AND r.project_id=v.project_id
                  AND r.workspace_id=v.workspace_id
                  AND r.dataset_version_id=v.id
                  AND r.model_version<>'presentation-live-v1'
              )
              AND (
                SELECT MAX(r.observed_at) FROM pm_result_artifacts r
                WHERE r.organization_id=v.organization_id
                  AND r.project_id=v.project_id
                  AND r.workspace_id=v.workspace_id
                  AND r.dataset_version_id=v.id
                  AND r.model_version<>'presentation-live-v1'
              ) <= %s
            ORDER BY latest_result_observed_at DESC NULLS LAST,
                     v.created_at DESC,
                     v.version_number DESC
            LIMIT 1
        """
        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                query,
                (organization_id, project_id, workspace_id, cutoff),
            ).fetchone()
        if row is None:
            raise KeyError("latest wall-clock live predictive-maintenance Dataset Version")
        return dict(row)

    def risk_index_rows(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
        start: datetime,
        end: datetime,
        bucket_interval: str,
        asset_id: str | None,
    ) -> list[dict[str, Any]]:
        """Return bounded, chart-ready risk buckets from governed runtime data.

        Asset mode averages repeated model outputs within a bucket. Plant mode
        intentionally exposes a transparent P95 risk statistic rather than an
        opaque synthetic score. This makes the "plant risk index" auditable.
        """

        filters = [
            "organization_id=%s",
            "project_id=%s",
            "workspace_id=%s",
            "dataset_version_id=%s",
            "model_version<>'presentation-live-v1'",
            "observed_at>=%s",
            "observed_at<=%s",
        ]
        parameters: list[Any] = [
            organization_id,
            project_id,
            workspace_id,
            dataset_version_id,
            start,
            end,
        ]
        if asset_id:
            filters.append("asset_id=%s")
            parameters.append(asset_id)
        where = " AND ".join(filters)
        origin = "2000-01-01T00:00:00+00"
        with self._connection(organization_id, project_id) as connection:
            if asset_id:
                rows = connection.execute(
                    f"""
                    SELECT date_bin(%s::interval, observed_at, %s::timestamptz) AS observed_at,
                           AVG(failure_probability)::double precision AS risk_value,
                           AVG(failure_probability)::double precision AS mean_risk,
                           MAX(failure_probability)::double precision AS max_risk,
                           COUNT(*)::integer AS sample_count,
                           COUNT(*) FILTER (WHERE status='critical')::integer AS critical_count,
                           COUNT(DISTINCT asset_id)::integer AS asset_count
                    FROM pm_prediction_timeline
                    WHERE {where}
                    GROUP BY 1
                    ORDER BY 1
                    """,
                    (bucket_interval, origin, *parameters),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""
                    WITH asset_bucket AS (
                        SELECT date_bin(%s::interval, observed_at, %s::timestamptz) AS observed_at,
                               asset_id,
                               AVG(failure_probability)::double precision AS asset_risk,
                               MAX(failure_probability)::double precision AS asset_max_risk,
                               COUNT(*)::integer AS sample_count,
                               BOOL_OR(status='critical') AS has_critical
                        FROM pm_prediction_timeline
                        WHERE {where}
                        GROUP BY 1,asset_id
                    )
                    SELECT observed_at,
                           percentile_cont(0.95) WITHIN GROUP (ORDER BY asset_risk)::double precision AS risk_value,
                           AVG(asset_risk)::double precision AS mean_risk,
                           MAX(asset_max_risk)::double precision AS max_risk,
                           SUM(sample_count)::integer AS sample_count,
                           COUNT(*) FILTER (WHERE has_critical)::integer AS critical_count,
                           COUNT(*)::integer AS asset_count
                    FROM asset_bucket
                    GROUP BY observed_at
                    ORDER BY observed_at
                    """,
                    (bucket_interval, origin, *parameters),
                ).fetchall()
        return [dict(row) for row in rows]

    def list_versions(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT v.*,d.display_name AS dataset_name,d.source_type,
                   COALESCE(rel.status,'unavailable') AS relational_status,
                   COALESCE(rel.record_count,0) AS relational_record_count,
                   COALESCE(g.status,'unavailable') AS graph_status,
                   COALESCE(g.record_count,0) AS graph_record_count,
                   g.last_error AS graph_last_error,
                   g.provider_run_id AS graph_provider_run_id,
                   COALESCE(g.attempt_count,0) AS graph_attempt_count,
                   g.updated_at AS graph_updated_at,
                   (SELECT COUNT(*) FROM pm_result_artifacts r
                    WHERE r.dataset_version_id=v.id) AS result_artifact_count,
                   (SELECT COUNT(*) FROM pm_prediction_timeline t
                    WHERE t.dataset_version_id=v.id) AS prediction_timeline_count,
                   COALESCE(
                     (SELECT string_agg(DISTINCT r.model_version, ', ' ORDER BY r.model_version)
                      FROM pm_result_artifacts r WHERE r.dataset_version_id=v.id),
                     (SELECT s.model_version FROM pm_prediction_snapshots s
                      WHERE s.dataset_version_id=v.id ORDER BY s.observed_at DESC LIMIT 1)
                   ) AS runtime_model_version,
                   (SELECT r.schema_version FROM pm_result_artifacts r
                    WHERE r.dataset_version_id=v.id ORDER BY r.observed_at DESC LIMIT 1)
                     AS result_artifact_schema_version,
                   (SELECT r.prediction_task FROM pm_result_artifacts r
                    WHERE r.dataset_version_id=v.id ORDER BY r.observed_at DESC LIMIT 1)
                     AS runtime_prediction_task
            FROM dataset_versions v
            JOIN datasets d ON d.id=v.dataset_id
            LEFT JOIN store_projections rel
              ON rel.dataset_version_id=v.id AND rel.store_kind='relational'
            LEFT JOIN store_projections g
              ON g.dataset_version_id=v.id AND g.store_kind='graph'
            WHERE v.organization_id=%s
              AND v.project_id=%s
              AND v.workspace_id=%s
              AND EXISTS (
                SELECT 1 FROM pm_assets a WHERE a.dataset_version_id=v.id
              )
            ORDER BY v.version_number DESC,v.created_at DESC
        """
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                query,
                (organization_id, project_id, workspace_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def selected_version_for_user(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        user_id: str,
    ) -> str | None:
        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                """
                SELECT s.dataset_version_id
                FROM pm_workspace_dataset_selections s
                JOIN dataset_versions v ON v.id=s.dataset_version_id
                WHERE s.organization_id=%s
                  AND s.project_id=%s
                  AND s.workspace_id=%s
                  AND s.user_id=%s
                  AND s.selection_mode='explicit'
                  AND v.organization_id=s.organization_id
                  AND v.project_id=s.project_id
                  AND v.workspace_id=s.workspace_id
                  AND EXISTS (
                    SELECT 1 FROM pm_assets a
                    WHERE a.dataset_version_id=s.dataset_version_id
                  )
                """,
                (organization_id, project_id, workspace_id, user_id),
            ).fetchone()
        return None if row is None else str(row["dataset_version_id"])

    def save_selected_version(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        user_id: str,
        dataset_version_id: str | None,
    ) -> None:
        with self._connection(organization_id, project_id) as connection:
            if dataset_version_id is None:
                connection.execute(
                    """
                    DELETE FROM pm_workspace_dataset_selections
                    WHERE organization_id=%s AND project_id=%s
                      AND workspace_id=%s AND user_id=%s
                    """,
                    (organization_id, project_id, workspace_id, user_id),
                )
                return
            exists = connection.execute(
                """
                SELECT 1 FROM dataset_versions v
                WHERE v.id=%s AND v.organization_id=%s AND v.project_id=%s
                  AND v.workspace_id=%s
                  AND EXISTS (
                    SELECT 1 FROM pm_assets a WHERE a.dataset_version_id=v.id
                  )
                """,
                (dataset_version_id, organization_id, project_id, workspace_id),
            ).fetchone()
            if exists is None:
                raise KeyError(dataset_version_id)
            connection.execute(
                """
                INSERT INTO pm_workspace_dataset_selections(
                    organization_id,project_id,workspace_id,user_id,
                    dataset_version_id,selection_mode,created_at,updated_at
                ) VALUES (%s,%s,%s,%s,%s,'explicit',now(),now())
                ON CONFLICT (organization_id,project_id,workspace_id,user_id)
                DO UPDATE SET dataset_version_id=EXCLUDED.dataset_version_id,
                              selection_mode='explicit',updated_at=now()
                """,
                (
                    organization_id,
                    project_id,
                    workspace_id,
                    user_id,
                    dataset_version_id,
                ),
            )

    def dashboard_support_rows(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
        with self._connection(organization_id, project_id) as connection:
            maintenance_rows = connection.execute(
                """
                SELECT maintenance_id,asset_id,maintenance_type,started_at,
                       completed_at,tool_replaced,source_event_id,source_sha256
                FROM pm_maintenance_events
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                  AND dataset_version_id=%s
                ORDER BY asset_id,completed_at DESC
                """,
                (organization_id, project_id, workspace_id, dataset_version_id),
            ).fetchall()
            ontology_rows = connection.execute(
                """
                SELECT object_id,payload_json->'properties'->>'asset_id' AS asset_id
                FROM ontology_objects
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                  AND dataset_version_id=%s AND object_type='risk_event'
                """,
                (organization_id, project_id, workspace_id, dataset_version_id),
            ).fetchall()
        maintenance: dict[str, list[dict[str, Any]]] = {}
        for row in maintenance_rows:
            maintenance.setdefault(str(row["asset_id"]), []).append(dict(row))
        ontology = {
            str(row["asset_id"]): str(row["object_id"])
            for row in ontology_rows
            if row.get("asset_id")
        }
        return maintenance, ontology

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
                latest_results = """
                    SELECT DISTINCT ON (asset_id) *
                    FROM pm_result_artifacts
                    WHERE dataset_version_id=%s
                    ORDER BY asset_id,observed_at DESC,created_at DESC,artifact_id DESC
                """
                total = int(
                    connection.execute(
                        f"""
                        WITH latest_results AS ({latest_results})
                        SELECT COUNT(*) AS count
                        FROM latest_results r
                        JOIN pm_assets a
                          ON a.dataset_version_id=r.dataset_version_id
                         AND a.asset_id=r.asset_id
                        WHERE {where}
                        """,
                        (dataset_version_id, *parameters),
                    ).fetchone()["count"]
                )
                rows = connection.execute(
                    f"""
                    WITH latest_results AS ({latest_results})
                    SELECT r.*,a.site_id,a.cell_id,p.payload_json AS prediction_result_payload,
                           p.created_at AS prediction_result_created_at
                    FROM latest_results r
                    JOIN pm_assets a
                      ON a.dataset_version_id=r.dataset_version_id
                     AND a.asset_id=r.asset_id
                    JOIN prediction_results p ON p.prediction_id=r.prediction_result_id
                    WHERE {where}
                    ORDER BY r.failure_probability DESC,r.asset_id
                    OFFSET %s LIMIT %s
                    """,
                    (dataset_version_id, *parameters, offset, limit),
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

    def post_maintenance_result_row(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        asset_id: str,
        maintenance_event_id: str,
    ) -> dict[str, Any] | None:
        """Return the newest Product Result correlated to one maintenance event.

        A post-maintenance result normally belongs to the live replay dataset,
        while the user's selected dashboard context can still point at the
        immutable Canonical dataset.  The maintenance lineage is therefore the
        canonical correlation key for this cross-dataset lookup.
        """

        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                """
                SELECT r.*,a.site_id,a.cell_id,
                       p.payload_json AS prediction_result_payload,
                       p.created_at AS prediction_result_created_at
                FROM pm_result_artifacts r
                JOIN pm_assets a
                  ON a.dataset_version_id=r.dataset_version_id
                 AND a.asset_id=r.asset_id
                JOIN prediction_results p
                  ON p.prediction_id=r.prediction_result_id
                WHERE r.organization_id=%s AND r.project_id=%s
                  AND r.workspace_id=%s AND r.asset_id=%s
                  AND (
                    r.provenance->>'maintenance_event_id'=%s
                    OR p.payload_json#>>'{lineage,source_context,lineage,maintenance_event_id}'=%s
                  )
                ORDER BY r.observed_at DESC,r.created_at DESC,r.artifact_id DESC
                LIMIT 1
                """,
                (
                    organization_id,
                    project_id,
                    workspace_id,
                    asset_id,
                    maintenance_event_id,
                    maintenance_event_id,
                ),
            ).fetchone()
        return None if row is None else dict(row)

    def post_maintenance_runtime_status_row(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        asset_id: str,
        maintenance_event_id: str,
    ) -> dict[str, Any] | None:
        """Return the newest Generator outcome for a maintenance replay branch."""

        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                """
                SELECT raw_item->>'output_status' AS status,
                       raw_item->>'failure_reason' AS failure_reason,
                       raw_item->>'observed_at' AS observed_at,
                       raw_item->>'model_id' AS model_id,
                       raw_item->>'model_version' AS model_version,
                       raw_item->'lineage' AS lineage,
                       received_at,updated_at
                FROM pm_prediction_result_inbox_items
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                  AND validation_status IN ('accepted','duplicate')
                  AND raw_item->>'asset_id'=%s
                  AND raw_item->>'source_kind'='maintenance_replay_overlay'
                  AND raw_item#>>'{lineage,maintenance_event_id}'=%s
                ORDER BY received_at DESC,receive_item_id DESC
                LIMIT 1
                """,
                (
                    organization_id,
                    project_id,
                    workspace_id,
                    asset_id,
                    maintenance_event_id,
                ),
            ).fetchone()
        return None if row is None else dict(row)

    def result_artifact_row(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        artifact_id: str,
    ) -> dict[str, Any] | None:
        """Return one canonical Product Result row inside the requested scope."""

        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                """
                SELECT r.*,a.site_id,a.cell_id,
                       p.payload_json AS prediction_result_payload,
                       p.created_at AS prediction_result_created_at
                FROM pm_result_artifacts r
                JOIN pm_assets a
                  ON a.dataset_version_id=r.dataset_version_id
                 AND a.asset_id=r.asset_id
                JOIN prediction_results p
                  ON p.prediction_id=r.prediction_result_id
                WHERE r.organization_id=%s AND r.project_id=%s
                  AND r.workspace_id=%s AND r.artifact_id=%s
                ORDER BY r.created_at DESC,r.dataset_version_id DESC
                LIMIT 2
                """,
                (organization_id, project_id, workspace_id, artifact_id),
            ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("Product Result artifact_id is ambiguous inside workspace scope")
        return dict(rows[0])

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
            "model_version<>'presentation-live-v1'",
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

    def result_history_rows(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
        asset_id: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return governed runtime Product Results for one AssetDetail chart."""

        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                """
                SELECT artifact_id,prediction_id,observed_at,
                       failure_probability,status_grade,source_sha256
                FROM pm_result_artifacts
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                  AND dataset_version_id=%s AND asset_id=%s
                  AND model_version<>'presentation-live-v1'
                  AND observed_at >= %s AND observed_at <= %s
                ORDER BY observed_at,created_at,artifact_id
                LIMIT %s
                """,
                (
                    organization_id,
                    project_id,
                    workspace_id,
                    dataset_version_id,
                    asset_id,
                    start,
                    end,
                    limit,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

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
            "model_version<>'presentation-live-v1'",
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
                SELECT DISTINCT ON (asset_id)
                       artifact_id,asset_id,observed_at,prediction_id,prediction_result_id,
                       status_grade,failure_probability,model_version,schema_version,source_sha256
                FROM pm_result_artifacts
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                  AND dataset_version_id=%s
                  AND model_version<>'presentation-live-v1'
                ORDER BY asset_id,observed_at DESC,created_at DESC,artifact_id DESC
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
            if advance and data["state"] == "running":
                row = connection.execute(
                    """
                    UPDATE pm_replay_sessions SET last_advanced_at=%s,updated_at=%s
                    WHERE id=%s RETURNING *
                    """,
                    (now, now, session_id),
                ).fetchone()
                return dict(row)
        return data

    def asset_exists_in_version(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
        asset_id: str,
    ) -> bool:
        """Return whether an asset belongs to the scoped Dataset Version."""

        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM dataset_versions v
                    JOIN pm_assets a ON a.dataset_version_id=v.id
                    WHERE v.id=%s
                      AND v.organization_id=%s
                      AND v.project_id=%s
                      AND v.workspace_id=%s
                      AND a.asset_id=%s
                ) AS asset_exists
                """,
                (
                    dataset_version_id,
                    organization_id,
                    project_id,
                    workspace_id,
                    asset_id,
                ),
            ).fetchone()
        return bool(row and row["asset_exists"])

    def assets_exist_in_workspace(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        asset_ids: Sequence[str],
    ) -> set[str]:
        if not asset_ids:
            return set()
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT a.asset_id
                FROM dataset_versions v
                JOIN pm_assets a ON a.dataset_version_id=v.id
                WHERE v.organization_id=%s
                  AND v.project_id=%s
                  AND v.workspace_id=%s
                  AND a.asset_id=ANY(%s)
                """,
                (organization_id, project_id, workspace_id, list(asset_ids)),
            ).fetchall()
        return {str(row["asset_id"]) for row in rows}

    @staticmethod
    def _prediction_inbox_lock_key(*parts: str) -> str:
        return "prediction-result-inbox:" + ":".join(parts)

    def _lock_prediction_inbox_identity(
        self,
        connection,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        kind: str,
        identity: str,
    ) -> None:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (
                self._prediction_inbox_lock_key(
                    organization_id,
                    project_id,
                    workspace_id,
                    kind,
                    identity,
                ),
            ),
        )

    def save_prediction_batch_inbox(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        batch_id: str,
        payload_sha256: str,
        validation_status: str,
        rejection_reason: str | None,
        raw_payload: dict[str, Any],
        received_at: datetime,
        item_receipts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = self._now()
        with self._connection(organization_id, project_id) as connection:
            self._lock_prediction_inbox_identity(
                connection,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                kind="batch",
                identity=batch_id,
            )
            for event_id in sorted(
                str(receipt["event_id"]) for receipt in item_receipts
            ):
                self._lock_prediction_inbox_identity(
                    connection,
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    kind="event",
                    identity=event_id,
                )
            same_batch = connection.execute(
                """
                SELECT receive_id
                FROM pm_prediction_result_inbox_batches
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                  AND batch_id=%s AND payload_sha256=%s
                FOR UPDATE
                """,
                (organization_id, project_id, workspace_id, batch_id, payload_sha256),
            ).fetchone()
            other_batch = None
            if same_batch is None:
                other_batch = connection.execute(
                    """
                    SELECT receive_id
                    FROM pm_prediction_result_inbox_batches
                    WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                      AND batch_id=%s
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (organization_id, project_id, workspace_id, batch_id),
                ).fetchone()

            batch_status = validation_status
            batch_reason = rejection_reason
            if same_batch is not None:
                batch_status = "duplicate"
                batch_reason = None
            elif other_batch is not None:
                batch_status = "conflict"
                batch_reason = (
                    "batch_payload_conflict: same batch_id received with "
                    "different payload_sha256"
                )

            persisted_items: list[dict[str, Any]] = []
            raw_items = [
                item for item in raw_payload.get("results", []) if isinstance(item, dict)
            ]
            for receipt in item_receipts:
                event_id = str(receipt["event_id"])
                item_sha = str(receipt["payload_sha256"])
                same_item = connection.execute(
                    """
                    SELECT receive_item_id
                    FROM pm_prediction_result_inbox_items
                    WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                      AND event_id=%s AND payload_sha256=%s
                    FOR UPDATE
                    """,
                    (organization_id, project_id, workspace_id, event_id, item_sha),
                ).fetchone()
                other_item = None
                if same_item is None:
                    other_item = connection.execute(
                        """
                        SELECT receive_item_id
                        FROM pm_prediction_result_inbox_items
                        WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                          AND event_id=%s
                        LIMIT 1
                        FOR UPDATE
                        """,
                        (organization_id, project_id, workspace_id, event_id),
                    ).fetchone()
                item_status = str(receipt["validation_status"])
                item_reason = receipt.get("rejection_reason")
                if same_item is not None:
                    item_status = "duplicate"
                    item_reason = None
                elif other_item is not None:
                    item_status = "conflict"
                    item_reason = (
                        "event_payload_conflict: same event_id received "
                        "with different payload_sha256"
                    )
                if item_status == "conflict":
                    batch_status = "conflict"
                    batch_reason = batch_reason or "one or more items conflicted"
                elif item_status == "rejected" and batch_status not in {"conflict"}:
                    batch_status = "rejected"
                    batch_reason = batch_reason or "one or more items were rejected"
                raw_item = next(
                    (item for item in raw_items if str(item.get("event_id")) == event_id),
                    {},
                )
                persisted_items.append(
                    {
                        "event_id": event_id,
                        "payload_sha256": item_sha,
                        "validation_status": item_status,
                        "rejection_reason": item_reason,
                    }
                )

            if same_batch is not None and persisted_items and all(
                item["validation_status"] == "duplicate" for item in persisted_items
            ):
                batch_status = "duplicate"
                batch_reason = None

            should_insert_attempt = batch_status != "duplicate"
            if should_insert_attempt:
                receive_id = f"prediction-inbox-{uuid.uuid4()}"
                connection.execute(
                    """
                    INSERT INTO pm_prediction_result_inbox_batches(
                        receive_id,organization_id,project_id,workspace_id,batch_id,
                        payload_sha256,validation_status,rejection_reason,
                        raw_payload,promotion_result_id,received_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,NULL,%s,%s)
                    """,
                    (
                        receive_id,
                        organization_id,
                        project_id,
                        workspace_id,
                        batch_id,
                        payload_sha256,
                        batch_status,
                        batch_reason,
                        json.dumps(raw_payload, sort_keys=True),
                        received_at,
                        now,
                    ),
                )
                for item in persisted_items:
                    if item["validation_status"] == "duplicate":
                        continue
                    raw_item = next(
                        (
                            raw
                            for raw in raw_items
                            if str(raw.get("event_id")) == item["event_id"]
                        ),
                        {},
                    )
                    connection.execute(
                        """
                        INSERT INTO pm_prediction_result_inbox_items(
                            receive_item_id,receive_id,
                            organization_id,project_id,workspace_id,batch_id,event_id,
                            payload_sha256,validation_status,rejection_reason,
                            raw_item,promotion_result_id,received_at,updated_at
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,NULL,%s,%s)
                        """,
                        (
                            f"prediction-inbox-item-{uuid.uuid4()}",
                            receive_id,
                            organization_id,
                            project_id,
                            workspace_id,
                            batch_id,
                            item["event_id"],
                            item["payload_sha256"],
                            item["validation_status"],
                            item["rejection_reason"],
                            json.dumps(raw_item, sort_keys=True),
                            received_at,
                            now,
                        ),
                    )

        return {
            "batch_id": batch_id,
            "payload_sha256": payload_sha256,
            "validation_status": batch_status,
            "rejection_reason": batch_reason,
            "item_receipts": persisted_items,
        }

    def prediction_batch_promotion_context(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        batch_id: str,
    ) -> dict[str, Any] | None:
        with self._connection(organization_id, project_id) as connection:
            batch = connection.execute(
                """
                SELECT receive_id,batch_id,raw_payload,promotion_result_id
                FROM pm_prediction_result_inbox_batches
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                  AND batch_id=%s AND validation_status='accepted'
                ORDER BY received_at DESC
                LIMIT 1
                """,
                (organization_id, project_id, workspace_id, batch_id),
            ).fetchone()
            if batch is None:
                return None
            raw_payload = dict(batch["raw_payload"])
            source_context = raw_payload.get("source_context") or {}
            dataset_id = str(source_context.get("dataset_id") or "")
            source_version = str(source_context.get("dataset_version") or "")
            dataset = connection.execute(
                """
                SELECT v.id AS dataset_version_id,v.source_version,v.version_number,
                       v.checksum_sha256 AS bundle_checksum_sha256,
                       v.record_count,v.status AS dataset_status,
                       d.display_name AS dataset_name
                FROM dataset_versions v
                JOIN datasets d ON d.id=v.dataset_id
                WHERE v.organization_id=%s AND v.project_id=%s AND v.workspace_id=%s
                  AND v.dataset_id=%s
                  AND (v.id=%s OR v.source_version=%s)
                ORDER BY v.version_number DESC
                LIMIT 1
                """,
                (
                    organization_id,
                    project_id,
                    workspace_id,
                    dataset_id,
                    source_version,
                    source_version,
                ),
            ).fetchone()
            if dataset is None:
                raise ValueError(
                    "prediction batch source_context does not resolve to a Dataset Version"
                )
            accepted_items = connection.execute(
                """
                SELECT event_id,promotion_result_id
                FROM pm_prediction_result_inbox_items
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                  AND batch_id=%s AND validation_status='accepted'
                """,
                (organization_id, project_id, workspace_id, batch_id),
            ).fetchall()
            asset_ids = sorted(
                {
                    str(item.get("asset_id"))
                    for item in raw_payload.get("results", [])
                    if isinstance(item, dict) and item.get("asset_id")
                }
            )
            assets = {}
            if asset_ids:
                asset_rows = connection.execute(
                    """
                    -- pm_assets does not yet own authoritative criticality.
                    -- Until Equipment metadata is wired through this port, promotion
                    -- materialization must expose asset.criticality as an evidence gap.
                    SELECT asset_id,asset_type,site_id,cell_id
                    FROM pm_assets
                    WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                      AND dataset_version_id=%s AND asset_id = ANY(%s)
                    """,
                    (
                        organization_id,
                        project_id,
                        workspace_id,
                        dataset["dataset_version_id"],
                        asset_ids,
                    ),
                ).fetchall()
                assets = {str(row["asset_id"]): dict(row) for row in asset_rows}
        return {
            **dict(dataset),
            "batch_id": str(batch["batch_id"]),
            "raw_payload": raw_payload,
            "already_promoted_batch": batch["promotion_result_id"],
            "accepted_items": [dict(row) for row in accepted_items],
            "assets": assets,
        }

    def save_prediction_batch_promotions(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        batch_id: str,
        dataset_version_id: str,
        promotions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        item_receipts: list[dict[str, Any]] = []
        now = self._now()
        with self._connection(organization_id, project_id) as connection:
            receive = connection.execute(
                """
                SELECT receive_id,promotion_result_id
                FROM pm_prediction_result_inbox_batches
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                  AND batch_id=%s AND validation_status='accepted'
                ORDER BY received_at DESC
                LIMIT 1
                FOR UPDATE
                """,
                (organization_id, project_id, workspace_id, batch_id),
            ).fetchone()
            if receive is None:
                raise KeyError(batch_id)

            for promotion in promotions:
                event_id = str(promotion["event_id"])
                artifact = dict(promotion["artifact"])
                prediction_result_id = str(promotion["prediction_result_id"])
                artifact_id = str(artifact["artifact_id"])
                prediction_id = str(artifact["provenance"]["prediction_id"])
                model_version = str(artifact["provenance"]["model_version"])
                source_sha256 = str(promotion["source_sha256"])
                existing = connection.execute(
                    """
                    SELECT artifact_id,prediction_result_id
                    FROM pm_result_artifacts
                    WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                      AND dataset_version_id=%s AND artifact_id=%s
                    FOR UPDATE
                    """,
                    (
                        organization_id,
                        project_id,
                        workspace_id,
                        dataset_version_id,
                        artifact_id,
                    ),
                ).fetchone()
                if existing is not None:
                    item_receipts.append(
                        {
                            "event_id": event_id,
                            "promotion_status": "already_promoted",
                            "product_result_id": str(existing["prediction_result_id"]),
                            "artifact_id": str(existing["artifact_id"]),
                            "reason": None,
                        }
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO prediction_results(
                            prediction_id,organization_id,project_id,workspace_id,
                            subject_object_type,subject_object_id,prediction_status,
                            model_version,dataset_version,payload_json,created_at,received_at
                        ) VALUES (%s,%s,%s,%s,'equipment',%s,%s,%s,%s,%s::jsonb,%s,%s)
                        """,
                        (
                            prediction_result_id,
                            organization_id,
                            project_id,
                            workspace_id,
                            artifact["asset_id"],
                            artifact["status_grade"],
                            model_version,
                            artifact["provenance"]["dataset_version"],
                            json.dumps(artifact, sort_keys=True),
                            artifact["generated_at"],
                            now,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO pm_prediction_snapshots(
                            organization_id,project_id,workspace_id,dataset_version_id,
                            prediction_id,prediction_result_id,asset_id,asset_type,observed_at,
                            prediction_horizon_hours,failure_probability,predicted_failure_type,
                            confidence,status,model_version,feature_scope,source_sha256
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,24,%s,%s,%s,%s,%s,%s::jsonb,%s)
                        """,
                        (
                            organization_id,
                            project_id,
                            workspace_id,
                            dataset_version_id,
                            prediction_id,
                            prediction_result_id,
                            artifact["asset_id"],
                            artifact["asset_type"],
                            artifact["observed_at"],
                            artifact["failure_probability"],
                            artifact["predicted_failure_type"],
                            artifact["confidence"],
                            artifact["status_grade"],
                            model_version,
                            json.dumps({"source": "generator_prediction_result_batch"}, sort_keys=True),
                            source_sha256,
                        ),
                    )
                    for factor in artifact["top_factors"]:
                        signed = float(factor["signed_contribution"])
                        connection.execute(
                            """
                            INSERT INTO pm_prediction_factors(
                                organization_id,project_id,workspace_id,dataset_version_id,
                                prediction_id,rank,feature,feature_value,signed_contribution,
                                absolute_contribution,direction,explanation_method,source_type,
                                source_sha256
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                      'generator_prediction_result_batch',%s)
                            """,
                            (
                                organization_id,
                                project_id,
                                workspace_id,
                                dataset_version_id,
                                prediction_id,
                                int(factor["rank"]),
                                factor["feature"],
                                float(factor["feature_value"]),
                                signed,
                                abs(signed),
                                factor["direction"],
                                factor["explanation_method"],
                                source_sha256,
                            ),
                        )
                    connection.execute(
                        """
                        INSERT INTO pm_prediction_timeline(
                            organization_id,project_id,workspace_id,dataset_version_id,
                            prediction_id,asset_id,asset_type,observed_at,
                            prediction_horizon_hours,failure_probability,status,top_factors,
                            model_version,feature_scope,source_type,source_sha256
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,24,%s,%s,%s::jsonb,%s,%s::jsonb,
                                  'generator_prediction_result_batch',%s)
                        """,
                        (
                            organization_id,
                            project_id,
                            workspace_id,
                            dataset_version_id,
                            prediction_id,
                            artifact["asset_id"],
                            artifact["asset_type"],
                            artifact["observed_at"],
                            artifact["failure_probability"],
                            artifact["status_grade"],
                            json.dumps(artifact["top_factors"], sort_keys=True),
                            model_version,
                            json.dumps({"source": "generator_prediction_result_batch"}, sort_keys=True),
                            source_sha256,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO pm_result_artifacts(
                            organization_id,project_id,workspace_id,dataset_version_id,
                            artifact_id,prediction_id,prediction_result_id,asset_id,asset_type,
                            observed_at,prediction_horizon_hours,prediction_task,
                            failure_probability,predicted_failure_type,status_grade,confidence,
                            top_factors,recommended_action,provenance,schema_version,
                            model_version,source_sha256
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,24,
                                  'binary_failure_within_horizon',%s,%s,%s,%s,%s::jsonb,
                                  %s::jsonb,%s::jsonb,'result-artifact-v1.0',%s,%s)
                        """,
                        (
                            organization_id,
                            project_id,
                            workspace_id,
                            dataset_version_id,
                            artifact_id,
                            prediction_id,
                            prediction_result_id,
                            artifact["asset_id"],
                            artifact["asset_type"],
                            artifact["observed_at"],
                            artifact["failure_probability"],
                            artifact["predicted_failure_type"],
                            artifact["status_grade"],
                            artifact["confidence"],
                            json.dumps(artifact["top_factors"], sort_keys=True),
                            json.dumps(artifact["recommended_action"], sort_keys=True),
                            json.dumps(artifact["provenance"], sort_keys=True),
                            model_version,
                            source_sha256,
                        ),
                    )
                    item_receipts.append(
                        {
                            "event_id": event_id,
                            "promotion_status": "promoted",
                            "product_result_id": prediction_result_id,
                            "artifact_id": artifact_id,
                            "reason": None,
                        }
                    )
                connection.execute(
                    """
                    UPDATE pm_prediction_result_inbox_items
                    SET promotion_result_id=%s, updated_at=%s
                    WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                      AND batch_id=%s AND event_id=%s AND validation_status='accepted'
                    """,
                    (
                        prediction_result_id,
                        now,
                        organization_id,
                        project_id,
                        workspace_id,
                        batch_id,
                        event_id,
                    ),
                )
            if item_receipts:
                first_product_result_id = next(
                    (
                        item["product_result_id"]
                        for item in item_receipts
                        if item.get("product_result_id")
                    ),
                    None,
                )
                connection.execute(
                    """
                    UPDATE pm_prediction_result_inbox_batches
                    SET promotion_result_id=%s, updated_at=%s
                    WHERE receive_id=%s
                    """,
                    (first_product_result_id, now, receive["receive_id"]),
                )
        return {"item_receipts": item_receipts}

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
