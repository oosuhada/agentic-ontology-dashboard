"""Compatibility facade for legacy extraction_agent imports.

.. deprecated::
    Use `systems.generator.app.preprocessing.preprocessing_planner` instead.
"""

from __future__ import annotations

from systems.generator.app.preprocessing.preprocessing_planner import PreprocessingPlanner as ExtractionPlanner

_default_planner = ExtractionPlanner()


def classify_structure(filepath: str, df_preview) -> str:
    return _default_planner.classify_structure(filepath, df_preview)


def plan_extraction(filepath: str, structure_type: str, df_preview) -> dict:
    return _default_planner.plan_columns(filepath, structure_type, df_preview)


def enforce_key_columns(selected_columns: list[str], available_columns: list[str]) -> list[str]:
    return _default_planner.enforce_key_columns(selected_columns, available_columns)


def build_extraction_plan(filepath: str, force_reanalyze: bool = False) -> dict:
    return _default_planner.build_plan(filepath, force_reanalyze=force_reanalyze)


__all__ = [
    "classify_structure",
    "plan_extraction",
    "enforce_key_columns",
    "build_extraction_plan",
    "ExtractionPlanner",
]
