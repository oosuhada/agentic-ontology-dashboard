"""Database location configuration kept separate from application runtime settings."""

from __future__ import annotations

import os
import warnings
from pathlib import Path

CANONICAL_DATABASE_ENV = "ONTOLOGY_DASHBOARD_DATABASE_URL"
CANONICAL_SQLITE_ENV = "ONTOLOGY_DASHBOARD_DB"
LEGACY_DATABASE_ENV = "FACTORY_SIGNAL_DB"


def database_location(root: Path) -> str:
    database_url = os.getenv(CANONICAL_DATABASE_ENV, "").strip()
    if database_url:
        return database_url

    sqlite_path = os.getenv(CANONICAL_SQLITE_ENV, "").strip()
    if sqlite_path:
        return sqlite_path

    legacy_path = os.getenv(LEGACY_DATABASE_ENV, "").strip()
    if legacy_path:
        warnings.warn(
            f"{LEGACY_DATABASE_ENV} is deprecated; use {CANONICAL_SQLITE_ENV} or "
            f"{CANONICAL_DATABASE_ENV} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return legacy_path

    canonical_path = root / "data" / "local" / "ontology_dashboard.db"
    legacy_default = root / "data" / "local" / "factory_signal_board.db"
    return str(legacy_default if legacy_default.exists() and not canonical_path.exists() else canonical_path)


def is_postgresql_url(value: str) -> bool:
    return value.startswith(("postgresql://", "postgresql+psycopg://"))
