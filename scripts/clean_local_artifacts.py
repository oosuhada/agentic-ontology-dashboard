#!/usr/bin/env python3
"""Remove local caches and generated development artifacts without touching source data."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DIRECTORY_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

EXPLICIT_DIRECTORIES = {
    ROOT / "systems" / "frontend" / "dist",
    ROOT / "systems" / "frontend" / "test-results",
    ROOT / "systems" / "frontend" / "playwright-report",
    ROOT / "systems" / "frontend" / "coverage",
    ROOT / "htmlcov",
}


RUNTIME_CACHE_DIRECTORIES = {
    ROOT / "systems" / "frontend" / ".vite",
    ROOT / "systems" / "frontend" / "node_modules" / ".vite",
}

FILE_NAMES = {".DS_Store", ".coverage", "coverage.xml", "junit.xml"}
FILE_SUFFIXES = {".pyc", ".pyo"}


def candidates(*, include_runtime_caches: bool = False) -> list[Path]:
    paths: set[Path] = set(EXPLICIT_DIRECTORIES)
    if include_runtime_caches:
        paths.update(RUNTIME_CACHE_DIRECTORIES)
    for current, directory_names, file_names in os.walk(ROOT):
        current_path = Path(current)
        directory_names[:] = [
            name
            for name in directory_names
            if name not in {".git", ".venv", "venv", "node_modules"}
        ]
        for name in list(directory_names):
            if name in DIRECTORY_NAMES:
                paths.add(current_path / name)
                directory_names.remove(name)
        for name in file_names:
            path = current_path / name
            if name in FILE_NAMES or path.suffix in FILE_SUFFIXES:
                paths.add(path)
    return sorted(paths, key=lambda item: (len(item.parts), str(item)), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print targets without deleting them.")
    parser.add_argument(
        "--include-runtime-caches",
        action="store_true",
        help="Also remove Vite dependency caches. Stop and restart the frontend server after using this option.",
    )
    args = parser.parse_args()

    removed = 0
    for path in candidates(include_runtime_caches=args.include_runtime_caches):
        if not path.exists():
            continue
        print(path.relative_to(ROOT))
        removed += 1
        if args.dry_run:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    action = "would remove" if args.dry_run else "removed"
    print(f"{action} {removed} local artifact(s)")
    if args.include_runtime_caches:
        print("Vite runtime caches were included; restart the frontend server before opening the app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
