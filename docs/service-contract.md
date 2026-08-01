# Factory Signal Board Service Contract

## 서비스 경계

```text
Gold/AI4I-compatible input
→ model or deterministic predictor
→ operational threshold policy
→ Evidence Package
→ grounded report agent
→ governed layout planner
→ FastAPI
→ React manager/engineer dashboard
```

React는 모델 모듈을 import하지 않는다. Report와 Layout은 Evidence Package만 참조한다.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | 서비스와 offline-capable 상태 확인 |
| GET | `/api/equipment` | 설비 목록 |
| GET | `/api/equipment/{equipment_id}` | 설비와 연결 사건 |
| GET | `/api/events` | 위험 우선순위 사건 목록 |
| GET | `/api/events/{event_id}` | 원본 fixture 사건과 사용자 활동 |
| GET | `/api/events/{event_id}/evidence` | 검증된 Evidence Package |
| POST | `/api/events/{event_id}/report` | 역할별 Report 생성 |
| POST | `/api/events/{event_id}/layout` | 역할·intent별 governed Layout 생성 |
| POST | `/api/events/{event_id}/decision` | 사람의 판단 기록 |
| POST | `/api/events/{event_id}/notes` | 점검·전달 메모 기록 |
| POST | `/api/events/{event_id}/follow-up` | 제한된 후속 질문과 화면 재구성 |
| GET | `/api/events/{event_id}/activity` | 판단·메모·대화 이력 |
| POST | `/api/demo/reset` | 로컬 데모 상태 초기화 |
| GET | `/api/openapi-contract` | OpenAPI 문서 JSON |

## 역할별 요청 예시

```json
{
  "role": "manager",
  "use_llm": true
}
```

```json
{
  "role": "engineer",
  "intent": "explain-risk",
  "use_llm": true
}
```

## 오류 계약

```json
{
  "error": {
    "code": "not_found",
    "message": "resource not found: EVT-UNKNOWN"
  }
}
```

```json
{
  "error": {
    "code": "contract_validation_failed",
    "message": "..."
  }
}
```

Provider 오류는 사용자 요청 실패로 전파하기보다 검증된 결정론적 fallback으로 처리한다. 내부 자격 증명과 상세 예외는 응답에 포함하지 않는다.

## 감사 계약

SQLite는 다음 테이블을 가진다.

- `decisions`
- `notes`
- `conversations`
- `audit_log`

모델·Evidence·리포트·Layout 생성에는 `event_id`, `run_id`, `model_version`과 핵심 trace를 남긴다. 이는 실제 CMMS 작업 지시가 아니라 로컬 데모 감사 기록이다.

## CORS와 로컬 포트

- API: `127.0.0.1:8100`
- React: `127.0.0.1:3100`
- 허용 origin은 로컬 개발 주소로 제한한다.

## 안전 경계

- 설비 제어 API가 없다.
- 결정·점검·정지 검토는 사람이 기록한다.
- 미등록 UI Block과 data field는 Planner validation에서 차단된다.
- 후속 질문은 허용된 intent만 지원한다.
- prompt injection 또는 실제 제어 요청은 지원 범위 밖으로 처리한다.
