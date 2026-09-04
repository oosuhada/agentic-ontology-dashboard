# Predictive Maintenance Decision Workspace 개인 발표·데모 흐름

이 문서는 한 명이 `dashboard.oosu.dev`에서 제품의 전체 가치를 일관된 이야기로 설명하기
위한 개인 실행 가이드다.

## 1. 핵심 메시지

> 제조 현장의 문제는 고장을 예측하지 못하는 것만이 아니다. 현장의 기술 근거가 운영
> 판단과 경영 보고로 바뀌는 과정에서 시간차와 맥락 손실이 발생한다.

> 이 제품은 같은 설비 사건을 엔지니어에게는 점검 근거로, 운영 관리자에게는 판단 자료로,
> 경영진에게는 KPI와 보고 언어로 제공해 Decision Lead Time과 Report Lead Time을 줄인다.

## 2. 데모에 사용할 두 Case

안정적인 시연을 위해 완료된 이력 Case와 live workflow Case를 분리한다.

### 완료된 이력 Case

다음을 이미 가진 immutable Event를 선택한다.

- 감지와 Evidence
- 점검 요청·수락·완료
- 비용 분석과 정비 승인
- 정비 실행·완료
- 정비 후 Observation과 새 Product Result
- Before/After
- 운영 판단 보고와 Executive Brief

이 Case는 timeline, 정비 효과, 보고서와 lineage를 설명하는 기준이다.

### Live workflow Case

완료된 이력 Case와 다른 설비를 사용한다.

- 실제 Generator Runtime이 만든 최신 Product Result
- 점검 요청을 생성할 수 있는 상태
- 현장 역할에서 요청을 수락하고 결과를 기록할 수 있는 상태
- 운영 관리자 또는 경영진 보고 초안으로 전환할 수 있는 상태

Frontend가 임의 Result를 생성하는 presentation tick은 사용하지 않는다.

## 3. 시작 전 고정할 값

```bash
DEMO_HISTORY_EVENT_ID=RESULT#...
DEMO_HISTORY_ASSET_ID=...
DEMO_LIVE_EVENT_ID=RESULT#...
DEMO_LIVE_ASSET_ID=...
```

두 Event 모두 Mac mini PostgreSQL에서 복원 가능해야 하며, URL의 `event_id`와 화면의
선택 Case가 일치해야 한다.

## 4. 권장 시간 배분

| 시간 | 화면 | 메시지 |
|---|---|---|
| 0:00–1:00 | Login / 역할 소개 | 같은 데이터가 역할별 화면과 언어로 바뀐다 |
| 1:00–2:30 | 엔지니어 설비 현황 | 위험 설비 위치와 센서 근거를 바로 찾는다 |
| 2:30–4:00 | 원인 분석 / 모델 근거 | 실제 observation과 model artifact lineage를 보존한다 |
| 4:00–6:00 | 운영 관리자 Decision Case | 영향·비용·다음 Action을 한 화면에서 판단한다 |
| 6:00–7:30 | 현장 수락과 점검 기록 | 사람의 권한으로 workflow를 진행한다 |
| 7:30–8:40 | 완료 Case Before/After | 정비 완료가 아니라 재예측으로 효과를 확인한다 |
| 8:40–9:30 | Executive Brief / Report | 같은 snapshot으로 보고 언어를 생성한다 |
| 9:30–10:00 | Architecture / 마무리 | 하나의 실제 runtime 경로와 추적 가능한 의사결정 |

## 5. 화면 준비

### Tab 1 — Login

- 역할별 제품 경험 소개
- 화면 프리셋은 발표 환경에 맞춰 선택

### Tab 2 — Engineer

- 완료된 이력 Case URL
- 설비 현황, 원인 분석, 점검, 정비 효과 순서

### Tab 3 — Operations

- Live workflow Case URL
- 판단 대기, 비용 분석, Action panel과 보고

### Tab 4 — Executive

- 완료된 이력 Case의 Executive Brief와 출력 가능한 report

## 6. 시연 순서

### 6.1 문제와 역할

로그인 화면에서 세 역할을 짧게 설명한다.

- 엔지니어: 왜 이상이고 무엇을 점검해야 하는가
- 운영 관리자: 무엇을 판단하고 승인해야 하는가
- 경영진: 어떤 리스크와 병목을 보고해야 하는가

### 6.2 실시간 설비 현황

엔지니어 또는 운영 관리자 화면에서 다음을 보여준다.

1. 상단 live KPI
2. 구역·셀 기반 공장 상태맵
3. 위험 설비 선택
4. 상세 drawer
5. 핵심 센서 그래프

“실시간”은 source, ingestion, prediction, promotion과 UI refresh가 각각 다른 cadence를
가진다는 점을 정확히 설명한다.

### 6.3 실제 모델 근거

다음 lineage를 설명한다.

```text
gen_data observation
→ live-ingestor
→ Generator Runtime feature/prediction
→ Prediction Result Batch
→ Backend validation/promotion
→ Product Result Artifact / Evidence
```

모델 품질은 모든 모델이 좋다고 주장하지 않는다.

