from ontology_dashboard.automation_runtime import AutomationSimulationRequest, automation_snapshot, simulate_automation


def test_high_risk_event_requires_four_eyes_and_simulation_suppresses_side_effects() -> None:
    result = simulate_automation(AutomationSimulationRequest(event_id="event-1", failure_probability=0.91, criticality="high"))
    assert result["state"] == "awaiting_approval"
    assert result["four_eyes"] is True
    assert result["external_side_effects_executed"] is False
    assert result["actions"] == ["request-asset-inspection"]


def test_duplicate_event_is_deduplicated_and_replay_safe() -> None:
    result = simulate_automation(AutomationSimulationRequest(event_id="event-1", failure_probability=0.91, criticality="high", duplicate=True))
    assert result["state"] == "deduplicated"
    assert result["actions"] == []
    assert result["replay_safe"] is True
    snapshot = automation_snapshot()
    assert snapshot.definition["raw_code_allowed"] is False
    assert snapshot.approval["agent_draft_is_published"] is False
