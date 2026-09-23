#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.orbstack/bin:${PATH}"

TARGET_SHA="${1:?target SHA is required}"
BUILD_CACHE_MAX_AGE="${ONTOLOGY_DOCKER_BUILD_CACHE_MAX_AGE:-72h}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for Mac mini artifact pruning" >&2
  exit 1
fi

prune_repo() {
  local repo="$1"
  local keep_one_rollback="$2"
  local rollback_kept=0
  local ref tag

  # `docker image ls` is newest-first. Keep the deployed SHA, `latest`, and
  # at most one rollback tag. Removing a tag is safe for an image that is still
  # referenced by a running container; Docker refuses to remove in-use image
  # data and the command below is deliberately best-effort.
  while IFS= read -r ref; do
    [[ -n "$ref" ]] || continue
    tag="${ref#${repo}:}"
    case "$tag" in
      latest|"$TARGET_SHA"|'<none>')
        continue
        ;;
      rollback-*)
        if [[ "$keep_one_rollback" == "yes" && "$rollback_kept" -eq 0 ]]; then
          rollback_kept=1
          continue
        fi
        ;;
    esac
    docker image rm "$ref" >/dev/null 2>&1 || true
  done < <(docker image ls "$repo" --format '{{.Repository}}:{{.Tag}}')
}

prune_repo ontology-dashboard-macmini-backend yes
prune_repo ontology-dashboard-macmini-frontend yes
prune_repo ontology-dashboard-macmini-generator-runtime no
prune_repo ontology-dashboard-macmini-project3 no

# Clear only dangling layers after tag retention and age out old BuildKit
# cache. Docker volumes and persistent database data are intentionally outside
# this script's scope.
docker image prune -f >/dev/null 2>&1 || true
docker builder prune -f --filter "until=$BUILD_CACHE_MAX_AGE" >/dev/null 2>&1 || true

echo "Pruned Mac mini Docker artifacts for ontology release $TARGET_SHA"
