# Factory Signal Board 역할별 사용자 니즈 조사

- 문서 상태: 사용자 인터뷰 전 Research Hypothesis
- 작성일: 2026-08-01
- 입력 자료: 팀이 정리한 `Role별로 실제로 하는 일` 표, 기존 `docs/personas.md`, 제조 대시보드·Human-Centered AI·예지보전·품질·권한관리 관련 문헌
- 목적: 현재 `매니저 / 엔지니어` 2개 역할을 넘어 실제 제조 AI 서비스에서 필요한 역할, 정보, 행동, 권한과 화면 차이를 정의한다.

> 이 문서는 논문과 표준에서 도출한 설계 가설이다. 실제 고객사의 직무명과 책임은 회사·공장·라인마다 다르므로 사용자 인터뷰와 현장 관찰로 검증해야 한다.

---

## 1. 이번 조사에서 내린 제품 결정

### 1.1 사용자 화면의 초기화 기능 제거

`발표 상태 초기화` 또는 `데모 기록 초기화`는 제조 업무 사용자의 작업이 아니다. 실제 서비스처럼 보이는 MVP의 일반 사용자 화면에서는 제거한다.

현재 정책:

- 사용자 화면: 초기화 버튼 없음
- 공개 사용자 API: reset endpoint 없음
- 개발자 로컬 도구: `scripts/reset_demo.py`
- 향후 관리자 페이지: 사용자·역할·권한 관리와 함께 인증된 관리자 기능으로 검토
- 실제 운영 데이터: 일반 관리자가 임의 삭제할 수 없고 보존·감사 정책을 따라야 함

### 1.2 역할은 권한만이 아니라 업무 맥락이다

역할별 차이는 메뉴 접근 권한에 그치지 않는다. 다음 요소가 달라진다.

1. 달성하려는 결과
2. 판단 시간 범위
3. 책임과 승인 권한
4. 필요한 데이터의 상세도
5. 설명의 언어와 깊이
6. 첫 화면의 정보 순서
7. 알림 빈도와 긴급성
8. 수행 가능한 행동
9. 남겨야 하는 기록

제조 대시보드 연구는 현장 작업자, 전술 관리자, 경영진이 서로 다른 KPI와 화면을 필요로 한다고 보고한다. 따라서 하나의 대시보드를 역할별 필터만 바꿔 제공하는 방식보다, 공통 Evidence를 역할·업무에 맞춰 다르게 구성하는 방식이 적합하다.

### 1.3 역할 기반 + 상황 기반 + 개인 선호 기반

동적 대시보드의 추천 모델:

```text
Role baseline
+ current task
+ equipment/event context
+ organization policy
+ personal preference
= rendered dashboard
```

- `Role baseline`: 직무상 반드시 필요한 고정 정보
- `current task`: 모니터링, 점검, 보고, 검증, 감사 등 현재 목적
- `equipment/event context`: 위험도, 설비 중요도, 고장 유형, 데이터 품질
- `organization policy`: 승인 체계, SOP, 에스컬레이션 규칙
- `personal preference`: 자주 보는 설비, 접힌 상세, 정렬 방식

개인 선호가 안전·감사 필수 정보를 숨기면 안 된다.

---

## 2. 첨부 자료에서 시작한 역할 목록

| Role | 주로 보는 것 | 수행하는 행동 |
|---|---|---|
| 고객사 임원 | 전체 위험도, 생산 영향, 추세 | 보고서 확인, 대응 현황 점검 |
| 공정 매니저 | 위험 설비 순위, 미조치 건 | 우선순위 결정, 담당자 배정 |
| 공정 엔지니어 | 센서값, 원인, SOP, 이력 | 원인 분석, 점검, 결과 기록 |
| 데이터 사이언티스트 | 모델 점수, SHAP, 임계값 | 결과 검증, 오탐 분석 |
| 품질·감사 담당 | 입력·모델·설명·조치 이력 | 근거 확인, 자료 추출 |
| 비전문가 고객 | 쉬운 상태 설명과 다음 행동 | 질문, 확인, 공유 |

이 표는 좋은 출발점이지만 세 역할과 하나의 별도 관리 기능이 추가로 필요하다.

- **현장 작업자·정비 기술자**: 분석을 현장에서 실제 점검·교체·측정으로 전환한다.
- **FDE(Forward Deployed Engineer)**: 고객 workflow를 ontology·integration·dashboard application으로 빠르게 구현하고 운영 피드백을 제품에 연결한다.
- **조직 관리자**: 사용자, 역할, resource scope, 정책과 통합 설정을 관리한다. 일반 사용자 역할 확장 순위가 아니라 별도 관리자 control plane이다.

향후 고객에 따라 다음 역할도 분리할 수 있다.

- 정비 계획·자재 담당
- 안전·EHS 담당
- 생산 계획 담당
- 외부 서비스 엔지니어
- 솔루션 공급사 운영자

---

# 3. 역할별 상세 니즈

## 3.1 고객사 임원·공장장·사업 책임자

### 업무 목표

- 전사 또는 공장 수준의 운영 위험과 생산 영향을 이해한다.
- AI 도입이 다운타임, 비용, 품질과 대응 속도에 어떤 변화를 만들었는지 확인한다.
- 중대한 미조치 위험과 조직 대응 상태를 점검한다.
- 모델 하나의 점수보다 사업 리스크와 책임 상태를 본다.

### 판단 시간 범위

- 주간, 월간, 분기
- 중대 사건 발생 시 예외적으로 실시간

### 핵심 질문

- 현재 공장 전체에서 가장 큰 운영 위험은 무엇인가?
- 위험이 증가하고 있는 라인이나 설비군은 어디인가?
- 미조치 중대 사건은 몇 건이며 담당 조직은 대응하고 있는가?
- 예방 점검으로 피한 다운타임과 예상 손실은 어느 정도인가?
- AI가 잘못 판단한 사례와 개선 상태는 무엇인가?

### 기본 화면

1. 전체 위험 요약
2. 공장·라인별 추세
3. 생산 영향과 중요 사건
4. 미조치·기한 초과 현황
5. 대응 완료율
6. AI 성능·신뢰 이슈의 경영 요약
7. 상세 사건은 drill-down

