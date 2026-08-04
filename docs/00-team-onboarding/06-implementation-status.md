# 구현 상태와 경계

기준 브랜치: `prototype/ontology-dashboard-prebuild`

검증 태그: `team-share-capture-integrity-20260804`

## 상태 정의

- **연결 완료:** UI, API, 저장소와 자동 검증이 연결됨
- **UI·계약 완료:** UI와 경계는 있으나 외부 authoritative engine 연결이 후속
- **환경 의존:** 코드 경계는 있으나 외부 인프라·자격증명이 필요
- **후속 범위:** 현재 제품 흐름에 포함하지 않음

## 기능 Matrix

| 영역 | 상태 | 구현 내용 | 남은 경계 |
|---|---|---|---|
| 회원가입·승인 | 연결 완료 | 희망 역할, pending, 관리자 알림, 승인 | 외부 이메일·Slack 알림 |
| 역할·Workspace·권한 | 연결 완료 | 역할, scope, permission allow/deny, audit | 대규모 조직 SCIM·SSO |
| 역할별 첫 화면 | 연결 완료 | 매니저·임원 Report, 실무자 Dashboard | 역할 정책의 팀 확정 |
| 보고서 | 연결 완료 | 공용 draft revision, Evidence 시각화, 편집·열람 | 결재·반려·코멘트 workflow |
| Dashboard 편집 | 연결 완료 | Tab, Board, drag, resize, hide, saved view, cross-filter | 다중 사용자 실시간 협업 |
| Dataset 적응형 구성 | 연결 완료 | Schema signal 기반 Board definition·배치 선택 | 고객별 semantic rule 관리 UI |
| Team Share 캡처 무결성 | 연결 완료 | 관리자 셸, Report 준비, 8개 Board, ECharts finished·Canvas pixel 검증 | 브라우저별 visual baseline 확장 |
| 사용자별 Preference | 연결 완료 | Dashboard와 Display 계정 저장·격리 | 조직 정책 기반 설정 강제 |
| Analysis | 연결 완료 | Path·Canvas·Graph, 실행, 결과, materialization | 대규모 distributed execution |
| Forecast Editor | UI·계약 완료 | Range, model, horizon, confidence band | authoritative prediction service |
| Ontology Explorer | 연결 완료 | 검색, Inspector, ObjectSet, traversal, action | 외부 Graph 운영 인프라 |
| Dataset Catalog | 연결 완료 | immutable version, schema, projection, lineage | managed object storage 운영화 |
| Agent Evidence | 연결 완료·환경 의존 | route, evidence, claim, trace, fallback | 외부 LLM·Vector·Graph credentials |
| Governance | 연결 완료 | Run audit, claim/evidence, lineage, checkpoint | 장기 보존·규제 정책 |
| Export | 연결 완료 | JSON·CSV·PDF, hash, checkpoint | 배포 환경 object storage |
| 실제 설비 제어 | 후속 범위 | 의도적으로 미연결 | 안전 승인·OT integration 필요 |

## 자동 검증

현재 핵심 검증:

```text
Backend targeted tests        18 passed
Frontend unit tests           16 passed
Team-share capture E2E         1 passed / 15 screenshots
Team-share Story E2E           5 passed / 4 viewports + interaction
```

검증 명령:

```bash
export PYTHONPATH="$PWD/api:$PWD/ml/src"
.venv/bin/pytest -q tests/test_auth_rbac.py tests/test_dashboard_stages20_24.py

cd web
npm run lint
npm test
npm run build
```

## 공유할 때 구분해야 하는 내용

### 그대로 동작하는 제품 흐름

- 가입·관리자 승인
- 역할별 메인 화면
- 실무자 보고서 작성과 매니저 열람
- Dataset별 Dashboard 구성 전환
- 사용자별 preference 저장
- Analysis와 Ontology 탐색

### 구조 검증 목적이 강한 영역

- 전체 Palantir Board Catalog
- Forecast 수식과 모델 설정 UI
- 외부 Graph·Vector·LLM 운영 연결
- 모든 역할의 최종 고객별 업무 용어

## 기준 태그

```text
team-share-capture-integrity-20260804
```

팀이 기능을 채택하기 전 상태로 돌아갈 때는 태그를 삭제하거나 reset하지 않고 별도 브랜치로 확인한다.

