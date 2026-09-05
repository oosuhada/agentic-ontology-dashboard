from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

from app.dataset.bundle_contract import DatasetBundleManifestV2, compute_bundle_checksum
from app.dataset.ingestion.bundle_file_adapter import BundleFileAdapter
from app.diagnosis.runtime_service import PredictiveMaintenanceRuntimeService
from app.infra.db.agent_run_repository import AgentRunRepository
from app.infra.db.diagnosis_runtime_repository import (
    PredictiveMaintenanceRuntimeRepository,
)
from app.infra.db.migrations import migrate
from app.infra.db.postgresql_bundle_ingestion import PostgreSQLPredictiveMaintenanceBundleIngestor
from app.infra.db.pool import close_pools
from app.infra.live_predictive_maintenance_runtime import (
    _consume_overlay_event,
    _persist_overlay_product_result,
)
from app.infra.runtime_overlay_contract import (
    expected_storage_reference,
    resolve_storage_reference,
    semantic_observation_sha256,
)
from tests.test_predictive_maintenance_bundle_adapter import (
    build_manifest,
    create_small_package,
)
from tests.test_prediction_result_inbox import load_payload
from tests.test_runtime_overlay_output_contract import (
    available_event as runtime_overlay_available_event,
    observation as runtime_overlay_observation,
)


class _RecordingGeneratorRuntimeClient:
    def enqueue(self, payload: dict[str, object]) -> dict[str, object]:
        return {"job_id": payload["job_id"], "status": "queued"}


def _runtime_overlay_input(
    *,
    observed_at: str = "2026-08-18T01:40:00+00:00",
    maintenance_action_id: str = "ACTION-001",
    maintenance_event_id: str = "MAINT-001",
    overlay_branch_id: str = "MAINT-001:post",
    history_segment_id: str = "MAINT-001:post",
    state_version: int = 3,
    event_suffix: str = "1",
) -> tuple[dict[str, object], dict[str, object]]:
    row = copy.deepcopy(runtime_overlay_observation())
    row.update(
        {
            "run_id": f"SESSION-001:overlay:{maintenance_event_id}",
            "asset_id": "CNC-001",
            "equipment_id": "CNC-001",
            "observed_at": observed_at,
            "simulation_session_id": "SESSION-001",
            "overlay_branch_id": overlay_branch_id,
            "maintenance_event_id": maintenance_event_id,
            "maintenance_action_id": maintenance_action_id,
            "state_version": state_version,
            "history_segment_id": history_segment_id,
        }
    )
    row["overlay"] = {
        "overlay_id": overlay_branch_id,
        "parent_branch": "canonical",
        "maintenance_event_id": maintenance_event_id,
        "state_patch_reference": maintenance_action_id,
        "simulation_session_id": "SESSION-001",
        "history_segment_id": history_segment_id,
        "state_version": state_version,
    }
    row["observation_sha256"] = semantic_observation_sha256(row)

    event = copy.deepcopy(runtime_overlay_available_event())
    event.update(
        {
            "event_id": f"OVERLAY-AVAILABLE:{overlay_branch_id}:{event_suffix}",
            "simulation_session_id": "SESSION-001",
            "equipment_id": "CNC-001",
            "maintenance_action_id": maintenance_action_id,
            "maintenance_event_id": maintenance_event_id,
            "overlay_branch_id": overlay_branch_id,
            "history_segment_id": history_segment_id,
            "state_version": state_version,
            "batch_rows": 1,
            "generated_rows": 1,
            "observed_from": observed_at,
            "observed_to": observed_at,
        }
    )
    event["storage_reference"] = expected_storage_reference(event)
    return event, row


def _write_runtime_overlay_input(
    stream_root: Path,
    event: dict[str, object],
    row: dict[str, object],
) -> None:
    path = resolve_storage_reference(stream_root, event)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")


