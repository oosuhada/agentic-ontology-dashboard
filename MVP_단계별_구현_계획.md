# P2 MVP 단계별 구현 계획

## 0. 계획의 목적

이 계획은 `프로젝트2_멘토링_통합정리_및_Takeaways.md`, 수행계획서, `레퍼런스-프로젝트2/README.md`를 기준으로 프로젝트 2의 MVP를 구현하기 위한 작업 순서를 정의한다.

프로젝트 2의 핵심 제품은 단순한 고장 예측 모델이나 고정형 대시보드가 아니다.

> 제조 설비의 예측·이상 탐지 결과를 근거 데이터와 함께 해석하고, 매니저와 엔지니어의 역할에 따라 필요한 설명·차트·조치 정보를 동적으로 구성하는 의사결정 지원 시스템을 만든다.

기간보다 **완료 조건을 통과하는 순서**를 우선한다. 앞 단계의 산출물은 다음 단계의 입력 계약이 된다.

핵심 수직 흐름은 다음과 같다.

```text
AI4I·설비 센서 데이터
→ 데이터 검증·피처 생성
→ 고장 확률·고장 유형 예측
→ 판정 임계값·오탐/미탐 정책
→ Evidence Package
→ 규칙 기반 리포트
→ LLM 리포트 에이전트
→ Audience·Intent Planner
→ 허용된 UI Block Spec
→ React 역할별 대시보드
→ 매니저 판단·엔지니어 점검·감사 기록
```

레퍼런스 저장소는 구조와 구현 패턴을 참고하는 용도다. 서로 다른 저장소를 통째로 합치지 않는다. 라이선스가 없는 `agentic-predictive-maintenance`, `mainitq-predict-spc`는 코드 복사 없이 업무 흐름과 아이디어만 참고한다.

---

# 1. MVP 최종 사용자 여정

## 1.1 매니저 여정

1. 위험 설비 우선순위 목록을 본다.
2. 한 설비를 선택한다.
3. 고장 위험도, 예상 영향, 판단 근거 요약을 확인한다.
4. `계속 운전`, `점검 요청`, `정지 검토` 중 권장 결정을 확인한다.
5. 담당 엔지니어에게 전달할 조치 내용을 승인하거나 메모를 남긴다.
6. 필요하면 근거 차트와 상세 리포트로 내려간다.

## 1.2 엔지니어 여정

1. 자신에게 배정된 위험 설비를 본다.
2. 센서 시계열과 이상 구간을 확인한다.
3. 위험도를 올린 주요 변수와 정상 범위를 비교한다.
4. 예상 고장 유형과 점검 체크리스트를 확인한다.
5. 매니저 보고용 요약을 생성한다.
6. 점검 상태와 메모를 기록한다.

## 1.3 MVP 데모에서 반드시 보여줄 차이

동일한 설비 사건을 매니저와 엔지니어가 열었을 때 다음이 달라야 한다.

| 구분 | 매니저 | 엔지니어 |
|---|---|---|
| 첫 정보 | 위험도·영향·권장 결정 | 센서 변화·이상 구간 |
| 설명 깊이 | 짧고 업무 중심 | 기술 근거 중심 |
| 차트 우선순위 | 필요할 때만 노출 | 기본 노출 |
| 주요 행동 | 판단·승인·지시 | 점검·분석·보고 |
| 모델 정보 | 접힌 상세 영역 | 필요 시 상세 확인 |

---

# 2. MVP 필수 범위와 제외 범위

## 2.1 필수 범위

- AI4I 2020 데이터 로딩과 검증
- 최소 1개 베이스라인 모델과 1개 비교 모델
- 클래스 불균형을 고려한 평가
- 판정 임계값과 오탐·미탐 정책 분리
- 개별 예측의 주요 근거 생성
- 공통 Evidence Package JSON 계약
- 규칙 기반 리포트 fallback
- LLM 기반 매니저·엔지니어 리포트
- 허용된 UI 블록 기반 동적 화면 구성
- React 최종 사용자 UI
- FastAPI 서비스 경계
- 역할 전환 또는 역할별 진입 화면
- Gold 데모 시나리오
- 자동 테스트와 원커맨드 실행
- GitHub 저장소와 단계별 태그

## 2.2 MVP에서 제외

- 실제 설비 제어
- 실제 CMMS·MES·ERP 쓰기 연동
- 프로젝트 3 Knowledge Graph 전체 구현
- 완전 자유 형식 HTML·JavaScript 생성형 UI
- 모든 제조 데이터셋 지원
- 실시간 공장 스트리밍 인프라 구축
- 최고 수준의 모델 성능 경쟁
- 디지털 트윈 3D 구현
- 자동 작업 지시 실행
- 다중 테넌트와 정교한 사용자 인증

## 2.3 선택 확장

- 프로젝트 3 Neo4j Context Adapter
- Streamlit 내부 모델 검증 콘솔
- WebSocket 실시간 센서 시뮬레이션
- 다중 설비 위험 우선순위화
- 작업 지시 승인 워크플로
- 보고서 PDF 내보내기
- LlamaIndex 기반 매뉴얼 RAG

---

# 3. 권장 기술 구조

