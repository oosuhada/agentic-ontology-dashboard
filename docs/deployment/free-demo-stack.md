# Mac mini demo deployment baseline

공유 환경의 정본은 Vercel Preview가 아니라 Mac mini의
`https://ontology.oosu.dev/`이다.

```text
pull_request
  └─ 자동 CI 테스트 없음

main push
  └─ lightweight architecture release marker green
       └─ Mac mini outbound release watcher
            └─ verified main SHA pull
                 └─ Frontend container :8120
                      └─ Cloudflare Tunnel → ontology.oosu.dev
```

## CI and CD ownership

- PR에서는 자동 unit/build/Playwright/Docker/contract CI를 실행하지 않는다.
- `architecture` workflow는 테스트를 수행하지 않고 `main` push SHA에 대한 최소 release marker만
  남긴다. Mac mini CD는 이 성공 marker가 있는 SHA만 소비한다.
- 저장소가 public이므로 Mac mini를 repository self-hosted runner로 노출하지 않는다.
- Mac mini의 launchd watcher가 outbound로 `main` 및 GitHub Actions 상태를 확인하고 검증된 SHA만 pull한다.
- Frontend 입력(`systems/frontend`, `docs`)이 마지막 평가 SHA 이후 바뀌지 않았다면 배포를 건너뛴다.
- 배포 실패 시 직전 Frontend image로 rollback하고 workflow를 실패 처리한다.

## Mac mini runtime

- Public URL: `https://ontology.oosu.dev/`
- Published Blueprint showcase compatibility alias: `https://dashboard.oosu.dev/`
  (same Frontend origin). The alias exists so historical README/demo links keep
  resolving even though `ontology.oosu.dev` remains the canonical product URL.
- Frontend origin: `127.0.0.1:8120`
- Backend origin: `127.0.0.1:8110`
- Frontend container는 기존 `ontology-dashboard-macmini_private` network에 연결되어
  same-origin `/api/*` 요청을 `api:8000`으로 proxy한다.
- Week 2 Operations-only routing remains enabled for normal product navigation. The
  published `blueprint-compare`, `blueprint-v4`, and the comparison page's
  scoped iframe preview routes are explicit exceptions so design-review links
  do not collapse into `/operations`.
- Mac mini Compose enables the scoped read-only public Blueprint comparison
  session. General deployments keep `ENABLE_PUBLIC_BLUEPRINT_COMPARISON=0`
  unless they intentionally expose the same showcase.
- Cloudflare Tunnel과 Backend/PostgreSQL/Redis/live ingestion runtime은 Frontend CD가
  재생성하거나 중단하지 않는다.

## Secrets

Frontend CD는 GitHub secret을 Mac mini로 전송하지 않는다. Release watcher는 public Git/GitHub
API를 읽기만 하고 Mac mini에서 이미 실행 중인 Docker/OrbStack과 production network만 사용한다.
Backend/database/model secrets는 기존 Mac mini production runtime의 로컬 secret/environment
관리 범위에 남긴다.

## Release watcher polling and GitHub rate limits

Release watcher의 기본 `launchd` 간격은 `StartInterval=60`이다. 같은 `main` SHA를 이미
평가한 정상 상태에서는 `git ls-remote` 뒤 즉시 종료하고 GitHub Actions REST API를 호출하지
않으므로 이 간격을 유지한다.

새 `main` SHA의 Architecture release marker가 장시간 pending/failure 상태이면 같은 SHA의 Actions 상태를
60초마다 다시 확인할 수 있다. 이때 GitHub가 `403` 또는 `429`를 반환하면 수동으로 즉시 반복
호출하지 않는다.

- 응답에 `Retry-After`가 있으면 그 시간이 지난 뒤 다시 확인한다.
- `X-RateLimit-Reset`이 있으면 reset 시각 이후 다시 확인한다.
- 반복적인 rate limit이 발생하거나 Mac mini에 다른 GitHub polling 자동화를 추가한다면 전체
  unauthenticated API 호출량을 다시 검토하고 watcher 간격을 임시로 300초로 늘린다.
- Architecture release marker 실패가 장시간 유지될 때는
  `$HOME/Library/Logs/dev.oosu.ontology-dashboard-release-watcher/` 로그를 먼저 확인하고,
  원인 해소 전에는 polling 간격 확대를 우선한다.

300초로 전환할 때는 설치된 LaunchAgent의 `StartInterval`만 변경하고 다시 로드한다.

```bash
PLIST="$HOME/Library/LaunchAgents/dev.oosu.ontology-dashboard-release-watcher.plist"
DOMAIN="gui/$(id -u)"

/usr/libexec/PlistBuddy -c 'Set :StartInterval 300' "$PLIST"
plutil -lint "$PLIST"
launchctl bootout "$DOMAIN" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl kickstart -k "$DOMAIN/dev.oosu.ontology-dashboard-release-watcher"
```

rate limit 원인이 해소되고 전체 GitHub polling 사용량에 여유가 있음을 확인한 뒤 같은 절차로
`StartInterval`을 `60`으로 되돌린다. `infra/macmini/install-release-watcher.sh`를 다시 실행하면
기본값 `60`으로 설치된다는 점도 함께 확인한다.
