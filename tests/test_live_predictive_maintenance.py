from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.infra import live_predictive_maintenance_runtime as live_runtime
from app.infra.live_predictive_maintenance_runtime import (
    LIVE_SOURCE_VERSION,
    LiveDatasetIngestionAdapter,
    LiveDiagnosisApplicationAdapter,
    _materialize_live_pipeline_snapshot,
    _materialize_runtime_results,
    active_overlay_asset_ids,
    read_complete_ticks,
    read_overlay_available_events,
)
from app.infra.runtime_overlay_contract import expected_storage_reference
from app.maintenance.live_service import LivePredictiveMaintenanceService


def test_live_ingestion_adapter_keeps_wall_clock_guard_by_default() -> None:
    adapter = LiveDatasetIngestionAdapter(
        "postgresql://example.invalid/test",
        predictor_factory=lambda _asset_type: None,
        artifact_builder=lambda **_kwargs: {},
    )

    assert adapter.allow_accelerated_simulation is False


def test_live_ingestion_adapter_can_explicitly_enable_accelerated_simulation() -> None:
    adapter = LiveDatasetIngestionAdapter(
        "postgresql://example.invalid/test",
        predictor_factory=lambda _asset_type: None,
        artifact_builder=lambda **_kwargs: {},
        allow_accelerated_simulation=True,
    )

    assert adapter.allow_accelerated_simulation is True


def test_macmini_compose_runs_canonical_live_worker() -> None:
    root = Path(__file__).resolve().parents[1]
    compose = (root / "infra" / "macmini" / "docker-compose.yml").read_text(encoding="utf-8")

    assert 'command: ["python", "-m", "app.live_predictive_maintenance"]' in compose
    assert "ontology_dashboard.live_predictive_maintenance" not in compose
    assert "generator-runtime:" in compose
    assert 'entrypoint: ["python", "-m", "uvicorn"]' in compose
    assert 'command: ["systems.generator.app.main:app", "--host", "0.0.0.0", "--port", "8000"]' in compose
    assert 'GENERATOR_RUNTIME_PREDICTION_ENABLED: "true"' in compose
    assert "GENERATOR_PIPELINE_INPUT_ROOTS: /runtime-pipeline-input" in compose
    assert "GENERATOR_PREDICTION_RESULT_URL: http://backend:8000/internal/prediction-results" in compose
    assert "PREDICTION_RESULT_INGEST_TOKEN is required" in compose
    assert "http://generator-runtime:8000/internal/runtime-pipeline/enqueue" in compose
    assert "generator-active-model-set.json:/data/models/active-model-set.json:ro" in compose
    assert "${GEN_DATA_RUNTIME_OUTPUT_ROOT}:/gen-data-runtime:ro" in compose
    assert "${RUNTIME_PIPELINE_INPUT_ROOT}:/runtime-pipeline-input" in compose
    assert "${RUNTIME_PIPELINE_INPUT_ROOT}:/runtime-pipeline-input:ro" in compose
    assert "ONTOLOGY_DASHBOARD_RUNTIME_PIPELINE_INPUT_ROOT: /runtime-pipeline-input" in compose
    assert not (
        root / "systems" / "backend" / "ontology_dashboard" / "live_predictive_maintenance.py"
    ).exists()


def test_runtime_product_result_materialization_never_deletes_history() -> None:
    implementation = inspect.getsource(_materialize_runtime_results)
    for table in (
        "pm_result_artifacts",
        "pm_prediction_factors",
        "pm_prediction_timeline",
        "pm_prediction_snapshots",
        "prediction_results",
    ):
        assert f"DELETE FROM {table}" not in implementation


def test_live_pipeline_snapshot_uses_only_cadence_aligned_observations() -> None:
    implementation = inspect.getsource(live_runtime._live_pipeline_observation_rows)

    assert "MOD(EXTRACT(EPOCH FROM observed_at)::bigint, 600) = 0" in implementation
    assert "lookback_rows = max(minimum_history_rows, minimum_history_rows * 8)" in implementation
    assert "latest_continuous_window" in implementation


def test_macmini_generator_active_model_set_pins_both_equipment_families() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "infra" / "macmini" / "generator-active-model-set.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["model_set_id"] == "hanbit-live-reliability"
    assert payload["models"] == {
        "cnc-failure-risk": {
            "model_version": "cnc-random-forest-v3-f898a33ade7f",
            "required": True,
        },
        "compressor-failure-risk": {
            "model_version": "compressor-random-forest-v3-138e75c0f721",
            "required": True,
        },
    }


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_live_pipeline_snapshot_is_content_addressed_and_immutable(tmp_path):
    rows = [
        {
            "contract_version": "gen-data-sensor-observation-v2",
            "schema_version": "2",
            "source_kind": "live_sensor",
            "asset_id": "CNC-1",
            "asset_type": "cnc",
            "observed_at": "2026-08-18T05:30:00+00:00",
            "tool_wear_min": 10.0,
        }
    ]

    first = _materialize_live_pipeline_snapshot(tmp_path, rows)
    second = _materialize_live_pipeline_snapshot(tmp_path, rows)

    assert first == second
    assert first["job_id"].startswith("live-sensor-")
    assert Path(first["source_uri"]).read_text(encoding="utf-8").count("\n") == 1


