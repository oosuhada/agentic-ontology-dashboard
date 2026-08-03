from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.backup_database import checksum, sqlite_backup
from scripts.restore_database import restore_sqlite, verify_manifest


def test_sqlite_backup_restore_round_trip_and_manifest_verification(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE records(id INTEGER PRIMARY KEY,value TEXT NOT NULL)")
        connection.execute("INSERT INTO records(value) VALUES ('original')")

    backup = tmp_path / "backup.db"
    sqlite_backup(database, backup)
    manifest = {
        "artifact": str(backup),
        "backend": "sqlite",
        "sha256": checksum(backup),
        "size_bytes": backup.stat().st_size,
    }
    backup.with_suffix(".db.manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    assert verify_manifest(backup)["sha256"] == manifest["sha256"]

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE records SET value='corrupted'")
    restore_sqlite(backup, database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM records").fetchone()[0] == "original"


def test_backup_manifest_detects_tampering(tmp_path: Path) -> None:
    backup = tmp_path / "backup.db"
    with sqlite3.connect(backup) as connection:
        connection.execute("CREATE TABLE records(id INTEGER)")
    backup.with_suffix(".db.manifest.json").write_text(
        json.dumps({"backend": "sqlite", "sha256": "0" * 64}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="checksum"):
        verify_manifest(backup)
