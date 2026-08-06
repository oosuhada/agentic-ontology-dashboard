# 배포 및 공개 검증

## 배포 원칙

- 추적된 source가 아니라 검증된 `web/dist`만 Web 정적 서비스에 제공
- API와 Web을 각각 health check
- 기존 서비스 checkout에 다른 세션의 미커밋 변경이 있으면 reset, stash, overwrite하지 않음
- 대규모 저장소 정리 브랜치는 공개 서비스에 바로 배포하지 않고 검토 후 기준 브랜치로 병합

## 빌드

```bash
npm --prefix web run build
PYTHONPATH=api:ml/src .venv/bin/python -m compileall -q api/ontology_dashboard
```

## 서비스 재시작

로컬 launchd 구성이 준비된 환경에서는:

```bash
./scripts/restart_public_services.sh
```

## 검증 항목

1. `/health` HTTP 200
2. `/login`에서 역할 카드가 정확히 두 개
3. 관리자·임원과 실무 엔지니어 로그인 성공
4. `/app/projects/manufacturing-demo-project/mvp` HTTP 200
5. Overview → Objects → Operations → Executive Report 이동
6. 관리자 Decision과 엔지니어 Note 저장
7. 390px viewport에서 가로 overflow 없음
8. A4 print media에서 app chrome 숨김
9. 이전 V1~V4·Analysis·Admin 경로가 현재 MVP로 redirect

## 롤백

배포 전 `web/dist`를 별도 경로에 복사하고 검증 실패 시 원자적으로 복구합니다. DB migration과 Canonical Dataset Version은 immutable 식별자로 관리하고, 화면에서 Dataset Version을 바꾸어 결과를 되돌립니다.
