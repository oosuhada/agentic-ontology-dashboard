# 다음 ChatGPT 세션용 구현 프롬프트

아래 내용을 새 채팅의 첫 메시지로 그대로 붙여넣는다.

---

## 프롬프트 시작

다음 로컬 프로젝트의 후속 구현을 진행해줘.

```text
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2
```

이 프로젝트는 기존 `Factory Signal Board` 제조 예지보전 MVP에서 출발했지만, 이제 가칭 **Ontology Dashboard**라는 도메인 중립적 온톨로지 기반 대시보드·업무 애플리케이션으로 확장하려고 한다.

### 가장 먼저 할 일

1. DevSpace로 위 프로젝트 폴더를 연다.
2. 파일을 수정하기 전에 다음 문서를 순서대로 읽는다.

```text
docs/ontology-dashboard-additional-implementation-plan.md
docs/palantir-contour-dashboard-benchmark.md
docs/role-needs-research.md
docs/architecture/current-state.md
docs/service-contract.md
README.md
```

3. 현재 baseline을 확인한다.

```bash
PYTHONPATH=api:ml/src python scripts/release_gate.py --with-e2e
```

4. 기존 기능과 Gold 8개 시나리오를 깨뜨리지 않는다.
5. Git 초기화·commit·push는 내가 별도로 요청하기 전에는 하지 않는다.

### 중요한 제품 방향

- 제품 표시명은 우선 `Ontology Dashboard`로 사용한다.
- 기존 제조 예지보전 기능은 폐기하지 않고 `Manufacturing Predictive Maintenance Pack`이라는 첫 domain pack으로 유지한다.
- 제품은 제조업에 한정되지 않는다.
- 핵심 데이터 모델은 `ObjectType`, `Object`, `LinkType`, `Link`, `ActionType`, `Evidence`, `Dashboard`, `Board`다.
- 같은 Ontology를 사용하되 역할에 따라 default dashboard가 다르다.
- 사용자는 허용 범위 안에서 탭, 보드 순서, 크기, 표시 여부, 기본 필터를 바꿀 수 있다.
- 개인 설정은 계정 storage에 저장하고 재로그인 시 복원한다.
- 안전·감사 필수 Board는 사용자가 숨길 수 없다.
- session override와 영구 Saved View를 구분한다.
- Palantir Contour의 Board·Tab·Parameter·cross-filter·view/edit mode를 적극적으로 벤치마킹한다.
- 현재 좌측 설비 사건 목록 중심 UI에서, 상단 Dashboard Tab + 좌측 contextual panel 구조로 전환한다.
- 좌측 panel에는 parameter, filter, saved view, selected object, related object, task 등을 표시한다.
- 편집 모드에서는 좌측 Board Catalog, 중앙 grid canvas, 우측 Board Inspector를 사용한다.

### 역할

일반 사용자 앱:

```text
executive_viewer
process_manager
process_engineer
maintenance_technician
quality_auditor
ml_validator
fde
```

관리자 앱:

```text
tenant_admin
```

FDE는 조직 관리자가 아니다. 고객 workflow·ontology·integration·dashboard template을 구축하고 진단하는 역할이다. 사용자 계정·비밀번호·보안 정책을 임의로 관리할 수 없어야 한다.

### 인증·관리자 요구사항

별도 사용자 앱과 관리자 앱을 만든다.

```text
/login
/register
/app
/admin
```

회원가입 사용자는 바로 역할을 선택할 수 없고 `pending_approval` 상태가 된다. 관리자가 조직, 역할과 workspace scope를 할당한 후 활성화한다.

인증 권장안:

- FastAPI
- SQLite MVP, 향후 PostgreSQL
- Argon2id password hash
- HttpOnly·SameSite cookie session
- API server-side permission check
- 관리자 변경 audit

개발·데모 test account:

```text
admin@ontology.local / OntologyAdmin!2026
executive@ontology.local / Executive!2026
manager@ontology.local / Manager!2026
engineer@ontology.local / Engineer!2026
technician@ontology.local / Technician!2026
quality@ontology.local / Quality!2026
datascientist@ontology.local / DataScience!2026
fde@ontology.local / FDE!2026
```

