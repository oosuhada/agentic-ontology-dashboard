# 현재 API 계약

## 인증

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/auth/login` | 이메일·비밀번호로 session과 CSRF token 생성 |
| POST | `/api/auth/logout` | 현재 session 폐기, CSRF 필요 |
| GET | `/api/auth/me` | 현재 Principal과 scope 조회 |

회원가입, 공개 비교 세션, Admin 사용자 관리, display preference API는 현재 제품 계약에서 제외합니다.

## Project

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/projects` | Principal이 접근 가능한 Project 목록 |
| GET | `/api/projects/{project_id}` | Project 상세 |
| GET | `/api/projects/{project_id}/workspaces` | Project Workspace 목록 |
| GET | `/api/projects/{project_id}/events` | Canonical 장애 시 사용할 Project-scoped Event |

## Canonical Predictive Maintenance

Base path:

```text
/api/projects/{project_id}/workspaces/{workspace_id}/predictive-maintenance
```

현재 UI의 필수 API는 다음 두 개입니다.

| Method | Path | 설명 |
|---|---|---|
| GET | `/dashboard` | 데이터 출처, Event, 선택 상세, Evidence/Report 문맥 |
| GET | `/results/latest` | 자산별 최신 Result Artifact 목록 |

데이터 운영과 검증을 위해 `/context`, `/versions`, `/selection`, `/release`, `/snapshots/{prediction_id}`, `/timeline`, `/observations`, `/replay/sessions` 계열도 유지합니다.

## Event 업무 API

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| GET | `/api/events/{event_id}/evidence` | `events.read` | 검증된 Evidence Package |
| POST | `/api/events/{event_id}/report` | `events.read` | 역할별 Report 생성 |
| POST | `/api/events/{event_id}/decision` | `events.decision` | 사람의 실제 운영 판단 기록 |
| POST | `/api/events/{event_id}/notes` | `events.note` | 현장 메모 기록 |
| GET | `/api/events/{event_id}/activity` | `events.read` | Decision·Note·Conversation 이력 |

## 오류 계약

- 인증 없음: `401 authentication_required`
- 권한 없음: `403 permission_denied` 또는 scope 관련 code
- active Project 불일치: `409 active_project_mismatch`
- 계약 검증 실패: `422 contract_validation_failed`
- Canonical Runtime에 PostgreSQL이 없음: `503`
- 존재하지 않는 현재 API 경로: 표준 `404`

상태 변경 요청은 `X-CSRF-Token` header가 필요합니다.
