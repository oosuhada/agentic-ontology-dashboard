from ontology_dashboard.mlops_runtime import DriftEvaluationRequest, evaluate_drift, mlops_snapshot


def test_drift_requires_minimum_sample_and_never_auto_promotes() -> None:
    insufficient = evaluate_drift(DriftEvaluationRequest(metric="psi", value=0.9, threshold=0.2, sample_size=20))
    assert insufficient["state"] == "insufficient_sample"
    assert insufficient["automatic_promotion"] is False
    breached = evaluate_drift(DriftEvaluationRequest(metric="psi", value=0.3, threshold=0.2, sample_size=900))
    assert breached["state"] == "breached"
    assert breached["retraining_action"] == "queue_review"


def test_shadow_cannot_trigger_actions_and_online_staleness_fails_closed() -> None:
    snapshot = mlops_snapshot()
    assert snapshot.deployment["mode"] == "shadow"
    assert snapshot.deployment["shadow_can_trigger_actions"] is False
    assert snapshot.feature_view["freshness"] == "stale online values fail closed"
    assert snapshot.rollback["unit"] == "model + feature + policy + artifact"
