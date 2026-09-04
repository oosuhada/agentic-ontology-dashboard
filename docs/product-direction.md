# Predictive Maintenance Decision Workspace 제품 방향

> 이 문서는 프로젝트의 문제 정의, UX 우선순위와 제품 의사결정의 기준점이다.

## 1. 제품 정의

이 프로젝트는 단순한 고장 예측 모델이나 예지보전 모니터가 아니다.

> 설비 이상 발견부터 운영 판단과 경영 보고까지 걸리는 시간을 줄이는 제조 운영
> 의사결정 워크스페이스다.

같은 실시간 근거를 엔지니어, 운영 관리자, 경영진이 각자의 화면과 언어로 이해하고,
점검·승인·정비·보고로 이어지는 과정을 하나의 Decision Case 안에서 관리한다.

## 2. 해결할 문제

설비 이상이 발견된 뒤에는 다음과 같은 맥락 손실이 발생한다.

- 센서와 모델 근거가 운영 판단 자료로 변환되는 데 시간이 걸린다.
- 운영 관리자가 생산 영향과 조치 옵션을 다시 정리해야 한다.
- 경영 보고가 수동으로 작성되어 원본 근거와 판단 맥락이 누락될 수 있다.
- 사용자마다 필요한 정보의 깊이가 다른데 같은 화면과 용어를 제공하기 쉽다.
- 누가 다음 Action을 수행해야 하는지 불명확해진다.
- 정비를 완료한 사실과 위험이 실제로 감소한 결과를 혼동할 수 있다.

따라서 제품은 기술 근거를 역할별 판단 언어로 빠르게 변환하면서도 같은 Event와 Evidence
lineage를 유지해야 한다.

## 3. 역할별 중심 질문

| 역할 | 중심 질문 | 우선 화면 | 언어 |
|---|---|---|---|
| 엔지니어 | 왜 이상이며 어디를 점검해야 하는가? | 상태맵, 센서, Evidence, checklist | 센서·설비·점검 근거 |
| 운영 관리자 | 지금 무엇을 판단하고 승인해야 하는가? | Decision Case, 영향, 비용, Action | 우선순위·영향·승인 |
| 경영진 | 운영 리스크와 병목이 성과에 어떤 영향을 주는가? | Executive Brief, KPI, 보고서 | 리스크·비용·성과 |

데이터는 하나지만 메뉴 순서, 카드 배치, 기본 탭, CTA, Assistant 질문, 보고 옵션과 기술
metadata의 노출 수준은 역할별로 달라야 한다.

## 4. 역할별 제품 경험

### 엔지니어

- 실시간 공장 상태와 위험 설비 위치
- 선택 설비의 핵심 센서 2~4개
- 원인 후보, 반증 근거와 점검 위치
- 오늘의 작업 큐와 다음 Action
- 점검 checklist, 현장 메모, 정비 이력
- 정비 후 관측과 Before/After 결과

### 운영 관리자

- 판단 대기 Case와 생산 영향 우선순위
- 점검 요청, 비용 분석과 정비 승인
- 담당자, SLA, backlog와 handoff 상태
- 현재 판단에 필요한 Evidence 요약
- 보고 초안과 경영 보고 전환

### 경영진

- 전체 운영 리스크와 고위험 설비 영향
- Decision/Report lead time과 backlog trend
- 정비 효과와 비용·생산 영향
- 조직 handoff 병목
- 근거 snapshot을 보존한 Executive Brief

## 5. 조직 흐름

기술 흐름은 `Prediction → Decision → Action → Verification`이지만, 사용자가 경험하는
제품 흐름은 다음과 같다.

```text
문제 발견
→ 역할별 근거 확인
→ 운영 판단
→ 현장 실행
→ 결과 확인
→ 경영 보고
```

하나의 Decision Case는 위험 설비, 센서 Evidence, 예측 위험도, 생산 영향, 비용,
추천 조치, 담당자, workflow 단계, 다음 Action, 보고 상태와 정비 후 결과를 연결한다.

## 6. 온톨로지의 역할

온톨로지는 설비, 센서, 공정, 생산 영향, 정비 이력, 의사결정, 담당자와 보고서를
연결하는 조직의 공통 언어다. AI 예측 결과를 단순 점수가 아니라 실행 가능한 업무 객체로
바꾸고, 역할이 달라도 같은 사건을 참조하게 한다.

## 7. LLM의 역할

