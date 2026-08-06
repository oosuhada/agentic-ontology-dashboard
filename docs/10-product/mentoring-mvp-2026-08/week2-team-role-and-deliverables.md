# Week 2 역할 분담 및 산출물 정의

- 문서 상태: `Week 2 execution baseline`
- 기준일: `2026-08-06`
- 근거: 2026년 8월 6일 오전 멘토링 결과 및 팀 역할 재조정
- 기준 데이터: `UCI AI4I 2020 Manufacturing Predictive Maintenance — Physics & Maintenance Canonical V3.1`
- 연관 문서:
  - [MVP 범위 및 4개 화면 명세서](./mvp-scope-and-screen-specification.md)
  - [MVP API 명세서](./mvp-api-specification.md)
  - [MVP 데이터 계약서](./mvp-data-contract.md)

## 1. 문서 목적

이 문서는 2주차에 진행할 팀원별 작업을 실제 구현 범위, 협업 관계, 산출물과 완료 기준까지 포함한 실행 단위로 정의한다.

2주차의 공통 목표는 다음 세 가지다.

1. 요구사항 정의서 작성
2. MVP를 어떻게 구현할지 설명하는 설계 계획서 작성
3. 실제로 확인할 수 있는 MVP 화면 공유

이번 주에는 전체 제품 기능을 확장하기보다 멘토링에서 확정한 네 개 화면과 두 개 사용자 그룹에 집중한다.

```text
Canonical V3.1
→ 데이터·예측 파이프라인 및 재현성 확보
→ 예측 결과 조회 API 제공
→ Overview·Objects·Operations 화면 연결
→ LLM 기반 리포트 생성
→ 임원 보고서 화면 제공
```

## 2. 멘토링에서 확정된 MVP 기준

### 2.1 데이터

- Canonical V3.1을 MVP의 단일 기준 데이터로 사용한다.
- 새로운 데이터셋을 다시 찾거나 교체하는 작업은 이번 범위에 포함하지 않는다.

### 2.2 화면

MVP 화면은 다음 네 개로 제한한다.

1. `V2 · Blueprint 1차`의 Overview
2. `V2 · Blueprint 1차`의 Objects
3. `V2 · Blueprint 1차`의 Operations
4. `V1 · 기존 Dashboard`의 임원 보고서 View

`Analysis` 화면은 이번 MVP에서 제외한다.

### 2.3 사용자

핵심 사용자 범위는 다음 두 그룹으로 축소한다.

- 생산 관리자
- 현장 담당자

시스템 관리자, 모델 검증 담당자와 품질 감사 담당자 등 전체 역할 확장은 MVP 이후 단계로 미룬다.

### 2.4 모델링

- 미탐과 오탐의 적정 비율은 산업·업종·고객 요구에 따라 달라진다.
- 하나의 임계값을 절대적인 정답으로 주장하지 않는다.
- 고객의 안전 우선순위와 점검 비용에 따라 적절한 임계값 후보를 제안하는 방향으로 설계한다.

## 3. 최종 역할 요약

| 담당 | 팀 역할 | 핵심 책임 | 주요 산출물 |
|---|---|---|---|
| 우수 | 팀원1 | MVP 프론트엔드와 화면 연결 | 4개 화면, API 연결, 화면 링크, 화면 캡처, 사용자 흐름 |
| 광우 | 팀원2 | 요구사항·리포트·스키마·기능·API·MVP 설계 문서화 | 요구사항 정의서, 리포트 정의서, 스키마 정의서, 기능 명세서, API 명세서, MVP 설계 명세서 |
| 성민 | 팀원3 | 예측 결과 조회 API와 데이터·예측 파이프라인 및 재현성 | 조회 API, 파이프라인, Manifest, Checksum, 재현성 검증 결과 |
| 호범 | 팀원4 | LLM을 활용한 백엔드 리포트 자동 생성 | 리포트 생성 API, Prompt·Schema, 근거 기반 생성, 검증 및 예시 결과 |

## 4. 역할 간 연결 구조

