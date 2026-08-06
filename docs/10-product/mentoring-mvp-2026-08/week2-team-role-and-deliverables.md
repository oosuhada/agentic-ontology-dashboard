# Week 2 역할 분담 및 산출물 정의

- 문서 상태: `Week 2 execution baseline`
- 기준일: `2026-08-06`
- 근거: 2026년 8월 6일 오전 멘토링 결과
- 기준 데이터: `UCI AI4I 2020 Manufacturing Predictive Maintenance — Physics & Maintenance Canonical V3.1`
- 연관 문서: [MVP 범위 및 4개 화면 명세서](./mvp-scope-and-screen-specification.md)

## 1. 문서 목적

이 문서는 2주차에 진행할 팀원별 작업을 단순한 한 줄 숙제가 아니라, 실제 구현 범위·협업 관계·산출물·완료 기준까지 포함한 실행 단위로 구체화한다.

2주차의 공통 목표는 다음 세 가지다.

1. 요구사항 정의서 작성
2. MVP를 어떤 구조로 구현할지 설명하는 설계 계획서 작성
3. 실제로 확인할 수 있는 MVP 화면 공유

이번 주에는 전체 제품 기능을 확장하기보다, 멘토링에서 확정한 네 개 화면과 두 개 사용자 그룹에 집중한다.

```text
Canonical V3.1
→ 예측 결과 생성
→ 조회 API 제공
→ Overview·Objects·Operations 화면 표시
→ 임원 보고서로 결과 요약
```

## 2. 멘토링에서 확정된 MVP 기준

### 2.1 데이터

- Canonical V3.1 데이터를 MVP의 단일 기준 데이터로 사용한다.
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

시스템 관리자, 모델 검증 담당자, 품질 감사 담당자 등 전체 역할 확장은 MVP 이후 단계로 미룬다.

### 2.4 모델링

- 미탐과 오탐의 적정 비율은 산업·업종·고객 요구에 따라 달라진다.
- 하나의 임계값을 절대적인 정답으로 주장하지 않는다.
- 고객의 안전 우선순위와 점검 비용을 입력으로 받아 적절한 임계값 후보를 제안하는 방향으로 설계한다.

## 3. 역할 요약

| 담당 | 핵심 역할 | 핵심 질문 | 주요 산출물 |
|---|---|---|---|
| 팀원1 | MVP 프론트엔드와 화면 연결 | 사용자가 무엇을 보고 클릭하는가? | 4개 화면, 화면 링크, 화면 캡처, 사용자 흐름 |
| 팀원2 | 요구사항 및 리포트 정의 | 무엇을 어떤 문장과 보고서로 설명하는가? | 요구사항 정의서, 리포트 템플릿, 문장 생성 규칙 |
| 팀원3 | 예측 결과 조회 API | 화면이 필요한 데이터를 어떻게 조회하는가? | 목록·상세 API, OpenAPI 문서, 테스트 |
| 팀원4 | 데이터·예측 파이프라인과 재현성 | 예측 결과를 어떻게 동일하게 다시 생성하는가? | 함수화 파이프라인, Manifest, Checksum, 재현성 결과 |

## 4. 팀원1 — 대시보드 골격 및 MVP 화면 구현

### 4.1 역할 해석

기존 역할 문구는 다음과 같다.

> 대시보드 골격 — 설비 목록 표 + 상태등급 색상

이 역할은 설비 목록 표 하나만 만드는 작업이 아니다. 다음 주에 공유할 MVP의 프론트엔드 화면을 정리하고, 사용자가 네 화면을 따라 실제 업무 흐름을 확인할 수 있도록 만드는 역할이다.

### 4.2 기본 화면 구조

다음 네 화면이 서로 이동 가능한 구조로 제공되어야 한다.

- Overview
- Objects
- Operations
- 임원 보고서 View

기준 화면은 다음과 같다.

| MVP 화면 | 기준 구현 |
|---|---|
| Overview | V2 · Blueprint 1차 |
| Objects | V2 · Blueprint 1차 |
| Operations | V2 · Blueprint 1차 |
| 임원 보고서 | V1 · 기존 Dashboard |

