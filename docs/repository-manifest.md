# 저장소 유지 경계

## 유지하는 영역

| 경로 | 책임 |
|---|---|
| `web/src/features/mvp` | 현재 네 화면과 ViewModel/Adapter |
| `web/src/features/auth` | 두 역할 로그인과 session UI |
| `web/src/features/predictive-maintenance/types.ts` | Canonical Runtime 타입 |
| `api/ontology_dashboard/routers` | 현재 등록 Router |
| `api/ontology_dashboard/predictive_maintenance_runtime` | Canonical V3.1 조회와 replay |
| `api/migrations` | 이미 적용된 DB의 forward-upgrade를 위한 immutable migration history |
| `api/ontology_dashboard/service.py` | Gold Fixture Evidence/Report fallback |
| `data/fixtures` | 8개 검증 시나리오 |
| `schemas` | 현재 ingest, Result, Evidence, Report 계약 |
| `ml` | Fixture 예측과 Evidence 생성 |
| `scripts` | 현재 실행·적재·검증·백업 도구 |
| `tests` | 현재 MVP와 Canonical 계약 |

## 제거한 영역

- V1, V2, V3, V4와 comparison frontend
- 범용 Dashboard authoring, Analysis, Agent, Governance, Modeling, Admin frontend
- Team Share와 Palantir 복제용 페이지·visual baseline
- 단계별 개발 prompt, stage history, 완료 보고서 중복본
- 종료된 화면의 E2E와 screenshot snapshot
- 회원가입·Admin·공개 비교 API route

## 판단 기준

파일을 유지하려면 다음 중 하나를 만족해야 합니다.

1. 현재 ASGI 또는 React entrypoint에서 도달 가능
2. Canonical V3.1 데이터 적재·조회·검증에 필요
3. 현재 배포·백업·복원에 필요
4. 현재 계약 테스트가 직접 검증
5. 이 문서 세트가 현재 제품 동작을 설명하는 데 필요

Git history가 과거 구현을 보존하므로 현재 working tree에 별도 archive 디렉터리를 두지 않습니다.

단, 적용된 DB migration은 예외입니다. 과거 기능명이 포함된 migration 파일도 배포된 schema upgrade chain을 깨지 않기 위해 삭제·개명·수정하지 않습니다. 이 파일을 유지해도 종료된 API나 화면이 다시 활성화되지는 않습니다.

이번 수렴 기준으로 추적 파일은 954개에서 271개로 축소되었습니다.
