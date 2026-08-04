# Project 3 Maintenance Context Adapter Contract

## 1. 목적

> 2026-08-02 architecture update: 이 문서의 flat maintenance-context 계약은 local demo와 backward compatibility를 위한 최소 계약이다. Integrated production target은 `docs/10-product-convergence-polyglot-agentic-roadmap.md`와 ADR-013을 따른다.

프로젝트 2는 프로젝트 3 장애 시 relational 운영 화면과 이미 materialized된 결과를 degraded mode로 제공해야 한다. 그러나 Project 2와 Project 3은 하나의 실제 업무 제품을 두 구현 과제로 나눈 것이며, integrated mode에서 프로젝트 3은 설비·부품 관계, 정비 이력, graph query, LangGraph Text-to-Cypher, 매뉴얼과 유사 사례 RAG를 제공하는 정식 capability provider다.

프로젝트 2는 모델 예측·위험 정책·Dashboard·Ontology/Dataset/Governance Workbench·Evidence·Action·Report·UI 계약을 소유하고, Project 3 capability를 typed client와 multi-store query tool로 사용한다.

## 2. Provider 인터페이스

```python
class MaintenanceContextProvider:
    provider_name: str

    def get_context(
        self,
        equipment_id: str,
        failure_type: str,
    ) -> dict:
        ...
```

현재 compatibility 구현:

- `FixtureContextProvider`: 로컬 합성 SOP context
- `Project3HttpContextProvider`: 프로젝트 3 flat maintenance context API
- `ResilientContextProvider`: 프로젝트 3 실패 시 fixture fallback

Target integrated client:

- health/readiness
- `/api/v1/query`
- `/api/v1/rag/search`와 `/api/v1/rag/query`
- `/api/v1/graph/schema`
- `/api/v1/graph/search`
- `/api/v1/graph/subgraph`
- agent run inspect/resume

새 기능은 flat context payload를 확장하는 대신 versioned typed contract로 추가한다.

## 3. HTTP 요청 계약

```http
GET {PROJECT3_API_URL}/api/maintenance-context
    ?equipment_id=M-014
    &failure_type=tool_wear_failure
```

허용되는 `failure_type` 예시:

- `none`
- `tool_wear_failure`
- `heat_dissipation_failure`
- `power_or_overstrain_failure`
- `multi_factor_risk`
- `uncertain`

## 4. 최소 응답 계약

```json
{
  "version": "project3-context-v1",
  "source_type": "project3_evidence",
  "source_refs": [
    "manual:press-maintenance-v2#section-4.2",
    "graph:path:equipment-M-014-to-part-TOOL-22"
  ],
  "checklist": [
    "공구 날끝 마모 상태 확인",
    "토크 센서와 실제 가공 부하 교차 확인"
  ],
  "recommended_actions": [
    "다음 교대 전 현장 점검",
    "점검 결과를 매니저에게 보고"
  ]
}
```

필수 필드:

- `version`
- `source_refs`
- `checklist`
- `recommended_actions`

`source_type`은 없으면 `project3_evidence`로 처리한다.

## 5. 출처와 사실성 경계

- 프로젝트 3 응답은 유지보수 지식과 관계 근거이다.
- 프로젝트 3이 프로젝트 2의 확률, 위험 등급 또는 권장 결정을 덮어쓰면 안 된다.
- Graph 경로 또는 문서 근거는 `source_refs`로 남긴다.
- 검색된 체크리스트를 이미 수행된 작업으로 표현하면 안 된다.
- 유사 사례는 현재 사건의 확정 원인으로 승격하지 않는다.

## 6. 장애 처리

프로젝트 3 URL 미설정, timeout, HTTP 오류, JSON 오류 또는 필수 필드 누락 시:

1. `FixtureContextProvider`로 즉시 fallback한다.
2. Evidence의 `maintenance_context.provider`는 `fixture_fallback`이 된다.
3. version에 fallback 원인 타입을 기록한다.
4. 모델·리포트·화면 흐름은 중단하지 않는다.
5. 외부 서비스의 상세 오류나 자격 증명은 사용자 화면에 노출하지 않는다.

## 7. 호환성 규칙

Provider가 바뀌어도 다음 스키마는 변경하지 않는다.

- `schemas/evidence-package.schema.json`
- `schemas/report.schema.json`
- `schemas/ui-block.schema.json`

Context가 늘어나더라도 기존 필드를 제거하지 않고 새 계약 버전을 도입한다.

## 8. 검증

`tests/test_mvp.py::test_project3_context_failure_falls_back`는 연결 실패 시 fixture fallback과 source reference 보존을 검증한다.