### 수행 행동

- 보고서 확인
- 책임자에게 현황 확인 요청
- 중대 사건 리뷰 회의 요청
- 투자·인력·정비 정책 검토
- PDF·링크 공유

### 권한

- 전체 집계 조회
- 중요 사건과 대응 상태 조회
- 개별 센서 상세는 선택 조회
- 현장 점검 결과를 직접 수정하지 않음
- 모델 정책을 직접 변경하지 않음

### 설명 방식

- 쉬운 운영 언어
- 금액·시간·생산 영향 중심
- 불확실성과 추정 가정 표시
- 기술 용어는 접어서 제공

### 피해야 할 UX

- 첫 화면에 개별 센서 수십 개 노출
- SHAP 막대그래프를 사업 영향보다 먼저 표시
- AI 점수를 실제 절감액으로 직접 환산
- 대응 담당자와 기한이 없는 경고
- 정상 설비까지 모두 동일한 중요도로 노출

### 인터뷰 질문

- 주간 운영회의에서 반드시 보는 지표는 무엇인가?
- 사고나 대규모 정지 시 첫 10분에 누구에게 어떤 정보를 요청하는가?
- AI 예측을 투자 결정에 사용하려면 어떤 검증 자료가 필요한가?
- 추정 생산 영향은 어느 수준의 정확도와 근거가 있어야 유용한가?

---

## 3.2 공정·생산·설비 매니저

### 업무 목표

- 한정된 인력과 시간을 위험도가 높은 설비에 배분한다.
- 미조치 사건이 누락되지 않게 한다.
- 생산계획과 정비 필요 사이의 우선순위를 결정한다.
- 엔지니어에게 명확한 요청을 전달하고 결과를 회수한다.

### 판단 시간 범위

- 현재 교대, 오늘, 이번 주
- 이상 알림 발생 시 즉시

### 핵심 질문

- 지금 가장 먼저 확인해야 할 설비는 무엇인가?
- 같은 경고 중 무엇이 더 중요한가?
- 계속 운전, 현장 점검, 계획 정지 검토 중 무엇이 적절한가?
- 담당자는 누구이며 언제까지 확인해야 하는가?
- 엔지니어가 점검했고 어떤 결과를 남겼는가?
- 동일 문제가 반복되는가?

### 기본 화면

1. 위험·중요도·생산 영향을 조합한 우선순위
2. 미배정·미조치·기한 초과 사건
3. 선택 사건의 상태 요약과 권장 결정
4. 담당자·기한·진행 상태
5. 예상 운영 영향
6. 핵심 근거 2~3개
7. 필요 시 센서와 모델 상세

### 동적 화면 니즈

매니저 화면은 정형화된 한 장보다 사건 맥락에 따라 첫 정보가 달라져야 한다.

- 중대 위험: 상태·영향·담당 행동을 최상단
- 데이터 품질 오류: 고장 위험 대신 데이터 검증 책임을 최상단
- 복합 이상: 단일 원인보다 여러 위험 요인의 충돌을 최상단
- 반복 사건: 과거 조치와 재발 여부를 최상단
- 정상 운영: 예외 없는 설비를 압축하고 미조치 항목 중심

### 수행 행동

- 담당 엔지니어 배정
- 점검 요청
- 마감 기한 설정
- 계속 모니터링 승인
- 정지 여부 검토를 상위 책임자에게 에스컬레이션
- 엔지니어 결과 확인
- 임원용 요약 공유

### 권한

- 담당 공장·라인의 사건 조회
- 업무 배정과 기한 변경
- 판단 메모 기록
- 현장 점검 결과 조회
- 센서 원본·모델 정책 수정 불가
- 실제 설비 제어는 별도 승인 체계

### 피해야 할 UX

- 위험 확률만으로 자동 순위 결정
- 데이터 품질 문제와 설비 이상을 같은 방식으로 표현
- 담당자·마감일 없는 점검 요청
- 모든 설비에 같은 고정 위젯
- 개인 선호로 중대 미조치 경고를 숨길 수 있음

### 인터뷰 질문

- 실제 우선순위를 위험도 외에 무엇으로 결정하는가?
- 설비 중요도, 생산계획, 부품 재고 중 어떤 것이 가장 자주 판단을 바꾸는가?
- 엔지니어에게 요청할 때 반드시 포함하는 정보는 무엇인가?
- 어떤 상황에서 상위 관리자에게 에스컬레이션하는가?

---

## 3.3 공정·설비·신뢰성 엔지니어

### 업무 목표

- 이상 발생 시점과 영향을 준 센서를 찾는다.
- 모델의 원인 후보를 설비 메커니즘과 대조한다.
- SOP, 과거 정비 이력, 유사 사건을 이용해 점검 순서를 정한다.
- 점검 결과를 재현 가능하게 기록하고 매니저에게 보고한다.

### 판단 시간 범위

- 분, 시간, 교대
- 사건 분석 시 과거 수일·수주의 추세까지 확장

### 핵심 질문

- 어떤 센서가 언제부터 어떻게 변했는가?
- 정상 범위와 비교했을 때 변화 규모는 어느 정도인가?
- 위험도를 올린 모델 요인은 무엇인가?
- 센서 오류, 공정 조건 변화, 실제 설비 이상 중 무엇이 가능한가?
- 먼저 점검할 항목은 무엇이며 관련 SOP는 무엇인가?
- 이전에 같은 패턴이 있었고 당시 조치는 무엇이었는가?

### 기본 화면

1. 이상 구간이 표시된 센서 시계열
2. 현재 값·단위·정상 범위
3. 주요 기여 요인과 상호작용
4. 데이터 품질 상태
5. 원인 후보와 반증 근거
6. SOP·정비 이력·유사 사건
7. 점검 체크리스트
8. 매니저 보고용 요약

### 고정 화면 니즈

엔지니어의 일상 업무에는 자주 비교하는 센서와 기준을 고정할 필요가 있다.

- 담당 설비군
- 핵심 센서 세트
- 정상 범위
- 최근 정비일
- 반복 고장 패턴
- 배정된 미완료 점검

