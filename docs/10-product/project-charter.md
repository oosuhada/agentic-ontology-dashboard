# Ontology Dashboard Project Charter

- Canonical project name: **Ontology Dashboard**
- Status: active project constitution
- Last updated: 2026-08-01

## Mission

Ontology Dashboard는 예측 모델 자체를 만드는 프로젝트가 아니다.

Prediction Module, 분석 파이프라인 또는 외부 자동 감지 시스템이 생성한 결과를 받아서, 각 역할의 사용자가 가장 빠르고 안전하게 판단할 수 있도록 역할별 Dashboard와 Report를 제공하는 **Decision Support Platform**이다.

핵심 산출물은 다음과 같다.

- 역할별 Dashboard
- 근거 기반 Report
- Evidence와 lineage
- 권장 Action
- 승인과 감사 기록
- 프로젝트별 데이터·도메인·화면 설정

## Product Position

Ontology Dashboard는 다음 전달 계층을 담당한다.

```text
[원본 데이터 / 외부 시스템 / Prediction Module]
                    ↓
          [Prediction Result Contract]
                    ↓
         [Ontology Dashboard Platform]
                    ↓
      [Role Dashboard / Report / Action]
                    ↓
                  [사람]
```

Prediction과 Dashboard는 분리한다.

- Prediction Module은 분석 결과를 생성한다.
- Ontology Dashboard는 결과를 검증 가능한 근거와 함께 역할별로 전달한다.
- 입력 방식은 파일, REST API, Kafka, MQTT, OPC-UA 등으로 확장할 수 있다.
- Dashboard는 입력 방식이 아니라 공통 Result Contract에 의존해야 한다.

## Canonical Naming Rules

1. 제품의 공식 가칭과 canonical name은 `Ontology Dashboard`이다.
2. Python canonical namespace는 `ontology_dashboard`이다.
3. 제조 분석 ML canonical namespace는 `ontology_dashboard_manufacturing_ml`이다.
4. `Factory Signal Board`는 과거 임시 명칭이며 신규 코드, 화면, API, 문서 제목, schema, 배포 자산에서 사용하지 않는다.
5. 제조 관련 개념은 platform 이름이 아니라 domain pack 또는 project 이름 안에서만 사용한다.

## Core Principles

### 1. Project 중심

사용자는 하나의 데이터셋이 아니라 하나의 업무 목적을 가진 Project를 선택한다.

```text
Project
=
Dataset / Data Source
+ Domain Pack
+ Ontology Mapping
+ Prediction Contract
+ Dashboard Template
+ Workspace
+ Analysis Runs
```

`Project != Dataset`이다.

하나의 Project는 여러 데이터 소스와 여러 dataset version을 가질 수 있고, 같은 dataset을 서로 다른 업무 목적의 Project에서 사용할 수도 있다.

### 2. Role 중심

같은 분석 결과도 역할마다 다른 판단이 필요하다.

주요 역할:

- Tenant Admin
- Executive Viewer
- Process Manager
- Process Engineer
- Maintenance Technician
- Quality Auditor
- Data Scientist / ML Validator
- FDE

Dashboard Template과 권한은 project, workspace, role 경계에서 관리한다.

### 3. Evidence First

모든 주요 주장과 권장 Action은 다음 중 하나 이상의 근거를 가져야 한다.

- 데이터 관측치
- 비교군
- 정비 이력
- 모델 결과
- source lineage
- 사용자 행동 기록

LLM 출력은 근거 없이 자동 확정하거나 자동 저장하지 않는다.

### 4. Ontology는 목적에 맞게 사용

Ontology Core는 서로 다른 Project의 공통 개념을 표현한다.

- Asset
- Observation
- Event
- AnalysisRun
- Evidence
- Recommendation
- Action

Project별 Domain Schema는 이 공통 Core에 mapping한다.

P3 수준의 전사 시스템 통합 Ontology가 반드시 필요한 것은 아니다. 이미 하나의 식별자 체계로 정리된 데이터셋은 복잡한 의미 통합을 생략할 수 있다. 그러나 Project 간 재사용성과 Dashboard 조회를 위해 명시적인 domain model과 mapping은 유지한다.

### 5. Safe Extension

- arbitrary SQL, Cypher, Python, React 코드를 LLM 출력으로 실행하지 않는다.
- typed intent와 catalog whitelist를 사용한다.
- Action은 permission, object type, parameter, idempotency를 서버에서 검증한다.
- 사용자 저장과 template publish는 승인 경계를 가진다.

### 6. Backward Safety

- 기존 Gold flow와 release gate를 깨지 않는다.
- 구조 변경은 migration과 test를 함께 추가한다.
- 임시 compatibility는 명시적인 종료 계획을 가져야 한다.

## In Scope

- Multi-project selector
- Project별 Domain Pack
- Project별 Dataset Adapter
- Prediction Result Contract
- Role-based Dashboard
- Evidence·Report·Action
- Tenant isolation
- Persistent Ontology object/link store
- PostgreSQL migration과 RLS
- Export·Audit·Approval workflow

## Out of Scope for Current MVP

- 범용 MES·ERP 통합 플랫폼 전체 구현
- 모든 산업 protocol 동시 구현
- 고가용성 분산 inference platform
- LLM이 직접 임의 코드를 생성·실행하는 시스템
- 완전한 graph database 전환
- 실제 모든 데이터셋의 production-grade 모델 개발

## Success Criteria

- 사용자가 로그인 후 접근 가능한 Project를 선택할 수 있다.
- Project마다 다른 dataset, ontology mapping, analysis profile, dashboard template이 적용된다.
- 같은 분석 결과가 역할별로 다른 화면과 설명으로 전달된다.
- 결과의 근거와 lineage를 추적할 수 있다.
- tenant 간 데이터와 관리 기능이 격리된다.
- release gate가 자동으로 구조·보안·회귀를 검증한다.
