# 15분 팀 데모 가이드

## 실행

```bash
cp .env.example .env
bash scripts/run_local.sh
```

```text
Web     http://127.0.0.1:3100/
API     http://127.0.0.1:8100/docs
```

## Demo 1 — 가입과 관리자 승인 · 3분

1. `/register`에서 새 사용자를 생성한다.
2. 희망 역할로 `도메인 엔지니어`를 선택한다.
3. 가입 후 `pending_approval` 화면을 확인한다.
4. 관리자 계정으로 로그인한다.
5. `Notifications`에서 신규 가입 요청을 연다.
6. 역할을 `운영 매니저`로 변경한다.
7. Manufacturing Workspace를 할당한다.
8. permission override 하나를 차단한 뒤 승인한다.
9. 승인된 계정으로 로그인해 Reports가 첫 화면인지 확인한다.

관리자 계정:

```text
admin@ontology.local
OntologyAdmin!2026
```

## Demo 2 — 실무자 작성, 매니저 검토 · 4분

### 엔지니어

```text
engineer@ontology.local
Engineer!2026
```

1. 로그인 후 Dashboard가 첫 화면인지 확인한다.
2. `Reports`로 이동한다.
3. `Edit report`를 선택한다.
4. 제목이나 요약을 수정하고 저장한다.
5. 로그아웃한다.

### 운영 매니저

```text
manager@ontology.local
Manager!2026
```

1. 로그인 후 Reports가 첫 화면인지 확인한다.
2. 엔지니어가 수정한 제목과 요약을 확인한다.
3. 텍스트 섹션과 오른쪽 근거 시각화의 연결을 설명한다.
4. `Open detailed dashboard`로 상세 화면을 연다.
5. 다시 로그인했을 때 Reports로 복귀하는지 확인한다.

## Demo 3 — Dataset별 적응형 화면 · 3분

FDE 계정:

```text
fde@ontology.local
FDE!2026
```

Project 선택에서 다음 순서로 전환한다.

```text
Manufacturing Demo Project
→ Azure Fleet Maintenance
→ MetroPT Compressor Monitoring
```

설명할 포인트:

- 상단 문구만 바뀌는 것이 아니다.
- Board definition 목록이 달라진다.
- 첫 행 폭과 정보 구조가 달라진다.
- Factory는 위험·원인·점검, Fleet은 서비스·운행 영향, Compressor는 시계열·이상 구간 중심이다.

## Demo 4 — 사용자별 개인화 · 2분

1. 엔지니어 Dashboard에서 Board 하나를 즐겨찾기한다.
2. `Personalized for this user` 상태를 확인한다.
3. Display 메뉴에서 Accessible preset을 선택한다.
4. 로그아웃하고 localStorage를 지운 뒤 재로그인해 설정이 복원되는 것을 설명한다.
5. 현장 작업자 계정에서는 해당 설정이 보이지 않는 것을 확인한다.

## Demo 5 — Analysis와 Ontology · 3분

1. Analysis에서 `Path → Canvas → Graph`를 전환한다.
2. DataPill과 Compatible action을 설명한다.
3. Graph에서 계산 노드와 Dependency를 보여준다.
4. Ontology로 이동해 객체 두 개를 선택한다.
5. `Union`으로 적용한다.
6. 선택 ObjectSet을 기준으로 관계 탐색이 가능하다고 설명한다.

## 데모에서 하지 말아야 할 주장

- 실제 공장 제어를 자동화한다고 말하지 않는다.
- Forecast UI를 실제 운영 예측 엔진이라고 설명하지 않는다.
- 모든 외부 Graph·LLM 인프라가 배포 완료됐다고 말하지 않는다.
- 모든 버튼이 production 운영 수준이라고 표현하지 않는다.