동적 구성은 이 고정 업무 영역 위에서 이상 유형에 맞는 근거를 추가하는 방식이 적합하다.

### 수행 행동

- 시계열 구간 확대
- 센서 간 비교
- 데이터 품질 이슈 등록
- 점검 체크리스트 수행
- 측정값과 사진·메모 기록
- 원인 후보 상태 변경
- 추가 데이터 요청
- 점검 결과를 매니저에게 제출

### 권한

- 담당 설비의 센서·이력·SOP 조회
- 점검 결과와 원인 후보 기록
- 데이터 품질 이슈 제기
- 모델 예측을 확정 고장으로 변경할 수 없음
- 임계값과 모델 버전 변경 불가

### 피해야 할 UX

- 자연어 요약만 제공하고 센서 근거를 숨김
- 단위와 정상 범위 누락
- 모델 설명과 SOP 권고를 같은 출처처럼 표현
- 시계열이 없는 단일 현재값
- 점검 전 원인을 확정 표현

### 인터뷰 질문

- 이상 알림을 받으면 가장 먼저 여는 화면과 문서는 무엇인가?
- 어떤 센서 조합을 항상 함께 보는가?
- AI 원인 설명을 믿지 않는 대표적인 상황은 무엇인가?
- 매니저에게 보고하기 위해 반복 작성하는 내용은 무엇인가?

---

## 3.4 현장 작업자·정비 기술자

### 업무 목표

- 배정된 점검을 안전하고 빠르게 수행한다.
- 현장에서 필요한 최소 정보와 작업 순서를 확인한다.
- 결과와 증거를 누락 없이 남긴다.
- 분석가가 아니라 실행자 관점에서 복잡한 모델 정보를 작업으로 변환한다.

### 판단 시간 범위

- 현재 작업, 현재 교대

### 핵심 질문

- 어느 설비의 어느 위치를 확인해야 하는가?
- 어떤 안전 절차와 도구가 필요한가?
- 정상·비정상을 무엇으로 판단하는가?
- 측정하거나 촬영해야 할 항목은 무엇인가?
- 문제가 확인되면 누구에게 에스컬레이션해야 하는가?

### 기본 화면

1. 설비 식별과 위치
2. 점검 목적 한 문장
3. 안전 주의사항
4. 단계별 체크리스트
5. 정상·비정상 예시
6. 기록해야 할 측정값·사진·메모
7. 완료·문제 발견·작업 불가 선택
8. 담당 엔지니어 연락 또는 에스컬레이션

### 수행 행동

- 작업 시작·중단·완료
- 체크리스트 기록
- 측정값 입력
- 사진·메모 첨부
- 부품 사용 기록
- 문제 발견 보고
- 작업 불가 사유 기록

### 권한

- 배정된 작업과 관련 자료만 조회
- 점검 결과 입력
- 분석 모델·정책·우선순위 수정 불가
- 다른 사용자의 기록 삭제 불가

### 설명 방식

- 짧고 명확한 문장
- 현장 용어와 설비 위치 중심
- 모델 점수보다 관찰할 증상 중심
- 모바일·태블릿과 장갑 착용 환경 고려

### 피해야 할 UX

- 작은 글씨와 복잡한 차트
- 작업 위치가 없는 추상적 경고
- 모델 확률을 작업 판정 기준으로 강요
- 오프라인·네트워크 불량 상황 미지원
- 안전 절차보다 생산 영향 우선 노출

### 인터뷰 질문

- 현장에서 실제로 손에 들고 보는 정보는 무엇인가?
- 체크리스트에서 가장 자주 빠지는 기록은 무엇인가?
- 작업 중 네트워크나 장비 사용 제약은 무엇인가?
- 어떤 표현이 작업자에게 위험하거나 모호하게 느껴지는가?

---

## 3.5 데이터 사이언티스트·ML 엔지니어

### 업무 목표

- 모델과 데이터가 운영 조건에서 유효한지 확인한다.
- 오탐·미탐·드리프트·입력 오류를 분석한다.
- 모델 버전과 임계값 변경의 효과를 검증한다.
- 사용자 피드백과 현장 결과를 모델 개선으로 연결한다.

### 판단 시간 범위

- 일간·주간 모니터링
- 모델 릴리스 전후
- 이상 성능 사건 발생 시

### 핵심 질문

- 현재 모델·정책·데이터 버전은 무엇인가?
- 최근 Precision, Recall, false negative가 어떻게 변했는가?
- 특정 설비·라인·제품군에서 성능이 나빠지는가?
- 입력 데이터가 학습 분포와 달라졌는가?
- 설명값과 예측값이 안정적인가?
- 사용자가 어떤 예측을 거부하거나 수정했는가?

### 기본 화면

1. 모델·데이터·정책 버전
2. 성능과 오류 유형 추세
3. 설비·라인·제품군 slice 성능
4. 데이터 품질·schema·drift
5. 임계값별 비용과 confusion matrix
6. 설명 분포와 주요 feature 변화
7. 사용자 피드백·현장 결과
8. Gold·회귀 테스트 결과

### 수행 행동

- 오류 사례 분석
- 데이터 품질 규칙 제안
- threshold 후보 시뮬레이션
- 새 모델 평가
- 모델 릴리스 요청
- rollback 요청
- Gold 시나리오 추가

### 권한

- 모델 검증 데이터와 운영 피드백 조회
- 후보 모델·정책 작성
- 운영 배포는 승인 workflow 필요
- 현장 점검 결과 원본 수정 불가
- 사용자 역할·권한 변경 불가

### 피해야 할 UX

- 전체 Accuracy 하나만 제공
- 운영 threshold와 학습 성능을 혼합
- 데이터 버전·lineage 누락
- 사용자의 조치 결과와 예측을 연결하지 않음
- 모델 변경을 승인 없이 즉시 운영 반영

### 인터뷰 질문

- 운영 모델 장애를 가장 먼저 발견하는 지표는 무엇인가?
- 현재 오탐과 미탐을 어떻게 수집·분류하는가?
- 모델 배포 승인에 필요한 최소 증거는 무엇인가?
- 현장 피드백을 학습 데이터로 반영할 때 어떤 검토가 필요한가?

