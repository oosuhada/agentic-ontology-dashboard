---
title: "CI 개발 피드백 시간 단축 제안"
status: proposal
date: 2026-08-19
scope: GitHub Actions pull request validation
---

# CI 개발 피드백 시간 단축 제안

## 결정 요청

PR 검증 범위는 유지하면서, 빠른 실패 확인과 무거운 통합 검증을 병렬화한다. 이 문서는 구현 완료 기록이 아니라 workflow 변경 전 합의용 제안이다.

## 관측된 기준선

PR #50의 2026-08-19 실행에서 `backend-contract` job은 1분 27초에 완료했다.

| 단계 | 관측 시간 | 해석 |
| --- | ---: | --- |
| Backend contract 의존성 설치 | 31초 | 가장 큰 backend-contract 단계 |
| Product Result/Evidence 계약 테스트 | 9초 | 테스트 실행 자체는 병목이 아님 |
| `architecture`의 Playwright 직전 단계 | 약 1분 23초 | Python/Node 설치, import smoke, unit/build가 직렬 실행됨 |
| Playwright Chromium 설치 이후 | 실행 중 장시간 | Browser 설치, Operations E2E, Docker build/start가 뒤이어 직렬 실행됨 |

현재 `.github/workflows/architecture.yml`은 backend 변경 시 integration과 Docker 검증을 함께 활성화한다. `tests/*` 변경은 fail-closed로 전체 검증을 활성화한다. 이는 범위를 줄이는 문제가 아니라 한 job 안에서 browser와 Docker까지 순차 실행하는 구조가 대기 시간을 키운다.

## 목표와 비목표

### 목표

- PR push 뒤 정적 규칙·migration ratchet·영향 범위 계약 테스트의 실패를 먼저 알린다.
- Playwright Operations smoke와 Docker runtime smoke는 계속 실행한다.
- 같은 브랜치에 연속 push가 발생하면 오래된 실행을 취소한다.
- 캐시 효과와 검증 범위를 job 로그로 측정할 수 있게 한다.

### 비목표

- backend 변경에서 PostgreSQL replay, browser, Docker 검증을 제거하지 않는다.
- 실패 시 skip을 통과로 처리하거나 branch protection의 required check를 약화하지 않는다.
- CI 통과를 production 배포 또는 사용자 영향 증거로 확장 해석하지 않는다.

## 권장 설계

### 1. 검증을 세 job으로 분리하고 최종 gate는 유지한다

`architecture` workflow의 changed-file classifier를 정본으로 유지하고, 다음 job을 병렬 실행한다.

| Job | 책임 | 실행 조건 |
| --- | --- | --- |
| `architecture-fast` | architecture rules, migration ratchet, generator/backend smoke, 영향받은 frontend unit/build | 모든 PR에서 정적 규칙; classifier에 따라 domain smoke |
| `operations-e2e` | Playwright 설치와 대표 Operations browser smoke | `integration=true` |
| `docker-runtime` | Docker image build, compose 기동, health와 storage smoke | `docker=true` |
| `architecture` gate | 위 결과와 required/verified output을 집계 | 모든 PR |

최종 `architecture` gate 이름과 output 계약은 유지한다. 현재 reusable code-review workflow가 `needs.architecture` output과 `architecture` job 로그를 소비하므로, job 분리와 함께 실패한 하위 job 로그를 선택하는 경로를 명시적으로 갱신해야 한다.

이 구조는 검증을 삭제하지 않고, 총 대기 시간을 `fast + e2e + docker`의 합에서 가장 오래 걸리는 병렬 job 시간으로 바꾼다.

### 2. 의존성 캐시와 재현 가능한 설치를 적용한다

- Python: `actions/setup-python`의 `cache: pip` 및 backend/ml/generator dependency file 경로를 설정한다.
- Node: `actions/setup-node`의 npm cache와 `systems/frontend/package-lock.json`을 사용하고 `npm install`을 `npm ci --no-audit --no-fund`으로 바꾼다.
- Playwright: `~/.cache/ms-playwright` cache를 OS와 frontend lockfile hash로 keying하는 PoC를 만든다. cache miss에서는 기존 `--with-deps chromium` 경로를 유지한다.

Playwright의 OS 패키지와 browser binary는 GitHub-hosted runner에서 항상 같은 방식으로 cache되지 않을 수 있다. 따라서 cache hit/miss, 설치 시간, E2E 결과를 최소 5회씩 기록한 뒤에만 기본 경로로 채택한다.

### 3. 오래된 PR 실행을 취소한다

`architecture.yml`에 PR 번호 또는 ref를 포함한 concurrency group과 `cancel-in-progress: true`를 추가한다.

```yaml
concurrency:
  group: architecture-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
```

이는 단일 실행을 빠르게 만들지는 않지만, 수정 중인 브랜치에서 이전 Playwright/Docker job이 runner를 점유하는 낭비를 막는다. main push에는 ref별 group이 적용되므로 main의 최신 실행은 유지된다.

### 4. 로컬 fast gate를 CI와 같은 명령으로 고정한다

개발자는 Docker/E2E 전에 다음 범위로 빠르게 확인한다. 이 명령은 현재 PR #50 runtime/Evidence 경로의 계약 테스트 기준이며, PostgreSQL service replay 실행을 대체하지는 않는다.

```bash
python systems/verify_architecture.py
APP_ENV=test python -m pytest -q \
  tests/test_demo_predictive_maintenance_bootstrap.py \
  tests/test_product_result_artifact_evidence_contract.py \
  tests/test_product_result_evidence_enrichment.py \
  tests/test_predictive_maintenance_result_replay.py
```

후속 구현에서는 이 명령을 `scripts/`의 명명된 fast-gate script로 옮겨, 개인별 명령 차이와 CI 드리프트를 줄인다.

## 단계적 도입과 수용 기준

1. **기준선 수집:** cache 없이 PR 실행 5건의 job별 queue/start/end 시간을 보관한다.
2. **병렬 job 분리:** 기존 조건, required output, 실패 semantics를 유지한 채 workflow만 분리한다. 문서-only PR과 backend PR을 각각 확인한다.
3. **캐시 PoC:** Python/npm을 먼저 적용하고, Playwright cache는 hit/miss 측정 후 적용 여부를 결정한다.
4. **concurrency 적용:** 동일 PR에 두 번 push하여 이전 heavy job이 취소되고 최신 head만 남는지 확인한다.

수용 기준은 다음과 같다.

- backend 변경 PR에서 fast gate, Playwright, Docker 검증이 모두 실행된다.
- 어느 하위 job이든 실패하면 최종 `architecture` gate와 code-review 입력이 실패를 정확히 반영한다.
- cache miss에서도 현재와 같은 검증 명령이 실행된다.
- 기준선 대비 PR 완료 wall-clock의 p50이 감소했음을 5회 이상 측정으로 확인한다.
- PostgreSQL replay, browser E2E, Docker smoke의 skip 수가 증가하지 않는다.

## 예상 변경 범위

- `.github/workflows/architecture.yml`
- `.github/workflows/code-review.yml` (집계 job으로 변경될 때 실패 로그 선택 경로)
- 선택 사항: `scripts/verify-backend-contract-fast.sh`
- 선택 사항: CI 측정 결과 문서

작업 순서는 workflow 병렬화와 output 보존을 먼저 검증하고, 캐시와 local script는 그 다음 별도 commit으로 분리한다.
