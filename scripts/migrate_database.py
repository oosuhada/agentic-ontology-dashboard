#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from app.infra.db.migrations import migrate, migration_status
from app.infra.db.settings import database_location

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Ontology Dashboard database migrations")
    parser.add_argument("--database", default=database_location(ROOT))
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.status:
        print(migration_status(args.database))
        return

    applied = migrate(args.database)
    print({"database": args.database, "applied": applied, "count": len(applied)})


if __name__ == "__main__":
    main()
