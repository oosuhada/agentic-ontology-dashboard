# Web

Vite·React 기반 역할별 대시보드다. API가 반환한 `UILayout`의 등록된 블록만 렌더링한다.

## 실행

```bash
npm install --no-audit --no-fund
npm run dev
```

기본 주소: `http://127.0.0.1:3100`

## 기능

- 매니저·엔지니어 역할 전환
- 위험 사건 선택과 우선순위
- 역할·intent별 동적 블록 순서
- 센서 SVG 차트, 기여 요인, Evidence 표
- 판단·메모·체크리스트 저장
- 제한된 후속 질문과 화면 재구성
- 데이터 품질·LLM fallback 시각화

## 검증

```bash
npm test
npm run lint
npm run build
npm run test:e2e
```

Playwright E2E는 FastAPI가 함께 실행 중이어야 한다. 전체 자동 실행은 루트의 `scripts/release_gate.py --with-e2e`를 사용한다.
