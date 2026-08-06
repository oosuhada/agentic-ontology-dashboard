#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from ontology_dashboard.identity import DEMO_ACCOUNTS, IdentityService
from ontology_dashboard.settings import database_location

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Ontology Dashboard development demo accounts")
    parser.add_argument(
        "--database",
        default=database_location(ROOT),
    )
    args = parser.parse_args()

    app_env = os.getenv("APP_ENV", "development").lower()
    if app_env == "production":
        raise SystemExit("Refusing to seed demo accounts when APP_ENV=production")

    IdentityService(args.database, app_env=app_env, seed_demo=True)
    print(f"Demo accounts available: {len(DEMO_ACCOUNTS)}")
    for account in DEMO_ACCOUNTS:
        print(f"- {account['email']}")


if __name__ == "__main__":
    main()
