"""Cross-store projection coordinator with explicit store ports and idempotent batches."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .dataset_repository import DatasetRepositoryPort
from .dataset_schema import CanonicalObjectEnvelope, ProjectionBatch, StoreKind


class ProjectionPort(Protocol):
    store_kind: StoreKind

    def project(self, batch: ProjectionBatch) -> int:
        """Project a version and return the number of accepted canonical objects."""


@dataclass
class InMemoryProjectionPort:
    store_kind: StoreKind
    objects: dict[str, CanonicalObjectEnvelope] = field(default_factory=dict)
    calls: int = 0

    def project(self, batch: ProjectionBatch) -> int:
        self.calls += 1
        for item in batch.objects:
            self.objects[item.object_id] = item
        return len(batch.objects)


class DatasetProjectionCoordinator:
    def __init__(
        self,
        repository: DatasetRepositoryPort,
        ports: dict[StoreKind, ProjectionPort],
    ) -> None:
        self.repository = repository
        self.ports = ports

    def run(
        self,
        *,
        batch: ProjectionBatch,
        organization_id: str,
        project_id: str,
    ) -> dict[StoreKind, int]:
        projections = self.repository.list_projections(
            organization_id=organization_id,
            project_id=project_id,
            dataset_id=batch.dataset.id,
            version_id=batch.version.id,
        )
        results: dict[StoreKind, int] = {}
        for projection in projections:
            store_kind = projection["store_kind"]
            if store_kind not in self.ports:
                continue
            if projection["status"] == "ready":
                results[store_kind] = int(projection["record_count"])
                continue
            claimed = self.repository.claim_projection(
                organization_id=organization_id,
                project_id=project_id,
                projection_id=projection["id"],
            )
            try:
                count = self.ports[store_kind].project(batch)
                self._validate_identity_parity(
                    batch=batch,
                    projected_count=count,
                    store_kind=store_kind,
                )
                self.repository.complete_projection(
                    organization_id=organization_id,
                    project_id=project_id,
                    projection_id=claimed["id"],
                    record_count=count,
                )
                results[store_kind] = count
            except Exception as error:
                self.repository.fail_projection(
                    organization_id=organization_id,
                    project_id=project_id,
                    projection_id=claimed["id"],
                    error_message=f"{type(error).__name__}: {error}",
                )
                raise
        return results

    @staticmethod
    def _validate_identity_parity(
        *,
        batch: ProjectionBatch,
        projected_count: int,
        store_kind: StoreKind,
    ) -> None:
        if projected_count != len(batch.objects):
            raise RuntimeError(
                f"{store_kind} projection accepted {projected_count} of {len(batch.objects)} objects"
            )
        identities = {item.object_id for item in batch.objects}
        if len(identities) != len(batch.objects):
            raise RuntimeError("canonical object identities are not unique inside the dataset version")
        for item in batch.objects:
            if item.dataset_version_id != batch.version.id:
                raise RuntimeError("dataset version identity drift detected")
            if item.project_id != batch.dataset.project_id:
                raise RuntimeError("project identity drift detected")


__all__ = [
    "DatasetProjectionCoordinator",
    "InMemoryProjectionPort",
    "ProjectionPort",
]
