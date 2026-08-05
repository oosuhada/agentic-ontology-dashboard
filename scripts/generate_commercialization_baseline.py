#!/usr/bin/env python3
"""Generate the Phase 17 commercialization truth-source artifacts.

The report intentionally separates source-code readiness from capabilities that
require credentials or managed infrastructure.  It only reads the checkout and
does not mutate application state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROUTES = (
    ("v1", "/app/projects/manufacturing-demo-project", "matchProjectDashboardPath", "Ontology Dashboard"),
    ("v2", "/app/projects/manufacturing-demo-project/blueprint", "matchBlueprintProjectPath", "Blueprint V1"),
    ("v3", "/app/projects/manufacturing-demo-project/blueprint-v2", "matchBlueprintV2ProjectPath", "Blueprint V2"),
    ("v4", "/app/projects/manufacturing-demo-project/blueprint-v4", "matchBlueprintV4ProjectPath", "Commercial V4"),
)

CAPABILITY_PHASE = {
    "compose": 22,
    "postgresql": 20,
    "redis": 23,
    "neo4j": 28,
    "project3": 29,
    "oidc": 21,
    "connectors": 26,
    "object-storage": 24,
    "observability": 25,
}

CAPABILITY_OWNER = {
    "compose": "deployment",
    "postgresql": "identity-persistence",
    "redis": "distributed-runtime",
    "neo4j": "lineage-graph",
    "project3": "integrations",
    "oidc": "enterprise-identity",
    "connectors": "ingestion",
    "object-storage": "artifact-governance",
    "observability": "operations",
}

DOCUMENTS = (
    "README.md",
    "docs/00-team-onboarding/06-implementation-status.md",
    "docs/20-architecture/current-state/current-state.md",
    "docs/30-implementation/implementation-status.md",
    "docs/50-operations/release-gate-report.md",
    "docs/50-operations/production-environment-completion-runbook.md",
)

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "test-results",
    "playwright-report",
    "__pycache__",
}

PHASE17_OWNED_PATHS = {
    "scripts/generate_commercialization_baseline.py",
    "tests/test_commercialization_baseline.py",
    "docs/30-implementation/commercialization-baseline.md",
    "docs/50-operations/commercialization-readiness.json",
    "docs/50-operations/commercialization-phase17-verification.json",
}


def _run(root: Path, *command: str, check: bool = True) -> str:
    result = subprocess.run(
        list(command),
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed ({result.returncode}):\n{result.stdout}")
    return result.stdout.strip()


def _tracked_files(root: Path) -> list[Path]:
    output = _run(root, "git", "ls-files", "-z")
    return [root / item for item in output.split("\0") if item]


def _source_files(root: Path) -> list[Path]:
    allowed = {".py", ".ts", ".tsx", ".js", ".mjs", ".css", ".sql"}
    files: list[Path] = []
    for path in _tracked_files(root):
        if path.suffix not in allowed:
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        files.append(path)
    return files


def _line_count(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        try:
            total += len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    return total


def _package_lock_consistency(root: Path) -> dict[str, Any]:
    package = json.loads((root / "web/package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "web/package-lock.json").read_text(encoding="utf-8"))
    lock_root = lock.get("packages", {}).get("", {})
    mismatches: list[str] = []
    for section in ("dependencies", "devDependencies"):
        declared = package.get(section, {})
        locked = lock_root.get(section, {})
        for name, version in sorted(declared.items()):
            if locked.get(name) != version:
                mismatches.append(f"{section}:{name}:{version}!={locked.get(name)}")
        for name in sorted(set(locked) - set(declared)):
            mismatches.append(f"{section}:{name}:lock-only")
    return {
        "lockfile_version": lock.get("lockfileVersion"),
        "consistent": not mismatches,
        "mismatches": mismatches,
        "node_engine": package.get("engines", {}).get("node"),
        "dependencies": package.get("dependencies", {}),
        "dev_dependencies": package.get("devDependencies", {}),
    }


def _bundle_metrics(root: Path) -> dict[str, Any]:
    assets = root / "web/dist/assets"
    js = sorted(assets.glob("*.js")) if assets.is_dir() else []
    css = sorted(assets.glob("*.css")) if assets.is_dir() else []

    def entries(paths: list[Path]) -> list[dict[str, Any]]:
        return [
            {"name": path.name, "bytes": path.stat().st_size, "kib": round(path.stat().st_size / 1024, 2)}
            for path in paths
        ]

    js_entries = entries(js)
    css_entries = entries(css)
    return {
        "available": bool(js or css),
        "javascript_total_kib": round(sum(item["bytes"] for item in js_entries) / 1024, 2),
        "javascript_largest_kib": max((item["kib"] for item in js_entries), default=0),
        "css_total_kib": round(sum(item["bytes"] for item in css_entries) / 1024, 2),
        "javascript_chunks": js_entries,
        "css_chunks": css_entries,
    }


def _route_inventory(root: Path) -> list[dict[str, Any]]:
    routing = (root / "web/src/routing.ts").read_text(encoding="utf-8")
    app = (root / "web/src/App.tsx").read_text(encoding="utf-8")
    result = []
    for version, path, matcher, identity in ROUTES:
        matcher_present = matcher in routing
        app_present = matcher in app
        result.append(
            {
                "version": version.upper(),
                "path": path,
                "application_identity": identity,
                "registered": matcher_present and app_present,
                "redirected_to_v4": False,
                "state": "implemented" if matcher_present and app_present else "not_implemented",
            }
        )
    return result


def _document_registry(root: Path, branch: str, head: str) -> list[dict[str, Any]]:
    registry: list[dict[str, Any]] = []
    for relative in DOCUMENTS:
        path = root / relative
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        last_commit = _run(root, "git", "log", "-1", "--format=%H|%cI", "--", relative, check=False)
        commit, _, committed_at = last_commit.partition("|")
        branch_claim = None
        for pattern in (
            r"(?:Current branch baseline|기준 브랜치):\s*`?([^`\n]+)`?",
            r"(?:Current branch baseline|기준 브랜치):\s*([^\n]+)",
        ):
            match = re.search(pattern, text)
            if match:
                branch_claim = match.group(1).strip().strip("`")
                break
        reasons: list[str] = []
        if not path.exists():
            reasons.append("missing")
        if branch_claim and branch_claim not in {branch, "main"}:
            reasons.append(f"branch claim {branch_claim!r} differs from {branch!r}")
        if relative.endswith("current-state.md") and "api/factory_signal_board" in text:
            reasons.append("references removed compatibility namespace")
        if relative.endswith("current-state.md") and "SQLite Identity + Audit" in text:
            reasons.append("describes legacy SQLite composition as current")
        registry.append(
            {
                "path": relative,
                "basis_branch": branch_claim,
                "last_commit": commit or None,
                "last_committed_at": committed_at or None,
                "current_head": head,
                "status": "stale" if reasons else "current",
                "reasons": reasons,
                "canonical": relative == "docs/30-implementation/implementation-status.md",
            }
        )
    return registry


def _production_capabilities(root: Path, include_environment: bool) -> list[dict[str, Any]]:
    if not include_environment:
        return []
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(root / "api"), str(root / "ml/src")])
    result = subprocess.run(
        [sys.executable, "scripts/verify_production_environment.py"],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    payload = json.loads(result.stdout)
    capabilities = []
    for item in payload.get("capabilities", []):
        name = item["name"]
        capabilities.append(
            {
                "capability_id": name,
                "state": item["state"],
                "evidence": item["evidence"],
                "required_environment": item["action"],
                "owner": CAPABILITY_OWNER.get(name, "platform"),
                "blocking_phase": CAPABILITY_PHASE.get(name),
            }
        )
    return capabilities


def _hardcode_inventory(root: Path) -> dict[str, int]:
    patterns = {
        "manufacturing-demo-project": re.compile(r"manufacturing-demo-project"),
        "manufacturing-demo": re.compile(r"manufacturing-demo"),
        "gold-scenario": re.compile(r"GS-\d+"),
        "ai4i": re.compile(r"AI4I", re.IGNORECASE),
    }
    counts = {name: 0 for name in patterns}
    for path in _source_files(root):
        relative = path.relative_to(root)
        if "tests" in relative.parts or "e2e" in relative.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, pattern in patterns.items():
            counts[name] += len(pattern.findall(text))
    return counts


def _preserved_external_changes(root: Path) -> list[str]:
    output = _run(root, "git", "status", "--porcelain=v1", "-z")
    paths: list[str] = []
    entries = [entry for entry in output.split("\0") if entry]
    index = 0
    while index < len(entries):
        entry = entries[index]
        status = entry[:2]
        path = entry[3:]
        if status.startswith(("R", "C")) and index + 1 < len(entries):
            index += 1
            path = entries[index]
        if path not in PHASE17_OWNED_PATHS:
            paths.append(path)
        index += 1
    return sorted(set(paths))


def build_baseline(root: Path, *, include_environment: bool = True) -> dict[str, Any]:
    root = root.resolve()
    head = _run(root, "git", "rev-parse", "HEAD")
    branch = _run(root, "git", "branch", "--show-current")
    upstream = _run(root, "git", "rev-parse", "--abbrev-ref", "@{upstream}", check=False)
    ahead_behind_raw = _run(root, "git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}", check=False)
    ahead, behind = (ahead_behind_raw.split() + ["unknown", "unknown"])[:2]
    commit_time = _run(root, "git", "show", "-s", "--format=%cI", "HEAD")
    tracked = _tracked_files(root)
    source = _source_files(root)
    largest = sorted(
        (
            {"path": str(path.relative_to(root)), "bytes": path.stat().st_size}
            for path in tracked
            if path.exists()
        ),
        key=lambda item: item["bytes"],
        reverse=True,
    )[:15]
    migrations = sorted(
        str(path.relative_to(root))
        for path in (root / "api/migrations").rglob("*.sql")
    )
    backend_tests = sorted(str(path.relative_to(root)) for path in (root / "tests").glob("test_*.py"))
    frontend_unit = sorted(str(path.relative_to(root)) for path in (root / "web/src").rglob("*.test.*"))
    frontend_e2e = sorted(str(path.relative_to(root)) for path in (root / "web/e2e").glob("*.spec.ts"))
    legacy_files = sorted(str(path.relative_to(root)) for path in (root / "api/factory_signal_board").rglob("*.py")) if (root / "api/factory_signal_board").exists() else []
    routes = _route_inventory(root)
    capabilities = _production_capabilities(root, include_environment)
    verification_path = root / "docs/50-operations/commercialization-phase17-verification.json"
    verification = (
        json.loads(verification_path.read_text(encoding="utf-8"))
        if verification_path.exists()
        else None
    )
    return {
        "schema_version": "commercialization-baseline/v1",
        "generated_from": {
            "branch": branch,
            "head": head,
            "commit_time": commit_time,
            "upstream": upstream or None,
            "ahead": ahead,
            "behind": behind,
            "preserved_external_changes": _preserved_external_changes(root),
        },
        "readiness_definition": {
            "feature": "local contract and user workflow exist",
            "demo": "deterministic fixtures and local E2E exist",
            "pilot": "tenant isolation, recovery and operator workflow are verified",
            "production": "managed dependencies and operational drills have evidence",
            "security": "identity, policy, audit and supply-chain controls have evidence",
            "performance": "measured budgets and representative load evidence exist",
        },
        "version_baseline": routes,
        "inventory": {
            "tracked_files": len(tracked),
            "source_files": len(source),
            "source_lines": _line_count(source),
            "backend_test_files": backend_tests,
            "frontend_unit_test_files": frontend_unit,
            "frontend_e2e_files": frontend_e2e,
            "postgresql_migrations": [item for item in migrations if "/postgresql/" in item],
            "sqlite_migrations": [item for item in migrations if "/sqlite/" in item],
            "legacy_namespace_files": legacy_files,
            "largest_tracked_files": largest,
            "hardcoded_identifier_occurrences": _hardcode_inventory(root),
        },
        "package_lock": _package_lock_consistency(root),
        "bundle": _bundle_metrics(root),
        "verification_snapshot": verification,
        "document_freshness": _document_registry(root, branch, head),
        "production_capabilities": capabilities,
        "architecture_claims": [
            {
                "claim": "api/factory_signal_board remains a runtime namespace",
                "state": "invalidated" if not legacy_files else "current",
                "evidence": f"{len(legacy_files)} tracked Python files",
            },
            {
                "claim": "V4 commercial route exists",
                "state": "current" if any(item["version"] == "V4" and item["registered"] for item in routes) else "invalidated",
                "evidence": next(item for item in routes if item["version"] == "V4"),
            },
            {
                "claim": "tests passing implies production readiness",
                "state": "invalidated",
                "evidence": "production capabilities are evaluated independently",
            },
        ],
        "roadmap_freeze": {
            "phases": list(range(18, 38)),
            "v4_promotion_policy": "explicit release approval only; never automatic",
            "duplicate_implementation_prohibited": [
                "V3 source copied into a fourth monolith",
                "screen-specific Action or Function contracts",
                "unscoped browser storage and query keys",
                "raw SQL/Cypher/code execution from user or LLM text",
            ],
        },
        "interpretation": [
            "Passing tests do not imply that production capabilities are ready.",
            "Missing credentials and missing implementation are different states.",
            "The number of demo screens is not a platform-maturity metric.",
            "Palantir-like visual styling and reusable platform primitives are evaluated separately.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated = payload["generated_from"]
    route_rows = "\n".join(
        f"| {item['version']} | `{item['path']}` | {item['application_identity']} | {item['state']} |"
        for item in payload["version_baseline"]
    )
    capability_rows = "\n".join(
        f"| {item['capability_id']} | {item['state']} | {item['blocking_phase']} | {str(item['evidence']).replace(chr(10), ' ')} |"
        for item in payload["production_capabilities"]
    ) or "| environment probe omitted | not_measured | - | rerun generator without `--no-environment` |"
    stale_rows = "\n".join(
        f"| `{item['path']}` | {item['status']} | {'; '.join(item['reasons']) or 'current checkout evidence'} |"
        for item in payload["document_freshness"]
    )
    bundle = payload["bundle"]
    inventory = payload["inventory"]
    verification = payload.get("verification_snapshot") or {}
    backend = verification.get("backend", {})
    frontend = verification.get("frontend", {})
    verification_rows = "\n".join(
        [
            f"| Backend pytest | {backend.get('state', 'not_measured')} | {backend.get('passed', '-')} passed / {backend.get('warnings', '-')} warnings |",
            f"| Frontend Vitest | {frontend.get('unit_state', 'not_measured')} | {frontend.get('unit_tests', '-')} tests |",
            f"| TypeScript | {frontend.get('typecheck_state', 'not_measured')} | `npm run lint` |",
            f"| Production build | {frontend.get('build_state', 'not_measured')} | initial {frontend.get('initial_javascript_kib', '-')} KiB / {frontend.get('initial_budget_kib', '-')} KiB |",
            f"| Documentation | {verification.get('docs', {}).get('state', 'not_measured')} | structure and local-link check |",
            f"| Deterministic generator | {verification.get('generator', {}).get('state', 'not_measured')} | rerun comparison |",
        ]
    )
    return f"""# Commercialization Baseline and Roadmap Freeze

