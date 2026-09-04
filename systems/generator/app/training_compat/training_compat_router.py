"""Legacy internal training endpoints and execution coordination."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import systems.generator.model.model_training as model_training

logger = logging.getLogger(__name__)

_training_lock = asyncio.Lock()
router = APIRouter(tags=["legacy-training-compat"])


def _validate_data_dir(data_dir: str | None) -> None:
    """Validate data directory: must exist, be a directory, and not be empty."""
    if not data_dir:
        return
    path = Path(data_dir)
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"지정한 data_dir가 존재하지 않습니다: {data_dir}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"지정한 data_dir가 디렉터리가 아닙니다: {data_dir}")
    if not any(path.iterdir()):
        raise HTTPException(status_code=400, detail=f"지정한 data_dir가 비어 있습니다: {data_dir}")


async def execute_training(*, data_dir: str | None, force_reanalyze: bool) -> dict:
    """Execute model training under process-wide concurrency lock."""
    _validate_data_dir(data_dir)
    if _training_lock.locked():
        raise HTTPException(status_code=409, detail="모델 학습이 이미 진행 중입니다.")
    async with _training_lock:
        try:
            import systems.generator.generator_main as gen_main_mod
            target_fn = getattr(gen_main_mod, "train_all", model_training.train_all)
            return await asyncio.to_thread(target_fn, data_dir=data_dir, force_reanalyze=force_reanalyze)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("[GeneratorDaemon] Training failed")
            raise HTTPException(status_code=500, detail="모델 학습에 실패했습니다.") from exc


async def run_initial_training() -> None:
    """Background startup training worker."""
    try:
        await execute_training(data_dir=None, force_reanalyze=False)
        logger.info("[GeneratorDaemon] Initial automatic training completed successfully.")
    except Exception:
        logger.exception("[GeneratorDaemon] Initial automatic training failed. Daemon remains available.")


class TrainRequest(BaseModel):
    data_dir: Optional[str] = None
    force_reanalyze: bool = False


@router.post("/internal/train")
async def train(req: TrainRequest) -> dict:
    """Initial training execution endpoint. Runs train_all under concurrency lock."""
    return await execute_training(data_dir=req.data_dir, force_reanalyze=req.force_reanalyze)


@router.post("/internal/retrain")
async def retrain(req: TrainRequest) -> dict:
    """Explicit re-training endpoint. Dispatches to train_all under concurrency lock."""
    return await execute_training(data_dir=req.data_dir, force_reanalyze=req.force_reanalyze)
