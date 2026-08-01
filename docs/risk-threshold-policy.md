# Stage 4 Threshold and Operational Risk Policy

## Two policy profiles

The project deliberately separates the benchmark model policy from the offline Gold-demo policy.

### Trained benchmark profile

- File: `ml/config/trained_model_policy.json`
- Compatible model: `ai4i-random_forest-v1`
- Recall-constrained decision threshold: 0.20
- Cost-minimizing threshold under illustrative 10:1 costs: 0.19
- Purpose: reproducible AI4I model evaluation and optional artifact-backed inference

### Deterministic Gold fallback profile

- File: `ml/config/threshold_policy.json`
- Compatible predictor: `fixture-heuristic-v1`
- Attention: 0.25
- Warning: 0.55
- Critical: 0.85
- Purpose: offline product demonstration, regression tests, and external-provider fallback

Thresholds from one profile must never be applied to the other model version.

## Severity semantics

| State | Meaning | Default decision |
|---|---|---|
| `normal` | no immediate operational action indicated | `continue_monitoring` |
| `attention` | borderline or low-confidence evidence | `request_inspection` while monitoring |
| `warning` | actionable evidence above policy threshold | `request_inspection` |
| `critical` | high-risk evidence requiring prompt human review | `review_shutdown` |
| `data_quality_hold` | inference is unavailable or unreliable | `hold_for_data_check` |

## Equipment criticality

High-criticality equipment can enter `attention` or `warning` slightly earlier, but equipment criticality does not lower the `critical` boundary. This prevents a business metadata field from silently converting a warning into a shutdown-review recommendation.

## Safety rules

- No state executes a stop command.
- `review_shutdown` is a recommendation for authorized human review.
- A probability does not confirm a root cause.
- Data-quality failure suppresses failure inference.
- Low-confidence results display uncertainty and additional verification needs.
- Threshold policy version and model version are included in every Evidence Package.

## Gold calibration

The deterministic profile is regression-calibrated to the eight accepted fixtures:

| Scenario | Expected state |
|---|---|
| GS-001 | normal |
| GS-002 | warning |
| GS-003 | warning |
| GS-004 | critical |
| GS-005 | warning |
| GS-006 | attention |
| GS-007 | data_quality_hold |
| GS-008 | warning |

This calibration is a product test contract and is not reported as statistical model performance.