```text
성민
Canonical V3.1 → Feature → Prediction → Result Artifact
                    ↓
              GET /predictions API
                    ↓
우수                                      호범
Overview·Objects·Operations  ←→  LLM 리포트 자동 생성
                    ↑                  ↓
                    └──── 임원 보고서 View

광우
사용자 요구·화면·스키마·기능·API·리포트 계약을 문서로 고정
→ 세 구현 담당자가 같은 계약을 사용하도록 연결
```

역할별 핵심 질문은 다음과 같다.

| 담당 | 핵심 질문 |
|---|---|
| 우수 | 사용자가 무엇을 보고 어떤 순서로 클릭하는가? |
| 광우 | 어떤 요구사항과 계약을 기준으로 기능을 구현해야 하는가? |
| 성민 | 화면과 LLM이 사용할 예측 결과를 어떻게 안정적으로 생성·조회하는가? |
| 호범 | 예측 결과와 근거를 어떻게 신뢰 가능한 보고서 문장으로 변환하는가? |

---

## 5. 우수 — 팀원1 — MVP 프론트엔드와 화면 연결

### 5.1 역할 목적

우수는 다음 주에 공유할 MVP의 프론트엔드 담당자다. 화면을 새로 크게 확장하는 것보다 이미 구현된 V1·V2 화면에서 확정된 네 화면을 추려 하나의 업무 흐름으로 연결하고, 성민의 API와 호범의 리포트 생성 기능을 실제 UI에 연결하는 것이 핵심이다.

### 5.2 필수 작업

#### A. 네 개 MVP 화면 정리

| MVP 화면 | 기준 구현 | 핵심 사용자 |
|---|---|---|
| Overview | V2 · Blueprint 1차 | 생산 관리자 |
| Objects | V2 · Blueprint 1차 | 생산 관리자·현장 담당자 |
| Operations | V2 · Blueprint 1차 | 생산 관리자·현장 담당자 |
| 임원 보고서 | V1 · 기존 Dashboard | 생산 관리자·임원 |

다음 사항을 정리한다.

- `Analysis` 메뉴를 MVP 동선에서 제외
- 네 화면 사이 이동 경로 고정
- 같은 설비가 화면마다 다른 ID·상태·확률로 보이지 않도록 데이터 연결
- 미완성 기능은 숨기거나 `향후 기능`으로 명확히 표시

#### B. Overview 연결

Overview에는 최소한 다음 정보를 표시한다.

- 전체 설비 수
- 정상·주의·경고·위험 설비 수
- 고위험 설비 Top N
- 라인별 위험 현황
- 점검 또는 조치가 필요한 설비 수
- 보고서 생성 또는 임원 보고서 진입 버튼

#### C. Objects 설비 목록 연결

| 항목 | API 필드 후보 |
|---|---|
| 설비 ID | `asset_id` |
| 설비명 | `display_name` |
| 설비 유형 | `asset_type` |
| 위치 | `site`, `line`, `cell` |
| 현재 상태 | `status_grade` |
| 고장 확률 | `failure_probability` |
| 신뢰도 | `confidence` |
| 담당자 | `assigned_engineer` |
| 권장 조치 | `recommended_action` |

목록에서 설비를 선택하면 다음 상세 정보로 이어져야 한다.

- 주요 센서값
- Top factors
- 예상 고장 유형
- 권장 조치
- 데이터셋·모델 버전

#### D. 상태등급 색상 적용

| 상태 | 색상 | 표시 원칙 |
|---|---|---|
| 정상 | 초록색 | 색상 + `정상` 텍스트 |
| 주의 | 파란색 또는 회색 | 색상 + `주의` 텍스트 |
| 경고 | 주황색 | 색상 + `경고` 텍스트 |
| 위험 | 빨간색 | 색상 + `위험` 텍스트 |

색상만으로 상태를 구분하지 않는다. 텍스트와 아이콘을 함께 사용한다.

#### E. Operations 연결

- 위험 설비 Queue
- 우선순위
- 권장 조치
- 점검 요청 상태
- 담당자 또는 담당 팀
- 처리 상태
- 리포트 생성 버튼

