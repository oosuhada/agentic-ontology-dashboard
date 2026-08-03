# Ontology Dashboard Demo Runbook

## 1. 시작

```bash
cd "/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2"
cp .env.example .env
bash scripts/run_local.sh
```

기본 주소:

- Login: `http://127.0.0.1:3100/login`
- User app: `http://127.0.0.1:3100/app`
- Admin app: `http://127.0.0.1:3100/admin`
- API docs: `http://127.0.0.1:8100/docs`

API 키 없이도 모든 핵심 데모가 deterministic fallback으로 동작한다.

## 2. 발표 전 검증

```bash
source .venv/bin/activate
PYTHONPATH=api:ml/src python scripts/release_gate.py --with-e2e
```

결과 마지막에 `"pass": true`가 있어야 한다.

## 3. 권장 발표 순서

### 장면 1 — 제품 목적과 domain pack

1. `manager@ontology.local / Manager!2026`으로 로그인한다.
2. 제품명이 `Ontology Dashboard`이고 현재 workspace에 `Manufacturing Predictive Maintenance Pack`이 연결된 것을 보여준다.
3. 위험 우선순위 목록과 현재 선택 설비를 보여준다.
4. “제조 전용 제품이 아니라 같은 Ontology를 역할별 업무 화면으로 구성하고, 제조 예지보전은 첫 domain pack”이라고 설명한다.

### 장면 2 — 공구 마모 사건 GS-002

1. 사이드바에서 `GS-002`를 선택한다.
2. `StatusSummary`, 위험도, 예상 정지 영향, 권장 결정 순서를 보여준다.
3. `현장 점검 요청`을 선택하고 메모를 기록한다.
4. 기술 차트가 첫 정보가 아니라 필요 시 내려가는 근거임을 강조한다.

### 장면 3 — 같은 사건의 엔지니어 화면

1. 로그아웃한 뒤 `engineer@ontology.local / Engineer!2026`으로 로그인한다.
2. 계정 역할에 따라 첫 블록이 `SensorLineChart`로 바뀌는 것을 보여준다.
3. 공구 마모·토크 추세, 주요 기여 요인, Evidence 표와 체크리스트를 확인한다.
4. 점검 항목을 체크하고 현장 메모를 저장한다.

### 장면 4 — 후속 질문과 동적 구성

다음 버튼을 순서대로 사용한다.

- `왜 위험한가?`
- `정상 설비와 비교해줘.`
- `매니저용으로 짧게 요약해줘.`
- `무엇을 먼저 점검해야 하는가?`

답변뿐 아니라 블록 순서와 강조점이 intent에 따라 달라지는 것을 보여준다.

### 장면 5 — 안전한 실패

1. `GS-007`을 연다.
2. 데이터 품질 경고가 첫 블록이며 고장을 단정하지 않는 것을 보여준다.
3. `GS-008`을 연다.
4. 상단 `deterministic_fallback` badge를 보여준다.
5. LLM과 Planner가 꺼져도 리포트·차트·점검 흐름이 유지됨을 설명한다.

### 장면 6 — 인증·관리자와 FDE 경계

1. `fde@ontology.local / FDE!2026`으로 로그인해 FDE 기본 landing을 보여준다.
2. `/admin`으로 이동하면 403 화면이 나오는 것을 보여준다.
3. `admin@ontology.local / OntologyAdmin!2026`으로 다시 로그인한다.
4. Users에서 pending 승인, 역할과 workspace scope를 설정하는 foundation을 보여준다.
5. Audit Logs에서 관리자 변경 기록을 확인한다.

### 장면 7 — 프로젝트 3 확장

`ModelDetails`에서 Context provider/version을 보여준다.

- 현재: fixture context
- 확장: Project 3 HTTP Adapter
- 장애 시: fixture fallback

프로젝트 3은 지식·관계 근거를 보강하고 프로젝트 2는 의사결정·설명·화면을 담당한다고 정리한다.

## 4. 로컬 기록 초기화 — 개발자 전용

사용자 화면에는 초기화 기능을 노출하지 않는다. 발표를 다시 준비해야 할 때만 프로젝트 운영자가 애플리케이션을 종료한 뒤 로컬 명령으로 판단·메모·대화·감사 기록을 비운다.

```bash
python scripts/reset_demo.py
```

확인 질문 없이 실행해야 하는 자동화 환경에서는:

```bash
python scripts/reset_demo.py --yes
```

관리자 페이지가 구현됐지만 reset은 Development Tools에 노출하지 않았다. 이 명령은 판단·메모·대화와 기존 operational audit만 비우며 사용자, password hash, session schema와 관리자 audit는 삭제하지 않는다. 설비 fixture, 모델, Evidence 규칙과 소스 코드도 삭제되지 않는다.

## 5. 데모 핵심 문장

> Ontology Dashboard는 같은 Object, Link와 Evidence를 계정 역할과 workspace scope에 맞는 업무 화면으로 구성하며, 제조 예지보전은 첫 번째 domain pack으로 동작합니다.

## 6. 발표에서 하지 말아야 할 주장

- AI4I 결과가 실제 고객 공장의 성능을 보장한다고 말하지 않는다.
- 예측 고장 유형을 확정된 근본 원인이라고 말하지 않는다.
- 작업 지시나 설비 정지를 시스템이 자동 실행한다고 말하지 않는다.
- synthetic 정지 영향 시간을 실제 ROI로 설명하지 않는다.