## 3.1 기본 기술 선택

- 최종 사용자 UI: React 기반 Next.js
- API: FastAPI
- 모델링: Python, pandas, scikit-learn, XGBoost 또는 LightGBM 후보
- 설명 가능성: permutation importance, SHAP 또는 InterpretML Adapter
- 차트: Recharts 또는 검증된 React 차트 컴포넌트
- UI 블록: 사전 등록 React 컴포넌트
- LLM: Provider Adapter 구조
- 상태 저장: 초기 SQLite
- 계약: JSON Schema와 Pydantic
- 테스트: pytest, frontend unit test, Playwright
- 실행: Docker Compose 또는 로컬 원커맨드 스크립트

## 3.2 React를 기본 UI로 선택하는 이유

- 역할별 화면 구조와 블록 순서를 유연하게 바꿀 수 있다.
- 대화, 차트, 승인 카드와 상세 화면을 하나의 제품 UX로 연결하기 쉽다.
- 멘토가 강조한 동적 정보 구조와 사용자별 대시보드 구현에 적합하다.
- 기존 프로젝트 3의 React·FastAPI 운영 경험을 재사용할 수 있다.

Streamlit은 MVP의 공식 제품 UI로 사용하지 않는다. 필요할 경우 모델 실험과 내부 검증용 콘솔로 후순위 추가한다.

---

# 4. 권장 폴더 구조

```text
mvp-프로젝트2/
├── .github/
│   └── workflows/
├── api/
│   ├── app/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── adapters/
│   │   ├── repositories/
│   │   └── main.py
│   └── pyproject.toml
├── web/
│   ├── app/
│   ├── components/
│   │   ├── dashboard-blocks/
│   │   └── shared/
│   ├── lib/
│   └── package.json
├── ml/
│   ├── src/
│   ├── notebooks/
│   └── artifacts/
├── data/
│   ├── raw/
│   ├── processed/
│   └── fixtures/
├── schemas/
│   ├── evidence-package.schema.json
│   ├── report.schema.json
│   └── ui-block.schema.json
├── prompts/
│   ├── manager-report.md
│   ├── engineer-report.md
│   └── ui-planner.md
├── evaluation/
│   ├── gold_scenarios.yml
│   ├── report_cases.yml
│   └── results/
├── docs/
│   ├── adr/
│   ├── architecture/
│   ├── mvp-scope.md
│   ├── data-dictionary.md
│   └── service-contract.md
├── infra/
│   └── docker-compose.yml
├── scripts/
├── tests/
├── .env.example
├── .gitignore
├── README.md
└── MVP_단계별_구현_계획.md
```

---

# 5. 단계별 구현 계획

## 0단계. 폴더·GitHub 저장소·개발 규칙 초기화

**상태: 부분 완료 — 폴더 구조·정책 파일·README·CI·Git bootstrap 스크립트 완료, Git 저장소 초기화·원격 연결·초기 push 대기**

### 구현할 내용

- 로컬 프로젝트 경로를 `mvp-프로젝트2`로 고정한다.
- 독립 Git 저장소로 초기화한다.
- GitHub 사용자 `oosuhada` 아래 원격 저장소를 생성한다.
- 권장 저장소명은 `factory-signal-board`로 한다.
- 초기에는 Private 저장소로 만들고 발표 또는 공개 준비 후 공개 여부를 다시 결정한다.
- 기본 브랜치는 `main`으로 한다.
- Git 작성자 정보는 기존 프로젝트 3과 동일하게 설정한다.
  - 이름: `우수`
  - 이메일: `185910926+oosuhada@users.noreply.github.com`
- `.env`, 모델 산출물, 임시 데이터, 로그, node_modules, Python 가상환경을 `.gitignore`에 포함한다.
- `.env.example`만 추적한다.
- Conventional Commit 형식을 사용한다.

### 권장 GitHub 연결 결과

```text
local:  .../비스텔리전스 파이널 프로젝트/mvp-프로젝트2
remote: https://github.com/oosuhada/factory-signal-board.git
branch: main
```

### 브랜치 전략

- `main`: 실행 가능하고 검증된 상태만 유지
- `feat/<topic>`: 기능 개발
- `fix/<topic>`: 오류 수정
- `docs/<topic>`: 문서 변경
- 규모가 작은 초기 MVP에서는 장기 `develop` 브랜치를 두지 않는다.

### 첫 커밋

```text
chore: bootstrap project 2 workspace
```

### 첫 태그

```text
p2-stage0-bootstrap-v1
```

### 산출물

- GitHub 원격 저장소
- 기본 폴더 구조
- `.gitignore`
- `.env.example`
- `README.md`
- CI 초안

### 완료 조건

- `git status`가 깨끗하다.
- `main`과 `origin/main`이 일치한다.
- 새 환경에서 저장소를 clone할 수 있다.
- 비밀정보와 대용량 산출물이 추적되지 않는다.
- README에 개발 환경과 실행 예정 구조가 기록돼 있다.

---

## 1단계. MVP 질문·사용자·Gold 시나리오 고정

**상태: 완료 — MVP 범위, 핵심 Persona, 역할별 정보 계약, 8개 Gold 시나리오와 안전한 fallback 기준 확정**

