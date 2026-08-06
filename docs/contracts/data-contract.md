# 데이터 계약

## Canonical V3.1

운영 데이터의 기본 식별자는 다음 조합입니다.

- `organization_id`
- `project_id`
- `workspace_id`
- `dataset_id`
- `dataset_version_id`
- `asset_id`
- `observed_at`

Dataset Version은 immutable하며 dashboard 응답에 `source_version`, checksum, row count, model version, Result Artifact schema version을 함께 제공합니다.

## Result Artifact

자산별 최신 결과는 최소 다음 의미를 가집니다.

```text
asset_id
asset_type
site_id / cell_id
observed_at
prediction_task = binary_failure_within_horizon
failure_probability
status_grade
confidence
top_factors[]
recommended_action
provenance
```

`predicted_failure_type`은 AI4I 개별 고장 모드를 확정하는 값이 아니라 `failure_risk` 또는 `no_significant_risk`의 일반 이진 위험 의미입니다.

## 권고 계약

`recommended_action`은 `policy_recommendation`입니다.

- `approval_state = not_requested`
- `execution_state = not_executed`
- `creates_work_order_automatically = false`

따라서 Result Artifact 자체가 설비 제어·정지·정비 지시를 실행하지 않습니다.

## Evidence Package

Gold Fixture와 Event 상세은 다음을 포함합니다.

- 설비와 위험 상태
- 모델·정책 version
- 현재 observation과 history
- 감지 구간
- top factor와 source type
- 정비 checklist와 source reference
- data quality warning
- lineage와 generated time

JSON Schema 기준은 `schemas/evidence-package.schema.json`입니다.

## Fallback

Canonical Runtime을 사용할 수 없으면 `data/fixtures/GS-*.json`에서 생성한 Project Event와 Evidence를 사용합니다. UI는 이를 숨기지 않고 `계약형 Fallback`과 warning으로 표시합니다.

Fallback은 화면 흐름과 권한 계약을 검증하기 위한 데모 데이터이며 운영 성능 근거가 아닙니다.

## 금지 사항

- 학습 target과 failure-mode 정답 column을 feature로 사용하지 않음
- 평가용 truth를 운영 dashboard에 노출하지 않음
- 최신 결과 병합 시 같은 `asset_id`를 중복 KPI로 집계하지 않음
- stale 관측을 최신 데이터처럼 표현하지 않음
