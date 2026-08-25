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
)
from app.simulation.producer import SimulationProducer


START = datetime(2026, 8, 18, 1, 0, tzinfo=timezone.utc)
MAPPING = Path("mappings/opcua_nodes.v1.json")


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
        self.assertEqual(available["batch_rows"], 3)
        self.assertNotIn("required_rows", available)

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
                / "DEMO-001"
                / "MAINT-001_post.jsonl"
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