### 구현할 내용

매니저와 엔지니어가 실제로 판단할 질문을 먼저 정의한다.

권장 Gold 시나리오:

1. 정상 설비: 불필요한 경고를 만들지 않는다.
2. 공구 마모 위험: `tool_wear` 증가가 핵심 근거이다.
3. 열 방출 이상: 공정 온도와 공기 온도 차이가 핵심 근거이다.
4. 동력·토크 이상: 동력 또는 과부하 관련 근거를 보여준다.
5. 복합 이상: 여러 위험 근거 중 우선순위를 정한다.
6. 저신뢰 결과: 불확실성을 표시하고 추가 점검을 권고한다.
7. 데이터 품질 문제: 잘못된 값을 고장으로 단정하지 않는다.
8. LLM 장애: 규칙 기반 리포트로 정상 동작한다.

각 시나리오에 다음을 기록한다.

- 입력 데이터 또는 fixture ID
- 사용자 역할
- 기대 상태
- 기대 주요 근거
- 기대 UI 블록
- 허용 가능한 결론
- 금지해야 하는 단정
- 기대 사용자 행동

### 산출물

- [x] `docs/10-product/mvp-scope.md`
- [x] `docs/10-product/personas.md`
- [x] `evaluation/gold_scenarios.yml`
- [x] `docs/30-implementation/stage-history/stage1-scope-validation.md`
- [x] 필수 기능·제외 기능 목록

### 완료 조건

- [x] 8개 Gold 시나리오의 목적·기대 상태·근거·금지 단정·사용자 행동이 정의돼 있다.
- [x] 같은 사건의 매니저·엔지니어 기대 화면 차이가 정의돼 있다.
- [x] 성공 기준이 “대시보드를 만든다”가 아니라 구체적인 판단 흐름으로 기록돼 있다.
- [x] 데이터 품질 오류와 저신뢰 결과를 확정 고장으로 표현하지 않는 안전 기준이 있다.
- [x] LLM·Planner 장애 시 결정론적 fallback 완료 조건이 있다.

### 참고 레퍼런스

- `agentic-predictive-maintenance`: 다중 위험 우선순위와 매니저 흐름
- `mainitq-predict-spc`: 운영자·관리자·승인 화면 분리
- `ai-self-healing-machine-lab`: 진단·점검·승인 사용자 여정

### 권장 커밋·태그

```text
commit: docs: define MVP personas and gold scenarios
tag: p2-stage1-scope-v1
```

---

## 2단계. AI4I 데이터 검증과 데이터 계약 정의

**상태: 완료 — AI4I 컬럼·출처·checksum·누수 정책, 데이터 gap, 입력 스키마와 8개 Gold fixture 구현·검증**

### 구현할 내용

- AI4I 2020 원본 데이터 출처와 라이선스를 기록한다.
- 행 수, 결측, 중복, 데이터 타입을 검사한다.
- 입력 피처와 사후 분석용 고장 모드 컬럼을 분리한다.
- 데이터 누수 가능성을 검토한다.
- 주요 변수의 단위와 정상 범위를 정의한다.
- 실제 제품 시나리오에 부족한 설비 메타데이터를 합성 fixture로 보강한다.

합성 가능한 보조 정보:

- 설비 ID와 표시명
- 설비 중요도
- 생산 라인
- 담당 엔지니어
- 최근 점검일
- 부품 재고
- 예상 정지 영향
- 점검 체크리스트

### 산출물

- `docs/10-product/data-dictionary.md`
- `docs/10-product/data-gap.md`
- `data/raw/README.md`
- 데이터 검증 스크립트
- 합성 설비 메타데이터 fixture

### 완료 조건

- 입력 피처와 라벨·고장 모드 용도가 분리돼 있다.
- 데이터 누수 검사가 자동화돼 있다.
- 모든 Gold 시나리오가 실제 또는 합성 fixture와 연결된다.
- 원본 데이터 출처와 사용 조건이 기록돼 있다.

### 참고 레퍼런스

- `predictive-maintenance-ml`: AI4I 입력·고장 모드 분리
- `agentic-predictive-maintenance`: 설비·인력·부품 합성 마스터 데이터

### 권장 커밋·태그

```text
commit: feat: add validated AI4I data contract and fixtures
tag: p2-stage2-data-v1
```

---

## 3단계. 재현 가능한 모델 베이스라인 구현

**상태: 완료 — Dummy·Logistic Regression·Random Forest 비교, 고정 split·seed, Random Forest 선택과 held-out test 기록**

### 구현할 내용

최소한 다음 모델을 비교한다.

- Logistic Regression 또는 Decision Tree
- Random Forest 또는 XGBoost

필수 원칙:

- 학습·검증·테스트 분리
- 동일 전처리 파이프라인
- 클래스 불균형 대응
- Accuracy 단독 사용 금지
- Average Precision, Precision, Recall, F1, 혼동행렬 기록
- 학습 데이터에서 임계값을 선택하고 테스트 데이터는 최종 평가에만 사용

파생변수 후보:

- 공정 온도와 공기 온도의 차이
- 회전 속도와 토크 기반 동력
- 토크×공구 마모 기반 과부하 지표

