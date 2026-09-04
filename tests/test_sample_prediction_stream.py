from __future__ import annotations

from datetime import datetime, timezone

from systems.generator.app.runtime_pipeline.sample_prediction_stream import (
    build_sample_prediction_batch,
    iter_sample_prediction_batches,
    run_sample_stream,
)


def test_sample_prediction_batches_advance_event_time_by_five_seconds():
    start = datetime(2026, 8, 29, 3, 0, 0, tzinfo=timezone.utc)

    batches = list(
        iter_sample_prediction_batches(
            count=3,
            start_observed_at=start,
            event_time_step_seconds=5,
            asset_id="CNC-001",
        )
    )

    assert [batch.results[0].observed_at for batch in batches] == [
        datetime(2026, 8, 29, 3, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 29, 3, 0, 5, tzinfo=timezone.utc),
        datetime(2026, 8, 29, 3, 0, 10, tzinfo=timezone.utc),
    ]
    assert len({batch.batch_id for batch in batches}) == 3
    assert all(batch.results[0].source_kind == "simulation_overlay" for batch in batches)


def test_sample_prediction_batch_matches_external_contract():
    batch = build_sample_prediction_batch(
        sequence=0,
        observed_at=datetime(2026, 8, 29, 3, 0, 0, tzinfo=timezone.utc),
        asset_id="CNC-001",
    )

    assert batch.contract_version == "prediction-result-batch-v1"
    assert batch.producer.system == "systems.generator"
    assert batch.source_context.source_kind == "simulation_overlay"
    assert batch.results[0].payload_sha256
    assert batch.results[0].score is not None


def test_run_sample_stream_sleeps_between_dry_run_batches(capsys):
    sleeps: list[float] = []

    receipts = run_sample_stream(
        count=3,
        interval_seconds=5,
        event_time_step_seconds=5,
        asset_id="CNC-001",
        start_observed_at=datetime(2026, 8, 29, 3, 0, 0, tzinfo=timezone.utc),
        dry_run=True,
        sleep=sleeps.append,
    )

    assert sleeps == [5, 5]
    assert [receipt["observed_at"] for receipt in receipts] == [
        "2026-08-29T03:00:00Z",
        "2026-08-29T03:00:05Z",
        "2026-08-29T03:00:10Z",
    ]
    output = capsys.readouterr().out
    assert "dry_run" in output
