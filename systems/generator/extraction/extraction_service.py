"""Compatibility facade for legacy extraction_service imports.

.. deprecated::
    Use `systems.generator.app.preprocessing.preprocessing_service` instead.
"""

from __future__ import annotations

from systems.generator.app.preprocessing.preprocessing_service import (
    preprocess_with_plan as extract_with_plan,
    load_all_sources,
    get_last_plans,
    SUPPORTED_EXTENSIONS,
)

__all__ = [
    "extract_with_plan",
    "load_all_sources",
    "get_last_plans",
    "SUPPORTED_EXTENSIONS",
]
