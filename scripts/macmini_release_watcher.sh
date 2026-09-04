#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

REPO_SLUG="Biz-CollabCraft/ontology_dashboard"
REPO_URL="https://github.com/${REPO_SLUG}.git"
WATCH_ROOT="${ONTOLOGY_MACMINI_WATCH_ROOT:-$HOME/Services/ontology-dashboard-release}"
SOURCE_ROOT="$WATCH_ROOT/source"
PROD_ROOT="${ONTOLOGY_MACMINI_PROD_ROOT:-$HOME/Services/ontology-dashboard-prod}"
LOCK_DIR="$WATCH_ROOT/.watch-lock"
RUNS_FILE="$WATCH_ROOT/architecture-runs.json"

mkdir -p "$WATCH_ROOT" "$PROD_ROOT"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "release watcher is already running"
  exit 0
fi
trap 'rm -rf "$LOCK_DIR"' EXIT

for command in git curl python3; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "$command is required for Mac mini release watching" >&2
    exit 1
  fi
done

TARGET_SHA="$(git ls-remote "$REPO_URL" refs/heads/main | awk '{print $1}')"
if [[ ! "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "could not resolve origin/main" >&2
  exit 1
fi

EVALUATED_SHA=""
if [[ -f "$PROD_ROOT/frontend-deploy-base-sha" ]]; then
  EVALUATED_SHA="$(tr -d '[:space:]' < "$PROD_ROOT/frontend-deploy-base-sha")"
fi

if [[ "$EVALUATED_SHA" == "$TARGET_SHA" ]]; then
  echo "main already evaluated at $TARGET_SHA"
  exit 0
fi

curl --fail --silent --show-error --location --max-time 20 \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/${REPO_SLUG}/actions/workflows/architecture.yml/runs?branch=main&event=push&per_page=30" \
  -o "$RUNS_FILE"

read -r CI_STATUS CI_CONCLUSION < <(
  python3 - "$RUNS_FILE" "$TARGET_SHA" <<'PY'
import json
import sys

path, target = sys.argv[1:]
payload = json.load(open(path, encoding="utf-8"))
for run in payload.get("workflow_runs", []):
    if run.get("head_sha") == target:
        print(run.get("status") or "missing", run.get("conclusion") or "pending")
        break
else:
    print("missing", "pending")
PY
)

if [[ "$CI_STATUS" != "completed" ]]; then
  echo "architecture CI for $TARGET_SHA is not completed yet: $CI_STATUS"
  exit 0
fi

if [[ "$CI_CONCLUSION" != "success" ]]; then
  echo "architecture CI for $TARGET_SHA is not green: $CI_CONCLUSION" >&2
  exit 0
fi

if [[ ! -d "$SOURCE_ROOT/.git" ]]; then
  git clone --filter=blob:none --no-checkout "$REPO_URL" "$SOURCE_ROOT"
fi

git -C "$SOURCE_ROOT" fetch --prune origin main
FETCHED_SHA="$(git -C "$SOURCE_ROOT" rev-parse FETCH_HEAD)"
if [[ "$FETCHED_SHA" != "$TARGET_SHA" ]]; then
  echo "main changed while preparing deployment; retry on next watcher run" >&2
  exit 0
fi

git -C "$SOURCE_ROOT" checkout --detach --force "$TARGET_SHA"
git -C "$SOURCE_ROOT" clean -ffd

if [[ ! -x "$SOURCE_ROOT/scripts/deploy_macmini_frontend.sh" ]]; then
  echo "verified main does not contain the Mac mini frontend deployment script yet; waiting"
  exit 0
fi

echo "Deploying CI-verified main $TARGET_SHA"
GITHUB_SHA="$TARGET_SHA" \
ONTOLOGY_MACMINI_PROD_ROOT="$PROD_ROOT" \
  "$SOURCE_ROOT/scripts/deploy_macmini_frontend.sh"
