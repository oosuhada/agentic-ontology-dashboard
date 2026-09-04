"""Application lifecycle management for Generator daemon and training workers."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

import systems.generator.generator_config as gen_cfg
import systems.generator.model.model_registry as model_reg
import systems.generator.app.training_compat.training_compat_router as compat_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan managing configuration loading, non-blocking startup, and graceful shutdown worker completion."""
    import systems.generator.generator_main as gen_main_mod

    load_cfg_fn = getattr(gen_main_mod, "load_config", gen_cfg.load_config)
    has_art_fn = getattr(gen_main_mod, "has_any_published_model_artifact", model_reg.has_any_published_model_artifact)
    run_init_fn = getattr(gen_main_mod, "_run_initial_training", compat_router.run_initial_training)

    load_cfg_fn()
    app.state.initial_training_task = None

    if not has_art_fn():
        logger.info("[GeneratorDaemon] No published model artifacts found. Scheduling initial automatic training...")
        app.state.initial_training_task = asyncio.create_task(run_init_fn())
    else:
        logger.info("[GeneratorDaemon] Existing published model artifacts detected. Skipping auto-training.")

    yield

    task = getattr(app.state, "initial_training_task", None)
    if task is not None and not task.done():
        logger.info("[GeneratorDaemon] Waiting for active initial training to finish before graceful shutdown.")
        await task
