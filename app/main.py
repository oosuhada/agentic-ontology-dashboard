"""FastAPI entrypoint for the gen_data Source Data Producer."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI

import config
from app.api.routes import router
from app.runtime.manager import RuntimeManager


ROOT = Path(__file__).resolve().parents[1]


def create_app(manager: RuntimeManager | None = None) -> FastAPI:
    runtime_manager = manager or RuntimeManager(
        output_root=Path(config.GEN_DATA_OUTPUT_DIR),
        mapping_path=ROOT / "mappings" / "opcua_nodes.v1.json",
        opcua_endpoint=config.GEN_DATA_OPCUA_ENDPOINT,
        maintenance_event_file=config.GEN_DATA_RUNTIME_OVERLAY_EVENT_FILE,
        runtime_overlay_fast_forward_rows=(
            config.GEN_DATA_RUNTIME_OVERLAY_FAST_FORWARD_ROWS
        ),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if config.GEN_DATA_AUTOSTART_CONTINUOUS:
            now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            interval_minutes = 10
            aligned_now = now - timedelta(minutes=now.minute % interval_minutes)
            session_id = f"continuous-reliability-{aligned_now.strftime('%Y%m%dT%H%MZ')}"
            runtime_manager.start_run(
                run_id=session_id,
                simulation_session_id=session_id,
                seed=42,
                start_at=aligned_now - timedelta(
                    hours=config.GEN_DATA_AUTOSTART_BACKFILL_HOURS
                ),
                duration_hours=config.GEN_DATA_AUTOSTART_DURATION_HOURS,
                interval_minutes=interval_minutes,
                product_cycle_minutes=20,
                rate_profile="balanced_demo",
                scenario_profile="continuous_reliability",
                speed=config.GEN_DATA_AUTOSTART_SPEED,
                continuous=True,
                publish_opcua=False,
                source_kind="simulation",
                runtime_overlay_fast_forward_rows=(
                    config.GEN_DATA_RUNTIME_OVERLAY_FAST_FORWARD_ROWS
                ),
            )
            runtime_manager.fast_forward_simulation(
                session_id,
                target_elapsed_hours=config.GEN_DATA_AUTOSTART_BACKFILL_HOURS,
            )
        yield
        runtime_manager.shutdown()

    app = FastAPI(
        title="gen_data Source Data Producer",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.runtime_manager = runtime_manager
    app.include_router(router)
    return app


app = create_app()