새로운 UI를 처음부터 다시 만드는 것보다, 이미 구현된 화면에서 MVP에 필요한 기능만 추려 일관된 사용자 흐름으로 정리하는 것을 우선한다.

### 4.3 Objects 설비 목록 표

Objects 화면에는 최소한 다음 정보가 표시되어야 한다.

| 항목 | 설명 | API 연계 후보 |
|---|---|---|
| 설비 ID | 압축기 또는 CNC 식별자 | `asset_id` |
| 설비명 | 사용자가 알아볼 수 있는 설비명 | `display_name` |
| 설비 유형 | Compressor 또는 CNC | `asset_type` |
| 위치 | 공장·라인·셀 | `site`, `line`, `cell` |
| 현재 상태 | 정상·주의·경고·위험 | `status_grade` |
| 고장 확률 | 향후 24시간 내 고장 가능성 | `failure_probability` |
| 담당자 | 현장 점검 담당자 | `assigned_engineer` |
| 권장 조치 | 관찰·점검·정지 검토 | `recommended_action` |

API에 아직 없는 필드는 임의로 확정하지 않고 팀원2·3과 계약을 먼저 맞춘다. API 연결 전에는 동일한 필드 구조의 Mock 데이터를 사용한다.

### 4.4 상태등급 색상

| 상태 | 권장 색상 | 표시 원칙 |
|---|---|---|
| 정상 | 초록색 | `정상` 텍스트와 함께 표시 |
| 주의 | 파란색 또는 회색 | `주의` 텍스트와 함께 표시 |
| 경고 | 주황색 | `경고` 텍스트와 함께 표시 |
| 위험 | 빨간색 | `위험` 텍스트와 함께 표시 |

색상만으로 상태를 구분하지 않는다. 색상, 텍스트, 아이콘 중 최소 두 가지 이상을 함께 사용해 접근성을 확보한다.

### 4.5 역할별 첫 화면

#### 현장 담당자 관점

- 내가 점검해야 할 설비
- 위험 설비 목록
- 현재 센서값
- 위험 판단 이유
- 권장 점검 내용
- 점검 또는 정비 요청 버튼

#### 생산 관리자 관점

- 전체 위험 설비 수
- 라인별 위험 현황
- 생산에 영향을 줄 수 있는 설비
- 우선 처리 대상
- 정비 판단 상태
- 임원 보고서 또는 요약 보고

### 4.6 사용자 흐름

사용자는 다음 흐름을 화면에서 실제로 수행할 수 있어야 한다.

```text
Overview에서 위험 현황 확인
→ Objects에서 위험 설비 선택
→ Operations에서 조치 검토
→ 임원 보고서에서 결과 요약 확인
```

### 4.7 다음 주 산출물

- 실제 접속 가능한 MVP 화면 링크
- Overview·Objects·Operations·임원 보고서 화면 캡처
- 화면별 주요 기능 설명
- 네 화면을 연결한 사용자 흐름 설명
- API 연결 전 사용할 Mock 데이터
- API 연결 상태와 미연결 필드 목록

### 4.8 완료 기준

- 네 화면이 모두 접근 가능하다.
- 화면 간 이동이 가능하다.
- 동일 설비의 ID·상태·위험도가 화면마다 다르게 나타나지 않는다.
- API가 준비되면 Mock 데이터를 제거하고 실제 응답으로 전환할 수 있다.
- 생산 관리자와 현장 담당자의 주요 과업이 화면에서 구분된다.

## 5. 팀원2 — 리포트 템플릿 및 요구사항 문서화

### 5.1 역할 해석

기존 역할 문구는 다음과 같다.

> 리포트 템플릿 1종 — ‘설비 상태 요약’ 문단 생성

이 역할은 예시 문장 하나만 작성하는 작업이 아니다. MVP에서 어떤 사용자에게 어떤 데이터를 어떤 문장과 보고서 구조로 전달할지 정의하는 역할이다. 다음 주 산출물 중 요구사항 정의서의 주 담당 역할이다.

### 5.2 리포트 사용자

