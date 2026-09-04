from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.infra.generator_runtime_pipeline import (
    GeneratorRuntimePipelineClient,
    GeneratorRuntimePipelineUnavailable,
)
from app.infra.live_predictive_maintenance_runtime import (
    _materialize_overlay_pipeline_snapshot,
    _overlay_generator_enqueue_payload,
    _read_overlay_history_rows,
)
from app.infra.runtime_overlay_contract import (
    expected_storage_reference,
    semantic_observation_sha256,
)


def _event() -> dict[str, object]:
    return {
        "event_id": "OVERLAY-AVAILABLE:MAINT-1:post:1",
        "simulation_session_id": "SIM-1",
        "maintenance_action_id": "ACTION-1",
        "maintenance_event_id": "MAINT-1",
        "overlay_branch_id": "MAINT-1:post",
        "history_segment_id": "MAINT-1:post",
        "source_kind": "maintenance_replay_overlay",
        "state_version": 3,
        "equipment_id": "CNC-1",
    }


def _row() -> dict[str, object]:
    return {
        "contract_version": "runtime-overlay-observation-v1",
        "schema_version": "2",
        "asset_id": "CNC-1",
        "equipment_id": "CNC-1",
        "observed_at": "2026-08-27T01:00:00+00:00",
        "simulation_session_id": "SIM-1",
        "maintenance_action_id": "ACTION-1",
        "maintenance_event_id": "MAINT-1",
        "overlay_branch_id": "MAINT-1:post",
        "history_segment_id": "MAINT-1:post",
        "source_kind": "maintenance_replay_overlay",
        "state_version": 3,
        "tool_wear_min": 0,
    }


def test_overlay_delta_is_frozen_as_content_addressed_generator_input(tmp_path: Path) -> None:
    rows = [_row()]
    snapshot_root = tmp_path / "shared-runtime-pipeline-input"

    first = _materialize_overlay_pipeline_snapshot(snapshot_root, _event(), rows)
    second = _materialize_overlay_pipeline_snapshot(snapshot_root, _event(), rows)

    snapshot = Path(first["source_uri"])
    content = snapshot.read_bytes()
    assert first == second
    assert snapshot.parent == snapshot_root
    assert snapshot.name == f"sha256-{first['source_checksum']}.jsonl"
    assert hashlib.sha256(content).hexdigest() == first["source_checksum"]
    assert first["size_bytes"] == len(content)
    assert first["source_contract_version"] == "runtime-overlay-observation-v1"
    assert first["source_schema_version"] == "2"
    assert json.loads(content.decode("utf-8")) == rows[0]


def test_overlay_snapshot_does_not_change_when_branch_file_keeps_growing(tmp_path: Path) -> None:
    producer_root = tmp_path / "producer-owned-output"
    snapshot_root = tmp_path / "shared-runtime-pipeline-input"
    branch = producer_root / "runtime_overlay" / "branch.jsonl"
    branch.parent.mkdir(parents=True)
    branch.write_text(json.dumps(_row()) + "\n", encoding="utf-8")
    original_branch = branch.read_bytes()
    snapshot = _materialize_overlay_pipeline_snapshot(snapshot_root, _event(), [_row()])
    frozen = Path(snapshot["source_uri"]).read_bytes()

    branch.write_text(
        branch.read_text(encoding="utf-8") + json.dumps({**_row(), "observed_at": "2026-08-27T01:10:00+00:00"}) + "\n",
        encoding="utf-8",
    )

    assert Path(snapshot["source_uri"]).read_bytes() == frozen
    assert hashlib.sha256(frozen).hexdigest() == snapshot["source_checksum"]
    assert not producer_root.joinpath("runtime_pipeline_input").exists()
    assert original_branch != branch.read_bytes()
    assert Path(snapshot["source_uri"]).parent == snapshot_root


def test_runtime_pipeline_snapshot_does_not_mutate_producer_output(tmp_path: Path) -> None:
    producer_root = tmp_path / "producer-owned-output"
    producer_root.mkdir()
    marker = producer_root / "overlay.jsonl"
    marker.write_text(json.dumps(_row()) + "\n", encoding="utf-8")
    before = marker.read_bytes()
    snapshot_root = tmp_path / "shared-runtime-pipeline-input"

    snapshot = _materialize_overlay_pipeline_snapshot(
        snapshot_root,
        _event(),
        [_row()],
    )

    assert marker.read_bytes() == before
    assert Path(snapshot["source_uri"]).parent == snapshot_root
    assert not producer_root.joinpath("runtime_pipeline_input").exists()


