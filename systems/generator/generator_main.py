"""Compatibility entrypoint for Generator Daemon application."""

from __future__ import annotations

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from systems.generator.generator_config import load_config
from systems.generator.model.model_registry import has_any_published_model_artifact
from systems.generator.model.model_training import train_all
from systems.generator.app.training_compat.training_compat_router import (
    TrainRequest,
    _training_lock,
    execute_training,
    run_initial_training,
)
from systems.generator.app.training_compat.training_lifecycle import lifespan
from systems.generator.app.main import app, create_app

_execute_training = execute_training
_run_initial_training = run_initial_training

__all__ = [
    "app",
    "create_app",
    "TrainRequest",
    "_training_lock",
    "execute_training",
    "_execute_training",
    "run_initial_training",
    "_run_initial_training",
    "lifespan",
    "train_all",
    "load_config",
    "has_any_published_model_artifact",
]
