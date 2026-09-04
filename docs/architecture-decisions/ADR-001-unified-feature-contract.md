# ADR-001: Unified Feature Contract 및 Feature Naming 명세

- **상태**: Proposed (제안 — 목표 계약)
- **날짜**: 2026-08-12
- **결정자**: 팀 공통 (검토 진행 중)

---

## 1. 맥락 (Context)

기존 피처 생성 모듈(`feature_builder.py`)은 `{ontology_node}_{operation}` 형태(예: `Vibration_rolling_mean`)로 컬럼명을 작성하여, 하나의 온톨로지 노드로 매핑된 복수 source 컬럼이 존재할 경우 피처 덮어쓰기(Collision) 현상이 발생하였다. 또한 피처 스키마 메타데이터가 체계적으로 저장되지 않아 Backend와의 피처 규격 동기화가 불명확했다.

---

## 2. 의사결정 (Decision)

1. **Feature Naming 표준화**:
   피처 이름은 무충돌 구성을 위해 `<source_field>__<ontology_node>__<operation>__<parameters>` 규칙을 따른다.
   - 예: `vibration_raw__Vibration__rolling_mean__window_5`
2. **Feature Partition & Ordering**:
   설비별 파티션(`id_col`)과 결정론적 타임스탬프(`time_col`) 정렬을 강제한다 (`groupby(id_col)` 필수).
3. **Feature Schema Serialization**:
   `feature_schema_version: "pdm-feature-v2"`를 부여하고 Model Artifact 발행 시 `feature_schema.json`으로 포함시킨다.

---

## 3. 결과 및 영향 (Consequences)

- 피처 덮어쓰기 충돌(Invariant 17 위반) 문제 해결.
- PR #21의 `feature_builder.py` 피처 생성기 및 피처 명칭 수정이 필요하며, 기존 NPY 캐시와의 마이그레이션이 필요하다.
