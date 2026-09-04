#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from argon2 import PasswordHasher

from app.identity import DEMO_ACCOUNTS, IdentityService
from app.infra.db.identity_repository import IdentityRepository
from app.infra.db.settings import database_location

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

    password_hasher = PasswordHasher(
        time_cost=2,
        memory_cost=19456,
        parallelism=1,
        hash_len=32,
        salt_len=16,
    )
    service = IdentityService(
        IdentityRepository(args.database, password_hasher=password_hasher),
        app_env=app_env,
        seed_demo=True,
        rate_limit_namespace=f"identity:{args.database}",
    )
    users = service.repository.list_users()
    seeded_emails = {account["email"] for account in DEMO_ACCOUNTS}
    available = sorted(user["email"] for user in users if user["email"] in seeded_emails)
    print(f"Demo accounts available: {len(available)}/{len(DEMO_ACCOUNTS)}")
    for email in available:
        print(f"- {email}")


if __name__ == "__main__":
    main()
