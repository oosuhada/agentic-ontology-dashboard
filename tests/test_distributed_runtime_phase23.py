from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ontology_dashboard.distributed_runtime import (
    DistributedRateLimiter,
    DurableJobRepository,
    DurableWorker,
    InMemoryAtomicWindowStore,
    QueueSaturated,
    QueueUnavailable,
    distributed_runtime_readiness,
)
from ontology_dashboard.migrations import migrate
from ontology_dashboard.projects import ProjectRepository
from ontology_dashboard.security import RateLimitExceeded


def repository(tmp_path: Path, *, max_queued: int = 100) -> DurableJobRepository:
    database = tmp_path / "phase23.db"
    migrate(str(database))
    ProjectRepository(database)
    return DurableJobRepository(database, max_queued_per_project=max_queued)


def enqueue(repo: DurableJobRepository, key: str, *, max_attempts: int = 3):
    return repo.enqueue(
        organization_id="org-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        job_type="analysis",
        idempotency_key=key,
        payload={"run_id": key},
        created_by="user-manager",
        max_attempts=max_attempts,
    )


def claim(repo: DurableJobRepository, worker: str = "worker-a"):
    return repo.claim(
        organization_id="org-demo",
        project_id="manufacturing-demo-project",
        worker_id=worker,
        worker_version="phase23",
        runtime_checksum="checksum-v1",
        job_types=("analysis",),
        lease_seconds=5,
    )


def test_enqueue_is_idempotent_and_project_quota_is_atomic(tmp_path: Path) -> None:
    repo = repository(tmp_path, max_queued=1)
    first, created = enqueue(repo, "same-key")
    replay, replay_created = enqueue(repo, "same-key")
    assert created is True
    assert replay_created is False
    assert replay.id == first.id
    with pytest.raises(QueueSaturated) as saturated:
        enqueue(repo, "second-key")
    assert saturated.value.depth == 1
    assert saturated.value.limit == 1


def test_two_workers_do_not_claim_the_same_job_and_delivery_is_idempotent(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    enqueue(repo, "exclusive-claim")
    first = claim(repo, "worker-a")
    second = claim(repo, "worker-b")
    assert first is not None
    assert second is None
    completed = repo.complete(first, result={"delivery_id": "stable-result"})
    assert completed.state == "succeeded"
    assert completed.result == {"delivery_id": "stable-result"}
    assert claim(repo, "worker-b") is None


def test_crashed_worker_lease_is_recovered_with_same_job_identity(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    original, _ = enqueue(repo, "crash-recovery")
    running = claim(repo, "worker-crashed")
    assert running and running.id == original.id
    database = Path(repo.database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE durable_jobs SET lease_expires_at=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), original.id),
        )
    recovered = claim(repo, "worker-replacement")
    assert recovered is not None
    assert recovered.id == original.id
    assert recovered.attempt_count == 2
    assert recovered.lease_owner == "worker-replacement"
    assert [item.event_type for item in repo.events_after(
        organization_id="org-demo",
        project_id="manufacturing-demo-project",
    )] == ["job.queued", "job.claimed", "job.retry", "job.claimed"]


def test_poison_message_moves_to_dead_letter_and_replay_is_audited(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    job, _ = enqueue(repo, "poison", max_attempts=1)
    running = claim(repo)
    dead = repo.fail(running, failure_class="transient", error="upstream timeout")
    assert dead.state == "dead_letter"
    replayed = repo.replay(
        organization_id="org-demo",
        project_id="manufacturing-demo-project",
        job_id=job.id,
        actor_user_id="user-admin",
    )
    assert replayed.state == "queued"
    assert replayed.attempt_count == 0
    events = repo.events_after(
        organization_id="org-demo",
        project_id="manufacturing-demo-project",
        cursor=0,
        limit=20,
    )
    assert events[-1].event_type == "job.replayed"
    assert events[-1].payload["actor_user_id"] == "user-admin"
    assert repo.events_after(
        organization_id="org-demo",
        project_id="manufacturing-demo-project",
        cursor=events[-1].cursor,
    ) == ()


def test_cancellation_and_worker_heartbeat_are_operationally_visible(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    queued, _ = enqueue(repo, "cancel-before-run")
    cancelled = repo.cancel(
        organization_id="org-demo",
        project_id="manufacturing-demo-project",
        job_id=queued.id,
        reason="operator cancelled duplicate request",
    )
    assert cancelled.state == "cancelled"
    repo.record_worker_heartbeat(
        worker_id="worker-a",
        worker_type="analysis",
        worker_version="phase23",
        runtime_checksum="checksum",
        state="ready",
        queue_names=("analysis",),
        organization_id="org-demo",
        project_id="manufacturing-demo-project",
        metrics={"processed": 3},
    )
    status = repo.worker_status()
    assert status[0]["worker_id"] == "worker-a"
    assert status[0]["queue_names"] == ["analysis"]
    assert status[0]["metrics"] == {"processed": 3}
    assert status[0]["stale"] is False


def test_durable_worker_classifies_missing_handler_without_losing_job(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    enqueue(repo, "missing-handler", max_attempts=1)
    worker = DurableWorker(
        repo,
        worker_id="worker-no-handler",
        worker_version="phase23",
        runtime_checksum="checksum",
        job_types=("analysis",),
        handlers={},
    )
    result = worker.process_once(
        organization_id="org-demo",
        project_id="manufacturing-demo-project",
    )
    assert result is not None
    assert result.state == "dead_letter"
    assert result.failure_class == "permanent"


def test_shared_atomic_rate_limit_is_consistent_across_two_api_instances() -> None:
    now = [100.0]
    store = InMemoryAtomicWindowStore(clock=lambda: now[0])
    api_a = DistributedRateLimiter(store, namespace="ontology")
    api_b = DistributedRateLimiter(store, namespace="ontology")
    for index in range(12):
        limiter = api_a if index % 2 == 0 else api_b
        assert limiter.check(policy="login", subject="198.51.100.1|user@example.com") is True
    with pytest.raises(RateLimitExceeded) as exceeded:
        api_b.check(policy="login", subject="198.51.100.1|user@example.com")
    assert exceeded.value.retry_after == 60
    now[0] += 61
    assert api_a.check(policy="login", subject="198.51.100.1|user@example.com") is True


def test_redis_outage_fail_mode_is_explicit_per_endpoint_class() -> None:
    store = InMemoryAtomicWindowStore()
    store.available = False
    limiter = DistributedRateLimiter(store, namespace="ontology")
    assert limiter.check(policy="planner", subject="org|user") is False
    with pytest.raises(QueueUnavailable):
        limiter.check(policy="action", subject="org|user")


def test_runtime_readiness_separates_local_queue_from_managed_redis(monkeypatch, tmp_path: Path) -> None:
    repo = repository(tmp_path)
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_REDIS_URL", raising=False)
    readiness = distributed_runtime_readiness(
        repo.database,
        organization_id="org-demo",
        project_id="manufacturing-demo-project",
    )
    assert readiness.state == "degraded"
    assert readiness.queue_backend == "sqlite"
    assert readiness.redis_state == "not_configured"
    assert readiness.rate_limit_policies["action"]["fail_mode"] == "closed"
    assert readiness.rate_limit_policies["planner"]["fail_mode"] == "open"