쓰기 기능이 아직 준비되지 않았다면 읽기 전용 화면으로 범위를 제한하고, 버튼은 `MVP 데모 Action`인지 실제 저장 Action인지 구분한다.

#### F. 임원 보고서 화면 연결

- 호범의 리포트 생성 API 호출
- 생성 중·성공·실패 상태 표시
- 보고 기준 시각 표시
- 보고서 근거 설비 목록 표시
- 데이터셋·모델 버전 표시
- 생성된 문장을 사용자가 확인할 수 있도록 구성

### 5.3 협업 입력과 출력

받아야 하는 것:

- 광우: 화면·기능·필드·API·리포트 명세
- 성민: 예측 목록·상세 API와 응답 예시
- 호범: 리포트 생성 API와 응답 Schema

전달해야 하는 것:

- 화면에서 실제 필요한 필드 목록
- API 연결 중 발견한 누락 필드
- 화면별 URL과 캡처
- 사용자 흐름과 데모 순서

### 5.4 다음 주 산출물

- 실제 접속 가능한 MVP 링크
- Overview·Objects·Operations·임원 보고서 화면
- 네 화면 캡처
- 화면별 주요 기능 설명
- 사용자 흐름 설명
- API 연결 상태표
- 남은 Mock 데이터 목록

### 5.5 완료 기준

```text
Overview에서 위험 현황 확인
→ Objects에서 위험 설비 선택
→ Operations에서 조치 검토
→ 임원 보고서 생성·확인
```

- 네 화면이 모두 접근 가능하다.
- 같은 설비의 상태와 확률이 화면 간 일치한다.
- API 오류와 로딩 상태가 표시된다.
- 화면이 데스크톱과 발표용 노트북 폭에서 깨지지 않는다.

### 5.6 플러스 알파 추천 태스크

1. **역할별 첫 화면 전환**
   - 생산 관리자와 현장 담당자 역할에 따라 첫 화면과 강조 정보 변경
2. **Deep link 공유**
   - 특정 설비·필터·운영 판단 상태를 URL로 공유
3. **데모 모드**
   - 발표 시 위험 설비 하나를 중심으로 네 화면을 자동 순회
4. **접근성 강화**
   - 키보드 탐색, 상태 아이콘, 색상 대비와 스크린리더 Label 보강
5. **리포트 근거 Highlight**
   - 생성된 보고서 문장을 클릭하면 근거 설비와 Top factor를 화면에서 강조

---

## 6. 광우 — 팀원2 — 요구사항·리포트·스키마·기능·API·MVP 설계 문서화

### 6.1 역할 목적

광우는 MVP의 문서 계약을 고정하는 담당자다. 단순 회의록 작성이 아니라, 우수·성민·호범이 서로 다른 해석으로 구현하지 않도록 사용자 요구, 화면, 데이터, API와 리포트 계약을 하나의 문서 체계로 연결해야 한다.

초반 문서화 작업이 완료된 뒤에는 LLM 에이전트, 계약 자동 검증과 Traceability 기능으로 확장할 수 있다.

### 6.2 필수 문서 6종

#### A. 요구사항 정의서

포함 항목:

- 핵심 사용자: 생산 관리자·현장 담당자
- 사용자별 목적과 주요 업무
- 화면에서 확인해야 할 정보
- 수행 가능한 Action
- 권한과 데이터 범위
- MVP 포함 범위
- MVP 제외 범위
- 기능별 완료 기준

MVP 제외 범위:

- Analysis Workbench
- 시스템 관리자 화면
- 모델 재학습 화면
- 모든 역할별 Dashboard
- 자동 설비 정지
- 완전 자율형 LLM Agent

#### B. 리포트 정의서

리포트 사용자:

- 생산 관리자
- 임원 또는 의사결정자

리포트 구조:

1. 보고 기준 시각
2. 전체 설비 상태 요약
3. 가장 위험한 설비
4. 고장 가능성
5. 주요 위험 요인
6. 생산 영향
7. 권장 조치
8. 처리 상태
9. 데이터셋·모델 버전
10. 주의사항과 한계