리포트의 핵심 독자는 다음과 같다.

- 생산 관리자
- 임원 또는 의사결정자

현장 담당자 화면이 센서와 점검 대상 중심이라면, 보고서는 전체 상황, 생산 영향, 대응 상태와 의사결정 중심으로 구성한다.

### 5.3 설비 상태 요약 템플릿

리포트에는 최소한 다음 항목이 포함되어야 한다.

1. 보고 기준 시각
2. 전체 설비 수
3. 정상·주의·경고·위험 설비 수
4. 가장 위험한 설비
5. 고장 가능성
6. 주요 위험 요인
7. 생산 영향
8. 권장 조치
9. 현재 처리 상태
10. 데이터셋 및 모델 버전

### 5.4 문장 생성 규칙

입력 예시는 다음과 같다.

```json
{
  "asset_id": "CNC-S01-L02-03",
  "status_grade": "critical",
  "failure_probability": 0.87,
  "top_factor": "tool_wear_min",
  "recommended_action": "immediate_inspection_and_stop_review"
}
```

출력 문장 예시는 다음과 같다.

> CNC-S01-L02-03 설비는 향후 24시간 내 고장 가능성이 87%로 위험 상태입니다. 주요 위험 요인은 공구 마모 증가이며, 즉시 현장 점검을 수행하고 설비 정지 여부를 검토해야 합니다.

문장 생성 시 다음 원칙을 지킨다.

- API나 Result Artifact에 없는 사실을 임의로 생성하지 않는다.
- 고장 확률과 위험 등급을 혼동하지 않는다.
- 모델 권장 조치를 자동 설비 정지 명령처럼 표현하지 않는다.
- 원인으로 확정되지 않은 항목은 `주요 위험 요인`, `연관 요인`, `점검 후보` 등으로 표현한다.
- 데이터셋·모델·관측 시각을 추적할 수 있게 한다.

### 5.5 요구사항 정의서

요구사항 정의서에는 최소한 다음 내용을 포함한다.

- 사용자 유형
- 사용자별 주요 업무
- 사용자가 화면에서 확인해야 할 정보
- 사용자가 수행할 수 있는 행동
- 화면별 기능
- 데이터 출처
- API 필요 항목
- 사용자별 권한 범위
- MVP 포함 범위
- MVP 제외 범위
- 성공 기준과 확인 방법

이번 MVP의 제외 범위는 다음과 같이 명시한다.

- Analysis Workbench
- 시스템 관리자 화면
- 모델 재학습 화면
- 전체 역할별 Dashboard
- 자동 설비 정지
- 완전한 LLM Agent 자동화
- 상용화용 전체 Governance·MLOps 기능

### 5.6 임원 보고서 View 구성안

팀원1이 별도 해석 없이 구현할 수 있도록 다음 구조를 화면 명세로 전달한다.

```text
상단
├── 보고 기준 시각
├── 전체 상태 요약
└── 핵심 KPI

중단
├── 주요 위험 설비
├── 위험 판단 근거
└── 생산 영향

하단
├── 권장 조치
├── 현재 처리 상태
└── 담당자·예정 시각

부록
├── 데이터셋 버전
├── 모델 버전
└── 근거 데이터·Provenance
```

### 5.7 다음 주 산출물

- 요구사항 정의서
- 설비 상태 요약 리포트 템플릿 1종
- 정상·주의·경고·위험 상황별 예시 문장
- 보고서 입력 필드 정의
- 보고서 출력 예시
- MVP 네 화면의 제목·설명·빈 상태 문구
- API 필드와 보고서 문장 간 매핑표

### 5.8 완료 기준

- 팀원1이 추가 질문 없이 임원 보고서 화면을 구현할 수 있다.
- 팀원3이 어떤 API 필드를 제공해야 하는지 알 수 있다.
- 모든 보고 문장의 근거 필드를 역추적할 수 있다.
- MVP 포함·제외 범위가 문서에 명확하다.

## 6. 팀원3 — 예측 결과 조회 API 구현

### 6.1 역할 해석

기존 역할 문구는 다음과 같다.

