# 팀 공유 패키지 검증 보고서

검증 기준:

- Tag: `team-share-audit-ready-20260804`
- 검증일: 2026-08-04
- 공개 Story: `/team-share`
- 검증 데이터: Playwright 격리 SQLite DB와 demo seed

## 이번 재검증에서 확인한 문제

기존 Story 검증은 1440×1000 데스크톱 한 종류만 포함했다. 실제 390×844 모바일 검증을 추가하자 캡처가 294px까지 줄어 세부 텍스트를 읽기 어려운 문제가 확인됐다.

다음 항목도 코드상 아직 없었다.

- 현재 섹션을 표시하는 Sticky Navigation
- 특정 섹션을 바로 공유하는 URL hash
- 캡처 Lightbox
- 검증 Tag·날짜·테스트 결과 표시
- 구현 수준을 설명하는 구체적인 연결 항목
- 팀 피드백 양식 복사

## 반영한 개선

### 반응형 화면

- 1440×1000
- 1024×768
- 768×1024
- 390×844

네 viewport에서 가로 overflow가 없음을 측정한다. 모바일에서는 설명 카드의 중복 padding을 줄여 핵심 캡처 폭을 320px보다 크게 유지한다.

### 탐색과 공유

- `#overview`
- `#user-flow`
- `#roles`
- `#adaptive`
- `#workbenches`
- `#capabilities`
- `#review`

Sticky Navigation은 현재 섹션에 `aria-current="location"`을 표시한다. 따라서 팀 채팅에서 `/team-share#adaptive`처럼 특정 논의 지점을 바로 공유할 수 있다.

### 캡처 확인

모든 캡처는 클릭하면 Lightbox로 확대된다.

- `Esc`로 닫기
- 배경 클릭으로 닫기
- 원본 이미지 새 탭 열기
- 모바일에서도 확대 버튼 상시 표시

### 구현 상태 표현

기존 `Mixed`, `Runtime`, `API + UI`처럼 해석이 필요한 상태명을 제거했다. 각 기능 카드에 실제 연결 항목을 표시한다.

예시:

```text
Role Reports
End-to-end prototype
UI · API · Revision DB · Permission · E2E
```

### 문서 구조

기존 루트 문서와 루트 수준의 ADR·current-state 디렉터리는 목적별 폴더로 물리 이동했다. `docs/document-registry.json`과 `scripts/check_docs_structure.py`가 다음을 검증한다.

- 목적별 번호 폴더와 실제 하위 폴더 존재
- 팀 온보딩·제품·아키텍처·운영 필수 문서 존재
- `docs/README.md` 외 루트 Markdown 생성 차단
- 폐기된 과거 경로 재생성 차단
- Markdown 로컬 링크와 이미지 존재

새 문서는 더 이상 `docs/` 루트에 만들지 않는다.

물리 정리 결과:

```text
이동한 문서                    64개
docs 루트 Markdown             README.md 1개
목적별 필수 디렉터리           17개
필수 진입 문서                 33개
검사한 Markdown 로컬 링크      128개
깨진 링크                      0개
폐기된 과거 경로               0개
과거 경로 문자열 참조          0건
```

일회성 이동과 링크 재계산은 `scripts/migrate_docs_to_purpose_folders.py`로 수행했다. 이동 완료 후 재실행하면 변경 없이 종료한다.

## 자동 검증

전체 팀 공유 패키지:

```bash
cd web
npm run verify:team-share
```

```text
Backend targeted tests      18 passed
Frontend unit tests         16 passed
Team-share Story E2E         1 passed
Responsive Story E2E         4 passed
TypeScript lint              passed
Production build             passed
Documentation structure      passed
```

## 현재 남은 공유 제약

`http://127.0.0.1:3100/team-share`는 로컬 주소다. 팀원이 설치 없이 외부에서 바로 보려면 이후 다음 중 하나가 필요하다.

1. GitHub Pages 정적 export
2. Vercel 또는 Netlify preview
3. 팀 공용 개발 서버

현재 Prototype 브랜치와 전체 Story 캡처만으로도 비동기 검토는 가능하지만, 인터랙티브 공유에는 배포 주소가 필요하다.
