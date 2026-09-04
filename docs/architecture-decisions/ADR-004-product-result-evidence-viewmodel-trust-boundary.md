# ADR-004: Product Result / Evidence / ViewModel 신뢰 경계

- **상태**: Proposed (제안)
- **날짜**: 2026-08-29
- **결정자**: 팀 확인 필요
- **관련 문서**:
  - [`ADR-003-generator-runtime-prediction-result-and-backend-decision-ownership.md`](./ADR-003-generator-runtime-prediction-result-and-backend-decision-ownership.md)
  - [`../plans/ai-workflow/2026-08-29-002-product-result-evidence-materialization-plan.md`](../plans/ai-workflow/2026-08-29-002-product-result-evidence-materialization-plan.md)
  - [`../plans/ai-workflow/2026-08-29-003-evidence-snapshot-consistency-guard-plan.md`](../plans/ai-workflow/2026-08-29-003-evidence-snapshot-consistency-guard-plan.md)

---

## 1. 맥락 (Context)

ADR-003은 Generator가 runtime prediction batch를 만들고, Backend가 Product Result / Evidence /
Report / 사용자 알림 같은 product-facing 판단을 소유한다고 결정했다. 후속으로 필요한 것은 raw
prediction이 Backend에 도착한 뒤 화면과 Closed-loop가 어떤 신뢰 경계를 통해 소비하는지 명시하는
것이다.

AI Solutions Engineer / AI Data Integration / MLOps 계열 JD는 데이터 파이프라인, API 통합, 운영화,
모니터링, 비기술 이해관계자 커뮤니케이션을 반복해서 요구한다. 이 요구를 현재 프로젝트에 적용할 때
핵심은 대규모 DB 플랫폼 재설계가 아니라, AI 예측 결과가 업무 화면에서 신뢰 가능한 판단 근거로
쓰이도록 검증/승격/소비 경계를 고정하는 것이다.

---

## 2. 의사결정 (Decision)

Backend는 Generator raw 산출물을 UI, Report, Closed-loop, Agent Review에 직접 노출하지 않는다.
AI 결과는 다음 경계를 통과한 뒤 product-facing 소비자별 projection으로 분기된다.

```text
Generator raw 산출
  -> Backend Diagnosis validation / promotion
  -> Product Result Artifact
      -> Evidence Projection / Evidence Package -> Report
      -> AssetDetailViewModel -> UI
      -> Closed-loop Recommendation Input
      -> Agent Review Packet -> Agent Review Summary Materialization -> UI / Report
```

세부 결정은 다음과 같다.

1. **Raw prediction과 Product Result 분리**
   - Generator batch, raw score, raw JSONL은 화면과 Closed-loop의 직접 입력이 아니다.
   - Backend Diagnosis가 schema, scope, checksum, lineage, model/dataset version을 검증한 뒤
     Product Result Artifact로 승격한다.

2. **Product Result와 Evidence의 shared lineage 보존**
   - Product Result Artifact는 `failure_probability`, `status_grade`, `top_factors`,
     `recommended_action` 같은 product-facing 판단을 소유한다.
   - Evidence Projection은 Product Result Artifact에서 파생되며 `artifact_reference`,
     `assessment`, `report_projection`, `provenance`, `limitations`를 보존한다.
   - `evaluation_truth`와 `hidden_truth`는 dashboard/API/LLM/Evidence 입력으로 사용하지 않는다.

3. **ViewModel은 read model composer로 유지**
   - `AssetDetailViewModel`은 저장 이벤트를 듣는 materialized table이 아니라 화면용 composer다.
   - UI는 raw payload를 직접 조합하지 않고 Backend가 구성한 typed ViewModel을 소비한다.
   - Report는 ViewModel 표현을 일부 재사용할 수 있지만, provenance와 limitations는 Evidence 경계에서
     보존한다.
   - Closed-loop Recommendation Input은 ViewModel을 직접 소비하지 않고, 동일 Product Result/Evidence
     snapshot에서 별도 projection으로 구성한다.
   - 결측 또는 미연결 근거는 `null`, `gap`, `warning`, `근거 부족`으로 표현하고 정상값으로 보정하지
     않는다.

