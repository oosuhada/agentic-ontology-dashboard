from __future__ import annotations

import csv
import asyncio
import inspect
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from ontology_dashboard.adapters import (
    BundleFileAdapter,
    PostgreSQLPredictiveMaintenanceBundleIngestor,
    PredictiveMaintenanceCanonicalV2Adapter,
)
from ontology_dashboard.predictive_maintenance_runtime import (
    PredictiveMaintenanceRuntimeRepository,
    PredictiveMaintenanceRuntimeService,
)
from ontology_dashboard.dependencies import (
    get_identity_service,
    get_predictive_maintenance_runtime_service,
)
from ontology_dashboard.identity import AuthError, CSRF_COOKIE, Principal, SESSION_COOKIE
from ontology_dashboard.main import app
from ontology_dashboard.routers.predictive_maintenance_runtime import replay_events
from predictive_maintenance_v3_helpers import (
    create_small_v3_package,
    refresh_v3_contracts,
)
from test_predictive_maintenance_bundle_adapter import (
    create_small_package,
    refresh_contracts,
)
from test_predictive_maintenance_postgresql import postgresql_database


REAL_V3_ROOT = (
    Path(__file__).resolve().parents[2]
    / "predictive_maintenance_canonical_v3.1"
)


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


class RuntimeIdentity:
    def __init__(self) -> None:
        self.principal = Principal(
            user_id="runtime-user",
            organization_id="org-test",
            email="runtime@example.com",
            display_name="Runtime User",
            status="active",
            roles=["process_engineer"],
            permissions=["events.read", "governance.read"],
            workspace_scopes=["workspace-test"],
            project_scopes=["project-test"],
            project_roles={"project-test": ["process_engineer"]},
            active_project_id="project-test",
            active_project_roles=["process_engineer"],
            is_admin=False,
            default_path="/app",
            landing_key="process_engineer",
        )

    def principal_for_token(self, *_args, **_kwargs) -> Principal:
        return self.principal

    @staticmethod
    def require_permission(principal: Principal, permission: str) -> None:
        if permission not in principal.permissions:
            raise AuthError(403, "permission_denied", "denied")

    @staticmethod
    def require_project(principal: Principal, project_id: str) -> None:
        if project_id not in principal.project_scopes:
            raise AuthError(403, "project_scope_denied", "denied")

    @staticmethod
    def require_workspace(principal: Principal, workspace_id: str) -> None:
        if workspace_id not in principal.workspace_scopes:
            raise AuthError(403, "workspace_scope_denied", "denied")

    @staticmethod
    def verify_csrf(cookie_value: str | None, header_value: str | None) -> None:
        if not cookie_value or cookie_value != header_value:
            raise AuthError(403, "csrf_validation_failed", "denied")


class ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


