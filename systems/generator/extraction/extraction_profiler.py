"""Compatibility facade for legacy extraction_profiler imports.

.. deprecated::
    Use `systems.generator.app.preprocessing.preprocessing_profiler` instead.
"""

from __future__ import annotations

from systems.generator.app.preprocessing.preprocessing_profiler import (
    build_family_registry,
    load_family_registry,
    profile_source_file_with_llm,
    compute_family_id,
    infer_key_signature,
    FAMILY_REGISTRY_PATH,
)

__all__ = [
    "build_family_registry",
    "load_family_registry",
    "profile_source_file_with_llm",
    "compute_family_id",
    "infer_key_signature",
    "FAMILY_REGISTRY_PATH",
]
