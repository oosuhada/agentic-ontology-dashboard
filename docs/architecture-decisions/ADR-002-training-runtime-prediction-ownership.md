# ADR-002: Training과 Runtime Prediction 소유권 분리 및 Feature History Execution

- **상태**: Superseded (ADR-003에 의해 대체됨)
- **날짜**: 2026-08-12 (2026-08-25 대체)
- **결정자**: 팀 공통
- **대체 문서**: [`ADR-003-generator-runtime-prediction-and-anomaly-signal-ownership.md`](./ADR-003-generator-runtime-prediction-and-anomaly-signal-ownership.md)

> 이 문서는 ADR-003 승인 이전의 역사적 의사결정을 보존한다.
> 현재 Runtime Prediction 소유권의 규범적 기준으로 사용하지 않는다.
> 현재 기준은 [`ADR-003-generator-runtime-prediction-and-anomaly-signal-ownership.md`](./ADR-003-generator-runtime-prediction-and-anomaly-signal-ownership.md)이다.

---

## 1. 맥락 (Context)


- `systems/generator`는 학습과 Model Artifact publish까지만 소유한다. `systems/backend`는 Model Artifact를 로드해 직접 runtime inference를 수행하고, 그 결과로 Product Result Artifact와 Evidence를 생성한다.
- 그러나 rolling, lag, EMA 등 시계열 피처는 단일 Current Observation만으로 계산할 수 없으므로, Backend가 추론 시 피처를 재현하는 방식에 대한 명확한 결정이 필요하다.

---

## 2. 의사결정 (Decision)

1. **Model Artifact에 History Requirement 명시**:
   Model Artifact 패키지 내 `history_requirement.json`을 포함하여 추론에 필요한 과거 시계열 조건(`minimum_history_rows`, `maximum_lookback_hours`)을 명시한다.
2. **Backend Feature Executor 적용**:
   `systems/backend`는 `history_requirement.json`에 따라 자산별 시계열 history를 조회한 후 `feature_schema.json` 기반으로 피처를 재현한다.
3. **책임 경계 완전 격리**:
   `systems/backend`는 `systems/generator` 코드를 static/direct import 하지 않고 versioned Model Artifact만 소비한다.
4. **정비 후 Feature History 경계**:
   Closed-loop Runtime Overlay Observation은 `restart_at`부터 새로운
   `history_segment_id`를 사용한다. 별도 versioned transform 계약이 없는 한 정비 전
   history를 정비 후 rolling/lag/EMA 입력에 암묵적으로 혼합하지 않는다.
5. **Inference-ready 실행**:
   정비 후 최소 Observation 수와 lookback은 고정 demo 값이 아니라 현재 Model
   Artifact의 `history_requirement.json`에서 계산한다. Backend는 요구 이력을 충족한
   첫 Observation에서 최초 Prediction을 생성하고 이후 정상 runtime 주기를 유지한다.
6. **Readiness 및 Observation availability 소유권**:
   Backend Diagnosis만 현재 Model Artifact와 `history_requirement.json`을 소비해
   inference readiness를 판정한다. `gen_data` Runtime Overlay는 Model Artifact를 읽지
   않고 정비 후 Observation을 지속 생성·제공한다. 이력이 부족하면 Backend는 Prediction을
   수행하지 않고 다음 Observation을 기다린다.

---

## 3. 결과 및 영향 (Consequences)

- `history_requirement.json`은 Feature Parity에 필요한 **입력 이력 조건**
  (partition, order, minimum rows, lookback)을 정의한다. 실제 수치 재현
  parity는 이것만으로 보장되지 않는다.
- 완전한 parity는 다음이 추가로 확정되어야 보장된다: rolling `min_periods`,
  std `ddof`, EMA `adjust`, NaN/drop 정책, timestamp 중복 순서, dtype 변환,
  categorical preprocessing, transform executor 버전. 이 파라미터 집합은
  `feature_schema.json`의 각 feature 항목에 포함시키거나(권장), 별도
  versioned transform specification 문서로 분리한다.
- parity 보장 여부는 선언이 아니라 **golden-vector contract test**(고정된
  입력 → generator 산출 feature 벡터와 Backend 재현 feature 벡터가 완전
  일치하는지 비교하는 테스트)로 검증한다. 이 테스트가 없으면 parity가
  "보장"되었다고 표기하지 않는다.
- 정비 후 요구 이력을 충족하지 못한 상태는 `warming_up` 또는
  `history_insufficient`로 명시한다. 이를 정상 Prediction이나 heuristic 결과로
  대체하지 않는다.
- 대상 설비 Overlay branch의 Fast-forward와 Observation 생성은 Source Data Producer
  경계이며 Backend는 그 실행을 소유하지 않는다.

정비 완료에서 Overlay Observation으로 이어지는 Integration 계약은
[`../closed-loop-runtime-overlay-contract.md`](../closed-loop-runtime-overlay-contract.md)를
따른다. 이 추가 결정도 ADR의 전체 상태가 `Accepted`로 변경됐다는 의미는 아니다.

---

## 4. 역사적 미해결 논의 — ADR-003 승인 이전 기록

> 아래 내용은 ADR-003 승인 이전에 미해결 상태였던 논의를 보존한다.
> ADR-003 승인 이후에는 현재 규범으로 적용하지 않는다.

다음 운영 흐름이 제안되었으나, 위 §2의 Decision과 충돌할 수 있어 당시 Artifact
계약 확정 과정에서는 임의로 결정하지 않고 미해결로 남겨두었던 기록이다.


```text
센서값 주기적 확인
→ 구성된 모델 전체 예측
→ 모델별 이상 여부 확인
→ 결과 취합
→ 하나라도 이상이면 이상 신호 전송
→ Backend가 신호의 관측 근거와 설비 메타데이터 확인
→ Product Result Artifact / Evidence / Report 생성
→ Dashboard 알림 표시
```

**결정이 필요한 지점**:
- 주기적으로 센서값을 확인하고 구성된 모든 모델의 예측을 실행하는 컴포넌트는
  무엇인가 (Generator daemon 확장 / Backend 신규 컴포넌트 / 별도 서비스)
- 모델별 결과를 취합해 "하나 이상 이상 감지 시 신호 전송"을 판단하는 aggregation
  policy는 누가 소유하고 버전 관리하는가
- 이 aggregation policy는 개별 Model Artifact 계약에 포함되지 않는다 — 별도
  versioned policy로 관리한다 (결정 시 별도 계약 문서 신설 여부도 함께 결정)
- 신호 전송 이후 Backend가 신호 당시와 다른 최신 센서값을 잘못 조회하지 않도록
  보장하는 안정적인 observation reference 전달 방식
- 신호 최소 필드셋 확정: `signal_id`, `asset_id`, observation reference/ID,
  `observed_at`, `signal_generated_at`, aggregation policy와 version, 모델별
  `model_id`/`model_version`, 모델별 probability/score, 모델별 anomaly 판정,
  최종 aggregated anomaly 결과
- 취합 후에도 개별 모델 결과를 버리지 않는다는 원칙은 이미 합의됨 — 저장 위치와
  스키마만 결정 필요
- Frontend가 예측 실행 주체나 Generator를 직접 호출하지 않는다는 원칙은 이미
  합의됨 — Backend API 경로 설계만 결정 필요

이 항목들은 `docs/operations/history/2026-08-week2/contract-review-checklist.md`의
`GEN-STACK-02`로 추적한다.
