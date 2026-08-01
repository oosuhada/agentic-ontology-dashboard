# Stage 3 Reproducible Model Baseline Results

## Run identity

- Dataset: UCI AI4I 2020
- SHA-256: `59db4f1d9c34c58136d89e5a006ec190dcea19e9dbea74f6b3b0c6f22a44d183`
- Rows: 10,000
- Failure rows: 339
- Failure rate: 3.39%
- Missing cells: 0
- Duplicate rows: 0
- Random seed: 42
- Split: train 60%, validation 20%, held-out test 20%
- Failure-mode leakage columns in model input: 0

## Validation comparison at threshold 0.5

| Model | Average Precision | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| Dummy prior | 0.0340 | 0.0000 | 0.0000 | 0.0000 |
| Balanced Logistic Regression | 0.4346 | 0.1538 | 0.8235 | 0.2593 |
| Balanced Random Forest | **0.8529** | **0.9231** | 0.7059 | **0.8000** |

Random Forest was selected using validation Average Precision. The test split did not participate in model or threshold selection.

## Threshold selection

- Minimum validation Recall target: 0.80
- Recall-constrained threshold: 0.20
- Illustrative cost-minimizing threshold: 0.19
- False-negative cost assumption: 10
- False-positive cost assumption: 1

The default 0.5 threshold was not used for the final test. The selected 0.20 threshold makes the operational preference for avoiding missed failures explicit.

## Held-out test at threshold 0.20

| Metric | Result |
|---|---:|
| Average Precision | 0.8739 |
| Precision | 0.6591 |
| Recall | 0.8529 |
| F1 | 0.7436 |
| True negatives | 1,902 |
| False positives | 30 |
| False negatives | 10 |
| True positives | 58 |

The trained artifact was generated in a temporary validation directory during implementation. Reproducible generation is available through:

```bash
PYTHONPATH=ml/src python -m ontology_dashboard_manufacturing_ml.cli train data/raw/ai4i2020.csv --output ml/artifacts
```

Generated binary artifacts are intentionally ignored by Git. Model metadata and policy are reproducible from code and the verified dataset checksum.

## Interpretation

- The selected model is meaningfully better than the class-prior Dummy model.
- Accuracy is intentionally not used as the primary selection metric because only 3.39% of rows are failures.
- The lower threshold improves Recall at the cost of 30 false positives on 2,000 held-out rows.
- These results validate the benchmark pipeline, not production readiness.

## Limitations

- AI4I is synthetic.
- Rows are treated as independent rather than equipment-level time series.
- Operational costs are assumptions, not customer measurements.
- Gold product scenarios use a deterministic fallback predictor so the demo can run without a binary artifact; that predictor is not presented as the benchmark model.