### 산출물

- 학습 파이프라인
- 모델 비교 결과
- 재현 가능한 CLI
- 모델 메타데이터
- 평가 표와 그래프

### 완료 조건

- 고정 seed로 재실행했을 때 같은 결과가 나온다.
- 단순 Dummy 모델보다 의미 있게 우수하다.
- 테스트 세트가 모델·임계값 선택에 사용되지 않는다.
- 모델 버전과 학습 데이터 버전을 추적할 수 있다.

### 참고 레퍼런스

- `predictive-maintenance-ml`: 모델 비교, 피처 엔지니어링, 재현 가능한 artifact 생성
- `ai-self-healing-machine-lab`: AI4I 제품 통합 구조

### 권장 커밋·태그

```text
commit: feat: add reproducible predictive maintenance baseline
tag: p2-stage3-model-v1
```

---

## 4단계. 판정 임계값과 운영 비용 정책 설계

**상태: 완료 — Recall 제약·비용 기반 임계값을 계산하고 trained model과 deterministic Gold 정책을 버전별로 분리**

### 구현할 내용

모델의 기본 `0.5` 임계값을 그대로 사용하지 않는다.

- Recall 제약 기반 임계값 후보
- 오탐·미탐 비용 기반 임계값 후보
- 설비 중요도에 따른 위험 등급
- `normal`, `attention`, `warning`, `critical` 상태 정책
- 저신뢰 예측 처리

권장 정책 파일:

```json
{
  "model_version": "baseline-v1",
  "decision_threshold": 0.57,
  "minimum_recall_target": 0.80,
  "severity_rules": {
    "attention": 0.40,
    "warning": 0.57,
    "critical": 0.80
  },
  "false_negative_cost": 10,
  "false_positive_cost": 1
}
```

수치는 실험 결과와 업무 가정을 바탕으로 확정하며 위 예시는 초기 계약 형태만 의미한다.

### 산출물

- `threshold_policy.json`
- 임계값별 Precision·Recall·비용 곡선
- 위험 등급 정책 문서

### 완료 조건

- 모델 파일과 운영 임계값이 분리돼 있다.
- 왜 해당 임계값을 선택했는지 설명할 수 있다.
- 모든 Gold 시나리오가 기대 위험 등급으로 분류된다.

### 참고 레퍼런스

- `predictive-maintenance-ml`: recall-constrained threshold, cost-minimizing threshold
- `mainitq-predict-spc`: 실험 임계값과 운영 정책 분리

### 권장 커밋·태그

```text
commit: feat: add threshold and operational risk policy
tag: p2-stage4-threshold-v1
```

---

## 5단계. Evidence Package 계약과 개별 예측 근거 구현

**상태: 완료 — 센서·파생변수·정책·context·lineage를 포함한 Evidence Schema와 8개 패키지 검증 완료**

### 구현할 내용

모델과 리포트·UI 사이에 공통 Evidence Package를 둔다.

최소 계약:

```json
{
  "event_id": "EVT-001",
  "equipment_id": "M-001",
  "model_version": "baseline-v1",
  "status": "warning",
  "failure_probability": 0.82,
  "threshold": 0.57,
  "predicted_failure_type": "tool_wear_failure",
  "detected_interval": {
    "start": "2026-08-20T10:20:00",
    "end": "2026-08-20T10:30:00"
  },
  "top_factors": [
    {
      "feature": "tool_wear",
      "display_name": "공구 마모",
      "value": 235,
      "normal_range": "0-180",
      "direction": "risk_up",
      "contribution": 0.41
    }
  ],
  "maintenance_context": [],
  "data_quality_warnings": [],
  "generated_at": "2026-08-20T10:30:05"
}
```

- 전역 변수 중요도와 개별 예측 근거를 구분한다.
- 모든 수치는 원본 데이터 또는 계산 결과로 역추적할 수 있게 한다.
- LLM이 임의로 수치를 만들 수 없게 한다.

### 산출물

- `schemas/evidence-package.schema.json`
- Pydantic 모델
- 모델 출력 Adapter
- local explanation 구현
- 샘플 Evidence fixture

### 완료 조건

- 모든 Gold 사건에 유효한 Evidence Package가 생성된다.
- JSON Schema 검증을 통과한다.
- 주요 근거가 예측 결과와 모순되지 않는다.
- UI와 LLM이 원시 모델 객체에 직접 의존하지 않는다.

### 참고 레퍼런스

- `interpret`: global/local explanation 분리
- `predictive-maintenance-ml`: feature importance와 failure-mode 분석
- `ai-self-healing-machine-lab`: 진단 결과와 유지보수 context 분리

### 권장 커밋·태그

```text
commit: feat: add traceable evidence package contract
tag: p2-stage5-evidence-v1
```

---

## 6단계. 규칙 기반 역할별 리포트 구현

**상태: 완료 — 매니저·엔지니어·데이터 품질용 deterministic grounded report와 human-approved action 구현**

### 구현할 내용

LLM보다 먼저 결정론적 리포트를 만든다.

매니저 리포트 필드:

- 현재 상태
- 핵심 위험 요약
- 예상 영향
- 권장 결정
- 담당자·기한
- 근거 요약