---

## 3.6 품질·감사·규제 대응 담당

### 업무 목표

- 어떤 입력, 모델, 설명과 사람이 어떤 판단을 했는지 재구성한다.
- 조치가 SOP와 승인 정책을 따랐는지 확인한다.
- 자료 요청에 대응할 수 있도록 변경 불가능한 근거와 기록을 추출한다.
- AI가 품질 판단을 대체했는지, 보조했는지 구분한다.

### 판단 시간 범위

- 사건 후 검토
- 정기 내부 감사
- 고객·인증·규제 요청 시

### 핵심 질문

- 이 결과는 어떤 입력과 모델 버전으로 생성됐는가?
- 당시 임계값과 정책은 무엇이었는가?
- 자연어 설명이 Evidence와 일치하는가?
- 누가 언제 무엇을 조회·결정·수정했는가?
- 점검 결과와 승인 기록이 완전한가?
- 데이터 또는 설명이 변경됐다면 변경 이력은 무엇인가?

### 기본 화면

1. 사건 타임라인
2. 입력 snapshot과 data quality
3. 모델·정책·prompt·context 버전
4. Evidence와 Report 연결
5. 사용자 행동·승인·수정 이력
6. SOP·점검 결과·첨부 증거
7. 예외와 미준수 상태
8. 감사 패키지 추출

### 수행 행동

- 근거 검토
- 감사 자료 추출
- 누락 기록 요청
- 예외 등록
- 검토 완료·보완 필요 표시
- 보존 정책 확인

### 권한

- 넓은 범위의 read-only 조회
- 감사 의견과 검토 상태 기록
- 원본 기록 수정·삭제 불가
- 사용자 역할·모델 정책 직접 변경 불가

### 설명 방식

- 요약보다 추적성과 원본 우선
- 시간·사용자·버전이 명확해야 함
- observed, derived, predicted, estimated, user-entered 구분

### 피해야 할 UX

- 현재 상태만 있고 과거 snapshot이 없음
- 리포트 문장의 출처가 없음
- 관리자가 감사 로그를 임의 삭제 가능
- 동일 사건의 버전이 덮어쓰기됨
- PDF만 있고 구조화 데이터 추출 불가

### 인터뷰 질문

- 감사 시 가장 자주 요청받는 자료 묶음은 무엇인가?
- 전자 기록에서 필수인 사용자·시간·승인 정보는 무엇인가?
- AI 설명의 충분성을 어떤 기준으로 판단하는가?
- 보존 기간과 삭제 승인 규칙은 어떻게 되는가?

---

## 3.7 비전문가 고객·외부 조회 사용자

### 업무 목표

- 복잡한 제조·AI 지식 없이 상태와 다음 행동을 이해한다.
- 자신에게 관련된 사건만 확인한다.
- 필요한 질문을 하고 담당자에게 공유한다.

### 판단 시간 범위

- 알림을 받았을 때
- 고객 보고 또는 협업 요청 시

### 핵심 질문

- 지금 정상인가, 확인이 필요한가?
- 무엇이 관찰됐고 확실하지 않은 것은 무엇인가?
- 내가 해야 할 일은 무엇인가?
- 언제 다시 확인하면 되는가?
- 누구에게 문의해야 하는가?

### 기본 화면

1. 쉬운 상태 문장
2. 영향 범위
3. 권장 다음 행동
4. 담당자와 예상 응답 시간
5. 핵심 근거 1~2개
6. 제한사항과 불확실성
7. 질문·공유

### 수행 행동

- 질문
- 확인 표시
- 링크·보고서 공유
- 담당자에게 문의

### 권한

- 허용된 고객·설비·사건만 조회
- 내부 센서 원본·SOP·모델 상세 제한
- 판단·점검 기록 수정 불가

### 피해야 할 UX

- 설명 없는 약어와 모델 용어
- 내부 사용자 이름·민감 데이터 노출
- 확률을 확정 고장으로 표현
- 사용자가 수행할 수 없는 내부 행동 버튼 노출

### 인터뷰 질문

- 현재 고객에게 상태를 어떻게 설명하고 있는가?
- 고객에게 공개하면 안 되는 내부 정보는 무엇인가?
- 어느 정도의 기술 상세가 있어야 설명을 신뢰하는가?
- 질문 후 기대하는 응답 시간과 채널은 무엇인가?

---

## 3.8 FDE·Forward Deployed Engineer

### 업무 목표

- 고객의 실제 업무와 데이터 구조를 빠르게 이해한다.
- 고객 문제를 ObjectType, LinkType, ActionType과 dashboard workflow로 변환한다.
- datasource·API·LLM·업무 시스템 통합을 구성하고 장애를 진단한다.
- 역할별 default dashboard template을 만들고 사용자와 검증한다.
- 고객별 요구를 일회성 custom code로 끝내지 않고 재사용 가능한 product capability로 환류한다.

### 핵심 질문

- 고객이 해결하려는 실제 운영 결과는 무엇인가?
- 현재 workflow에서 어떤 사람·시스템·데이터가 연결되는가?
- 어떤 object와 relation으로 업무를 표현해야 하는가?
- 어떤 Action을 누가 어떤 조건에서 실행해야 하는가?
- 역할별로 첫 화면과 필수 Board가 어떻게 달라야 하는가?
- integration·permission·LLM 실패가 어느 계층에서 발생했는가?

### 기본 화면

1. 고객 workspace와 목표
2. workflow map
3. ObjectType·LinkType·ActionType inventory
4. datasource·integration mapping 상태
5. 역할별 dashboard template preview
6. Board binding과 parameter dependency
7. provider·LLM·Action 오류 진단
8. 배포 checklist와 사용자 피드백

### 수행 행동

- 고객 workflow 기록
- ontology schema·mapping draft 작성
- integration 설정과 health 확인
- dashboard template draft 편집
- 다른 역할로 preview
- test data·Gold scenario 실행
- publish·deployment 승인 요청
- 사용자 피드백을 제품 backlog로 연결

### 권한