def test_runtime_pipeline_snapshot_root_is_required_and_absolute(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.live_predictive_maintenance import runtime_pipeline_input_root

    monkeypatch.delenv("ONTOLOGY_DASHBOARD_RUNTIME_PIPELINE_INPUT_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="is required"):
        runtime_pipeline_input_root()

    monkeypatch.setenv("ONTOLOGY_DASHBOARD_RUNTIME_PIPELINE_INPUT_ROOT", "relative/path")
    with pytest.raises(RuntimeError, match="must be an absolute path"):
        runtime_pipeline_input_root()

    expected = tmp_path / "shared-runtime-pipeline-input"
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_RUNTIME_PIPELINE_INPUT_ROOT", str(expected))
    assert runtime_pipeline_input_root() == expected.resolve()


def test_generator_snapshot_uses_cumulative_history_not_only_latest_delta(
    tmp_path: Path,
) -> None:
    producer_root = tmp_path / "producer-owned-output"
    snapshot_root = tmp_path / "shared-runtime-pipeline-input"
    vector_path = (
        Path(__file__).parents[1]
        / "contracts"
        / "test-vectors"
        / "runtime-overlay-output-v1"
        / "observation-unicode.json"
    )
    first = json.loads(vector_path.read_text(encoding="utf-8"))
    second = {
        **first,
        "sequence": 2,
        "observation_id": "obs-22222222222222222222222222222222",
        "observed_at": "2026-08-18T01:50:00+00:00",
        "generated_at": "2026-08-18T02:01:00+00:00",
    }
    second["observation_sha256"] = semantic_observation_sha256(second)
    event = {
        "contract_version": "runtime-overlay-observations-available-v1",
        "event_type": "runtime_overlay.observations.available",
        "event_id": "OVERLAY-AVAILABLE:MAINT-1:post:2",
        "simulation_session_id": first["simulation_session_id"],
        "equipment_id": first["equipment_id"],
        "maintenance_action_id": first["maintenance_action_id"],
        "maintenance_event_id": first["maintenance_event_id"],
        "overlay_branch_id": first["overlay_branch_id"],
        "history_segment_id": first["history_segment_id"],
        "source_kind": "maintenance_replay_overlay",
        "state_version": first["state_version"],
        "batch_rows": 1,
        "generated_rows": 2,
        "observed_from": second["observed_at"],
        "observed_to": second["observed_at"],
        "storage_reference": "",
    }
    event["storage_reference"] = expected_storage_reference(event)
    storage = producer_root.joinpath(*Path(event["storage_reference"]).parts)
    storage.parent.mkdir(parents=True)
    storage.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in (first, second)) + "\n",
        encoding="utf-8",
    )

    history = _read_overlay_history_rows(producer_root, event)
    snapshot = _materialize_overlay_pipeline_snapshot(snapshot_root, event, history)
    frozen_rows = [
        json.loads(line)
        for line in Path(snapshot["source_uri"]).read_text(encoding="utf-8").splitlines()
    ]

    assert [row["observation_id"] for row in history] == [
        first["observation_id"],
        second["observation_id"],
    ]
    assert frozen_rows == history


def test_generator_enqueue_client_sends_pr127_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={**captured, "status": "queued"})

    client = GeneratorRuntimePipelineClient(
        "http://generator/internal/runtime-pipeline/enqueue",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    snapshot = {
        "job_id": "runtime-overlay-job",
        "source_uri": "/shared/runtime_pipeline_input/source.jsonl",
        "source_checksum": "a" * 64,
        "size_bytes": 123,
        "source_contract_version": "runtime-overlay-observation-v1",
        "source_schema_version": "2",
    }
    payload = _overlay_generator_enqueue_payload(
        snapshot,
        _event(),
        dataset_id="canonical-ai4i-v1",
        dataset_version="canonical-ai4i-physics-v3.1",
    )

    result = client.enqueue(payload)

    assert captured == payload
    assert result["status"] == "queued"


def test_overlay_enqueue_payload_preserves_operational_lineage() -> None:
    payload = _overlay_generator_enqueue_payload(
        {
            "job_id": "runtime-overlay-job",
            "source_uri": "/shared/runtime_pipeline_input/source.jsonl",
            "source_checksum": "a" * 64,
            "size_bytes": 123,
            "source_contract_version": "runtime-overlay-observation-v1",
            "source_schema_version": "2",
        },
        _event(),
        dataset_id="canonical-ai4i-v1",
        dataset_version="canonical-ai4i-physics-v3.1",
    )

    assert payload["source_kind"] == "maintenance_replay_overlay"
    assert payload["lineage"] == {
        "simulation_session_id": "SIM-1",
        "overlay_branch_id": "MAINT-1:post",
        "history_segment_id": "MAINT-1:post",
        "maintenance_event_id": "MAINT-1",
        "maintenance_action_id": "ACTION-1",
        "state_version": 3,
    }


def test_overlay_enqueue_payload_rejects_non_overlay_source_kind() -> None:
    with pytest.raises(ValueError, match="source_kind=maintenance_replay_overlay"):
        _overlay_generator_enqueue_payload(
            {
                "job_id": "runtime-overlay-job",
                "source_uri": "/shared/runtime_pipeline_input/source.jsonl",
                "source_checksum": "a" * 64,
                "size_bytes": 123,
                "source_contract_version": "runtime-overlay-observation-v1",
                "source_schema_version": "2",
            },
            {**_event(), "source_kind": "canonical_observation"},
            dataset_id="canonical-ai4i-v1",
            dataset_version="canonical-ai4i-physics-v3.1",
        )


@pytest.mark.parametrize(
    "code",
    [
        "PIPELINE_DUPLICATE_INPUT",
        "PIPELINE_SOURCE_ALREADY_REGISTERED",
        "PIPELINE_SOURCE_ALREADY_PROCESSED",
    ],
)
def test_generator_enqueue_client_treats_same_source_redelivery_as_reuse(code: str) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            409,
            json={"error": {"code": code, "message": "duplicate"}},
        )
    )
    client = GeneratorRuntimePipelineClient(
        "http://generator/internal/runtime-pipeline/enqueue",
        client=httpx.Client(transport=transport),
    )

    result = client.enqueue({"job_id": "stable-job"})

    assert result == {
        "job_id": "stable-job",
        "status": "reused",
        "duplicate_code": code,
    }