정상·경고·위험 상태별 예시 문장과 금지 표현도 정의한다.

#### C. 스키마 정의서

다음 계약을 한 문서에서 연결한다.

- Canonical V3.1 Asset
- Prediction Result Artifact
- API 목록 응답
- API 상세 응답
- LLM 리포트 입력
- LLM 리포트 출력
- 화면 표시 필드

각 필드에 다음 정보를 포함한다.

| 항목 | 설명 |
|---|---|
| 필드명 | 실제 JSON Key |
| 자료형 | string·number·array·object |
| 필수 여부 | required·optional |
| 출처 | Canonical·Prediction·사용자 입력 |
| 사용 화면 | Overview·Objects·Operations·Report |
| 설명 | 사용자 관점 의미 |
| 예시 | 실제 예시 값 |

#### D. 기능 명세서

화면별로 다음을 정리한다.

- 기능 ID
- 사용자
- 선행 조건
- 입력
- 처리
- 출력
- 오류 상태
- 완료 조건
- MVP 포함 여부

#### E. API 명세서

- `GET /predictions`
- `GET /predictions/{asset_id}`
- 리포트 생성 API
- Query Parameter
- 요청·응답 Schema
- 오류 코드
- 예시 JSON
- 화면별 사용 API

#### F. MVP 설계 명세서

- MVP 목표
- 사용자 범위
- 네 화면 범위
- 시스템 구성
- 데이터 흐름
- API 흐름
- LLM 리포트 흐름
- 역할 분담
- 일정
- 완료 기준
- 제외 범위

### 6.3 문서 간 Traceability

문서가 서로 독립적으로 끝나지 않도록 다음 연결표를 만든다.

| 요구사항 ID | 기능 ID | 화면 | API | Schema | 테스트 |
|---|---|---|---|---|---|
| `REQ-MGR-001` | `FEAT-OV-001` | Overview | `GET /predictions` | Prediction summary | `TC-OV-001` |

이 표를 통해 요구사항이 실제 구현과 테스트로 이어졌는지 확인한다.

### 6.4 협업 입력과 출력

받아야 하는 것:

- 우수: 화면에서 필요한 실제 필드와 사용자 흐름
- 성민: API·Pipeline·Result Artifact 계약
- 호범: LLM 입력·출력 Schema와 Prompt 제약

전달해야 하는 것:

- 확정된 필드 Dictionary
- 요구사항·기능 ID
- 화면별 완료 조건
- API 요청·응답 계약
- 리포트 문장 규칙과 금지 표현

### 6.5 다음 주 산출물

- 요구사항 정의서
- 리포트 정의서
- 스키마 정의서
- 기능 명세서
- API 명세서
- MVP 설계 명세서
- 문서 간 Traceability Matrix
- 상단 산출물 링크 인덱스

### 6.6 완료 기준

- 팀원이 추가 질문 없이 자신의 구현을 시작할 수 있다.
- 화면 필드와 API 필드 이름이 일치한다.
- API와 LLM 리포트가 같은 Schema를 사용한다.
- 모든 요구사항이 기능·화면·API·테스트 중 하나 이상과 연결된다.
- 문서 상단에서 각 산출물 링크를 바로 열 수 있다.

### 6.7 플러스 알파 추천 태스크

광우의 필수 작업은 초반에 완료될 가능성이 높으므로, 이후 아래 순서로 확장하는 것을 권장한다.

#### 1순위 — 요구사항 검증 LLM 에이전트

문서를 입력하면 다음을 자동 점검하는 에이전트다.

- 요구사항이 모호한지
- 사용자와 기능이 연결돼 있는지
- 기능에 API가 없는지
- API 필드가 Schema에 없는지
- MVP 제외 범위가 구현 목록에 섞였는지
- 완료 기준이 측정 가능한지

출력 예시:

```json
{
  "issue_type": "missing_api_contract",
  "requirement_id": "REQ-FIELD-003",
  "message": "점검 요청 기능에 대응하는 API가 없습니다.",
  "severity": "high"
}
```

#### 2순위 — Schema·API 계약 자동 비교

