#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

API_HOST="${APP_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8100}"
WEB_PORT="${WEB_PORT:-3100}"
API_PID_FILE="/tmp/ontology-dashboard-api.pid"
WEB_PID_FILE="/tmp/ontology-dashboard-web.pid"
API_LOG="/tmp/ontology-dashboard-api.log"
WEB_LOG="/tmp/ontology-dashboard-web.log"

stop_pid() {
  local pid="$1"
  local expected="$2"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 0
  kill -0 "${pid}" 2>/dev/null || return 0
  local command
  command="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
  if [[ "${command}" != *"${expected}"* ]]; then
    echo "Refusing to stop PID ${pid}: command does not contain ${expected}" >&2
    return 1
  fi
  kill -TERM "${pid}"
  for _ in $(seq 1 30); do
    kill -0 "${pid}" 2>/dev/null || return 0
    sleep 0.2
  done
  kill -KILL "${pid}" 2>/dev/null || true
}

stop_service() {
  local pid_file="$1"
  local port="$2"
  local expected="$3"
  if [[ -f "${pid_file}" ]]; then
    stop_pid "$(tr -d '[:space:]' < "${pid_file}")" "${expected}"
  fi
  while IFS= read -r listener_pid; do
    [[ -n "${listener_pid}" ]] || continue
    stop_pid "${listener_pid}" "${expected}"
  done < <(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | sort -u)
}

stop_service "${API_PID_FILE}" "${API_PORT}" "uvicorn ontology_dashboard.app:app"
stop_service "${WEB_PID_FILE}" "${WEB_PORT}" "vite"
sleep 0.5

: > "${API_LOG}"
: > "${WEB_LOG}"
export PYTHONPATH="${ROOT_DIR}/api:${ROOT_DIR}/ml/src"

if [[ ! -f "${ROOT_DIR}/web/dist/index.html" ]]; then
  echo "web/dist is missing; run: npm --prefix web run build" >&2
  exit 1
fi

API_PID="$(lsof -tiTCP:"${API_PORT}" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
if [[ -z "${API_PID}" ]]; then
  nohup "${ROOT_DIR}/.venv/bin/python" -m uvicorn ontology_dashboard.app:app \
    --host "${API_HOST}" --port "${API_PORT}" >> "${API_LOG}" 2>&1 &
  API_PID=$!
fi

WEB_PID="$(lsof -tiTCP:"${WEB_PORT}" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
if [[ -z "${WEB_PID}" ]]; then
  nohup bash -c 'cd "$1" && exec ./node_modules/.bin/vite preview --host "$2" --port "$3" --strictPort' \
    _ "${ROOT_DIR}/web" "${API_HOST}" "${WEB_PORT}" >> "${WEB_LOG}" 2>&1 &
  WEB_PID=$!
fi

for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null \
    && curl -fsS "http://127.0.0.1:${WEB_PORT}/" >/dev/null; then
    API_PID="$(lsof -tiTCP:"${API_PORT}" -sTCP:LISTEN | head -1)"
    WEB_PID="$(lsof -tiTCP:"${WEB_PORT}" -sTCP:LISTEN | head -1)"
    printf '%s\n' "${API_PID}" > "${API_PID_FILE}"
    printf '%s\n' "${WEB_PID}" > "${WEB_PID_FILE}"
    printf 'api_pid=%s web_pid=%s api_port=%s web_port=%s\n' \
      "${API_PID}" "${WEB_PID}" "${API_PORT}" "${WEB_PORT}"
    exit 0
  fi
  sleep 1
done

echo "Services did not become healthy within 90 seconds" >&2
exit 1
