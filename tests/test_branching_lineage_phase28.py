from pathlib import Path

import pytest

from ontology_dashboard.branching_lineage import (
    BranchChangeRequest,
    BranchingLineageRepository,
    PolicyCheckRequest,
)
from ontology_dashboard.migrations import migrate


ORG = "org-ontology-demo"
PROJECT = "manufacturing-demo-project"
ACTOR = "user-manager"


def repo(tmp_path: Path) -> BranchingLineageRepository:
    database = tmp_path / "phase28.db"
    migrate(str(database))
    result = BranchingLineageRepository(database)
    result.ensure_samples(ORG, PROJECT, ACTOR)
    return result


def test_branch_overlay_diff_and_atomic_merge(tmp_path: Path) -> None:
    repository = repo(tmp_path)
    diff = repository.create_change(
        ORG,
        PROJECT,
        BranchChangeRequest(
            branch_name="risk-policy-review",
            resource_type="function",
            resource_id="asset-risk-metric",
            payload={"timeout_ms": 200, "status": "draft"},
        ),
        ACTOR,
    )
    assert diff.branch.base_branch_id == "branch-main"
    assert diff.branch.head_revision == 1
    assert diff.mergeable is True
    merged = repository.merge(ORG, PROJECT, diff.branch.id)
    assert merged.branch.status == "merged"


def test_direct_main_write_is_prohibited(tmp_path: Path) -> None:
    repository = repo(tmp_path)
    with pytest.raises(ValueError, match="direct writes to main"):
        repository.create_change(
            ORG,
            PROJECT,
            BranchChangeRequest(
                branch_name="main",
                resource_type="dashboard",
                resource_id="commercial-v4",
                payload={"title": "unsafe"},
            ),
            ACTOR,
        )


def test_lineage_covers_source_dataset_object_function_action_and_dashboard(tmp_path: Path) -> None:
    snapshot = repo(tmp_path).snapshot(ORG, PROJECT)
    relations = {(edge["source_type"], edge["target_type"]) for edge in snapshot.lineage_edges}
    assert {("source", "dataset"), ("dataset", "object_type"), ("object_type", "function"), ("function", "action"), ("dataset", "dashboard")} <= relations


def test_marking_policy_requires_all_markings_and_denies_export(tmp_path: Path) -> None:
    repository = repo(tmp_path)
    denied = repository.policy_check(
        ORG,
        PROJECT,
        ACTOR,
        PolicyCheckRequest(
            resource_type="dataset",
            resource_id="canonical-v3.1",
            purpose="operations",
            eligible_markings=("confidential",),
        ),
    )
    assert denied.decision == "deny"
    assert denied.masked is True
    allowed = repository.policy_check(
        ORG,
        PROJECT,
        ACTOR,
        PolicyCheckRequest(
            resource_type="dataset",
            resource_id="canonical-v3.1",
            purpose="maintenance",
            eligible_markings=("confidential", "export_restricted"),
        ),
    )
    assert allowed.decision == "allow"
    export = repository.policy_check(
        ORG,
        PROJECT,
        ACTOR,
        PolicyCheckRequest(
            resource_type="dataset",
            resource_id="canonical-v3.1",
            purpose="export",
            eligible_markings=("confidential", "export_restricted"),
        ),
    )
    assert export.decision == "deny"

