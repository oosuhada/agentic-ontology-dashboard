# Ontology Dashboard Web

Vite·React 기반 역할별 운영 애플리케이션이다. API가 반환한 `UILayout`의 등록된 블록만 렌더링하고, identity와 permission은 서버 계약을 기준으로 사용한다.

## 실행

```bash
npm install --no-audit --no-fund
npm run dev
```

기본 주소: `http://127.0.0.1:3100/login`

## 기능별 구조

```text
src/App.tsx                       route/auth orchestration
src/features/auth/               login, register, pending, AuthContext
src/features/manufacturing/      Manufacturing Predictive Maintenance Pack
src/features/admin/              tenant administrator control plane
src/features/ontology/types.ts   Object·Link·Action TypeScript contracts
src/components.tsx               registered governed UI block renderer
src/api.ts                        credentials + CSRF aware API client
```

## route

- `/login`
- `/register`
- `/pending`
- protected `/app`
- tenant-admin-only `/admin`

## 현재 기능

- 실제 계정 role별 기본 landing과 허용 Action
- workspace와 Manufacturing Predictive Maintenance Pack 표시
- 위험 사건 선택과 우선순위
- 역할·intent별 동적 블록 순서
- 센서 SVG 차트, 기여 요인, Evidence 표
- permission이 있는 role만 판단·메모·체크리스트 저장
- 제한된 후속 질문과 화면 재구성
- 데이터 품질·LLM fallback 시각화
- 가입 승인, 비활성화, 역할·workspace scope 설정
- 관리자 audit와 FDE/tenant-admin 경계 표시

`App.tsx`는 더 이상 대시보드 구현을 포함하지 않고 route와 인증 상태만 조정한다.

## 검증

```bash
npm test
npm run lint
npm run build
npm run test:e2e
```

Playwright E2E는 FastAPI가 함께 실행 중이어야 한다. 전체 자동 실행은 루트의 `scripts/release_gate.py --with-e2e`를 사용한다.
