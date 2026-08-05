#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${WEEK1_PYTHON:-${ROOT_DIR}/.venv-week1/bin/python}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing experiment Python: ${PYTHON_BIN}" >&2
  echo "Create .venv-week1 and install experiments/week1_prototype/requirements.txt" >&2
  exit 1
fi

export PYTHONPATH="${ROOT_DIR}/experiments/week1_prototype${PYTHONPATH:+:${PYTHONPATH}}"

exec "${PYTHON_BIN}" -m framework_comparison.compare \
  --iterations "${FRAMEWORK_BENCHMARK_ITERATIONS:-500}" \
  --format "${FRAMEWORK_BENCHMARK_FORMAT:-markdown}"

