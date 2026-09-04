# CNC and Compressor model quality baseline and roadmap

This document records the production-facing quality baseline for the Canonical
V3.1 CNC and compressor failure-within-24h models. It is a release/operations
record, not a claim of SOTA predictive performance.

## Acceptance interpretation

The project accepts a model for the product closed loop when it has real signal,
reproducible feature/runtime parity, an immutable artifact, and a deployment
threshold selected without touching the final time holdout. Model quality is
still an ongoing ML-lifecycle responsibility after acceptance.

For Canonical V3.1, random prevalence is about `0.0352` in the hourly temporal
evaluation table. The legacy reference regression sanity benchmark is:

- ROC-AUC: `0.734353`
- PR-AUC / average precision: `0.222111`
- Top 5% recall: `0.283333`

The first Mac mini Generator artifact used only current sensor values and had
average precision about `0.0196`, with precision/recall/F1 all zero at the
fixed 0.5 threshold. That artifact is retained as immutable failure evidence
but is not an acceptable quality baseline.

## Temporal calibration contract

The first seven running days per asset are calibration-only. Their statistics
may be embedded in the Model Artifact, but samples inside that seven-day window
must not enter train/validation/test. This is also the serving contract:
post-maintenance or new-asset inference starts only after an isolated history
segment satisfies the current Model Artifact runtime context. This removes the
look-ahead leakage identified during PR review.

## Compressor temporal baseline

Per-asset first-seven-day running baselines plus 1 h / 6 h temporal features
raised the selected RandomForest candidate to:

- regression sanity PR-AUC: `0.185693`
- regression sanity recall: `0.410417` at the v2 threshold
- deployment time-holdout PR-AUC: `0.509353`
- deployment recall: `0.958333`
- deployment precision: `0.056931`
- deployment F1: `0.107477`

This is acceptable for proving the real prediction → Model Artifact → Backend
inference → product closed loop, but the low precision produces too many alerts
for a mature operational model.

## v3 threshold-quality improvement

The ranking model remains RandomForest because the untouched time holdout has
the strongest ranking among the evaluated CPU-friendly candidates. Threshold
selection is changed to validation maximum F1 subject to validation recall >=
0.30. In the pre-release experiment this selects approximately `0.12` and gives
the untouched deployment holdout:

- PR-AUC: `0.509353` (ranking unchanged)
- precision: `0.135338`
- recall: `0.750000`
- F1: `0.229299`
- false positives: `115` instead of `381` in the same holdout

The threshold is selected from validation data only. The deployment holdout is
used for final release acceptance/regression reporting, not threshold tuning.

The v3 promotion gate additionally rejects a candidate that materially regresses
deployment alert quality. A 43-day leakage-free retraining run produced a new
candidate whose deployment precision was about `0.012`; it was retained as an
immutable diagnostic artifact but was not allowed to replace `current`. The Mac
mini therefore keeps `compressor-random-forest-v3-138e75c0f721` as the rollback
runtime artifact while the next leakage-free compressor candidate is improved.
That rollback is an explicit limitation, not evidence that the older artifact's
offline metrics should be treated as a new clean benchmark.

## CNC 43-day candidate comparison

Canonical V3.1 was extended through `2026-09-12 23:50 KST` and the CNC model was
retrained after removing the seven-day calibration leakage. Candidate selection
uses validation operating points subject to the minimum-recall constraint; the
untouched deployment holdout is not used for model or threshold selection.

The evaluated candidates are LogisticRegression, RandomForest, ExtraTrees,
LightGBM and XGBoost. XGBoost had the strongest leave-one-site-out AP among the
five in this run, but its validation-selected operating point produced only
`0.3448` deployment precision and failed the `0.50` CNC release floor. The final
selection therefore remains RandomForest:

- model: `cnc-random-forest-v3-f898a33ade7f`
- deployment PR-AUC: `0.696063`
- deployment ROC-AUC: `0.890311`
- deployment precision: `0.546067`
- deployment recall: `0.678771`
- deployment F1: `0.605230`
- selected threshold: `0.07`
- leave-one-site-out AP: `0.604111`

LightGBM and XGBoost are consequently supported and experimentally justified as
CPU candidates on the M1 host, but neither is promoted merely because its
ranking metric is higher. The release operating point and alert workload remain
part of the selection contract.

## Compressor candidate comparison

- LogisticRegression reproduces the legacy regression sanity PR-AUC almost
  exactly (`0.222111`) and is retained as an important regression reference.
  Its deployment time-holdout PR-AUC is lower (`0.335445`).
- HistGradientBoosting was evaluated as a CPU-friendly candidate. It reached
  regression sanity PR-AUC `0.203291` and deployment PR-AUC `0.472380`, but its
  validation-selected release threshold produced lower deployment F1 than the
  RandomForest v3 candidate, so it is not promoted.
- More complex GPU/LSTM/Transformer candidates are still not justified by the
  current Operations and 16 GiB M1 production target.

## Remaining improvement opportunities

1. Preserve a new lockbox time window before repeated model/threshold iteration;
   repeated decisions against the same final holdout eventually overfit the
   evaluation process even if training never sees its labels.
2. Add probability calibration and alert-budget/cost evaluation if product
   requirements define an acceptable false-positive workload.
3. Add drift monitoring by site/asset and retrain only when source distribution
   or alert quality materially changes.
4. Add calibrated new-asset baseline support instead of requiring every runtime
   asset to exist in the training artifact baseline map.
5. Replace the compressor rollback artifact with a leakage-free candidate only
   after it clears the strengthened promotion gate.
6. Add official local explanation support (for example a governed SHAP artifact)
   only if the product needs instance-level attribution beyond the current local
   proxy factor contract.

These items extend the existing ML lifecycle plan in
`docs/final_team_role_and_step_plan.md`: retraining, quality regression,
runtime feature parity, model limitation provenance, golden-vector tests, and
artifact reproducibility remain active responsibilities after first release.
