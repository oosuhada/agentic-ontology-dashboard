# Operations Runtime Ownership

## 목적

이 문서는 실시간 관측이 Product Result, Closed-loop 업무와 역할별 화면으로 이어지는 현재
시스템 경계를 정의한다. 구현 책임은 실행 컴포넌트와 versioned contract를 기준으로 한다.
상위 결정은
[ADR-003](../architecture-decisions/ADR-003-generator-runtime-prediction-result-and-backend-decision-ownership.md)을
따른다.

## 운영 데이터 경로

```text
gen_data live source
→ live-ingestor
→ Backend observation tables
→ Generator Runtime Queue
→ Preprocessing / Runtime Feature / Prediction
→ Prediction Result Batch
→ Backend validation / Threshold Policy / promotion
→ Product Result Artifact / Evidence
→ Decision Case / Workflow / Report
→ Role-aware Frontend
```

이 경로가 운영 결과의 단일 진실 경로다. Frontend는 화면을 열어 둔 것만으로 Observation이나
Product Result를 생성하지 않는다. presentation 전용 결과를 Backend에 직접 주입하는 경로는
기본 제품 모드에서 사용하지 않는다.

## 컴포넌트 책임

### `gen_data`

- raw, simulation, synthetic sensor data를 재현 가능한 seed와 scenario로 생성한다.
- SensorRecord protocol과 source lineage를 보존한다.
- Closed-loop에서 정비 대상 설비의 post-maintenance Runtime Overlay Observation을 생성한다.
- 모델을 로드하거나 inference readiness, 위험도, Product Result를 결정하지 않는다.
- 과거 prediction fixture가 있더라도 제품의 최신 Result로 사용하지 않는다.

### `live-ingestor`

- source record를 검증해 선택된 live dataset과 simulation session scope로 적재한다.
- 재시도와 cursor 처리에서 중복을 만들지 않는다.
- 서로 다른 simulation session의 Observation을 하나의 연속 history로 섞지 않는다.
- 모델 feature, prediction 또는 업무 상태를 만들지 않는다.

### `systems/generator`

- 학습용 Feature/Label Dataset과 versioned Model Artifact를 생성한다.
- 런타임 관측 이력을 읽어 학습과 동일한 전처리·feature 규칙을 실행한다.
- 활성 Model Artifact별 score를 계산하고 설비별 Prediction Result Batch를 만든다.
- Outbox를 통해 Backend에 멱등 전달한다.
- threshold, 이상 판정, Product Result, Evidence, Report와 사용자 알림은 만들지 않는다.

### `systems/backend`

- Observation을 저장하고 Generator가 보낸 Prediction Result Batch를 검증·멱등 수신한다.
- scope, schema, model/dataset/session lineage를 확인한다.
- Threshold Policy와 업무 정책을 적용해 Product Result Artifact와 Evidence로 승격한다.
- Recommendation, Decision, Inspection, Maintenance, Outcome 상태 머신을 소유한다.
- 열린 WorkOrder의 `current_step`과 현재 가능한 `available_actions`를 계산한다.
- 역할별 presentation facts와 report snapshot을 제공한다.
- Generator 내부 코드를 직접 import하거나 score를 임의 생성하지 않는다.

### `systems/frontend`

- Backend API가 제공한 live Result, Evidence, workflow와 report snapshot을 표현한다.
- 실시간 그래프는 실제 최신 Observation을 이어 그리고, 데이터 로딩·비어 있음·오류를 구분한다.
- 선택한 Decision Case의 immutable snapshot을 새 Event로 자동 교체하지 않는다.
- WorkOrder ID, Result ID와 업무 상태를 합성하거나 상태 머신을 재구현하지 않는다.
- 역할에 따라 다음 행동, 판단 근거와 보고 깊이를 다르게 구성한다.

## Closed-loop 경로

```text
Product Result / Evidence
→ Inspection request
→ Field acceptance / inspection result
→ Cost decision / maintenance recommendation
→ Human approval
→ Maintenance action / completion
→ post-maintenance Runtime Overlay Observation
→ Generator re-prediction
→ Backend promotion
→ Before/After Outcome and role reports
```

정비 완료는 작업 사실일 뿐 정상 판정이 아니다. 정상화는 같은 lineage와 비교 가능한 모델
기준을 가진 post-maintenance Prediction이 도착한 뒤에만 표시한다.

진행 중 WorkOrder는 새 위험 Result보다 우선 추적한다. 새 Result가 도착해도 사용자가 수행 중인
Case를 화면에서 밀어내지 않으며, 상태맵·작업 큐·상세 패널·보고서는 동일한 Product Result와
workflow projection을 사용한다.

## Runtime 불변식

1. 모델 추론에 필요한 최소 history와 warm-up은 Model Artifact 계약으로 결정한다.
2. history backfill과 live session은 구분하며 다른 session의 tick을 섞지 않는다.
3. Prediction Result Batch는 실제 추론에 사용된 `observed_at`, model, dataset과 session을 보존한다.
4. 동일 delivery는 같은 idempotency key로 재시도한다.
5. post-maintenance 첫 prediction은 해당 workflow의 결과 확인에 우선 연결한다.
6. `presentation-live-v1` 같은 presentation-only source는 canonical live queue와 report의 기준이 아니다.
7. 운영 DB와 runtime cache는 Git 저장소에 포함하지 않는다.

## 보고와 사용자 언어

구조화된 Artifact가 사실의 기준이고 LLM은 표현 계층이다.

```text
Canonical Result Artifact
→ deterministic presentation dictionary
→ role-specific presentation facts
→ grounded LLM composition
→ artifact_id + dictionary_version + prompt_version cache
```

사용자 화면은 센서·상태·조치의 업무 용어를 우선한다. raw ID, schema, model version과 source
version은 기술 정보 disclosure에 보존한다. LLM은 lifecycle이나 Action을 결정하지 않으며,
근거가 없을 때는 내용을 만들지 않고 deterministic fallback을 사용한다.

## 검증 기준

- Generator runtime stage와 Prediction Result Batch schema contract test
- Backend 수신 멱등성, threshold/promotion과 lineage test
- session 격리 및 연속 history window test
- WorkOrder `current_step`, role permission과 `available_actions` test
- maintenance replay 후 Prediction과 Before/After 연결 E2E test
- Frontend가 demo Result 생성 API를 자동 호출하지 않는 검증
- 같은 Case의 상태맵·큐·상세·보고 snapshot 일치 검증

세부 계약은 다음 문서를 따른다.

- [프로젝트 아키텍처](../architecture.md)
- [Prediction/Decision 소유권 ADR](../architecture-decisions/ADR-003-generator-runtime-prediction-result-and-backend-decision-ownership.md)
- [Closed-loop Domain](../closed-loop-domain-contract.md)
- [Product/API/UI 소비 계약](../closed-loop-product-consumption-contract.md)
- [Runtime Overlay 계약](../closed-loop-runtime-overlay-contract.md)