- 할당된 고객·workspace의 ontology·integration·template 구성
- draft 생성과 preview
- 제한된 diagnostic log 조회
- production publish는 승인 필요
- 사용자 비밀번호·secret 원문 열람 불가
- 조직 전체 사용자 삭제·보안 정책 우회 불가
- 감사 로그 삭제 불가

### 피해야 할 UX

- FDE를 super-admin으로 취급
- 고객 workflow보다 데이터 schema만 먼저 노출
- role preview 없이 template 게시
- 고객별 custom logic의 출처·버전 누락
- secret과 개인정보가 diagnostic 화면에 노출
- production 변경과 draft 변경의 경계가 없음

### 인터뷰 질문

- 고객 요구를 제품 workflow로 변환할 때 가장 많은 시간이 드는 단계는 무엇인가?
- 데이터 mapping과 사용자 workflow 중 어느 쪽의 불확실성이 더 큰가?
- 역할별 dashboard를 검증할 때 고객에게 어떤 과제를 수행하게 하는가?
- production publish 전에 어떤 승인과 회귀 검증이 필요한가?

---

## 3.9 조직 관리자·Tenant Administrator

### 업무 목표

- 사용자를 조직, 공장, 라인, 설비와 역할에 연결한다.
- 역할별 권한과 데이터 접근 범위를 관리한다.
- 인증, 통합, 보존 정책과 관리자 작업을 감사 가능하게 유지한다.
- 사용자 업무 화면과 관리 기능을 분리한다.

### 핵심 질문

- 이 사용자는 어떤 역할과 설비 범위를 가져야 하는가?
- 역할별로 읽기·작성·승인 권한이 어떻게 다른가?
- 퇴사·부서 이동 사용자의 권한이 제거됐는가?
- 외부 고객의 접근 기간과 범위는 무엇인가?
- 관리자 작업은 누가 언제 수행했는가?

### 관리자 페이지 후보 기능

1. 사용자 초대·비활성화
2. 역할 할당
3. 공장·라인·설비 scope 할당
4. 세부 권한 확인
5. 임시 외부 사용자 만료일
6. IdP·SSO 설정
7. LLM·Project 3·CMMS 연결 상태
8. 데이터 보존 정책
9. 관리자 감사 로그
10. 개발·데모 환경에서만 기록 초기화

### 권한 모델 권장안

단순 RBAC만으로는 같은 `엔지니어`라도 공장·라인·설비 범위가 다른 문제를 해결하기 어렵다.

```text
Permission = Role × Resource Scope × Environment × Action
```

예:

```text
process_engineer
× plant=A, line=2
× production
× read_sensor, create_inspection, submit_report
```

역할 수가 과도하게 늘지 않도록 역할은 직무 책임을 표현하고, 공장·라인·설비 범위는 attribute/scope로 분리한다.

### 데모 기록 초기화 정책

- 일반 사용자 UI에 노출하지 않음
- production 환경에서는 기본 비활성
- development/demo 환경에서만 허용
- 실행 전 삭제 범위 표시와 재확인
- 실행 사용자·시간·대상 환경 감사
- 실제 고객 데이터는 reset 대상에서 제외
- 향후 관리자 페이지 구현 전에는 CLI만 사용

### 피해야 할 UX

- 관리자 메뉴와 생산 의사결정 화면 혼합
- 모든 관리자를 super-admin으로 처리
- 역할 이름만 있고 실제 권한을 확인할 수 없음
- 사용자별 개별 권한을 무제한으로 추가해 관리 불가능해짐
- 관리자 감사 로그까지 초기화 대상에 포함

### 인터뷰 질문

- 사용자 권한은 현재 어느 조직이 승인하는가?
- 공장·라인·설비 접근 범위는 어떤 규칙으로 정하는가?
- 외부 협력사 계정은 어떻게 만료·회수하는가?
- 관리자 작업 중 이중 승인이나 감사가 필요한 것은 무엇인가?

---

# 4. 역할 간 정보·행동 비교

| 역할 | 시간 범위 | 첫 정보 | 설명 깊이 | 대표 행동 | 쓰기 권한 |
|---|---|---|---|---|---|
| 고객사 임원 | 주·월·분기 | 전체 위험·영향·추세 | 사업 요약 | 확인, 리뷰 요청, 공유 | 제한적 |
| 공정 매니저 | 현재·일·주 | 우선순위·미조치·담당 | 운영 요약+핵심 근거 | 배정, 기한, 점검 요청 | 업무 배정·판단 |
| 공정 엔지니어 | 분·시간·교대 | 센서·구간·원인 후보 | 기술 상세 | 분석, 점검 계획, 보고 | 분석·점검 기록 |
| 현장 작업자 | 현재 작업 | 위치·안전·체크리스트 | 작업 지시 수준 | 수행, 측정, 사진, 완료 | 배정 작업 기록 |
| 데이터 사이언티스트 | 일·주·릴리스 | 모델·데이터 품질·오류 | 모델 상세 | 검증, 후보 정책, 릴리스 요청 | 검증 산출물 |
| 품질·감사 | 사건 후·정기 | lineage·변경·승인 이력 | 원본·추적성 우선 | 감사, 자료 추출, 보완 요청 | 감사 의견 |
| 비전문가 고객 | 알림·문의 시 | 쉬운 상태·다음 행동 | 평이한 설명 | 질문, 확인, 공유 | 매우 제한적 |
| FDE | 구축·배포·장애 대응 | workflow·ontology·integration·template | 기술+고객 업무 | 구성, preview, 진단, 게시 요청 | 할당 workspace draft |
| 조직 관리자 | 계정 변경·정책 관리 | 사용자·역할·scope | 권한 상세 | 할당, 비활성화, 설정 | 관리자 설정 |

---

# 5. 역할별 대시보드 구성 원칙

## 5.1 모든 역할이 공유해야 하는 사실

역할별 화면이 달라도 다음 값은 같은 Evidence에서 나와야 한다.

- 사건 ID
- 설비 ID
- 관측 시각
- 입력 센서 값
- 모델·정책 버전
- 위험도와 신뢰도
- 데이터 품질 상태
- 사람의 판단·점검 기록