엔지니어 리포트 필드:

- 이상 시작 시점
- 주요 센서 변화
- 정상 범위 비교
- 예상 고장 유형
- 점검 체크리스트
- 매니저 보고용 요약

### 산출물

- `report.schema.json`
- manager renderer
- engineer renderer
- 리포트 snapshot test

### 완료 조건

- LLM API 없이 모든 Gold 시나리오가 설명된다.
- 동일 입력은 동일 핵심 결론을 생성한다.
- Evidence에 없는 수치나 사실이 나오지 않는다.
- 역할별 정보 깊이와 용어가 구분된다.

### 참고 레퍼런스

- `agentic-predictive-maintenance`: deterministic fallback
- `mainitq-predict-spc`: 매니저 노트·승인 흐름

### 권장 커밋·태그

```text
commit: feat: add deterministic role-based reports
tag: p2-stage6-rule-report-v1
```

---

## 7단계. LLM 리포트 에이전트 연결

**상태: 완료 — OpenAI-compatible Adapter, JSON Schema·grounding·금지 단정 검사와 fail-closed fallback 구현**

### 구현할 내용

- LLM Provider Adapter를 만든다.
- manager와 engineer prompt를 분리한다.
- 구조화 출력으로 Report Schema를 강제한다.
- Evidence Package만 컨텍스트로 전달한다.
- 근거 필드 ID를 리포트 문장에 연결한다.
- timeout, schema failure, provider failure 시 규칙 기반 리포트로 fallback한다.
- 과도한 단정과 조작 지시를 막는다.

필수 출력 원칙:

- 현재 데이터가 말해주는 사실과 추정 의견을 구분한다.
- 불확실한 원인은 `가능성`, `추정`, `추가 점검 필요`로 표현한다.
- 안전에 영향을 주는 실제 설비 제어는 권고만 하고 자동 실행하지 않는다.

### 산출물

- LLM Provider Adapter
- 역할별 prompt
- 구조화 출력 parser
- fallback 정책
- LLM 호출 추적 로그

### 완료 조건

- 모든 Gold 시나리오가 schema-valid 리포트를 반환한다.
- LLM 장애 시 제품 흐름이 중단되지 않는다.
- 수치 일치 테스트를 통과한다.
- 역할별 문장 길이와 정보 깊이가 구분된다.

### 참고 레퍼런스

- `agentic-predictive-maintenance`: provider fallback과 에이전트 도구 경계
- `data-formulator`: 대화와 분석 결과의 연결
- `OpenGenerativeUI`: 에이전트 응답과 UI 이벤트 분리

### 권장 커밋·태그

```text
commit: feat: add grounded LLM report agent with fallback
tag: p2-stage7-llm-report-v1
```

---

## 8단계. 동적 UI Block Schema와 Planner 구현

**상태: 완료 — 등록 블록·data field 전용 Planner와 역할·intent·시나리오별 우선순위, 임의 UI 차단 구현**

### 구현할 내용

LLM이 React 코드를 직접 만들지 않는다. 사전에 허용된 UI 블록만 선택·배치하게 한다.

초기 허용 블록:

- `StatusSummary`
- `RiskKpi`
- `PriorityList`
- `SensorLineChart`
- `AnomalyTimeline`
- `FactorContribution`
- `EvidenceTable`
- `RecommendedActions`
- `ManagerDecisionCard`
- `EngineerChecklist`
- `ModelDetails`
- `DataQualityWarning`

Planner 입력:

- 사용자 역할
- 현재 질문 의도
- Evidence Package
- 리포트
- 화면 크기 또는 채널

Planner 출력:

- 블록 종류
- 표시 순서
- 강조 수준
- 사용할 데이터 필드
- 접힘 여부

### 산출물

- `ui-block.schema.json`
- 규칙 기반 Planner
- 선택적 LLM Planner
- block registry
- invalid block 차단 테스트

### 완료 조건

- 허용되지 않은 컴포넌트가 렌더링되지 않는다.
- 매니저와 엔지니어가 같은 사건에서 다른 블록 순서를 받는다.
- 차트 데이터는 Evidence의 필드만 참조한다.
- Planner 실패 시 역할별 기본 레이아웃을 반환한다.

### 참고 레퍼런스

- `data-formulator`: Chart Spec과 Renderer 분리
- `OpenGenerativeUI`: visual decision matrix와 이벤트 구조
- `tremor`: dashboard block 카탈로그

### 권장 커밋·태그

```text
commit: feat: add governed dynamic UI block planner
tag: p2-stage8-ui-planner-v1
```

---

## 9단계. FastAPI 서비스 계약 구현

**상태: 완료 — 조회·Evidence·Report·Layout·판단·메모·대화·reset API와 SQLite 감사·구조화 오류 구현**

### 구현할 내용

초기 API 후보:

```text
GET  /health
GET  /api/equipment
GET  /api/equipment/{id}
GET  /api/events
GET  /api/events/{event_id}/evidence
POST /api/events/{event_id}/report
POST /api/events/{event_id}/layout
POST /api/events/{event_id}/decision
POST /api/events/{event_id}/notes
```

서비스 경계:

