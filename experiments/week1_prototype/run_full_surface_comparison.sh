#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${WEEK1_PYTHON:-${ROOT_DIR}/.venv/bin/python}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing project Python: ${PYTHON_BIN}" >&2
  exit 1
fi

export PYTHONPATH="${ROOT_DIR}/api:${ROOT_DIR}/ml/src:${ROOT_DIR}/experiments/week1_prototype${PYTHONPATH:+:${PYTHONPATH}}"
exec "${PYTHON_BIN}" "${ROOT_DIR}/experiments/week1_prototype/generate_full_surface_report.py"

