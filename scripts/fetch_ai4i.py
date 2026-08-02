#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path

URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/00601/ai4i2020.csv"
EXPECTED_SHA256 = "59db4f1d9c34c58136d89e5a006ec190dcea19e9dbea74f6b3b0c6f22a44d183"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and verify the UCI AI4I 2020 CSV")
    parser.add_argument("--output", default="data/raw/ai4i2020.csv")
    parser.add_argument(
        "--local-source",
        help="Optional already-downloaded compatible CSV. It is copied only after checksum verification.",
    )
    args = parser.parse_args()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)

    if args.local_source:
        shutil.copyfile(args.local_source, target)
    else:
        with urllib.request.urlopen(URL, timeout=60) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output)

    actual = sha256(target)
    if actual != EXPECTED_SHA256:
        target.unlink(missing_ok=True)
        raise SystemExit(f"checksum mismatch: expected {EXPECTED_SHA256}, got {actual}")
    print(f"AI4I_READY path={target} sha256={actual}")


if __name__ == "__main__":
    main()