- OpenAPI JSON과 Markdown API 명세 비교
- Pydantic Schema와 문서 필드 비교
- 화면 TypeScript Type과 API 응답 비교
- 누락·이름 불일치·자료형 불일치 Report 생성

#### 3순위 — Traceability 자동 생성

요구사항 문서, 기능 명세, API 명세와 테스트 파일을 읽어 다음 표를 자동 생성한다.

```text
Requirement → Feature → Screen → API → Schema → Test
```

#### 4순위 — 사용자 요구 인터뷰 에이전트

생산 관리자 또는 현장 담당자 역할을 선택하면 LLM이 부족한 요구사항을 질문한다.

예:

- 위험 설비가 여러 대일 때 무엇을 먼저 판단합니까?
- 점검 요청 전 반드시 확인해야 할 정보는 무엇입니까?
- 임원 보고서에서 반드시 포함해야 할 숫자는 무엇입니까?

#### 5순위 — 리포트 품질 평가 에이전트

호범이 생성한 리포트를 다음 기준으로 평가한다.

- 입력 데이터와 숫자가 일치하는가?
- 근거 없는 원인을 단정하지 않는가?
- 권장 조치가 Result Artifact와 일치하는가?
- 사용자 역할에 맞는 설명 수준인가?
- 지나치게 장황하거나 기술적이지 않은가?

#### 6순위 — 변경 영향 분석 에이전트

Schema 또는 API가 바뀌면 영향을 받는 화면·문서·테스트를 자동으로 제안한다.

광우에게 가장 권장하는 확장 조합은 다음이다.

```text
문서화 완료
→ 요구사항 검증 에이전트
→ API·Schema 계약 자동 비교
→ 리포트 품질 평가 에이전트
```

---

## 7. 성민 — 팀원3 — 예측 결과 조회 API + 데이터·예측 파이프라인 및 재현성

### 7.1 역할 목적

성민은 기존 팀원3과 팀원4의 역할을 통합해 담당한다. Canonical V3.1에서 예측 결과를 재현 가능하게 생성하고, 우수의 화면과 호범의 LLM 리포트가 조회할 수 있는 API로 제공한다.

### 7.2 필수 작업 A — 파이프라인 함수화

```python
def load_canonical_data():
    ...

def validate_canonical_data():
    ...

def build_features():
    ...

def load_model():
    ...

def run_predictions():
    ...

def build_result_artifacts():
    ...

def save_outputs():
    ...
```

한 번에 실행 가능한 진입점을 제공한다.

```bash
python run_prediction_pipeline.py \
  --dataset-version canonical-ai4i-physics-v3.1 \
  --output-dir outputs \
  --seed 42
```

### 7.3 필수 작업 B — 재현성 검증

동일한 입력과 설정으로 두 번 실행했을 때 다음 항목이 같아야 한다.

- 데이터 행 수
- 설비 수
- Feature 컬럼
- 예측 건수
- 설비별 예측 확률
- Result Artifact
- Checksum

산출물 예시:

```text
outputs/
├── predictions.json
├── result_artifact.jsonl
├── pipeline_manifest.json
├── reproducibility_report.json
└── checksums.sha256
```

### 7.4 필수 작업 C — 전체 예측 목록 API

```http
GET /predictions
```

사용 화면:

- Overview
- Objects
- Operations

기본 필드:

```json
{
  "items": [
    {
      "asset_id": "CNC-S01-L02-03",
      "asset_type": "cnc",
      "observed_at": "2026-08-06T09:00:00Z",
      "failure_probability": 0.87,
      "status_grade": "critical",
      "predicted_failure_type": "failure_risk",
      "confidence": 0.91,
      "recommended_action": {
        "action": "immediate_inspection_and_stop_review",
        "priority": "urgent"
      }
    }
  ],
  "total": 100
}
```

권장 필터:

```http
GET /predictions?status_grade=critical
GET /predictions?asset_type=cnc
GET /predictions?min_probability=0.7
GET /predictions?limit=20
```

### 7.5 필수 작업 D — 설비별 상세 API

```http
GET /predictions/{asset_id}
```

