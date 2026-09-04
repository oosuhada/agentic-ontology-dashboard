"""Compatibility facade for legacy extraction_cache imports.

.. deprecated::
    Use `systems.generator.app.preprocessing.preprocessing_repository` or `preprocessing_planner` instead.
"""

from __future__ import annotations

from systems.generator.app.preprocessing.preprocessing_planner import PreprocessingPlanner as ExtractionPlanner
from systems.generator.app.preprocessing.preprocessing_repository import PreprocessingRepository as ExtractionRepository

_default_planner = ExtractionPlanner()
_default_repo = ExtractionRepository()


def compute_fingerprint(df_preview) -> str:
    return _default_planner.compute_fingerprint(df_preview)


def load_plan_cache() -> dict:
    return {}


def save_plan_cache(cache: dict) -> None:
    pass


__all__ = [
    "compute_fingerprint",
    "load_plan_cache",
    "save_plan_cache",
]
