"""Durable knowledge index worker driven by DB-backed dirty state."""

from __future__ import annotations

import logging
import os
import sys
import time

from app.common.runtime_settings import project_root
from app.dependencies import get_knowledge_service
from app.infra.db.settings import database_location
from app.knowledge.repository import KnowledgeRepository


LOGGER = logging.getLogger("ontology-dashboard.knowledge-indexer")


def _scope():
    service = get_knowledge_service()
    project_id = os.getenv("ONTOLOGY_DASHBOARD_KNOWLEDGE_PROJECT_ID", "manufacturing-demo-project")
    workspace_id = os.getenv("ONTOLOGY_DASHBOARD_KNOWLEDGE_WORKSPACE_ID", "manufacturing-demo")
    organization_id = service.repository.resolve_organization(
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return service, organization_id, project_id, workspace_id


def healthcheck() -> int:
    project_id = os.getenv("ONTOLOGY_DASHBOARD_KNOWLEDGE_PROJECT_ID", "manufacturing-demo-project")
    workspace_id = os.getenv("ONTOLOGY_DASHBOARD_KNOWLEDGE_WORKSPACE_ID", "manufacturing-demo")
    repository = KnowledgeRepository(database_location(project_root()))
    organization_id = repository.resolve_organization(project_id=project_id, workspace_id=workspace_id)
    state = repository.index_state(
        organization_id=organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return 1 if state.get("status") == "failed" else 0


def run_forever() -> None:
    interval = max(1.0, float(os.getenv("ONTOLOGY_DASHBOARD_KNOWLEDGE_INDEX_POLL_SECONDS", "5")))
    service, organization_id, project_id, workspace_id = _scope()
    LOGGER.info("knowledge indexer started", extra={"project_id": project_id, "workspace_id": workspace_id})
    while True:
        state = service.repository.index_state(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if state.get("status") == "dirty":
            try:
                result = service.reindex(
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    actor_user_id="knowledge-indexer",
                    force=False,
                )
                LOGGER.info(
                    "knowledge index refreshed",
                    extra={
                        "project_id": project_id,
                        "workspace_id": workspace_id,
                        "chunk_count": result.get("chunk_count"),
                        "status": result.get("status"),
                    },
                )
            except Exception:
                LOGGER.exception("knowledge index refresh failed")
        time.sleep(interval)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    if "--healthcheck" in sys.argv:
        raise SystemExit(healthcheck())
    run_forever()


if __name__ == "__main__":
    main()