상세 응답에는 다음을 포함한다.

- 설비 기본 정보
- 고장 확률과 상태
- 신뢰도
- Top factors
- 권장 조치
- Dataset·Model provenance
- 리포트 생성에 필요한 근거

### 7.6 필수 작업 E — 오류와 OpenAPI

- 존재하지 않는 설비: `404 prediction_not_found`
- 잘못된 Filter: `422 validation_error`
- 데이터 로드 실패: `503 prediction_source_unavailable`
- Swagger 또는 OpenAPI에서 요청·응답 예시 제공

### 7.7 임계값·미탐·오탐 비교

| 임계값 | 오탐 | 미탐 | 적용 관점 |
|---|---:|---:|---|
| 0.3 | 높음 | 낮음 | 안전 우선 |
| 0.5 | 중간 | 중간 | 균형형 |
| 0.7 | 낮음 | 높음 | 점검 비용 우선 |

절대 최적값을 주장하지 않고 비용·안전 가정별 후보를 제공한다.

### 7.8 협업 입력과 출력

받아야 하는 것:

- 광우: 확정된 API·Schema·화면 필드 계약
- 우수: 실제 화면에서 필요한 Filter와 정렬 요구
- 호범: LLM 리포트 입력에 필요한 상세 근거

전달해야 하는 것:

- API URL과 Swagger
- 요청·응답 예시
- Result Artifact Sample
- Pipeline Manifest
- 재현성 Report
- API 테스트와 실행 방법

### 7.9 다음 주 산출물

- 함수화된 파이프라인
- 실행 CLI
- 재현성 검증 결과
- Pipeline Manifest와 Checksum
- `GET /predictions`
- `GET /predictions/{asset_id}`
- OpenAPI 문서
- API 테스트
- 임계값 비교 초안

### 7.10 완료 기준

- 새 환경에서도 문서대로 실행 가능하다.
- 동일 Seed에서 동일 결과가 생성된다.
- API가 Canonical V3.1 기반 실제 결과를 반환한다.
- 화면과 LLM이 같은 Result Artifact를 사용한다.
- 오류와 빈 결과가 명확히 구분된다.

### 7.11 플러스 알파 추천 태스크

1. **Threshold Recommendation API**
   - 안전 비용·점검 비용을 입력받아 임계값 후보 제공
2. **Prediction Timeline API**
   - 설비별 위험도 변화 시계열 제공
3. **Replay API 연결**
   - 고장 전 시점으로 이동하며 위험도 변화 재생
4. **Model·Dataset Version 비교**
   - 버전 변경 전후 확률과 Top factor 비교
5. **데이터 품질 Health API**
   - 누락·지연·Schema 불일치·Checksum 상태 제공

---

## 8. 호범 — 팀원4 — LLM을 활용한 백엔드 리포트 자동 생성

### 8.1 역할 목적

호범은 성민의 예측 결과와 광우가 정의한 리포트 계약을 사용해, 생산 관리자와 임원이 읽을 수 있는 설비 상태 보고서를 자동 생성하는 백엔드 기능을 구현한다.

핵심은 단순 자연어 생성이 아니라 **입력 데이터에 근거하고, 숫자를 왜곡하지 않으며, 원인을 단정하지 않는 리포트 생성**이다.

### 8.2 필수 작업 A — 리포트 생성 API

권장 형태:

```http
POST /reports/generate
```

입력 예시:

```json
{
  "report_type": "equipment_status_summary",
  "audience": "production_manager",
  "asset_ids": ["CNC-S01-L02-03"],
  "as_of": "2026-08-06T09:00:00Z",
  "language": "ko"
}
```

출력 예시:

```json
{
  "report_id": "REPORT-20260806-001",
  "title": "설비 상태 요약",
  "summary": "CNC-S01-L02-03 설비는 향후 24시간 내 고장 가능성이 87%로 위험 상태입니다.",
  "recommended_actions": [
    "즉시 현장 점검",
    "설비 정지 여부 검토"
  ],
  "evidence": [
    {
      "asset_id": "CNC-S01-L02-03",
      "prediction_id": "PRED-001",
      "top_factor": "tool_wear_min"
    }
  ],
  "provenance": {
    "dataset_version": "canonical-ai4i-physics-v3.1",
    "model_version": "independent-logreg-v3.1",
    "prompt_version": "equipment-summary-v1"
  }
}
```