- model service
- evidence service
- report service
- layout planner
- maintenance context adapter
- audit repository

### 산출물

- OpenAPI 계약
- FastAPI routes와 services
- SQLite 저장소
- 오류 응답 계약
- API 테스트

### 완료 조건

- UI가 모델 코드를 직접 import하지 않는다.
- 같은 API에서 규칙 기반·LLM 모드를 교체할 수 있다.
- 오류가 구조화된 형식으로 반환된다.
- 주요 작업에 `event_id`, `run_id`, `model_version`이 남는다.

### 참고 레퍼런스

- `ai-self-healing-machine-lab`: FastAPI·WebSocket·저장소 구조
- `agentic-predictive-maintenance`: service interface와 adapter 패턴

### 권장 커밋·태그

```text
commit: feat: add FastAPI service boundary and audit storage
tag: p2-stage9-api-v1
```

---

## 10단계. React 매니저 대시보드 구현

**상태: 완료 — 위험 우선순위, 상태·영향·결정·담당 메모 중심 React 화면 구현**

### 구현할 내용

- 설비 위험 우선순위 목록
- 상태 KPI
- 위험 요약
- 예상 영향
- 권장 결정 카드
- 근거 펼쳐보기
- 엔지니어 전달 메모
- 승인·보류 상태

초기에는 실제 로그인 대신 역할 선택 fixture를 사용할 수 있다.

### 산출물

- 매니저 페이지
- 공통 디자인 토큰
- 로딩·빈 결과·오류·저신뢰 상태
- 반응형 UI
- Playwright 핵심 흐름 테스트

### 완료 조건

- 매니저가 센서 차트를 분석하지 않아도 현재 판단을 이해할 수 있다.
- 중요한 정보가 첫 화면에 노출된다.
- 상세 근거로 내려갈 수 있다.
- Gold 매니저 시나리오가 자동 테스트를 통과한다.

### 참고 레퍼런스

- `agentic-predictive-maintenance`: fleet priority와 business impact
- `mainitq-predict-spc`: manager report·approval
- `tremor`: KPI·카드·차트 UI

### 권장 커밋·태그

```text
commit: feat: add manager decision dashboard
tag: p2-stage10-manager-ui-v1
```

---

## 11단계. React 엔지니어 대시보드 구현

**상태: 완료 — 센서 추세, 이상 구간, 기여 요인, Evidence 표, 체크리스트와 보고 흐름 구현**

### 구현할 내용

- 센서 시계열 차트
- 이상 구간 highlight
- 주요 변수 기여도
- 정상 범위 비교
- 고장 유형 설명
- 점검 체크리스트
- 매니저 보고용 요약 생성
- 점검 상태와 메모

### 산출물

- 엔지니어 페이지
- 차트 block
- Evidence drill-down
- 체크리스트 상태 저장
- Playwright 핵심 흐름 테스트

### 완료 조건

- 이상 시점과 주요 근거를 차트에서 확인할 수 있다.
- 리포트 문장과 차트 근거가 서로 연결된다.
- 엔지니어가 점검 후 매니저에게 보낼 요약을 만들 수 있다.
- Gold 엔지니어 시나리오가 자동 테스트를 통과한다.

### 참고 레퍼런스

- `ai-self-healing-machine-lab`: 진단·점검 checklist·incident report
- `interpret`: local explanation UI
- `data-formulator`: 질문·차트·설명 결합 UX

### 권장 커밋·태그

```text
commit: feat: add engineer evidence dashboard
tag: p2-stage11-engineer-ui-v1
```

---

## 12단계. 대화형 후속 질문과 역할별 재구성

**상태: 완료 — 허용 intent router, 화면 재구성, 대화 이력과 injection·실제 제어 요청 거부 구현**

### 구현할 내용

초기 지원 질문을 제한적으로 정의한다.

- 왜 위험한가?
- 어떤 센서가 가장 크게 영향을 줬는가?
- 정상 설비와 비교해줘.
- 매니저용으로 짧게 요약해줘.
- 엔지니어용으로 근거를 자세히 보여줘.
- 무엇을 먼저 점검해야 하는가?

질문을 다음 intent로 라우팅한다.

- explain-risk
- compare
- summarize-manager
- detail-engineer
- recommend-check
- show-model-details

### 산출물

- intent router
- 대화 Thread 저장
- UI 재구성 이벤트
- 허용 질문·금지 질문 정책

### 완료 조건

- 지원 질문은 기존 Evidence를 벗어나지 않는다.
- 질문에 따라 텍스트와 UI 블록이 함께 바뀐다.
- 같은 사건의 대화 이력이 유지된다.
- 범위를 벗어난 질문은 안전하게 한계를 설명한다.

### 참고 레퍼런스

- `data-formulator`: unified data thread와 branching
- `OpenGenerativeUI`: text 또는 visual response 선택

### 권장 커밋·태그

```text
commit: feat: add evidence-grounded follow-up interaction
tag: p2-stage12-conversation-v1
```

---

## 13단계. 프로젝트 3 연결 Adapter 준비

**상태: 완료 — Project 3 HTTP Maintenance Context 계약과 장애 시 fixture fallback 구현·검증**