> `GET /predictions`, `GET /predictions/{설비ID}` 서빙

이 역할은 Canonical V3.1의 예측 결과를 프론트엔드와 리포트가 안정적으로 사용할 수 있는 API 계약으로 제공하는 역할이다.

### 6.2 전체 예측 목록 API

```http
GET /predictions
```

사용 목적은 다음과 같다.

- Overview의 상태별 설비 수 계산
- Objects의 설비 목록 표시
- Operations의 위험 설비 Queue 표시

최소 응답 예시는 다음과 같다.

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

시간이 허용되면 다음 필터를 지원한다.

```http
GET /predictions?status_grade=critical
GET /predictions?asset_type=cnc
GET /predictions?min_probability=0.7
GET /predictions?limit=20
```

우선순위는 기본 목록 조회, 상태 필터, 설비 유형 필터 순으로 둔다.

### 6.3 설비별 상세 API

```http
GET /predictions/{asset_id}
```

사용 목적은 다음과 같다.

- Objects에서 설비 선택 시 상세 정보 표시
- Operations에서 위험 판단 근거 표시
- 팀원2의 리포트 문장 생성

응답 예시는 다음과 같다.

```json
{
  "asset_id": "CNC-S01-L02-03",
  "asset_type": "cnc",
  "observed_at": "2026-08-06T09:00:00Z",
  "failure_probability": 0.87,
  "status_grade": "critical",
  "confidence": 0.91,
  "top_factors": [
    {
      "rank": 1,
      "feature": "tool_wear_min",
      "feature_value": 192.4,
      "direction": "risk_up"
    }
  ],
  "recommended_action": {
    "action": "immediate_inspection_and_stop_review",
    "priority": "urgent"
  },
  "provenance": {
    "dataset_version": "canonical-ai4i-physics-v3.1",
    "model_version": "independent-logreg-v3.1"
  }
}
```

### 6.4 오류 응답

존재하지 않는 설비 ID 요청은 빈 객체나 서버 오류가 아니라 명확한 `404` 응답을 반환한다.

```json
{
  "error": {
    "code": "prediction_not_found",
    "message": "해당 설비의 예측 결과를 찾을 수 없습니다."
  }
}
```

### 6.5 API 문서

FastAPI Swagger 또는 OpenAPI에서 다음 내용을 확인할 수 있어야 한다.

- 요청 URL
- Path·Query Parameter
- 응답 Schema
- 정상 응답 예시
- 404 오류 예시
- 데이터 기준 시각
- Dataset Version과 Model Version

### 6.6 프론트엔드·리포트 계약

API 구현 전에 팀원1·2와 공통 필드 표를 확정한다.

확인할 항목:

- 화면에서 실제로 사용하는 필드
- 목록 API와 상세 API의 필드 차이
- `assigned_engineer`, 위치, 생산 영향처럼 Result Artifact에 없을 수 있는 필드의 출처
- 상태 등급 enum
- 권장 조치 enum과 사용자 표시 문구
- 시간대와 날짜 형식
- 누락값 처리 방식

### 6.7 다음 주 산출물

- `GET /predictions`
- `GET /predictions/{asset_id}`
- OpenAPI 또는 Swagger 주소
- 요청·응답 예시
- 정상·오류 API 테스트
- `curl` 또는 Postman 실행 예시
- 프론트엔드 연동 방법
- 팀원4 산출물 파일을 읽는 Adapter 또는 Loader

### 6.8 완료 기준

다음 요청에서 Canonical V3.1 기반 실제 JSON 결과가 반환되어야 한다.

```bash
curl http://localhost:8000/predictions
curl http://localhost:8000/predictions/CNC-S01-L02-03
```

추가 완료 조건:

- 동일한 설비가 목록과 상세 API에서 동일한 상태를 가진다.
- 잘못된 설비 ID는 404로 처리된다.
- Swagger에서 응답 Schema를 확인할 수 있다.
- 팀원1 화면에서 실제 API 호출이 가능하다.

## 7. 팀원4 — 데이터·예측 파이프라인 함수화 및 재현성 검증

### 7.1 역할 해석