4. **Snapshot 일관성은 별도 guard로 검증**
   - UI ViewModel, Report, Closed-loop Recommendation Input, Agent Review Packet은 부모-자식 관계가
     아니라 같은 Product Result/Evidence에서 파생되는 sibling projection이다.
   - 현재 Closed-loop는 서버에서 Evidence Projection을 조회해 caller-supplied lineage를 신뢰하지 않는다.
   - `AssetDetailViewModel`과 `AgentReviewPacket`은 같은 Product Result/Evidence 기준을 비교할 수
     있도록 `snapshot_basis`를 노출한다.
   - 다만 caller가 본 `snapshot_basis`와 Closed-loop mutation 시점에 조회한 Evidence Projection의
     동일성을 비교하는 guard는 별도 구현 단위로 남긴다.

5. **Transactional outbox는 후속 처리 요구가 있을 때만 적용**
   - Product Result / Evidence 저장 원자성이 필요한 경우 Backend repository transaction으로 묶는다.
   - 검색 인덱스, 집계, report cache invalidation, audit projection 같은 후속 소비자가 생기면
     `diagnosis.product_result.materialized` outbox event를 별도 PR로 추가한다.
   - exactly-once delivery는 주장하지 않는다. outbox는 at-least-once를 전제로 consumer idempotency가
     필요하다.

6. **Agent Review Summary는 UI 클릭이 아니라 watcher diff로 materialize**
   - UI 사이드뷰 열림, 탭 전환, refresh 같은 presentation event는 LLM 호출 트리거가 아니다.
   - Backend watcher는 Product Result/Evidence snapshot의 lineage, `source_sha256`, prompt/schema/model
     version diff를 감지해 `Agent Review Packet`을 재구성하고, 필요한 경우에만 `Agent Review Summary`를
     생성한다.
   - Summary는 `summary_key = asset_id + event_id + dataset_version_id + snapshot_basis/source_sha256
     + prompt_version + summary_schema_version + model_version` 같은 멱등 키로 저장한다.
   - 같은 `summary_key`가 이미 있으면 UI와 Report는 저장된 Summary를 재사용한다. snapshot 또는
     prompt/schema/model version이 달라진 경우에만 새 Summary 후보를 만든다.
   - LLM 후보는 저장 전에 validation을 통과해야 하며, 실패하거나 provider가 없으면 deterministic
     fallback Summary를 같은 저장 계약으로 남긴다.
   - Closed-loop는 Summary 문장을 추천/승인/상태 전이 입력으로 사용하지 않는다. 필요한 경우
     `summary_id`는 사용자가 본 설명의 감사 참조로만 연결하고, 실제 mutation guard는 동일
     `snapshot_basis` 비교로 수행한다.

7. **Agent Review Packet은 도메인별로 섹션화하되 public ViewModel은 아직 물리 분리하지 않는다**
   - 현재 AI 요약에 필요한 도메인은 위험 판단, 운영 영향, 정비/Closed-loop 이력, 점검 위치, SOP,
     ontology 관계, read-only 권한 경계다.
   - 이 도메인들은 하나의 `Agent Review Packet` 안에서 `domain_sections` lineage로 구분한다. 각 섹션은
     `owner_domain`, `source`, `packet_paths`, `mutation_allowed=false`를 가진다.
   - 별도 `OperationReviewViewModel`, `MaintenanceReviewViewModel`, `SopReviewViewModel` API를 지금 만들지
     않는다. 현재 소비자는 같은 snapshot의 조합 결과를 한 번에 읽는 UI/Report/AI summary이며, 물리 분리는
     API 호출 수, cache invalidation, snapshot mismatch, 테스트 fixture 폭발을 먼저 키운다.
   - 도메인별 데이터가 독립 저장소, 독립 권한, 독립 freshness, 독립 retry 정책을 갖기 전까지는
     `ContextProvider`/adapter가 도메인 사실을 모으고, packet composer가 LLM 노출면을 정규화한다.
   - 물리 분리 승격 기준은 명확히 둔다. SOP가 PDF/RAG source로 독립 조회되거나, MES/CMMS/ERP 같은 운영
     도메인이 별도 DB/source freshness를 갖거나, Closed-loop mutation guard가 특정 도메인 snapshot을
     독립 비교해야 하거나, tool trajectory eval에서 도메인 툴 선택/재시도가 release gate가 되는 경우다.

