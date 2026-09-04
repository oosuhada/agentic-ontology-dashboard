#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

load_team_env_file() {
  local line key value
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
    case "${line}" in
      export\ ONTOLOGY_DASHBOARD_TEAM_*=*) line="${line#export }" ;;
      ONTOLOGY_DASHBOARD_TEAM_*=*) ;;
      *) continue ;;
    esac
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      ONTOLOGY_DASHBOARD_TEAM_DB_HOST) : "${ONTOLOGY_DASHBOARD_TEAM_DB_HOST:=${value}}" ;;
      ONTOLOGY_DASHBOARD_TEAM_DB_PORT) : "${ONTOLOGY_DASHBOARD_TEAM_DB_PORT:=${value}}" ;;
      ONTOLOGY_DASHBOARD_TEAM_DB_NAME) : "${ONTOLOGY_DASHBOARD_TEAM_DB_NAME:=${value}}" ;;
      ONTOLOGY_DASHBOARD_TEAM_DB_USER) : "${ONTOLOGY_DASHBOARD_TEAM_DB_USER:=${value}}" ;;
      ONTOLOGY_DASHBOARD_TEAM_DB_PASSWORD) : "${ONTOLOGY_DASHBOARD_TEAM_DB_PASSWORD:=${value}}" ;;
      ONTOLOGY_DASHBOARD_TEAM_ORGANIZATION_ID) : "${ONTOLOGY_DASHBOARD_TEAM_ORGANIZATION_ID:=${value}}" ;;
      ONTOLOGY_DASHBOARD_TEAM_PROJECT_ID) : "${ONTOLOGY_DASHBOARD_TEAM_PROJECT_ID:=${value}}" ;;
      ONTOLOGY_DASHBOARD_TEAM_WORKSPACE_ID) : "${ONTOLOGY_DASHBOARD_TEAM_WORKSPACE_ID:=${value}}" ;;
    esac
  done < .env
}

if [[ -f .env ]]; then
  load_team_env_file
fi

DB_HOST="${ONTOLOGY_DASHBOARD_TEAM_DB_HOST:-gabriels-m1-mac-mini.tailb988c5.ts.net}"
DB_PORT="${ONTOLOGY_DASHBOARD_TEAM_DB_PORT:-15432}"
DB_NAME="${ONTOLOGY_DASHBOARD_TEAM_DB_NAME:-ontology_dashboard}"
DB_USER="${ONTOLOGY_DASHBOARD_TEAM_DB_USER:-ontology_team_readonly}"

APP_ORGANIZATION_ID="${ONTOLOGY_DASHBOARD_TEAM_ORGANIZATION_ID:-org-ontology-demo}"
APP_PROJECT_ID="${ONTOLOGY_DASHBOARD_TEAM_PROJECT_ID:-manufacturing-demo-project}"
APP_WORKSPACE_ID="${ONTOLOGY_DASHBOARD_TEAM_WORKSPACE_ID:-manufacturing-demo}"

PASSWORD="${ONTOLOGY_DASHBOARD_TEAM_DB_PASSWORD:-${PGPASSWORD:-}}"

usage() {
  cat <<'EOF'
Usage:
  ONTOLOGY_DASHBOARD_TEAM_DB_PASSWORD=... scripts/connect_team_db.sh [--check]

Optional scope overrides:
  ONTOLOGY_DASHBOARD_TEAM_PROJECT_ID=azure-fleet-maintenance-project \
  ONTOLOGY_DASHBOARD_TEAM_WORKSPACE_ID=azure-fleet-maintenance \
  scripts/connect_team_db.sh

Supported local modes:
  --check   Verify connection and scope, then exit.

The password is read only from ONTOLOGY_DASHBOARD_TEAM_DB_PASSWORD or PGPASSWORD.
Do not commit it to .env.example, docs, or shell history.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql is required. Install PostgreSQL client tools first." >&2
  exit 1
fi

if [[ -z "${PASSWORD}" ]]; then
  echo "Set ONTOLOGY_DASHBOARD_TEAM_DB_PASSWORD or PGPASSWORD before running this script." >&2
  exit 1
fi

export PGPASSWORD="${PASSWORD}"
export PGOPTIONS="-c app.organization_id=${APP_ORGANIZATION_ID} -c app.project_id=${APP_PROJECT_ID} -c app.workspace_id=${APP_WORKSPACE_ID}"

echo "Connecting to ${DB_HOST}:${DB_PORT}/${DB_NAME} as ${DB_USER}"
echo "Scope: ${APP_ORGANIZATION_ID} / ${APP_PROJECT_ID} / ${APP_WORKSPACE_ID}"

if [[ "${1:-}" == "--check" ]]; then
  psql \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    -v ON_ERROR_STOP=1 \
    -c "SELECT current_setting('app.organization_id', true) AS organization_id, current_setting('app.project_id', true) AS project_id, current_setting('app.workspace_id', true) AS workspace_id;"
  exit 0
fi

psql \
  -h "${DB_HOST}" \
  -p "${DB_PORT}" \
  -U "${DB_USER}" \
  -d "${DB_NAME}" \
  -v ON_ERROR_STOP=1
