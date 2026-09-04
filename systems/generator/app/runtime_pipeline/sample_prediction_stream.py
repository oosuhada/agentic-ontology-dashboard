"""Local sample Prediction Result Batch stream for receiver/UI testing."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Sequence

from systems.generator.app.runtime_pipeline.pipeline_schema import (
    ActiveModelSetSnapshot,
    ActiveModelSnapshotItem,
    PredictionResultBatchPayload,
    PredictionResultBatchSourceContext,
    PredictionResultItem,
    PredictionResultLineage,
    PredictionResultProducer,
    PredictionResultSourceRef,
    compute_prediction_result_batch_id,
    compute_prediction_result_item_event_id,
    compute_prediction_result_item_sha256,
    compute_model_set_payload_sha256,
    compute_source_context_digest,
)
from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
    PredictionDeliveryService,
)


DEFAULT_ASSET_ID = "CNC-001"
DEFAULT_DATASET_ID = "canonical-ai4i-v1"
DEFAULT_DATASET_VERSION = "v1.0"
DEFAULT_MODEL_ID = "pdm-lightgbm"
DEFAULT_MODEL_VERSION = "1.0.0"
DEFAULT_INTERVAL_SECONDS = 5.0
DEFAULT_COUNT = 3

MODEL_ARTIFACT_SHA256 = "a" * 64
FEATURE_SCHEMA_SHA256 = "1" * 64
HISTORY_REQUIREMENT_SHA256 = "2" * 64
LABEL_SCHEMA_SHA256 = "3" * 64
SOURCE_SHA256 = "b" * 64


def parse_utc_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc).replace(microsecond=0)
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def score_for_tick(index: int) -> float:
    return round(min(0.98, 0.72 + (index % 6) * 0.035), 4)


def build_sample_prediction_batch(
    *,
    sequence: int,
    observed_at: datetime,
    asset_id: str = DEFAULT_ASSET_ID,
    dataset_id: str = DEFAULT_DATASET_ID,
    dataset_version: str = DEFAULT_DATASET_VERSION,
    model_id: str = DEFAULT_MODEL_ID,
    model_version: str = DEFAULT_MODEL_VERSION,
) -> PredictionResultBatchPayload:
    lineage = PredictionResultLineage(
        simulation_session_id="local-generator-sample",
        overlay_branch_id="sample-5s-stream",
        history_segment_id=f"sample-window-{sequence:04d}",
        maintenance_event_id=None,
        maintenance_action_id=None,
        state_version=sequence + 1,
    )
    source_context = PredictionResultBatchSourceContext(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        source_uri=f"sample/generator-5s/{asset_id}/{sequence:04d}.jsonl",
        source_checksum=SOURCE_SHA256,
        source_kind="simulation_overlay",
        source_contract_version="sample-generator-stream-v1",
        source_schema_version="prediction-result-sample-v1",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=lineage,
    )
    model_set = ActiveModelSetSnapshot(
        model_set_id="sample-pdm-model-set",
        model_set_version="local-5s",
        models=[
            ActiveModelSnapshotItem(
                model_id=model_id,
                model_version=model_version,
                required=True,
                model_artifact_manifest_sha256=MODEL_ARTIFACT_SHA256,
                selected_threshold=0.55,
            )
        ],
    )
    model_set_payload_sha256 = compute_model_set_payload_sha256(
        model_set_id=model_set.model_set_id,
        model_set_version=model_set.model_set_version,
        models=model_set.models,
    )
    source_context_digest = compute_source_context_digest(source_context)
    event_id = compute_prediction_result_item_event_id(
        source_context_digest=source_context_digest,
        asset_id=asset_id,
        observed_at=observed_at,
        model_id=model_id,
        model_version=model_version,
        model_artifact_manifest_sha256=MODEL_ARTIFACT_SHA256,
    )
    item_dict: dict[str, Any] = {
        "event_id": event_id,
        "asset_id": asset_id,
        "observed_at": observed_at,
        "source_kind": "simulation_overlay",
        "source_ref": {
            "uri": source_context.source_uri,
            "sha256": source_context.source_checksum,
        },
        "output_status": "predicted",
        "score": score_for_tick(sequence),
        "model_id": model_id,
        "model_version": model_version,
        "model_artifact_manifest_sha256": MODEL_ARTIFACT_SHA256,
        "feature_schema_version": "v1.0",
        "history_requirement_version": "v1.0",
        "label_schema_version": "v1.0",
        "feature_schema_sha256": FEATURE_SCHEMA_SHA256,
        "history_requirement_sha256": HISTORY_REQUIREMENT_SHA256,
        "label_schema_sha256": LABEL_SCHEMA_SHA256,
        "lineage": lineage.model_dump(mode="json"),
        "failure_reason": None,
    }
    item_fields = dict(item_dict)
    item_fields["source_ref"] = PredictionResultSourceRef(
        uri=source_context.source_uri,
        sha256=source_context.source_checksum,
    )
    item_fields["lineage"] = lineage
    item_fields["payload_sha256"] = compute_prediction_result_item_sha256(item_dict)
    item = PredictionResultItem(**item_fields)
    batch_id = compute_prediction_result_batch_id(
        source_context_digest=source_context_digest,
        model_set_id=model_set.model_set_id,
        model_set_version=model_set.model_set_version,
        model_set_payload_sha256=model_set_payload_sha256,
        sorted_event_ids=[item.event_id],
    )
    return PredictionResultBatchPayload(
        contract_version="prediction-result-batch-v1",
        batch_id=batch_id,
        producer=PredictionResultProducer(
            system="systems.generator",
            runtime_version="sample-5s-stream",
            outbox_id=None,
        ),
        emitted_at=datetime.now(timezone.utc).replace(microsecond=0),
        source_context=source_context,
        model_set=model_set,
        results=[item],
    )


def iter_sample_prediction_batches(
    *,
    count: int,
    start_observed_at: datetime,
    event_time_step_seconds: float,
    asset_id: str = DEFAULT_ASSET_ID,
) -> Iterable[PredictionResultBatchPayload]:
    for sequence in range(count):
        yield build_sample_prediction_batch(
            sequence=sequence,
            observed_at=start_observed_at + timedelta(seconds=sequence * event_time_step_seconds),
            asset_id=asset_id,
        )


def run_sample_stream(
    *,
    count: int,
    interval_seconds: float,
    event_time_step_seconds: float,
    asset_id: str,
    start_observed_at: datetime,
    endpoint_url: str | None = None,
    dry_run: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    service = PredictionDeliveryService(endpoint_url=endpoint_url) if not dry_run else None
    receipts: list[dict[str, Any]] = []
    batches = list(
        iter_sample_prediction_batches(
            count=count,
            start_observed_at=start_observed_at,
            event_time_step_seconds=event_time_step_seconds,
            asset_id=asset_id,
        )
    )
    for index, batch in enumerate(batches):
        if dry_run:
            result = {"delivered": False, "status_code": None, "response": "dry_run"}
        else:
            assert service is not None
            result = service.send_once(batch)
        receipt = {
            "sequence": index,
            "batch_id": batch.batch_id,
            "event_id": batch.results[0].event_id,
            "asset_id": batch.results[0].asset_id,
            "observed_at": batch.results[0].observed_at.isoformat().replace("+00:00", "Z"),
            "score": batch.results[0].score,
            "delivery": result,
        }
        print(json.dumps(receipt, ensure_ascii=False), flush=True)
        receipts.append(receipt)
        if index < len(batches) - 1:
            sleep(interval_seconds)
    return receipts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send sample Prediction Result Batches every N seconds for local receiver/UI testing.",
    )
    parser.add_argument("--endpoint-url", default=None, help="Receiver URL. Defaults to GENERATOR_PREDICTION_RESULT_URL.")
    parser.add_argument("--asset-id", default=DEFAULT_ASSET_ID)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--interval-seconds", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--event-time-step-seconds", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--start-observed-at", default=None, help="UTC ISO timestamp. Defaults to current UTC second.")
    parser.add_argument("--dry-run", action="store_true", help="Build and print payload metadata without POSTing.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.count <= 0:
        raise SystemExit("--count must be positive")
    if args.interval_seconds <= 0:
        raise SystemExit("--interval-seconds must be positive")
    if args.event_time_step_seconds <= 0:
        raise SystemExit("--event-time-step-seconds must be positive")
    run_sample_stream(
        count=args.count,
        interval_seconds=args.interval_seconds,
        event_time_step_seconds=args.event_time_step_seconds,
        asset_id=args.asset_id,
        start_observed_at=parse_utc_datetime(args.start_observed_at),
        endpoint_url=args.endpoint_url,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
