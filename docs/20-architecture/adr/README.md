# Architecture Decision Records

중요한 기술·제품 결정을 다음 형식으로 기록한다.

```text
# ADR-NNN 제목

- 상태: proposed | accepted | superseded
- 맥락
- 결정
- 대안
- 결과와 trade-off
- 검증 근거
```

초기 ADR 후보:

1. React를 최종 사용자 UI로 선택
2. Evidence Package를 모델·리포트·UI의 공통 계약으로 사용
3. 완전 자유 생성형 UI 대신 등록된 UI Block 사용
4. 규칙 기반 리포트를 LLM fallback으로 유지
5. 프로젝트 3 연결을 Adapter로 격리