def _append_csv(path: Path, row: dict[str, object]) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    rows.append({key: row[key] for key in fieldnames})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _extend_replay_clock(root: Path) -> None:
    dataset = root / "canonical" / "dataset"
    model = root / "canonical" / "model_outputs"
    second_time = "2026-08-01T02:00:00+09:00"
    _append_csv(
        dataset / "compressor_sensor_observation.csv",
        {
            "observed_at": second_time,
            "asset_id": "CMP-001",
            "site_id": "S01",
            "cell_id": "S01-L01",
            "is_operating": 1,
            "operating_state": "running",
            "voltage_raw": 221.0,
            "rotation_raw": 1510.0,
            "pressure_raw": 7.1,
            "vibration_raw": 0.21,
            "relative_vibration_z": 0.11,
            "relative_vibration_zone": "normal",
            "generator_version": "canonical-ai4i-physics-v3.1",
        },
    )
    _append_csv(
        dataset / "cnc_sensor_observation.csv",
        {
            "observed_at": second_time,
            "asset_id": "CNC-001",
            "site_id": "S01",
            "cell_id": "S01-L01",
            "is_operating": 1,
            "operating_state": "running",
            "product_type": "H",
            "air_temperature_k": 301.0,
            "process_temperature_k": 312.0,
            "rotational_speed_rpm": 1300,
            "torque_nm": 42.0,
            "tool_wear_min": 12.0,
            "generator_version": "canonical-ai4i-physics-v3.1",
        },
    )
    timeline_path = model / "prediction_timeline.jsonl"
    rows = [
        json.loads(line)
        for line in timeline_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for asset_id, asset_type, probability in (
        ("CMP-001", "compressor", 0.25),
        ("CNC-001", "cnc", 0.35),
    ):
        rows.append(
            {
                "prediction_id": f"{asset_id}#{second_time}",
                "asset_id": asset_id,
                "asset_type": asset_type,
                "observed_at": second_time,
                "prediction_horizon_hours": 24,
                "failure_probability": probability,
                "status": "attention",
                "top_factors": ["feature-a"],
                "model_version": "independent-logreg-v3.1",
                "feature_scope": "independent",
                "source_type": "derived_replay_prediction",
            }
        )
    timeline_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    refresh_v3_contracts(root)


def _ingest(
    database_url: str,
    root: Path,
    *,
    manifest_id: str,
):
    manifest = PredictiveMaintenanceCanonicalV2Adapter.build_manifest(
        root,
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        manifest_id=manifest_id,
    )
    validation = BundleFileAdapter(allowed_roots=[root]).validate(manifest)
    assert validation.status == "completed"
    result = PostgreSQLPredictiveMaintenanceBundleIngestor(
        database_url
    ).ingest_validated_bundle(manifest=manifest, validation=validation)
    return manifest, result


def _runtime(
    database_url: str,
    clock: MutableClock | None = None,
) -> PredictiveMaintenanceRuntimeService:
    return PredictiveMaintenanceRuntimeService(
        PredictiveMaintenanceRuntimeRepository(
            database_url,
            clock=clock,
        )
    )


def test_v3_result_artifact_mapping_observation_query_and_replay_controls(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg.rows import dict_row

    root = create_small_v3_package(tmp_path / "v3")
    _extend_replay_clock(root)
    manifest, ingestion = _ingest(
        postgresql_database,
        root,
        manifest_id="pm-runtime-v3",
    )
    clock = MutableClock(datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc))
    service = _runtime(postgresql_database, clock)

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        before_work_orders = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM ontology_objects WHERE object_type='work_order'"
            ).fetchone()["count"]
        )
        connection.execute(
            """
            UPDATE store_projections
            SET status='failed',last_error='graph projection offline'
            WHERE dataset_version_id=%s AND store_kind='graph'
            """,
            (ingestion.dataset_version_id,),
        )

    page = service.latest_results(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_version_id=ingestion.dataset_version_id,
        limit=100,
    )
    assert page.latest_product_contract == "result_artifact"
    assert page.total == len(page.items) == 2
    assert page.context.source_version == "canonical-ai4i-physics-v3.1"
    assert page.context.bundle_checksum_sha256 == manifest.bundle_checksum_sha256
    assert page.context.graph.status == "failed"
    assert page.context.graph.required_for_runtime is False
    assert page.context.governance.tool_wear_continuity == {
        "pass": True,
        "running_reset_count": 0,
        "tool_replacement_event_count": 731,
        "aligned_reset_transition_count": 731,
        "reset_without_matching_maintenance_count": 0,
        "replacement_without_reset_count": 0,
    }
    rendered_governance = json.dumps(
        page.context.governance.model_dump(mode="json"),
        ensure_ascii=False,
    ).lower()
    for forbidden in (
        "event_condition_details",
        "failure_mode_conditions",
        "condition_variant",
        "hidden_truth",
        "evaluation_truth",
    ):
        assert forbidden not in rendered_governance

    for item in page.items:
        assert item.provenance.prediction_id in item.artifact_id
        assert item.provenance.prediction_result_id == item.prediction_result.prediction_id
        assert item.provenance.source_version == "canonical-ai4i-physics-v3.1"
        assert item.provenance.model_version == "independent-logreg-v3.1"
        assert item.provenance.schema_version == "result-artifact-v1.0"
        assert item.prediction_task == "binary_failure_within_horizon"
        assert item.predicted_failure_type in {
            "failure_risk",
            "no_significant_risk",
        }
        assert item.predicted_failure_type not in {"PWF", "HDF", "OSF", "TWF"}
        assert item.recommended_action is not None
        assert item.recommended_action.execution_state == "not_executed"
        assert item.recommended_action.creates_work_order_automatically is False
        assert item.prediction_result.recommended_actions[0].requires_approval is True

    prediction_schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "prediction-result.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert list(
        Draft202012Validator(
            prediction_schema,
            format_checker=FormatChecker(),
        ).iter_errors(page.items[0].prediction_result.model_dump(mode="json"))
    ) == []

    with psycopg.connect(postgresql_database) as connection:
        connection.execute(
            """
            UPDATE pm_result_artifacts SET model_version='invalid-model'
            WHERE dataset_version_id=%s AND artifact_id=%s
            """,
            (ingestion.dataset_version_id, page.items[0].artifact_id),
        )
    with pytest.raises(ValueError, match="model/schema provenance mismatch"):
        service.latest_results(
            organization_id="org-test",
            project_id="project-test",
            workspace_id="workspace-test",
            dataset_version_id=ingestion.dataset_version_id,
            limit=100,
        )
    with psycopg.connect(postgresql_database) as connection:
        connection.execute(
            """
            UPDATE pm_result_artifacts SET model_version='independent-logreg-v3.1'
            WHERE dataset_version_id=%s AND artifact_id=%s
            """,
            (ingestion.dataset_version_id, page.items[0].artifact_id),
        )

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        after_work_orders = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM ontology_objects WHERE object_type='work_order'"
            ).fetchone()["count"]
        )
    assert after_work_orders == before_work_orders

    at = datetime.fromisoformat("2026-08-01T01:00:00+09:00")
    observations = service.observations(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_version_id=ingestion.dataset_version_id,
        start=at,
        end=at,
        asset_id=None,
        site_id="S01",
        cell_id="S01-L01",
        asset_type=None,
        grain="raw",
        derived_measures={"power_w", "temperature_gap_k", "overstrain_load"},
        limit=100,
    )
    assert observations.returned_observation_count == 2
    compressor = next(
        item for item in observations.observations if item.asset_type == "compressor"
    )
    cnc = next(item for item in observations.observations if item.asset_type == "cnc")
    assert compressor.measurements["pressure_raw"] == 7.0
    assert cnc.measurements["torque_nm"] == 40.0
    assert cnc.derived_measures["power_w"] == pytest.approx(
        40.0 * 1200 * 2 * math.pi / 60
    )
    assert cnc.derived_measures["temperature_gap_k"] == pytest.approx(10.0)
    assert cnc.derived_measures["overstrain_load"] == pytest.approx(400.0)
    assert {item.observed_at for item in observations.nearest_predictions} == {at}
    assert observations.source_rows_mutated is False

    replay = service.create_replay(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        user_id="user-test",
        dataset_version_id=ingestion.dataset_version_id,
        start_time=at,
        speed=1.0,
    )
    assert replay.cursor.state == "running"
    assert replay.cursor.model_retrained is False
    assert replay.truth_exposed is False
    assert replay.sensor_values_generated is False
    assert replay.canonical_sensor_time == at
    assert replay.nearest_prediction_time == at

    clock.advance(seconds=30)
    advanced = service.replay_snapshot(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        session_id=replay.cursor.session_id,
    )
    assert advanced.cursor.simulation_time == at + timedelta(minutes=30)
    assert advanced.canonical_sensor_time == at

    paused = service.control_replay(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        session_id=replay.cursor.session_id,
        action="pause",
    )
    paused_time = paused.cursor.simulation_time
    clock.advance(seconds=120)
    still_paused = service.replay_snapshot(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        session_id=replay.cursor.session_id,
    )
    assert still_paused.cursor.state == "paused"
    assert still_paused.cursor.simulation_time == paused_time

    speed_changed = service.control_replay(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        session_id=replay.cursor.session_id,
        action="speed",
        speed=2.0,
    )
    assert speed_changed.cursor.speed_minutes_per_second == 2.0
    service.control_replay(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        session_id=replay.cursor.session_id,
        action="resume",
    )
    clock.advance(seconds=15)
    completed = service.replay_snapshot(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        session_id=replay.cursor.session_id,
    )
    assert completed.cursor.simulation_time == datetime.fromisoformat(
        "2026-08-01T02:00:00+09:00"
    )
    assert completed.cursor.state == "completed"
    assert completed.canonical_sensor_time == completed.cursor.dataset_end
    assert completed.nearest_prediction_time == completed.cursor.dataset_end

    seeked = service.control_replay(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        session_id=replay.cursor.session_id,
        action="seek",
        time_value=at,
    )
    assert seeked.cursor.state == "paused"
    assert seeked.cursor.simulation_time == at
    assert seeked.nearest_prediction_time == at
    assert "train" not in inspect.getsource(
        PredictiveMaintenanceRuntimeService.control_replay
    ).lower()
    assert "train" not in inspect.getsource(
        PredictiveMaintenanceRuntimeRepository.update_session
    ).lower()

    with pytest.raises(ValueError, match="inside Dataset Version"):
        service.control_replay(
            organization_id="org-test",
            project_id="project-test",
            workspace_id="workspace-test",
            session_id=replay.cursor.session_id,
            action="seek",
            time_value=at - timedelta(minutes=10),
        )
    with pytest.raises(KeyError):
        service.replay_snapshot(
            organization_id="org-test",
            project_id="project-other",
            workspace_id="workspace-other",
            session_id=replay.cursor.session_id,
        )


