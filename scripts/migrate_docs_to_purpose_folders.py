#!/usr/bin/env python3
"""Physically move legacy docs into purpose folders and rewrite local links.

Run once from the repository root:

    python3 scripts/migrate_docs_to_purpose_folders.py

The migration resolves Markdown links against each file's pre-move location,
then recalculates them against the post-move location. Plain repository-relative
path references in source, scripts, and configuration files are also updated.
"""

from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]

MOVES: dict[str, str] = {
    # Product
    "docs/10-product/project-charter.md": "docs/10-product/project-charter.md",
    "docs/10-product/domain-model.md": "docs/10-product/domain-model.md",
    "docs/10-product/dataset-strategy.md": "docs/10-product/dataset-strategy.md",
    "docs/10-product/project-catalog.md": "docs/10-product/project-catalog.md",
    "docs/10-product/core-role-report-adaptive-experience.md": "docs/10-product/core-role-report-adaptive-experience.md",
    "docs/10-product/data-dictionary.md": "docs/10-product/data-dictionary.md",
    "docs/10-product/data-gap.md": "docs/10-product/data-gap.md",
    "docs/10-product/model-baseline-results.md": "docs/10-product/model-baseline-results.md",
    "docs/10-product/operations-scope.md": "docs/10-product/operations-scope.md",
    "docs/10-product/personas.md": "docs/10-product/personas.md",
    "docs/10-product/risk-threshold-policy.md": "docs/10-product/risk-threshold-policy.md",
    "docs/10-product/role-needs-research.md": "docs/10-product/role-needs-research.md",
    # Architecture
    "docs/20-architecture/system-architecture.md": "docs/20-architecture/system-architecture.md",
    "docs/20-architecture/architecture-decisions.md": "docs/20-architecture/architecture-decisions.md",
    "docs/20-architecture/physical-namespace-relocation-inventory.md": "docs/20-architecture/physical-namespace-relocation-inventory.md",
    "docs/20-architecture/project3-adapter-contract.md": "docs/20-architecture/project3-adapter-contract.md",
    "docs/20-architecture/service-contract.md": "docs/20-architecture/service-contract.md",
    "docs/20-architecture/adr/README.md": "docs/20-architecture/adr/README.md",
    "docs/20-architecture/current-state/README.md": "docs/20-architecture/current-state/README.md",
    "docs/20-architecture/current-state/current-state.md": "docs/20-architecture/current-state/current-state.md",
    # Implementation and history
    "docs/30-implementation/project-roadmap.md": "docs/30-implementation/project-roadmap.md",
    "docs/30-implementation/implementation-status.md": "docs/30-implementation/implementation-status.md",
    "docs/30-implementation/product-convergence-roadmap.md": "docs/30-implementation/product-convergence-roadmap.md",
    "docs/30-implementation/autonomous-implementation-progress.md": "docs/30-implementation/autonomous-implementation-progress.md",
    "docs/30-implementation/pre-release-gap-analysis-and-upgrade-plan.md": "docs/30-implementation/pre-release-gap-analysis-and-upgrade-plan.md",
    "docs/30-implementation/stage-history/stage1-scope-validation.md": "docs/30-implementation/stage-history/stage1-scope-validation.md",
    "docs/30-implementation/stage-history/stage2-15-implementation-summary.md": "docs/30-implementation/stage-history/stage2-15-implementation-summary.md",
    "docs/30-implementation/stage-history/stage16-18-implementation-summary.md": "docs/30-implementation/stage-history/stage16-18-implementation-summary.md",
    "docs/30-implementation/stage-history/stage19-implementation-summary.md": "docs/30-implementation/stage-history/stage19-implementation-summary.md",
    "docs/30-implementation/stage-history/stage20-24-implementation-summary.md": "docs/30-implementation/stage-history/stage20-24-implementation-summary.md",
    "docs/30-implementation/stage-history/stage25-29-implementation-summary.md": "docs/30-implementation/stage-history/stage25-29-implementation-summary.md",
    "docs/30-implementation/stage-history/stage30-31-implementation-summary.md": "docs/30-implementation/stage-history/stage30-31-implementation-summary.md",
    "docs/30-implementation/stage-history/stage32-naming-and-runtime-safety-summary.md": "docs/30-implementation/stage-history/stage32-naming-and-runtime-safety-summary.md",
    "docs/30-implementation/stage-history/stage34-39-implementation-summary.md": "docs/30-implementation/stage-history/stage34-39-implementation-summary.md",
    "docs/30-implementation/stage-history/stage40-residual-hardening-summary.md": "docs/30-implementation/stage-history/stage40-residual-hardening-summary.md",
    "docs/30-implementation/stage-history/stage41-palantir-analytics-workbench-summary.md": "docs/30-implementation/stage-history/stage41-palantir-analytics-workbench-summary.md",
    "docs/30-implementation/stage-history/stage42-palantir-ui-modernization-summary.md": "docs/30-implementation/stage-history/stage42-palantir-ui-modernization-summary.md",
    "docs/30-implementation/stage-history/stage43-sprint0-5-frontend-acceleration-summary.md": "docs/30-implementation/stage-history/stage43-sprint0-5-frontend-acceleration-summary.md",
    # UI/UX
    "docs/40-ui-ux/reference/palantir-contour-ui-reference.md": "docs/40-ui-ux/reference/palantir-contour-ui-reference.md",
    "docs/40-ui-ux/reference/palantir-contour-dashboard-benchmark.md": "docs/40-ui-ux/reference/palantir-contour-dashboard-benchmark.md",
    "docs/40-ui-ux/plans/chart-intelligence-color-system-uiux-plan.md": "docs/40-ui-ux/plans/chart-intelligence-color-system-uiux-plan.md",
    "docs/40-ui-ux/plans/palantir-typography-loader-dashboard-interaction-plan.md": "docs/40-ui-ux/plans/palantir-typography-loader-dashboard-interaction-plan.md",
    "docs/40-ui-ux/plans/palantir-ui-gap-verification-and-plan-v2.md": "docs/40-ui-ux/plans/palantir-ui-gap-verification-and-plan-v2.md",
    "docs/40-ui-ux/plans/palantir-ui-overhaul-master-plan.md": "docs/40-ui-ux/plans/palantir-ui-overhaul-master-plan.md",
    "docs/40-ui-ux/implementation/palantir-uiux-integration-phases-1-3.md": "docs/40-ui-ux/implementation/palantir-uiux-integration-phases-1-3.md",
    # Operations
    "docs/50-operations/release-checklist.md": "docs/50-operations/release-checklist.md",
    "docs/50-operations/devspace-workflow.md": "docs/50-operations/devspace-workflow.md",
    "docs/50-operations/demo-runbook.md": "docs/50-operations/demo-runbook.md",
    "docs/50-operations/production-environment-completion-runbook.md": "docs/50-operations/production-environment-completion-runbook.md",
    "docs/50-operations/release-gate-report.md": "docs/50-operations/release-gate-report.md",
    "docs/50-operations/troubleshooting.md": "docs/50-operations/troubleshooting.md",
    # Development prompts
    "docs/60-development-prompts/next-session-autonomous-full-implementation-prompt.md": "docs/60-development-prompts/next-session-autonomous-full-implementation-prompt.md",
    "docs/60-development-prompts/next-session-chart-intelligence-uiux-prompt.md": "docs/60-development-prompts/next-session-chart-intelligence-uiux-prompt.md",
    "docs/60-development-prompts/next-session-master-prompt.md": "docs/60-development-prompts/next-session-master-prompt.md",
    "docs/60-development-prompts/next-session-ontology-dashboard-prompt.md": "docs/60-development-prompts/next-session-ontology-dashboard-prompt.md",
    "docs/60-development-prompts/next-session-palantir-ui-overhaul-prompt.md": "docs/60-development-prompts/next-session-palantir-ui-overhaul-prompt.md",
    "docs/60-development-prompts/next-session-remaining-work-execution-plan.md": "docs/60-development-prompts/next-session-remaining-work-execution-plan.md",
    "docs/60-development-prompts/next-session-typography-loader-dashboard-arrange-prompt.md": "docs/60-development-prompts/next-session-typography-loader-dashboard-arrange-prompt.md",
    # Archive
    "docs/90-archive/plans/ontology-dashboard-additional-implementation-plan.md": "docs/90-archive/plans/ontology-dashboard-additional-implementation-plan.md",
    "docs/90-archive/plans/palantir-ui-gap-verification-and-plan.md": "docs/90-archive/plans/palantir-ui-gap-verification-and-plan.md",
    "docs/90-archive/research/palantir-ui-integration-analysis-antigravity-opus-4.6.md": "docs/90-archive/research/palantir-ui-integration-analysis-antigravity-opus-4.6.md",
    "docs/90-archive/research/palantir-ui-integration-analysis-chatgpt-sol-extra-high.md": "docs/90-archive/research/palantir-ui-integration-analysis-chatgpt-sol-extra-high.md",
    "docs/90-archive/research/palantir-ui-integration-analysis-chatgpt-sol-high.md": "docs/90-archive/research/palantir-ui-integration-analysis-chatgpt-sol-high.md",
    "docs/90-archive/research/palantir-ui-integration-analysis-claude-sonnet5-extra.md": "docs/90-archive/research/palantir-ui-integration-analysis-claude-sonnet5-extra.md",
}

TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_PARTS = {
    ".git",
    ".pytest_cache",
    ".venv",
    ".vite",
    "dist",
    "node_modules",
    "test-results",
}
MARKDOWN_TARGET = re.compile(r"(?P<prefix>\]\()(?P<target>[^)]+)(?P<suffix>\))")


def normalize(path: str | PurePosixPath) -> str:
    return posixpath.normpath(PurePosixPath(path).as_posix())


def split_markdown_target(raw: str) -> tuple[str, str, str]:
    """Return wrapper prefix, path, and trailing title/fragment payload."""
    leading = raw[: len(raw) - len(raw.lstrip())]
    trailing_space = raw[len(raw.rstrip()) :]
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        end = value.index(">")
        return leading + "<", value[1:end], ">" + value[end + 1 :] + trailing_space
    match = re.match(r"^(\S+)(.*)$", value)
    if not match:
        return leading, value, trailing_space
    return leading, match.group(1), match.group(2) + trailing_space


def rewrite_markdown_links(text: str, old_source: str, new_source: str) -> str:
    old_parent = PurePosixPath(old_source).parent.as_posix()
    new_parent = PurePosixPath(new_source).parent.as_posix()

    def replace(match: re.Match[str]) -> str:
        raw = match.group("target")
        before, target, after = split_markdown_target(raw)
        if not target or target.startswith(("#", "/", "http://", "https://", "mailto:", "data:")):
            return match.group(0)

        path_part = target
        fragment = ""
        for separator in ("#", "?"):
            if separator in path_part:
                index = path_part.index(separator)
                fragment = path_part[index:]
                path_part = path_part[:index]
                break
        if not path_part:
            return match.group(0)

        resolved_old = normalize(posixpath.join(old_parent, path_part))
        if resolved_old.startswith("../"):
            return match.group(0)
        resolved_new = MOVES.get(resolved_old, resolved_old)
        rewritten = posixpath.relpath(resolved_new, start=new_parent)
        if path_part.startswith("./") and not rewritten.startswith("."):
            rewritten = f"./{rewritten}"
        return f"{match.group('prefix')}{before}{rewritten}{fragment}{after}{match.group('suffix')}"

    return MARKDOWN_TARGET.sub(replace, text)


