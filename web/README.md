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
src/features/manufacturing/      Manufacturing data orchestration and governed renderer adapter
src/features/dashboard/          persistent shell, tabs, context, canvas, inspector and catalog
src/features/roles/              Executive·Audit·Field·FDE·Model 전용 board renderer와 contracts
src/features/planner/            자연어 Object query·Board 추천·grounded narrative·Dashboard draft UI
src/features/admin/              tenant administrator control plane와 workflow approvals
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

- 실제 계정 role별 persistent default template과 허용 Action
- workspace selector, Dashboard tabs, context panel, 12-column canvas와 inspector
- 위험 사건 선택과 우선순위
- 역할·intent별 동적 블록 순서
- 센서 SVG 차트, 기여 요인, Evidence 표
- permission이 있는 role만 판단·메모·체크리스트 저장
- 제한된 후속 질문과 화면 재구성
- 데이터 품질·LLM fallback 시각화
- 가입 승인, 비활성화, 역할·workspace scope 설정
- 관리자 audit와 FDE/tenant-admin 경계 표시
- tab·board drag order, width, hide/show, duplicate, delete와 custom tab
- 역할별 Board Catalog 검색·category와 plain text board
- 개인 설정 저장·reload 복원, role default restore와 Saved View
- parameter dependency graph, affected board 표시, fullscreen과 share link
- FDE 역할 template preview·승인 요청과 tenant-admin version publish
- 임원 조직 위험·영향·미조치 사건과 drill-down
- 품질·감사 사건 재구성·version·Evidence trace·export checkpoint
- 390px 모바일 현장 task·안전·측정·사진 metadata·상태 Action
- FDE customer workspace·ontology registry·deployment·diagnostic Workbench
- 데이터 사이언티스트 threshold cost·slice·drift·Gold regression·release 요청
- 관리자 Template·Model Workflow Approvals
- FDE Planner Assistant의 registry·Catalog·Evidence whitelist preview
- PDF·CSV·JSON export format selector와 browser artifact download
- Planner draft의 non-persisted Canvas 적용과 별도 승인 요청 경계

`App.tsx`는 더 이상 대시보드 구현을 포함하지 않고 route와 인증 상태만 조정한다.

## 검증

```bash
npm test
npm run lint
npm run build
npm run test:e2e
```

Playwright E2E는 FastAPI가 함께 실행 중이어야 한다. 전체 자동 실행은 루트의 `scripts/release_gate.py --with-e2e`를 사용한다.
