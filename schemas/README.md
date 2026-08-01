# Schemas

모든 계층의 공통 계약을 JSON Schema Draft 2020-12로 관리한다.

- `input-event.schema.json`: Gold event와 runtime switches
- `evidence-package.schema.json`: 모델·정책·근거·context·lineage
- `report.schema.json`: 역할별 grounded report와 human-approved action
- `ui-block.schema.json`: 허용 블록, 순서, data field
- `ontology-core.schema.json`: domain-neutral Object, Link, Action invocation·execution result, traversal, Evidence reference
- `dashboard-platform.schema.json`: resolved Dashboard, tab, board, preference save, dependency graph와 share payload
- `role-workspaces.schema.json`: Executive·Audit·Field·FDE·Model workspace와 approval request 응답
- `ontology-planner.schema.json`: typed Object query, Board recommendation, Dashboard draft와 grounded narrative 응답
- `export.schema.json`: organization/project/workspace 범위의 export request, snapshot과 checkpoint 계약
- `dataset-manifest.schema.json`: Project별 dataset source, checksum, schema alias와 quality rule 계약
- `prediction-result.schema.json`: Prediction Module과 Dashboard 사이의 Evidence·Model·Action 포함 결과 계약

스키마를 변경할 때는 fixture, Pydantic model, backend tests, Gold evaluator와 TypeScript type을 함께 변경해야 한다. LLM 출력은 스키마와 grounding 검사를 모두 통과하지 못하면 폐기하고 deterministic fallback을 사용한다.
