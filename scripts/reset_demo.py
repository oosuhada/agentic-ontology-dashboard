#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

TABLES = ("decisions", "notes", "conversations", "audit_log")


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_database(value: str | None) -> Path:
    configured = value or os.getenv("FACTORY_SIGNAL_DB") or "data/local/factory_signal_board.db"
    path = Path(configured).expanduser()
    return path if path.is_absolute() else project_root() / path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset local development records without exposing a public reset API"
    )
    parser.add_argument(
        "--database",
        help="SQLite database path. Defaults to FACTORY_SIGNAL_DB or data/local/factory_signal_board.db.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation.",
    )
    args = parser.parse_args()
    database = resolve_database(args.database)

    if not database.exists():
        print(json.dumps({"status": "not_found", "database": str(database)}, ensure_ascii=False, indent=2))
        return

    if not args.yes:
        confirmation = input(
            "로컬 판단·메모·대화·감사 기록을 삭제합니다. 설비 fixture와 분석 코드는 유지됩니다. 계속할까요? [y/N] "
        )
        if confirmation.strip().lower() not in {"y", "yes"}:
            print(json.dumps({"status": "cancelled", "database": str(database)}, ensure_ascii=False, indent=2))
            return

    deleted: dict[str, int] = {}
    with sqlite3.connect(database) as connection:
        existing = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in TABLES:
            if table not in existing:
                deleted[table] = 0
                continue
            count = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            connection.execute(f"DELETE FROM {table}")
            deleted[table] = count

    print(
        json.dumps(
            {
                "status": "reset",
                "database": str(database),
                "deleted": deleted,
                "scope": "local development records only",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
