# 역할과 Action 계약

## 제품 역할

| UI 역할 | Demo 계정 | 주요 권한 | 기본 관점 |
|---|---|---|---|
| 관리자·임원 | `manager@ontology.local` | `events.read`, `events.decision` | Overview, Operations, Executive Report |
| 실무 엔지니어 | `engineer@ontology.local` | `events.read`, `events.note` | Objects, Evidence, 현장 메모 |

백엔드에 다른 seed identity가 남아 있더라도 로그인 화면과 현재 제품 계약은 이 두 역할만 사용합니다.

## Decision

관리자·임원만 `/api/events/{event_id}/decision`을 호출할 수 있습니다.

```json
{
  "decision": "request_inspection",
  "note": "다음 교대 전 점검"
}
```

지원 판단 예시는 `request_inspection`, `review_shutdown`, `defer`입니다. `review_shutdown`은 정지 여부를 사람이 검토한다는 뜻이며 자동 정지 명령이 아닙니다.

## Note

실무 엔지니어는 `/api/events/{event_id}/notes`에 현장 점검 결과를 기록합니다.

```json
{
  "body": "공구 상태와 센서 연결을 확인했습니다."
}
```

## 감사 원칙

- client가 전달한 actor 문자열은 신뢰하지 않음
- 서버가 인증 Principal의 display name을 actor로 기록
- Recommendation, Decision, Note를 서로 다른 의미로 저장
- Activity에서 시간순으로 재구성 가능해야 함
- Decision과 Note는 CSRF 검증을 통과해야 함
