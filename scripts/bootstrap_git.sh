#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="oosuhada"
REPO_NAME="factory-signal-board"
REPO_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}.git"
AUTHOR_NAME="우수"
AUTHOR_EMAIL="185910926+oosuhada@users.noreply.github.com"
TAG_NAMES=(
  "p2-stage0-bootstrap-v1"
  "p2-stage1-scope-v1"
)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

command -v git >/dev/null 2>&1 || {
  echo "git is required"
  exit 1
}

command -v gh >/dev/null 2>&1 || {
  echo "GitHub CLI (gh) is required"
  exit 1
}

gh auth status >/dev/null

if [[ ! -d .git ]]; then
  git init -b main
fi

git config user.name "${AUTHOR_NAME}"
git config user.email "${AUTHOR_EMAIL}"

git add .

if git rev-parse --verify HEAD >/dev/null 2>&1; then
  if ! git diff --cached --quiet; then
    git commit -m "docs: bootstrap workspace and define Operations scope"
  fi
else
  git commit -m "docs: bootstrap workspace and define Operations scope"
fi

if gh repo view "${REPO_OWNER}/${REPO_NAME}" >/dev/null 2>&1; then
  echo "GitHub repository already exists: ${REPO_OWNER}/${REPO_NAME}"
else
  gh repo create "${REPO_OWNER}/${REPO_NAME}" \
    --private \
    --description "Role-aware predictive maintenance reports and dynamic dashboards" \
    --source . \
    --remote origin
fi

if git remote get-url origin >/dev/null 2>&1; then
  current_origin="$(git remote get-url origin)"
  if [[ "${current_origin}" != "${REPO_URL}" ]]; then
    git remote set-url origin "${REPO_URL}"
  fi
else
  git remote add origin "${REPO_URL}"
fi

git branch -M main
git push -u origin main

for tag_name in "${TAG_NAMES[@]}"; do
  if git rev-parse "${tag_name}" >/dev/null 2>&1; then
    echo "Tag already exists: ${tag_name}"
  else
    git tag -a "${tag_name}" -m "Project 2 verified snapshot: ${tag_name}"
  fi
  git push origin "${tag_name}"
done

echo
echo "Stage 0 and Stage 1 Git bootstrap complete"
echo "Local:  ${ROOT_DIR}"
echo "Remote: https://github.com/${REPO_OWNER}/${REPO_NAME}"
echo "Branch: main"
echo "Tags:   ${TAG_NAMES[*]}"
echo
echo "Note: Stage 0 and Stage 1 share the same initial commit because the"
echo "independent repository was initialized after the scope documents were completed."
