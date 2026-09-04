#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

EXTERNAL_ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK="${ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK-}"
EXTERNAL_LLM_MODEL="${LLM_MODEL-}"
EXTERNAL_LLM_PROVIDER="${LLM_PROVIDER-}"
EXTERNAL_OPENAI_API_KEY="${OPENAI_API_KEY-}"
EXTERNAL_LLM_API_KEY="${LLM_API_KEY-}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -n "${EXTERNAL_ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK}" ]]; then
  export ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK="${EXTERNAL_ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK}"
fi
if [[ -n "${EXTERNAL_LLM_MODEL}" ]]; then
  export LLM_MODEL="${EXTERNAL_LLM_MODEL}"
fi
if [[ -n "${EXTERNAL_LLM_PROVIDER}" ]]; then
  export LLM_PROVIDER="${EXTERNAL_LLM_PROVIDER}"
fi
if [[ -n "${EXTERNAL_OPENAI_API_KEY}" ]]; then
  export OPENAI_API_KEY="${EXTERNAL_OPENAI_API_KEY}"
fi
if [[ -n "${EXTERNAL_LLM_API_KEY}" ]]; then
  export LLM_API_KEY="${EXTERNAL_LLM_API_KEY}"
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
APP_BIND_HOST="${APP_HOST:-127.0.0.1}"
APP_CHECK_HOST="${APP_CHECK_HOST:-127.0.0.1}"
API_PORT_START="${API_PORT:-8100}"
WEB_PORT_START="${WEB_PORT:-3100}"
POSTGRES_PORT_START="${POSTGRES_PORT:-5432}"
PORT_RETRY_LIMIT="${PORT_RETRY_LIMIT:-20}"
AUTO_START_DOCKER="${AUTO_START_DOCKER:-1}"
DOCKER_START_TIMEOUT_SECONDS="${DOCKER_START_TIMEOUT_SECONDS:-90}"
SKIP_POSTGRES="${SKIP_POSTGRES:-0}"
STOP_POSTGRES_ON_EXIT="${STOP_POSTGRES_ON_EXIT:-0}"
SKIP_DEMO_BOOTSTRAP="${SKIP_DEMO_BOOTSTRAP:-0}"
PM_DEMO_PACKAGE_ROOT="${PM_DEMO_PACKAGE_ROOT:-}"
ENABLE_AGENT_SUMMARY_WATCHER="${ENABLE_AGENT_SUMMARY_WATCHER:-0}"
AGENT_SUMMARY_WATCHER_INTERVAL_SECONDS="${AGENT_SUMMARY_WATCHER_INTERVAL_SECONDS:-60}"
AGENT_SUMMARY_WATCHER_LIMIT="${AGENT_SUMMARY_WATCHER_LIMIT:-10}"
AGENT_SUMMARY_WATCHER_MAX_ATTEMPTS="${AGENT_SUMMARY_WATCHER_MAX_ATTEMPTS:-2}"
AGENT_SUMMARY_WATCHER_MAX_ITERATIONS="${AGENT_SUMMARY_WATCHER_MAX_ITERATIONS:-}"
AGENT_SUMMARY_WATCHER_STALE_POLICY="${AGENT_SUMMARY_WATCHER_STALE_POLICY:-summary_key}"

API_LOG="${API_LOG:-/tmp/ontology-dashboard-live-api.log}"
WEB_LOG="${WEB_LOG:-/tmp/ontology-dashboard-live-web.log}"
AGENT_SUMMARY_WATCHER_LOG="${AGENT_SUMMARY_WATCHER_LOG:-/tmp/ontology-dashboard-agent-summary-watcher.log}"

