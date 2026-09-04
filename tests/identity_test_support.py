"""Test-only composition helpers for the canonical Identity service."""

from __future__ import annotations

from pathlib import Path

from argon2 import PasswordHasher

from app.identity import IdentityService
from app.infra.db.identity_repository import IdentityRepository


def build_identity_service(
    database_path: str | Path,
    *,
    app_env: str | None = None,
    seed_demo: bool | None = None,
) -> IdentityService:
    password_hasher = PasswordHasher(
        time_cost=2,
        memory_cost=19456,
        parallelism=1,
        hash_len=32,
        salt_len=16,
    )
    repository = IdentityRepository(database_path, password_hasher=password_hasher)
    return IdentityService(
        repository,
        app_env=app_env,
        seed_demo=seed_demo,
        rate_limit_namespace=f"identity:{database_path}",
    )


__all__ = ["build_identity_service"]