| Model | PR-AUC | Precision | Recall | 판단 |
|---|---:|---:|---:|---|
| CNC RandomForest | 0.696 | 0.546 | 0.679 | release candidate |
| Compressor | 0.509 | 0.135 | 0.750 | precision 개선 필요 |

### 6.4 운영 판단과 현장 실행

Live workflow Case에서 다음 순서로 진행한다.

```text
Evidence 확인
→ 점검 요청
→ 현장 역할로 전환
→ 요청 수락
→ 점검 시작
→ 점검 결과 기록
→ 운영 관리자 비용·조치 판단
```

화면 상단 Next Action과 drawer의 처리 탭을 사용한다. UI에 보이는 권한과 Backend 권한이
일치하는 Action만 실행한다.

### 6.5 완료된 이력과 정비 효과

완료 Case로 전환해 다음 timeline을 보여준다.

```text
Original Result
→ Inspection
→ Human Approval
→ Maintenance
→ Runtime Overlay Observation
→ Generator Re-prediction
→ New Result
→ Before/After
```

정비 완료 자체를 정상화라고 말하지 않는다. 새 Product Result가 실제 위험 감소를 보여줄
때만 효과가 확인됐다고 설명한다.

### 6.6 역할별 보고

같은 완료 Case를 기준으로 다음 차이를 보여준다.

- 엔지니어: 센서와 점검 결과
- 운영 관리자: 생산 영향, 비용과 판단
- 경영진: 리스크, KPI, 병목과 결정 요청

보고서는 별도의 truth가 아니라 선택 Event와 Evidence snapshot을 참조하는 업무 산출물이다.
LLM은 deterministic presentation facts를 문장으로 조합하며 승인이나 workflow 상태를
결정하지 않는다.

## 7. 생산 영향 설명

```text
예상 정지시간 × 시간당 계획 생산량 = 예상 영향 수량
예상 영향 수량 × 단위 공헌이익 = 공헌이익 노출 추정치
```

이는 capacity/economics model 기반 추정치이며 실제 생산 손실이나 회계 확정값이 아니다.

## 8. 현재 아키텍처 정본

```text
Offline
Source → Extraction → Feature/Label → Training/Evaluation → Model Artifact

Online
Live Source → live-ingestor → Generator Runtime Prediction
→ Backend Validation/Promotion → PostgreSQL Product Result
→ Product UI / Workflow / Report
```

## 9. 시작 전 체크리스트

### Runtime

- [ ] frontend, backend, postgres, redis health 정상
- [ ] live-ingestor와 generator-runtime 실행 중
- [ ] 최근 Product Result의 observed_at 갱신 확인
- [ ] presentation-only Result가 기본 조회에 섞이지 않음

### Event lineage

- [ ] 완료 Case와 Live Case가 서로 다른 설비 또는 독립 workflow 사용
- [ ] reload 후 explicit Event 유지
- [ ] Evidence, Decision, Action과 Report가 같은 Event 참조
- [ ] 진행 중 Work Order가 새 Result에 밀리지 않음

### Workflow

- [ ] 점검 요청 생성 가능
- [ ] 현장 수락·시작·완료 가능
- [ ] 비용 분석과 정비안 생성 가능
- [ ] 역할 전환 시 허용된 Action만 노출
- [ ] 완료 Case에 실제 post-maintenance Result 존재

### Report

- [ ] raw artifact ID가 기본 본문에 노출되지 않음
- [ ] 역할별 문장과 section이 실제로 달라짐
- [ ] print preview가 불필요한 공백 없이 표시됨

## 10. 표현 원칙

피해야 할 표현:

- “실제 고장이 확정됐습니다.”
- “AI가 정비를 승인했습니다.”
- “이 숫자는 실제 손실입니다.”
- “모든 모델의 품질이 높습니다.”
- “정비했으니 정상입니다.”

권장 표현:

- “24시간 이내 고장 위험을 예측한 결과입니다.”
- “시스템이 근거와 조치 후보를 제공하고 사람이 승인합니다.”
- “계획 capacity model 기반 영향 추정치입니다.”
- “release gate를 통과한 모델과 개선 중인 모델을 구분합니다.”
- “후속 관측과 재예측 결과로 정상화 여부를 확인합니다.”

## 11. Fallback

- live Result가 바뀌면 explicit 완료 Case URL로 전환한다.
- Assistant가 늦으면 deterministic report를 사용한다.
- chart가 로딩 중이면 평평한 선이 아니라 loading state가 끝날 때까지 기다린다.
- 네트워크 문제가 생기면 동일 Case의 고정 snapshot과 짧은 backup recording을 사용한다.
- workflow Action이 실패하면 실패를 숨기지 말고 권한·현재 단계·API 응답을 확인한다.

## 12. 마무리 문장

> 이 제품은 위험 점수를 보여주는 데서 끝나지 않습니다. 같은 사건의 근거를 현장 점검,
> 운영 판단, 정비 결과와 경영 보고까지 연결해 조직의 의사결정 시간을 줄이고 모든 단계의
> 책임과 결과를 추적 가능하게 만듭니다.
