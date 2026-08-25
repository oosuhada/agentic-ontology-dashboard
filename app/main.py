"""FastAPI entrypoint for the gen_data Source Data Producer."""

from __future__ import annotations

from contextlib import asynccontextmanager
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
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
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
