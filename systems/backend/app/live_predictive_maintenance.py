"""Mac mini live predictive-maintenance worker entrypoint.

All prediction, persistence, and ontology-materialization behavior is owned by
the injected application/runtime services.  This module only resolves worker
configuration, invokes one application use case, and controls polling.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from app.dependencies import build_live_predictive_maintenance_service


LOGGER = logging.getLogger(__name__)
DEFAULT_STREAM_ROOT = Path("/gen-data-runtime")
RUNTIME_PIPELINE_INPUT_ROOT_ENV = "ONTOLOGY_DASHBOARD_RUNTIME_PIPELINE_INPUT_ROOT"


def runtime_pipeline_input_root() -> Path:
    raw = os.getenv(RUNTIME_PIPELINE_INPUT_ROOT_ENV, "").strip()
    if not raw:
        raise RuntimeError(
            f"{RUNTIME_PIPELINE_INPUT_ROOT_ENV} is required for immutable "
            "Runtime Prediction snapshots"
        )
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise RuntimeError(
            f"{RUNTIME_PIPELINE_INPUT_ROOT_ENV} must be an absolute path shared "
            "by Backend and Generator"
        )
    return root.resolve()


def active_simulation_session_id(stream_root: Path) -> str | None:
    """Resolve the newest running gen_data Source run without mixing sessions."""

    manifests = sorted(
        stream_root.glob("runs/*/run_manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        session_id = str(manifest.get("simulation_session_id") or "").strip()
        if session_id and manifest.get("status") == "running":
            return session_id
    return None


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    stream_root = Path(
        os.getenv("GEN_DATA_RUNTIME_OUTPUT_ROOT", str(DEFAULT_STREAM_ROOT))
    )
    poll_seconds = max(1.0, float(os.getenv("LIVE_PM_POLL_SECONDS", "5")))
    once = os.getenv("LIVE_PM_RUN_ONCE", "0").lower() in {"1", "true", "yes"}
    simulation_session_id = active_simulation_session_id(stream_root)
    service = build_live_predictive_maintenance_service(
        runtime_pipeline_input_root=runtime_pipeline_input_root(),
        simulation_session_id=simulation_session_id,
    )
    LOGGER.info("active gen_data simulation session: %s", simulation_session_id or "shared")

    while True:
        try:
            payload = service.ingest_once(stream_root=stream_root)
            LOGGER.info(
                "live predictive-maintenance ingest: %s",
                json.dumps(payload, default=str),
            )
        except Exception:
            LOGGER.exception("live predictive-maintenance ingest failed")
            if once:
                raise
        if once:
            break
        time.sleep(poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