def _postgres_tools_available() -> bool:
    required = ("createdb", "dropdb", "pg_isready")
    if any(shutil.which(command) is None for command in required):
        return False
    return subprocess.run(
        [
            "pg_isready",
            "-h",
            os.getenv("TEST_POSTGRES_HOST", "127.0.0.1"),
            "-p",
            os.getenv("TEST_POSTGRES_PORT", "5432"),
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def _dsn_for_database(database: str) -> str:
    user = os.getenv("TEST_POSTGRES_USER") or subprocess.check_output(
        ["whoami"], text=True
    ).strip()
    password = os.getenv("TEST_POSTGRES_PASSWORD")
    host = os.getenv("TEST_POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("TEST_POSTGRES_PORT", "5432")
    credentials = user if not password else f"{user}:{password}"
    return f"postgresql://{credentials}@{host}:{port}/{database}"


def _dsn_for_user(database_url: str, user: str, password: str | None = None) -> str:
    parsed = urlsplit(database_url)
    host = parsed.hostname or "127.0.0.1"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    credentials = user if not password else f"{user}:{password}"
    return urlunsplit(("postgresql", f"{credentials}@{host}", parsed.path, parsed.query, ""))


def _postgres_cli_env() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PGHOST": os.getenv("TEST_POSTGRES_HOST", "127.0.0.1"),
            "PGPORT": os.getenv("TEST_POSTGRES_PORT", "5432"),
            "PGUSER": os.getenv("TEST_POSTGRES_USER")
            or subprocess.check_output(["whoami"], text=True).strip(),
        }
    )
    if os.getenv("TEST_POSTGRES_PASSWORD"):
        environment["PGPASSWORD"] = os.environ["TEST_POSTGRES_PASSWORD"]
    return environment


@pytest.fixture()
def postgresql_database():
    if not _postgres_tools_available():
        pytest.skip("local disposable PostgreSQL is unavailable")
    database = f"od_pm_test_{uuid.uuid4().hex[:12]}"
    subprocess.run(["createdb", database], check=True, env=_postgres_cli_env())
    dsn = _dsn_for_database(database)
    try:
        applied = migrate(dsn)
        assert "0029_governed_event_automation" in applied
        assert "0030_closed_loop_operations" in applied
        assert "0031_predictive_maintenance_runtime_overlay" in applied
        assert "0032_predictive_maintenance_append_only_results" in applied
        assert "0033_recommendation_materialization_strategy" in applied
        assert "0034_operations_manual_recommendation" in applied
        assert "0035_inspection_results" in applied
        assert "0036_prediction_result_inbox" in applied
        assert migrate(dsn) == []
        import psycopg

        with psycopg.connect(dsn) as connection:
            connection.execute(
                """
                INSERT INTO organizations(id,slug,name) VALUES
                    ('org-test','org-test','Org Test'),
                    ('org-ontology-demo','org-ontology-demo','Ontology Demo');
                INSERT INTO projects(
                    id,organization_id,slug,display_name,domain_pack_code
                ) VALUES
                    ('project-test','org-test','project-test','Project Test','predictive-maintenance'),
                    ('project-other','org-test','project-other','Project Other','predictive-maintenance'),
                    ('manufacturing-demo-project','org-ontology-demo',
                     'manufacturing-demo-project','Manufacturing Demo',
                     'predictive-maintenance');
                INSERT INTO workspaces(
                    id,organization_id,project_id,slug,display_name,domain_pack
                ) VALUES
                    ('workspace-test','org-test','project-test','workspace-test','Workspace Test','predictive-maintenance'),
                    ('workspace-other','org-test','project-other','workspace-other','Workspace Other','predictive-maintenance'),
                    ('manufacturing-demo','org-ontology-demo',
                     'manufacturing-demo-project','manufacturing-demo',
                     'Manufacturing Demo','predictive-maintenance');
                INSERT INTO users(id,organization_id,email,display_name,status) VALUES
                    ('runtime-user','org-test','runtime@example.com','Runtime User','active'),
                    ('runtime-user-other','org-test','runtime-other@example.com','Runtime Other','active');
                """
            )
        yield dsn
    finally:
        close_pools()
        subprocess.run(
            ["dropdb", "--if-exists", database],
            check=False,
            env=_postgres_cli_env(),
        )


def test_postgresql_runtime_overlay_rejects_identity_and_lineage_conflicts(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    package_root = create_small_package(tmp_path)
    manifest = build_manifest(package_root)
    validation = BundleFileAdapter(allowed_roots=[package_root]).validate(manifest)
    ingestor = PostgreSQLPredictiveMaintenanceBundleIngestor(postgresql_database)
    ingestion = ingestor.ingest_validated_bundle(manifest=manifest, validation=validation)
    stream_root = tmp_path / "runtime-output"
    snapshot_root = tmp_path / "runtime-input"
    client = _RecordingGeneratorRuntimeClient()

    event, row = _runtime_overlay_input()
    _write_runtime_overlay_input(stream_root, event, row)
    first = _consume_overlay_event(
        postgresql_database,
        ingestion.dataset_version_id,
        stream_root,
        event,
        dataset_id=ingestion.dataset_id,
        snapshot_root=snapshot_root,
        enqueue_client=client,
    )
    repeated = _consume_overlay_event(
        postgresql_database,
        ingestion.dataset_version_id,
        stream_root,
        event,
        dataset_id=ingestion.dataset_id,
        snapshot_root=snapshot_root,
        enqueue_client=client,
    )
    assert first["reused"] is False
    assert repeated["reused"] is True

    conflicting_row = copy.deepcopy(row)
    conflicting_row["measurements"]["tool_wear_min"] = 1.0
    conflicting_row["tool_wear_min"] = 1.0
    conflicting_row["observation_sha256"] = semantic_observation_sha256(conflicting_row)
    _write_runtime_overlay_input(stream_root, event, conflicting_row)
    with pytest.raises(ValueError, match="observation identity conflict"):
        _consume_overlay_event(
            postgresql_database,
            ingestion.dataset_version_id,
            stream_root,
            event,
            dataset_id=ingestion.dataset_id,
            snapshot_root=snapshot_root,
            enqueue_client=client,
        )

    conflicting_event = {**event, "event_id": "OVERLAY-AVAILABLE:MAINT-001:conflict"}
    _write_runtime_overlay_input(stream_root, conflicting_event, conflicting_row)
    with pytest.raises(ValueError, match="observation identity conflict"):
        _consume_overlay_event(
            postgresql_database,
            ingestion.dataset_version_id,
            stream_root,
            conflicting_event,
            dataset_id=ingestion.dataset_id,
            snapshot_root=snapshot_root,
            enqueue_client=client,
        )

    reused_branch_event, reused_branch_row = _runtime_overlay_input(
        observed_at="2026-08-18T01:50:00+00:00",
        maintenance_action_id="ACTION-002",
        maintenance_event_id="MAINT-002",
        overlay_branch_id=str(event["overlay_branch_id"]),
        history_segment_id="MAINT-002:post",
        state_version=4,
        event_suffix="2",
    )
    _write_runtime_overlay_input(stream_root, reused_branch_event, reused_branch_row)
    with pytest.raises(ValueError, match="branch lineage conflict"):
        _consume_overlay_event(
            postgresql_database,
            ingestion.dataset_version_id,
            stream_root,
            reused_branch_event,
            dataset_id=ingestion.dataset_id,
            snapshot_root=snapshot_root,
            enqueue_client=client,
        )


def test_postgresql_runtime_overlay_serializes_same_event_retries(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    package_root = create_small_package(tmp_path)
    manifest = build_manifest(package_root)
    validation = BundleFileAdapter(allowed_roots=[package_root]).validate(manifest)
    ingestor = PostgreSQLPredictiveMaintenanceBundleIngestor(postgresql_database)
    ingestion = ingestor.ingest_validated_bundle(manifest=manifest, validation=validation)
    stream_root = tmp_path / "runtime-output"
    event, row = _runtime_overlay_input()
    _write_runtime_overlay_input(stream_root, event, row)

    start = threading.Barrier(2)

    def consume(index: int) -> dict[str, object]:
        start.wait()
        return _consume_overlay_event(
            postgresql_database,
            ingestion.dataset_version_id,
            stream_root,
            event,
            dataset_id=ingestion.dataset_id,
            snapshot_root=tmp_path / f"runtime-input-{index}",
            enqueue_client=_RecordingGeneratorRuntimeClient(),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(consume, range(2)))

    assert sorted(result["reused"] for result in results) == [False, True]


def test_postgresql_prediction_inbox_repository_idempotency_and_conflicts(
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg.rows import dict_row

    repository = PredictiveMaintenanceRuntimeRepository(postgresql_database)
    payload = load_payload()
    item = payload["results"][0]
    received_at = datetime(2026, 8, 27, tzinfo=timezone.utc)
    common = {
        "organization_id": "org-test",
        "project_id": "project-test",
        "workspace_id": "workspace-test",
        "batch_id": payload["batch_id"],
        "payload_sha256": "a" * 64,
        "validation_status": "accepted",
        "rejection_reason": None,
        "raw_payload": payload,
        "received_at": received_at,
        "item_receipts": [
            {
                "event_id": item["event_id"],
                "payload_sha256": item["payload_sha256"],
                "validation_status": "accepted",
                "rejection_reason": None,
            }
        ],
    }

    first = repository.save_prediction_batch_inbox(**common)
    duplicate = repository.save_prediction_batch_inbox(**common)
    batch_conflict = repository.save_prediction_batch_inbox(
        **{**common, "payload_sha256": "b" * 64}
    )
    item_conflict = repository.save_prediction_batch_inbox(
        **{
            **common,
            "batch_id": "batch-item-conflict",
            "payload_sha256": "c" * 64,
            "item_receipts": [
                {
                    "event_id": item["event_id"],
                    "payload_sha256": "d" * 64,
                    "validation_status": "accepted",
                    "rejection_reason": None,
                }
            ],
        }
    )

    assert first["validation_status"] == "accepted"
    assert duplicate["validation_status"] == "duplicate"
    assert batch_conflict["validation_status"] == "conflict"
    assert item_conflict["validation_status"] == "conflict"

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        batch_rows = connection.execute(
            """
            SELECT batch_id,validation_status,promotion_result_id,raw_payload
            FROM pm_prediction_result_inbox_batches
            ORDER BY received_at, batch_id, validation_status
            """
        ).fetchall()
        item_rows = connection.execute(
            """
            SELECT event_id,validation_status,promotion_result_id
            FROM pm_prediction_result_inbox_items
            ORDER BY received_at, batch_id, validation_status
            """
        ).fetchall()

    assert [row["validation_status"] for row in batch_rows].count("accepted") == 1
    assert [row["validation_status"] for row in batch_rows].count("conflict") == 2
    assert all(row["promotion_result_id"] is None for row in batch_rows)
    assert batch_rows[0]["raw_payload"]["batch_id"] == payload["batch_id"]
    assert [row["validation_status"] for row in item_rows].count("accepted") == 1
    assert [row["validation_status"] for row in item_rows].count("conflict") == 1
    assert all(row["promotion_result_id"] is None for row in item_rows)


def test_postgresql_prediction_inbox_concurrent_delivery_is_serialized(
    postgresql_database: str,
) -> None:
    repository = PredictiveMaintenanceRuntimeRepository(postgresql_database)
    payload = load_payload()
    item = payload["results"][0]
    received_at = datetime(2026, 8, 27, tzinfo=timezone.utc)

    def save(
        *,
        batch_id: str,
        batch_sha: str,
        item_sha: str,
        barrier: threading.Barrier,
    ) -> str:
        barrier.wait(timeout=10)
        result = repository.save_prediction_batch_inbox(
            organization_id="org-test",
            project_id="project-test",
            workspace_id="workspace-test",
            batch_id=batch_id,
            payload_sha256=batch_sha,
            validation_status="accepted",
            rejection_reason=None,
            raw_payload={**payload, "batch_id": batch_id},
            received_at=received_at,
            item_receipts=[
                {
                    "event_id": f"{item['event_id']}-{batch_id}",
                    "payload_sha256": item_sha,
                    "validation_status": "accepted",
                    "rejection_reason": None,
                }
            ],
        )
        return str(result["validation_status"])

    same_barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        same_results = sorted(
            future.result(timeout=20)
            for future in (
                executor.submit(
                    save,
                    batch_id="batch-concurrent-same",
                    batch_sha="a" * 64,
                    item_sha="b" * 64,
                    barrier=same_barrier,
                ),
                executor.submit(
                    save,
                    batch_id="batch-concurrent-same",
                    batch_sha="a" * 64,
                    item_sha="b" * 64,
                    barrier=same_barrier,
                ),
            )
        )

    conflict_barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        conflict_results = sorted(
            future.result(timeout=20)
            for future in (
                executor.submit(
                    save,
                    batch_id="batch-concurrent-conflict",
                    batch_sha="c" * 64,
                    item_sha="d" * 64,
                    barrier=conflict_barrier,
                ),
                executor.submit(
                    save,
                    batch_id="batch-concurrent-conflict",
                    batch_sha="e" * 64,
                    item_sha="f" * 64,
                    barrier=conflict_barrier,
                ),
            )
        )

    assert same_results == ["accepted", "duplicate"]
    assert conflict_results == ["accepted", "conflict"]


def test_postgresql_prediction_batch_promotion_materializes_product_result(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg.rows import dict_row

    package_root = create_small_package(tmp_path)
    manifest = build_manifest(package_root)
    validation = BundleFileAdapter(allowed_roots=[package_root]).validate(manifest)
    ingestion = PostgreSQLPredictiveMaintenanceBundleIngestor(
        postgresql_database
    ).ingest_validated_bundle(manifest=manifest, validation=validation)

    repository = PredictiveMaintenanceRuntimeRepository(postgresql_database)
    service = PredictiveMaintenanceRuntimeService(repository)
    payload = load_payload()
    payload["source_context"]["dataset_id"] = ingestion.dataset_id
    payload["source_context"]["dataset_version"] = ingestion.source_version
    payload["results"][0]["payload_sha256"] = (
        PredictiveMaintenanceRuntimeService._prediction_item_sha256(payload["results"][0])
    )

    inbox = service.receive_prediction_result_batch(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        payload=payload,
    )
    promotion = service.promote_prediction_result_batch(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        batch_id=payload["batch_id"],
    )
    replay = service.promote_prediction_result_batch(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        batch_id=payload["batch_id"],
    )

    assert inbox.validation_status == "accepted"
    assert promotion.promotion_status == "promoted"
    assert promotion.product_result_created is True
    assert promotion.promoted_results == 1
    assert replay.promotion_status == "already_promoted"

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.organization_id','org-test',true)")
        connection.execute("SELECT set_config('app.project_id','project-test',true)")
        artifact = connection.execute(
            """
            SELECT r.artifact_id,r.prediction_result_id,r.status_grade,
                   r.failure_probability,p.payload_json,
                   b.promotion_result_id AS batch_promotion_result_id,
                   i.promotion_result_id AS item_promotion_result_id
            FROM pm_result_artifacts r
            JOIN prediction_results p ON p.prediction_id=r.prediction_result_id
            JOIN pm_prediction_result_inbox_batches b ON b.batch_id=%s
            JOIN pm_prediction_result_inbox_items i ON i.batch_id=b.batch_id
            WHERE r.dataset_version_id=%s
            """,
            (payload["batch_id"], ingestion.dataset_version_id),
        ).fetchone()

    assert artifact is not None
    assert artifact["batch_promotion_result_id"] == artifact["prediction_result_id"]
    assert artifact["item_promotion_result_id"] == artifact["prediction_result_id"]
    assert artifact["status_grade"] == "critical"
    assert float(artifact["failure_probability"]) == 0.82
    gap_ids = {
        gap["gap_id"]
        for gap in artifact["payload_json"]["evidence_payload"]["evidence_gaps"]
    }
    assert "generator-batch-asset-criticality-unavailable" in gap_ids


def test_postgresql_prediction_inbox_tables_are_rls_scoped(
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row

    repository = PredictiveMaintenanceRuntimeRepository(postgresql_database)
    payload = load_payload()
    item = payload["results"][0]
    repository.save_prediction_batch_inbox(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        batch_id="batch-rls-visible",
        payload_sha256="a" * 64,
        validation_status="accepted",
        rejection_reason=None,
        raw_payload=payload,
        received_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        item_receipts=[
            {
                "event_id": "event-rls-visible",
                "payload_sha256": item["payload_sha256"],
                "validation_status": "accepted",
                "rejection_reason": None,
            }
        ],
    )

    role = f"pm_inbox_rls_{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role),
                    sql.Literal("runtime-test-password"),
                )
            )
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            for table in (
                "pm_prediction_result_inbox_batches",
                "pm_prediction_result_inbox_items",
            ):
                admin.execute(
                    sql.SQL("GRANT SELECT ON {} TO {}").format(
                        sql.Identifier(table),
                        sql.Identifier(role),
                    )
                )
        with psycopg.connect(
            _dsn_for_user(postgresql_database, role, "runtime-test-password"),
            row_factory=dict_row,
        ) as scoped:
            scoped.execute("SELECT set_config('app.organization_id','org-test',false)")
            scoped.execute("SELECT set_config('app.project_id','project-test',false)")
            visible_batches = int(
                scoped.execute(
                    "SELECT COUNT(*) AS count FROM pm_prediction_result_inbox_batches"
                ).fetchone()["count"]
            )
            visible_items = int(
                scoped.execute(
                    "SELECT COUNT(*) AS count FROM pm_prediction_result_inbox_items"
                ).fetchone()["count"]
            )
            scoped.execute("SELECT set_config('app.project_id','project-other',false)")
            hidden_batches = int(
                scoped.execute(
                    "SELECT COUNT(*) AS count FROM pm_prediction_result_inbox_batches"
                ).fetchone()["count"]
            )
            hidden_items = int(
                scoped.execute(
                    "SELECT COUNT(*) AS count FROM pm_prediction_result_inbox_items"
                ).fetchone()["count"]
            )

        assert visible_batches == 1
        assert visible_items == 1
        assert hidden_batches == 0
        assert hidden_items == 0
    finally:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


def test_postgresql_agent_execution_activity_round_trips(
    postgresql_database: str,
) -> None:
    repository = AgentRunRepository(postgresql_database)
    run_id = f"agent-test-{uuid.uuid4().hex[:12]}"
    state = {
        "run_id": run_id,
        "organization_id": "org-test",
        "project_id": "project-test",
        "workspace_id": "workspace-test",
        "user_id": "runtime-user",
        "question": "Why is this asset high risk?",
        "route": "hybrid",
        "status": "succeeded",
        "object_type": "equipment",
        "object_id": "CNC-001",
        "event_id": "RESULT#CNC-001#1",
        "evidence": [{"evidence_id": "evidence-1"}],
        "claims": [{"claim_id": "claim-1"}],
        "steps": [
            {
                "name": "evidence_retrieval",
                "store": "pgvector",
                "status": "succeeded",
                "latency_ms": 18,
                "detail": "Retrieved governed evidence.",
            }
        ],
        "answer": "Grounded answer",
        "caveats": [],
        "error": None,
        "checkpoint_sequence": 1,
        "duration_ms": 24,
        "activity_persistence": "persisted",
    }
    traces = [
        {
            "id": f"trace-{run_id}",
            "run_id": run_id,
            "step_name": "evidence_retrieval",
            "store_kind": "pgvector",
            "status": "succeeded",
            "input": {},
            "output": {"detail": "Retrieved governed evidence."},
            "latency_ms": 18,
            "created_at": datetime.now(timezone.utc),
        }
    ]

    repository.save_run(state=state, traces=traces)
    page = repository.list_runs(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        user_id="runtime-user",
        offset=0,
        limit=10,
        status=None,
        route=None,
        search=None,
        object_id="CNC-001",
    )
    assert page["total"] == 1
    assert page["items"][0]["run_id"] == run_id
    restored = repository.get_run(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        user_id="runtime-user",
        run_id=run_id,
    )
    assert restored is not None
    assert restored["state"]["answer"] == "Grounded answer"
    assert restored["state"]["activity_persistence"] == "persisted"
    assert restored["traces"][0]["store_kind"] == "pgvector"
    assert restored["traces"][0]["latency_ms"] == 18


def test_postgresql_risk_index_buckets_are_chart_ready_and_asset_balanced(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg.rows import dict_row

    package_root = create_small_package(tmp_path)
    manifest = build_manifest(package_root)
    validation = BundleFileAdapter(allowed_roots=[package_root]).validate(manifest)
    ingestion = PostgreSQLPredictiveMaintenanceBundleIngestor(
        postgresql_database
    ).ingest_validated_bundle(manifest=manifest, validation=validation)

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.organization_id','org-test',true)")
        connection.execute("SELECT set_config('app.project_id','project-test',true)")
        bounds = connection.execute(
            """
            SELECT MIN(observed_at) AS start,MAX(observed_at) AS end
            FROM pm_prediction_timeline
            WHERE dataset_version_id=%s
            """,
            (ingestion.dataset_version_id,),
        ).fetchone()
    assert bounds is not None
    assert bounds["start"] is not None and bounds["end"] is not None

    repository = PredictiveMaintenanceRuntimeRepository(postgresql_database)
    plant = repository.risk_index_rows(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_version_id=ingestion.dataset_version_id,
        start=bounds["start"],
        end=bounds["end"],
        bucket_interval="1 hour",
        asset_id=None,
    )
    asset = repository.risk_index_rows(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_version_id=ingestion.dataset_version_id,
        start=bounds["start"],
        end=bounds["end"],
        bucket_interval="1 hour",
        asset_id="CNC-001",
    )

    assert plant
    assert asset
    assert all(0.0 <= float(row["risk_value"]) <= 1.0 for row in plant)
    assert all(int(row["sample_count"]) >= int(row["asset_count"]) >= 1 for row in plant)
    assert all(int(row["asset_count"]) == 1 for row in asset)


def _changed_schema_manifest(manifest: DatasetBundleManifestV2) -> DatasetBundleManifestV2:
    schema_version = f"{manifest.schema_version}.revision-2"
    checksum = compute_bundle_checksum(
        dataset_version=manifest.dataset_version,
        schema_version=schema_version,
        generation=manifest.generation,
        source_contract=manifest.source_contract,
        files=manifest.files,
    )
    return DatasetBundleManifestV2.model_validate(
        {
            **manifest.model_dump(mode="python", by_alias=True),
            "schema_version": schema_version,
            "bundle_checksum_sha256": checksum,
        }
    )


def test_product_results_remain_append_only_across_maintenance_overlay(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb

    package_root = create_small_package(tmp_path)
    manifest = build_manifest(package_root)
    validation = BundleFileAdapter(allowed_roots=[package_root]).validate(manifest)
    ingestion = PostgreSQLPredictiveMaintenanceBundleIngestor(
        postgresql_database
    ).ingest_validated_bundle(manifest=manifest, validation=validation)

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.organization_id','org-test',true)")
        connection.execute("SELECT set_config('app.project_id','project-test',true)")
        source = connection.execute(
            """
            SELECT prediction_id,prediction_result_id,asset_id,asset_type,observed_at,
                   failure_probability,confidence,status,model_version
            FROM pm_prediction_snapshots
            WHERE dataset_version_id=%s AND asset_id='CNC-001'
            """,
            (ingestion.dataset_version_id,),
        ).fetchone()
        source_artifact_id = "source-product-result-before-maintenance"
        connection.execute(
            """
            INSERT INTO pm_result_artifacts(
                organization_id,project_id,workspace_id,dataset_version_id,
                artifact_id,prediction_id,prediction_result_id,asset_id,asset_type,
                observed_at,prediction_horizon_hours,prediction_task,
                failure_probability,predicted_failure_type,status_grade,confidence,
                top_factors,recommended_action,provenance,schema_version,
                model_version,source_sha256
            ) VALUES (
                'org-test','project-test','workspace-test',%s,%s,%s,%s,%s,%s,%s,24,
                'binary_failure_within_horizon',%s,'no_significant_risk',%s,%s,
                '[]'::jsonb,'{}'::jsonb,%s::jsonb,'result-artifact-v1.0',%s,%s
            )
            """,
            (
                ingestion.dataset_version_id,
                source_artifact_id,
                source["prediction_id"],
                source["prediction_result_id"],
                source["asset_id"],
                source["asset_type"],
                source["observed_at"],
                source["failure_probability"],
                "critical",
                source["confidence"],
                Jsonb(
                    {
                        "prediction_id": source["prediction_id"],
                        "model_version": source["model_version"],
                    }
                ),
                source["model_version"],
                "a" * 64,
            ),
        )

        overlay_result = {
            "artifact_id": "product-result-after-maintenance",
            "observed_at": (source["observed_at"] + timedelta(hours=2)).isoformat(),
            "failure_probability": 0.12,
            "predicted_failure_type": "none",
            "status_grade": "normal",
            "confidence": 0.91,
            "top_factors": [
                {
                    "rank": 1,
                    "feature": "tool_wear_min",
                    "feature_value": 0.0,
                    "signed_contribution": -0.2,
                    "direction": "negative",
                    "explanation_method": "maintenance_replay",
                }
            ],
            "recommended_action": {"action": "continue_monitoring"},
            "provenance": {
                "prediction_id": "prediction-after-maintenance",
                "model_version": "test-v2",
                "maintenance_event_id": "maintenance-event-1",
                "overlay_branch_id": "overlay-branch-1",
                "history_segment_id": "history-segment-1",
                "maintenance_action_id": "maintenance-action-1",
            },
        }
        _persist_overlay_product_result(
            connection,
            Jsonb,
            dataset_version_id=ingestion.dataset_version_id,
            asset_id="CNC-001",
            asset_type="cnc",
            result=overlay_result,
        )
        _persist_overlay_product_result(
            connection,
            Jsonb,
            dataset_version_id=ingestion.dataset_version_id,
            asset_id="CNC-001",
            asset_type="cnc",
            result=overlay_result,
        )

        artifacts = connection.execute(
            """
            SELECT artifact_id,prediction_result_id,provenance
            FROM pm_result_artifacts
            WHERE dataset_version_id=%s AND asset_id='CNC-001'
            ORDER BY observed_at
            """,
            (ingestion.dataset_version_id,),
        ).fetchall()
        assert [row["artifact_id"] for row in artifacts] == [
            source_artifact_id,
            "product-result-after-maintenance",
        ]
        assert artifacts[1]["provenance"]["maintenance_event_id"] == "maintenance-event-1"
        assert artifacts[1]["provenance"]["source_product_result_id"] == source_artifact_id
        for table in ("pm_prediction_snapshots", "pm_prediction_timeline"):
            count = connection.execute(
                f"SELECT COUNT(*) AS count FROM {table} "
                "WHERE dataset_version_id=%s AND asset_id='CNC-001'",
                (ingestion.dataset_version_id,),
            ).fetchone()["count"]
            assert int(count) == 2

    repository = PredictiveMaintenanceRuntimeRepository(postgresql_database)
    source_contract, total, latest_rows = repository.latest_result_rows(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_version_id=ingestion.dataset_version_id,
        asset_id="CNC-001",
        site_id=None,
        cell_id=None,
        asset_type=None,
        status_grade=None,
        offset=0,
        limit=100,
    )
    assert source_contract == "result_artifact"
    assert total == 1
    assert [row["artifact_id"] for row in latest_rows] == [
        "product-result-after-maintenance"
    ]

    post_maintenance = repository.post_maintenance_result_row(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        asset_id="CNC-001",
        maintenance_event_id="maintenance-event-1",
    )
    assert post_maintenance is not None
    assert post_maintenance["artifact_id"] == "product-result-after-maintenance"
    assert post_maintenance["dataset_version_id"] == ingestion.dataset_version_id
    assert (
        post_maintenance["provenance"]["maintenance_event_id"]
        == "maintenance-event-1"
    )

    assert repository.post_maintenance_result_row(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        asset_id="CNC-001",
        maintenance_event_id="maintenance-event-unknown",
    ) is None

    _, critical_total, critical_rows = repository.latest_result_rows(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_version_id=ingestion.dataset_version_id,
        asset_id="CNC-001",
        site_id=None,
        cell_id=None,
        asset_type=None,
        status_grade="critical",
        offset=0,
        limit=100,
    )
    assert critical_total == 0
    assert critical_rows == []


def test_postgresql_copy_idempotency_rls_and_atomic_rollback(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row

    package_root = create_small_package(tmp_path)
    manifest = build_manifest(package_root)
    validation = BundleFileAdapter(allowed_roots=[package_root]).validate(manifest)
    assert validation.status == "completed"
    expected = {item.role: item.source_record_count for item in validation.roles}
    ingestor = PostgreSQLPredictiveMaintenanceBundleIngestor(postgresql_database)

    first = ingestor.ingest_validated_bundle(manifest=manifest, validation=validation)
    assert first.reused_dataset_version is False
    assert first.row_counts == expected
    assert first.source_record_count == sum(expected.values())

    second = ingestor.ingest_validated_bundle(manifest=manifest, validation=validation)
    assert second.reused_dataset_version is True
    assert second.dataset_id == first.dataset_id
    assert second.dataset_version_id == first.dataset_version_id
    assert second.row_counts == expected
    assert second.outbox_event_id is None

    revised_manifest = _changed_schema_manifest(manifest)
    revised_validation = BundleFileAdapter(allowed_roots=[package_root]).validate(
        revised_manifest
    )
    revised = ingestor.ingest_validated_bundle(
        manifest=revised_manifest,
        validation=revised_validation,
    )
    assert revised.reused_dataset_version is False
    assert revised.dataset_id == first.dataset_id
    assert revised.dataset_version_id != first.dataset_version_id
    assert revised.version_number == first.version_number + 1
    assert revised.row_counts == expected

    other_manifest = DatasetBundleManifestV2.model_validate(
        {
            **manifest.model_dump(mode="python", by_alias=True),
            "project_id": "project-other",
            "workspace_id": "workspace-other",
        }
    )
    other_validation = BundleFileAdapter(allowed_roots=[package_root]).validate(
        other_manifest
    )
    with pytest.raises(RuntimeError, match="injected bundle transaction failure"):
        ingestor.ingest_validated_bundle(
            manifest=other_manifest,
            validation=other_validation,
            fail_after_role="asset_master",
        )

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        version_rows = connection.execute(
            "SELECT id,checksum_sha256 FROM dataset_versions WHERE dataset_id=%s ORDER BY version_number",
            (first.dataset_id,),
        ).fetchall()
        assert [str(row["id"]) for row in version_rows] == [
            first.dataset_version_id,
            revised.dataset_version_id,
        ]
        assert len({str(row["checksum_sha256"]) for row in version_rows}) == 2
        assert int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM transactional_outbox WHERE event_type='dataset.version.relational_ready'"
            ).fetchone()["count"]
        ) == 2
        assert int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM adapter_ingestion_runs WHERE project_id='project-test' AND status='completed'"
            ).fetchone()["count"]
        ) == 3
        assert int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM adapter_ingestion_runs WHERE project_id='project-other' AND status='failed'"
            ).fetchone()["count"]
        ) == 1
        for table in (
            "datasets",
            "dataset_versions",
            "pm_assets",
            "pm_asset_relations",
            "pm_compressor_observations",
            "pm_cnc_observations",
            "pm_production_cycles",
            "pm_maintenance_events",
            "pm_prediction_snapshots",
            "pm_prediction_factors",
            "pm_prediction_timeline",
            "transactional_outbox",
        ):
            count = int(
                connection.execute(
                    sql.SQL("SELECT COUNT(*) AS count FROM {} WHERE project_id='project-other'").format(
                        sql.Identifier(table)
                    )
                ).fetchone()["count"]
            )
            assert count == 0, table

        orphan_checks = [
            """
            SELECT COUNT(*) AS count FROM pm_asset_relations r
            LEFT JOIN pm_assets a ON a.dataset_version_id=r.dataset_version_id
                AND a.asset_id=r.from_asset_id
            WHERE a.asset_id IS NULL
            """,
            """
            SELECT COUNT(*) AS count FROM pm_prediction_factors f
            LEFT JOIN pm_prediction_snapshots p
                ON p.dataset_version_id=f.dataset_version_id
                AND p.prediction_id=f.prediction_id
            WHERE p.prediction_id IS NULL
            """,
        ]
        assert all(
            int(connection.execute(statement).fetchone()["count"]) == 0
            for statement in orphan_checks
        )

    role = f"pm_rls_test_{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role),
                    sql.Literal("runtime-test-password"),
                )
            )
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            admin.execute(
                sql.SQL("GRANT SELECT ON pm_assets TO {}").format(sql.Identifier(role))
            )
        with psycopg.connect(
            _dsn_for_user(postgresql_database, role, "runtime-test-password"),
            row_factory=dict_row,
        ) as scoped:
            scoped.execute("SELECT set_config('app.organization_id','org-test',false)")
            scoped.execute("SELECT set_config('app.project_id','project-test',false)")
            visible = int(scoped.execute("SELECT COUNT(*) AS count FROM pm_assets").fetchone()["count"])
            scoped.execute("SELECT set_config('app.project_id','project-other',false)")
            hidden = int(scoped.execute("SELECT COUNT(*) AS count FROM pm_assets").fetchone()["count"])
        assert visible == expected["asset_master"] * 2
        assert hidden == 0
    finally:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