def test_live_diagnosis_adapter_enqueues_ready_snapshot(tmp_path, monkeypatch):
    rows = [
        {
            "contract_version": "gen-data-sensor-observation-v2",
            "schema_version": "2",
            "source_kind": "live_sensor",
            "asset_id": "CNC-1",
            "asset_type": "cnc",
            "observed_at": "2026-08-18T05:30:00+00:00",
            "tool_wear_min": 10.0,
        }
    ]
    monkeypatch.setattr(
        live_runtime,
        "_live_pipeline_observation_rows",
        lambda *_args, **_kwargs: (rows, {"CNC-1": 36}),
    )

    class EnqueueClient:
        def __init__(self):
            self.payload = None

        def enqueue(self, payload):
            self.payload = payload
            return {"job_id": payload["job_id"], "status": "queued"}

    client = EnqueueClient()
    adapter = LiveDiagnosisApplicationAdapter(
        snapshot_root=tmp_path,
        enqueue_client=client,
    )
    result = adapter.materialize_live_results(
        {
            "database_url": "postgresql://backend/live",
            "dataset_id": "dataset-1",
            "dataset_version_id": "version-1",
            "active_overlay_assets": set(),
        }
    )

    assert result["status"] == "queued"
    assert result["ready_assets"] == 1
    assert client.payload["source_kind"] == "live_sensor"
    assert client.payload["lineage"] == {}


def test_read_complete_ticks_ignores_half_written_cross_line_tick(tmp_path):
    first = "2026-08-18T05:30:00+00:00"
    second = "2026-08-18T05:40:00+00:00"
    _write(
        tmp_path / "sensor/facS01/lineL01/sensor_stream.jsonl",
        [
            {"asset_id": "CMP-1", "observed_at": first},
            {"asset_id": "CMP-1", "observed_at": second},
        ],
    )
    _write(
        tmp_path / "sensor/facS01/lineL02/sensor_stream.jsonl",
        [{"asset_id": "CNC-1", "observed_at": first}],
    )

    ticks = read_complete_ticks(tmp_path, expected_asset_count=2)

    assert [tick[0] for tick in ticks] == [datetime(2026, 8, 18, 5, 30, tzinfo=timezone.utc)]
    assert {row["asset_id"] for row in ticks[0][1]} == {"CMP-1", "CNC-1"}


def test_read_complete_ticks_supports_current_gen_data_run_output(tmp_path):
    observed_at = "2026-08-18T05:30:00+00:00"
    _write(
        tmp_path / "runs/run-1/source/sensor_records.jsonl",
        [
            {
                "schema_version": "2",
                "run_id": "run-1",
                "sequence": 1,
                "asset_id": "CNC-1",
                "asset_type": "cnc",
                "site_id": "S01",
                "cell_id": "L01",
                "observed_at": observed_at,
                "generator_version": "test",
                "measurements": {
                    "is_operating": 1,
                    "operating_state": "running",
                    "product_type": "M",
                    "air_temperature_k": 300.0,
                    "process_temperature_k": 310.0,
                    "rotational_speed_rpm": 1500.0,
                    "torque_nm": 40.0,
                    "tool_wear_min": 10.0,
                },
            }
        ],
    )

    ticks = read_complete_ticks(tmp_path, expected_asset_ids={"CNC-1"})

    assert ticks[0][1][0]["tool_wear_min"] == 10.0
    assert "measurements" not in ticks[0][1][0]


def test_read_complete_ticks_isolates_requested_simulation_session(tmp_path):
    for session_id, value in (("session-old", 10.0), ("session-current", 42.0)):
        _write(
            tmp_path / f"runs/{session_id}/source/sensor_records.jsonl",
            [
                {
                    "asset_id": "CNC-1",
                    "observed_at": "2026-09-04T02:40:00+00:00",
                    "measurements": {"tool_wear_min": value},
                }
            ],
        )

    ticks = read_complete_ticks(
        tmp_path,
        simulation_session_id="session-current",
        expected_asset_ids={"CNC-1"},
    )

    assert len(ticks) == 1
    assert ticks[0][1][0]["tool_wear_min"] == 42.0