### 8.3 필수 작업 B — Prompt와 생성 규칙

Prompt에 다음 제약을 명시한다.

- 입력에 없는 숫자를 만들지 않는다.
- `failure_probability`를 퍼센트로 변환할 때 반올림 규칙을 고정한다.
- 상관관계를 원인으로 단정하지 않는다.
- 권장 조치는 `recommended_action` 계약을 벗어나지 않는다.
- Dataset·Model provenance를 유지한다.
- 데이터가 없으면 추측하지 않고 `근거 부족`으로 표시한다.

### 8.4 필수 작업 C — 템플릿과 LLM 역할 분리

다음 구조를 권장한다.

```text
정형 데이터 검증
→ 보고서용 Facts 구성
→ 고정 템플릿으로 필수 문장 생성
→ LLM으로 표현 개선
→ 숫자·근거 재검증
→ 최종 Report Artifact 저장
```

LLM이 전체 내용을 자유롭게 만드는 방식보다, 검증된 Facts를 자연스럽게 표현하는 역할로 제한한다.

### 8.5 필수 작업 D — 출력 검증

최소 검증 항목:

- 설비 ID 일치
- 고장 확률 일치
- 상태 등급 일치
- Top factor 일치
- 권장 조치 일치
- Dataset·Model version 일치
- 근거 없는 숫자 없음
- 금지 표현 없음

검증 실패 시 리포트를 반환하지 않고 오류 또는 템플릿 Fallback을 사용한다.

### 8.6 필수 작업 E — 리포트 유형

MVP 필수:

- 설비 상태 요약 1종

가능하면 역할별 표현을 분리한다.

| 대상 | 표현 방식 |
|---|---|
| 생산 관리자 | 위험, 생산 영향, 우선순위와 조치 중심 |
| 임원 | 전체 현황, 핵심 위험, 영향과 대응 상태 중심 |

### 8.7 협업 입력과 출력

받아야 하는 것:

- 광우: 리포트 정의서, 문장 규칙, 금지 표현, 출력 Schema
- 성민: Prediction 상세 API와 Result Artifact
- 우수: 화면에서 필요한 응답 구조와 오류 상태

전달해야 하는 것:

- 리포트 생성 API
- Prompt Version
- 입력·출력 Schema
- 성공·실패 예시
- 검증 결과
- Fallback 정책

### 8.8 다음 주 산출물

- 백엔드 리포트 생성 API
- 리포트 Prompt와 버전 정보
- 입력·출력 Schema
- 설비 상태 요약 템플릿 1종
- 정상·경고·위험 예시
- 출력 검증 로직
- API 테스트
- 우수 화면 연동 방법

### 8.9 완료 기준

- Canonical V3.1 예측 결과로 리포트가 생성된다.
- 입력 숫자와 출력 숫자가 일치한다.
- 근거 없는 원인이나 조치를 생성하지 않는다.
- 실패 시 템플릿 Fallback이 동작한다.
- 생성 결과에 Dataset·Model·Prompt provenance가 포함된다.

### 8.10 플러스 알파 추천 태스크

1. **역할별 리포트 자동 변환**
   - 같은 Facts를 현장·관리자·임원 문체로 변환
2. **다중 설비·라인 요약**
   - 여러 설비를 하나의 라인 위험 보고서로 요약
3. **근거 인용형 리포트**
   - 문장마다 사용한 Prediction·Top factor ID 연결
4. **리포트 품질 평가기**
   - 정확성·근거성·가독성·간결성을 자동 채점
5. **한국어·영어 다국어 리포트**
   - 같은 Facts에서 언어만 변환하고 숫자 계약은 유지
6. **Streaming Generation**
   - 긴 보고서를 화면에 점진적으로 표시

---

## 9. 공통 데이터 계약