기존 역할 문구는 다음과 같다.

> 파이프라인 함수화 + 재현성 확인

이 역할은 데이터 생성부터 예측 결과 생성까지의 흐름을 정리해, 다른 팀원이 같은 입력과 설정으로 다시 실행해도 동일한 결과를 얻을 수 있도록 만드는 역할이다.

팀원3이 API로 제공할 예측 결과의 생성 책임을 가진다.

### 7.2 단계별 함수 분리

현재 실행 과정을 다음과 같이 의미 있는 함수로 분리한다.

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

목표는 다른 팀원이 전체 구현을 읽지 않아도 함수 이름과 실행 순서만으로 파이프라인을 이해할 수 있게 하는 것이다.

### 7.3 단일 실행 진입점

다음과 같이 한 번의 명령으로 결과를 생성할 수 있어야 한다.

```bash
python run_prediction_pipeline.py \
  --dataset-version canonical-ai4i-physics-v3.1 \
  --output-dir outputs
```

실행 실패 시에는 어느 단계에서 어떤 이유로 실패했는지 명확한 오류를 출력한다.

### 7.4 재현성 검증

동일한 입력·Seed·설정으로 두 번 실행했을 때 다음 항목이 같은지 확인한다.

- 데이터 행 수
- 설비 수
- Feature 컬럼과 순서
- 예측 건수
- 설비별 예측 확률
- Result Artifact 내용
- 파일별 SHA-256

검증 결과 예시는 다음과 같다.

```text
1차 실행 checksum: abc123...
2차 실행 checksum: abc123...
결과: 동일
```

생성 시각처럼 실행마다 달라지는 메타데이터는 재현성 비교 대상에서 제외하거나 별도 필드로 분리한다.

### 7.5 Seed와 설정 분리

랜덤 요소가 있다면 Seed를 명시적으로 고정한다.

```python
RANDOM_SEED = 42
```

다음 설정은 코드에 흩어 두지 않고 설정 파일이나 CLI Argument로 분리한다.

- Dataset 경로
- Dataset Version
- Model 경로
- Model Version
- Prediction horizon
- Risk threshold
- Output 경로
- Random seed

### 7.6 팀원3에게 제공할 산출물

API가 읽을 수 있는 결과 구조를 고정한다.

```text
outputs/
├── predictions.json
├── result_artifact.jsonl
├── pipeline_manifest.json
└── checksums.sha256
```

`pipeline_manifest.json` 예시는 다음과 같다.

```json
{
  "dataset_version": "canonical-ai4i-physics-v3.1",
  "model_version": "independent-logreg-v3.1",
  "generated_at": "2026-08-06T10:00:00Z",
  "prediction_count": 100,
  "random_seed": 42
}
```

### 7.7 미탐·오탐 임계값 비교

이번 MVP에서는 하나의 절대 임계값을 정답으로 확정하지 않는다. 임계값을 변경했을 때 다음 지표가 어떻게 달라지는지 비교할 수 있게 한다.

- 미탐률
- 오탐률
- Precision
- Recall
- 예상 점검 건수
- 예상 정지 위험

예시 구조:

| 임계값 | 오탐 | 미탐 | 적용 관점 |
|---:|---|---|---|
| 0.3 | 높음 | 낮음 | 안전 우선 산업 |
| 0.5 | 중간 | 중간 | 균형형 운영 |
| 0.7 | 낮음 | 높음 | 점검 비용 우선 |

실제 수치는 현재 모델 평가 결과를 사용해야 하며, 위 표의 `높음·중간·낮음`은 설명 구조 예시다.

### 7.8 다음 주 산출물

- 함수화된 파이프라인 코드
- 한 번에 실행 가능한 CLI
- 재현성 검증 결과
- Pipeline Manifest
- 예측 결과 파일
- 팀원3 API가 읽을 파일 위치와 계약
- 실행 방법 README
- 임계값별 미탐·오탐 비교 초안

### 7.9 완료 기준

