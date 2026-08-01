"""Canonical ML namespace for the Manufacturing Predictive Maintenance domain pack."""

from __future__ import annotations

from pathlib import Path

_LEGACY_MODULE_PATH = Path(__file__).resolve().parent.parent / "factory_signal_ml"
if _LEGACY_MODULE_PATH.is_dir():
    __path__.append(str(_LEGACY_MODULE_PATH))

from .contracts import audit_fixture, derive_features, load_fixture
from .evidence import FixtureContextProvider, build_evidence_package
from .predictor import HeuristicPredictor, Prediction

__all__ = [
    "FixtureContextProvider",
    "HeuristicPredictor",
    "Prediction",
    "audit_fixture",
    "build_evidence_package",
    "derive_features",
    "load_fixture",
]