역할에 따라 표현과 순서는 달라도 원본 사실이 모순되면 안 된다.

## 5.2 고정 영역과 동적 영역

### 고정 영역

- 사용자의 담당 설비·업무
- 안전·품질 필수 경고
- 미완료 작업
- 역할상 필수 KPI
- 조직 정책상 필수 승인 상태

### 동적 영역

- 현재 사건의 주요 근거
- 위험 유형에 맞는 차트
- 역할과 질문 intent에 따른 블록 우선순위
- 생산 영향 또는 SOP context
- 사용자가 펼친 기술 상세

### 사용자 선호 영역

- 자주 보는 설비
- 정렬과 필터
- 기본 기간
- 접힌 상세 상태
- 알림 채널

사용자 선호는 중대 경고, 데이터 품질 경고, 감사 필드를 제거할 수 없다.

## 5.3 설명의 역할 적합성

NIST AI RMF는 설명과 인간 감독 요구를 최종 사용자와 역할·기술 수준에 맞게 설계하고 검증할 것을 권고한다. 따라서 같은 SHAP 결과를 모든 사람에게 동일한 그래프로 보여주는 것은 역할 기반 설명이 아니다.

- 임원: `생산 영향에 가장 큰 관련 요인`
- 매니저: `점검 우선순위를 높인 핵심 근거`
- 엔지니어: `센서 값·단위·정상 범위·기여 방향`
- 데이터 사이언티스트: `feature attribution 안정성·slice·threshold`
- 감사 담당: `설명 생성 방식·버전·원본 Evidence`
- 비전문가: `관찰된 변화와 확실하지 않은 점`

---

# 6. 현재 MVP와 역할 확장 권장 순서

현재 구현된 `manager`와 `engineer`는 역할 연구의 끝이 아니라 첫 vertical slice다.

## 6.1 다음 구현 우선순위

### 1순위: 고객사 임원 Viewer

이유:

- 기존 Evidence와 사건 집계를 재사용할 수 있다.
- 매니저보다 상위의 사업·추세 화면을 검증할 수 있다.
- 판매·발표에서 제품 가치를 설명하는 사용자가 된다.

### 2순위: 품질·감사 Viewer

이유:

- 현재 Evidence·lineage·audit 구조의 차별점을 명확히 보여준다.
- read-only 역할이므로 작업 workflow보다 구현 위험이 낮다.
- AI 설명의 신뢰성과 추적성 요구를 제품 기능으로 만든다.

### 3순위: 현장 작업자·정비 기술자

이유:

- 매니저의 요청과 엔지니어의 분석을 실제 작업 완료로 연결한다.
- 현재 체크리스트를 모바일 작업 흐름으로 확장할 수 있다.
- 역할 간 handoff를 검증할 수 있다.

### 4순위: FDE Workbench

이유:

- 고객 workflow를 ontology와 dashboard template으로 전환하는 제품 구축 역할이 필요하다.
- 역할별 preview, integration health와 배포 진단을 하나의 workspace에서 검증할 수 있다.
- 고객별 요구를 재사용 가능한 domain pack과 Board로 환류하는 핵심 역할이다.

### 5순위: 데이터 사이언티스트 Console

데이터 사이언티스트 화면은 고객 업무 대시보드보다 model observability console에 가깝다. 동일 navigation에 억지로 넣지 말고 별도 검증 영역 또는 내부 운영 제품으로 분리한다.

### 별도 선행 Control Plane: 조직 관리자

회원가입 승인, 역할·resource scope, dashboard template 게시 권한을 관리하기 위해 관리자 페이지는 역할 Viewer 구현과 별도로 먼저 필요하다. 다만 조직 관리자는 1~4순위 사용자 dashboard 확장에 포함하지 않고 별도 `/admin` 애플리케이션으로 구현한다.

## 6.2 권장 역할 코드

```text
executive_viewer
process_manager
process_engineer
maintenance_technician
quality_auditor
ml_validator
fde
external_viewer

# 별도 관리자 control plane
tenant_admin
```

직무명은 고객별로 바뀔 수 있지만 내부 권한·정보 계약은 안정된 코드로 관리한다.

---

# 7. 사용자 조사 계획

문헌 조사만으로 각 역할의 우선순위를 확정하면 안 된다. 최소한 다음 조사를 수행한다.

## 7.1 인터뷰 표본

- 공장장·임원 2명
- 생산·공정 매니저 3명
- 공정·설비 엔지니어 4명
- 현장 작업자·정비 기술자 4명
- 데이터 사이언티스트·ML 엔지니어 2명
- 품질·감사 담당 2명
- 시스템 관리자 1~2명

## 7.2 인터뷰 방식

- 일반적인 선호보다 최근 실제 사건을 재구성한다.
- `마지막으로 설비 이상을 처리했던 날`을 기준으로 질문한다.
- 사용 중인 Excel, MES, CMMS, 메신저, 종이 작업지를 실제로 보여달라고 요청한다.
- 어떤 정보를 확인했는지보다 어떤 결정을 내렸고 누구에게 전달했는지 묻는다.
- AI가 없을 때의 업무와 AI가 들어왔을 때 바뀌면 안 되는 책임을 구분한다.

## 7.3 검증해야 할 핵심 가설

1. 매니저는 고정 차트보다 사건별 우선 정보 구성이 더 유용하다.
2. 엔지니어는 담당 설비와 핵심 센서의 고정 업무 영역이 필요하다.
3. 현장 작업자는 모델 설명보다 위치·안전·단계·판정 기준이 중요하다.
4. 임원은 확률보다 영향·추세·미조치 상태를 우선한다.
5. 감사 담당은 자연어 보고서보다 lineage·버전·원본 기록을 우선한다.
6. 데이터 사이언티스트 도구는 일반 업무 UI와 분리하는 편이 낫다.
7. 역할과 설비 scope를 조합한 권한 모델이 필요하다.
8. LLM 설명은 역할별로 내용 깊이가 달라야 하지만 Evidence는 동일해야 한다.

## 7.4 프로토타입 테스트 과제

