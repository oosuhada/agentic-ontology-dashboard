# Gold Fixtures

작고 결정론적인 발표·테스트 입력만 추적한다.

## 1단계 상태

8개 Gold fixture의 ID와 예정 경로가 `evaluation/gold_scenarios.yml`에 확정됐다. 실제 JSON 값은 2단계에서 AI4I 데이터 사전과 입력 스키마를 확정한 뒤 생성한다.

예정 파일:

```text
GS-001-normal-stable.json
GS-002-tool-wear-warning.json
GS-003-heat-dissipation-warning.json
GS-004-power-overstrain-critical.json
GS-005-multi-factor-warning.json
GS-006-low-confidence.json
GS-007-invalid-sensor-data.json
GS-008-llm-offline.json
```

각 fixture는 다음 정보를 포함해야 한다.

- Gold 시나리오 ID
- 설비 ID와 표시명
- 생산 라인과 설비 중요도
- 입력 센서 값과 단위
- 관측 시간 또는 시계열 구간
- 데이터 품질 플래그
- 기대 위험 등급
- 기대 주요 근거
- 사용자 역할별 기대 행동

## 원칙

- 실제 고객 데이터나 식별 가능한 공장 데이터는 저장하지 않는다.
- 같은 fixture를 매니저·엔지니어 화면에서 공유한다.
- 역할별 표현은 달라도 모델 입력과 Evidence 원본은 동일하다.
- GS-007 이외의 fixture는 입력 스키마와 물리 범위를 만족해야 한다.
- GS-007은 데이터 품질 검증 실패를 의도적으로 재현한다.
- GS-008은 센서 사건은 유효하지만 LLM·Planner 공급자만 비활성화한다.
