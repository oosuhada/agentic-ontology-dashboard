# Palantir UI 격차 검증 및 개선 계획 (2차)

- 작성일: 2026-08-02 (1차 문서 `palantir-ui-gap-verification-and-plan.md` 이후 재검증)
- 방식: 이전 문서에서 "미검증"으로 남긴 항목 위주로 실제 소스를 다시 열어 확인. 이번에도 "파일이 있다"가 아니라 "실제로 동작한다" 기준.
- 결론 먼저: **1차 문서의 P0 4개, P1(Agent Evidence UI) 전부 실제로 구현되어 있는 것을 확인했다.** 이번 문서는 남은 격차와 이번에 새로 드러난 두 가지 확인 필요 항목을 정리한다.
- 실행 결과(2026-08-02): 미사용 `langgraph`/local vector Python adapter 의존성을 제거했고, Project 2 local pgvector를 인프라·projection schema 경계로 재확정했다. Dashboard cross-filter는 server-query board와 client-filter legacy board가 공존하는 hybrid 구조로 확인했으며, Analysis Result Inspector의 고정 Lineage 목록은 실제 upstream DAG mini graph로 교체했다. Dashboard Audit Trace의 Agent Evidence drill-down은 이미 구현돼 있어 유지했다.

---

## 1. 1차 계획 대비 검증 결과

| 1차 문서에서 지정한 항목 | 이번 확인 결과 |
|---|---|
| Join 화이트리스트 서버 강제 | ✅ 확인됨. `factory_signal_board/analysis_service.py`에 `ALLOWED_JOIN_RELATIONSHIPS`가 정확히 3개 관계(RiskEvent↔Equipment, RiskEvent↔Evidence, Equipment↔WorkOrder)로 고정돼 있고, 정의 저장 시점(`_validate_definition`)과 실행 시점(`_join_rows`) 양쪽에서 이중으로 검증함 |
| DAG 순환 검사 | ✅ 확인됨. `_topological_order`가 Kahn 알고리즘으로 위상 정렬하고, 정렬된 노드 수가 전체 노드 수와 다르면 `"analysis graph must be acyclic"`을 던짐. 생성/수정/실행 세 지점 모두에서 호출됨 |
| Result Inspector 서버 계산 여부 | ✅ 서버 계산 확인됨. `_profile()`/`_quality_summary()`가 null_rate, distinct_count, duplicate_key_count를 계산하고 응답에 `"computed_by": "server"`를 명시적으로 표기. 프론트 `AnalysisResultInspector.tsx`가 이 값을 그대로 렌더링하며, 서버 실행 결과가 없을 때만 클라이언트 추정치로 fallback (그리고 "server run" / "client preview" 배지로 구분 표시) |
| 비결정성/timezone 경고 배지 | ✅ 확인됨. 서버가 `warnings: []`(현재 시각 의존, Group 정렬 미보장 등)와 `timezone: "UTC"`를 응답에 포함하고, `AnalysisResultInspector.tsx`가 `<AlertTriangle>` 아이콘과 함께 렌더링. 클라이언트 측 경고(`clientWarnings`)와 서버 경고를 합쳐서 표시 |
| Agent Evidence UI (P1) | ✅ 확인됨. `web/src/features/agent/`에 `AgentWorkbenchPage.tsx`, `AgentQueryBoard.tsx`, `EvidenceTraceList.tsx`, `GroundedClaimList.tsx`, `OrchestrationStepper.tsx` 전부 존재. `routing.ts`에 `agentPath`/`matchAgentPath` 추가, `App.tsx`에 `planner.object_query` 권한 스코프로 lazy route 연결까지 확인 |

이 정도면 1차 문서를 실제로 반영한 게 맞다. 다음 항목으로 넘어가면 된다.

---

## 2. 이번에 새로 확인된 것: 시각 디자인이 생각보다 이미 진행돼 있다

