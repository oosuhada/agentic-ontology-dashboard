# AI4I 2020 Data Dictionary

## Dataset identity

- Name: AI4I 2020 Predictive Maintenance Dataset
- Publisher: UCI Machine Learning Repository
- Dataset identifier: 601
- DOI: `10.24432/C5HS5C`
- License: Creative Commons Attribution 4.0 International (`CC BY 4.0`)
- Attribution: `AI4I 2020 Predictive Maintenance Dataset [Dataset]. (2020). UCI Machine Learning Repository.`
- Direct CSV endpoint: `https://archive.ics.uci.edu/ml/machine-learning-databases/00601/ai4i2020.csv`
- Archive endpoint: `https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip`
- Rows: 10,000 observations
- Reference CSV SHA-256: `59db4f1d9c34c58136d89e5a006ec190dcea19e9dbea74f6b3b0c6f22a44d183`
- Intended use in this MVP: public benchmark for reproducible binary machine-failure prediction and post-hoc failure-mode analysis

The original dataset is not committed. `scripts/fetch_ai4i.py` downloads and verifies it, while `data/fixtures/` contains small deterministic product scenarios.

## Column classification

| Original column | Canonical field | Type | Unit | Role | Model input |
|---|---|---:|---|---|---|
| `UDI` | `udi` | integer | — | source row identifier | no |
| `Product ID` | `product_id` | string | — | source product identifier | no |
| `Type` | `product_type` | category `L/M/H` | — | product-quality class | yes, encoded |
| `Air temperature [K]` | `air_temperature_k` | float | K | sensor | yes |
| `Process temperature [K]` | `process_temperature_k` | float | K | sensor | yes |
| `Rotational speed [rpm]` | `rotational_speed_rpm` | integer | rpm | sensor | yes |
| `Torque [Nm]` | `torque_nm` | float | N·m | sensor | yes |
| `Tool wear [min]` | `tool_wear_min` | integer | min | accumulated operating condition | yes |
| `Machine failure` | `machine_failure` | binary | — | training target | no |
| `TWF` | `tool_wear_failure` | binary | — | post-hoc failure-mode label | **never** |
| `HDF` | `heat_dissipation_failure` | binary | — | post-hoc failure-mode label | **never** |
| `PWF` | `power_failure` | binary | — | post-hoc failure-mode label | **never** |
| `OSF` | `overstrain_failure` | binary | — | post-hoc failure-mode label | **never** |
| `RNF` | `random_failure` | binary | — | post-hoc failure-mode label | **never** |

## Leakage policy

`Machine failure` is the prediction target. `TWF`, `HDF`, `PWF`, `OSF`, and `RNF` encode the generating failure mechanisms and therefore must not enter preprocessing, feature engineering, model training, threshold selection, or inference. They may only be used after prediction for slice evaluation and fixture labeling.

The validation command fails when any target or failure-mode column appears in the model feature list.

## Derived features

| Canonical field | Formula | Unit | Interpretation |
|---|---|---|---|
| `temperature_difference_k` | `process_temperature_k - air_temperature_k` | K | process-to-air thermal gap |
| `mechanical_power_w` | `torque_nm × rotational_speed_rpm × 2π / 60` | W | approximate shaft mechanical power |
| `overstrain_index` | `torque_nm × tool_wear_min` | N·m·min | interaction between load and accumulated wear |

Derived features are deterministic and computed from model-input fields only.

## Validation ranges

The following ranges are broad physical/data-quality guards, not learned normal-operation thresholds.

| Field | Accepted fixture range |
|---|---:|
| `air_temperature_k` | 250–350 K |
| `process_temperature_k` | 250–400 K |
| `rotational_speed_rpm` | 0–10,000 rpm |
| `torque_nm` | 0–500 N·m |
| `tool_wear_min` | 0–1,000 min |

A value outside these guards, a missing required sensor, or a non-monotonic timestamp produces a data-quality hold. Operational normal ranges used in an Evidence Package come from policy/reference statistics and are distinct from these broad guards.

## Product fixture envelope

Each `data/fixtures/GS-*.json` file contains:

- `schema_version`, `scenario_id`, `event_id`
- equipment identity, line, criticality, assigned engineer, maintenance context
- current observation and a short sensor history
- runtime switches such as LLM/provider availability
- expected Gold state used only by tests

The same fixture is rendered for manager and engineer roles; role-specific language and layout never alter the source facts.