command -v "${PYTHON_BIN}" >/dev/null 2>&1 || { echo "python3 is required"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "Node.js is required"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm is required"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "curl is required"; exit 1; }

is_port_open() {
  local host="$1"
  local port="$2"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1 && return 0
  fi
  nc -z "${host}" "${port}" >/dev/null 2>&1
}

next_free_port() {
  local host="$1"
  local start="$2"
  local limit="$3"
  local port
  for ((port = start; port < start + limit; port++)); do
    if ! is_port_open "${host}" "${port}"; then
      printf '%s\n' "${port}"
      return 0
    fi
  done
  echo "No free port found from ${start} to $((start + limit - 1))" >&2
  return 1
}

has_v3_1_demo_package() {
  local package_root="$1"
  [[ -f "${package_root}/dist/predictive_maintenance_canonical_v3.1.zip" ]] \
    && [[ -f "${package_root}/dist/predictive_maintenance_canonical_v3.1.zip.sha256" ]] \
    && [[ -f "${package_root}/canonical/dataset/dataset_manifest.json" ]]
}

resolve_pm_demo_package_root() {
  if [[ -n "${PM_DEMO_PACKAGE_ROOT}" ]]; then
    if has_v3_1_demo_package "${PM_DEMO_PACKAGE_ROOT}"; then
      printf '%s\n' "${PM_DEMO_PACKAGE_ROOT}"
      return 0
    fi
    echo "PM_DEMO_PACKAGE_ROOT is set but is not a complete V3.1 demo package: ${PM_DEMO_PACKAGE_ROOT}" >&2
    return 1
  fi

  local candidate
  for candidate in \
    "${ROOT_DIR}/data/raw/predictive_maintenance_canonical_v3.1" \
    "${ROOT_DIR}/data/raw/predictive_maintenance_canonical_v3_1" \
    "${HOME}/Downloads/predictive_maintenance_canonical_v3.1" \
    "${ROOT_DIR}/../gen-data" \
    "${ROOT_DIR}/../gen-data/predictive_maintenance_canonical_v3_1"
  do
    if has_v3_1_demo_package "${candidate}"; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

wait_for_docker() {
  local timeout="$1"
  for _ in $(seq 1 "${timeout}"); do
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

ensure_docker() {
  command -v docker >/dev/null 2>&1 || { echo "Docker CLI is required"; exit 1; }
  if docker info >/dev/null 2>&1; then
    return 0
  fi

  if [[ "${AUTO_START_DOCKER}" == "1" && "$(uname -s)" == "Darwin" && "$(command -v open || true)" != "" ]]; then
    echo "Docker daemon is not running; trying to open Docker or OrbStack..."
    open -ga Docker >/dev/null 2>&1 || open -ga OrbStack >/dev/null 2>&1 || true
    if wait_for_docker "${DOCKER_START_TIMEOUT_SECONDS}"; then
      return 0
    fi
  fi

  echo "Docker daemon is not running. Start Docker Desktop or OrbStack, then retry." >&2
  exit 1
}

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/pip" install -e ml -e 'systems/backend[postgres]'

if [[ ! -d systems/frontend/node_modules ]]; then
  npm --prefix systems/frontend install --no-audit --no-fund
fi

API_PORT="$(next_free_port "${APP_CHECK_HOST}" "${API_PORT_START}" "${PORT_RETRY_LIMIT}")"
WEB_PORT="$(next_free_port "${APP_CHECK_HOST}" "${WEB_PORT_START}" "${PORT_RETRY_LIMIT}")"
POSTGRES_PORT="$(next_free_port "${APP_CHECK_HOST}" "${POSTGRES_PORT_START}" "${PORT_RETRY_LIMIT}")"

if [[ "${API_PORT}" != "${API_PORT_START}" ]]; then
  echo "API port ${API_PORT_START} is busy; using ${API_PORT}"
fi
if [[ "${WEB_PORT}" != "${WEB_PORT_START}" ]]; then
  echo "Web port ${WEB_PORT_START} is busy; using ${WEB_PORT}"
fi

export PYTHONPATH="${ROOT_DIR}:${ROOT_DIR}/systems/backend:${ROOT_DIR}/ml/src"
export ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK="${ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK:-1}"
export SEED_DEMO_ACCOUNTS="${SEED_DEMO_ACCOUNTS:-1}"
export ONTOLOGY_DASHBOARD_SEED_REFERENCE_DATA="${ONTOLOGY_DASHBOARD_SEED_REFERENCE_DATA:-true}"

if [[ "${SKIP_POSTGRES}" != "1" ]]; then
  ensure_docker
  if [[ "${POSTGRES_PORT}" != "${POSTGRES_PORT_START}" ]]; then
    echo "Postgres port ${POSTGRES_PORT_START} is busy; using ${POSTGRES_PORT}"
  fi
  export POSTGRES_PORT
  docker compose -f infra/docker-compose.yml --profile polyglot up -d postgres
  POSTGRES_MAPPED_PORT="$(docker compose -f infra/docker-compose.yml --profile polyglot port postgres 5432 2>/dev/null | awk -F: 'END {print $NF}')"
  if [[ -n "${POSTGRES_MAPPED_PORT}" ]]; then
    POSTGRES_PORT="${POSTGRES_MAPPED_PORT}"
  fi
  export ONTOLOGY_DASHBOARD_DATABASE_URL="${ONTOLOGY_DASHBOARD_DATABASE_URL:-postgresql://ontology:ontology-local-only@127.0.0.1:${POSTGRES_PORT}/ontology_dashboard}"
else
  export ONTOLOGY_DASHBOARD_DATABASE_URL="${ONTOLOGY_DASHBOARD_DATABASE_URL:-}"
fi

if [[ -n "${ONTOLOGY_DASHBOARD_DATABASE_URL}" && "${SKIP_DEMO_BOOTSTRAP}" != "1" ]]; then
  if RESOLVED_PM_DEMO_PACKAGE_ROOT="$(resolve_pm_demo_package_root)"; then
    echo "Using V3.1 demo package: ${RESOLVED_PM_DEMO_PACKAGE_ROOT}"
    "${VENV_DIR}/bin/python" scripts/bootstrap_predictive_maintenance_v3_1_demo.py \
      --package-root "${RESOLVED_PM_DEMO_PACKAGE_ROOT}" \
      --database-url "${ONTOLOGY_DASHBOARD_DATABASE_URL}" \
      --skip-graph
  else
    echo "Skipping V3.1 demo bootstrap; no complete package found."
    echo "Set PM_DEMO_PACKAGE_ROOT to a directory containing dist/predictive_maintenance_canonical_v3.1.zip and canonical/dataset/dataset_manifest.json."
  fi
fi

export VITE_API_BASE_URL="http://${APP_CHECK_HOST}:${API_PORT}"

: > "${API_LOG}"
: > "${WEB_LOG}"

"${VENV_DIR}/bin/python" -m uvicorn app.main:app \
  --host "${APP_BIND_HOST}" --port "${API_PORT}" > "${API_LOG}" 2>&1 &
API_PID=$!

(
  cd systems/frontend
  npx vite --host "${APP_BIND_HOST}" --port "${WEB_PORT}" --strictPort
) > "${WEB_LOG}" 2>&1 &
WEB_PID=$!
WATCHER_PID=""

cleanup() {
  if [[ -n "${WATCHER_PID}" ]]; then
    kill "${WATCHER_PID}" 2>/dev/null || true
  fi
  kill "${API_PID}" "${WEB_PID}" 2>/dev/null || true
  if [[ "${SKIP_POSTGRES}" != "1" && "${STOP_POSTGRES_ON_EXIT}" == "1" ]]; then
    docker compose -f infra/docker-compose.yml --profile polyglot stop postgres >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 90); do
  if curl -fsS "http://${APP_CHECK_HOST}:${API_PORT}/health" >/dev/null 2>&1 \
    && curl -fsS "http://${APP_CHECK_HOST}:${WEB_PORT}/" >/dev/null 2>&1; then
    echo
    printf 'Ontology Dashboard live local runtime is running\n'
    printf '  Web: http://%s:%s/login\n' "${APP_CHECK_HOST}" "${WEB_PORT}"
    printf '  API: http://%s:%s/docs\n' "${APP_CHECK_HOST}" "${API_PORT}"
    if [[ -n "${ONTOLOGY_DASHBOARD_DATABASE_URL}" ]]; then
      printf '  DB: PostgreSQL on host port %s\n' "${POSTGRES_PORT}"
    fi
    if [[ "${ENABLE_AGENT_SUMMARY_WATCHER}" == "1" && -n "${ONTOLOGY_DASHBOARD_DATABASE_URL}" ]]; then
      : > "${AGENT_SUMMARY_WATCHER_LOG}"
      WATCHER_ARGS=(
        scripts/watch_agent_review_summaries.py
        --database "${ONTOLOGY_DASHBOARD_DATABASE_URL}" \
        --watch \
        --limit "${AGENT_SUMMARY_WATCHER_LIMIT}" \
        --max-attempts "${AGENT_SUMMARY_WATCHER_MAX_ATTEMPTS}" \
        --interval-seconds "${AGENT_SUMMARY_WATCHER_INTERVAL_SECONDS}" \
        --stale-policy "${AGENT_SUMMARY_WATCHER_STALE_POLICY}"
      )
      if [[ -n "${AGENT_SUMMARY_WATCHER_MAX_ITERATIONS}" ]]; then
        WATCHER_ARGS+=(--max-iterations "${AGENT_SUMMARY_WATCHER_MAX_ITERATIONS}")
      fi
      PYTHONUNBUFFERED=1 "${VENV_DIR}/bin/python" "${WATCHER_ARGS[@]}" > "${AGENT_SUMMARY_WATCHER_LOG}" 2>&1 &
      WATCHER_PID=$!
      printf '  Agent Summary Watcher: pid %s, interval %ss, limit %s, max attempts %s, stale policy %s\n' "${WATCHER_PID}" "${AGENT_SUMMARY_WATCHER_INTERVAL_SECONDS}" "${AGENT_SUMMARY_WATCHER_LIMIT}" "${AGENT_SUMMARY_WATCHER_MAX_ATTEMPTS}" "${AGENT_SUMMARY_WATCHER_STALE_POLICY}"
      if [[ -n "${AGENT_SUMMARY_WATCHER_MAX_ITERATIONS}" ]]; then
        printf '  Agent Summary Watcher max iterations: %s\n' "${AGENT_SUMMARY_WATCHER_MAX_ITERATIONS}"
      fi
      printf '  Logs: %s %s %s\n' "${API_LOG}" "${WEB_LOG}" "${AGENT_SUMMARY_WATCHER_LOG}"
    else
      printf '  Logs: %s %s\n' "${API_LOG}" "${WEB_LOG}"
    fi
    if [[ "${SKIP_POSTGRES}" != "1" && "${STOP_POSTGRES_ON_EXIT}" == "1" ]]; then
      echo 'Press Ctrl+C to stop API, Web, watcher, and Docker Postgres.'
    else
      echo 'Press Ctrl+C to stop API, Web, and watcher. Docker Postgres keeps running.'
    fi
    if command -v open >/dev/null 2>&1 && [[ "${OPEN_BROWSER:-1}" == "1" ]]; then
      open "http://${APP_CHECK_HOST}:${WEB_PORT}/login" >/dev/null 2>&1 || true
    fi
    wait
  fi
  sleep 1
done

echo "Services did not become healthy within 90 seconds" >&2
echo "API log: ${API_LOG}" >&2
echo "Web log: ${WEB_LOG}" >&2
exit 1
