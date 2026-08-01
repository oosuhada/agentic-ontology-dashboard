"""Canonical Ontology Dashboard API namespace.

Implementation modules are being migrated from the historical
``factory_signal_board`` namespace. During the compatibility window this
package also searches the legacy module directory, so new code can import
``ontology_dashboard.identity`` and related modules without duplicating
runtime state or breaking existing integrations.
"""

from __future__ import annotations

from pathlib import Path

_LEGACY_MODULE_PATH = Path(__file__).resolve().parent.parent / "factory_signal_board"
if _LEGACY_MODULE_PATH.is_dir():
    __path__.append(str(_LEGACY_MODULE_PATH))

__all__: list[str] = []
