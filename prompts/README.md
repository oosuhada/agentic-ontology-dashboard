# Prompts

- `manager-report.md`: 판단·영향·담당 행동 우선
- `engineer-report.md`: 센서·구간·단위·점검 근거 우선
- `ui-planner.md`: 등록된 UI Block 선택과 순서만 허용

프롬프트는 Evidence Package 밖의 숫자·원인·완료 행동을 만들 수 없다. Provider 호출·파싱·스키마·grounding 검사가 실패하면 프롬프트 결과를 사용하지 않고 deterministic report/layout으로 전환한다.