LLM은 센서값을 임의로 해석하거나 lifecycle을 결정하지 않는다. 서버가 선택한 검증 가능한
근거를 역할별 문장과 보고 초안으로 조합한다.

```text
Canonical Result Artifact
→ deterministic presentation dictionary
→ role-specific presentation facts
→ grounded LLM composition
→ versioned cache
```

- 엔지니어: 센서 변화, 점검 위치와 주의사항
- 운영 관리자: 생산 영향, 판단 옵션과 다음 Action
- 경영진: 리스크, 비용, KPI와 보고 문장

raw ID와 내부 모델 필드는 기술 정보에 보존하되 기본 화면에는 사용자 언어를 표시한다.

## 8. 첫 화면 우선순위

모든 역할의 공통 출발점은 실시간 현황과 공장 설비 상태맵이다. 그 아래의 강조 영역은
역할별로 다르게 구성한다.

1. 실시간 현황 KPI
2. 공장 설비 상태맵
3. 역할별 Next Action 또는 핵심 판단 블록
4. 선택 설비 상세
5. 실시간 피쳐 그래프
6. 생산 영향과 workflow 상태
7. 짧은 근거 설명
8. Assistant와 보고 초안

AI 요약이나 긴 보고서가 상태맵과 핵심 근거보다 앞에 나오지 않게 한다.

## 9. 실시간 UI 원칙

- 현재 값은 실제 최신 관측 또는 Product Result에서 읽는다.
- Frontend가 화면 효과를 위해 Product Result를 생성하지 않는다.
- 과거 구간은 10분 요약으로 읽기 쉽게 표시하되 hover 시 정확한 관측 시각과 값을 제공한다.
- 단기 구간은 미래 시간축 공간을 확보해 최신 점과 변화 방향이 눈에 들어오게 한다.
- 미래 범위는 예측 또는 추세 범위임을 실제 관측과 시각적으로 구분한다.
- 로딩 중에는 평평한 가짜 그래프가 아니라 skeleton을 표시한다.
- 결과가 없을 때만 관측 이력 없음 상태를 표시한다.

## 10. 제품 신뢰성 원칙

- 선택한 Event snapshot은 명시적으로 바꾸기 전까지 유지한다.
- 진행 중 Work Order가 새 위험 Event에 밀리지 않게 한다.
- UI 권한과 Backend 권한을 동일하게 유지한다.
- 정비 완료 후 새 Observation과 Generator prediction이 만들어질 때까지 정상으로 확정하지 않는다.
- 생산·재무 영향은 산식과 source를 함께 제공한다.
- synthetic/internal evaluation과 production fact를 구분한다.
- 보고서의 Event, Evidence, dictionary와 prompt version을 추적한다.

## 11. 핵심 KPI

- Decision lead time
- Report lead time
- Inspection request-to-completion time
- Approval-to-maintenance-start time
- Workflow backlog와 SLA 초과
- Downtime risk estimate
- Maintenance effectiveness와 재발 여부

KPI는 화면 갱신 시각이 아니라 실제 workflow milestone을 기준으로 계산한다.

## 12. 제품·기술 Roadmap

### Product / Operations

- 역할별 Next Action과 Work Queue 고도화
- 완료된 이력의 timeline과 Before/After 강화
- 보고서 승인·배포·revision lifecycle
- 장기 Decision/Report lead time 축적
- 실제 MES·ERP·CMMS 기반 영향 산식
- 모바일 현장 입력과 offline fallback

### Technology

- multi-factory / multi-tenant
- event stream 기반 갱신
- replay orchestration과 session 격리
- edge inference
- mapping/model lifecycle governance
- governed evidence와 vector retrieval
- schema drift 검증
- LLM groundedness·citation·boundary 평가 확대

## 13. 완료 기준

아래 흐름이 하나의 lineage로 실제 동작해야 한다.

```text
Live Observation
→ Generator Runtime Prediction
→ Backend Product Result promotion
→ Evidence / Decision Case
→ Inspection / Cost Decision / Human Approval
→ Maintenance Completion
→ Runtime Overlay Observation
→ Generator Re-prediction
→ New Result
→ Before/After Outcome
→ Role-specific Report
```

제품의 핵심 가치는 AI가 사람을 대신하는 것이 아니라, 사람이 같은 사건과 근거를 더 빨리
이해하고 실행하며 보고할 수 있게 만드는 것이다.
