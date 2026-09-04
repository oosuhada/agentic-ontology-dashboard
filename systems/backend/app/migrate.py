"""Canonical database migration command used by hosted startup."""

from __future__ import annotations

from app.common.runtime_settings import project_root
from app.infra.db.migrations import migrate
from app.infra.db.settings import database_location


def main() -> int:
    target = database_location(project_root())
    applied = migrate(target)
    print({"applied": applied, "count": len(applied)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
