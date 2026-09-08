# Evaluation

Gold 시나리오와 모델·임계값·Evidence·리포트·UI 평가를 관리한다.

## 현재 산출물

- [`gold_scenarios.yml`](./gold_scenarios.yml): Operations가 반드시 통과해야 하는 8개 사용자·안전 시나리오
- [`agent_workflow_task_set.py`](./agent_workflow_task_set.py): Easy 40 / Medium 40 / Adversarial 40으로 고정한 read-only agent task matrix
- [`agent_workflow_benchmark.py`](./agent_workflow_benchmark.py): route/tool/evidence/policy/fallback/latency를 packet-only baseline과 비교하는 실행 harness
- [`results/agent_workflow_benchmark_2026-09-08.json`](./results/agent_workflow_benchmark_2026-09-08.json): 120-task 실제 측정 결과
- `results/`: 단계별 평가 결과 저장 위치

## Read-only agent workflow benchmark

2026-09-08 측정에서는 기존 `agent_tool_trajectory_gold.jsonl`의 세 operational scenario를 질문 난이도와 4개 audience로 확장해 총 120 task를 고정했습니다.

| Metric | Packet-only baseline | Situation-routed candidate |
|---|---:|---:|
| Route accuracy | 0.3000 | **1.0000** |
| Exact tool selection | 0.0000 | **1.0000** |
| Evidence correctness | 1.0000 | **1.0000** |
| Unsupported claim rate | n/a | **0.0000** |
| Role-policy violation rate | 0.0000 | **0.0000** |
| Failure-injection fallback success | n/a | **1.0000 (16/16 tasks)** |
| Candidate p50 local latency | n/a | **1.5557 ms** |

외부 LLM 호출은 routing/tool/evidence boundary를 격리해서 보기 위해 의도적으로 비활성화했습니다. 따라서 이 실험의 external model token usage는 실제 측정값 `0`이지만, production answer-generation cost가 0이라는 뜻은 아닙니다.

## Gold 평가 범위

모델 성능뿐 아니라 다음을 함께 검증한다.

- 기대 위험 등급과 추천 결정
- 개별 예측의 주요 근거
- 수치와 단위의 Evidence 추적성
- 매니저·엔지니어 역할별 정보 우선순위
- 필수 UI 블록과 금지 UI 블록
- 허용 가능한 결론과 금지해야 하는 단정
- 저신뢰·데이터 품질 문제의 안전한 처리
- LLM·Planner 장애 시 결정론적 fallback

## 단계별 추가 예정 파일

- 2단계: Gold JSON fixture와 입력 스키마 검증
- 3단계: 모델 비교·고정 seed 재현성 평가
- 4단계: 임계값·오탐/미탐 비용 평가
- 5단계: Evidence Package 추적성 검사
- 6단계: 규칙 기반 리포트 snapshot
- 7단계: LLM 리포트 사실 일치·역할 적합성 평가
- 8단계: UI Block Planner schema·정책 평가
- 10단계 이후: API 통합·Playwright Gold flow

## 원칙

- 테스트 데이터로 모델이나 임계값을 선택하지 않는다.
- 역할별 표현은 달라도 원본 사실은 동일해야 한다.
- 모든 숫자 문장은 Evidence Package 필드로 추적돼야 한다.
- 확정 근거가 없는 고장 원인과 조치를 단정하지 않는다.
- 외부 LLM 없이도 핵심 Gold 흐름을 검증할 수 있어야 한다.
