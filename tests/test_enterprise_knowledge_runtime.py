from __future__ import annotations

import sqlite3
from pathlib import Path

from app.common.company_context import company_documents, load_company_context
from app.infra.db.migrations import migrate
from app.knowledge.embedding import HashingEmbeddingProvider
from app.knowledge.repository import KnowledgeRepository, _timestamp
from app.knowledge.service import KnowledgeService, chunk_text


ORG = "org-ontology-demo"
PROJECT = "manufacturing-demo-project"
WORKSPACE = "manufacturing-demo"


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "knowledge.db"
    migrate(str(path))
    now = "2026-09-05T00:00:00+00:00"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO organizations(id,slug,name,created_at) VALUES (?,?,?,?)",
            (ORG, "ontology-demo", "Ontology Demo", now),
        )
        connection.execute(
            "INSERT INTO workspaces(id,organization_id,slug,display_name,domain_pack,created_at) VALUES (?,?,?,?,?,?)",
            (WORKSPACE, ORG, WORKSPACE, "Manufacturing", "predictive-maintenance", now),
        )
        connection.execute(
            """
            INSERT INTO projects(id,organization_id,slug,display_name,description,domain_pack_code,status,default_workspace_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (PROJECT, ORG, PROJECT, "Manufacturing Demo", "", "predictive-maintenance", "active", WORKSPACE, now, now),
        )
    return path


def test_enterprise_history_expands_real_work_question_domains():
    context = load_company_context()

    assert len(context["production_orders"]) >= 400
    assert len(context["quality_incidents"]) >= 140
    assert len(context["purchase_orders"]) >= 200
    assert any(
        item["source_ref"] == "erp-po:MRO-202608-CORE-001"
        and "CNC-S04-L02-03" in item["related_asset_ids"]
        for item in context["purchase_orders"]
    )
    assert len(context["capa_records"]) >= 70
    assert len(context["shift_handoffs"]) >= 300
    assert len(context["calibration_records"]) >= 170
    assert len(context["safety_events"]) >= 30
    assert len(company_documents(context)) >= 2800


def test_hashing_embedding_and_chunking_are_deterministic():
    provider = HashingEmbeddingProvider()
    first = provider.embed("CNC spindle bearing vibration inspection history")
    second = provider.embed("CNC spindle bearing vibration inspection history")

    assert first == second
    assert len(first) == 1536
    assert abs(sum(value * value for value in first) - 1.0) < 1e-6
    assert len(chunk_text("A" * 2200, max_chars=900, overlap_chars=100)) >= 3


def test_knowledge_source_periods_normalize_to_postgresql_timestamps():
    assert _timestamp("2026") == "2026-01-01T00:00:00+00:00"
    assert _timestamp("2026-09") == "2026-09-01T00:00:00+00:00"
    assert _timestamp("2026-H1") == "2026-01-01T00:00:00+00:00"
    assert _timestamp("2026-H2") == "2026-07-01T00:00:00+00:00"
    assert _timestamp("2026-19") is None
    assert _timestamp("not-a-date") is None


def test_knowledge_ingestion_versions_and_marks_index_dirty(tmp_path: Path):
    service = KnowledgeService(KnowledgeRepository(_database(tmp_path)), HashingEmbeddingProvider())
    values = dict(
        organization_id=ORG,
        project_id=PROJECT,
        workspace_id=WORKSPACE,
        actor_user_id="user-1",
        title="Spindle inspection report",
        document_type="maintenance_report",
        source_ref="inspection:spindle:001",
        source_updated_at="2026-09-01T10:00:00+09:00",
        allowed_roles=[],
        metadata={"related_asset_ids": ["CNC-S04-L02-03"]},
    )
    created = service.ingest(content="bearing vibration increased during high load", **values)
    unchanged = service.ingest(content="bearing vibration increased during high load", **values)
    updated = service.ingest(content="bearing vibration increased; alignment inspection completed", **values)

    assert created["changed"] is True
    assert unchanged["changed"] is False
    assert updated["changed"] is True
    stats = service.stats(organization_id=ORG, project_id=PROJECT, workspace_id=WORKSPACE)
    assert stats["document_count"] == 1
    assert stats["version_count"] == 2
    assert stats["index"]["status"] == "dirty"


def test_hybrid_index_search_and_document_role_filter(tmp_path: Path):
    path = _database(tmp_path)
    service = KnowledgeService(KnowledgeRepository(path), HashingEmbeddingProvider())
    common = dict(organization_id=ORG, project_id=PROJECT, workspace_id=WORKSPACE, actor_user_id="user-1")
    service.ingest(
        **common,
        title="Spindle bearing maintenance history",
        document_type="maintenance_report",
        content="CNC-S04-L02-03 spindle bearing vibration increased. Alignment and lubrication were inspected.",
        source_ref="maintenance:test:001",
        metadata={"related_asset_ids": ["CNC-S04-L02-03"]},
    )
    service.ingest(
        **common,
        title="Spindle bearing inbound purchase order",
        document_type="purchase_order",
        content="Spindle bearing replacement part ETA is 2026-09-12 and inbound quantity is three units.",
        source_ref="erp-po:test:001",
        metadata={"related_asset_ids": ["CNC-S04-L02-03"]},
    )
    service.ingest(
        **common,
        title="August operating profit",
        document_type="financial_actual",
        content="August operating profit and maintenance OPEX were reviewed for executive reporting.",
        source_ref="finance:test:2026-08",
        allowed_roles=["executive_viewer"],
    )
    state = service.reindex(**common)

    assert state["status"] == "ready"
    assert state["chunk_count"] == 3
    assert state["requested_generation"] == state["indexed_generation"]
    engineer = service.search(
        "CNC-S04-L02-03 bearing vibration maintenance",
        organization_id=ORG,
        project_id=PROJECT,
        workspace_id=WORKSPACE,
        roles=["process_engineer"],
        asset_id="CNC-S04-L02-03",
        top_k=4,
        actor_user_id="engineer",
    )
    executive = service.search(
        "operating profit maintenance OPEX",
        organization_id=ORG,
        project_id=PROJECT,
        workspace_id=WORKSPACE,
        roles=["executive_viewer"],
        top_k=4,
        actor_user_id="executive",
    )

    assert any(item["source_ref"] == "maintenance:test:001" for item in engineer)
    assert any(item["source_ref"] == "erp-po:test:001" for item in engineer)
    assert all(item["source_ref"] != "finance:test:2026-08" for item in engineer)
    assert any(item["source_ref"] == "finance:test:2026-08" for item in executive)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM vector_document_chunks").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM knowledge_retrieval_audit").fetchone()[0] == 2

    # A later ingestion is durable work for the index worker, not an in-memory
    # callback. Generation counters prove the active index is now stale.
    service.ingest(
        **common,
        title="Follow-up bearing inspection",
        document_type="maintenance_report",
        content="Follow-up inspection found stable vibration after alignment.",
        source_ref="maintenance:test:002",
        metadata={"related_asset_ids": ["CNC-S04-L02-03"]},
    )
    dirty = service.stats(organization_id=ORG, project_id=PROJECT, workspace_id=WORKSPACE)["index"]
    assert dirty["status"] == "dirty"
    assert dirty["requested_generation"] > dirty["indexed_generation"]
    refreshed = service.reindex(**common, force=False)
    assert refreshed["status"] == "ready"
    assert refreshed["requested_generation"] == refreshed["indexed_generation"]
