import inspect
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import scripts.run_local_realtime as local_realtime
from scripts.run_local_realtime import (
    DEFAULT_HISTORY_BACKFILL_HOURS,
    DEFAULT_SIMULATION_HOURS,
    LIVE_SOURCE_VERSION,
    MODEL_MINIMUM_HISTORY_HOURS,
    MODEL_MINIMUM_HISTORY_ROWS,
    _bootstrap_database,
    _fast_forward_initial_history,
    _initial_fast_forward_target_hours,
    _latest_live_observed_at,
    _simulation_start_at,
)


def test_simulation_continues_exactly_one_cadence_after_persisted_cursor() -> None:
    latest = datetime(2026, 9, 2, 3, 41, 5, tzinfo=timezone.utc)

    assert _simulation_start_at(
        now=datetime(2026, 9, 2, 4, 0, tzinfo=timezone.utc),
        latest_observed_at=latest,
    ) == latest + timedelta(minutes=10)


def test_first_simulation_run_backfills_seven_days_of_history() -> None:
    now = datetime(2026, 9, 2, 4, 0, tzinfo=timezone.utc)

    assert _simulation_start_at(
        now=now,
        latest_observed_at=None,
        history_backfill_hours=DEFAULT_HISTORY_BACKFILL_HOURS,
    ) == now - timedelta(hours=168)


def test_first_live_run_fast_forwards_the_full_historical_window() -> None:
    assert _initial_fast_forward_target_hours(latest_observed_at=None) == 168


def test_one_year_history_backfill_is_supported_without_changing_model_warmup() -> None:
    now = datetime(2026, 9, 2, 4, 0, tzinfo=timezone.utc)

    assert _simulation_start_at(
        now=now,
        latest_observed_at=None,
        history_backfill_hours=8760,
    ) == now - timedelta(hours=8760)
    assert (
        _initial_fast_forward_target_hours(
            latest_observed_at=None,
            history_backfill_hours=8760,
        )
        == 8760
    )
    assert MODEL_MINIMUM_HISTORY_HOURS == 6


def test_history_backfill_is_separate_from_model_minimum_history() -> None:
    assert DEFAULT_HISTORY_BACKFILL_HOURS == 168
    assert MODEL_MINIMUM_HISTORY_ROWS == 36
    assert MODEL_MINIMUM_HISTORY_HOURS == 6
    assert DEFAULT_HISTORY_BACKFILL_HOURS > MODEL_MINIMUM_HISTORY_HOURS


def test_resumed_live_run_does_not_repeat_initial_fast_forward() -> None:
    latest = datetime(2026, 9, 2, 3, 41, 5, tzinfo=timezone.utc)

    assert _initial_fast_forward_target_hours(latest_observed_at=latest) is None


def test_initial_fast_forward_keeps_the_original_run(monkeypatch) -> None:
    calls = []

    def post_json(url, payload):
        calls.append((url, payload))
        return {"run_id": "original-run", "generated_records": 3600}

    monkeypatch.setattr(local_realtime, "_post_json", post_json)

    result = _fast_forward_initial_history(
        gen_data_port=8300,
        run_id="original-run",
        latest_observed_at=None,
    )

    assert result == {"run_id": "original-run", "generated_records": 3600}
    assert calls == [
        (
            "http://127.0.0.1:8300/api/runs/original-run/simulation/fast-forward",
            {"target_elapsed_hours": 168},
        )
    ]


def test_live_cursor_query_excludes_canonical_dataset_versions(monkeypatch) -> None:
    expected = datetime(2026, 9, 2, 3, 41, 5, tzinfo=timezone.utc)

    class Result:
        def fetchone(self):
            return (expected,)

    class Connection:
        def __init__(self):
            self.executed = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, params=None):
            self.executed.append((statement, params))
            if "SELECT MAX(live_observation.observed_at)" in statement:
                return Result()
            return self

    connection = Connection()
    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda _database_url: connection),
    )

    assert _latest_live_observed_at("postgresql://local/demo") == expected
    query, params = connection.executed[-1]
    assert query.count("version.source_version=%s") == 2
    assert params.count(LIVE_SOURCE_VERSION) == 2


def test_database_bootstrap_migrates_and_seeds_before_package_ingestion(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        local_realtime,
        "_wait_database",
        lambda database_url: calls.append(("wait", database_url)),
    )

    def run(command, *, cwd, env, check):
        calls.append(("run", command, cwd, env, check))

    monkeypatch.setattr(local_realtime.subprocess, "run", run)

    _bootstrap_database(
        python="python",
        database_url="postgresql://local/demo",
        base_env={"APP_ENV": "local"},
    )

    assert calls[0] == ("wait", "postgresql://local/demo")
    assert calls[1][1] == ["python", "-m", "app.migrate"]
    assert calls[2][1][0:2] == ["python", "-c"]
    assert "get_identity_service" in calls[2][1][2]


def test_clean_start_creates_simulation_before_selecting_live_dataset_and_frontend() -> None:
    source = inspect.getsource(local_realtime.main)
    run_create = source.index('f"http://127.0.0.1:{args.gen_data_port}/api/runs"')
    dataset_select = source.index("_select_live_dataset_for_project_users(")
    frontend_start = source.index('"frontend",')

    assert run_create < dataset_select < frontend_start
    assert '"--speed", type=float, default=60.0' in source
    assert "default=DEFAULT_SIMULATION_HOURS" in source
    assert DEFAULT_SIMULATION_HOURS == 336
    assert DEFAULT_HISTORY_BACKFILL_HOURS == 168
    assert MODEL_MINIMUM_HISTORY_HOURS == 6
    assert MODEL_MINIMUM_HISTORY_ROWS == 36