def test_read_complete_ticks_respects_ingestion_checkpoint(tmp_path):
    first = "2026-08-18T05:30:00+00:00"
    second = "2026-08-18T05:40:00+00:00"
    for line, asset in (("lineL01", "CMP-1"), ("lineL02", "CNC-1")):
        _write(
            tmp_path / f"sensor/facS01/{line}/sensor_stream.jsonl",
            [
                {"asset_id": asset, "observed_at": first},
                {"asset_id": asset, "observed_at": second},
            ],
        )

    ticks = read_complete_ticks(
        tmp_path,
        after=datetime(2026, 8, 18, 5, 30, tzinfo=timezone.utc),
        expected_asset_count=2,
    )

    assert len(ticks) == 1
    assert ticks[0][0] == datetime(2026, 8, 18, 5, 40, tzinfo=timezone.utc)


def test_read_complete_ticks_excludes_active_overlay_asset_by_identity(tmp_path):
    observed_at = "2026-08-18T05:30:00+00:00"
    for line, asset in (
        ("lineL01", "CMP-1"),
        ("lineL02", "CNC-1"),
        ("lineL03", "CNC-2"),
    ):
        _write(
            tmp_path / f"sensor/facS01/{line}/sensor_stream.jsonl",
            [{"asset_id": asset, "observed_at": observed_at}],
        )

    ticks = read_complete_ticks(
        tmp_path,
        expected_asset_ids={"CMP-1", "CNC-2"},
        excluded_asset_ids={"CNC-1"},
    )

    assert len(ticks) == 1
    assert {row["asset_id"] for row in ticks[0][1]} == {"CMP-1", "CNC-2"}


def test_active_overlay_row_cannot_hide_missing_expected_asset(tmp_path):
    observed_at = "2026-08-18T05:30:00+00:00"
    for line, asset in (("lineL01", "CMP-1"), ("lineL02", "CNC-1")):
        _write(
            tmp_path / f"sensor/facS01/{line}/sensor_stream.jsonl",
            [{"asset_id": asset, "observed_at": observed_at}],
        )

    ticks = read_complete_ticks(
        tmp_path,
        expected_asset_ids={"CMP-1", "CNC-2"},
        excluded_asset_ids={"CNC-1"},
    )

    assert ticks == []


def test_read_complete_ticks_rejects_unknown_identity_against_live_dataset(tmp_path):
    observed_at = "2026-08-18T05:30:00+00:00"
    _write(
        tmp_path / "sensor/facS01/lineL01/sensor_stream.jsonl",
        [
            {"asset_id": "CNC-1", "observed_at": observed_at},
            {"asset_id": "UNKNOWN-1", "observed_at": observed_at},
        ],
    )

    with pytest.raises(ValueError, match="outside the live Dataset Version.*UNKNOWN-1"):
        read_complete_ticks(tmp_path, expected_asset_ids={"CNC-1"})


def test_live_dataset_adapter_derives_expected_identity_set_from_dataset(
    tmp_path, monkeypatch
):
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        live_runtime,
        "_ensure_live_version",
        lambda *_args, **_kwargs: ("dataset-1", "version-1"),
    )
    monkeypatch.setattr(live_runtime, "_latest_ingested_at", lambda *_args: None)
    monkeypatch.setattr(
        live_runtime,
        "_dataset_asset_ids",
        lambda *_args: {"CMP-1", "CNC-1", "CNC-2"},
    )

    def capture_ticks(_stream_root, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(live_runtime, "read_complete_ticks", capture_ticks)
    adapter = LiveDatasetIngestionAdapter(
        "postgresql://backend/live",
        predictor_factory=lambda _asset_type: object(),
        artifact_builder=lambda **_kwargs: {},
    )

    batch = adapter.prepare_batch(
        stream_root=tmp_path,
        active_overlay_assets={"CNC-1"},
    )

    assert captured["expected_asset_ids"] == {"CMP-1", "CNC-2"}
    assert captured["excluded_asset_ids"] == {"CNC-1"}
    assert batch["expected_asset_ids"] == {"CMP-1", "CNC-2"}


def test_wall_clock_live_version_does_not_admit_future_accelerated_ticks(tmp_path):
    current = "2026-08-18T09:30:00+00:00"
    future = "2026-08-19T09:30:00+00:00"
    for line, asset in (("lineL01", "CMP-1"), ("lineL02", "CNC-1")):
        _write(
            tmp_path / f"sensor/facS01/{line}/sensor_stream.jsonl",
            [
                {"asset_id": asset, "observed_at": current},
                {"asset_id": asset, "observed_at": future},
            ],
        )

    ticks = read_complete_ticks(
        tmp_path,
        not_after=datetime(2026, 8, 18, 9, 32, tzinfo=timezone.utc),
        expected_asset_count=2,
    )

    assert LIVE_SOURCE_VERSION == "gen-data-wall-clock-live-v2"
    assert [tick[0] for tick in ticks] == [
        datetime(2026, 8, 18, 9, 30, tzinfo=timezone.utc)
    ]


def test_active_overlay_asset_ids_reads_checkpoint_without_model_semantics(tmp_path):
    state = {
        "checkpoint_version": 1,
        "branches": {
            "session:CNC-1:action": {
                "equipment_id": "CNC-1",
                "phase": "running",
            },
            "session:CNC-2:action": {
                "equipment_id": "CNC-2",
                "phase": "maintenance",
            },
        },
    }
    path = tmp_path / "runtime_overlay/runtime_overlay_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")

    assert active_overlay_asset_ids(tmp_path) == {"CNC-1", "CNC-2"}


