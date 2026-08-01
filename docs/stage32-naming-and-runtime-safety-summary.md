# 32단계 구현 요약 — Ontology Dashboard canonical naming과 runtime safety

- 구현일: 2026-08-01
- Git 작업: 수행하지 않음
- Release gate: 11/11 PASS

## 1. Canonical namespace

새 canonical API namespace:

```text
ontology_dashboard
```

새 canonical ASGI entrypoint:

```text
ontology_dashboard.app:app
```

기존 `factory_signal_board` package는 한시적인 compatibility namespace로 유지한다. 신규 테스트, 실행 스크립트와 배포 entrypoint는 canonical namespace를 사용한다.

## 2. Manufacturing ML namespace

새 canonical ML namespace:

```text
ontology_dashboard_manufacturing_ml
```

새 distribution과 CLI:

```text
ontology-dashboard-manufacturing-ml
ontology-dashboard-manufacturing-ml
```

기존 ML package와 CLI는 migration compatibility를 위해 유지한다.

## 3. Service naming

제조 vertical slice service의 canonical class 이름을 다음으로 변경했다.

```text
ManufacturingPredictiveMaintenanceService
```

기존 `FactorySignalService` 이름은 임시 alias로만 유지한다.

## 4. Runtime·deployment naming

변경:

- API distribution: `ontology-dashboard-api`
- CI: `ontology-dashboard-ci`
- DB env: `ONTOLOGY_DASHBOARD_DATABASE_URL`, `ONTOLOGY_DASHBOARD_DB`
- DB default: `ontology_dashboard.db`
- JSON Schema host: `ontology-dashboard.local`
- Gold suite: `ontology-dashboard-manufacturing-gold-v1`
- Docker·local·release gate entrypoint: `ontology_dashboard.app:app`

기존 `FACTORY_SIGNAL_DB`와 이전 DB 파일은 deprecation warning과 자동 감지를 통해 한시 호환한다.

## 5. Canonical naming gate

`scripts/check_canonical_naming.py`를 release gate에 추가했다.

검사 대상:

- 사용자 노출 제품명
- schema host
- CI 이름
- 신규 runtime의 legacy API import
- 신규 runtime의 legacy ML import

현재 58개 사용자·runtime 파일에서 violation 0건이다.

## 6. Production fail-fast

production 설정 오류를 startup에서 차단한다.

차단 조건:

- demo account seed 활성화
- HTTPS CORS origin 미설정 또는 잘못된 origin
- SQLite-only persistence인데 명시적 pilot 승인 없음
- 아직 지원하지 않는 PostgreSQL URL 설정

현재 persistence는 SQLite 전용이므로 일반 production 시작은 기본적으로 차단한다. 제한된 단일 instance pilot만 다음 설정으로 명시적으로 허용할 수 있다.

```text
ONTOLOGY_DASHBOARD_ALLOW_PRODUCTION_SQLITE=1
```

PostgreSQL URL은 repository migration이 완료될 때까지 fail-fast한다.

## 7. 검증

```text
Canonical naming: PASS, 58 files, 0 violations
Runtime settings tests: 5 PASS
Backend tests: 58 PASS
Gold scenarios: 8/8 PASS
Playwright: 13 PASS
TypeScript: PASS
Production build: PASS
Release gate: 11/11 PASS
```

## 8. 남은 구조 작업

- 실제 source file을 `api/ontology_dashboard` 하위 domain module로 이동
- `factory_signal_board` compatibility namespace 제거 release
- PostgreSQL·migration·transaction 도입
- `main.py` router 분리
- `ManufacturingApp.tsx` orchestration 분리
- organization tenant isolation