def iter_text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        files.append(path)
    return files


def main() -> None:
    existing_sources = [ROOT / old for old in MOVES if (ROOT / old).exists()]
    if not existing_sources:
        print("documentation migration already applied")
        return

    conflicts = [new for new in MOVES.values() if (ROOT / new).exists()]
    if conflicts:
        raise SystemExit("destination already exists:\n" + "\n".join(conflicts))

    original_files = iter_text_files()
    rewritten: dict[str, str] = {}
    for source_path in original_files:
        old_relative = source_path.relative_to(ROOT).as_posix()
        new_relative = MOVES.get(old_relative, old_relative)
        try:
            text = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if source_path.suffix.lower() == ".md":
            text = rewrite_markdown_links(text, old_relative, new_relative)
        for old, new in sorted(MOVES.items(), key=lambda item: len(item[0]), reverse=True):
            text = text.replace(old, new)
        rewritten[new_relative] = text

    for relative, text in rewritten.items():
        destination = ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")

    for old, new in MOVES.items():
        old_path = ROOT / old
        if old_path.exists() and old != new:
            old_path.unlink()

    for directory in (ROOT / "docs/adr", ROOT / "docs/architecture"):
        if directory.exists():
            try:
                directory.rmdir()
            except OSError:
                pass

    print(f"moved {len(existing_sources)} documentation files")


if __name__ == "__main__":
    main()