@pytest.mark.skip(reason="Adaptive Modeling Workbench was removed from the Operations runtime")
def test_postgresql_adaptive_modeling_repository_jsonb_idempotency_and_rls(
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row

    repository = ModelingRepository(postgresql_database)
    source_checksum = "a" * 64
    profile = DatasetIntakeProfile(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        profile_id="profile-postgresql-runtime",
        source_uri="file:///tmp/governed-source.csv",
        source_checksum_sha256=source_checksum,
        parser_version="dataset-intake-v1",
        cache_key=canonical_checksum(
            {
                "source_checksum_sha256": source_checksum,
                "parser_version": "dataset-intake-v1",
            }
        ),
        byte_size=128,
        media_type="text/csv",
        status="ready_for_review",
        structure_type="tabular_column_as_attribute",
        row_count=2,
        idempotency_key="profile-postgresql-runtime",
    )
    first = repository.put(
        "intake_profile",
        profile.model_dump(mode="json"),
        idempotency_key=profile.idempotency_key,
    )
    repeated = repository.put(
        "intake_profile",
        profile.model_dump(mode="json"),
        idempotency_key=profile.idempotency_key,
    )
    assert repeated == first
    assert repository.get(
        "intake_profile",
        profile.profile_id,
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
    )["source_checksum_sha256"] == source_checksum
    with pytest.raises(KeyError):
        repository.get(
            "intake_profile",
            profile.profile_id,
            organization_id="org-test",
            project_id="project-other",
            workspace_id="workspace-other",
        )
    repository.record_audit(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        actor_id="user-test",
        action="modeling.profile.verified",
        aggregate_type="DatasetIntakeProfile",
        aggregate_id=profile.profile_id,
        payload={"checksum": source_checksum},
    )
    assert repository.list_audit(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
    )[0]["payload"]["checksum"] == source_checksum

    role = f"modeling_rls_test_{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role),
                    sql.Literal("runtime-test-password"),
                )
            )
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            admin.execute(
                sql.SQL("GRANT SELECT ON modeling_intake_profiles TO {}").format(
                    sql.Identifier(role)
                )
            )
        with psycopg.connect(
            _dsn_for_user(postgresql_database, role, "runtime-test-password"),
            row_factory=dict_row,
        ) as scoped:
            scoped.execute("SELECT set_config('app.organization_id','org-test',false)")
            scoped.execute("SELECT set_config('app.project_id','project-test',false)")
            visible = int(
                scoped.execute(
                    "SELECT COUNT(*) AS count FROM modeling_intake_profiles"
                ).fetchone()["count"]
            )
            scoped.execute("SELECT set_config('app.project_id','project-other',false)")
            hidden = int(
                scoped.execute(
                    "SELECT COUNT(*) AS count FROM modeling_intake_profiles"
                ).fetchone()["count"]
            )
        assert visible == 1
        assert hidden == 0
    finally:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
