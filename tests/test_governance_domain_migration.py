from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.governance import GovernanceService
from app.governance.artifact_policy import RetentionPolicyInput, evaluate_retention
from app.governance.ports import ModelReleaseCandidateQueryPort


ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE = ROOT / "systems" / "backend" / "app" / "governance"
LEGACY = ROOT / "systems" / "backend" / "ontology_dashboard"


def test_governance_sources_are_physically_canonical_and_agent_surface_is_removed() -> None:
    for relative in (
        "governance/__init__.py",
        "governance/models.py",
        "governance/service.py",
        "routers/governance.py",
    ):
        assert not (LEGACY / relative).exists(), relative
    assert not hasattr(GovernanceService, "agent_run")


def test_governance_domain_has_no_legacy_or_infra_implementation_imports() -> None:
    violations: list[str] = []
    for path in GOVERNANCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            for name in names:
                if name == "ontology_dashboard" or name.startswith("app.runtime."):
                    violations.append(f"{path.name}: {name}")
                if name.startswith("app.infra"):
                    violations.append(f"{path.name}: {name}")
    assert violations == []


def test_artifact_retention_policy_is_governance_owned() -> None:
    now = datetime.now(timezone.utc)
    legal_hold = evaluate_retention(
        RetentionPolicyInput(retention_class="legal_hold", legal_hold=True),
        now=now,
    )
    expired = evaluate_retention(
        RetentionPolicyInput(
            retention_class="standard",
            retain_until=now - timedelta(seconds=1),
        ),
        now=now,
    )
    assert legal_hold.action == "skip_legal_hold"
    assert expired.action == "delete"
    assert ModelReleaseCandidateQueryPort