1차 문서에서 "4개 분석 문서 어디에도 시각 디자인이 없다"고 지적했는데, 이번에 `styles.css` 상단을 다시 열어보니 실제로 토큰 시스템이 있다.

```css
--od-accent: #2d72d2;        /* Blueprint blue3 — Palantir 계열 제품이 쓰는 바로 그 파랑 */
--od-density-row: 30px;      /* 정보 밀도 토큰 */
--od-radius-panel: 6px;
[data-theme="dark"] { ... }  /* 다크 테마 토큰 세트 별도 존재 */
```

그리고 `AgentWorkbenchPage.tsx`가 `@blueprintjs/core`(Button, Callout, Card, HTMLSelect, InputGroup, Spinner, Tag)를 직접 사용하고 있다. Blueprint는 Palantir가 자체 공개한 컴포넌트 라이브러리이므로, 최소한 컴포넌트 레벨에서는 "팔란티어와 같은 시각 언어"를 이미 쓰고 있는 셈이다.

→ 1차 문서의 "P2 시각 디자인 트랙"은 "0에서 시작"이 아니라 "이미 있는 토큰·Blueprint 채택을 전 화면에 일관되게 적용했는지 감사"로 범위를 좁혀야 한다. 아래 4장에서 재정의한다.

다만 이건 코드에서 토큰 값과 라이브러리 사용을 확인한 것이지, 실제 렌더링 화면을 본 것은 아니다. 밀도·정렬·여백이 화면마다 실제로 일관되게 적용됐는지는 스크린샷 없이는 확정할 수 없다.

---

## 3. 이번에 새로 발견된 확인 필요 항목

### 3.1 `langgraph` 의존성은 선언만 되고 실제 사용되지 않았다 — 정리 완료

`api/pyproject.toml`의 `polyglot`/`production` extras에 다음이 있다.

```toml
langgraph>=0.2
langgraph-checkpoint-postgres>=2
```

그런데 실제 오케스트레이션 코드를 확인한 결과:
- `orchestration/orchestrator.py` — `langgraph` import 없음. `route → collect → merge_evidence → validate_claims`를 직접 순차 호출
- `orchestration/repository.py` — `langgraph` import 없음. `sqlite3`/`postgresql` 직접 사용해 체크포인트 저장
- `planner/service.py` — `langgraph` import 없음. 규칙 기반 typed intent 생성

전체 `api/`와 `web/src/`를 재검색한 결과 `langgraph`와 `langgraph-checkpoint-postgres`는 `api/pyproject.toml` 외 실제 import·호출이 없었다. 현재 직접 구현한 typed state/checkpoint/trace가 제품 요구사항을 충족하므로 두 패키지를 `polyglot`/`production` extras에서 제거했다. 설치 시간과 공급망·공격 표면을 줄이고, 향후 실제 LangGraph runtime을 도입할 때 명시적인 ADR과 contract test를 동반해 다시 추가한다.

### 3.2 Project 2 local pgvector는 runtime RAG 소비처가 없다 — 경계 확정 및 의존성 정리 완료

`orchestration/ports.py`의 `Project3VectorPort`는 `Project3Client.rag_search()`를 호출한다 — 즉 벡터 검색은 Project 3 쪽 pgvector를 쓴다. `polyglot/health.py`는 Project 2 자체 DB에 대해 `pg_extension WHERE extname = 'vector'`를 체크하는데, Project 2 자체 pgvector에 뭔가를 넣고 검색하는 코드는 이번에도 찾지 못했다. `pyproject.toml`에 `llama-index-vector-stores-postgres`가 있는 걸 보면 Project 2 자체 RAG를 준비하려는 의도는 있어 보이지만, 아직 연결된 라우터/서비스를 확인하지 못했다.

