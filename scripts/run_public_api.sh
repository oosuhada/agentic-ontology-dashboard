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

export PYTHONPATH="${ROOT_DIR}/systems/backend:${ROOT_DIR}/ml/src"
API_HOST="${APP_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8100}"

# Fail before accepting traffic when the configured database cannot be
# migrated. This also prevents the public LaunchAgent from silently falling
# back to an unrelated legacy SQLite file when PostgreSQL is configured in
# the project .env.
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/migrate_database.py"

exec "${ROOT_DIR}/.venv/bin/python" -m uvicorn app.main:app \
  --host "${API_HOST}" \
  --port "${API_PORT}"