---

## 3. 명명 계약 (Naming Contract)

이 ADR에서 사용하는 이름은 구현 계층과 신뢰 수준을 구분하기 위한 계약이다. 같은 데이터를 가리키더라도
경계를 통과하기 전후의 이름을 섞어 쓰지 않는다.

| 이름 | 의미 | 사용 위치 | 피해야 할 표현 |
| --- | --- | --- | --- |
| `Prediction Result Batch` | Generator가 만든 raw 예측 산출 묶음. schema/checksum/lineage 검증 전 입력이다. | Generator, Backend Inbox | Product Result, Evidence |
| `Product Result Artifact` | Backend Diagnosis가 검증/승격한 product-facing 판단 산출물. 화면/Closed-loop/AI가 신뢰할 수 있는 최소 판단 단위다. | Backend Diagnosis, repository, downstream read paths | raw result, model output |
| `Evidence Projection` | Product Result Artifact에서 파생한 근거 중심 canonical projection. 판단값, provenance, limitations를 보존한다. | Backend API, report/evidence contracts | UI state, report text |
| `Evidence Package` | 기존 report/legacy consumer 호환을 위한 evidence 형태. 신규 경계 설명에서는 Evidence Projection을 우선 이름으로 쓴다. | legacy report/tests | Product Result 원본 |
| `AssetDetailViewModel` | UI가 소비하는 화면용 read model composer 결과. 저장된 product result 자체가 아니다. | Operations API, frontend | materialized product result |
| `Recommendation Input` | Closed-loop 정책/상태 전이 후보가 소비하는 decision용 projection. ViewModel 표시값이 아니라 Product Result/Evidence lineage에서 파생한다. | Closed-loop service | UI state, Agent Review Summary |
| `Agent Review Packet` | AI 요약이 읽는 read-only 패킷. Product Result/Evidence/ViewModel/SOP/context를 조합하지만 mutation 권한은 없다. | AI summary provider, eval fixtures | agent decision, approval request |
| `Domain Section` | Agent Review Packet 안에서 도메인별 출처, packet path, read-only 경계를 설명하는 lineage 항목. 물리 API 분리가 아니라 조립 경계 표시다. | Agent Review Packet, tool/eval traces | separate ViewModel, domain source of truth |
| `Agent Review Summary` | Agent Review Packet을 근거로 만든 역할별 설명 문장. 사용자 판단 보조용이며 Closed-loop 명령이 아니다. | UI, summary API | recommendation decision, approval |
| `Agent Review Summary Materialization` | watcher가 snapshot diff를 감지해 생성/검증/저장한 Summary 산출물. 같은 근거와 버전에서는 재사용된다. | Backend watcher, summary repository, UI/Report read API | UI click-triggered LLM call |

### 적용 규칙

1. `Product Result`는 Backend가 승격한 판단 artifact에만 사용한다. Generator 출력에는 사용하지 않는다.
2. `Evidence`는 판단 근거와 provenance를 보존하는 projection/package에만 사용한다. 단순 화면 문구나 LLM 응답을 Evidence라고 부르지 않는다.
3. `ViewModel`은 화면 조합 결과다. 저장 원자성, outbox, retry 논의에서는 Product Result/Evidence와 구분한다.
4. `Recommendation Input`은 ViewModel의 하위 산출물이 아니라 Product Result/Evidence의 형제 projection이다.
5. `Agent Review`는 read-only human-review support다. Closed-loop의 승인, 상태 전이, 작업 지시를 대신하지 않는다.
6. `Materialization`은 저장/조회 가능한 산출물 생성에만 사용한다. 현재 composer-only 경로에는 붙이지 않는다.
7. `Agent Review Summary Materialization`은 Product Result/Evidence snapshot 변화 또는 prompt/schema/model
   version 변화에 의해 갱신된다. UI 탭 진입이나 사이드뷰 클릭은 조회 이벤트일 뿐 생성 이벤트가 아니다.
