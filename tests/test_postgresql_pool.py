from __future__ import annotations

from app.infra.db import pool as postgresql_pool


def test_pool_checks_connection_before_checkout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakePool:
        @staticmethod
        def check_connection(_connection) -> None:
            return None

        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def close(self) -> None:
            return None

    postgresql_pool.close_pools()
    monkeypatch.setattr(
        postgresql_pool,
        "require_psycopg_pool",
        lambda: (FakePool, object()),
    )

    try:
        postgresql_pool.get_pool("postgresql://pool-check.invalid/test")
        assert captured["check"] is FakePool.check_connection
        assert captured["open"] is True
    finally:
        postgresql_pool.close_pools()
