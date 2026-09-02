"""Lifecycle owner for the Source Data Producer runtime."""

from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.protocol.opcua import OpcUaCollector, OpcUaMapping, OpcUaPublisher
from app.runtime.overlay import RuntimeOverlayCoordinator
from app.runtime.state import RunState
from app.simulation.producer import SimulationProducer
from app.storage.canonical_writer import CanonicalWriter
from app.storage.manifest import sha256, write_manifest
from app.storage.protocol_writer import ProtocolRecordWriter
from app.storage.source_writer import SourceRecordWriter
from physics_engine import GENERATOR_VERSION


RUN_MANIFEST_SCHEMA_VERSION = "1"
MAX_RUNTIME_OVERLAY_FAST_FORWARD_ROWS = 10_000


class _RunContext:
    def __init__(
        self,
        *,
        run_id: str,
        simulation_session_id: str,
        output_root: Path,
        mapping_path: Path,
        opcua_endpoint: str,
        start_at: datetime,
        end_at: datetime,
        interval_minutes: int,
        product_cycle_minutes: int,
        seed: int,
        rate_profile: str,
        speed: float,
        continuous: bool,
        publish_opcua: bool,
        maintenance_event_file: Path | None,
        runtime_overlay_fast_forward_rows: int,
    ) -> None:
        self.run_id = run_id
        self.simulation_session_id = simulation_session_id
        self.output_root = output_root
        self.run_dir = output_root / "runs" / run_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.manifest_path = self.run_dir / "run_manifest.json"
        self.interval_minutes = interval_minutes
        self.seed = seed
        self.rate_profile = rate_profile
        self.speed = speed
        self.continuous = continuous
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.thread: threading.Thread | None = None
        self.producer = SimulationProducer(
            run_id=run_id,
            start_at=start_at,
            end_at=end_at,
            interval_minutes=interval_minutes,
            product_cycle_minutes=product_cycle_minutes,
            seed=seed,
            rate_profile=rate_profile,
        )
        self.maintenance_event_file = maintenance_event_file
        self.runtime_overlay_fast_forward_rows = runtime_overlay_fast_forward_rows
        self.overlay = RuntimeOverlayCoordinator(
            canonical_producer=self.producer,
            simulation_session_id=simulation_session_id,
            output_root=output_root,
        )
        self.overlay.recover_pending_available_events()
        self.source_writer = SourceRecordWriter(self.run_dir / "source" / "sensor_records.jsonl")
        self.protocol_writer = ProtocolRecordWriter(self.run_dir / "protocol")
        self.canonical_writer = CanonicalWriter(self.run_dir / "canonical")
        self.canonical_writer.write_static_contract(self.producer.assets, self.producer.relations)
        self.mapping = OpcUaMapping.load(mapping_path)
        self.publisher: OpcUaPublisher | None = None
        now = datetime.now(tz=timezone.utc)
        self.state = RunState(
            run_id=run_id,
            status="running",
            started_at=now,
            current_observed_at=start_at,
            source_kind="simulation",
            simulation_session_id=simulation_session_id,
        )
        self._closed = False
        if publish_opcua:
            try:
                self.publisher = OpcUaPublisher(endpoint=opcua_endpoint, mapping=self.mapping)
                self.publisher.start()
            except Exception as exc:
                self.publisher = None
                self._record_failure("protocol_start", exc)
        self._write_manifest()

    def process_tick(self) -> RunState:
        with self.lock:
            if self._closed or self.state.status not in {"running", "partial_failure"}:
                raise RuntimeError(f"run {self.run_id} is not active")
            observed_at = self.state.current_observed_at
            if observed_at >= self.producer.end_at:
                self.finish("completed")
                return self.state
            try:
                self.overlay.activate_due_started_events(observed_at)
                if self.maintenance_event_file is not None:
                    _processed, rejected = self.overlay.consume_event_file(
                        self.maintenance_event_file,
                        source_virtual_time=observed_at,
                    )
                    if rejected:
                        self._record_failure(
                            "runtime_overlay_event",
                            RuntimeError(
                                f"quarantined {rejected} invalid maintenance event(s)"
                            ),
                        )
            except Exception as exc:
                self._record_failure("runtime_overlay_event", exc)
            try:
                result = self.producer.produce_tick(
                    observed_at,
                    excluded_asset_ids=self.overlay.excluded_equipment_ids(observed_at),
                )
            except Exception as exc:
                self._record_failure("sensor_calculation", exc)
                self.state.current_observed_at += timedelta(minutes=self.interval_minutes)
                self._refresh_counts()
                self._write_manifest()
                return self.state

            try:
                self.overlay.record_canonical_observations(
                    observed_at,
                    {record.asset_id for record in result.records},
                )
            except Exception as exc:
                self._record_failure("runtime_overlay_checkpoint", exc)

            for record in result.records:
                try:
                    self.source_writer.write(record)
                except Exception as exc:
                    self._record_failure("source", exc, record)

                if self.publisher is not None:
                    try:
                        for provenance in self.publisher.publish(record):
                            self.protocol_writer.write_provenance(provenance)
                    except Exception as exc:
                        error = self._failure_payload("protocol", exc, record)
                        self.protocol_writer.write_error(error)
                        self.state.failures.append(error)

                try:
                    self.canonical_writer.write_record(record)
                except Exception as exc:
                    self._record_failure("canonical", exc, record)

            for event in result.production_events:
                try:
                    self.canonical_writer.write_production(event)
                except Exception as exc:
                    self._record_failure("canonical_production", exc)
            for event in result.maintenance_events:
                try:
                    self.canonical_writer.write_maintenance(event)
                except Exception as exc:
                    self._record_failure("canonical_maintenance", exc)

            try:
                self.overlay.advance_active_branches_to(
                    observed_at,
                    minimum_generated_rows=self.runtime_overlay_fast_forward_rows,
                )
            except Exception as exc:
                self._record_failure("runtime_overlay", exc)

            self.state.last_sequence = self.producer.sequence
            self.state.current_observed_at += timedelta(minutes=self.interval_minutes)
            self.flush()
            self._refresh_counts()
            if self.state.failures:
                self.state.status = "partial_failure"
            self._write_manifest()
            return self.state

    def run_loop(self) -> None:
        real_seconds_per_tick = (self.interval_minutes * 60) / max(self.speed, 0.001)
        try:
            while not self.stop_event.is_set():
                self.process_tick()
                if self._closed or self.state.current_observed_at >= self.producer.end_at:
                    break
                if self.stop_event.wait(real_seconds_per_tick):
                    break
        finally:
            if not self._closed:
                terminal = "completed" if self.state.current_observed_at >= self.producer.end_at else "stopped"
                self.finish(terminal)

    def finish(self, terminal_status: str) -> RunState:
        with self.lock:
            if self._closed:
                return self.state
            self.stop_event.set()
            self.flush()
            if self.publisher is not None:
                try:
                    self.publisher.stop()
                except Exception as exc:
                    self._record_failure("protocol_cleanup", exc)
                self.publisher = None
            self.source_writer.close()
            self.protocol_writer.close()
            self.canonical_writer.close()
            self._refresh_counts()
            if self.state.failures:
                self.state.status = "partial_failure"
            else:
                self.state.status = terminal_status
            self.state.completed_at = datetime.now(tz=timezone.utc)
            self._closed = True
            self._write_manifest()
            return self.state

    def flush(self) -> None:
        self.source_writer.flush()
        self.protocol_writer.flush()
        self.canonical_writer.flush()

    def outputs(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_manifest": str(self.manifest_path),
            "source": str(self.source_writer.path),
            "protocol_provenance": str(self.protocol_writer.provenance_path),
            "protocol_errors": str(self.protocol_writer.error_path),
            "protocol_quarantine": str(self.protocol_writer.quarantine_path),
            "canonical": {path.name: str(path) for path in self.canonical_writer.paths},
            "runtime_overlay": self.overlay.outputs(),
            "counts": {
                "source_records": self.source_writer.count,
                "protocol_datavalues": self.protocol_writer.datavalue_count,
                "quarantined_datavalues": self.protocol_writer.quarantine_count,
                "canonical_observations": self.canonical_writer.observation_count,
            },
        }

    def _record_failure(self, stage: str, exc: Exception, record=None) -> None:
        self.state.failures.append(self._failure_payload(stage, exc, record))
        self.state.status = "partial_failure"

    def _failure_payload(self, stage: str, exc: Exception, record=None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stage": stage,
            "error": f"{type(exc).__name__}: {exc}",
            "recorded_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        }
        if record is not None:
            payload.update(
                {
                    "run_id": record.run_id,
                    "sequence": record.sequence,
                    "asset_id": record.asset_id,
                }
            )
        return payload

    def _refresh_counts(self) -> None:
        self.state.source_record_count = self.source_writer.count
        self.state.protocol_datavalue_count = self.protocol_writer.datavalue_count
        self.state.canonical_observation_count = self.canonical_writer.observation_count

    def _write_manifest(self) -> None:
        output_files = [
            self.source_writer.path,
            self.protocol_writer.provenance_path,
            self.protocol_writer.error_path,
            self.protocol_writer.quarantine_path,
            *self.canonical_writer.paths,
        ]
        checksums = {
            str(path.relative_to(self.run_dir)): sha256(path)
            for path in output_files
            if path.exists()
        }
        write_manifest(
            self.manifest_path,
            {
                "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
                "run_id": self.run_id,
                "simulation_session_id": self.simulation_session_id,
                "source_kind": "simulation",
                "seed": self.seed,
                "scenario": self.rate_profile,
                "runtime_overlay_fast_forward_rows": (
                    self.runtime_overlay_fast_forward_rows
                ),
                "generator_version": GENERATOR_VERSION,
                "mapping_version": self.mapping.mapping_version,
                "started_at": self.state.started_at.isoformat(timespec="seconds"),
                "completed_at": (
                    self.state.completed_at.isoformat(timespec="seconds")
                    if self.state.completed_at
                    else None
                ),
                "status": self.state.status,
                "source_record_count": self.source_writer.count,
                "protocol_datavalue_count": self.protocol_writer.datavalue_count,
                "canonical_observation_count": self.canonical_writer.observation_count,
                "outputs": self.outputs(),
                "checksums": checksums,
                "partial_failures": self.state.failures,
            },
        )


class _OpcUaRunContext:
    """Runtime context for configured-node OPC UA collection."""

    def __init__(
        self,
        *,
        run_id: str,
        output_root: Path,
        mapping_path: Path,
        endpoint: str,
        node_ids: list[str],
        reconnect_seconds: float,
    ) -> None:
        self.run_id = run_id
        self.output_root = output_root
        self.run_dir = output_root / "runs" / run_id
        self.mapping = OpcUaMapping.load(mapping_path)
        self.run_dir.mkdir(parents=True, exist_ok=False)
        source_writer: SourceRecordWriter | None = None
        protocol_writer: ProtocolRecordWriter | None = None
        try:
            self.manifest_path = self.run_dir / "run_manifest.json"
            self.endpoint = endpoint
            self.node_ids = list(dict.fromkeys(node_ids))
            source_writer = SourceRecordWriter(
                self.run_dir / "source" / "sensor_records.jsonl"
            )
            protocol_writer = ProtocolRecordWriter(self.run_dir / "protocol")
            self.source_writer = source_writer
            self.protocol_writer = protocol_writer
            self.stop_event = threading.Event()
            self.lock = threading.RLock()
            self.thread: threading.Thread | None = None
            now = datetime.now(tz=timezone.utc)
            self.state = RunState(
                run_id=run_id,
                status="running",
                started_at=now,
                current_observed_at=now,
                source_kind="opcua",
            )
            self._closed = False
            self.collector = OpcUaCollector(
                endpoint=endpoint,
                mapping=self.mapping,
                run_id=run_id,
                node_ids=self.node_ids,
                on_record=self._on_record,
                on_provenance=self._on_provenance,
                on_quarantine=self._on_quarantine,
                on_error=self._on_error,
                reconnect_seconds=reconnect_seconds,
            )
            self._write_manifest()
        except Exception:
            if protocol_writer is not None:
                protocol_writer.close()
            if source_writer is not None:
                source_writer.close()
            shutil.rmtree(self.run_dir, ignore_errors=True)
            raise

    def process_tick(self) -> RunState:
        raise RuntimeError("manual tick is only supported for simulation source runs")

    def run_loop(self) -> None:
        try:
            self.collector.run(self.stop_event)
        finally:
            if not self._closed:
                self.finish("stopped")

    def finish(self, terminal_status: str) -> RunState:
        with self.lock:
            if self._closed:
                return self.state
            self.stop_event.set()
            self.flush()
            self.source_writer.close()
            self.protocol_writer.close()
            self._refresh_counts()
            self.state.status = "partial_failure" if self.state.failures else terminal_status
            self.state.completed_at = datetime.now(tz=timezone.utc)
            self._closed = True
            self._write_manifest()
            return self.state

    def flush(self) -> None:
        self.source_writer.flush()
        self.protocol_writer.flush()

    def outputs(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_manifest": str(self.manifest_path),
            "source": str(self.source_writer.path),
            "protocol_provenance": str(self.protocol_writer.provenance_path),
            "protocol_errors": str(self.protocol_writer.error_path),
            "protocol_quarantine": str(self.protocol_writer.quarantine_path),
            "canonical": {},
            "counts": {
                "source_records": self.source_writer.count,
                "protocol_datavalues": self.protocol_writer.datavalue_count,
                "quarantined_datavalues": self.protocol_writer.quarantine_count,
                "canonical_observations": 0,
            },
        }

    def _on_record(self, record) -> None:
        with self.lock:
            try:
                self.source_writer.write(record)
                self.state.last_sequence = record.sequence
                self.state.current_observed_at = record.observed_at
            except Exception as exc:
                self._append_failure("source", exc)
            self._checkpoint()

    def _on_provenance(self, payload: dict[str, Any]) -> None:
        with self.lock:
            try:
                self.protocol_writer.write_provenance(payload)
            except Exception as exc:
                self._append_failure("protocol_provenance", exc)
            self._checkpoint()

    def _on_quarantine(self, payload: dict[str, Any]) -> None:
        with self.lock:
            self.protocol_writer.write_quarantine(payload)
            self.state.failures.append({"stage": "opcua_quarantine", **payload})
            self.state.status = "partial_failure"
            self._checkpoint()

    def _on_error(self, payload: dict[str, Any]) -> None:
        with self.lock:
            self.protocol_writer.write_error(payload)
            self.state.failures.append(payload)
            self.state.status = "partial_failure"
            self._checkpoint()

    def _append_failure(self, stage: str, exc: Exception) -> None:
        payload = {
            "stage": stage,
            "error": f"{type(exc).__name__}: {exc}",
            "recorded_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        }
        self.state.failures.append(payload)
        self.state.status = "partial_failure"

    def _checkpoint(self) -> None:
        self.flush()
        self._refresh_counts()
        self._write_manifest()

    def _refresh_counts(self) -> None:
        self.state.source_record_count = self.source_writer.count
        self.state.protocol_datavalue_count = self.protocol_writer.datavalue_count
        self.state.canonical_observation_count = 0

    def _write_manifest(self) -> None:
        output_files = [
            self.source_writer.path,
            self.protocol_writer.provenance_path,
            self.protocol_writer.error_path,
            self.protocol_writer.quarantine_path,
        ]
        checksums = {
            str(path.relative_to(self.run_dir)): sha256(path)
            for path in output_files
            if path.exists()
        }
        write_manifest(
            self.manifest_path,
            {
                "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
                "run_id": self.run_id,
                "source_kind": "opcua",
                "endpoint": self.endpoint,
                "node_ids": self.node_ids,
                "mapping_version": self.mapping.mapping_version,
                "started_at": self.state.started_at.isoformat(timespec="seconds"),
                "completed_at": (
                    self.state.completed_at.isoformat(timespec="seconds")
                    if self.state.completed_at
                    else None
                ),
                "status": self.state.status,
                "source_record_count": self.source_writer.count,
                "protocol_datavalue_count": self.protocol_writer.datavalue_count,
                "quarantine_count": self.protocol_writer.quarantine_count,
                "canonical_observation_count": 0,
                "outputs": self.outputs(),
                "checksums": checksums,
                "partial_failures": self.state.failures,
            },
        )


class RuntimeManager:
    def __init__(
        self,
        *,
        output_root: Path,
        mapping_path: Path,
        opcua_endpoint: str,
        worker_join_timeout_seconds: float = 5.0,
        maintenance_event_file: Path | None = None,
        runtime_overlay_fast_forward_rows: int = 0,
    ) -> None:
        self.output_root = output_root
        self.mapping_path = mapping_path
        self.opcua_endpoint = opcua_endpoint
        self.worker_join_timeout_seconds = max(0.0, worker_join_timeout_seconds)
        self.maintenance_event_file = maintenance_event_file
        if not 0 <= runtime_overlay_fast_forward_rows <= MAX_RUNTIME_OVERLAY_FAST_FORWARD_ROWS:
            raise ValueError(
                "runtime_overlay_fast_forward_rows must be between 0 and "
                f"{MAX_RUNTIME_OVERLAY_FAST_FORWARD_ROWS}"
            )
        self.runtime_overlay_fast_forward_rows = runtime_overlay_fast_forward_rows
        self._runs: dict[str, _RunContext | _OpcUaRunContext] = {}
        self._lock = threading.RLock()

    def start_run(
        self,
        *,
        run_id: str | None = None,
        simulation_session_id: str | None = None,
        seed: int = 42,
        start_at: datetime | None = None,
        duration_hours: int = 24,
        interval_minutes: int = 10,
        product_cycle_minutes: int = 20,
        rate_profile: str = "balanced_demo",
        speed: float = 60.0,
        continuous: bool = True,
        publish_opcua: bool = True,
        source_kind: str = "simulation",
        opcua_source_endpoint: str | None = None,
        opcua_node_ids: list[str] | None = None,
        reconnect_seconds: float = 1.0,
        runtime_overlay_fast_forward_rows: int | None = None,
    ) -> dict[str, Any]:
        if source_kind not in {"simulation", "opcua"}:
            raise ValueError(f"unsupported source_kind: {source_kind}")
        if speed <= 0:
            raise ValueError("speed must be positive")
        if duration_hours <= 0:
            raise ValueError("duration_hours must be positive")
        if (
            runtime_overlay_fast_forward_rows is not None
            and not 0
            <= runtime_overlay_fast_forward_rows
            <= MAX_RUNTIME_OVERLAY_FAST_FORWARD_ROWS
        ):
            raise ValueError(
                "runtime_overlay_fast_forward_rows must be between 0 and "
                f"{MAX_RUNTIME_OVERLAY_FAST_FORWARD_ROWS}"
            )
        resolved_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        resolved_session_id = simulation_session_id or resolved_id
        if not resolved_session_id.strip():
            raise ValueError("simulation_session_id must not be blank")
        resolved_start = start_at or datetime.now(tz=timezone.utc).replace(microsecond=0)
        if resolved_start.tzinfo is None:
            raise ValueError("start_at must include a timezone")
        with self._lock:
            if resolved_id in self._runs or (self.output_root / "runs" / resolved_id).exists():
                raise ValueError(f"run_id already exists: {resolved_id}")
            active = [run for run in self._runs.values() if not run._closed]
            if active:
                raise RuntimeError(f"another run is active: {active[0].run_id}")
            if source_kind == "opcua":
                if runtime_overlay_fast_forward_rows is not None:
                    raise ValueError(
                        "runtime_overlay_fast_forward_rows is only supported for "
                        "simulation source runs"
                    )
                if simulation_session_id is not None:
                    raise ValueError(
                        "simulation_session_id is only supported for simulation source runs"
                    )
                if not continuous:
                    raise ValueError("OPC UA source runs require continuous=true")
                if not opcua_node_ids:
                    raise ValueError("at least one OPC UA node_id is required")
                if reconnect_seconds <= 0:
                    raise ValueError("reconnect_seconds must be positive")
                context = _OpcUaRunContext(
                    run_id=resolved_id,
                    output_root=self.output_root,
                    mapping_path=self.mapping_path,
                    endpoint=opcua_source_endpoint or self.opcua_endpoint,
                    node_ids=opcua_node_ids or [],
                    reconnect_seconds=reconnect_seconds,
                )
            else:
                context = _RunContext(
                    run_id=resolved_id,
                    simulation_session_id=resolved_session_id,
                    output_root=self.output_root,
                    mapping_path=self.mapping_path,
                    opcua_endpoint=self.opcua_endpoint,
                    start_at=resolved_start,
                    end_at=resolved_start + timedelta(hours=duration_hours),
                    interval_minutes=interval_minutes,
                    product_cycle_minutes=product_cycle_minutes,
                    seed=seed,
                    rate_profile=rate_profile,
                    speed=speed,
                    continuous=continuous,
                    publish_opcua=publish_opcua,
                    maintenance_event_file=self.maintenance_event_file,
                    runtime_overlay_fast_forward_rows=(
                        self.runtime_overlay_fast_forward_rows
                        if runtime_overlay_fast_forward_rows is None
                        else runtime_overlay_fast_forward_rows
                    ),
                )
            self._runs[resolved_id] = context
            if continuous:
                context.thread = threading.Thread(
                    target=context.run_loop,
                    name=f"gen-data-{resolved_id}",
                    daemon=True,
                )
                context.thread.start()
            return context.state.to_dict()

    def tick(self, run_id: str) -> dict[str, Any]:
        context = self._get(run_id)
        return context.process_tick().to_dict()

    def stop(self, run_id: str) -> dict[str, Any]:
        context = self._get(run_id)
        context.stop_event.set()
        thread = context.thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=self.worker_join_timeout_seconds)
            if thread.is_alive():
                with context.lock:
                    context.state.status = "stopping"
                    context.state.failures.append(
                        {
                            "stage": "worker_stop_timeout",
                            "error": (
                                "worker did not stop within "
                                f"{self.worker_join_timeout_seconds:g} seconds; "
                                "writers remain open until worker termination"
                            ),
                            "recorded_at": datetime.now(tz=timezone.utc).isoformat(
                                timespec="seconds"
                            ),
                        }
                    )
                    context._write_manifest()
                    return context.state.to_dict()
        if not context._closed:
            context.finish("stopped")
        return context.state.to_dict()

    def status(self, run_id: str) -> dict[str, Any]:
        return self._get(run_id).state.to_dict()

    def outputs(self, run_id: str) -> dict[str, Any]:
        return self._get(run_id).outputs()

    def process_maintenance_event(
        self,
        run_id: str,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        context = self._get(run_id)
        if not isinstance(context, _RunContext):
            raise RuntimeError("Runtime Overlay is only supported for simulation source runs")
        with context.lock:
            return context.overlay.process_event(event)

    def fast_forward_overlay(
        self,
        run_id: str,
        *,
        equipment_id: str,
        target_generated_rows: int,
    ) -> dict[str, Any]:
        """Advance one Overlay branch while preserving the global run clock."""
        context = self._get(run_id)
        if not isinstance(context, _RunContext):
            raise RuntimeError("Runtime Overlay is only supported for simulation source runs")
        with context.lock:
            if context._closed or context.state.status not in {
                "running",
                "partial_failure",
            }:
                raise RuntimeError(f"run {run_id} is not active")
            global_observed_at = context.state.current_observed_at
            global_sequence = context.producer.sequence
            rows, available = context.overlay.advance_branch_to_generated_rows(
                equipment_id,
                target_generated_rows,
            )
            if available is not None:
                context.overlay.persist_available_event(available)
            key = context.overlay.branch_by_equipment[equipment_id]
            branch = context.overlay.branches[key]
            context._refresh_counts()
            context._write_manifest()
            return {
                "run_id": run_id,
                "equipment_id": equipment_id,
                "global_clock_advanced": False,
                "global_observed_at": global_observed_at.isoformat(),
                "global_sequence": global_sequence,
                "generated_batch_rows": len(rows),
                "total_generated_rows": branch.generated_rows,
                "latest_observed_at": rows[-1]["observed_at"] if rows else None,
                "available_event": available,
            }

    def ready(self) -> bool:
        return self.mapping_path.is_file() and self.output_root.parent.exists()

    def shutdown(self) -> None:
        for context in list(self._runs.values()):
            if not context._closed:
                self.stop(context.run_id)

    def _get(self, run_id: str) -> _RunContext | _OpcUaRunContext:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise KeyError(f"run not found: {run_id}") from exc
