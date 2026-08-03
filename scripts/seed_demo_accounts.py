#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from factory_signal_board.identity import DEMO_ACCOUNTS, IdentityService

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Ontology Dashboard development demo accounts")
    parser.add_argument(
        "--database",
        default=os.getenv("FACTORY_SIGNAL_DB", str(ROOT / "data" / "local" / "factory_signal_board.db")),
    )
    args = parser.parse_args()

    app_env = os.getenv("APP_ENV", "development").lower()
    if app_env == "production":
        raise SystemExit("Refusing to seed demo accounts when APP_ENV=production")

    service = IdentityService(args.database, app_env=app_env, seed_demo=True)
    users = service.repository.list_users()
    seeded_emails = {account["email"] for account in DEMO_ACCOUNTS}
    available = sorted(user["email"] for user in users if user["email"] in seeded_emails)
    print(f"Demo accounts available: {len(available)}/{len(DEMO_ACCOUNTS)}")
    for email in available:
        print(f"- {email}")


if __name__ == "__main__":
    main()