- 임원: `이번 주 가장 큰 생산 위험과 대응 상태를 설명해달라.`
- 매니저: `엔지니어 한 명만 배정할 수 있을 때 무엇부터 처리할지 결정하라.`
- 엔지니어: `경고 원인 후보와 첫 세 개 점검 항목을 찾으라.`
- 작업자: `배정된 점검을 수행하고 문제 발견을 기록하라.`
- 데이터 사이언티스트: `최근 false negative 증가 원인을 찾으라.`
- 감사 담당: `특정 결정이 어떤 입력·모델·사람의 행동에서 나왔는지 재구성하라.`
- 관리자: `새 엔지니어에게 특정 라인만 접근하도록 권한을 할당하라.`

---

# 8. 제품 백로그로 변환

## 역할·권한

- [ ] 역할 코드와 권한 matrix 정의
- [ ] 사용자와 공장·라인·설비 scope 모델
- [ ] 관리자 전용 route와 layout
- [ ] 역할 변경·권한 변경 감사 로그
- [ ] 외부 사용자 만료일

## 역할별 화면

- [ ] 임원 전략 요약 화면
- [ ] 매니저 우선순위·배정·기한 화면
- [ ] 엔지니어 고정 설비·센서 workspace
- [ ] 작업자 모바일 점검 화면
- [ ] 품질·감사 사건 재구성 화면
- [ ] ML 검증 console 분리
- [ ] 비전문가용 plain-language viewer

## 역할 간 handoff

- [ ] 매니저 → 엔지니어 점검 요청
- [ ] 엔지니어 → 작업자 실행 요청
- [ ] 작업자 → 엔지니어 결과 제출
- [ ] 엔지니어 → 매니저 보고
- [ ] 매니저 → 임원 중요 사건 보고
- [ ] 품질 담당 → 보완 요청

## 관리자 기능

- [ ] 사용자 초대·비활성화
- [ ] 역할·scope 할당
- [ ] 통합 상태 확인
- [ ] 개발·데모 환경 전용 기록 초기화
- [ ] production 기록 삭제 금지·보존 정책

---

# 9. 근거 자료와 설계에 반영한 내용

## 제조 대시보드와 역할별 KPI