- Schema: `{payload['schema_version']}`
- Branch: `{generated['branch']}`
- HEAD: `{generated['head']}`
- Commit time: `{generated['commit_time']}`
- Upstream: `{generated['upstream']}` (ahead {generated['ahead']}, behind {generated['behind']})
- Canonical current-state document: `docs/30-implementation/implementation-status.md`

## Version baseline

| Version | Route | Application identity | State |
|---|---|---|---|
{route_rows}

V1, V2 and V3 are immutable comparison/regression surfaces for this track. V4 promotion to the
default Project route requires an explicit later release decision and is never automatic.

## Measured checkout inventory

| Metric | Value |
|---|---:|
| Tracked files | {inventory['tracked_files']} |
| Source files | {inventory['source_files']} |
| Source lines | {inventory['source_lines']} |
| Backend test files | {len(inventory['backend_test_files'])} |
| Frontend unit test files | {len(inventory['frontend_unit_test_files'])} |
| Frontend E2E specs | {len(inventory['frontend_e2e_files'])} |
| PostgreSQL migrations | {len(inventory['postgresql_migrations'])} |
| SQLite migrations | {len(inventory['sqlite_migrations'])} |
| Legacy namespace files | {len(inventory['legacy_namespace_files'])} |
| JavaScript total (built assets) | {bundle['javascript_total_kib']} KiB |
| Largest JavaScript chunk | {bundle['javascript_largest_kib']} KiB |
| CSS total (built assets) | {bundle['css_total_kib']} KiB |

