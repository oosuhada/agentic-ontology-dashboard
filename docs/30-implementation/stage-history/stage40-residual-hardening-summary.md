# 40단계 잔여 구조·PostgreSQL hardening 요약

- 구현일: 2026-08-01
- Git 작업: 수행하지 않음

## Frontend editor 분리

`useDashboardEditor.ts`를 추가해 다음 편집 명령을 `ManufacturingApp.tsx`에서 분리했다.

- tab 활성화
- tab 순서 변경
- board 이동
- board 설정 변경
- board 숨김
- board 삭제
- board 복제
- custom tab 추가
- catalog board 추가
- 공통 draft update/dirty 처리

`ManufacturingApp.tsx`는 약 806줄에서 약 737줄로 감소했다.

## Router handler 이동

실제 handler 구현을 다음 router로 이동했다.

- `routers/auth.py`
- `routers/admin.py`
- `routers/system.py`
- `routers/ontology.py`

이 router들은 더 이상 handler를 `main.py`에서 import하지 않는다. Auth, admin, system handler는 기존 main 구현에서도 제거했다.

`main.py`는 약 1,263줄에서 약 823줄로 감소했다.

Dashboard, export, planner, role-workspace, manufacturing router는 아직 일부 handler를 main module에서 import한다.

## PostgreSQL runtime foundation

추가:

- `postgresql.py`
  - optional psycopg loader
  - organization-scoped transaction
  - `app.organization_id` session binding
- `postgresql_ontology_repository.py`
  - object snapshot replace
  - link snapshot replace
  - object list/detail
  - link list
  - ingestion run

현재 Python 환경에는 psycopg가 설치되어 있지 않으므로 PostgreSQL repository 객체를 실제 애플리케이션 runtime에 연결하지 않았다. `api[postgres]` 설치 후 연결 가능하다.

## 실제 PostgreSQL integration check

`check_postgresql_migration.py`를 release gate에 추가했다.

검증 과정:

1. 임시 PostgreSQL 14 cluster 생성
2. database 생성
3. PostgreSQL migration 적용
4. 필수 테이블 9개 확인
5. Ontology RLS 5개 확인
6. 조직 A/B object 삽입
7. non-superuser tenant role로 조직 A session 설정
8. 조직 A object만 조회되는지 검증
9. cluster 종료 및 임시 파일 제거

검증 결과:

```text
Org A session visible objects: object-a
Org B object visibility: blocked by RLS
PostgreSQL migration/RLS check: PASS
```

## 남은 제한

- 기존 identity/dashboard/export/workflow/legacy manufacturing repository는 아직 SQLite implementation이다.
- 전체 runtime을 PostgreSQL로 전환하려면 SQL placeholder, JSON serialization, connection/transaction, migration lifecycle을 repository별로 변환해야 한다.
- physical legacy source directory는 도구에 삭제/rename 기능이 없어 현재 작업 세션에서 제거하지 못했다.
- canonical import는 legacy namespace를 이미 차단하고 있다.
- dashboard/export/planner/role-workspace/manufacturing handler의 물리적 feature module 이동은 추가 작업 대상이다.
