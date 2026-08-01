# Factory Signal Board Demo Runbook

## 1. 시작

```bash
cd "/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2"
cp .env.example .env
bash scripts/run_local.sh
```

기본 주소:

- Web: `http://127.0.0.1:3100`
- API docs: `http://127.0.0.1:8100/docs`

API 키 없이도 모든 핵심 데모가 deterministic fallback으로 동작한다.

## 2. 발표 전 검증

```bash
source .venv/bin/activate
PYTHONPATH=api:ml/src python scripts/release_gate.py --with-e2e
```

결과 마지막에 `"pass": true`가 있어야 한다.

## 3. 권장 발표 순서

### 장면 1 — 제품 목적

1. 매니저 역할로 시작한다.
2. 위험 우선순위 목록과 현재 선택 설비를 보여준다.
3. “모델 점수를 보여주는 대시보드가 아니라 역할별 의사결정을 돕는 화면”이라고 설명한다.

### 장면 2 — 공구 마모 사건 GS-002

1. 사이드바에서 `GS-002`를 선택한다.
2. `StatusSummary`, 위험도, 예상 정지 영향, 권장 결정 순서를 보여준다.
3. `현장 점검 요청`을 선택하고 메모를 기록한다.
4. 기술 차트가 첫 정보가 아니라 필요 시 내려가는 근거임을 강조한다.

### 장면 3 — 같은 사건의 엔지니어 화면

1. 역할을 엔지니어로 전환한다.
2. 첫 블록이 `SensorLineChart`로 바뀌는 것을 보여준다.
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

### 장면 6 — 프로젝트 3 확장

`ModelDetails`에서 Context provider/version을 보여준다.

- 현재: fixture context
- 확장: Project 3 HTTP Adapter
- 장애 시: fixture fallback

프로젝트 3은 지식·관계 근거를 보강하고 프로젝트 2는 의사결정·설명·화면을 담당한다고 정리한다.

## 4. 발표 상태 초기화

UI 왼쪽 하단 `발표 상태 초기화`를 누르거나:

```bash
python scripts/reset_demo.py
```

## 5. 데모 핵심 문장

> 동일한 설비 사건을 매니저에게는 결정과 영향 중심으로, 엔지니어에게는 센서와 점검 근거 중심으로 보여주며, 모든 자연어와 UI 블록은 추적 가능한 Evidence Package에서 생성됩니다.

## 6. 발표에서 하지 말아야 할 주장

- AI4I 결과가 실제 고객 공장의 성능을 보장한다고 말하지 않는다.
- 예측 고장 유형을 확정된 근본 원인이라고 말하지 않는다.
- 작업 지시나 설비 정지를 시스템이 자동 실행한다고 말하지 않는다.
- synthetic 정지 영향 시간을 실제 ROI로 설명하지 않는다.