- 새 환경에서 README 절차만으로 실행 가능하다.
- 동일 Seed와 입력으로 동일 Checksum을 얻는다.
- 팀원3이 별도 변환 없이 결과 파일을 읽을 수 있다.
- Dataset Version·Model Version·Seed가 Manifest에 남는다.
- 임계값 비교 결과의 계산 근거를 재현할 수 있다.

## 8. 역할 간 연결 구조

네 역할은 다음 순서로 연결된다.

```text
팀원4
Canonical V3.1 → Feature → Prediction → Result Artifact 생성
        ↓
팀원3
예측 결과를 GET /predictions API로 제공
        ↓
팀원1
Overview·Objects·Operations·임원 보고서 화면에 표시
        ↑
팀원2
필요 정보·사용자 요구사항·보고서 문장 규칙 정의
```

핵심 의존 관계는 다음과 같다.

| 선행 작업 | 후속 작업 | 전달해야 할 것 |
|---|---|---|
| 팀원2 | 팀원1 | 화면별 필수 정보, 보고서 구조, 사용자 문구 |
| 팀원2 | 팀원3 | API 필드 요구사항, enum 표시 문구 |
| 팀원4 | 팀원3 | 예측 결과 파일, Manifest, Schema, Checksum |
| 팀원3 | 팀원1 | API URL, 응답 예시, 오류 처리 방식 |
| 팀원1 | 팀원2 | 실제 화면 캡처, 누락 문구와 추가 요구사항 |

## 9. 다음 주 산출물별 주 담당자

### 9.1 요구사항 정의서

- 주 담당: 팀원2
- 협업: 팀원1
- 검토: 팀장 및 전체 팀원

포함 내용:

- 현장 담당자·생산 관리자 요구사항
- MVP 네 화면
- 화면별 기능
- 필요한 데이터
- 필요한 API
- 권한 범위
- 포함·제외 범위
- 완료 기준

### 9.2 MVP 설계 계획서

- 주 담당: 팀장
- 화면 내용 지원: 팀원1
- 요구사항·리포트 지원: 팀원2
- API 구조 지원: 팀원3
- 데이터·파이프라인 지원: 팀원4

포함 내용:

- MVP 목표
- 사용자 범위
- 화면 범위
- 시스템 구성
- 데이터 흐름
- API 구조
- 역할 분담
- 구현 일정
- 위험 요소
- 완료 기준

### 9.3 MVP 화면 공유

- 주 담당: 팀원1
- 데이터 연결: 팀원3
- 예측 결과: 팀원4
- 보고서 문구: 팀원2

공유 대상 화면:

1. Overview
2. Objects
3. Operations
4. 임원 보고서

## 10. 공통 작업 순서

재작업을 줄이기 위해 다음 순서를 권장한다.

1. 팀원1·2·3이 화면과 API 공통 필드 표를 먼저 확정한다.
2. 팀원4가 예측 결과 파일과 Manifest 계약을 고정한다.
3. 팀원3이 목록·상세 API를 구현한다.
4. 팀원1이 Mock 데이터를 실제 API로 교체한다.
5. 팀원2가 실제 응답을 기준으로 보고서 문장 예시를 확정한다.
6. 전체 팀이 동일 설비 하나를 기준으로 네 화면의 값이 일치하는지 검증한다.
7. 팀장이 요구사항 정의서·MVP 계획서·화면 링크를 상단 산출물 목록에 연결한다.

## 11. 통합 완료 기준

2주차 완료라고 판단하려면 다음 항목을 모두 충족해야 한다.

- Canonical V3.1을 기준 데이터로 사용한다.
- Overview·Objects·Operations·임원 보고서 네 화면을 공유할 수 있다.
- Analysis 화면은 MVP 동선에서 제외되어 있다.
- 생산 관리자와 현장 담당자의 요구사항이 문서화되어 있다.
- `GET /predictions`와 `GET /predictions/{asset_id}`가 동작한다.
- 화면의 데이터와 리포트 문장이 동일한 API·Result Artifact를 근거로 한다.
- 파이프라인 재실행 절차와 재현성 결과가 남아 있다.
- 요구사항 정의서, MVP 설계 계획서, MVP 화면 링크가 문서 상단에서 바로 열 수 있다.

