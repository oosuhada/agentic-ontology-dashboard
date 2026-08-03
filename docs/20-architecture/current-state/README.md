# Architecture

현재 구현 구조는 [`current-state.md`](./current-state.md)에 기록한다.

핵심 경계:

```text
Data and Model
→ Versioned Risk Policy
→ Evidence Package
→ Grounded Report
→ Governed UI Planner
→ FastAPI
→ React Role Views
→ SQLite Audit
```

원칙:

- 모델과 운영 임계값은 버전별로 결합하되 파일과 책임은 분리한다.
- UI와 리포트는 모델 객체가 아니라 Evidence Package만 사용한다.
- LLM은 Evidence의 상태·결정·수치를 변경할 수 없다.
- LLM은 임의 UI 코드를 만들지 않고 등록된 블록만 선택한다.
- 프로젝트 3은 Maintenance Context Adapter 뒤에 위치한다.
- 외부 서비스 장애는 검증된 deterministic fallback으로 격리한다.
- 실제 설비 제어는 아키텍처에 포함하지 않는다.

중요한 변경은 `docs/20-architecture/adr/`에 기록한다.
