#!/usr/bin/env python3
"""Validate the documentation registry, entrypoints, and local links."""

from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REGISTRY = DOCS / "document-registry.json"
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def local_target(document: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
    if not target or target.startswith(("#", "http://", "https://", "mailto:", "data:")):
        return None
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not target:
        return None
    return (document.parent / target).resolve()


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []

    for relative in registry["required_directories"]:
        path = DOCS / relative
        if not path.is_dir():
            errors.append(f"missing documentation directory: docs/{relative}")

    for relative in registry["required_entrypoints"]:
        path = DOCS / relative
        if not path.is_file():
            errors.append(f"missing documentation entrypoint: docs/{relative}")

    allowed = set(registry["canonical_root_files"]) | set(registry["compatibility_root_files"])
    globs = registry["compatibility_root_globs"]
    root_markdown = sorted(path.name for path in DOCS.glob("*.md"))
    for name in root_markdown:
        if name in allowed or any(fnmatch.fnmatch(name, pattern) for pattern in globs):
            continue
        errors.append(f"unregistered root documentation file: docs/{name}")

    compatibility_count = sum(
        1 for name in root_markdown
        if name in registry["compatibility_root_files"] or any(fnmatch.fnmatch(name, pattern) for pattern in globs)
    )
    if compatibility_count:
        warnings.append(
            f"{compatibility_count} root Markdown files remain as compatibility paths; add new documents only to numbered folders"
        )

    checked_links = 0
    for document in sorted(DOCS.rglob("*.md")):
        content = document.read_text(encoding="utf-8")
        for raw_target in LINK_PATTERN.findall(content):
            target = local_target(document, raw_target)
            if target is None:
                continue
            checked_links += 1
            if not target.exists():
                errors.append(
                    f"broken local link: {document.relative_to(ROOT)} -> {raw_target}"
                )

    print(f"documentation directories: {len(registry['required_directories'])}")
    print(f"required entrypoints: {len(registry['required_entrypoints'])}")
    print(f"root Markdown files: {len(root_markdown)}")
    print(f"checked local links: {checked_links}")
    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1
    print("documentation structure: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