비밀번호는 DB에 hash만 저장한다. production 환경에서는 demo seed를 금지한다.

### 초기화 기능 정책

- 일반 사용자 UI에 `발표 상태 초기화` 또는 `데모 기록 초기화` 버튼을 다시 만들지 않는다.
- 공개 `/api/demo/reset` endpoint를 다시 만들지 않는다.
- 개발자용 `scripts/reset_demo.py`만 유지한다.
- 향후 관리자 Development Tools는 demo/development 환경에서만 제공한다.
- 실제 운영 감사 기록을 임의 삭제하지 않는다.

### LLM

- LLM은 필수 제품 기능이지만 Vertex AI 자격 증명과 프로젝트 연결은 사용자가 직접 설정할 예정이다.
- 이번 인증·대시보드 기반 구현을 Vertex AI 연결 때문에 멈추지 않는다.
- provider가 없을 때 현재 deterministic fallback을 유지한다.
- LLM이 임의 UI code나 권한 밖 query를 생성할 수 없게 한다.

### 이번 세션에서 구현할 범위

`docs/ontology-dashboard-additional-implementation-plan.md`의 **16~18단계**를 순서대로 구현한다.

#### 16단계 — 제품 reframe와 domain-neutral foundation

- 화면 brand를 `Ontology Dashboard`로 변경
- 기존 제조 기능을 manufacturing workspace/domain pack으로 표시
- domain-neutral Object·Link·Action contract 초안
- 기존 API와 테스트를 유지

#### 17단계 — 회원가입·로그인

- user·credential·session DB migration
- register·login·logout·me API
- pending approval
- password hashing
- cookie session
- test account seed
- `/login`, `/register`, `/pending`
- protected `/app`

#### 18단계 — RBAC와 관리자 페이지 foundation

- role·permission·resource scope schema
- protected `/admin`
- 가입 승인·비활성화
- 사용자별 역할·workspace scope 할당
- 관리자 audit
- 일반 사용자의 admin 접근 403
- FDE와 tenant_admin 권한 분리

### 구현 방식

- 한 번에 거대한 파일로 만들지 말고 domain별 module로 분리한다.
- DB schema 변경에는 migration 또는 idempotent initialization을 제공한다.
- Pydantic contract와 TypeScript type을 함께 관리한다.
- 클라이언트의 role 숨김만으로 보안을 처리하지 않는다.
- 모든 admin API에서 server-side permission을 검사한다.
- test account는 별도 seed script 또는 development bootstrap에서 만든다.
- 현재 React production build와 Playwright test를 유지한다.
- 새 auth·permission test를 추가한다.
- UI는 실제 서비스처럼 구성하고 발표 전용 제어를 노출하지 않는다.

### 이번 세션 완료 조건

다음이 모두 되어야 한다.

1. 8개 test account 로그인 가능
2. 일반 사용자 role에 따라 `/app` default landing이 다름
3. admin만 `/admin` 접근 가능
4. pending·disabled account 로그인 차단
5. signup 후 admin 승인 가능
6. 관리자 role·scope 변경 audit 기록
7. 일반 사용자가 다른 workspace scope 데이터 조회 불가
8. 기존 manager·engineer Gold 화면 유지
9. reset UI·public reset API 없음
10. backend tests, frontend tests, TypeScript, build, Playwright 통과
11. 구현 결과와 남은 다음 단계 보고 후 멈춘다

### 작업 중 보고 방식

- 큰 단계 하나가 끝날 때 짧게 결과를 알려준다.
- 테스트 실패를 발견하면 원인과 수정 결과를 알려준다.
- 실제로 하지 못한 일은 완료했다고 말하지 않는다.
- Git 관련 작업은 하지 않는다.

## 프롬프트 끝

---

# 사용 메모

새 세션에서 범위를 더 작게 시작하려면 마지막 `이번 세션에서 구현할 범위`를 다음처럼 바꿀 수 있다.

```text
우선 16단계만 구현하고 전체 테스트 후 결과를 보고해줘.
```

인증부터 바로 시작하려면:

```text
16단계 문서·표시명 정리 후 17단계 회원가입·로그인까지 구현하고 멈춰줘.
```