1. **Tokola, H., Niemi, E., Gröger, C., & Järvenpää, E. (2016). Designing Manufacturing Dashboards on the Basis of a Key Performance Indicator Survey. Procedia CIRP, 57, 619–624.**  
   DOI: [10.1016/j.procir.2016.11.107](https://doi.org/10.1016/j.procir.2016.11.107)  
   반영: 작업자용 operational dashboard, 관리자용 tactical dashboard, 경영진용 strategy dashboard가 서로 다른 KPI를 선호한다는 근거.

2. **Gröger, C., Hillmann, M., Hahn, F., Mitschang, B., & Westkämper, E. (2013). The Operational Process Dashboard for Manufacturing. Procedia CIRP, 7, 205–210.**  
   DOI: [10.1016/j.procir.2013.05.035](https://doi.org/10.1016/j.procir.2013.05.035)  
   반영: 기존 MES가 현장 작업자의 개별 정보 요구를 충분히 지원하지 못하며, 공정 맥락 중심 정보와 빠른 대응이 필요하다는 근거.

3. **Vilarinho, S., Lopes, I., & Sousa, S. (2017). Design Procedure to Develop Dashboards Aimed at Improving the Performance of Productive Equipment and Processes. Procedia Manufacturing, 11, 1634–1641.**  
   DOI: [10.1016/j.promfg.2017.07.314](https://doi.org/10.1016/j.promfg.2017.07.314)  
   반영: 여러 계층의 직원이 참여하는 interactive performance management와 현장 인터뷰 기반 dashboard 설계 필요성.

4. **Johansson, P. E. C. et al. (2018). Assessment Based Information Needs in Manual Assembly.**  
   DOI: [10.12783/dtetr/icpr2017/17637](https://doi.org/10.12783/dtetr/icpr2017/17637)  
   Chalmers record: [research.chalmers.se/en/publication/515859](https://research.chalmers.se/en/publication/515859)  
   반영: 현장 작업자의 `언제, 무엇을, 어디에서` 수행할지에 관한 정보 요구와 실제 station 관찰의 중요성.

## Human-Centered AI와 역할 적합 설명

5. **Denno, P. O. (2024). Cognitive Work in Future Manufacturing Systems: Human-centered AI for Joint Work with Models.**  
   DOI: [10.3233/JID-230035](https://doi.org/10.3233/JID-230035)  
   NIST: [Cognitive Work in Future Manufacturing Systems](https://www.nist.gov/publications/cognitive-work-future-manufacturing-systems-human-centered-ai-joint-work-models)  
   반영: 모델은 엔지니어의 목표와 생산 시스템에 대한 이해를 지원해야 하며, 인간이 모델을 해석·수정하는 인지 업무를 중심으로 UI를 설계해야 한다는 근거.

6. **NIST (2023). Artificial Intelligence Risk Management Framework 1.0.**  
   DOI: [10.6028/NIST.AI.100-1](https://doi.org/10.6028/NIST.AI.100-1)  
   반영: 조직 내 역할·책임, 인간 감독, 투명성, 설명가능성, 기록과 거버넌스를 제품 수명주기 전체에서 다뤄야 한다는 근거.

7. **NIST AI RMF Playbook — Map and Measure.**  
   Map: [airc.nist.gov/airmf-resources/playbook/map](https://airc.nist.gov/airmf-resources/playbook/map/)  
   Measure: [airc.nist.gov/airmf-resources/playbook/measure](https://airc.nist.gov/airmf-resources/playbook/measure/)  
   반영: 최종 사용자 workflow와 설명 기준을 사용자와 함께 설계하고, 역할·지식 수준에 맞는 설명을 배포 전에 검증해야 한다는 근거.

8. **Toward human-centered intelligent assistance system in manufacturing: challenges and potentials for operator 5.0 (2024). Procedia Computer Science, 232.**  
   DOI: [10.1016/j.procs.2024.01.156](https://doi.org/10.1016/j.procs.2024.01.156)  
   반영: intelligent assistance의 장기적 가치는 usability, acceptance, understandability와 실제 작업 경험을 체계적으로 설계할 때 생긴다는 근거.

9. **World Economic Forum (2024). Views from the Manufacturing Front Line: Workers’ Insights on How to Introduce New Technology.**  
   Source: [WEF publication](https://www.weforum.org/publications/views-from-the-manufacturing-front-line-workers-insights-on-how-to-introduce-new-technology)  
   반영: 제조 기술 도입 시 현장 작업자의 목소리, workflow와 실제 제약을 초기 설계에 포함해야 한다는 근거.

## 예지보전 설명과 실행 가능한 판단

10. **An explainable artificial intelligence model for predictive maintenance and spare parts optimization (2024).**  
    DOI: [10.1016/j.sca.2024.100078](https://doi.org/10.1016/j.sca.2024.100078)  
    반영: 이진 모델 결과는 의사결정자가 오해할 수 있으므로 영향 요인 설명과 정비·부품 의사결정 맥락이 필요하다는 근거.

11. **Explainable anomaly detection framework for predictive maintenance in manufacturing systems (2022). Applied Soft Computing, 125.**  
    DOI: [10.1016/j.asoc.2022.109147](https://doi.org/10.1016/j.asoc.2022.109147)  
    반영: 조기 이상 탐지와 설명이 현장 엔지니어의 선제 정비에 필요하다는 근거. 제품에서는 `root cause 확정` 표현보다 원인 후보와 확인 절차로 제한한다.

12. **NIST Industrial Artificial Intelligence Management and Metrology.**  
    Source: [NIST IAIMM](https://www.nist.gov/programs-projects/industrial-artificial-intelligence-management-and-metrology-iaimm)  
    반영: 산업 AI의 성능 기대와 내부 논리를 인간 사용자에게 명확히 전달하는 것이 적절한 신뢰 형성에 중요하다는 근거.

## 모델 운영·데이터 사이언티스트 니즈

13. **Breck, E. et al. (2017). The ML Test Score: A Rubric for ML Production Readiness and Technical Debt Reduction.**  
    Source: [Google Research](https://research.google/pubs/the-ml-test-score-a-rubric-for-ml-production-readiness-and-technical-debt-reduction/)  
    반영: 모델 운영 역할에는 데이터·모델·인프라 테스트와 지속 monitoring이 필요하며 offline score만으로 production readiness를 판단하면 안 된다는 근거.

14. **Breck, E. et al. (2019). Data Validation for Machine Learning.**  
    Source: [Google Research](https://research.google/pubs/data-validation-for-machine-learning/)  
    반영: 입력 schema, anomaly, training-serving skew와 데이터 품질을 모델과 동급의 운영 자산으로 관리해야 한다는 근거.

15. **Sculley, D. et al. (2015). Hidden Technical Debt in Machine Learning Systems.**  
    Source: [Google Research](https://research.google/pubs/hidden-technical-debt-in-machine-learning-systems/)  
    반영: 모델 자체 외에도 데이터 의존성, feedback loop, undeclared consumer, 변화하는 외부 조건을 검증 담당 화면과 운영 정책에서 다뤄야 한다는 근거.

## 품질·감사·기록

16. **ISO 9001 — Quality management systems.**  
    Official page: [ISO 9001](https://www.iso.org/standard/62085.html)  
    반영: 품질 시스템의 competence, communication, documented information과 지속 개선 요구를 품질·감사 역할 설계에 반영.

17. **ISO 10013:2021 — Quality management systems — Guidance for documented information.**  
    Official announcement: [ISO 10013:2021](https://committee.iso.org/sites/tc176/home/news/content-left-area/news-and-updates/release-of-iso-100132021-quality.html)  
    반영: 디지털 기록, 보안, 자동화된 정보 흐름과 문서화 정책을 audit package 설계에 반영.

18. **ISO 19011 — Guidelines for auditing management systems.**  
    Official page: [ISO 19011](https://www.iso.org/standard/19011)  
    반영: 감사 프로그램, 수행, 증거 검토와 기록의 독립된 업무 역할을 정의.

19. **ISO 10012 — Quality management — Requirements for measurement management systems.**  
    Official page: [ISO 10012](https://www.iso.org/standard/10012)  
    반영: 생산·검사·monitoring에 사용되는 측정 결과의 신뢰성과 적합성을 품질 담당 정보 요구에 반영.

## 제조 정보 통합과 관리자 권한

20. **ISA-95 — Enterprise-Control System Integration.**  
    Official page: [ISA-95 Standard](https://www.isa.org/standards-and-publications/isa-standards/isa-95-standard)  
    반영: enterprise와 manufacturing operations의 기능·정보 흐름, production·quality·maintenance 활동을 분리하면서 연결하는 역할 모델의 근거.

21. **Sandhu, R. et al. Role-Based Access Control: Features and Motivations. NIST.**  
    Source: [NIST RBAC](https://www.nist.gov/publications/role-based-access-control-rbac-features-and-motivations)  
    반영: 권한은 개별 사용자에게 임의 부여하기보다 직무 역할에 연결하고 사용자를 역할에 배정하는 관리자 모델의 근거.

22. **Kuhn, D. R. et al. Adding Attributes to Role Based Access Control. NIST.**  
    Source: [NIST publication](https://www.nist.gov/publications/adding-attributes-role-based-access-control)  
    반영: 역할만으로 동적 공장·라인·설비 범위를 표현하면 role explosion이 생길 수 있으므로 role과 attribute/scope를 조합해야 한다는 근거.

---

# 10. 다음 업데이트 조건

다음 중 하나가 발생하면 이 문서를 갱신한다.

- 고객 인터뷰 3건 이상 완료
- 새로운 역할 prototype 테스트 완료
- 실제 조직의 역할·권한 표 수령
- CMMS·MES·SSO integration 범위 확정
- 인증·감사·데이터 보존 요구 수령
- 관리자 페이지 작업 시작

조사 결과가 기존 가설과 다르면 문헌보다 실제 사용자 workflow를 우선하되, 안전·품질·감사 요구는 별도 검토 후 변경한다.
