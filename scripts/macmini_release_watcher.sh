#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

REPO_SLUG="${ONTOLOGY_RELEASE_REPO_SLUG:-oosuhada/agentic-ontology-dashboard}"
REPO_URL="${ONTOLOGY_RELEASE_REPO_URL:-https://github.com/${REPO_SLUG}.git}"
WATCH_ROOT="${ONTOLOGY_MACMINI_WATCH_ROOT:-$HOME/Services/ontology-dashboard-release}"
SOURCE_ROOT="$WATCH_ROOT/source"
PROD_ROOT="${ONTOLOGY_MACMINI_PROD_ROOT:-$HOME/Services/ontology-dashboard-prod}"
LOCK_DIR="$WATCH_ROOT/.watch-lock"
RUNS_FILE="$WATCH_ROOT/architecture-runs.json"
FAILURE_STATE_FILE="$WATCH_ROOT/last-deploy-failure"
RETRY_SECONDS="${ONTOLOGY_RELEASE_RETRY_SECONDS:-900}"
MIN_FREE_GB="${ONTOLOGY_RELEASE_MIN_FREE_GB:-20}"
DEPLOY_STARTED=0
TARGET_SHA=""

mkdir -p "$WATCH_ROOT" "$PROD_ROOT"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "release watcher is already running"
  exit 0
fi

cleanup() {
  local status=$?
  if [[ "$status" -ne 0 && "$DEPLOY_STARTED" -eq 1 && -n "$TARGET_SHA" ]]; then
    printf '%s %s\n' "$TARGET_SHA" "$(date +%s)" > "$FAILURE_STATE_FILE"
  fi
  trap - EXIT
  rm -rf "$LOCK_DIR"
  exit "$status"
}
trap cleanup EXIT

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

if [[ -f "$FAILURE_STATE_FILE" ]]; then
  read -r FAILED_SHA FAILED_AT < "$FAILURE_STATE_FILE" || true
  if [[ "$FAILED_SHA" == "$TARGET_SHA" && "$FAILED_AT" =~ ^[0-9]+$ ]]; then
    now="$(date +%s)"
    age=$((now - FAILED_AT))
    if (( age < RETRY_SECONDS )); then
      echo "deployment for $TARGET_SHA is in failure backoff: ${age}s/${RETRY_SECONDS}s"
      exit 0
    fi
  fi
fi

FRONTEND_EVALUATED_SHA=""
if [[ -f "$PROD_ROOT/frontend-deploy-base-sha" ]]; then
  FRONTEND_EVALUATED_SHA="$(tr -d '[:space:]' < "$PROD_ROOT/frontend-deploy-base-sha")"
fi
BACKEND_EVALUATED_SHA=""
if [[ -f "$PROD_ROOT/backend-deploy-base-sha" ]]; then
  BACKEND_EVALUATED_SHA="$(tr -d '[:space:]' < "$PROD_ROOT/backend-deploy-base-sha")"
fi
GRAPH_EVALUATED_SHA=""
if [[ -f "$PROD_ROOT/graph-deploy-base-sha" ]]; then
  GRAPH_EVALUATED_SHA="$(tr -d '[:space:]' < "$PROD_ROOT/graph-deploy-base-sha")"
fi
HOST_POLICY_EVALUATED_SHA=""
if [[ -f "$PROD_ROOT/host-policy-base-sha" ]]; then
  HOST_POLICY_EVALUATED_SHA="$(tr -d '[:space:]' < "$PROD_ROOT/host-policy-base-sha")"
fi

if [[ "$FRONTEND_EVALUATED_SHA" == "$TARGET_SHA" \
  && "$BACKEND_EVALUATED_SHA" == "$TARGET_SHA" \
  && "$GRAPH_EVALUATED_SHA" == "$TARGET_SHA" \
  && "$HOST_POLICY_EVALUATED_SHA" == "$TARGET_SHA" ]]; then
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

