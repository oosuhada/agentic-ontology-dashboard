from __future__ import annotations

from collections import Counter

import pytest

from evaluation.agent_workflow_benchmark import _percentile
from evaluation.agent_workflow_task_set import AGENT_WORKFLOW_TASKS


def test_agent_workflow_task_set_is_balanced_120_task_matrix() -> None:
    counts = Counter(task.difficulty for task in AGENT_WORKFLOW_TASKS)

    assert len(AGENT_WORKFLOW_TASKS) == 120
    assert counts == {"easy": 40, "medium": 40, "adversarial": 40}
    assert len({task.case_id for task in AGENT_WORKFLOW_TASKS}) == 120
    assert {task.audience for task in AGENT_WORKFLOW_TASKS} == {
        "engineering",
        "operations",
        "executive",
        "maintenance",
    }


def test_agent_workflow_adversarial_set_contains_failure_injection() -> None:
    adversarial = [task for task in AGENT_WORKFLOW_TASKS if task.difficulty == "adversarial"]

    assert any(task.injected_failure == "transient_once" for task in adversarial)
    assert any(task.injected_failure == "timeout_exhausted" for task in adversarial)


def test_agent_workflow_percentile_interpolation_is_deterministic() -> None:
    assert _percentile([1.0, 2.0, 3.0, 4.0, 100.0], 0.50) == 3.0
    assert _percentile([1.0, 2.0, 3.0, 4.0, 100.0], 0.95) == pytest.approx(80.8)