네 담당자는 최소한 다음 필드 이름과 의미를 공동으로 확정해야 한다.

| 필드 | 의미 | 주요 사용처 |
|---|---|---|
| `asset_id` | 설비 식별자 | 전 화면·API·리포트 |
| `asset_type` | Compressor 또는 CNC | Objects·Report |
| `observed_at` | 예측 기준 시각 | 전 화면·Report |
| `failure_probability` | 24시간 내 고장 확률 | Overview·Objects·Report |
| `status_grade` | 상태 등급 | 전 화면·Report |
| `confidence` | 예측 신뢰도 | Objects·Operations |
| `top_factors` | 위험 기여 요인 | Objects·Report |
| `recommended_action` | 권장 조치 | Operations·Report |
| `dataset_version` | 데이터셋 버전 | Report·감사 |
| `model_version` | 모델 버전 | Report·감사 |
| `prediction_id` | 예측 결과 식별자 | Evidence·Report |

## 10. 권장 작업 순서

### 1단계 — 계약 고정

광우 중심:

- 사용자 요구사항
- 화면 범위
- 공통 필드
- API와 리포트 Schema
- 완료 기준

### 2단계 — 파이프라인과 API

성민 중심:

- 파이프라인 함수화
- 재현성 확인
- Result Artifact 생성
- 목록·상세 API 제공

### 3단계 — 화면과 LLM 병렬 구현

- 우수: 네 화면과 API 연결
- 호범: 리포트 자동 생성 API
- 광우: 계약 불일치 검토

### 4단계 — 통합

```text
예측 API
→ 화면 표시
→ 설비 선택
→ 리포트 생성
→ 임원 보고서 표시
```

### 5단계 — 검증과 공유

- 동일 설비 데이터 일치
- 리포트 숫자 일치
- 네 화면 사용자 흐름 확인
- 요구사항 Traceability 확인
- 상단 산출물 링크 정리

## 11. 산출물별 주 담당자

| 산출물 | 주 담당 | 협업 |
|---|---|---|
| 요구사항 정의서 | 광우 | 전체 검토 |
| 리포트 정의서 | 광우 | 호범 |
| 스키마 정의서 | 광우 | 성민·호범·우수 |
| 기능 명세서 | 광우 | 우수 |
| API 명세서 | 광우 | 성민·호범 |
| MVP 설계 명세서 | 광우 | 전체 |
| 파이프라인·재현성 | 성민 | 광우 |
| 예측 조회 API | 성민 | 우수·호범 |
| MVP 프론트엔드 | 우수 | 성민·호범 |
| LLM 리포트 백엔드 | 호범 | 광우·성민·우수 |
| MVP 화면 공유 | 우수 | 전체 |

## 12. 2주차 통합 완료 기준

- Canonical V3.1을 단일 기준 데이터로 사용한다.
- Overview·Objects·Operations·임원 보고서 네 화면이 연결된다.
- 생산 관리자와 현장 담당자 흐름이 구분된다.
- Prediction 목록·상세 API가 실제 결과를 반환한다.
- 동일 Seed에서 파이프라인 결과가 재현된다.
- LLM 리포트가 입력 데이터와 일치하고 근거를 보존한다.
- 요구사항·기능·화면·API·Schema·테스트가 Traceability Matrix로 연결된다.
- 모든 주요 산출물은 문서 상단 링크로 바로 열 수 있다.

## 13. 역할별 플러스 알파 우선순위

| 담당 | 1순위 | 2순위 | 3순위 |
|---|---|---|---|
| 우수 | 리포트 근거 Highlight | 역할별 첫 화면 | 발표용 데모 모드 |
| 광우 | 요구사항 검증 LLM 에이전트 | API·Schema 자동 비교 | 리포트 품질 평가 에이전트 |
| 성민 | Threshold 추천 API | Prediction Timeline | Replay 연결 |
| 호범 | 근거 인용형 리포트 | 역할별 문체 변환 | 리포트 자동 평가기 |

플러스 알파는 필수 산출물이 완료되고 통합 흐름이 깨지지 않는 범위에서 진행한다.
