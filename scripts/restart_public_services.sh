#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

DOMAIN="gui/$(id -u)"
API_LABEL="com.gabrieljang.ontology-dashboard-api-public"
WEB_LABEL="com.gabrieljang.ontology-dashboard-web-public"
API_PORT="${API_PORT:-8100}"
WEB_PORT="${WEB_PORT:-3100}"

if [[ ! -f web/dist/index.html ]]; then
  echo "web/dist is missing; run: npm --prefix web run build" >&2
  exit 1
fi

launchctl print "${DOMAIN}/${API_LABEL}" >/dev/null
launchctl print "${DOMAIN}/${WEB_LABEL}" >/dev/null
launchctl kickstart -k "${DOMAIN}/${API_LABEL}"
launchctl kickstart -k "${DOMAIN}/${WEB_LABEL}"

for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 \
    && curl -fsS "http://127.0.0.1:${WEB_PORT}/" >/dev/null 2>&1 \
    && python3 - "${API_PORT}" <<'PY' >/dev/null 2>&1
import json
import sys
import urllib.request

port = sys.argv[1]
paths = json.load(
    urllib.request.urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=2)
)["paths"]
required = {
    "/api/platform/projects/{project_id}/applications/v4",
    "/api/platform/projects/{project_id}/distributed-runtime",
    "/api/platform/projects/{project_id}/automation",
}
if not required.issubset(paths):
    raise SystemExit(1)
PY
  then
    printf 'public_api_pid=%s public_web_pid=%s api_port=%s web_port=%s\n' \
      "$(lsof -tiTCP:"${API_PORT}" -sTCP:LISTEN | head -1)" \
      "$(lsof -tiTCP:"${WEB_PORT}" -sTCP:LISTEN | head -1)" \
      "${API_PORT}" "${WEB_PORT}"
    exit 0
  fi
  sleep 0.5
done

echo "Public services did not become V4-ready" >&2
exit 1