free_kb="$(df -Pk /System/Volumes/Data 2>/dev/null | awk 'NR == 2 {print $4}')"
if [[ "$free_kb" =~ ^[0-9]+$ ]] && (( free_kb < MIN_FREE_GB * 1024 * 1024 )); then
  free_gb=$((free_kb / 1024 / 1024))
  echo "refusing ontology deployment with only ${free_gb}GB free; minimum is ${MIN_FREE_GB}GB" >&2
  exit 75
fi

if [[ ! -d "$SOURCE_ROOT/.git" ]]; then
  git clone --filter=blob:none --no-checkout "$REPO_URL" "$SOURCE_ROOT"
else
  # The release source predates the personal-repository cutover on some Mac
  # mini installations. Reconcile the existing clone on every run so the
  # watcher cannot silently keep following the old team repository.
  git -C "$SOURCE_ROOT" remote set-url origin "$REPO_URL"
fi

git -C "$SOURCE_ROOT" fetch --prune origin main
FETCHED_SHA="$(git -C "$SOURCE_ROOT" rev-parse FETCH_HEAD)"
if [[ "$FETCHED_SHA" != "$TARGET_SHA" ]]; then
  echo "main changed while preparing deployment; retry on next watcher run" >&2
  exit 0
fi

git -C "$SOURCE_ROOT" checkout --detach --force "$TARGET_SHA"
git -C "$SOURCE_ROOT" clean -ffd

if [[ ! -x "$SOURCE_ROOT/scripts/deploy_macmini_frontend.sh" ]] \
  || [[ ! -x "$SOURCE_ROOT/scripts/deploy_macmini_backend.sh" ]]; then
  echo "verified main does not contain the Mac mini deployment scripts yet; waiting"
  exit 0
fi

echo "Deploying CI-verified main $TARGET_SHA"
DEPLOY_STARTED=1
GITHUB_SHA="$TARGET_SHA" \
ONTOLOGY_MACMINI_PROD_ROOT="$PROD_ROOT" \
  "$SOURCE_ROOT/scripts/deploy_macmini_backend.sh"
if [[ -x "$SOURCE_ROOT/scripts/deploy_macmini_graph.sh" ]]; then
  GITHUB_SHA="$TARGET_SHA" \
  ONTOLOGY_MACMINI_PROD_ROOT="$PROD_ROOT" \
    "$SOURCE_ROOT/scripts/deploy_macmini_graph.sh"
fi
GITHUB_SHA="$TARGET_SHA" \
ONTOLOGY_MACMINI_PROD_ROOT="$PROD_ROOT" \
  "$SOURCE_ROOT/scripts/deploy_macmini_frontend.sh"

# Install/update the cadence-based home-server refresh only after Backend,
# Graph, and Frontend have all converged on the same verified SHA. This avoids
# waking a new Generator against an older graph projection during deployment.
if [[ -f "$SOURCE_ROOT/infra/macmini/install-background-refresh.sh" ]]; then
  ONTOLOGY_MACMINI_WATCH_ROOT="$WATCH_ROOT" \
  ONTOLOGY_MACMINI_PROD_ROOT="$PROD_ROOT" \
    /bin/bash "$SOURCE_ROOT/infra/macmini/install-background-refresh.sh"
fi

# Keep the low-traffic public demo ingress/supervisors under the same
# CI-verified release source. The installer is idempotent and keeps timestamped
# nginx/cloudflared backups so a failed reload rolls back to the previous host
# configuration instead of leaving a sleeping demo unreachable.
if [[ -f "$SOURCE_ROOT/infra/macmini/install-idle-demo-supervisors.sh" ]]; then
  /bin/bash "$SOURCE_ROOT/infra/macmini/install-idle-demo-supervisors.sh"
fi

if [[ -x "$SOURCE_ROOT/scripts/prune_macmini_docker_artifacts.sh" ]]; then
  "$SOURCE_ROOT/scripts/prune_macmini_docker_artifacts.sh" "$TARGET_SHA" || \
    echo "warning: ontology Docker artifact pruning failed" >&2
fi

# Host-level launchd/nginx/cloudflared policy is part of the release contract,
# not an untracked side effect. Record it only after every installer succeeds.
printf '%s\n' "$TARGET_SHA" > "$PROD_ROOT/host-policy-base-sha"
rm -f "$FAILURE_STATE_FILE"