Package-lock consistency: **{'PASS' if payload['package_lock']['consistent'] else 'FAIL'}**.

## Verification snapshot

| Gate | State | Evidence |
|---|---|---|
{verification_rows}

## Production capability snapshot

| Capability | State | Blocking Phase | Evidence |
|---|---|---:|---|
{capability_rows}

Passing local tests does not make a blocked external capability production-ready. A missing
credential, a missing managed service, and missing code are reported independently.

## Document freshness registry

| Document | State | Evidence |
|---|---|---|
{stale_rows}

Historical documents remain available, but stale claims are not authoritative. The machine-readable
truth source is `docs/50-operations/commercialization-readiness.json`.

## Readiness interpretation

- Feature/demo/pilot/production/security/performance readiness are separate dimensions.
- Demo screen count is not a platform-maturity metric.
- Palantir-like visual styling is not the same as reusable Ontology, Action, Function, Branching,
  Lineage, Marking and Application runtime primitives.
- V4 starts as `not_implemented`; Phase 18 creates its independent composition while preserving
  V1 through V3.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument(
        "--json-output",
        default="docs/50-operations/commercialization-readiness.json",
    )
    parser.add_argument(
        "--markdown-output",
        default="docs/30-implementation/commercialization-baseline.md",
    )
    parser.add_argument("--no-environment", action="store_true")
    parser.add_argument("--check", action="store_true", help="fail when generated files differ")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    payload = build_baseline(root, include_environment=not args.no_environment)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown_text = render_markdown(payload)
    destinations = {
        root / args.json_output: json_text,
        root / args.markdown_output: markdown_text,
    }
    if args.check:
        changed = [str(path.relative_to(root)) for path, content in destinations.items() if not path.exists() or path.read_text(encoding="utf-8") != content]
        if changed:
            print(json.dumps({"pass": False, "changed": changed}, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps({"pass": True, "changed": []}, ensure_ascii=False, indent=2))
        return 0
    for path, content in destinations.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(json.dumps({"pass": True, "outputs": [str(path.relative_to(root)) for path in destinations]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