def test_v2_latest_product_result_uses_snapshot_factor_compatibility(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    root = create_small_package(tmp_path / "v2")
    refresh_contracts(root)
    _, ingestion = _ingest(
        postgresql_database,
        root,
        manifest_id="pm-runtime-v2",
    )
    service = _runtime(postgresql_database)
    page = service.latest_results(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_version_id=ingestion.dataset_version_id,
        limit=100,
    )
    assert page.latest_product_contract == "prediction_snapshot_compatibility"
    assert page.total == len(page.items) == 2
    assert all(item.artifact_id is None for item in page.items)
    assert all(item.recommended_action is None for item in page.items)
    assert all(
        item.predicted_failure_type in {"failure_risk", "no_significant_risk"}
        for item in page.items
    )
    assert all(
        item.provenance.schema_version == "prediction-snapshot-compat-v1"
        for item in page.items
    )


def test_v2_v3_runtime_versions_and_release_overview_are_immutable(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    v2_root = create_small_package(tmp_path / "versions-v2")
    refresh_contracts(v2_root)
    _, v2_ingestion = _ingest(
        postgresql_database,
        v2_root,
        manifest_id="pm-runtime-versions-v2",
    )
    v3_root = create_small_v3_package(tmp_path / "versions-v3")
    _, v3_ingestion = _ingest(
        postgresql_database,
        v3_root,
        manifest_id="pm-runtime-versions-v3",
    )
    import psycopg

    with psycopg.connect(postgresql_database) as connection:
        connection.execute(
            "UPDATE dataset_versions SET status='published' WHERE id IN (%s,%s)",
            (v2_ingestion.dataset_version_id, v3_ingestion.dataset_version_id),
        )
    service = _runtime(postgresql_database)

    versions = service.versions(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
    )
    assert versions.rollback_supported is True
    assert versions.immutable_versioning is True
    assert versions.default_dataset_version_id == v3_ingestion.dataset_version_id
    assert versions.selection_mode == "automatic"
    assert versions.selection_reason == "canonical_v3_1_release_ready"
    assert {item.dataset_version_id for item in versions.items} == {
        v2_ingestion.dataset_version_id,
        v3_ingestion.dataset_version_id,
    }
    v3 = next(item for item in versions.items if item.dataset_version_id == v3_ingestion.dataset_version_id)
    assert v3.is_v3_1 is True
    assert v3.result_artifact_count == 2
    assert v3.model_version == "independent-logreg-v3.1"
    assert v3.result_artifact_schema_version == "result-artifact-v1.0"
    assert v3.prediction_task == "binary_failure_within_horizon"
    assert v3.release_ready is True

    explicit = service.select_version(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        user_id="runtime-user",
        dataset_version_id=v2_ingestion.dataset_version_id,
    )
    assert explicit.default_dataset_version_id == v2_ingestion.dataset_version_id
    assert explicit.selection_mode == "explicit"
    assert explicit.selection_reason == "explicit_user_selection"
    other_user = service.versions(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        user_id="runtime-user-other",
    )
    assert other_user.default_dataset_version_id == v3_ingestion.dataset_version_id
    with pytest.raises(KeyError):
        service.select_version(
            organization_id="org-test",
            project_id="project-other",
            workspace_id="workspace-other",
            user_id="runtime-user",
            dataset_version_id=v3_ingestion.dataset_version_id,
        )

    dashboard = service.dashboard(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        user_id="runtime-user-other",
        dataset_version_id=None,
        selected_event_id=None,
        role="engineer",
        intent="overview",
        locale="ko-KR",
    )
    assert dashboard.data_source.dataset_version_id == v3_ingestion.dataset_version_id
    assert dashboard.data_source.source_version == "canonical-ai4i-physics-v3.1"
    assert dashboard.data_source.model_version == "independent-logreg-v3.1"
    assert dashboard.data_source.result_artifact_count == 2
    assert dashboard.events
    assert dashboard.selected_event_detail is not None
    assert dashboard.selected_event_detail.evidence["lineage"]["dataset_version_id"] == (
        v3_ingestion.dataset_version_id
    )
    assert dashboard.selected_event_detail.report["locale"] == "ko-KR"
    assert "고장 위험" in dashboard.selected_event_detail.report["headline"]

    english_dashboard = service.dashboard(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        user_id="runtime-user-other",
        dataset_version_id=None,
        selected_event_id=dashboard.selected_event_id,
        role="engineer",
        intent="overview",
        locale="en-US",
    )
    assert english_dashboard.selected_event_detail is not None
    assert english_dashboard.selected_event_detail.report["locale"] == "en-US"
    assert "failure risk" in english_dashboard.selected_event_detail.report["headline"]
    assert (
        dashboard.selected_event_detail.report["report_id"]
        != english_dashboard.selected_event_detail.report["report_id"]
    )

    overview = service.release_overview(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_version_id=v3_ingestion.dataset_version_id,
    )
    assert overview.immutable_upgrade_verified is True
    assert overview.result_artifact_coverage == 2
    assert overview.hidden_truth_exposed is False
    assert overview.evaluation_truth_exposed is False
    assert overview.active.prediction_task == "binary_failure_within_horizon"
    assert overview.active.semantic_catalog_version == "predictive-maintenance-semantic-v3.1"
    rendered = json.dumps(overview.model_dump(mode="json")).lower()
    assert "event_condition_details" not in rendered
    assert "condition_variant" not in rendered


def test_result_replay_http_and_sse_contracts_are_scoped(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    root = create_small_v3_package(tmp_path / "api-v3")
    _extend_replay_clock(root)
    _, ingestion = _ingest(
        postgresql_database,
        root,
        manifest_id="pm-runtime-api",
    )
    clock = MutableClock(datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc))
    runtime = _runtime(postgresql_database, clock)
    identity = RuntimeIdentity()
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_predictive_maintenance_runtime_service] = (
        lambda: runtime
    )
    try:
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE, "runtime-token")
            client.cookies.set(CSRF_COOKIE, "runtime-csrf")
            headers = {"X-CSRF-Token": "runtime-csrf"}
            base = "/api/projects/project-test/workspaces/workspace-test/predictive-maintenance"

            context = client.get(
                f"{base}/context",
                params={"dataset_version_id": ingestion.dataset_version_id},
            )
            assert context.status_code == 200, context.text
            assert context.json()["dataset_version_id"] == ingestion.dataset_version_id

            versions = client.get(f"{base}/versions")
            assert versions.status_code == 200, versions.text
            assert versions.json()["default_dataset_version_id"] == ingestion.dataset_version_id
            assert versions.json()["items"][0]["release_ready"] is True

            release = client.get(
                f"{base}/release",
                params={"dataset_version_id": ingestion.dataset_version_id},
            )
            assert release.status_code == 200, release.text
            assert release.json()["hidden_truth_exposed"] is False
            assert release.json()["evaluation_truth_exposed"] is False

            latest = client.get(
                f"{base}/results/latest",
                params={"dataset_version_id": ingestion.dataset_version_id},
            )
            assert latest.status_code == 200, latest.text
            assert latest.json()["latest_product_contract"] == "result_artifact"

            timeline = client.get(
                f"{base}/timeline",
                params={
                    "dataset_version_id": ingestion.dataset_version_id,
                    "limit": 10,
                },
            )
            assert timeline.status_code == 200, timeline.text
            assert timeline.json()["source"] == "precomputed_prediction_timeline"
            assert timeline.json()["model_retrained"] is False

            start = client.post(
                f"{base}/replay/sessions",
                headers=headers,
                json={
                    "dataset_version_id": ingestion.dataset_version_id,
                    "start_time": "2026-08-01T01:00:00+09:00",
                    "speed_minutes_per_second": 1,
                },
            )
            assert start.status_code == 201, start.text
            session_id = start.json()["cursor"]["session_id"]
            assert start.json()["context"]["dataset_version_id"] == (
                ingestion.dataset_version_id
            )

            pause = client.post(
                f"{base}/replay/sessions/{session_id}/pause",
                headers=headers,
                json={},
            )
            assert pause.status_code == 200, pause.text
            assert pause.json()["cursor"]["state"] == "paused"

            async def first_sse_event() -> str:
                response = await replay_events(
                    request=ConnectedRequest(),
                    project_id="project-test",
                    workspace_id="workspace-test",
                    session_id=session_id,
                    principal=identity.principal,
                    identity=identity,
                    service=runtime,
                )
                iterator = response.body_iterator
                try:
                    return await iterator.__anext__()
                finally:
                    if hasattr(iterator, "aclose"):
                        await iterator.aclose()

            chunk = asyncio.run(first_sse_event())
            data_line = next(
                line for line in chunk.splitlines() if line.startswith("data: ")
            )
            event = json.loads(data_line.removeprefix("data: "))
            assert event["context"]["project_id"] == "project-test"
            assert event["context"]["workspace_id"] == "workspace-test"
            assert event["context"]["dataset_version_id"] == (
                ingestion.dataset_version_id
            )

            wrong_workspace = client.get(
                "/api/projects/project-test/workspaces/workspace-other/predictive-maintenance/context"
            )
            assert wrong_workspace.status_code == 403
            unknown_version = client.get(
                f"{base}/context",
                params={"dataset_version_id": "dsv-not-visible"},
            )
            assert unknown_version.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_real_v3_1_result_artifact_and_replay_row_parity(
    postgresql_database: str,
) -> None:
    if not REAL_V3_ROOT.is_dir():
        pytest.skip("real predictive_maintenance_canonical_v3.1 package is unavailable")
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(postgresql_database) as connection:
        connection.execute(
            """
            INSERT INTO organizations(id,slug,name)
            VALUES ('org-ontology-demo','org-ontology-demo','Ontology Demo')
            ON CONFLICT(id) DO NOTHING;
            INSERT INTO projects(
                id,organization_id,slug,display_name,domain_pack_code
            ) VALUES (
                'predictive-maintenance-v2','org-ontology-demo',
                'predictive-maintenance-v2','Predictive Maintenance',
                'predictive-maintenance'
            ) ON CONFLICT(id) DO NOTHING;
            INSERT INTO workspaces(
                id,organization_id,project_id,slug,display_name,domain_pack
            ) VALUES (
                'predictive-maintenance-main','org-ontology-demo',
                'predictive-maintenance-v2','predictive-maintenance-main',
                'Predictive Maintenance Main','predictive-maintenance'
            ) ON CONFLICT(id) DO NOTHING;
            """
        )

    manifest = PredictiveMaintenanceCanonicalV2Adapter.build_manifest(
        REAL_V3_ROOT,
        organization_id="org-ontology-demo",
        project_id="predictive-maintenance-v2",
        workspace_id="predictive-maintenance-main",
        manifest_id="predictive-maintenance-canonical-v2",
    )
    assert manifest.dataset_version == "canonical-ai4i-physics-v3.1"
    assert manifest.bundle_checksum_sha256 == (
        "12734b1eec67ae5ccf322221967d5628ba5cf1ecb0401e6daef5c3dd7a855682"
    )
    validation = BundleFileAdapter(allowed_roots=[REAL_V3_ROOT]).validate(manifest)
    assert validation.status == "completed"
    ingestion = PostgreSQLPredictiveMaintenanceBundleIngestor(
        postgresql_database
    ).ingest_validated_bundle(manifest=manifest, validation=validation)
    assert ingestion.dataset_id == "ds-c68277fe-817c-5a8a-8676-59dea8b39401"
    assert ingestion.dataset_version_id == "dsv-1914858a-cc17-57d8-819c-d8a2435fd805"
    assert ingestion.source_record_count == 672_553
    assert ingestion.row_counts == {
        "asset_master": 100,
        "asset_relation": 80,
        "cnc_production_cycle": 170_875,
        "cnc_sensor_observation": 345_600,
        "compressor_sensor_observation": 86_400,
        "maintenance_event": 790,
        "prediction_factor": 300,
        "prediction_snapshot": 100,
        "prediction_timeline": 68_208,
        "result_artifact": 100,
    }

    service = _runtime(postgresql_database)
    page = service.latest_results(
        organization_id="org-ontology-demo",
        project_id="predictive-maintenance-v2",
        workspace_id="predictive-maintenance-main",
        dataset_version_id=ingestion.dataset_version_id,
        limit=100,
    )
    assert page.latest_product_contract == "result_artifact"
    assert page.total == len(page.items) == 100
    assert {item.asset_id for item in page.items} == {
        item["asset_id"]
        for item in csv.DictReader(
            (REAL_V3_ROOT / "canonical" / "dataset" / "asset_master.csv").open(
                newline="", encoding="utf-8"
            )
        )
    }
    assert all(
        item.provenance.model_version == "independent-logreg-v3.1"
        and item.provenance.schema_version == "result-artifact-v1.0"
        and item.provenance.prediction_task == "binary_failure_within_horizon"
        and item.provenance.source_version == "canonical-ai4i-physics-v3.1"
        and item.provenance.bundle_checksum_sha256
        == "12734b1eec67ae5ccf322221967d5628ba5cf1ecb0401e6daef5c3dd7a855682"
        for item in page.items
    )
    assert {
        item.predicted_failure_type for item in page.items
    }.issubset({"failure_risk", "no_significant_risk"})

    timeline = service.timeline(
        organization_id="org-ontology-demo",
        project_id="predictive-maintenance-v2",
        workspace_id="predictive-maintenance-main",
        dataset_version_id=ingestion.dataset_version_id,
        asset_id=None,
        start=None,
        end=None,
        offset=0,
        limit=1,
    )
    assert timeline["total"] == 68_208
    assert timeline["model_retrained"] is False

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM pm_result_artifacts
               WHERE dataset_version_id=%s) AS artifacts,
              (SELECT COUNT(*) FROM pm_prediction_snapshots
               WHERE dataset_version_id=%s) AS snapshots,
              (SELECT COUNT(*) FROM pm_prediction_factors
               WHERE dataset_version_id=%s) AS factors,
              (SELECT COUNT(*) FROM pm_prediction_timeline
               WHERE dataset_version_id=%s) AS timeline,
              (SELECT COUNT(*) FROM prediction_results p
               JOIN pm_result_artifacts r ON r.prediction_result_id=p.prediction_id
               WHERE r.dataset_version_id=%s) AS linked_prediction_results
            """,
            (ingestion.dataset_version_id,) * 5,
        ).fetchone()
    assert dict(counts) == {
        "artifacts": 100,
        "snapshots": 100,
        "factors": 300,
        "timeline": 68_208,
        "linked_prediction_results": 100,
    }

    sample_time = datetime.fromisoformat("2026-08-04T10:00:00+09:00")
    sample = service.observations(
        organization_id="org-ontology-demo",
        project_id="predictive-maintenance-v2",
        workspace_id="predictive-maintenance-main",
        dataset_version_id=ingestion.dataset_version_id,
        start=sample_time,
        end=sample_time,
        asset_id=None,
        site_id="S01",
        cell_id="S01-L01",
        asset_type=None,
        grain="raw",
        derived_measures={"power_w", "temperature_gap_k", "overstrain_load"},
        limit=10,
    )
    assert sample.returned_observation_count >= 2
    cnc_source_row = next(
        row
        for row in csv.DictReader(
            (
                REAL_V3_ROOT
                / "canonical"
                / "dataset"
                / "cnc_sensor_observation.csv"
            ).open(newline="", encoding="utf-8")
        )
        if row["asset_id"] == "CNC-S01-L01-01"
        and row["observed_at"] == "2026-08-04T10:00:00+09:00"
    )
    compressor_source_row = next(
        row
        for row in csv.DictReader(
            (
                REAL_V3_ROOT
                / "canonical"
                / "dataset"
                / "compressor_sensor_observation.csv"
            ).open(newline="", encoding="utf-8")
        )
        if row["asset_id"] == "CMP-S01-L01-01"
        and row["observed_at"] == "2026-08-04T10:00:00+09:00"
    )
    cnc_observation = next(
        item for item in sample.observations if item.asset_id == "CNC-S01-L01-01"
    )
    compressor_observation = next(
        item for item in sample.observations if item.asset_id == "CMP-S01-L01-01"
    )
    assert cnc_observation.measurements["rotational_speed_rpm"] == float(
        cnc_source_row["rotational_speed_rpm"]
    )
    assert cnc_observation.measurements["torque_nm"] == float(
        cnc_source_row["torque_nm"]
    )
    assert cnc_observation.measurements["tool_wear_min"] == float(
        cnc_source_row["tool_wear_min"]
    )
    assert compressor_observation.measurements["pressure_raw"] == float(
        compressor_source_row["pressure_raw"]
    )
    assert compressor_observation.measurements["vibration_raw"] == float(
        compressor_source_row["vibration_raw"]
    )
    assert cnc_observation.derived_measures["power_w"] == pytest.approx(
        float(cnc_source_row["torque_nm"])
        * float(cnc_source_row["rotational_speed_rpm"])
        * 2
        * math.pi
        / 60
    )
    expected_timeline = next(
        json.loads(line)
        for line in (
            REAL_V3_ROOT
            / "canonical"
            / "model_outputs"
            / "prediction_timeline.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if '"prediction_id": "CNC-S01-L01-01#2026-08-04T10:00:00+09:00"'
        in line
    )
    nearest_cnc = next(
        item
        for item in sample.nearest_predictions
        if item.asset_id == "CNC-S01-L01-01"
    )
    assert nearest_cnc.prediction_id == expected_timeline["prediction_id"]
    assert nearest_cnc.failure_probability == expected_timeline[
        "failure_probability"
    ]
    assert nearest_cnc.status == expected_timeline["status"]
