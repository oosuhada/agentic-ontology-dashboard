# Schemas

모든 계층의 공통 계약을 JSON Schema Draft 2020-12로 관리한다.

- `input-event.schema.json`: Gold event와 runtime switches
- `evidence-package.schema.json`: 모델·정책·근거·context·lineage
- `report.schema.json`: 역할별 grounded report와 human-approved action
- `ui-block.schema.json`: 허용 블록, 순서, data field

스키마를 변경할 때는 fixture, Pydantic model, backend tests, Gold evaluator와 React type을 함께 변경해야 한다. LLM 출력은 스키마와 grounding 검사를 모두 통과하지 못하면 폐기하고 deterministic fallback을 사용한다.
