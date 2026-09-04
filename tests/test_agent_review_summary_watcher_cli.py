from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_review_summary_watcher_cli_reports_workflow_contract(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "APP_ENV": "test",
        "ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK": "1",
        "PYTHONPATH": "systems/backend:packages/backend:packages/ml_core",
    }

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/watch_agent_review_summaries.py",
            "--database",
            str(tmp_path / "watcher.db"),
            "--limit",
            "1",
            "--max-attempts",
            "1",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)

    assert payload["flow_version"] == "agent-review-summary-flow-v1.0"
    assert payload["trigger"] == "polling_watcher"
    assert payload["read_only"] is True
    assert payload["mutation_allowed"] is False
    assert payload["workflow"]["engine"] == "simple"
    assert payload["workflow"]["max_attempts"] == 1
    assert payload["workflow"]["attempt_count"] == 1
    assert payload["workflow"]["terminal_status"] == "completed"
    assert payload["workflow"]["attempts"] == [{"attempt": 1, "status": "succeeded"}]
    assert payload["operating_mode"] == {
        "mode": "once",
        "target_scope": "project",
        "history_window": "24h",
        "limit": 1,
        "stale_detection": "summary_key",
        "summary_duplicate_policy": "reuse_existing_summary",
        "run_record_policy": "record_each_explicit_trigger",
        "poll_interval_seconds": None,
        "max_iterations": None,
        "max_attempts": 1,
        "stop_behavior": "return_after_run",
    }
    assert payload["materialized_count"] == 1


def test_agent_review_summary_watcher_cli_reports_watch_operating_mode(
    tmp_path: Path,
) -> None:
    env = {
        **os.environ,
        "APP_ENV": "test",
        "ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK": "1",
        "PYTHONPATH": "systems/backend:packages/backend:packages/ml_core",
    }

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/watch_agent_review_summaries.py",
            "--database",
            str(tmp_path / "watcher-watch.db"),
            "--limit",
            "1",
            "--max-attempts",
            "2",
            "--watch",
            "--interval-seconds",
            "1.5",
            "--max-iterations",
            "1",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)

    assert payload["operating_mode"]["mode"] == "watch"
    assert payload["operating_mode"]["poll_interval_seconds"] == 1.5
    assert payload["operating_mode"]["max_iterations"] == 1
    assert payload["operating_mode"]["max_attempts"] == 2
    assert payload["operating_mode"]["stale_detection"] == "summary_key"
    assert payload["operating_mode"]["summary_duplicate_policy"] == (
        "reuse_existing_summary"
    )
    assert payload["operating_mode"]["run_record_policy"] == (
        "record_each_explicit_trigger"
    )
    assert payload["operating_mode"]["stop_behavior"] == (
        "bounded_iterations_or_signal"
    )
