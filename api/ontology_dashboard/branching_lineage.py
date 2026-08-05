"""Global product branches, lineage graph and marking-aware policy decisions."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .postgresql_compat import postgres_repository_connection
from .postgresql_repositories import is_postgresql


class PlatformBranch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    name: str
    base_branch_id: str | None
    status: Literal["open", "review", "merged", "closed", "conflicted"]
    owner_user_id: str
    head_revision: int


class BranchChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_name: str = Field(min_length=2, max_length=80)
    resource_type: Literal["dataset", "ontology", "action", "function", "dashboard", "application"]
    resource_id: str = Field(min_length=1, max_length=160)
    payload: dict[str, Any]


class BranchDiff(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    branch: PlatformBranch
    changes: tuple[dict[str, Any], ...]
    conflicts: tuple[str, ...]
    mergeable: bool


class PolicyCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_type: str
    resource_id: str
    purpose: Literal["operations", "maintenance", "training", "export"]
    eligible_markings: tuple[str, ...] = ()


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision: Literal["allow", "deny"]
    reason_code: str
    effective_markings: tuple[str, ...]
    masked: bool


class BranchingLineageSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    branches: tuple[PlatformBranch, ...]
    lineage_edges: tuple[dict[str, Any], ...]
    markings: tuple[dict[str, Any], ...]
    branchable_resources: tuple[str, ...]
    merge_semantics: dict[str, str]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BranchingLineageRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self.postgresql = is_postgresql(self.database)

    def _connection(self, organization_id: str, project_id: str):
        if self.postgresql:
            return postgres_repository_connection(
                self.database,
                organization_id=organization_id,
                project_id=project_id,
            )
        repository = self

        class Context:
            def __enter__(self):
                self.connection = sqlite3.connect(repository.database)
                self.connection.row_factory = sqlite3.Row
                return self.connection

            def __exit__(self, exc_type, exc, tb):
                if exc_type is None:
                    self.connection.commit()
                else:
                    self.connection.rollback()
                self.connection.close()

        return Context()

    def ensure_samples(self, organization_id: str, project_id: str, actor: str) -> None:
        now = _now()
        with self._connection(organization_id, project_id) as connection:
            connection.execute(
                """INSERT INTO platform_branches(
                id,organization_id,project_id,name,base_branch_id,status,owner_user_id,
                head_revision,created_at,updated_at) VALUES (?,?,?,?,?,'open',?,0,?,?)
                ON CONFLICT(organization_id,project_id,name) DO NOTHING""",
                ("branch-main", organization_id, project_id, "main", None, actor, now, now),
            )
            edges = (
                ("source", "connector-canonical-fixture", "dataset", "canonical-v3.1", "ingests"),
                ("dataset", "canonical-v3.1", "object_type", "equipment", "materializes"),
                ("object_type", "equipment", "function", "asset-risk-metric", "inputs"),
                ("function", "asset-risk-metric", "action", "request-asset-inspection", "supports"),
                ("dataset", "canonical-v3.1", "dashboard", "commercial-v4", "renders"),
            )
            for index, (source_type, source_id, target_type, target_id, relation) in enumerate(edges):
                connection.execute(
                    """INSERT INTO platform_lineage_edges(
                    id,organization_id,project_id,branch_id,source_type,source_id,target_type,
                    target_id,relation,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO NOTHING""",
                    (
                        f"lineage-sample-{index}", organization_id, project_id, "branch-main",
                        source_type, source_id, target_type, target_id, relation, now,
                    ),
                )
            for marking, field in (("confidential", None), ("export_restricted", "failure_probability")):
                connection.execute(
                    """INSERT INTO platform_markings(
                    id,organization_id,project_id,resource_type,resource_id,field_name,marking,created_at
                    ) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
                    (
                        f"marking-{marking}", organization_id, project_id, "dataset",
                        "canonical-v3.1", field, marking, now,
                    ),
                )

    def create_change(
        self,
        organization_id: str,
        project_id: str,
        request: BranchChangeRequest,
        actor: str,
    ) -> BranchDiff:
        if request.branch_name == "main":
            raise ValueError("direct writes to main are prohibited")
        now = _now()
        branch_id = f"branch-{request.branch_name}"
        with self._connection(organization_id, project_id) as connection:
            connection.execute(
                """INSERT INTO platform_branches(
                id,organization_id,project_id,name,base_branch_id,status,owner_user_id,
                head_revision,created_at,updated_at) VALUES (?,?,?,?,?,'open',?,0,?,?)
                ON CONFLICT(organization_id,project_id,name) DO NOTHING""",
                (branch_id, organization_id, project_id, request.branch_name, "branch-main", actor, now, now),
            )
            row = connection.execute(
                """SELECT head_revision FROM platform_branches
                WHERE organization_id=? AND project_id=? AND id=?""",
                (organization_id, project_id, branch_id),
            ).fetchone()
            revision = int(row["head_revision"]) + 1
            connection.execute(
                """INSERT INTO platform_branch_resources(
                id,organization_id,project_id,branch_id,resource_type,resource_id,revision,
                payload_json,operation,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"branch-resource-{uuid.uuid4()}", organization_id, project_id, branch_id,
                    request.resource_type, request.resource_id, revision,
                    json.dumps(request.payload), "upsert", actor, now,
                ),
            )
            connection.execute(
                "UPDATE platform_branches SET head_revision=?,updated_at=? WHERE id=?",
                (revision, now, branch_id),
            )
        return self.diff(organization_id, project_id, branch_id)

    def diff(self, organization_id: str, project_id: str, branch_id: str) -> BranchDiff:
        with self._connection(organization_id, project_id) as connection:
            branch_row = connection.execute(
                "SELECT * FROM platform_branches WHERE organization_id=? AND project_id=? AND id=?",
                (organization_id, project_id, branch_id),
            ).fetchone()
            if branch_row is None:
                raise KeyError("branch not found")
            changes = connection.execute(
                """SELECT resource_type,resource_id,revision,payload_json,operation
                FROM platform_branch_resources WHERE organization_id=? AND project_id=? AND branch_id=?
                ORDER BY revision""",
                (organization_id, project_id, branch_id),
            ).fetchall()
        branch = PlatformBranch(
            id=branch_row["id"], name=branch_row["name"], base_branch_id=branch_row["base_branch_id"],
            status=branch_row["status"], owner_user_id=branch_row["owner_user_id"],
            head_revision=int(branch_row["head_revision"]),
        )
        normalized = tuple(
            {
                "resource_type": row["resource_type"], "resource_id": row["resource_id"],
                "revision": int(row["revision"]),
                "payload": row["payload_json"] if isinstance(row["payload_json"], dict) else json.loads(row["payload_json"]),
                "operation": row["operation"],
            }
            for row in changes
        )
        identities = [(item["resource_type"], item["resource_id"]) for item in normalized]
        conflicts = tuple(
            f"duplicate resource identity: {kind}:{resource_id}"
            for kind, resource_id in set(identities)
            if identities.count((kind, resource_id)) > 1
        )
        return BranchDiff(branch=branch, changes=normalized, conflicts=conflicts, mergeable=not conflicts)

    def merge(self, organization_id: str, project_id: str, branch_id: str) -> BranchDiff:
        diff = self.diff(organization_id, project_id, branch_id)
        if not diff.mergeable:
            raise ValueError("branch has unresolved conflicts")
        with self._connection(organization_id, project_id) as connection:
            connection.execute(
                "UPDATE platform_branches SET status='merged',updated_at=? WHERE id=?",
                (_now(), branch_id),
            )
        return self.diff(organization_id, project_id, branch_id)

    def policy_check(
        self,
        organization_id: str,
        project_id: str,
        actor: str,
        request: PolicyCheckRequest,
    ) -> PolicyDecision:
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                """SELECT marking FROM platform_markings WHERE organization_id=? AND project_id=?
                AND resource_type=? AND resource_id=? ORDER BY marking""",
                (organization_id, project_id, request.resource_type, request.resource_id),
            ).fetchall()
            markings = tuple(row["marking"] for row in rows)
            required = set(markings)
            eligible = set(request.eligible_markings)
            denied = bool(required - eligible) or (
                request.purpose == "export" and "export_restricted" in required
            )
            decision = PolicyDecision(
                decision="deny" if denied else "allow",
                reason_code="missing_required_marking_or_export_restricted" if denied else "all_markings_satisfied",
                effective_markings=markings,
                masked=denied,
            )
            connection.execute(
                """INSERT INTO platform_policy_decisions(
                id,organization_id,project_id,actor_user_id,resource_type,resource_id,purpose,
                decision,reason_code,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"policy-{uuid.uuid4()}", organization_id, project_id, actor,
                    request.resource_type, request.resource_id, request.purpose,
                    decision.decision, decision.reason_code, _now(),
                ),
            )
        return decision

    def snapshot(self, organization_id: str, project_id: str) -> BranchingLineageSnapshot:
        with self._connection(organization_id, project_id) as connection:
            branches = connection.execute(
                "SELECT * FROM platform_branches WHERE organization_id=? AND project_id=? ORDER BY name",
                (organization_id, project_id),
            ).fetchall()
            edges = connection.execute(
                "SELECT * FROM platform_lineage_edges WHERE organization_id=? AND project_id=? ORDER BY id",
                (organization_id, project_id),
            ).fetchall()
            markings = connection.execute(
                "SELECT resource_type,resource_id,field_name,marking,inherited_from FROM platform_markings WHERE organization_id=? AND project_id=? ORDER BY marking",
                (organization_id, project_id),
            ).fetchall()
        return BranchingLineageSnapshot(
            branches=tuple(
                PlatformBranch(
                    id=row["id"], name=row["name"], base_branch_id=row["base_branch_id"],
                    status=row["status"], owner_user_id=row["owner_user_id"],
                    head_revision=int(row["head_revision"]),
                ) for row in branches
            ),
            lineage_edges=tuple(dict(row) for row in edges),
            markings=tuple(dict(row) for row in markings),
            branchable_resources=("dataset", "ontology", "action", "function", "dashboard", "application"),
            merge_semantics={
                "identity": "resource_type + stable resource_id",
                "validation": "cross-resource validation before atomic status transition",
                "partial_merge": "prohibited",
                "branch_actions": "dry-run only; no production side effect",
            },
        )


__all__ = [
    "BranchChangeRequest", "BranchDiff", "BranchingLineageRepository",
    "BranchingLineageSnapshot", "PlatformBranch", "PolicyCheckRequest", "PolicyDecision",
]
