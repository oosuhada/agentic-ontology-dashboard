import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.runtime.manager import RuntimeManager


START = datetime(2026, 8, 1, tzinfo=timezone.utc)
MAPPING = Path("mappings/opcua_nodes.v1.json")


def manager(tmp_path: Path) -> RuntimeManager:
    return RuntimeManager(
        output_root=tmp_path,
        mapping_path=MAPPING,
        opcua_endpoint="opc.tcp://127.0.0.1:48501/gen-data/",
    )


class RuntimeManagerTest(unittest.TestCase):
    def test_simulation_fast_forward_processes_every_global_tick(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            runtime = manager(tmp_path)
            runtime.start_run(
                run_id="global-fast-forward",
                start_at=START,
                duration_hours=8,
                interval_minutes=10,
                continuous=False,
                publish_opcua=False,
            )

            result = runtime.fast_forward_simulation(
                "global-fast-forward",
                target_elapsed_hours=2,
            )

            self.assertTrue(result["global_clock_advanced"])
            self.assertEqual(result["ticks_processed"], 12)
            self.assertEqual(result["generated_records"], 1_200)
            self.assertEqual(result["current_observed_at"], "2026-08-01T02:00:00+00:00")
            status = runtime.status("global-fast-forward")
            self.assertEqual(status["source_record_count"], 1_200)
            self.assertEqual(status["canonical_observation_count"], 1_200)
            runtime.stop("global-fast-forward")

    def test_simulation_fast_forward_rejects_backward_or_terminal_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = manager(Path(temporary))
            runtime.start_run(
                run_id="bounded-fast-forward",
                start_at=START,
                duration_hours=4,
                continuous=False,
                publish_opcua=False,
            )
            runtime.fast_forward_simulation(
                "bounded-fast-forward",
                target_elapsed_hours=2,
            )
            with self.assertRaisesRegex(ValueError, "later than the current"):
                runtime.fast_forward_simulation(
                    "bounded-fast-forward",
                    target_elapsed_hours=1,
                )
            with self.assertRaisesRegex(ValueError, "before the run end"):
                runtime.fast_forward_simulation(
                    "bounded-fast-forward",
                    target_elapsed_hours=4,
                )
            runtime.stop("bounded-fast-forward")

    def test_manual_tick_reuses_same_sensor_record_for_source_and_canonical(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            runtime = manager(tmp_path)
            runtime.start_run(
                run_id="manual",
                start_at=START,
                duration_hours=1,
                continuous=False,
                publish_opcua=False,
            )
            status = runtime.tick("manual")
            self.assertEqual(status["last_sequence"], 100)
            self.assertEqual(status["source_record_count"], 100)
            self.assertEqual(status["canonical_observation_count"], 100)
            source_path = tmp_path / "runs" / "manual" / "source" / "sensor_records.jsonl"
            source_first = json.loads(source_path.read_text(encoding="utf-8").splitlines()[0])
            canonical_path = (
                tmp_path / "runs" / "manual" / "canonical" / "compressor_sensor_observation.csv"
            )
            with canonical_path.open(encoding="utf-8", newline="") as handle:
                canonical_first = next(csv.DictReader(handle))
            self.assertEqual(source_first["asset_id"], canonical_first["asset_id"])
            self.assertEqual(source_first["record_kind"], "full_observation")
            self.assertEqual(source_first["quality"], "good")
            self.assertEqual(source_first["observed_at"], canonical_first["observed_at"])
            self.assertEqual(
                str(source_first["measurements"]["voltage_raw"]),
                canonical_first["voltage_raw"],
            )
            stopped = runtime.stop("manual")
            self.assertEqual(stopped["status"], "stopped")
            manifest = json.loads(
                (tmp_path / "runs" / "manual" / "run_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["source_record_count"], 100)
            self.assertEqual(manifest["canonical_observation_count"], 100)
            self.assertEqual(manifest["protocol_datavalue_count"], 0)

    def test_equipment_state_returns_latest_canonical_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = manager(Path(temporary))
            runtime.start_run(
                run_id="equipment-state",
                start_at=START,
                duration_hours=1,
                continuous=False,
                publish_opcua=False,
            )
            runtime.tick("equipment-state")
            state = runtime.equipment_state(
                "equipment-state", "CNC-S01-L01-01"
            )
            self.assertEqual(state["operational_state"], "RUNNING")
            self.assertFalse(state["held"])
            self.assertTrue(state["usable_for_prediction"])
            self.assertEqual(
                state["current_observation"]["asset_id"], "CNC-S01-L01-01"
            )
            runtime.stop("equipment-state")

    def test_protocol_start_failure_does_not_remove_source_or_canonical(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            runtime = manager(tmp_path)
            with patch("app.runtime.manager.OpcUaPublisher.start", side_effect=RuntimeError("offline")):
                started = runtime.start_run(
                    run_id="protocol-failure",
                    start_at=START,
                    duration_hours=1,
                    continuous=False,
                    publish_opcua=True,
                )
            self.assertEqual(started["partial_failure_count"], 1)
            status = runtime.tick("protocol-failure")
            self.assertEqual(status["source_record_count"], 100)
            self.assertEqual(status["canonical_observation_count"], 100)
            self.assertEqual(status["protocol_datavalue_count"], 0)
            self.assertEqual(status["status"], "partial_failure")
            runtime.stop("protocol-failure")
