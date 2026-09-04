# ADR-003: Generator Runtime Prediction Result 및 Backend Decision 소유권 결정

- **상태**: Accepted (확정)
- **날짜**: 2026-08-25
- **결정자**: 팀 공통
- **선행/대체 문서**: [`ADR-002-training-runtime-prediction-ownership.md`](./ADR-002-training-runtime-prediction-ownership.md) (Superseded)

---

## 1. 맥락 (Context)

기존 ADR-002에서는 Generator가 학습과 Model Artifact 발행까지만 담당하고, Backend Diagnosis가 Model Artifact를 직접 로드하여 런타임 피처 계산과 추론을 수행하도록 제안되었다.

그러나 실제 운영 흐름에서 다음과 같은 문제점과 경계 구분이 확인되었다:
1. **피처 엔지니어링 패리티 및 중복 구현 방지**: Generator에서 학습 시 적용한 Feature Schema 및 시계열 변환(raw, rolling, diff, ewm 등) 로직을 Generator의 런타임 파이프라인에서 직접 수행하여 피처 패리티를 보장한다.
2. **이상 판정 및 비즈니스 정책의 Backend 집중**: Generator는 순수하게 모델별 예측 수치(`score`: 0.0~1.0 float 또는 null)를 산출하고 설비별 묶음(`Prediction Result Batch`)으로 저장·송신한다. 임계치(Threshold Policy) 적용, 설비별 종합 판정, Diagnosis, Evidence, Report 생성 및 사용자 알림은 비즈니스 정책을 소유한 Backend가 전담한다.
3. **유연한 정책 변경 및 관심사 분리**: 판정 기준(Threshold)이나 다중 모델 융합 정책이 변경될 때 머신러닝 파이프라인(Generator)을 재배포하거나 재실행할 필요 없이, Backend의 정책 갱신만으로 즉시 반영할 수 있다.

---

## 2. 의사결정 (Decision)

1. **Generator의 런타임 예측 및 결과 배치 송신 소유권**:
   - `systems/generator`가 관측 데이터의 전처리(Preprocessing), 설비별 시계열 피처 추출(Runtime Feature), 활성 Model Artifact 로드 및 다중 모델 점수 계산(Runtime Prediction, `score`), 설비별 결과 묶음 구성(Batch Building)을 전담한다.
   - Generator는 임계치를 적용하거나 `is_anomaly` 등 이상 판정을 내리지 않으며, 모델 결과가 생성된 모든 설비에 대해 `Prediction Result Batch` (`results[]` 배열 기반 구조)를 생성하여 Outbox에 등록하고 Backend 수신 엔드포인트(`GENERATOR_PREDICTION_RESULT_URL`)로 멱등 송신한다.
   - 모델별 예측 대상 관측 시각(`observed_at`)은 실제 추론에 사용된 피처 행 메타데이터에서 추출하여 정합성을 보장하며, 결측/시각 불일치 시 조용한 fallback 없이 `501 Not Implemented` 오류로 fail-closed 처리한다.

2. **Backend의 예측 결과 수신, 정책 기반 이상 판정 및 근거/리포트 생성 소유권**:
   - `systems/backend`는 Generator가 송신한 `Prediction Result Batch`를 수신(`POST /internal/prediction-results`)하여 멱등 저장한다.
   - 수신된 모델별 점수에 Threshold Policy를 적용하여 모델별/설비별 이상 여부를 판정하고, Diagnosis를 수행한다.
   - 관련 센서 데이터와 설비 메타데이터를 조회하여 최종 Product Result Artifact, Evidence 및 Report를 생성하고 Dashboard API로 제공 및 알림을 처리한다.

3. **시스템 간 엄격한 결합 분리 및 내부/외부 계약 경계**:
   - Generator와 Backend는 상호 Python 코드를 직접 import하지 않는다.
   - 외부 wire 정본은 `contracts/schemas/prediction-result-batch.schema.json` (`prediction-result-batch-v1`) 하나뿐이며, 불변 파일 참조(URI, SHA-256 Checksum)와 함께 시스템 간 유일한 경계로 사용한다.
   - `contracts/schemas/generator-runtime-prediction-stage.schema.json`은 Generator 내부 staging 및 checkpoint 재개를 위한 전용 저장 계약이며 Backend로 절대 전송되지 않는다.
   - 내부 Stage를 외부 Batch로 변환하는 공식 경계는 `to_external_result_item()`과 `PredictionResultBatchPayload`이다.

4. **금지 범위 (Boundary Invariants)**:
   - Generator는 Threshold Policy를 로드하거나 임계치를 적용하지 않으며, 이상 판정, Product Result Artifact, Evidence, Report, 사용자 알림을 생성하지 않는다.
   - Frontend는 Generator API를 직접 호출하지 않으며 오직 Backend API만 소비한다.
   - 기존 Backend Diagnosis 코드는 이번 PR에서 삭제하지 않고, 새로운 예측 결과 수신 기반 흐름과의 통합은 후속 Backend 작업으로 진행한다.

---

## 3. 결과 및 영향 (Consequences)

- Generator는 학습(Training)뿐만 아니라 런타임 파이프라인(Runtime Pipeline) 워커와 Outbox 기반 전송 워커(Prediction Delivery Worker)를 소유한다.
- Backend는 ML 피처 추출 및 추론 엔진 의존성을 제거하고 도메인/온톨로지/판정 정책/리포트 비즈니스 로직에 집중할 수 있다.
- 예측 결과 배치 전송 실패 시 Outbox 패턴을 통해 동일 `event_id`로 안전하게 재시도되며, 파이프라인 전체를 불필요하게 재실행하지 않는다.
- 임계치나 판정 정책의 변경이 머신러닝 연산 레이어와 완전히 독립되어 운영 안정성이 향상된다.
