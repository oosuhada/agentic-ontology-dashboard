"""Run the complete local predictive-maintenance real-time topology.

Starts PostgreSQL/bootstrap, Backend, Generator Runtime, gen_data, the live
ingestor, the Maintenance replay dispatcher, and Frontend.  All generated files
are isolated under data_preprocessed/local-realtime and are ignored by Git.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GEN_DATA_ROOT = ROOT.parent / "gen_data"
LIVE_SOURCE_VERSION = "gen-data-wall-clock-live-v2"
OBSERVATION_INTERVAL_MINUTES = 10
MODEL_MINIMUM_HISTORY_ROWS = 36
MODEL_MINIMUM_HISTORY_HOURS = (
    MODEL_MINIMUM_HISTORY_ROWS * OBSERVATION_INTERVAL_MINUTES // 60
)
DEFAULT_HISTORY_BACKFILL_HOURS = 168
# Backward-compatible import name for older local demo helpers.  The value is
# historical backfill, not the model warm-up requirement.
DEFAULT_INITIAL_HISTORY_HOURS = DEFAULT_HISTORY_BACKFILL_HOURS
DEFAULT_SIMULATION_HOURS = 336


def _wait(url: str, *, seconds: int = 90) -> None:
    deadline = time.monotonic() + seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
        time.sleep(1)
    raise RuntimeError(f"service did not become ready: {url} ({last_error})")


def _wait_database(database_url: str, *, seconds: int = 90) -> None:
    """Wait until PostgreSQL accepts queries before running migrations."""
    import psycopg

    deadline = time.monotonic() + seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(database_url, connect_timeout=2) as connection:
                connection.execute("SELECT 1")
            return
        except psycopg.Error as exc:
            last_error = exc
        time.sleep(1)
    raise RuntimeError(f"database did not become ready: {database_url} ({last_error})")


def _bootstrap_database(*, python: str, database_url: str, base_env: dict[str, str]) -> None:
    """Create the schema and demo identity scope before package ingestion."""
    _wait_database(database_url)
    subprocess.run(
        [python, "-m", "app.migrate"],
        cwd=ROOT / "systems" / "backend",
        env=base_env,
        check=True,
    )
    subprocess.run(
        [
            python,
            "-c",
            (
                "from app.dependencies import get_identity_service; "
                "get_identity_service(); "
                "print('[database] reference scope and demo accounts ready')"
            ),
        ],
        cwd=ROOT / "systems" / "backend",
        env=base_env,
        check=True,
    )


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _next_free_port(start: int, *, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"no free local port in range {start}..{start + attempts - 1}")


def _latest_live_observed_at(database_url: str) -> datetime | None:
    """Return the persisted live-stream cursor used to continue simulation time."""
    import psycopg

    with psycopg.connect(database_url) as connection:
        connection.execute(
            "SELECT set_config('app.organization_id', %s, true)",
            ("org-ontology-demo",),
        )
        connection.execute(
            "SELECT set_config('app.project_id', %s, true)",
            ("manufacturing-demo-project",),
        )
        connection.execute(
            "SELECT set_config('app.workspace_id', %s, true)",
            ("manufacturing-demo",),
        )
        row = connection.execute(
            """
            SELECT MAX(live_observation.observed_at)
            FROM (
              SELECT observation.observed_at
              FROM pm_cnc_observations observation
              JOIN dataset_versions version
                ON version.id=observation.dataset_version_id
               AND version.organization_id=observation.organization_id
               AND version.project_id=observation.project_id
               AND version.workspace_id=observation.workspace_id
              WHERE observation.organization_id=%s
                AND observation.project_id=%s
                AND observation.workspace_id=%s
                AND version.source_version=%s
              UNION ALL
              SELECT observation.observed_at
              FROM pm_compressor_observations observation
              JOIN dataset_versions version
                ON version.id=observation.dataset_version_id
               AND version.organization_id=observation.organization_id
               AND version.project_id=observation.project_id
               AND version.workspace_id=observation.workspace_id
              WHERE observation.organization_id=%s
                AND observation.project_id=%s
                AND observation.workspace_id=%s
                AND version.source_version=%s
            ) live_observation
            """,
            (
                "org-ontology-demo",
                "manufacturing-demo-project",
                "manufacturing-demo",
                LIVE_SOURCE_VERSION,
                "org-ontology-demo",
                "manufacturing-demo-project",
                "manufacturing-demo",
                LIVE_SOURCE_VERSION,
            ),
        ).fetchone()
    return None if row is None else row[0]


def _simulation_start_at(
    *,
    now: datetime,
    latest_observed_at: datetime | None,
    interval_minutes: int = 10,
    history_backfill_hours: int = MODEL_MINIMUM_HISTORY_HOURS,
) -> datetime:
    """Choose a cadence-safe start without mixing histories from prior sessions."""
    if latest_observed_at is not None:
        return latest_observed_at + timedelta(minutes=interval_minutes)
    return now - timedelta(hours=history_backfill_hours)


def _initial_fast_forward_target_hours(
    *,
    latest_observed_at: datetime | None,
    history_backfill_hours: int = DEFAULT_HISTORY_BACKFILL_HOURS,
) -> int | None:
    """Return the one-time historical backfill target for a new live stream."""
    if latest_observed_at is not None:
        return None
    if history_backfill_hours <= 0:
        raise ValueError("history backfill duration must be positive")
    return history_backfill_hours


def _fast_forward_initial_history(
    *,
    gen_data_port: int,
    run_id: str,
    latest_observed_at: datetime | None,
    history_backfill_hours: int = DEFAULT_HISTORY_BACKFILL_HOURS,
) -> dict | None:
    """Generate historical observations on the original run without changing lineage."""
    target_hours = _initial_fast_forward_target_hours(
        latest_observed_at=latest_observed_at,
        history_backfill_hours=history_backfill_hours,
    )
    if target_hours is None:
        return None
    return _post_json(
        (
            f"http://127.0.0.1:{gen_data_port}/api/runs/"
            f"{run_id}/simulation/fast-forward"
        ),
        {"target_elapsed_hours": target_hours},
    )


def _select_live_dataset_for_project_users(
    database_url: str,
    *,
    timeout_seconds: int = 30,
) -> tuple[str, int]:
    """Make the local real-time Dataset visible in Operations for demo users."""
    import psycopg

    deadline = time.monotonic() + timeout_seconds
    while True:
        with psycopg.connect(database_url) as connection:
            for key, value in (
                ("app.organization_id", "org-ontology-demo"),
                ("app.project_id", "manufacturing-demo-project"),
                ("app.workspace_id", "manufacturing-demo"),
            ):
                connection.execute("SELECT set_config(%s, %s, true)", (key, value))
            row = connection.execute(
                """
                SELECT v.id
                FROM dataset_versions v
                WHERE v.organization_id=%s AND v.project_id=%s AND v.workspace_id=%s
                  AND v.source_version='gen-data-wall-clock-live-v2'
                  AND v.status='published'
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
                  ) <= now() + interval '5 minutes'
                ORDER BY (
                    SELECT MAX(r.observed_at) FROM pm_result_artifacts r
                    WHERE r.organization_id=v.organization_id
                      AND r.project_id=v.project_id
                      AND r.workspace_id=v.workspace_id
                      AND r.dataset_version_id=v.id
                      AND r.model_version<>'presentation-live-v1'
                ) DESC NULLS LAST,
                v.created_at DESC
                LIMIT 1
                """,
                (
                    "org-ontology-demo",
                    "manufacturing-demo-project",
                    "manufacturing-demo",
                ),
            ).fetchone()
            if row is not None:
                dataset_version_id = str(row[0])
                selected = connection.execute(
                    """
                    INSERT INTO pm_workspace_dataset_selections(
                        organization_id,project_id,workspace_id,user_id,
                        dataset_version_id,selection_mode,created_at,updated_at
                    )
                    SELECT pm.organization_id,pm.project_id,%s,pm.user_id,
                           %s,'automatic',now(),now()
                    FROM project_memberships pm
                    WHERE pm.organization_id=%s AND pm.project_id=%s
                      AND pm.status='active'
                    ON CONFLICT (organization_id,project_id,workspace_id,user_id)
                    DO UPDATE SET dataset_version_id=EXCLUDED.dataset_version_id,
                                  selection_mode='automatic',updated_at=now()
                    WHERE pm_workspace_dataset_selections.selection_mode='automatic'
                    RETURNING user_id
                    """,
                    (
                        "manufacturing-demo",
                        dataset_version_id,
                        "org-ontology-demo",
                        "manufacturing-demo-project",
                    ),
                ).fetchall()
                return dataset_version_id, len(selected)
        if time.monotonic() >= deadline:
            raise RuntimeError("live Dataset Version was not created before timeout")
        time.sleep(1)


class ProcessGroup:
    def __init__(self, log_root: Path) -> None:
        self.log_root = log_root
        self.log_root.mkdir(parents=True, exist_ok=True)
        self.processes: list[tuple[str, subprocess.Popen, object]] = []

    def start(
        self,
        name: str,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
    ) -> subprocess.Popen:
        log = (self.log_root / f"{name}.log").open("w", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        self.processes.append((name, process, log))
        print(f"[start] {name} pid={process.pid} log={self.log_root / (name + '.log')}")
        return process

    def assert_running(self) -> None:
        failed = [(name, proc.returncode) for name, proc, _ in self.processes if proc.poll() is not None]
        if failed:
            raise RuntimeError(f"runtime process exited unexpectedly: {failed}")

    def stop(self) -> None:
        if os.name == "nt":
            # npm/npx and venv launchers create child processes on Windows.
            # Terminating only the immediate Popen object leaves Vite/Uvicorn
            # listeners orphaned and forces every later run onto a new port.
            for _, process, _ in reversed(self.processes):
                if process.poll() is None:
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
            for _, _, log in self.processes:
                log.close()
            return
        for _, process, _ in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
        deadline = time.monotonic() + 8
        for _, process, _ in reversed(self.processes):
            if process.poll() is None:
                try:
                    process.wait(timeout=max(0.1, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    process.kill()
        for _, _, log in self.processes:
            log.close()


def _python_for(root: Path) -> str:
    candidate = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(candidate if candidate.exists() else Path(sys.executable))


def _base_env(database_url: str) -> dict[str, str]:
    env = os.environ.copy()
    python_paths = [str(ROOT), str(ROOT / "systems" / "backend"), str(ROOT / "ml" / "src")]
    if env.get("PYTHONPATH"):
        python_paths.append(env["PYTHONPATH"])
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(python_paths),
            "ONTOLOGY_DASHBOARD_DATABASE_URL": database_url,
            "PYTHONIOENCODING": "utf-8",
            "APP_ENV": "local",
            "SEED_DEMO_ACCOUNTS": "1",
            "ONTOLOGY_DASHBOARD_SEED_REFERENCE_DATA": "true",
        }
    )
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=8100)
    parser.add_argument("--generator-port", type=int, default=8200)
    parser.add_argument("--gen-data-port", type=int, default=8300)
    parser.add_argument("--web-port", type=int, default=3100)
    parser.add_argument("--postgres-port", type=int, default=5432)
    parser.add_argument("--speed", type=float, default=60.0)
    parser.add_argument(
        "--simulation-hours",
        type=int,
        default=DEFAULT_SIMULATION_HOURS,
        help="Total simulated horizon. Defaults to 336 hours (14 days).",
    )
    parser.add_argument(
        "--history-hours",
        "--initial-history-hours",
        dest="history_hours",
        type=int,
        default=DEFAULT_HISTORY_BACKFILL_HOURS,
        help=(
            "Historical backfill generated before the live demo reaches the "
            "current-time boundary. Defaults to 168 hours (7 days). The model "
            "itself requires only 36 ten-minute rows (6 hours)."
        ),
    )
    parser.add_argument(
        "--models-store",
        type=Path,
        default=ROOT / "models_store" / "local-realtime",
    )
    parser.add_argument("--skip-postgres", action="store_true")
    parser.add_argument("--skip-bootstrap", action="store_true")
    parser.add_argument("--skip-model-preparation", action="store_true")
    parser.add_argument(
        "--keep-dataset-selection",
        action="store_true",
        help="Do not select the live Dataset Version for local demo project users.",
    )
    args = parser.parse_args()

    if args.history_hours < MODEL_MINIMUM_HISTORY_HOURS:
        parser.error(
            "--history-hours must provide at least "
            f"{MODEL_MINIMUM_HISTORY_HOURS} hours for runtime model history"
        )
    if args.simulation_hours <= args.history_hours:
        parser.error(
            "--simulation-hours must be greater than --history-hours so "
            "the same run can continue into post-maintenance observations"
        )

    args.api_port = _next_free_port(args.api_port)
    args.generator_port = _next_free_port(args.generator_port)
    args.gen_data_port = _next_free_port(args.gen_data_port)
    args.web_port = _next_free_port(args.web_port)

    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    simulation_session_id = f"local-realtime-{session_id}"
    runtime_root = ROOT / "data_preprocessed" / "local-realtime"
    session_root = runtime_root / "sessions" / session_id
    stream_root = session_root / "gen-data-runtime"
    snapshot_root = session_root / "pipeline-input"
    log_root = session_root / "logs"
    models_store = args.models_store.expanduser().resolve()
    maintenance_file = stream_root / "runtime_overlay" / "maintenance_events.jsonl"
    database_url = os.getenv(
        "ONTOLOGY_DASHBOARD_DATABASE_URL",
        f"postgresql://ontology:ontology-local-only@127.0.0.1:{args.postgres_port}/ontology_dashboard",
    )
    python = _python_for(ROOT)
    gen_data_python = _python_for(GEN_DATA_ROOT)

    if not args.skip_postgres:
        docker_env = os.environ.copy()
        docker_env["POSTGRES_PORT"] = str(args.postgres_port)
        subprocess.run(
            ["docker", "compose", "-f", "infra/docker-compose.yml", "--profile", "polyglot", "up", "-d", "postgres"],
            cwd=ROOT,
            env=docker_env,
            check=True,
        )

    base_env = _base_env(database_url)
    _bootstrap_database(
        python=python,
        database_url=database_url,
        base_env=base_env,
    )
    if not args.skip_bootstrap:
        subprocess.run(
            [
                python,
                "scripts/bootstrap_predictive_maintenance_v3_1_demo.py",
                "--package-root",
                str(GEN_DATA_ROOT),
                "--database-url",
                database_url,
                "--skip-graph",
            ],
            cwd=ROOT,
            env=base_env,
            check=True,
        )
    if not args.skip_model_preparation:
        subprocess.run(
            [
                python,
                "scripts/prepare_local_realtime_models.py",
                "--gen-data-root",
                str(GEN_DATA_ROOT),
                "--models-store",
                str(models_store),
            ],
            cwd=ROOT,
            env=base_env,
            check=True,
        )

    token = f"local-generator-{session_id}"
    processes = ProcessGroup(log_root)
    try:
        backend_env = base_env.copy()
        backend_env.update(
            {
                "PREDICTION_RESULT_INGEST_TOKEN": token,
                "PREDICTION_RESULT_INGEST_ORGANIZATION_ID": "org-ontology-demo",
                "ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK": "0",
                # The launcher may move the Frontend to the next free port. Keep
                # the Backend CORS boundary aligned with the selected port so
                # browser login/API calls do not fail during local E2E runs.
                "ONTOLOGY_DASHBOARD_ALLOWED_ORIGINS": f"http://127.0.0.1:{args.web_port}",
            }
        )
        processes.start(
            "backend",
            [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.api_port)],
            cwd=ROOT / "systems" / "backend",
            env=backend_env,
        )
        _wait(f"http://127.0.0.1:{args.api_port}/health")

        generator_env = base_env.copy()
        generator_env.update(
            {
                "MODELS_STORE_DIR": str(models_store.resolve()),
                "MODEL_ARTIFACT_URI": str((models_store / "artifacts").resolve()),
                "DATA_DIR": str((GEN_DATA_ROOT / "canonical" / "dataset").resolve()),
                "DATA_PREPROCESSED_DIR": str((session_root / "generator-state").resolve()),
                "GENERATOR_PIPELINE_INPUT_ROOTS": str(snapshot_root.resolve()),
                "GENERATOR_RUNTIME_PREDICTION_ENABLED": "true",
                "GENERATOR_RUNTIME_VERSION": "local-realtime-v1",
                "GENERATOR_PREDICTION_RESULT_URL": f"http://127.0.0.1:{args.api_port}/internal/prediction-results",
                "GENERATOR_PREDICTION_RESULT_PROJECT_ID": "manufacturing-demo-project",
                "GENERATOR_PREDICTION_RESULT_WORKSPACE_ID": "manufacturing-demo",
                "GENERATOR_PREDICTION_RESULT_TOKEN": token,
            }
        )
        processes.start(
            "generator",
            [python, "-m", "uvicorn", "systems.generator.app.main:app", "--host", "127.0.0.1", "--port", str(args.generator_port)],
            cwd=ROOT,
            env=generator_env,
        )
        _wait(f"http://127.0.0.1:{args.generator_port}/health")

        gen_data_env = os.environ.copy()
        gen_data_env.update(
            {
                "PYTHONPATH": str(GEN_DATA_ROOT),
                "GEN_DATA_OUTPUT_DIR": str(stream_root.resolve()),
                "GEN_DATA_RUNTIME_OVERLAY_EVENT_FILE": str(maintenance_file.resolve()),
                "GEN_DATA_RUNTIME_OVERLAY_FAST_FORWARD_ROWS": str(
                    MODEL_MINIMUM_HISTORY_ROWS
                ),
            }
        )
        processes.start(
            "gen-data",
            [gen_data_python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.gen_data_port)],
            cwd=GEN_DATA_ROOT,
            env=gen_data_env,
        )
        _wait(f"http://127.0.0.1:{args.gen_data_port}/health/ready")

        worker_env = base_env.copy()
        worker_env.update(
            {
                "GEN_DATA_RUNTIME_OUTPUT_ROOT": str(stream_root.resolve()),
                "ONTOLOGY_DASHBOARD_SIMULATION_SESSION_ID": simulation_session_id,
                "ONTOLOGY_DASHBOARD_RUNTIME_PIPELINE_INPUT_ROOT": str(snapshot_root.resolve()),
                "ONTOLOGY_DASHBOARD_GENERATOR_RUNTIME_ENQUEUE_URL": f"http://127.0.0.1:{args.generator_port}/internal/runtime-pipeline/enqueue",
                "LIVE_PM_POLL_SECONDS": "5",
                "ONTOLOGY_DASHBOARD_OUTBOX_ORGANIZATION_ID": "org-ontology-demo",
                "ONTOLOGY_DASHBOARD_OUTBOX_PROJECT_ID": "manufacturing-demo-project",
                "ONTOLOGY_DASHBOARD_MAINTENANCE_REPLAY_EVENT_FILE": str(maintenance_file.resolve()),
                "ONTOLOGY_DASHBOARD_ALLOW_ACCELERATED_SIMULATION": "1",
            }
        )
        processes.start(
            "live-ingestor",
            [python, "-m", "app.live_predictive_maintenance"],
            cwd=ROOT / "systems" / "backend",
            env=worker_env,
        )
        processes.start(
            "maintenance-dispatcher",
            [python, "-m", "app.maintenance_replay_dispatcher", "--poll-seconds", "1"],
            cwd=ROOT / "systems" / "backend",
            env=worker_env,
        )
        # A clean database has no live Dataset Version until gen_data has
        # produced the first simulation observations and live-ingestor has
        # persisted them. Create the run before attempting user selection.
        latest_live_observed_at = _latest_live_observed_at(database_url)
        start_at = _simulation_start_at(
            now=datetime.now(timezone.utc),
            latest_observed_at=latest_live_observed_at,
            interval_minutes=OBSERVATION_INTERVAL_MINUTES,
            history_backfill_hours=args.history_hours,
        )
        run = _post_json(
            f"http://127.0.0.1:{args.gen_data_port}/api/runs",
            {
                "run_id": simulation_session_id,
                "simulation_session_id": simulation_session_id,
                "seed": 42,
                "start_at": start_at.isoformat(),
                "duration_hours": args.simulation_hours,
                "interval_minutes": OBSERVATION_INTERVAL_MINUTES,
                "product_cycle_minutes": 20,
                "rate_profile": "balanced_demo",
                "scenario_profile": "continuous_reliability",
                "speed": args.speed,
                "continuous": True,
                "publish_opcua": False,
                "source_kind": "simulation",
                "runtime_overlay_fast_forward_rows": MODEL_MINIMUM_HISTORY_ROWS,
            },
        )
        initial_fast_forward = _fast_forward_initial_history(
            gen_data_port=args.gen_data_port,
            run_id=str(run["run_id"]),
            latest_observed_at=latest_live_observed_at,
            history_backfill_hours=args.history_hours,
        )
        if initial_fast_forward is not None:
            initial_history_rows = (
                args.history_hours * 60 // OBSERVATION_INTERVAL_MINUTES
            )
            print(
                "[history] backfill ready: "
                f"{initial_history_rows} ticks / {args.history_hours}h, "
                f"{initial_fast_forward['generated_records']} records"
            )
            print(
                "[model] minimum history: "
                f"{MODEL_MINIMUM_HISTORY_ROWS} ticks / {MODEL_MINIMUM_HISTORY_HOURS}h; "
                "maintenance replay uses the same 36-row branch-local warm-up"
            )

        # Only after the first live Dataset exists do we bind demo users to it.
        # This is the clean-start ordering required by the Windows presentation
        # topology and avoids timing out on a Dataset that has not been created.
        if not args.keep_dataset_selection:
            live_version_id, selected_users = _select_live_dataset_for_project_users(
                database_url,
                timeout_seconds=90,
            )
            print(
                f"[dataset] selected {live_version_id} for {selected_users} "
                "manufacturing-demo user(s)"
            )

        frontend_env = os.environ.copy()
        frontend_env["VITE_API_BASE_URL"] = f"http://127.0.0.1:{args.api_port}"
        npx = "npx.cmd" if os.name == "nt" else "npx"
        processes.start(
            "frontend",
            [npx, "vite", "--host", "127.0.0.1", "--port", str(args.web_port), "--strictPort"],
            cwd=ROOT / "systems" / "frontend",
            env=frontend_env,
        )
        _wait(f"http://127.0.0.1:{args.web_port}/")

        processes.assert_running()
        print("\nLocal real-time predictive-maintenance runtime is ready")
        print(f"  Web:       http://127.0.0.1:{args.web_port}/login")
        print(f"  Backend:   http://127.0.0.1:{args.api_port}/docs")
        print(f"  Generator: http://127.0.0.1:{args.generator_port}/runtime-pipeline/status")
        print(f"  gen_data:  http://127.0.0.1:{args.gen_data_port}/api/runs/{run['run_id']}")
        print(
            "  Fast-forward: POST "
            f"http://127.0.0.1:{args.gen_data_port}/api/runs/{run['run_id']}"
            "/simulation/fast-forward "
            'with {"target_elapsed_hours": 40}'
        )
        print(f"  Logs:      {log_root}")
        print("Press Ctrl+C to stop application processes (PostgreSQL is preserved).")

        while True:
            time.sleep(2)
            processes.assert_running()
    except KeyboardInterrupt:
        print("\nStopping local runtime...")
    finally:
        processes.stop()
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.default_int_handler)
    raise SystemExit(main())
