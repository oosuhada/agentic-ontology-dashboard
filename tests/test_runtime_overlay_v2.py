"""Runtime Overlay tests for the current RuntimeManager/SensorRecord architecture."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.observation.models import SENSOR_RECORD_SCHEMA_VERSION, SensorRecord
from app.runtime.manager import RuntimeManager
from app.runtime.overlay import (
    OverlayConflict,
    OverlayContractError,
    RuntimeOverlayCoordinator,
    StaleOverlayEvent,
    _semantic_observation_hash,
    _storage_path_component,
)
from app.simulation.producer import SimulationProducer


START = datetime(2026, 8, 18, 1, 0, tzinfo=timezone.utc)
MAPPING = Path("mappings/opcua_nodes.v1.json")
CONTRACT_VECTOR = Path("tests/fixtures/runtime-overlay-output-v1")


def producer(run_id: str = "DEMO-001") -> SimulationProducer:
    return SimulationProducer(
        run_id=run_id,
        start_at=START,
        end_at=START + timedelta(hours=4),
        interval_minutes=10,
        product_cycle_minutes=20,
        seed=42,
    )


def lineage() -> dict[str, str]:
    return {
        "source_product_result_id": "RESULT-001",
        "source_evidence_id": "EVIDENCE-001",
        "decision_id": "DECISION-001",
    }


class RuntimeOverlayV2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.producer = producer()
        self.target = next(
            asset for asset in self.producer.assets if asset["asset_type"] == "cnc"
        )
        self.other = next(
            asset
            for asset in self.producer.assets
            if asset["asset_type"] == "cnc" and asset != self.target
        )
        self.producer.runtimes[self.target["asset_id"]].tool_wear_min = 123.4
        self.started_at = START
        self.completed_at = START + timedelta(minutes=30)
        self.restart_at = START + timedelta(minutes=40)

    def coordinator(
        self,
        canonical: SimulationProducer | None = None,
        simulation_session_id: str | None = None,
    ):
        selected = canonical or self.producer
        return RuntimeOverlayCoordinator(
            canonical_producer=selected,
            simulation_session_id=simulation_session_id or selected.run_id,
            output_root=self.root,
            generated_at=lambda: START + timedelta(hours=1),
        )

    def event(self, event_type: str, version: int, **extra: object):
        payload: dict[str, object] = {
            "contract_version": "maintenance-replay-v1",
            "event_type": event_type,
            "event_id": f"00000000-0000-5000-8000-{version:012d}",
            "idempotency_key": f"MAINTENANCE-001:{version}",
            "state_version": version,
            "simulation_session_id": "DEMO-001",
            "maintenance_action_id": "ACTION-001",
            "equipment_id": self.target["asset_id"],
            "caused_by": lineage(),
        }
        payload.update(extra)
        return payload

    def started(self):
        return self.event(
            "maintenance.started",
            1,
            work_order_id="WO-001",
            maintenance_started_at=self.started_at.isoformat(),
            action_code="TOOL_REPLACEMENT",
        )

    def completed(self):
        return self.event(
            "maintenance.completed",
            2,
            maintenance_event_id="MAINT-001",
            maintenance_completed_at=self.completed_at.isoformat(),
            action_code="TOOL_REPLACEMENT",
            state_patch={
                "tool_wear_min": {
                    "operation": "reset",
                    "value": 0,
                    "unit": "min",
                }
            },
        )

    def replay_requested(self):
        return self.event(
            "maintenance.replay_requested",
            3,
            maintenance_event_id="MAINT-001",
            restart_at=self.restart_at.isoformat(),
        )

    def prepare_branch(self, coordinator: RuntimeOverlayCoordinator) -> None:
        coordinator.process_event(self.started())
        coordinator.process_event(self.completed())
        coordinator.process_event(self.replay_requested())

    def cooling_started(self):
        return self.event(
            "maintenance.started",
            1,
            work_order_id="WO-COOLING-001",
            maintenance_started_at=self.started_at.isoformat(),
            action_code="COOLING_SYSTEM_RESTORE",
        )

    def cooling_completed(self):
        return self.event(
            "maintenance.completed",
            2,
            maintenance_event_id="MAINT-COOLING-001",
            maintenance_completed_at=self.completed_at.isoformat(),
            action_code="COOLING_SYSTEM_RESTORE",
            state_patch={
                "cooling_system_state": {
                    "operation": "restore",
                    "value": "nominal",
                    "unit": "state",
                }
            },
        )

    def cooling_replay_requested(self):
        return self.event(
            "maintenance.replay_requested",
            3,
            maintenance_event_id="MAINT-COOLING-001",
            restart_at=self.restart_at.isoformat(),
            action_code="COOLING_SYSTEM_RESTORE",
            state_patch={
                "cooling_system_state": {
                    "operation": "restore",
                    "value": "nominal",
                    "unit": "state",
                }
            },
        )

    def test_target_only_branch_preserves_canonical_runtime_and_other_assets(self):
        coordinator = self.coordinator()
        coordinator.process_event(self.started())

        excluded = coordinator.excluded_equipment_ids(self.started_at)
        self.assertEqual(excluded, {self.target["asset_id"]})
        target_runtime = self.producer.runtimes[self.target["asset_id"]]
        original_wear = target_runtime.tool_wear_min
        result = self.producer.produce_tick(
            self.started_at,
            excluded_asset_ids=excluded,
        )

        self.assertEqual(len(result.records), 99)
        self.assertNotIn(self.target["asset_id"], {row.asset_id for row in result.records})
        self.assertIn(self.other["asset_id"], {row.asset_id for row in result.records})
        self.assertEqual(target_runtime.tool_wear_min, original_wear)

        coordinator.process_event(self.completed())
        branch = coordinator.branches[
            coordinator.branch_by_equipment[self.target["asset_id"]]
        ]
        self.assertEqual(branch.runtime.tool_wear_min, 0.0)
        self.assertEqual(target_runtime.tool_wear_min, 123.4)

    def test_maintenance_holds_last_observation_until_restarted_overlay_is_generated(self):
        coordinator = self.coordinator()
        first_tick = self.producer.produce_tick(START)
        by_equipment = {
            record.asset_id: record.to_dict() for record in first_tick.records
        }
        coordinator.record_canonical_observations(
            START,
            set(by_equipment),
            by_equipment,
        )
        held_before = by_equipment[self.target["asset_id"]]

        started = self.started()
        started_at = START + timedelta(minutes=10)
        started["maintenance_started_at"] = started_at.isoformat()
        coordinator.process_event(started, source_virtual_time=started_at)

        maintenance = coordinator.equipment_state(self.target["asset_id"])
        self.assertEqual(maintenance["operational_state"], "MAINTENANCE")
        self.assertTrue(maintenance["held"])
        self.assertFalse(maintenance["usable_for_prediction"])
        self.assertEqual(maintenance["current_observation"], held_before)

        coordinator.process_event(self.completed(), source_virtual_time=started_at)
        completed = coordinator.equipment_state(self.target["asset_id"])
        self.assertEqual(
            completed["operational_state"], "MAINTENANCE_COMPLETED"
        )
        self.assertEqual(completed["current_observation"], held_before)

        coordinator.process_event(
            self.replay_requested(), source_virtual_time=started_at
        )
        restarting = coordinator.equipment_state(self.target["asset_id"])
        self.assertEqual(restarting["operational_state"], "RESTARTING")
        self.assertTrue(restarting["held"])

        rows, _available = coordinator.advance_branch_to(
            self.target["asset_id"], self.restart_at
        )
        running = coordinator.equipment_state(self.target["asset_id"])
        self.assertEqual(running["operational_state"], "RUNNING")
        self.assertFalse(running["held"])
        self.assertTrue(running["usable_for_prediction"])
        self.assertEqual(running["current_observation"], rows[-1])
        self.assertNotEqual(
            running["current_observation"]["observed_at"],
            held_before["observed_at"],
        )

    def test_cooling_restore_resumes_normal_overlay_without_resetting_tool_wear(self):
        coordinator = self.coordinator()
        coordinator.process_event(self.cooling_started())
        coordinator.process_event(self.cooling_completed())

        branch = coordinator.branches[
            coordinator.branch_by_equipment[self.target["asset_id"]]
        ]
        self.assertEqual(branch.action_code, "COOLING_SYSTEM_RESTORE")
        self.assertEqual(branch.runtime.tool_wear_min, 123.4)

        coordinator.process_event(self.cooling_replay_requested())
        rows, available = coordinator.advance_branch_to(
            self.target["asset_id"],
            self.restart_at + timedelta(minutes=20),
        )

        self.assertEqual(len(rows), 3)
        self.assertIsNotNone(available)
        self.assertTrue(all(row["tool_wear_min"] >= 123.4 for row in rows))
        self.assertTrue(
            all(
                row["process_temperature_k"] - row["air_temperature_k"] >= 8.89
                for row in rows
            )
        )
        self.assertTrue(
            all(row["maintenance_event_id"] == "MAINT-COOLING-001" for row in rows)
        )

    def test_action_and_state_patch_mismatch_is_rejected(self):
        coordinator = self.coordinator()
        coordinator.process_event(self.cooling_started())
        mismatched = self.cooling_completed()
        mismatched["state_patch"] = {
            "tool_wear_min": {"operation": "reset", "value": 0, "unit": "min"}
        }

        with self.assertRaisesRegex(
            OverlayContractError,
            "COOLING_SYSTEM_RESTORE requires its canonical state_patch",
        ):
            coordinator.process_event(mismatched)

    def test_replay_action_and_state_patch_must_be_provided_together(self):
        coordinator = self.coordinator()
        coordinator.process_event(self.cooling_started())
        coordinator.process_event(self.cooling_completed())
        invalid = self.replay_requested()
        invalid["action_code"] = "COOLING_SYSTEM_RESTORE"

        with self.assertRaisesRegex(
            OverlayContractError,
            "replay action_code and state_patch must be provided together",
        ):
            coordinator.process_event(invalid)

    def test_gap_then_branch_local_fast_forward_emits_flat_observations(self):
        coordinator = self.coordinator()
        coordinator.process_event(self.started())
        coordinator.process_event(self.completed())

        rows, available = coordinator.advance_branch_to(
            self.target["asset_id"],
            self.completed_at + timedelta(hours=1),
        )
        self.assertEqual(rows, [])
        self.assertIsNone(available)

        coordinator.process_event(self.replay_requested())
        rows, available = coordinator.advance_branch_to(
            self.target["asset_id"],
            self.restart_at + timedelta(minutes=20),
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [row["observed_at"] for row in rows],
            [
                self.restart_at.isoformat(),
                (self.restart_at + timedelta(minutes=10)).isoformat(),
                (self.restart_at + timedelta(minutes=20)).isoformat(),
            ],
        )
        self.assertTrue(
            all(
                row["source_kind"] == "maintenance_replay_overlay" for row in rows
            )
        )
        self.assertTrue(
            all(
                row["contract_version"] == "runtime-overlay-observation-v1"
                for row in rows
            )
        )
        self.assertTrue(
            all(len(row["base_source_sha256"]) == 64 for row in rows)
        )
        self.assertTrue(
            all(
                row["base_source_sha256"] == rows[0]["base_source_sha256"]
                for row in rows
            )
        )
        int(rows[0]["base_source_sha256"], 16)
        self.assertTrue(all(row["branch_kind"] == "overlay" for row in rows))
        self.assertTrue(
            all(
                row["measurements"]["torque_nm"] == row["torque_nm"]
                for row in rows
            )
        )
        self.assertTrue(all(row["maintenance_event_id"] == "MAINT-001" for row in rows))
        self.assertEqual(rows[0]["tool_wear_min"], 0.0)
        self.assertIn("torque_nm", rows[0])
        self.assertNotIn("history_requirement", rows[0])
        canonical_identity = SensorRecord(
            schema_version=SENSOR_RECORD_SCHEMA_VERSION,
            run_id="ANY-CANONICAL-RUN",
            sequence=1,
            asset_id=rows[0]["asset_id"],
            observed_at=datetime.fromisoformat(rows[0]["observed_at"]),
            measurements=rows[0]["measurements"],
            generator_version=rows[0]["generator_version"],
            asset_type=rows[0]["asset_type"],
            site_id=rows[0]["site_id"],
            cell_id=rows[0]["cell_id"],
        ).observation_id
        self.assertNotEqual(rows[0]["observation_id"], canonical_identity)
        self.assertEqual(
            available["event_type"], "runtime_overlay.observations.available"
        )
        self.assertEqual(
            available["contract_version"],
            "runtime-overlay-observations-available-v1",
        )
        self.assertEqual(available["batch_rows"], 3)
        self.assertEqual(available["generated_rows"], 3)
        self.assertEqual(
            available["storage_reference"],
            "runtime_overlay/"
            "sha256-7a9b002b3f8d2692b4473e3e5140438602f09c7186f9b2b8f99bda126775360d.jsonl",
        )
        self.assertFalse(Path(available["storage_reference"]).is_absolute())
        self.assertNotIn("required_rows", available)

    def test_manager_fast_forward_targets_one_branch_without_advancing_global_clock(self):
        manager = RuntimeManager(
            output_root=self.root,
            mapping_path=MAPPING,
            opcua_endpoint="opc.tcp://127.0.0.1:48501/gen-data/",
        )
        manager.start_run(
            run_id="DEMO-001",
            simulation_session_id="DEMO-001",
            start_at=START,
            duration_hours=8,
            continuous=False,
            publish_opcua=False,
        )
        try:
            context = manager._get("DEMO-001")
            other_runtime = context.producer.runtimes[self.other["asset_id"]]
            other_state_before = dict(vars(other_runtime))
            manager.process_maintenance_event("DEMO-001", self.started())
            manager.process_maintenance_event("DEMO-001", self.completed())
            manager.process_maintenance_event("DEMO-001", self.replay_requested())

            result = manager.fast_forward_overlay(
                "DEMO-001",
                equipment_id=self.target["asset_id"],
                target_generated_rows=36,
            )

            self.assertFalse(result["global_clock_advanced"])
            self.assertEqual(result["global_observed_at"], START.isoformat())
            self.assertEqual(result["global_sequence"], 0)
            self.assertEqual(result["generated_batch_rows"], 36)
            self.assertEqual(result["total_generated_rows"], 36)
            self.assertEqual(
                result["latest_observed_at"],
                (self.restart_at + timedelta(minutes=350)).isoformat(),
            )
            self.assertEqual(context.state.current_observed_at, START)
            self.assertEqual(context.producer.sequence, 0)
            self.assertEqual(dict(vars(other_runtime)), other_state_before)
            self.assertEqual(result["available_event"]["batch_rows"], 36)

            replay = manager.fast_forward_overlay(
                "DEMO-001",
                equipment_id=self.target["asset_id"],
                target_generated_rows=36,
            )
            self.assertEqual(replay["generated_batch_rows"], 0)
            self.assertEqual(replay["total_generated_rows"], 36)
            self.assertIsNone(replay["available_event"])

            next_status = manager.tick("DEMO-001")
            branch = context.overlay.branches[
                context.overlay.branch_by_equipment[self.target["asset_id"]]
            ]
            self.assertEqual(
                next_status["current_observed_at"],
                (START + timedelta(minutes=10)).isoformat(),
            )
            self.assertEqual(next_status["source_record_count"], 99)
            self.assertEqual(next_status["canonical_observation_count"], 99)
            self.assertEqual(branch.generated_rows, 37)
            self.assertEqual(
                branch.next_observed_at,
                self.restart_at + timedelta(minutes=370),
            )
        finally:
            manager.stop("DEMO-001")

    def test_configured_fast_forward_runs_automatically_after_replay_event(self):
        manager = RuntimeManager(
            output_root=self.root,
            mapping_path=MAPPING,
            opcua_endpoint="opc.tcp://127.0.0.1:48501/gen-data/",
            runtime_overlay_fast_forward_rows=36,
        )
        manager.start_run(
            run_id="DEMO-001",
            simulation_session_id="DEMO-001",
            start_at=START,
            duration_hours=8,
            continuous=False,
            publish_opcua=False,
        )
        try:
            manager.process_maintenance_event("DEMO-001", self.started())
            manager.process_maintenance_event("DEMO-001", self.completed())
            manager.process_maintenance_event("DEMO-001", self.replay_requested())

            status = manager.tick("DEMO-001")
            context = manager._get("DEMO-001")
            branch = context.overlay.branches[
                context.overlay.branch_by_equipment[self.target["asset_id"]]
            ]

            self.assertEqual(
                status["current_observed_at"],
                (START + timedelta(minutes=10)).isoformat(),
            )
            self.assertEqual(status["source_record_count"], 99)
            self.assertEqual(status["canonical_observation_count"], 99)
            self.assertEqual(branch.generated_rows, 36)
            self.assertEqual(
                branch.next_observed_at,
                self.restart_at + timedelta(minutes=360),
            )
            available_events = [
                json.loads(line)
                for line in context.overlay.available_event_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            self.assertEqual(len(available_events), 1)
            self.assertEqual(available_events[0]["batch_rows"], 36)
            self.assertEqual(available_events[0]["generated_rows"], 36)
        finally:
            manager.stop("DEMO-001")

    def test_run_level_fast_forward_target_overrides_application_default(self):
        manager = RuntimeManager(
            output_root=self.root,
            mapping_path=MAPPING,
            opcua_endpoint="opc.tcp://127.0.0.1:48501/gen-data/",
            runtime_overlay_fast_forward_rows=36,
        )
        manager.start_run(
            run_id="DEMO-001",
            simulation_session_id="DEMO-001",
            start_at=START,
            duration_hours=8,
            continuous=False,
            publish_opcua=False,
            runtime_overlay_fast_forward_rows=12,
        )
        try:
            manager.process_maintenance_event("DEMO-001", self.started())
            manager.process_maintenance_event("DEMO-001", self.completed())
            manager.process_maintenance_event("DEMO-001", self.replay_requested())

            manager.tick("DEMO-001")
            context = manager._get("DEMO-001")
            branch = context.overlay.branches[
                context.overlay.branch_by_equipment[self.target["asset_id"]]
            ]
            manifest = json.loads(context.manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(branch.generated_rows, 12)
            self.assertEqual(context.runtime_overlay_fast_forward_rows, 12)
            self.assertEqual(manifest["runtime_overlay_fast_forward_rows"], 12)
        finally:
            manager.stop("DEMO-001")

    def test_official_unicode_checksum_contract_vector(self):
        payload = json.loads(
            (CONTRACT_VECTOR / "observation-unicode.json").read_text(
                encoding="utf-8"
            )
        )
        expected = (
            CONTRACT_VECTOR / "expected-observation-sha256.txt"
        ).read_text(encoding="utf-8").strip()

        self.assertEqual(_semantic_observation_hash(payload), expected)
        self.assertEqual(payload["observation_sha256"], expected)

        payload["generated_at"] = "2026-08-18T03:00:00+00:00"
        self.assertEqual(_semantic_observation_hash(payload), expected)

    def test_path_identity_contract_vector_is_collision_resistant_and_contained(
        self,
    ):
        vector = json.loads(
            (CONTRACT_VECTOR / "path-identities.json").read_text(encoding="utf-8")
        )
        references = []
        for case in vector["cases"]:
            component = _storage_path_component(
                case["simulation_session_id"],
                case["overlay_branch_id"],
            )
            actual = f"runtime_overlay/{component}.jsonl"
            self.assertEqual(actual, case["expected_storage_reference"])
            references.append(actual)
        self.assertEqual(len(references), len(set(references)))

        coordinator = self.coordinator()
        self.prepare_branch(coordinator)
        branch = coordinator.branches[
            coordinator.branch_by_equipment[self.target["asset_id"]]
        ]
        branch.simulation_session_id = "."
        branch.overlay_branch_id = ".."
        path = coordinator.store.path_for(branch)
        self.assertEqual(path.parent.resolve(), coordinator.store.root.resolve())
        self.assertTrue(path.name.startswith("sha256-"))

    def test_contract_idempotency_version_and_unknown_field_guards(self):
        coordinator = self.coordinator()
        first = coordinator.process_event(self.started())
        replayed = coordinator.process_event(self.started())
        self.assertFalse(first["replayed"])
        self.assertTrue(replayed["replayed"])

        conflict = self.started()
        conflict["work_order_id"] = "WO-DIFFERENT"
        with self.assertRaises(OverlayConflict):
            coordinator.process_event(conflict)

        coordinator.process_event(self.completed())
        stale = self.replay_requested()
        stale["state_version"] = 1
        stale["event_id"] = "00000000-0000-5000-8000-000000000099"
        stale["idempotency_key"] = "MAINTENANCE-001:STALE"
        with self.assertRaises(StaleOverlayEvent):
            coordinator.process_event(stale)

        unknown = self.replay_requested()
        unknown["prediction_ready"] = True
        with self.assertRaises(OverlayContractError):
            coordinator.process_event(unknown)

        invalid_id = self.replay_requested()
        invalid_id["event_id"] = 123
        with self.assertRaises(OverlayContractError):
            coordinator.process_event(invalid_id)

        invalid_optional_patch = self.replay_requested()
        invalid_optional_patch["state_patch"] = {"tool_wear_min": {"value": 0}}
        with self.assertRaises(OverlayContractError):
            coordinator.process_event(invalid_optional_patch)

        wrong_session = self.replay_requested()
        wrong_session["simulation_session_id"] = "OTHER-SESSION"
        with self.assertRaises(OverlayContractError):
            coordinator.process_event(wrong_session)

    def test_checkpoint_branch_is_scoped_to_its_simulation_run(self):
        coordinator = self.coordinator()
        coordinator.process_event(self.started())
        original_branch = coordinator.branches[
            coordinator.branch_by_equipment[self.target["asset_id"]]
        ]

        other_run = self.coordinator(
            producer("OTHER-SOURCE-RUN"),
            simulation_session_id="DEMO-001",
        )
        self.assertEqual(other_run.active_equipment_ids, ())
        self.assertEqual(other_run.excluded_equipment_ids(self.started_at), set())
        checkpoint = json.loads(
            other_run.checkpoint_path.read_text(encoding="utf-8")
        )
        self.assertEqual(checkpoint["source_run_id"], "OTHER-SOURCE-RUN")
        self.assertEqual(checkpoint["simulation_session_id"], "DEMO-001")
        self.assertEqual(checkpoint["branches"], {})
        self.assertEqual(len(original_branch.base_source_sha256), 64)

    def test_checkpoint_recovers_pending_available_event_without_duplicates(self):
        coordinator = self.coordinator()
        self.prepare_branch(coordinator)
        rows, available = coordinator.advance_branch_to(
            self.target["asset_id"],
            self.restart_at + timedelta(minutes=20),
        )
        self.assertEqual(len(rows), 3)
        self.assertIsNotNone(available)
        self.assertFalse(coordinator.available_event_path.exists())
        branch = coordinator.branches[
            coordinator.branch_by_equipment[self.target["asset_id"]]
        ]

        resumed = self.coordinator(producer())
        resumed_branch = resumed.branches[
            resumed.branch_by_equipment[self.target["asset_id"]]
        ]
        self.assertEqual(
            resumed_branch.base_source_sha256,
            branch.base_source_sha256,
        )
        self.assertEqual(resumed.recover_pending_available_events(), 1)
        events = [
            json.loads(line)
            for line in resumed.available_event_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_id"], available["event_id"])

        second_restart = self.coordinator(producer())
        self.assertEqual(second_restart.recover_pending_available_events(), 0)
        self.assertEqual(
            len(
                second_restart.available_event_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ),
            1,
        )

    def test_future_start_snapshots_at_first_due_tick_without_canonical_overlap(self):
        coordinator = self.coordinator()
        future_start = self.started()
        future_started_at = START + timedelta(minutes=15)
        future_start["maintenance_started_at"] = future_started_at.isoformat()

        accepted = coordinator.process_event(
            future_start,
            source_virtual_time=START,
        )
        self.assertEqual(accepted["phase"], "pending")
        self.assertEqual(coordinator.active_equipment_ids, ())

        for observed_at in (START, START + timedelta(minutes=10)):
            result = self.producer.produce_tick(observed_at)
            coordinator.record_canonical_observations(
                observed_at,
                {record.asset_id for record in result.records},
            )
        runtime_at_boundary = self.producer.runtimes[self.target["asset_id"]]
        wear_at_boundary = runtime_at_boundary.tool_wear_min

        coordinator.activate_due_started_events(START + timedelta(minutes=20))
        branch = coordinator.branches[
            coordinator.branch_by_equipment[self.target["asset_id"]]
        ]
        self.assertEqual(branch.runtime.tool_wear_min, wear_at_boundary)
        self.assertEqual(
            coordinator.excluded_equipment_ids(START + timedelta(minutes=20)),
            {self.target["asset_id"]},
        )

        due_result = self.producer.produce_tick(
            START + timedelta(minutes=20),
            excluded_asset_ids=coordinator.excluded_equipment_ids(
                START + timedelta(minutes=20)
            ),
        )
        self.assertNotIn(
            self.target["asset_id"],
            {record.asset_id for record in due_result.records},
        )
        self.assertLess(
            coordinator.last_canonical_observed_at[self.target["asset_id"]],
            future_started_at,
        )

    def test_pending_future_start_is_restored_before_due_tick(self):
        coordinator = self.coordinator()
        future_start = self.started()
        future_started_at = START + timedelta(minutes=20)
        future_start["maintenance_started_at"] = future_started_at.isoformat()
        coordinator.process_event(future_start, source_virtual_time=START)
        coordinator.process_event(self.completed(), source_virtual_time=START)
        coordinator.process_event(self.replay_requested(), source_virtual_time=START)

        resumed_producer = producer()
        resumed_producer.runtimes[self.target["asset_id"]].tool_wear_min = 123.4
        resumed = self.coordinator(resumed_producer)
        self.assertEqual(len(resumed.pending_started_events), 1)
        self.assertEqual(len(next(iter(resumed.pending_event_streams.values()))), 3)
        self.assertEqual(resumed.active_equipment_ids, ())

        for observed_at in (START, START + timedelta(minutes=10)):
            result = resumed_producer.produce_tick(observed_at)
            resumed.record_canonical_observations(
                observed_at,
                {record.asset_id for record in result.records},
            )
        resumed.activate_due_started_events(future_started_at)
        self.assertEqual(
            resumed.active_equipment_ids,
            (self.target["asset_id"],),
        )
        self.assertEqual(resumed.pending_started_events, {})
        branch = resumed.branches[
            resumed.branch_by_equipment[self.target["asset_id"]]
        ]
        self.assertEqual(branch.phase, "restarting")
        self.assertEqual(branch.state_version, 3)
        self.assertEqual(branch.runtime.tool_wear_min, 0.0)
        rows, _available = resumed.advance_branch_to(
            self.target["asset_id"],
            self.restart_at,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["observed_at"], self.restart_at.isoformat())

    def test_future_lifecycle_stream_is_not_quarantined_and_restarts_on_schedule(self):
        coordinator = self.coordinator()
        future_start = self.started()
        future_started_at = START + timedelta(minutes=20)
        future_start["maintenance_started_at"] = future_started_at.isoformat()
        event_path = self.root / "maintenance-replay-future-stream.jsonl"
        event_path.write_text(
            "\n".join(
                json.dumps(event)
                for event in (
                    future_start,
                    self.completed(),
                    self.replay_requested(),
                )
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(
            coordinator.consume_event_file(event_path, source_virtual_time=START),
            (3, 0),
        )
        self.assertFalse(coordinator.rejected_event_path.exists())
        self.assertEqual(coordinator.active_equipment_ids, ())
        stream = next(iter(coordinator.pending_event_streams.values()))
        self.assertEqual(
            [event["event_type"] for event in stream],
            [
                "maintenance.started",
                "maintenance.completed",
                "maintenance.replay_requested",
            ],
        )

        for observed_at in (START, START + timedelta(minutes=10)):
            result = self.producer.produce_tick(observed_at)
            coordinator.record_canonical_observations(
                observed_at,
                {record.asset_id for record in result.records},
            )
        coordinator.activate_due_started_events(future_started_at)
        branch = coordinator.branches[
            coordinator.branch_by_equipment[self.target["asset_id"]]
        ]
        self.assertEqual(branch.phase, "restarting")
        self.assertEqual(branch.restart_at, self.restart_at)
        self.assertEqual(branch.runtime.tool_wear_min, 0.0)
        self.assertEqual(coordinator.pending_event_streams, {})

        before_restart, available = coordinator.advance_branch_to(
            self.target["asset_id"],
            self.restart_at - timedelta(minutes=10),
        )
        self.assertEqual(before_restart, [])
        self.assertIsNone(available)
        rows, available = coordinator.advance_branch_to(
            self.target["asset_id"],
            self.restart_at,
        )
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(available)

    def test_runtime_manager_applies_preloaded_future_stream_at_virtual_boundaries(self):
        future_start = self.started()
        future_start["maintenance_started_at"] = (
            START + timedelta(minutes=20)
        ).isoformat()
        event_path = self.root / "maintenance-replay-manager-future.jsonl"
        event_path.write_text(
            "\n".join(
                json.dumps(event)
                for event in (
                    future_start,
                    self.completed(),
                    self.replay_requested(),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        manager = RuntimeManager(
            output_root=self.root,
            mapping_path=MAPPING,
            opcua_endpoint="opc.tcp://127.0.0.1:48501/gen-data/",
            maintenance_event_file=event_path,
        )
        manager.start_run(
            run_id="SOURCE-FUTURE-001",
            simulation_session_id="DEMO-001",
            start_at=START,
            duration_hours=1,
            continuous=False,
            publish_opcua=False,
        )
        try:
            status = {}
            for _ in range(5):
                status = manager.tick("SOURCE-FUTURE-001")
            self.assertEqual(status["source_record_count"], 497)

            source_path = (
                self.root
                / "runs"
                / "SOURCE-FUTURE-001"
                / "source"
                / "sensor_records.jsonl"
            )
            target_rows = [
                json.loads(line)
                for line in source_path.read_text(encoding="utf-8").splitlines()
                if json.loads(line)["asset_id"] == self.target["asset_id"]
            ]
            self.assertEqual(
                [row["observed_at"] for row in target_rows],
                [START.isoformat(), (START + timedelta(minutes=10)).isoformat()],
            )

            outputs = manager.outputs("SOURCE-FUTURE-001")["runtime_overlay"]
            self.assertFalse(Path(outputs["rejected_maintenance_events"]).exists())
            overlay_rows = [
                json.loads(line)
                for line in Path(outputs["branches"][0]).read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            self.assertEqual(len(overlay_rows), 1)
            self.assertEqual(
                overlay_rows[0]["observed_at"],
                self.restart_at.isoformat(),
            )
        finally:
            manager.stop("SOURCE-FUTURE-001")

    def test_pending_stream_replay_and_state_version_conflicts(self):
        coordinator = self.coordinator()
        future_start = self.started()
        future_start["maintenance_started_at"] = (
            START + timedelta(minutes=20)
        ).isoformat()
        first = coordinator.process_event(future_start, source_virtual_time=START)
        replayed_start = coordinator.process_event(
            future_start,
            source_virtual_time=START,
        )
        self.assertFalse(first["replayed"])
        self.assertTrue(replayed_start["replayed"])

        completed = self.completed()
        coordinator.process_event(completed, source_virtual_time=START)
        self.assertTrue(
            coordinator.process_event(
                completed,
                source_virtual_time=START,
            )["replayed"]
        )

        identity_conflict = dict(completed)
        identity_conflict["maintenance_event_id"] = "MAINT-DIFFERENT"
        with self.assertRaises(OverlayConflict):
            coordinator.process_event(
                identity_conflict,
                source_virtual_time=START,
            )

        version_conflict = dict(completed)
        version_conflict["event_id"] = "00000000-0000-5000-8000-000000000202"
        version_conflict["idempotency_key"] = "MAINTENANCE-001:VERSION-CONFLICT"
        with self.assertRaisesRegex(OverlayConflict, "state_version_conflict"):
            coordinator.process_event(
                version_conflict,
                source_virtual_time=START,
            )

        coordinator.process_event(self.replay_requested(), source_virtual_time=START)
        self.assertEqual(len(next(iter(coordinator.pending_event_streams.values()))), 3)

    def test_orphan_followups_are_quarantined_without_blocking_other_equipment(self):
        coordinator = self.coordinator()
        orphan_completed = self.completed()
        orphan_replay = self.replay_requested()
        other_started = self.started()
        other_started.update(
            {
                "event_id": "00000000-0000-5000-8000-000000000301",
                "idempotency_key": "MAINTENANCE-OTHER:1",
                "maintenance_action_id": "ACTION-OTHER",
                "work_order_id": "WO-OTHER",
                "equipment_id": self.other["asset_id"],
            }
        )
        event_path = self.root / "maintenance-replay-orphans.jsonl"
        event_path.write_text(
            "\n".join(
                json.dumps(event)
                for event in (orphan_completed, orphan_replay, other_started)
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(
            coordinator.consume_event_file(event_path, source_virtual_time=START),
            (1, 2),
        )
        self.assertEqual(coordinator.active_equipment_ids, (self.other["asset_id"],))
        rejected = [
            json.loads(line)
            for line in coordinator.rejected_event_path.read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        self.assertEqual(len(rejected), 2)
        self.assertTrue(
            all("maintenance.started branch not found" in row["reason"] for row in rejected)
        )

    def test_late_start_is_quarantined_once_and_never_activates(self):
        coordinator = self.coordinator()
        result = self.producer.produce_tick(START)
        coordinator.record_canonical_observations(
            START,
            {record.asset_id for record in result.records},
        )
        event_path = self.root / "maintenance-replay-late.jsonl"
        event_path.write_text(json.dumps(self.started()) + "\n", encoding="utf-8")

        self.assertEqual(
            coordinator.consume_event_file(
                event_path,
                source_virtual_time=START + timedelta(minutes=10),
            ),
            (0, 1),
        )
        self.assertEqual(coordinator.active_equipment_ids, ())
        self.assertEqual(
            coordinator.consume_event_file(
                event_path,
                source_virtual_time=START + timedelta(minutes=10),
            ),
            (0, 0),
        )
        rejected = coordinator.rejected_event_path.read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(len(rejected), 1)
        self.assertEqual(json.loads(rejected[0])["reason_type"], "LateOverlayEvent")

    def test_stored_observation_payload_must_match_declared_checksum(self):
        coordinator = self.coordinator()
        self.prepare_branch(coordinator)
        rows, _available = coordinator.advance_branch_to(
            self.target["asset_id"],
            self.restart_at,
        )
        self.assertEqual(len(rows), 1)
        branch = coordinator.branches[
            coordinator.branch_by_equipment[self.target["asset_id"]]
        ]
        observation_path = coordinator.store.path_for(branch)
        tampered = json.loads(observation_path.read_text(encoding="utf-8"))
        tampered["tool_wear_min"] = 999.0
        observation_path.write_text(
            json.dumps(tampered, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        stored_line_count = len(
            observation_path.read_text(encoding="utf-8").splitlines()
        )

        resumed = self.coordinator(producer())
        with self.assertRaisesRegex(OverlayConflict, "checksum mismatch"):
            resumed.advance_branch_to(
                self.target["asset_id"],
                self.restart_at + timedelta(minutes=10),
            )
        self.assertEqual(
            len(observation_path.read_text(encoding="utf-8").splitlines()),
            stored_line_count,
        )

    def test_poison_line_is_quarantined_without_blocking_later_valid_event(self):
        event_path = self.root / "maintenance-replay-poison.jsonl"
        event_path.write_text(
            "{not-valid-json}\n" + json.dumps(self.started()) + "\n",
            encoding="utf-8",
        )
        manager = RuntimeManager(
            output_root=self.root,
            mapping_path=MAPPING,
            opcua_endpoint="opc.tcp://127.0.0.1:48501/gen-data/",
            maintenance_event_file=event_path,
        )
        manager.start_run(
            run_id="DEMO-001",
            start_at=START,
            duration_hours=1,
            continuous=False,
            publish_opcua=False,
        )
        rejected_path: Path | None = None
        try:
            first = manager.tick("DEMO-001")
            self.assertEqual(first["source_record_count"], 99)
            self.assertEqual(first["status"], "partial_failure")
            outputs = manager.outputs("DEMO-001")
            self.assertEqual(
                outputs["runtime_overlay"]["active_equipment_ids"],
                [self.target["asset_id"]],
            )
            rejected_path = Path(
                outputs["runtime_overlay"]["rejected_maintenance_events"]
            )
            self.assertEqual(
                len(rejected_path.read_text(encoding="utf-8").splitlines()),
                1,
            )

            second = manager.tick("DEMO-001")
            self.assertEqual(second["source_record_count"], 198)
            self.assertEqual(
                len(rejected_path.read_text(encoding="utf-8").splitlines()),
                1,
            )
            manifest = json.loads(
                (self.root / "runs" / "DEMO-001" / "run_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            overlay_failures = [
                failure
                for failure in manifest["partial_failures"]
                if failure["stage"] == "runtime_overlay_event"
            ]
            self.assertEqual(len(overlay_failures), 1)
        finally:
            manager.stop("DEMO-001")
        self.assertIsNotNone(rejected_path)
        resumed = self.coordinator(producer())
        self.assertEqual(
            resumed.consume_event_file(
                event_path,
                source_virtual_time=START + timedelta(minutes=20),
            ),
            (0, 0),
        )
        self.assertEqual(
            len(rejected_path.read_text(encoding="utf-8").splitlines()),
            1,
        )

    def test_runtime_manager_consumes_backend_jsonl_and_keeps_target_out_of_canonical(self):
        event_path = self.root / "maintenance-replay.jsonl"
        event_path.write_text(
            "\n".join(
                json.dumps(event, sort_keys=True)
                for event in (
                    self.started(),
                    self.completed(),
                    self.replay_requested(),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        manager = RuntimeManager(
            output_root=self.root,
            mapping_path=MAPPING,
            opcua_endpoint="opc.tcp://127.0.0.1:48501/gen-data/",
            maintenance_event_file=event_path,
        )
        started = manager.start_run(
            run_id="SOURCE-RUN-001",
            simulation_session_id="DEMO-001",
            start_at=START,
            duration_hours=2,
            continuous=False,
            publish_opcua=False,
        )
        self.assertEqual(started["run_id"], "SOURCE-RUN-001")
        self.assertEqual(started["simulation_session_id"], "DEMO-001")

        try:
            for _ in range(4):
                manager.tick("SOURCE-RUN-001")
            status = manager.tick("SOURCE-RUN-001")

            self.assertEqual(status["source_record_count"], 495)
            self.assertEqual(status["canonical_observation_count"], 495)
            source_path = (
                self.root
                / "runs"
                / "SOURCE-RUN-001"
                / "source"
                / "sensor_records.jsonl"
            )
            source_rows = [
                json.loads(line)
                for line in source_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertNotIn(
                self.target["asset_id"],
                {row["asset_id"] for row in source_rows},
            )

            overlay_path = (
                self.root
                / "runtime_overlay"
                / (
                    _storage_path_component("DEMO-001", "MAINT-001:post")
                    + ".jsonl"
                )
            )
            overlay_rows = [
                json.loads(line)
                for line in overlay_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(overlay_rows), 1)
            self.assertEqual(
                overlay_rows[0]["observed_at"], self.restart_at.isoformat()
            )
            available_path = (
                self.root / "runtime_overlay" / "observations_available.jsonl"
            )
            self.assertEqual(
                len(available_path.read_text(encoding="utf-8").splitlines()),
                1,
            )
        finally:
            manager.stop("SOURCE-RUN-001")

    def test_runtime_manager_consumes_cooling_restore_jsonl(self):
        event_path = self.root / "maintenance-replay-cooling.jsonl"
        event_path.write_text(
            "\n".join(
                json.dumps(event, sort_keys=True)
                for event in (
                    self.cooling_started(),
                    self.cooling_completed(),
                    self.cooling_replay_requested(),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        manager = RuntimeManager(
            output_root=self.root,
            mapping_path=MAPPING,
            opcua_endpoint="opc.tcp://127.0.0.1:48501/gen-data/",
            maintenance_event_file=event_path,
        )
        manager.start_run(
            run_id="SOURCE-RUN-001",
            simulation_session_id="DEMO-001",
            start_at=START,
            duration_hours=2,
            continuous=False,
            publish_opcua=False,
        )

        try:
            for _ in range(5):
                manager.tick("SOURCE-RUN-001")

            overlay_path = (
                self.root
                / "runtime_overlay"
                / (
                    _storage_path_component(
                        "DEMO-001", "MAINT-COOLING-001:post"
                    )
                    + ".jsonl"
                )
            )
            overlay_rows = [
                json.loads(line)
                for line in overlay_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(overlay_rows), 1)
            row = overlay_rows[0]
            self.assertEqual(row["maintenance_event_id"], "MAINT-COOLING-001")
            self.assertGreaterEqual(
                row["process_temperature_k"] - row["air_temperature_k"],
                8.89,
            )

            source_path = (
                self.root
                / "runs"
                / "SOURCE-RUN-001"
                / "source"
                / "sensor_records.jsonl"
            )
            source_rows = [
                json.loads(line)
                for line in source_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertNotIn(
                self.target["asset_id"],
                {source_row["asset_id"] for source_row in source_rows},
            )
        finally:
            manager.stop("SOURCE-RUN-001")

    def test_invalid_overlay_event_does_not_stop_unrelated_source_records(self):
        invalid = self.started()
        invalid["prediction_ready"] = True
        event_path = self.root / "maintenance-replay-invalid.jsonl"
        event_path.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
        manager = RuntimeManager(
            output_root=self.root,
            mapping_path=MAPPING,
            opcua_endpoint="opc.tcp://127.0.0.1:48501/gen-data/",
            maintenance_event_file=event_path,
        )
        manager.start_run(
            run_id="DEMO-001",
            start_at=START,
            duration_hours=1,
            continuous=False,
            publish_opcua=False,
        )
        try:
            status = manager.tick("DEMO-001")
            self.assertEqual(status["source_record_count"], 100)
            self.assertEqual(status["canonical_observation_count"], 100)
            self.assertEqual(status["status"], "partial_failure")
            manifest = json.loads(
                (self.root / "runs" / "DEMO-001" / "run_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                manifest["partial_failures"][0]["stage"],
                "runtime_overlay_event",
            )
        finally:
            manager.stop("DEMO-001")


if __name__ == "__main__":
    unittest.main()
