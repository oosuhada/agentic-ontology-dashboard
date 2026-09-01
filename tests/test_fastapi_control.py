import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.main import create_app
from app.runtime.manager import RuntimeManager


class FastApiControlTest(unittest.TestCase):
    def test_control_api_start_tick_status_outputs_stop_and_health(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = RuntimeManager(
                output_root=Path(temporary),
                mapping_path=Path("mappings/opcua_nodes.v1.json"),
                opcua_endpoint="opc.tcp://127.0.0.1:48502/gen-data/",
            )
            with TestClient(create_app(manager)) as client:
                self.assertEqual(client.get("/health/live").status_code, 200)
                self.assertEqual(client.get("/health/ready").json(), {"status": "ready"})
                response = client.post(
                    "/api/runs",
                    json={
                        "run_id": "api-run",
                        "start_at": "2026-08-01T00:00:00+00:00",
                        "duration_hours": 1,
                        "continuous": False,
                        "publish_opcua": False,
                    },
                )
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.json()["status"], "running")
                tick = client.post("/api/runs/api-run/tick")
                self.assertEqual(tick.status_code, 200)
                self.assertEqual(tick.json()["last_sequence"], 100)
                self.assertEqual(client.get("/api/runs/api-run").json()["source_record_count"], 100)
                outputs = client.get("/api/runs/api-run/outputs").json()
                self.assertEqual(outputs["counts"]["canonical_observations"], 100)
                stopped = client.post("/api/runs/api-run/stop")
                self.assertEqual(stopped.json()["status"], "stopped")

    def test_start_run_records_run_level_overlay_acceleration_setting(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = RuntimeManager(
                output_root=Path(temporary),
                mapping_path=Path("mappings/opcua_nodes.v1.json"),
                opcua_endpoint="opc.tcp://127.0.0.1:48502/gen-data/",
                runtime_overlay_fast_forward_rows=36,
            )
            with TestClient(create_app(manager)) as client:
                response = client.post(
                    "/api/runs",
                    json={
                        "run_id": "api-run-setting",
                        "start_at": "2026-08-01T00:00:00+00:00",
                        "duration_hours": 1,
                        "continuous": False,
                        "publish_opcua": False,
                        "runtime_overlay_fast_forward_rows": 12,
                    },
                )
                self.assertEqual(response.status_code, 201)
                outputs = client.get("/api/runs/api-run-setting/outputs").json()
                manifest = json.loads(
                    Path(outputs["run_manifest"]).read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["runtime_overlay_fast_forward_rows"], 12)
                client.post("/api/runs/api-run-setting/stop")

    def test_start_run_rejects_overlay_acceleration_above_contract_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = RuntimeManager(
                output_root=Path(temporary),
                mapping_path=Path("mappings/opcua_nodes.v1.json"),
                opcua_endpoint="opc.tcp://127.0.0.1:48502/gen-data/",
            )
            with TestClient(create_app(manager)) as client:
                response = client.post(
                    "/api/runs",
                    json={
                        "run_id": "api-run-invalid-setting",
                        "continuous": False,
                        "publish_opcua": False,
                        "runtime_overlay_fast_forward_rows": 10_001,
                    },
                )
                self.assertEqual(response.status_code, 422)

    def test_overlay_fast_forward_rejects_missing_branch(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = RuntimeManager(
                output_root=Path(temporary),
                mapping_path=Path("mappings/opcua_nodes.v1.json"),
                opcua_endpoint="opc.tcp://127.0.0.1:48502/gen-data/",
            )
            with TestClient(create_app(manager)) as client:
                client.post(
                    "/api/runs",
                    json={
                        "run_id": "api-overlay-run",
                        "start_at": "2026-08-01T00:00:00+00:00",
                        "duration_hours": 8,
                        "continuous": False,
                        "publish_opcua": False,
                    },
                )
                response = client.post(
                    "/api/runs/api-overlay-run/runtime-overlay/fast-forward",
                    json={
                        "equipment_id": "CNC-S01-L04-03",
                        "target_generated_rows": 36,
                    },
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("no overlay branch", response.json()["detail"])