def test_overlay_available_outbox_is_deduplicated_by_event_id(tmp_path):
    event = {
        "contract_version": "runtime-overlay-observations-available-v1",
        "event_type": "runtime_overlay.observations.available",
        "event_id": "OVERLAY-AVAILABLE:MAINT-1:post:36",
        "simulation_session_id": "SESSION-1",
        "equipment_id": "CNC-1",
        "maintenance_action_id": "ACTION-1",
        "maintenance_event_id": "MAINT-1",
        "overlay_branch_id": "MAINT-1:post",
        "history_segment_id": "MAINT-1:post",
        "source_kind": "maintenance_replay_overlay",
        "state_version": 3,
        "batch_rows": 36,
        "generated_rows": 36,
        "observed_from": "2026-08-18T05:30:00+00:00",
        "observed_to": "2026-08-18T11:20:00+00:00",
        "storage_reference": "",
    }
    event["storage_reference"] = expected_storage_reference(event)
    _write(
        tmp_path / "runtime_overlay/observations_available.jsonl",
        [event, event],
    )

    assert read_overlay_available_events(tmp_path) == [event]


def test_overlay_available_outbox_rejects_same_event_id_with_different_payload(
    tmp_path,
):
    event = {
        "contract_version": "runtime-overlay-observations-available-v1",
        "event_type": "runtime_overlay.observations.available",
        "event_id": "OVERLAY-AVAILABLE:MAINT-1:post:36",
        "simulation_session_id": "SESSION-1",
        "equipment_id": "CNC-1",
        "maintenance_action_id": "ACTION-1",
        "maintenance_event_id": "MAINT-1",
        "overlay_branch_id": "MAINT-1:post",
        "history_segment_id": "MAINT-1:post",
        "source_kind": "maintenance_replay_overlay",
        "state_version": 3,
        "batch_rows": 36,
        "generated_rows": 36,
        "observed_from": "2026-08-18T05:30:00+00:00",
        "observed_to": "2026-08-18T11:20:00+00:00",
        "storage_reference": "",
    }
    event["storage_reference"] = expected_storage_reference(event)
    conflicting = {**event, "generated_rows": 37}
    _write(
        tmp_path / "runtime_overlay/observations_available.jsonl",
        [event, conflicting],
    )

    with pytest.raises(ValueError, match="event_id conflict"):
        read_overlay_available_events(tmp_path)


def test_live_worker_orchestrates_owner_domain_ports_in_order(tmp_path):
    calls: list[str] = []
    ticks = [(datetime(2026, 8, 18, 5, 30, tzinfo=timezone.utc), [{"asset_id": "CNC-1"}])]
    batch = {
        "ticks": ticks,
        "summary": {"dataset_id": "dataset-1", "dataset_version_id": "version-1"},
    }

    class Dataset:
        def prepare_batch(self, **_kwargs):
            calls.append("dataset.prepare")
            return batch

        def persist_batch(self, _batch):
            calls.append("dataset.persist")
            return 1

    class Diagnosis:
        def materialize_live_results(self, _batch):
            calls.append("diagnosis.materialize")
            return {"result_artifact_count": 1}

    class Maintenance:
        def active_asset_ids(self, **_kwargs):
            calls.append("maintenance.active")
            return set()

        def process_available(self, _batch):
            calls.append("maintenance.overlay")
            return []

    class Ontology:
        def materialize_live_projection(self, _batch):
            calls.append("ontology.materialize")
            return {"object_count": 1}

    service = LivePredictiveMaintenanceService(
        dataset=Dataset(),
        diagnosis=Diagnosis(),
        maintenance=Maintenance(),
        ontology=Ontology(),
    )

    result = service.ingest_once(stream_root=tmp_path)

    assert calls == [
        "maintenance.active",
        "dataset.prepare",
        "dataset.persist",
        "diagnosis.materialize",
        "maintenance.overlay",
        "ontology.materialize",
    ]
    assert result["inserted_rows"] == 1
    assert result["runtime"]["result_artifact_count"] == 1