8. `Domain Section`은 packet 내부 lineage 용어다. 도메인 데이터가 독립 저장소/API로 승격되기 전에는
   public ViewModel 분리를 의미하지 않는다.

---

## 4. JD 대응 관점의 적용

| JD 요구 | 프로젝트 적용 | 제한 범위 |
| --- | --- | --- |
| Data Pipeline | raw 산출물을 검증 후 Product Result/Evidence로 승격 | 범용 ETL/ingestion framework 구축 제외 |
| API Integration | UI는 `AssetDetailViewModel` API를 소비하고 Closed-loop는 Product Result/Evidence 기준으로 진입 | Frontend raw payload 조합 금지 |
| MLOps / LLMOps | `model_version`, `dataset_version`, `source_sha256`, evidence reference로 판단 lineage 추적 | 모델 학습/배포 플랫폼 재구축 제외 |
| Operational Monitoring | `validation_status`, `rejection_reason`, `data_status`, `evidence.gaps`로 상태 표시 | full observability stack 제외 |
| Stakeholder Communication | 확률/feature를 위험도, 확인 이유, 권장 조치, 근거 부족으로 화면 언어화 | 내부 DB/outbox 용어의 사용자 노출 최소화 |
| AI Workflow | watcher가 evidence diff 기반으로 요약 산출물을 생성/검증/저장하고 UI/Report는 저장본을 소비 | UI event 기반 반복 LLM 호출 제외 |

---

## 5. 결과 및 영향 (Consequences)

- AI 예측값이 곧바로 사용자 판단값이 되는 경로를 차단한다.
- Backend Diagnosis가 product-facing 판단과 Evidence lineage의 소유자로 남는다.
- UI는 raw Generator 산출물 대신 `AssetDetailViewModel`을 소비하므로 화면 문구와 근거 표시를 더
  일관되게 유지할 수 있다.
- Agent Review Summary는 같은 snapshot에서 재사용되므로 사용자 클릭마다 LLM을 반복 호출하지 않고,
  비용, 응답 변동성, 감사 추적 리스크를 줄인다.
- Closed-loop mutation은 raw score가 아니라 Product Result / Evidence / RecommendationDecision
  기반으로 진입한다.
- Closed-loop는 ViewModel 표시값을 mutation 입력으로 쓰지 않지만, 사용자가 본 snapshot과 mutation
  시점 snapshot의 일치 여부는 별도 guard 없이는 완전히 증명할 수 없다.
- DB/outbox/idempotency 세부는 면접 또는 설계 리뷰에서 심화 근거로 사용할 수 있지만, 기본
  포지셔닝은 “AI 결과를 업무 화면에 신뢰 가능하게 연결한 통합 설계”로 제한한다.

---

## 6. 한계와 후속 확인

- 이 ADR은 제안 상태다. 구현 완료, 테스트, 배포, 운영 검증을 의미하지 않는다.
- Product Result / Evidence 저장 원자성은 후속 repository 구현과 rollback 테스트가 필요하다.
- ViewModel은 여러 read source를 조합하므로 완전한 동일 시점 snapshot 보장은 후속 `as_of` 또는
  Closed-loop `snapshot_basis` guard 정책이 필요하다.
- Agent Review Summary materialization은 SQLite/PostgreSQL schema, summary repository, workflow run
  trace, watcher retry, stale running-run recovery, validation/fallback 저장 계약, UI status 표시,
  persona별 read/materialize 권한, MVP browser e2e로 검증했다. PostgreSQL 서버 replay/integration
  경로도 로컬 Docker PostgreSQL에서 migration을 적용해 검증했다.
- Outbox 기반 후속 projection은 실제 consumer가 생긴 뒤 별도 PR에서 다룬다.
- 외부 JD 레퍼런스는 역할 요구를 해석하기 위한 참고이며, 프로젝트 구현 완료 증거가 아니다.
