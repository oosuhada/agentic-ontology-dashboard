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

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
API_HOST="${APP_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8100}"
WEB_PORT="${WEB_PORT:-3100}"

command -v "${PYTHON_BIN}" >/dev/null 2>&1 || { echo "python3 is required"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "Node.js is required"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm is required"; exit 1; }

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/pip" install -e ml -e api

if [[ ! -d web/node_modules ]]; then
  npm --prefix web install --no-audit --no-fund
fi

export PYTHONPATH="${ROOT_DIR}/api:${ROOT_DIR}/ml/src"
export ONTOLOGY_DASHBOARD_DB="${ONTOLOGY_DASHBOARD_DB:-${FACTORY_SIGNAL_DB:-${ROOT_DIR}/data/local/ontology_dashboard.db}}"
export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://${API_HOST}:${API_PORT}}"

"${VENV_DIR}/bin/python" scripts/preflight.py

"${VENV_DIR}/bin/python" -m uvicorn ontology_dashboard.app:app \
  --host "${API_HOST}" --port "${API_PORT}" > /tmp/ontology-dashboard-api.log 2>&1 &
API_PID=$!

npm --prefix web run dev -- --host "${API_HOST}" --port "${WEB_PORT}" --strictPort \
  > /tmp/ontology-dashboard-web.log 2>&1 &
WEB_PID=$!

cleanup() {
  kill "${API_PID}" "${WEB_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 60); do
  if curl -fsS "http://${API_HOST}:${API_PORT}/health" >/dev/null 2>&1 \
    && curl -fsS "http://${API_HOST}:${WEB_PORT}/" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS "http://${API_HOST}:${API_PORT}/health" >/dev/null || {
  echo "API failed to start. See /tmp/ontology-dashboard-api.log"
  exit 1
}
curl -fsS "http://${API_HOST}:${WEB_PORT}/" >/dev/null || {
  echo "Web failed to start. See /tmp/ontology-dashboard-web.log"
  exit 1
}

echo
printf 'Ontology Dashboard is running\n'
printf '  Login: http://%s:%s/login\n' "${API_HOST}" "${WEB_PORT}"
printf '  API: http://%s:%s/docs\n' "${API_HOST}" "${API_PORT}"
printf '  Logs: /tmp/ontology-dashboard-{api,web}.log\n'
echo 'Press Ctrl+C to stop.'

if command -v open >/dev/null 2>&1 && [[ "${OPEN_BROWSER:-1}" == "1" ]]; then
  open "http://${API_HOST}:${WEB_PORT}/login" >/dev/null 2>&1 || true
fi

wait