### 구현할 내용

프로젝트 2는 프로젝트 3 없이 독립 실행돼야 한다. 대신 다음 인터페이스를 둔다.

```python
class MaintenanceContextProvider:
    def get_context(self, equipment_id: str, failure_type: str) -> MaintenanceContext:
        ...
```

초기 구현:

- JSON fixture provider

후속 구현:

- Project 3 API provider
- Neo4j provider
- LlamaIndex document provider

Context 후보:

- 설비·부품 관계
- 유사 고장 사례
- 관련 매뉴얼
- 권장 점검 항목
- 최근 정비 이력
- MES·ERP 영향 정보

### 산출물

- Context Provider interface
- JSON fixture implementation
- project3 adapter contract
- 장애 fallback

### 완료 조건

- Project 3가 없어도 전체 MVP가 작동한다.
- Provider를 교체해도 Report와 UI 계약이 바뀌지 않는다.
- Context 출처와 버전이 Evidence Package에 남는다.

### 참고 레퍼런스

- `agentic-predictive-maintenance`: service adapter 구조
- `ai-self-healing-machine-lab`: local retriever와 optional RAG 경로
- 기존 `mvp-프로젝트3`: FastAPI·LlamaIndex·Evidence 계약

### 권장 커밋·태그

```text
commit: feat: add project 3 maintenance context adapter
tag: p2-stage13-p3-adapter-v1
```

---

## 14단계. 평가·회귀 테스트·안전성 검증

**상태: 완료 — Gold 8/8, backend 14 tests, frontend unit/type/build, browser E2E와 10/10 release gate 통과**

### 모델 평가

- Average Precision
- Precision, Recall, F1
- 혼동행렬
- 위험 등급별 결과
- threshold sensitivity
- 고장 유형별 slice

### 리포트 평가

- 수치 일치율
- Evidence field 추적률
- 허위 사실 발생 여부
- 역할 적합성
- 조치 가능성
- 불확실성 표현
- LLM fallback 성공률

### UI 평가

- 역할별 첫 정보 일치
- Gold scenario block 구성 일치
- 로딩·빈 결과·오류·저신뢰 화면
- 반응형 동작
- 키보드 접근성
- API 장애 시 안내

### 보안·안전 검증

- 비밀정보 추적 0건
- 생성 UI에서 임의 코드 실행 0건
- 실제 설비 제어 API 없음
- 위험 조치는 권고·승인 단계로 제한
- prompt injection 입력이 데이터 계약을 깨지 못함

### 산출물

- 평가 실행 스크립트
- 결과 리포트
- 회귀 테스트
- release gate

### 완료 조건

- Gold 시나리오 전체 PASS
- Evidence 없는 수치 생성 0건
- LLM 장애 fallback PASS
- backend test, frontend lint/build, Playwright PASS
- 비밀정보 검사 PASS

### 권장 커밋·태그

```text
commit: test: add project 2 release gates
tag: p2-stage14-release-gate-v1
```

---

## 15단계. 발표 데모 고정과 실행 패키징

**상태: 완료 — preflight·원커맨드 실행·reset·Docker·runbook·troubleshooting·CI 패키징 완료**

### 구현할 내용

- 원커맨드 실행
- Gold fixture 기반 데모 모드
- 외부 LLM 인증 실패 시 규칙 기반 모드
- 매니저와 엔지니어 비교 시연
- 데이터·모델·Evidence·리포트 lineage 표시
- 발표용 reset 기능
- README 실행 가이드
- 장애 대응 runbook

권장 발표 흐름:

1. 동일한 이상 사건을 선택한다.
2. 매니저 화면에서 위험·영향·결정을 보여준다.
3. 엔지니어 화면으로 전환해 센서·근거·점검을 보여준다.
4. `왜 위험한가?` 후속 질문으로 화면이 재구성되는 것을 보여준다.
5. LLM을 끄고도 규칙 기반 fallback이 작동하는 것을 보여준다.
6. 프로젝트 3 Context Adapter 연결 지점을 설명한다.

### 산출물

- `run_local.sh` 또는 동등한 실행 스크립트
- demo fixtures
- preflight script
- 발표 runbook
- 최종 README

### 완료 조건

- 새 clone 환경에서 문서대로 실행된다.
- 인터넷 또는 LLM 장애가 있어도 데모 핵심 흐름이 작동한다.
- 한 번의 reset으로 발표 초기 상태로 돌아간다.
- 매니저·엔지니어 차이가 5분 이내에 명확히 시연된다.

### 권장 커밋·태그

```text
commit: chore: package stable project 2 demonstration
tag: p2-mvp-v1.0.0
```

---

# 6. Git 운영 계획

## 6.1 커밋 원칙

- 한 커밋은 하나의 목적을 가진다.
- 동작하지 않는 대규모 중간 커밋을 `main`에 올리지 않는다.
- 코드와 함께 테스트·문서를 갱신한다.
- 생성 파일, 캐시, 비밀정보를 커밋하지 않는다.

권장 prefix:

- `feat:` 기능
- `fix:` 오류 수정
- `docs:` 문서
- `test:` 테스트
- `refactor:` 동작 변화 없는 구조 개선
- `chore:` 도구·환경·패키징
- `ci:` GitHub Actions

