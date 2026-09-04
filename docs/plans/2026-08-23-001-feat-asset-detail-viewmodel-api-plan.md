---
title: AssetDetailViewModel API Operations slice
type: plan
status: implemented
date: 2026-08-23
---

# AssetDetailViewModel API Operations Slice

## Goal

Add a backend-owned `AssetDetailViewModel` contract for the Operations asset inspector so frontend screens can consume one bounded projection instead of rebuilding sensor evidence, factor evidence, freshness, and source gaps in the UI.

## Implemented Scope

- Add `contracts/schemas/asset-detail-view-model.schema.json`.
- Add `systems/backend/app/operations/asset_detail_view_model.py` with a read-port service and pure composer.
- Add `GET /api/objects/{asset_id}/detail-view`.
- Let the frontend Objects/Event detail path request the ViewModel with `project_id` and `dataset_version_id`.
- Preserve unknown or unavailable values as `evidence.gaps[]`, `data_status.is_stale: null`, or display text such as `확인 필요`.
- Keep `risk.status_grade` separate from operational `criticality`; frontend adapters must not derive `criticality` from risk status.

## Boundary Decisions

`AssetDetailViewModel` is an Operations application ViewModel, not a Report domain object. The composer may accept Product Result Artifact, feature series, runtime prediction history, and equipment history from contracted ports, but it must not open raw `gen_data` files or import prototype map-report data.

Runtime prediction history is optional. If no contracted runtime prediction history exists, `risk_series` stays empty and the ViewModel emits a diagnosis-owned evidence gap. The Operations fixture adapter must not copy the current failure probability across historical observation rows.

Freshness is also optional. If the source cannot prove freshness, `data_status.is_stale` remains `null` with a warning instead of defaulting to `false`.

## Deferred Scope

- Production read-port backed by PostgreSQL runtime history.
- Map-report summary graphs consuming the new ViewModel baseline/history rows.
- Asset criticality modeling extension. That plan is tracked separately in PR #110 under `docs/plans`.
- LLM or agent workflow changes.

## Verification

Focused verification for this slice should include:

- `PYTHONPATH=. python3 -m pytest -q tests/test_asset_detail_view_model_contract.py tests/test_asset_detail_view_model_composer.py tests/test_operations.py`
- `cd systems/frontend && npm run test -- src/features/operations/api/operationsAdapters.test.ts`
- `cd systems/frontend && npm run lint`
- `git diff --check origin/main...HEAD`