def test_generator_enqueue_client_fails_closed_without_endpoint() -> None:
    client = GeneratorRuntimePipelineClient(endpoint="")
    with pytest.raises(
        GeneratorRuntimePipelineUnavailable,
        match="ONTOLOGY_DASHBOARD_GENERATOR_RUNTIME_ENQUEUE_URL",
    ):
        client.enqueue({"job_id": "job"})


def test_overlay_lineage_round_trips_through_generator_queue_checkpoint_and_batch(
    tmp_path: Path,
) -> None:
    from systems.generator.app.runtime_pipeline.pipeline_queue import PipelineQueue
    from systems.generator.app.runtime_pipeline.pipeline_router import EnqueueRequest
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
        ArtifactReference,
        InternalModelPredictionResult,
        PredictionResultProducer,
    )
    from systems.generator.app.runtime_pipeline.pipeline_state import PipelineStateManager
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        build_external_prediction_batch,
    )

    snapshot = _materialize_overlay_pipeline_snapshot(
        tmp_path / "shared-runtime-pipeline-input",
        _event(),
        [_row()],
    )
    payload = _overlay_generator_enqueue_payload(
        snapshot,
        _event(),
        dataset_id="canonical-ai4i-v1",
        dataset_version="canonical-ai4i-physics-v3.1",
    )
    request = EnqueueRequest.model_validate(payload)
    runtime_input = request.to_input_identity()
    queue = PipelineQueue(db_path=tmp_path / "runtime-pipeline-queue.db")
    item = queue.enqueue(
        job_id=request.job_id,
        runtime_input=runtime_input,
        size_bytes=request.size_bytes,
    )

    source_context = runtime_input.source
    state = PipelineStateManager.create(
        run_id="runtime-overlay-run-1",
        job_id=item.job_id,
        source_ref=ArtifactReference(
            uri=item.source_uri,
            sha256=item.source_checksum,
            role="observation_source",
            size_bytes=item.size_bytes,
        ),
        source_context=source_context,
    )
    checkpoint = state.record_checkpoint(
        stage_name="source_validated",
        next_stage="preprocessing",
        source_identity=item.source_identity or "",
        runtime_input=runtime_input,
        model_set_id="pdm-runtime",
        model_set_version="1.0.0",
        model_set_payload_sha256="f" * 64,
    )

    internal_result = InternalModelPredictionResult(
        asset_id="CNC-1",
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        status="succeeded",
        observed_at="2026-08-27T01:00:00+00:00",
        score=0.2,
        manifest_checksum="b" * 64,
        feature_schema_version="pdm-feature-v2",
        history_requirement_version="pdm-history-v1",
        label_schema_version="pdm-label-v3",
    )
    batch = build_external_prediction_batch(
        internal_results=[internal_result],
        source_context=runtime_input,
        active_model_set_snapshot=ActiveModelSetSnapshot(
            model_set_id="pdm-runtime",
            model_set_version="1.0.0",
            models=[
                ActiveModelSnapshotItem(
                    model_id="pdm-lightgbm",
                    model_version="1.0.0",
                    required=True,
                    model_artifact_manifest_sha256="b" * 64,
                )
            ],
        ),
        producer_snapshot=PredictionResultProducer(
            system="systems.generator",
            runtime_version="test-runtime-v1",
        ),
        emitted_at=datetime(2026, 8, 27, 1, 1, tzinfo=timezone.utc),
        model_schema_map={
            "pdm-lightgbm": {
                "feature_schema_sha256": "c" * 64,
                "history_requirement_sha256": "d" * 64,
                "label_schema_sha256": "e" * 64,
                "label_schema_version": "pdm-label-v3",
            }
        },
    )

    result = batch.results[0]
    assert item.source_contract_version == "runtime-overlay-observation-v1"
    assert item.source_schema_version == "2"
    assert checkpoint.source_context == source_context
    assert result.source_kind == "maintenance_replay_overlay"
    assert result.source_ref.sha256 == snapshot["source_checksum"]
    assert result.lineage == item.lineage