## 6.2 태그 계획

```text
p2-stage0-bootstrap-v1
p2-stage1-scope-v1
p2-stage2-data-v1
p2-stage3-model-v1
p2-stage4-threshold-v1
p2-stage5-evidence-v1
p2-stage6-rule-report-v1
p2-stage7-llm-report-v1
p2-stage8-ui-planner-v1
p2-stage9-api-v1
p2-stage10-manager-ui-v1
p2-stage11-engineer-ui-v1
p2-stage12-conversation-v1
p2-stage13-p3-adapter-v1
p2-stage14-release-gate-v1
p2-mvp-v1.0.0
```

각 태그는 해당 단계의 완료 조건을 실제로 통과한 뒤 생성한다.

## 6.3 GitHub Actions 계획

초기 CI:

- Python formatting·lint
- pytest
- frontend lint
- frontend build
- secret scan

통합 후 CI:

- API contract tests
- frontend unit tests
- Playwright Gold flow
- JSON Schema compatibility
- tracked dataset·artifact size 검사

## 6.4 데이터와 모델 파일 정책

- AI4I 원본이 작더라도 출처와 사용 조건을 문서화한다.
- 민감하거나 고객 데이터는 Git에 올리지 않는다.
- 재생성 가능한 모델 바이너리는 기본적으로 Git에서 제외한다.
- 발표에 필요한 작은 Gold fixture는 추적한다.
- 모델 artifact가 필요하면 GitHub Release 또는 별도 artifact 저장 방식을 사용한다.

---

# 7. 레퍼런스 적용 매트릭스

| 구현 영역 | 우선 참고 저장소 | 적용할 내용 | 적용하지 않을 내용 |
|---|---|---|---|
| 모델·평가 | `predictive-maintenance-ml` | 피처, 임계값, 비용 평가, 재현성 | 전체 코드 복제 |
| 전체 제품 구조 | `ai-self-healing-machine-lab` | FastAPI·React·지식 Adapter·감사 | 3D 디지털 트윈 |
| 에이전트 흐름 | `agentic-predictive-maintenance` | triage, fallback, service interface | 라이선스 없는 코드 복사 |
| 업무 승인 | `mainitq-predict-spc` | 매니저 노트·승인·검증 화면 분리 | 라이선스 없는 코드 복사 |
| 설명 가능성 | `interpret` | local explanation Adapter | 라이브러리 내부 재구현 |
| 차트·리포트 UX | `data-formulator` | Chart Spec, 대화 Thread, 편집 가능한 리포트 | 범용 분석 제품 전체 |
| 동적 UI 구조 | `OpenGenerativeUI` | UI 이벤트, 시각 선택 규칙, 샌드박스 사고방식 | 임의 HTML 실행 |
| UI 컴포넌트 | `tremor` | KPI·차트·카드 패턴 | 프로젝트 고유 로직 대체 |

---

# 8. 현재 실행 상태

1. [x] 0단계 프로젝트 골격·환경·CI 정책
2. [x] 1단계 MVP 범위·Persona·Gold 시나리오
3. [x] 2단계 AI4I 데이터 계약·Gold fixture
4. [x] 3단계 재현 가능한 모델 베이스라인
5. [x] 4단계 운영 임계값·비용 정책
6. [x] 5단계 Evidence Package
7. [x] 6단계 규칙 기반 역할별 리포트
8. [x] 7단계 선택적 LLM Adapter와 fallback
9. [x] 8단계 governed UI Planner
10. [x] 9단계 FastAPI·SQLite 감사 계약
11. [x] 10단계 매니저 React 화면
12. [x] 11단계 엔지니어 React 화면
13. [x] 12단계 후속 질문·동적 재구성
14. [x] 13단계 프로젝트 3 Context Adapter
15. [x] 14단계 Gold·회귀·안전·브라우저 검증
16. [x] 15단계 실행·reset·Docker·발표 패키징
17. [ ] 독립 Git 저장소·원격·태그 — 사용자 요청에 따라 이번 구현 범위에서 제외

최종 검증 결과는 `docs/50-operations/release-gate-report.md`에 기록했다.

---

# 9. MVP 완료의 정의

다음이 모두 만족되면 프로젝트 2 MVP를 완료로 본다.

- AI4I 기반 예측 결과가 재현 가능하다.
- 운영 임계값과 선택 근거가 기록돼 있다.
- 모든 결과가 Evidence Package로 표준화된다.
- LLM 없이도 역할별 리포트가 생성된다.
- LLM 사용 시 Evidence에 근거한 구조화 리포트를 만든다.
- 동일 사건을 매니저와 엔지니어에게 서로 다른 정보 구조로 보여준다.
- 차트와 리포트의 근거를 추적할 수 있다.
- 허용된 UI 블록만 동적으로 선택·배치된다.
- LLM·네트워크 장애에도 Gold 데모가 작동한다.
- 자동 테스트와 release gate를 통과한다.
- GitHub 저장소에서 단계별 커밋과 태그를 확인할 수 있다.
- 프로젝트 3을 나중에 연결할 Adapter 경계가 준비돼 있다.