`routers/`, `datasets/`, `orchestration/`, `planner/`를 재검색했지만 Project 2 local pgvector writer/search 또는 LlamaIndex PGVectorStore 소비처는 없었다. runtime semantic retrieval은 계속 `Project3Client.rag_search()` typed HTTP 경계만 사용한다. 따라서 `pgvector` Python package와 `llama-index-vector-stores-postgres`도 extras에서 제거했다. PostgreSQL의 `vector` extension·migration·projection target은 인프라 경계로 유지하되, writer와 role/project-filtered search port가 구현되기 전까지 Project 2 자체 RAG로 홍보하지 않는다.

---

## 4. 남은 격차 (재정리)

| 항목 | 상태 |
|---|---|
| Analysis Path 서버 실행/검증/품질 지표 | 완료 |
| Agent Evidence UI + 라우팅 | 완료 |
| Blueprint 컴포넌트 + 디자인 토큰 채택 | 진행됨. Dashboard·Analysis·Agent·Governance·Datasets를 동일한 1440×1000 light-theme viewport로 캡처했고 review manifest를 추가했다. |
| Dashboard cross-filter engine | Hybrid 확인. `EventDataGrid`와 catalog-backed board는 selection filter를 서버 API로 재쿼리하고, 일부 legacy/fixed renderer는 전달받은 EventSummary 배열을 client-side로 필터링한다. 서버 우선 renderer와 fallback 경계를 UI·문서에 명시하고 legacy 전면 전환은 별도 단계로 남긴다. |
| Analysis Result Inspector의 "Lineage" 섹션 | 완료. 선택 node의 실제 upstream nodes/edges를 React Flow read-only mini graph로 렌더링하고 선택 node, model version, Analysis revision을 함께 표시한다. |
| langgraph 의존성 실사용 여부 | 미사용 확인 및 dependency 제거 완료 |
| Project 2 자체 pgvector 소비처 | runtime 소비처 없음 확인. infrastructure/projection schema only 경계 유지, 미사용 Python adapter dependency 제거 완료 |
| 화면 실제 렌더링 품질(밀도·정렬·타이포 일관성) | 5개 화면 자동 캡처 및 route/render E2E 완료. PNG는 `docs/ui/screenshots/palantir-gap-v2/`에 있으며 공식 이미지 대응표도 함께 저장했다. 최종 시각적 선호 판단은 해당 PNG의 human side-by-side review 항목으로 남긴다. |

---

## 5. 다음 우선순위

### P0 — 완료
1. `langgraph`/checkpoint package 미사용 확인 후 dependency 제거
2. Project 2 local pgvector runtime 소비처 부재 확인, infrastructure/projection schema only 경계와 Project 3 typed RAG 경계 문서화, 미사용 Python vector adapter dependency 제거
3. Dashboard cross-filter를 hybrid 구조로 재확인: server-query board와 client-filter legacy board를 구분

### P1 — 완료
1. Analysis Result Inspector Lineage를 실제 upstream DAG React Flow mini graph로 교체
2. Dashboard `AuditTrace` renderer의 `agentPath(...)` drill-down 구현 확인 및 유지

### P2 — 캡처 완료, 시각 검토 artifact 준비
1. Playwright 고정 viewport(1440×1000, light theme)로 Dashboard, Analysis Path, Agent Workbench, Governance, Datasets 5개 PNG를 생성했다.
2. `docs/ui/screenshots/palantir-gap-v2/README.md`에 각 화면과 `palantir-contour-ui-reference.md` 공식 이미지의 대응표를 기록했다.
3. E2E는 각 route의 primary workbench와 Analysis upstream DAG mini graph 렌더링을 검증한다. 밀도·여백·색 대비의 최종 선호 평가는 저장된 PNG를 공식 이미지와 나란히 보는 human review로 남긴다.

---

## 6. 메모

이번 실행부터 `docs/ui/screenshots/palantir-gap-v2/`에 고정 viewport 캡처와 공식 레퍼런스 대응표를 함께 저장했다. 다음 stage 요약 문서도 동일하게 screenshot manifest와 검증 명령을 먼저 제시한다.
