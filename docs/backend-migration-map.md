# Backend Domain-First Migration Map

이 문서는 `systems/backend/ontology_dashboard`를 `systems/backend/app`으로 수렴할 때
사용하는 **처분 원장(Migration Ledger)** 이다. Source가 현재 import되거나 테스트된다는
사실만으로 제품 필수 기능 또는 자동 이관 대상으로 판단하지 않는다.

## 1. 처분 상태

| 상태 | 의미 |
|---|---|
| `MOVE` | 책임과 구현을 하나의 목표 도메인 또는 Infra로 이관 |
| `SPLIT` | 한 Source의 책임을 둘 이상의 소유자에게 분해한 뒤 레거시 삭제 |
| `REPLACE` | 새 canonical 구현 또는 명시적 bootstrap으로 대체한 뒤 레거시 삭제 |
| `REMOVE` | 승인된 제품 범위가 아니므로 API·테스트 종료 기준을 확인하고 삭제 |
| `DEFER` | 제품 범위 결정 전에는 이관하지 않음. Phase 0.5(#68) 완료 전 반드시 다른 상태로 해소 |

모든 레거시 Python Source는 아래 Ledger의 정확히 하나의 행에 포함되어야 한다.
`UNDECIDED`, 미배정 Source 또는 해소되지 않은 `DEFER`가 하나라도 있으면
`systems/backend/ontology_dashboard`를 삭제할 수 없다.

## 2. 이관 판단 기준

다음 중 하나 이상의 근거가 있어야 `MOVE` 또는 `SPLIT`할 수 있다.

1. 승인된 요구사항·ADR·공유 계약에서 제품 책임으로 정의된다.
2. 최종 API/UI/worker 또는 배포 경로에 실제 consumer가 있다.
3. 보안, 데이터 무결성, 영속성, health/readiness에 필수적이다.
4. 다른 canonical owner인 Generator, `gen_data`, Project 3가 대신 소유하지 않는다.

테스트가 존재하거나 레거시 `main.py`가 Router를 등록한다는 사실만으로는 이관
근거가 되지 않는다. 제거·대체 시에는 삭제되는 API와 회귀 테스트를 같이 기록한다.

## 3. Source 처분 Ledger

| Source | 현재 책임 | 처분 | 목표/결정 | 담당 이슈 |
|---|---|---|---|---|
| `__init__.py` | 레거시 package export | `REPLACE` | `app` package export로 대체 | #64 |
| `app.py`, `application.py`, `application_runtime.py`, `bootstrap.py`, `dependencies.py`, `main.py`, `openapi_contracts.py` | FastAPI host, DI, startup, OpenAPI 조립 | `REPLACE` | `app/main.py`와 composition wiring. 업무 로직은 포함하지 않음 | #64 |
| `settings.py` | 환경·DB·proxy·runtime 설정 | `SPLIT` | 공통 runtime 설정과 Infra 설정을 분리하고 composition에서 조립 | #52, #64 |
| `migrations.py`, `postgresql.py`, `postgresql_compat.py`, `postgresql_pool.py`, `postgresql_repositories.py`, `postgresql_ontology_repository.py` | DB pool, compatibility, 다중 도메인 repository 구현 | `SPLIT` | `infra/db` 기술 구현과 각 도메인 repository adapter로 분리 | #52~#63 |
| `deployment.py`, `persistence_readiness.py`, `observability.py` | health/startup/DB/관측 readiness | `SPLIT` | 필수 probe는 `infra`와 composition으로 이관, Platform 전용 응답은 #68에서 판정 | #52, #64, #68 |
| `security.py` | rate limit과 보안 정책 | `SPLIT` | 인증·권한 정책은 `identity`, Redis 구현은 `infra` | #52, #53 |
| `outbox.py` | Integration Outbox | `SPLIT` | messaging 기술 구현은 `infra`, Maintenance event 의미는 `maintenance` | #52, #59 |
| `artifact_storage.py` | storage driver와 Artifact governance | `SPLIT` | driver는 `infra/storage`, catalog·검증 정책은 `governance` | #52, #63 |
| `connectors.py` | 외부 connector와 ingestion job | `SPLIT` | HTTP/driver는 `infra/external`, ingestion use case는 `dataset` | #52, #57, #68 |
| `llm.py` | provider, report agent, grounding fallback | `SPLIT` | provider는 `infra/llm`, report/planner use case는 각 consumer domain | #52, #61, #62 |
| `integrations/*` | Project 3 client, DTO, projection | `SPLIT` | client는 `infra/external`; projection 의미는 `ontology`/consumer port. 최종 사용 여부 확인 | #52, #55, #62, #68 |
| `identity.py`, `identity_models.py`, `identity_repository.py`, `enterprise_identity.py` | IAM과 일부 Project 책임 | `SPLIT` | IAM은 `identity`, Project lifecycle은 `project` | #53, #54 |
| `projects/*`, `project_context.py` | Project lifecycle/context | `MOVE` | `app/project` | #54 |
| `ontology.py`, `ontology_primitives.py`, `ontology_repository.py`, `ontology_instance_repository.py`, `ontology_service.py`, `ontology_adapter.py` | Ontology registry, instance, action, projection | `SPLIT` | `app/ontology`; 다른 도메인 의미는 public port로 소비 | #55 |
| `domain_packs/*` | 범용 Domain Pack registry와 PdM materialization | `SPLIT` | PdM projection은 `ontology`/`dataset`; 범용 registry 유지 여부는 별도 판정 | #55, #57, #68 |
| `datasets/*` | Dataset catalog/source/projection/materialization | `MOVE` | `app/dataset`, Generator 학습 책임은 제외 | #57 |
| `adapters/*` | Dataset ingestion, file/DB adapter, Prediction repository가 혼재 | `SPLIT` | bundle·CSV·canonical ingestion은 `dataset`, Prediction persistence는 `diagnosis`, 기술 I/O는 `infra` | #52, #57, #58 |
| `predictive_maintenance_runtime/*`, `product_result_evidence_projection.py` | Runtime result/read model/replay | `SPLIT` | inference·Result/Evidence·history readiness는 `diagnosis`; Overlay 생성은 `gen_data` | #58 |
| `live_predictive_maintenance.py` | Mac mini live observation ingest, Runtime Overlay consume, Dataset Version materialization, Diagnosis 실행 orchestration | `SPLIT` | source 생성·Overlay 생성은 `gen_data`에 유지하고, stream/DB ingestion은 `dataset`+`infra`, prediction·Result/Evidence는 `diagnosis`, daemon composition은 canonical Backend composition entrypoint로 분리 | #52, #57, #58, #64, #68 |
| `modeling/*` | intake, mapping, feature, experiment, model registry/runtime DTO 혼재 | `SPLIT` | Backend runtime consumer 최소 계약만 `diagnosis`/`governance`; 학습·feature 생성은 Generator로 대체 후 Backend에서 삭제 | #58, #63, #68 |
| `analysis_models.py`, `analysis_repository.py`, `analysis_service.py` | 시각적 Analysis graph와 실행 | `REMOVE` | Operations 제외 범위. `/api/analyses`·Analysis UI·materialization compatibility를 종료한 뒤 삭제. Diagnosis로 이관하지 않음 | #58, #68 |
| `closed_loop/__init__.py`, `closed_loop/domain.py`, `closed_loop/integration.py`, `closed_loop/models.py`, `closed_loop/repository.py` | Recommendation, Decision, WorkOrder, MaintenanceAction/Event, persistence, integration | `MOVE` | `app/maintenance` public contracts/domain + `app/infra/db` persistence로 수렴 | #59 |
| `contracts.py` | Maintenance, Report, Dashboard, HTTP DTO 혼재 | `SPLIT` | 의미 소유 도메인별 schema로 분해, 공통 오류만 `common` | #59~#63 |
| `service.py`, `repository.py`, `context.py`, `conversation.py` | 제조 Facade, Audit, Project3 fallback, follow-up | `SPLIT` | Equipment/Maintenance/Report/Dashboard/Governance/Planner로 분해하거나 canonical 구현으로 대체 | #56, #59~#63 |
| `dashboard_catalog.py`, `dashboard_models.py`, `dashboard_repository.py`, `dashboard_service.py`, `visualizations/__init__.py`, `visualizations/models.py`, `visualizations/profiler.py`, `visualizations/recommender.py`, `visualizations/semantic.py` | Dashboard/read-model composition | `MOVE` | `app/dashboard` + persistence `app/infra/db`; upstream 의미를 재계산하지 않음 | #60 |
| `reports.py`, `export_models.py`, `export_repository.py`, `export_service.py` | Report와 Export | `MOVE` | `app/report` | #61 |
| `planner/*`, `ontology_planner_models.py`, `ontology_planner_service.py` | 자연어 Planner와 UI plan | `MOVE` | `app/planner`, provider는 Infra port로 소비 | #62 |
| `orchestration/*` | 범용 multi-store Agent orchestration | `REMOVE` | Agent는 Operations 제외 범위. Planner/Report는 필요한 public port를 각 도메인에서 새로 정의하고 legacy Agent runtime을 재사용하지 않음 | #62, #63, #68 |
| `governance/__init__.py`, `governance/models.py`, `governance/service.py` | Agent trace와 projection governance | `SPLIT` | Dataset/projection/audit/approval governance만 `app/governance`; Agent run/trace surface는 Agent 제거와 함께 종료 | #63, #68 |
| `role_workflow_models.py`, `role_workflow_repository.py`, `role_workflow_service.py` | Field task, 역할별 read model, template/model 승인, audit | `SPLIT` | `maintenance`, `dashboard`, `governance` | #59, #60, #63 |
| `automation_runtime.py` | Platform automation simulation | `REMOVE` | Human Decision 기반 Closed-loop와 다른 Commercial V4 simulation. 자동 설비 정지/Work Order도 Operations 제외 | #59, #68 |
| `branching_lineage.py` | Platform change/merge/marking policy branch | `REMOVE` | `maintenance_replay_overlay`와 무관한 generic resource branch. marking policy도 승인된 Operations 계약이 없어 branch와 함께 종료 | #63, #68 |
| `distributed_runtime.py`, `distributed_handlers.py`, `worker.py` | Analysis/Connector Durable Job | `REMOVE` | 실제 handler는 Analysis/Connector뿐이며 기본 worker는 Analysis. Maintenance Outbox와 별개. Dataset이 비동기 실행을 필요로 하면 #57에서 새 port/worker를 정의 | #52, #57, #68 |
| `mlops_runtime.py` | Backend Platform drift API | `REMOVE` | snapshot/drift simulation은 Generator의 학습·평가·Model Artifact 소유권과 중복. Backend에는 runtime artifact consumer만 유지 | #58, #68 |
| `pipeline_runtime.py` | Platform sample visual pipeline plan | `REMOVE` | sample SQL planner는 승인된 Operations가 아니며 extraction/Feature/Model pipeline의 canonical owner는 Generator | #57, #68 |
| `polyglot/*` | PostgreSQL/Neo4j/Redis 직접 health | `REMOVE` | 표준 Backend health는 composition/Infra로 대체하고, graph/RAG readiness는 Project 3 typed integration 경계에서 확인. Backend가 Neo4j를 직접 소유하지 않음 | #52, #64, #68 |
| `demo_predictive_maintenance_bootstrap.py` | Render용 Canonical demo materialization | `REPLACE` | 명시적 demo seed/bootstrap으로 대체하고 Domain package에서 분리 | #57, #64, #68 |
| `routers/adapters.py`, `routers/datasets.py` | Dataset API | `SPLIT` | `dataset` Router, Prediction endpoint는 `diagnosis` | #57, #58 |
| `routers/auth.py` | IAM API | `MOVE` | `app/identity` | #53 |
| `routers/projects.py` | Project API | `MOVE` | `app/project` | #54 |
| `routers/ontology.py` | Ontology API | `MOVE` | `app/ontology` | #55 |
| `routers/predictive_maintenance_runtime.py` | Prediction read/replay API | `SPLIT` | Diagnosis read/runtime과 외부 Overlay control 계약 분리 | #58 |
| `routers/manufacturing.py` | Equipment, Event, Evidence, Report, Decision API 혼재 | `SPLIT` | `equipment`, `maintenance`, `report`, `dashboard`/composition | #56, #59~#61 |
| `routers/dashboards.py` | Dashboard API | `MOVE` | `app/dashboard` | #60 |
| `routers/exports.py` | Export API | `MOVE` | `app/report` | #61 |
| `routers/planner.py` | Planner API | `MOVE` | 승인된 자연어 Planner API를 `app/planner`로 이관 | #62 |
| `routers/agent.py` | 범용 multi-store Agent API | `REMOVE` | Agent는 Operations 제외 범위. `/api/agent/*`와 Agent inspector/trace compatibility를 함께 종료 | #62, #63, #68 |
| `routers/governance.py` | Governance API | `MOVE` | `app/governance` | #63 |
| `routers/admin.py`, `routers/role_workspaces.py` | Identity, Dashboard, Governance, Maintenance API 혼재 | `SPLIT` | endpoint별 의미 소유 도메인으로 분해 | #53, #59, #60, #63 |
| `routers/project3.py` | Project 3 passthrough API | `SPLIT` | raw passthrough는 제거. 필요한 topology/schema/subgraph 소비는 `infra/external` typed client 뒤 `ontology` public query로, Planner가 필요로 하는 RAG는 Planner port로 제한 | #52, #55, #62, #68 |
| `routers/platform.py` | 31개 Commercial V4 Platform API 집합 | `SPLIT` | §5 endpoint ledger에 따라 canonical domain/health로 대체할 endpoint만 분해하고 generic Commercial V4 surface는 종료 | #52~#64, #68 |
| `routers/system.py` | health와 polyglot health | `SPLIT` | 표준 health는 composition/Infra로 이관하고 polyglot endpoint는 `REMOVE` 판정에 따라 종료 | #52, #64, #68 |
| `routers/analyses.py` | Analysis API | `REMOVE` | Analysis Operations 제외 결정에 따라 `/api/analyses/*` compatibility와 함께 종료 | #58, #68 |
| `routers/modeling.py` | Backend 학습/실험/registry Workbench API | `REMOVE` | Modeling Workbench는 Operations 제외. 학습·Feature·experiment는 Generator, runtime scoring은 Diagnosis API가 소유 | #58, #63, #68 |
| `routers/__init__.py` | 기술 중심 Router package export | `REPLACE` | 각 도메인 Router와 `app/main.py` 등록으로 대체 | #64 |

## 4. Phase 0.5 Legacy Capability Disposition 근거

현재 실행 경로 또는 테스트가 있다는 사실은 아래의 **현재 consumer**에 기록하되,
그 자체를 제품 유지 근거로 사용하지 않는다. Canonical 제품 기준은
`docs/operations/requirements-specification.md`의 Operations 화면/제외 범위와
`docs/architecture.md`의 Runtime Ownership이다. 특히 Analysis, Agent, Admin,
Modeling Workbench는 Operations 제외 범위이고, 학습·Feature·Model Artifact 생산은
`systems/generator`, Runtime Overlay Observation 생성은 `gen_data`, graph/RAG 저장·질의는
Project 3가 canonical owner다.

| Source / capability | 현재 consumer / 실행 근거 | canonical owner | 처분 | target / 공개 port | 판정 근거 | removal / replacement prerequisite | regression coverage |
|---|---|---|---|---|---|---|---|
| `analysis_*`, `routers/analyses.py` | Analysis UI, Dashboard Analysis reference, Dataset materialization, Analysis tests | 없음(Operations 제외) | `REMOVE` | 없음 | 시각적 Analysis graph는 Diagnosis가 아니며 Operations 제외 범위 | `/api/analyses/*`, Analysis route/board reference, analysis-derived Dataset compatibility를 함께 종료 | `tests/test_analysis_path.py`, `tests/test_dataset_projection_stage47.py`, 관련 frontend E2E를 삭제/대체 기준으로 사용 |
| `orchestration/*`, `routers/agent.py` | Agent UI/inspector, Governance Agent trace, Project 3 graph/RAG adapter | 없음(Operations 제외); Project 3는 외부 graph/RAG owner | `REMOVE` | Planner/Report가 필요하면 각 domain의 좁은 query port를 새로 정의 | generic multi-store Agent는 승인된 Planner/Report 계약이 아니며 Agent가 Operations 제외 | `/api/agent/*`, Governance Agent trace/read model, Agent UI를 같이 종료. Planner/Report가 legacy orchestrator를 import하지 않음 | `tests/test_multistore_orchestrator_stage49.py`, `tests/test_governance_workbench_stage51.py` |
| `automation_runtime.py` | Commercial V4 `/automation`, `/automation/simulate`, unit test | Maintenance 아님 | `REMOVE` | 없음 | side-effect 없는 sample ECA simulation이고 자동 설비 정지/자동 Work Order는 Operations 제외 | Commercial V4 automation cards/API 제거. Closed-loop human Decision/Action contract로 대체했다고 주장하지 않음 | `tests/test_automation_runtime_phase32.py` |
| `branching_lineage.py` | Commercial V4 branch/merge/policy UI, persistence tests | 없음; Runtime Overlay는 `gen_data` | `REMOVE` | 없음 | dataset/ontology/application generic branch는 `maintenance_replay_overlay`와 identity·clock·owner가 다름. generic marking policy도 승인된 Operations contract가 없음 | `/branching-lineage`, `/branches/*`, `/policy/check` 및 `platform_*` branch/marking compatibility 정리 | `tests/test_branching_lineage_phase28.py`, persistence migration coverage |
| `distributed_runtime.py`, `distributed_handlers.py`, `worker.py` | production manifest의 `python -m ontology_dashboard.worker`; handlers는 `analysis`, `connector_ingestion` | 없음. 필요 시 Dataset + Infra가 새 계약 소유 | `REMOVE` | #57에서 필요성이 확인될 때 Dataset job port + Infra worker를 새로 정의 | Maintenance Outbox가 아니며 기본 job type도 Analysis. Analysis는 Operations 제외 | worker deployment command, `scripts/run_durable_worker.py`, distributed Platform API, Analysis/Connector queue caller를 함께 정리 | `tests/test_distributed_runtime_phase23.py`, `tests/test_connectors_phase26.py`, `tests/test_analysis_path.py` |
| `mlops_runtime.py` | Commercial V4 MLOps card/API, drift unit test | `systems/generator`(학습·평가·publish), `app/diagnosis`(runtime consume) | `REMOVE` | 없음 | static champion/challenger/drift simulation은 canonical Model Artifact lifecycle과 중복 | `/api/platform/.../mlops*` 및 Commercial V4 card 종료. runtime Model Artifact 검증/score는 Diagnosis regression으로 보호 | `tests/test_mlops_runtime_phase31.py`, Generator artifact/Diagnosis runtime tests |
| `pipeline_runtime.py` | Commercial V4 sample pipeline card/API, unit test | `systems/generator` + `app/dataset` ingestion | `REMOVE` | 없음 | sample SQL planner는 승인된 Operations pipeline 계약이 아니며 Feature/training pipeline owner가 아님 | `/pipeline/*`와 sample card 종료. Dataset ingestion API와 Generator pipeline은 별도 유지 | `tests/test_pipeline_runtime_phase30.py`, Generator pipeline tests |
| `polyglot/*`, `/api/system/polyglot-health` | optional compose profile, direct PostgreSQL/Neo4j/Redis probes, unit test | Infra health + Project 3 | `REMOVE` | standard `/health/*`; Project 3 typed adapter readiness | Backend가 Neo4j를 직접 운영하는 계약이 없고 graph/RAG는 Project 3 경계 | optional polyglot dependency/profile/endpoint를 제거하되 standard liveness/startup/readiness 유지 | `tests/test_polyglot_infra_stage46.py`, deployment health tests |
| `domain_packs/*` | Project metadata resolution, Commercial V4 application definition, PdM ontology materialization | `app/ontology` + `app/dataset`; generic registry는 없음 | `SPLIT` | PdM materialization을 Ontology/Dataset port로 분리 | generic default pack/application shell은 final Operations requirement가 아니지만 PdM materialization은 canonical source projection에 필요 | generic registry/alias/API를 종료하고 PdM mapping/materialization contract만 이관 | `tests/test_domain_pack_platform_phase19.py`, PdM projection/materialization tests |
| `modeling/*` | Modeling Workbench/API; 일부 compatibility port가 Generator를 lazy import; model registry/scoring 일부 | Generator + `app/diagnosis` + `app/governance` | `SPLIT` | runtime artifact load/score는 Diagnosis, 승인/audit은 Governance; authoring/training은 Generator | Workbench는 제외 범위지만 이미 canonical owner가 있는 최소 runtime/governance 계약은 보존해야 함 | intake/mapping/feature/experiment/training Workbench를 제거하고 기존 `app/diagnosis` 계약과 Generator publish 계약으로 교체 | `tests/test_adaptive_modeling_*`, `tests/test_model_registry_and_explanations.py`를 owner별 회귀로 재배치 |
| `routers/modeling.py` | MLValidatorWorkbench가 `/api/modeling/*` 호출 | 없음(Workbench 제외); 기능 owner는 위와 같음 | `REMOVE` | Diagnosis/Dataset/Governance의 승인된 endpoint만 별도 유지 | 35개 Workbench endpoint 전체를 migration target으로 유지하면 Generator 중복 소유가 재발 | MLValidatorWorkbench와 `/api/modeling/*` compatibility 종료 후 router 삭제 | frontend modeling E2E + modeling API tests를 제거/owner API regression으로 전환 |
| `integrations/project3/*` | Project 3 passthrough, outbox projection, Agent graph/RAG ports | Project 3 + Backend `infra/external`/`ontology` | `SPLIT` | typed HTTP client=`infra/external`; PdM graph projection=`ontology` outbound port | Project 3 자체 기능은 Backend가 복제하지 않되 Objects topology/projection에는 typed integration이 필요 | raw graph/RAG 구현 금지; Project 3 장애/degraded contract와 projection idempotency 보존 | `tests/test_project3_client_stage45.py`, `tests/test_predictive_maintenance_graph_projection.py` |
| `routers/project3.py` | frontend status/schema/subgraph direct calls; tests | Ontology/Planner consumer + `infra/external` | `SPLIT` | schema/search/subgraph 필요분은 Ontology query, RAG 필요분은 Planner port | raw passthrough를 제품 public API로 고정할 근거는 없지만 Objects topology consumer는 존재 | `/query`, `/rag` raw passthrough 제거; status/schema/subgraph consumer를 canonical domain API로 전환 후 legacy router 삭제 | `tests/test_project3_routes_stage45.py`, frontend Project 3 calls |
| `demo_predictive_maintenance_bootstrap.py` | `systems/backend/render_start.sh` hosted startup; canonical V3.1 source ingest + runtime result materialization | Dataset bootstrap + Diagnosis runtime + composition | `REPLACE` | explicit deployment/bootstrap entrypoint; Domain package 밖에서 domain ports 호출 | 운영 domain implementation이 아니라 hosted-demo seed orchestration | #57/#64에서 source-only ingest, idempotency, Diagnosis-produced Result를 보존하는 새 bootstrap으로 Render start를 전환 | `tests/test_demo_predictive_maintenance_bootstrap.py`, `scripts/bootstrap_predictive_maintenance_v3_1_demo.py` release verification |
| `live_predictive_maintenance.py` | Mac mini wall-clock stream/Runtime Overlay를 PostgreSQL Dataset Version, Diagnosis Result/Evidence, Ontology projection으로 조립 | `gen_data`(source·Overlay generation) + `app/diagnosis` + canonical Infra/composition | `REPLACE` | `app.live_predictive_maintenance`가 장기 실행 composition entrypoint를 소유하고 `app.infra.db.predictive_maintenance_ontology_projection` 및 Diagnosis runtime을 조립 | source/Overlay 생성은 계속 `gen_data`가 소유하고 Backend는 consumer 역할만 수행 | legacy module/entrypoint 제거 완료; Compose와 regression test가 canonical module을 직접 실행 | `tests/test_live_predictive_maintenance.py`, `tests/test_generator_artifact_publication.py`, `infra/macmini/docker-compose.yml` runtime smoke |
| `governance/*` | Governance workbench가 Dataset projection, approval, Agent trace를 조합 | `app/governance` + 제거되는 Agent | `SPLIT` | Dataset projection/audit/approval query만 Governance public port | 승인된 governance와 제외 범위 Agent가 한 service에 혼재 | Agent run/count/trace 필드를 제거하고 Dataset/approval/audit consumer regression을 보존 | `tests/test_governance_workbench_stage51.py` |
| Platform application/runtime/search | Commercial V4가 `applications/v4`, `application-runtime`, `global-search` 사용 | 없음 | `REMOVE` | final workflow routing은 frontend + canonical domain APIs | Commercial V4 metadata-driven platform shell은 Operations 화면 기준선이 아님 | Commercial V4 route/registry/search UI와 API를 같이 종료 | Commercial V4 UI/E2E를 compatibility 종료 대상으로 추적 |
| Platform readiness wrappers | Commercial V4가 persistence/enterprise/deployment/observability readiness 조회 | composition/Infra/Identity | `REPLACE` | `/health/*`, Infra observability, Identity diagnostics가 필요 시 owner-specific query | project-scoped Commercial V4 wrapper와 실제 health invariant를 분리 | 배포 probe가 새 canonical host에서 먼저 통과한 뒤 wrapper 제거 | deployment/identity/observability tests |
| Platform artifact/connector/ontology primitive APIs | Commercial V4 operator UI | Governance/Dataset/Ontology + Infra adapters | `SPLIT` | owner domain router/public port | 일부 capability는 유지 가치가 있지만 generic Platform router 소유가 아님 | 각 owner API 회귀가 준비된 뒤 `/api/platform` compatibility 제거 | artifact/connectors/ontology primitive tests |

### 4.1 DEFER 해소 결과와 gate

Phase 0.5 판정 후 Section 3의 `DEFER`는 **0건**이다. 이후 새로운 제품 근거가 생겨도
legacy Source를 다시 `DEFER`로 되돌리지 않는다. 필요한 기능은 해당 owner Phase에서
새 canonical port로 제안하고 검증한다.

- #52~#64는 위 최종 disposition을 입력으로 삼되 PR #51 merge 전 구현하지 않는다.
- `REMOVE`는 해당 Phase에서 API/UI/script/deployment/test compatibility 종료를 함께 수행한다.
- `REPLACE`는 새 canonical entrypoint와 회귀 검증이 준비되기 전 legacy Source를 삭제하지 않는다.
- `SPLIT`은 표의 owner별 target이 준비되기 전 source 전체를 한 도메인으로 복사하지 않는다.
- #65는 ledger checker가 미배정/중복/`UNDECIDED`/`DEFER` 0건을 확인한 뒤에만 시작한다.

## 5. `routers/platform.py` 31개 endpoint 최종 처분

Commercial V4가 현재 consumer인 경우도 **현재 compatibility consumer**로만 기록한다.
Final Operations가 `/api/platform` namespace 자체를 요구하지 않으므로 유지되는 capability도
owner domain의 endpoint/port로 전환한 뒤 legacy Platform route를 종료한다.

| Endpoint | 처분 | canonical owner / 종료 조건 |
|---|---|---|
| `GET /api/platform/domain-packs` | `REMOVE` | generic registry 종료; PdM materialization은 Ontology/Dataset으로 분리 |
| `GET /api/platform/projects/{project_id}/applications/v4` | `REMOVE` | Commercial V4 application shell 종료 |
| `GET /api/platform/projects/{project_id}/persistence-readiness` | `REPLACE` | composition/Infra의 canonical readiness로 대체 |
| `GET /api/platform/projects/{project_id}/enterprise-identity` | `REPLACE` | 필요한 진단만 Identity owner로 이동; Commercial V4 wrapper 종료 |
| `GET /api/platform/projects/{project_id}/deployment-readiness` | `REPLACE` | canonical `/health/startup`, `/health/ready` 및 deployment probe로 대체 |
| `GET /api/platform/projects/{project_id}/distributed-runtime` | `REMOVE` | Analysis/Connector generic worker 제거와 함께 종료 |
| `GET /api/platform/projects/{project_id}/artifact-governance` | `SPLIT` | catalog/verification 정책은 Governance, storage driver는 Infra |
| `POST /api/platform/projects/{project_id}/artifacts/{artifact_id}/verify` | `SPLIT` | Governance 검증 use case로 owner API가 준비된 뒤 종료 |
| `POST /api/platform/projects/{project_id}/artifacts/{artifact_id}/sign-download` | `SPLIT` | Governance policy + Infra storage signing으로 분리 |
| `POST /api/platform/projects/{project_id}/artifact-reconciliation` | `SPLIT` | Governance reconciliation use case로 분리 |
| `GET /api/platform/projects/{project_id}/observability` | `REPLACE` | Infra/composition observability contract로 대체 |
| `GET /api/platform/projects/{project_id}/connectors` | `SPLIT` | Dataset ingestion use case + Infra external adapter로 분리 |
| `POST /api/platform/projects/{project_id}/connectors/{connector_id}/run` | `SPLIT` | Dataset-owned ingestion command로 전환; generic durable worker는 보존하지 않음 |
| `GET /api/platform/projects/{project_id}/ontology-primitives` | `SPLIT` | `app/ontology` query로 전환 |
| `POST /api/platform/projects/{project_id}/actions/preview` | `SPLIT` | Ontology Action preview만 유지; MaintenanceAction과 혼합하지 않음 |
| `POST /api/platform/projects/{project_id}/functions/execute` | `SPLIT` | `app/ontology` function execution port로 전환 |
| `GET /api/platform/projects/{project_id}/branching-lineage` | `REMOVE` | generic Platform branch/lineage 종료 |
| `POST /api/platform/projects/{project_id}/branches/change` | `REMOVE` | Runtime Overlay branch로 대체하지 않음 |
| `POST /api/platform/projects/{project_id}/branches/{branch_id}/merge` | `REMOVE` | Runtime Overlay에는 generic merge semantics를 적용하지 않음 |
| `POST /api/platform/projects/{project_id}/policy/check` | `REMOVE` | generic branch marking policy 종료; 필요한 owner-specific authorization은 Identity/Governance 계약 사용 |
| `GET /api/platform/projects/{project_id}/application-runtime` | `REMOVE` | Commercial V4 application runtime shell 종료 |
| `POST /api/platform/projects/{project_id}/global-search` | `REMOVE` | generic global search는 Operations 요구사항 아님 |
| `GET /api/platform/projects/{project_id}/pipeline/sample-plan` | `REMOVE` | sample visual pipeline 종료 |
| `POST /api/platform/projects/{project_id}/pipeline/plan` | `REMOVE` | Generator/Dataset canonical pipeline과 중복 방지 |
| `GET /api/platform/projects/{project_id}/mlops` | `REMOVE` | Generator Model Artifact lifecycle을 canonical owner로 사용 |
| `POST /api/platform/projects/{project_id}/mlops/drift/evaluate` | `REMOVE` | Backend drift simulation 종료; 향후 필요 시 Generator contract로 신규 정의 |
| `GET /api/platform/projects/{project_id}/automation` | `REMOVE` | generic automation simulation 종료 |
| `POST /api/platform/projects/{project_id}/automation/simulate` | `REMOVE` | Closed-loop human Decision/Action으로 자동 매핑하지 않음 |
| `GET /api/platform/projects/{project_id}/distributed-job-events` | `REMOVE` | generic durable runtime 제거와 함께 종료 |
| `POST /api/platform/projects/{project_id}/distributed-jobs/{job_id}/cancel` | `REMOVE` | generic durable runtime 제거와 함께 종료 |
| `POST /api/platform/projects/{project_id}/distributed-jobs/{job_id}/replay` | `REMOVE` | generic durable replay와 Maintenance Replay/Overlay를 구분하고 종료 |

## 6. Phase별 적용 규칙

실행 순서는 `#51 Phase 0 → #68 capability disposition → #73 Architecture CI Ratchet → #52~#64 Domain/Infra migration → #65 legacy deletion → #66 final strict CI`로 고정한다.

1. 각 Phase PR은 자기 Source 행의 세부 파일 목록과 최종 처분을 PR 본문에 기록한다.
2. `SPLIT`은 각 책임의 새 owner와 public port를 확인한 뒤 레거시 Source를 삭제한다.
3. `REPLACE`는 새 구현의 회귀 테스트와 deployment entrypoint가 통과한 뒤 삭제한다.
4. `REMOVE`는 삭제되는 API/테스트/문서 참조를 함께 정리한다.
5. #68 완료 전에는 Phase 1~13 구현을 시작하지 않고, Phase 0.5 이후 ledger에는 `DEFER`를 다시 추가하지 않는다. 새 필요성은 owner Phase에서 새 canonical port로 제안하며, #73 Ratchet 통과 전에는 해당 Phase 이슈의 DoD를 닫을 수 없다.
6. Phase 14(#65)는 Ledger의 미배정 Source, `UNDECIDED`, `DEFER`가 모두 0건일 때만 시작한다.

## 7. Architecture CI Ratchet

- Phase 0.6(#73): #68의 최종 처분 원장을 기준으로
  [`backend-migration-baseline.json`](./backend-migration-baseline.json)에 정확한 legacy Python Source와
  non-legacy static/dynamic import 및 문자열 runtime entrypoint를 동결한다.
- `scripts/check_backend_migration_ratchet.py`는 현 저장소와 baseline의 정확한 일치 및 PR base 대비
  감소 전용 조건을 검사하고, 기존 Ledger 검증도 함께 실행한다.
- Phase 1~13: 레거시 존재 자체는 허용하되 신규 레거시 파일, 신규 레거시 import/entrypoint,
  baseline 증가를 금지한다.
- 각 Phase: 이미 이관 완료로 선언한 Source의 재생성과 모든 non-legacy 영역에서 레거시로 향하는
  신규 참조를 금지하고, 실제 이관·삭제와 같은 PR에서 baseline을 함께 감소시킨다.
- Phase 14: `systems/backend/ontology_dashboard`와 모든 import/실행 참조가 0건인지 검사한다.
- Phase 15(#66): baseline 비교가 아닌 최종 strict invariant를 유지하고 이후 회귀를 차단한다.

Baseline 갱신은 `python scripts/check_backend_migration_ratchet.py --write-baseline`로 기계적으로
수행한다. 이 명령으로 증가를 승인할 수는 없으며, Architecture CI가 dependency 설치 전에
`github.event.pull_request.base.sha`의 baseline과 비교한다. baseline 자체를 바꾸는 docs-only PR도
동일 검사를 우회하지 않는다.

## 8. Physical migration progress

이 표는 처분 자체를 바꾸는 두 번째 Ledger가 아니라, Section 3의 결정을 실제 물리
이동으로 완료한 Source를 되돌리지 않기 위한 **CI ratchet**이다. `MIGRATED` Source는
더 이상 `systems/backend/ontology_dashboard` 아래에 존재해서는 안 되며, 기록된 canonical
target이 실제로 존재하고 비어 있지 않아야 한다. `SPLIT` Source는 이 표에 올라온 파일 단위 책임만 완료된
것이며, 같은 Section 3 행의 다른 Source까지 완료됐다는 의미는 아니다.

| Legacy Source | Canonical target(s) | State |
|---|---|---|
| `settings.py` | `systems/backend/app/common/runtime_settings.py`, `systems/backend/app/infra/db/settings.py`, `systems/backend/app/infra/observability/runtime_validation.py` | `MIGRATED` |
| `security.py` | `systems/backend/app/common/exceptions.py`, `systems/backend/app/common/rate_limit.py`, `systems/backend/app/infra/rate_limit.py` | `MIGRATED` |
| `postgresql.py` | `systems/backend/app/infra/db/connection.py` | `MIGRATED` |
| `postgresql_pool.py` | `systems/backend/app/infra/db/pool.py` | `MIGRATED` |
| `observability.py` | `systems/backend/app/infra/observability/runtime.py` | `MIGRATED` |
| `integrations/project3/client.py` | `systems/backend/app/infra/external/project3/client.py` | `MIGRATED` |
| `integrations/project3/models.py` | `systems/backend/app/infra/external/project3/models.py` | `MIGRATED` |
| `identity_models.py` | `systems/backend/app/identity/identity_schema.py`, `systems/backend/app/identity/ports.py` | `MIGRATED` |
| `identity_repository.py` | `systems/backend/app/identity/identity_repository.py` | `MIGRATED` |
| `enterprise_identity.py` | `systems/backend/app/identity/enterprise_identity.py` | `MIGRATED` |
| `routers/auth.py` | `systems/backend/app/identity/identity_router.py` | `MIGRATED` |
| `adapters/prediction_repository.py` | `systems/backend/app/diagnosis/ports.py`, `systems/backend/app/infra/db/prediction_result_repository.py` | `MIGRATED` |
| `predictive_maintenance_runtime/models.py` | `systems/backend/app/diagnosis/runtime_schema.py` | `MIGRATED` |
| `predictive_maintenance_runtime/repository.py` | `systems/backend/app/diagnosis/ports.py`, `systems/backend/app/infra/db/diagnosis_runtime_repository.py` | `MIGRATED` |
| `predictive_maintenance_runtime/service.py` | `systems/backend/app/diagnosis/runtime_service.py` | `MIGRATED` |
| `product_result_evidence_projection.py` | `systems/backend/app/diagnosis/evidence_projection.py` | `MIGRATED` |
| `routers/predictive_maintenance_runtime.py` | `systems/backend/app/diagnosis/diagnosis_router.py` | `MIGRATED` |
| `live_predictive_maintenance.py` | `systems/backend/app/live_predictive_maintenance.py`, `systems/backend/app/infra/db/predictive_maintenance_ontology_projection.py` | `MIGRATED` |
| `closed_loop/__init__.py` | `systems/backend/app/maintenance/__init__.py` | `MIGRATED` |
| `closed_loop/domain.py` | `systems/backend/app/maintenance/maintenance_domain.py` | `MIGRATED` |
| `closed_loop/integration.py` | `systems/backend/app/maintenance/integration.py` | `MIGRATED` |
| `closed_loop/models.py` | `systems/backend/app/maintenance/maintenance_schema.py`, `systems/backend/app/maintenance/ports.py` | `MIGRATED` |
| `closed_loop/repository.py` | `systems/backend/app/infra/db/maintenance_repository.py` | `MIGRATED` |
| `governance/__init__.py` | `systems/backend/app/governance/__init__.py` | `MIGRATED` |
| `governance/models.py` | `systems/backend/app/governance/governance_schema.py` | `MIGRATED` |
| `governance/service.py` | `systems/backend/app/governance/governance_service.py`, `systems/backend/app/governance/ports.py` | `MIGRATED` |
| `routers/governance.py` | `systems/backend/app/governance/governance_router.py` | `MIGRATED` |
| `dashboard_models.py` | `systems/backend/app/dashboard/dashboard_schema.py` | `MIGRATED` |
| `dashboard_catalog.py` | `systems/backend/app/dashboard/catalog.py` | `MIGRATED` |
| `dashboard_repository.py` | `systems/backend/app/dashboard/ports.py`, `systems/backend/app/infra/db/dashboard_repository.py` | `MIGRATED` |
| `dashboard_service.py` | `systems/backend/app/dashboard/dashboard_service.py`, `systems/backend/app/dashboard/ports.py` | `MIGRATED` |
| `visualizations/__init__.py` | `systems/backend/app/dashboard/visualizations/__init__.py` | `MIGRATED` |
| `visualizations/models.py` | `systems/backend/app/dashboard/visualizations/models.py` | `MIGRATED` |
| `visualizations/profiler.py` | `systems/backend/app/dashboard/visualizations/profiler.py` | `MIGRATED` |
| `visualizations/recommender.py` | `systems/backend/app/dashboard/visualizations/recommender.py` | `MIGRATED` |
| `visualizations/semantic.py` | `systems/backend/app/dashboard/visualizations/semantic.py` | `MIGRATED` |
| `routers/dashboards.py` | `systems/backend/app/dashboard/dashboard_router.py` | `MIGRATED` |
| `reports.py` | `systems/backend/app/report/generation.py`, `systems/backend/app/report/report_schema.py` | `MIGRATED` |
| `llm.py` | `systems/backend/app/report/generation_provider.py`, `systems/backend/app/report/ports.py`, `systems/backend/app/infra/llm/provider.py` | `MIGRATED` |
| `export_models.py` | `systems/backend/app/report/report_schema.py` | `MIGRATED` |
| `export_repository.py` | `systems/backend/app/report/ports.py`, `systems/backend/app/infra/db/report_repository.py` | `MIGRATED` |
| `export_service.py` | `systems/backend/app/report/report_service.py`, `systems/backend/app/report/ports.py` | `MIGRATED` |
| `routers/exports.py` | `systems/backend/app/report/report_router.py` | `MIGRATED` |

`artifact_storage.py`의 object-storage driver/key 생성 책임은 `app/infra/storage`로
분리됐지만 legacy Source에는 아직 Governance catalog/service 책임이 남아 있으므로 파일
자체를 `MIGRATED`로 표시하지 않는다. `llm.py`는 Infra provider와 Report generation
consumer가 모두 canonical owner로 분리되어 Phase 10에서 완전히 이관됐다.

`identity.py`는 IAM service 책임을 `app/identity/identity_service.py`로 분리했지만,
Project membership lifecycle 책임이 #54 소유로 남아 있으므로 legacy Source 자체는
아직 `MIGRATED`로 표시하지 않는다. `app/identity`는 `PrincipalContext`와
`WorkspaceScope` public port를 제공하고 Project membership lifecycle은 이 source에
남겨 다음 Phase에서 `app/project`로 이관한다.
Phase 5(#56)는 공유 Source를 삭제하지 않고 Equipment 책임만 물리적으로 분리한다.
`service.py`의 Equipment master application 책임과
`routers/manufacturing.py`의 `/api/equipment*` route 정의는
`systems/backend/app/equipment`으로 이동하고, Equipment current-state query/state-patch
public port와 optimistic `state_version` 규칙을 canonical domain에 정의한다. `service.py`, `repository.py`,
`routers/manufacturing.py`에는 다른 Domain 책임이 남아 있으므로 이 표의 `MIGRATED`
Source로 올리지 않으며 Section 3의 `SPLIT` disposition도 유지한다. Equipment가 소유하는
state patch 적용 규칙과 `state_version` compare-and-set 계약은 이후 Maintenance/Dashboard가
public Equipment contract를 통해 소비하고, 기존 `closed_loop` persistence 연결은 #59에서
그 port에 맞춰 수렴시킨다.

Phase 7 / #58에서 Product Result/Evidence와 PostgreSQL runtime read/replay 책임을
`app/diagnosis` public contract와 `app/infra/db` adapter로 분리했다. Dataset/Equipment
구현을 Diagnosis가 직접 import하지 않고 `ObservationDatasetQueryPort`와
`EquipmentSnapshotQueryPort` inbound boundary로 연결하며, modeling Workbench의
학습/실험/feature-learning 책임은 이관하지 않는다.

Phase 8 / #59에서는 Recommendation → Decision → WorkOrder → MaintenanceAction →
MaintenanceEvent 상태 흐름과 integration event schema를 `app/maintenance`가 소유한다.
DB/RLS persistence는 `app/infra/db/maintenance_repository.py`로 분리했으며,
Diagnosis Product Result/Evidence와 Equipment state patch/state-version은 각각 public
inbound port로만 소비한다.

Phase 12 / #63에서는 Dataset projection, approval/audit와 artifact retention policy만
`app/governance`로 수렴했다. Generic Agent run/trace detail과 Governance Agent endpoint는
#68 REMOVE 처분에 따라 canonical contract에서 제거했으며, 모델 릴리즈 후보 메타데이터는
Diagnosis-owned `ModelReleaseCandidateQueryPort`를 통해 소비하도록 경계를 고정한다.

Phase 9 / #60에서는 Dashboard schema/catalog/service/router/visualization read-model 책임을
`app/dashboard`로 이관하고 persistence를 `app/infra/db/dashboard_repository.py`로 분리했다.
Equipment/Diagnosis/Maintenance 의미를 Dashboard에서 재계산하지 않으며 각 owner의 public
query contract를 소비하기 위한 `EquipmentStatusQueryPort`, `DiagnosisReadModelQueryPort`,
`MaintenanceQueryPort`를 canonical Dashboard boundary에 둔다.

Phase 10 / #61에서는 grounded Report generation, localized draft, export snapshot/checkpoint와
HTTP API를 `app/report`로 수렴하고 SQLite/PostgreSQL persistence를
`app/infra/db/report_repository.py`로 분리했다. LLM 호출은 Report-owned
`ReportGenerationProviderPort` 뒤에서만 소비하며, Diagnosis Evidence와 Maintenance history,
Dashboard snapshot은 composition adapter가 각 owner public contract를 Report inbound port에
연결한다. `/api/reports/draft`도 Dashboard router에서 Report router로 ownership을 이동했다.
