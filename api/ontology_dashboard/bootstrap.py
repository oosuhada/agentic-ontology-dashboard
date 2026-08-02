"""Idempotent local/production-like persistence bootstrap command."""

from __future__ import annotations

import json

from .dependencies import database_target, get_identity_service, get_project_service
from .migrations import migrate
from .polyglot import PolyglotHealthService, PolyglotSettings


def bootstrap() -> dict[str, object]:
    target = database_target()
    applied = migrate(target)
    # Repository constructors perform idempotent reference-data seeding when
    # ONTOLOGY_DASHBOARD_SEED_REFERENCE_DATA is enabled.
    identity = get_identity_service()
    projects = get_project_service()
    project_count = len(
        projects.repository.list_projects(
            organization_id="org-ontology-demo",
        )
    )
    return {
        "database": "postgresql" if target.startswith("postgresql") else "sqlite",
        "applied_migrations": applied,
        "reference_users": len(identity.repository.list_users()),
        "reference_projects": project_count,
        "polyglot": PolyglotHealthService(PolyglotSettings.from_environment()).snapshot(),
    }


def main() -> int:
    print(json.dumps(bootstrap(), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
