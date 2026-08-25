"""Single calculation boundary for the existing Canonical V3.1 physics."""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.observation.models import SENSOR_RECORD_SCHEMA_VERSION, SensorRecord
from physics_engine import (
    COMPRESSOR_BASELINE,
    GENERATOR_VERSION,
    PRODUCT_CUTTING_MINUTES,
    TOOL_WEAR_EXPOSURE_FACTOR,
    Runtime,
    active_cnc_episode,
    ar_noise,
    build_episodes,
    build_schedule,
    build_topology,
    choose_product,
    clamp,
    coupled_cnc_values,
    make_baseline,
    operating_state,
    sensor_effects,
    stable_seed,
    vibration_zone,
)


@dataclass
class TickResult:
    records: list[SensorRecord] = field(default_factory=list)
    production_events: list[dict[str, object]] = field(default_factory=list)
    maintenance_events: list[dict[str, object]] = field(default_factory=list)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


class SimulationProducer:
    """Calculate each sensor value once and yield SensorRecord instances.

    Runtime state transitions intentionally mirror the historical canonical
    generator. Writers and protocol publishers are not allowed to invoke
    physics functions; they only consume the records returned here.
    """

    def __init__(
        self,
        *,
        run_id: str,
        start_at: datetime,
        end_at: datetime,
        interval_minutes: int,
        product_cycle_minutes: int,
        seed: int,
        rate_profile: str = "balanced_demo",
        initial_sequence: int = 0,
    ) -> None:
        if start_at.tzinfo is None or end_at.tzinfo is None:
            raise ValueError("start_at and end_at must be timezone-aware")
        if interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")
        if product_cycle_minutes % interval_minutes:
            raise ValueError("product cycle must be a multiple of observation interval")
        if initial_sequence < 0:
            raise ValueError("initial_sequence must not be negative")
        self.run_id = run_id
        self.start_at = start_at
        self.end_at = end_at
        self.interval_minutes = interval_minutes
        self.product_cycle_minutes = product_cycle_minutes
        self.seed = seed
        self.rate_profile = rate_profile
        self.assets, self.relations = build_topology()
        self.schedule = build_schedule(self.assets, seed, rate_profile)
        self.episodes = build_episodes(
            self.schedule,
            start_at,
            end_at,
            observation_interval_minutes=interval_minutes,
        )
        self.episodes_by_asset: dict[str, list] = defaultdict(list)
        for episode in self.episodes:
            self.episodes_by_asset[str(episode.issue["asset_id"])].append(episode)
        self.runtimes = {
            asset["asset_id"]: Runtime(
                asset=asset,
                rng=random.Random(stable_seed(seed, asset["asset_id"], "runtime")),
                baseline=make_baseline(asset, seed),
                tool_change_threshold_min=random.Random(
                    stable_seed(seed, asset["asset_id"], "tool-threshold")
                ).uniform(180, 235),
            )
            for asset in self.assets
        }
        self._sequence = initial_sequence
        self._written_failures: set[str] = set()

    @property
    def sequence(self) -> int:
        return self._sequence

    def produce_tick(
        self,
        observed_at: datetime,
        *,
        included_asset_ids: set[str] | None = None,
        excluded_asset_ids: set[str] | None = None,
    ) -> TickResult:
        if observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if included_asset_ids is not None and excluded_asset_ids is not None:
            raise ValueError("included_asset_ids and excluded_asset_ids are mutually exclusive")
        known_asset_ids = {str(asset["asset_id"]) for asset in self.assets}
        selected_asset_ids = included_asset_ids or excluded_asset_ids or set()
        unknown_asset_ids = sorted(selected_asset_ids - known_asset_ids)
        if unknown_asset_ids:
            raise ValueError(
                "unknown asset_id(s): " + ", ".join(unknown_asset_ids)
            )
        result = TickResult()
        tick = timedelta(minutes=self.interval_minutes)
        product_ticks = self.product_cycle_minutes // self.interval_minutes

        for asset in self.assets:
            asset_id = str(asset["asset_id"])
            if included_asset_ids is not None and asset_id not in included_asset_ids:
                continue
            if excluded_asset_ids is not None and asset_id in excluded_asset_ids:
                continue
            runtime = self.runtimes[asset["asset_id"]]
            asset_episodes = self.episodes_by_asset[asset["asset_id"]]
            if runtime.tool_reset_at and observed_at >= runtime.tool_reset_at:
                runtime.tool_wear_min = runtime.rng.uniform(0.0, 4.0)
                runtime.tool_reset_at = None
            is_operating, state = operating_state(asset_episodes, observed_at)
            if runtime.planned_maintenance_until and observed_at < runtime.planned_maintenance_until:
                is_operating, state = 0, "maintenance"
            effects = sensor_effects(asset_episodes, observed_at)

            for episode in asset_episodes:
                if episode.event_id in self._written_failures:
                    continue
                if observed_at <= episode.failure_at < observed_at + tick:
                    tool_replaced = int(
                        asset["asset_type"] == "cnc"
                        and episode.issue["component"] in {"TWF", "OSF"}
                    )
                    result.maintenance_events.append(
                        {
                            "maintenance_id": f"MNT-{episode.event_id}",
                            "asset_id": asset["asset_id"],
                            "maintenance_type": "failure_recovery",
                            "started_at": _iso(episode.maintenance_started_at),
                            "completed_at": _iso(episode.maintenance_completed_at),
                            "tool_replaced": tool_replaced,
                            "source_event_id": episode.event_id,
                        }
                    )
                    if tool_replaced:
                        runtime.tool_reset_at = episode.maintenance_started_at
                    self._written_failures.add(episode.event_id)

            if asset["asset_type"] == "compressor":
                values: dict[str, float] = {}
                for sensor, (_mean, std) in COMPRESSOR_BASELINE.items():
                    base = runtime.baseline[sensor]
                    values[sensor] = (
                        base + ar_noise(runtime, sensor, std) + base * effects.get(sensor, 0.0)
                    )
                vibration_z = (
                    values["vibration_raw"] - runtime.baseline["vibration_raw"]
                ) / COMPRESSOR_BASELINE["vibration_raw"][1]
                measurements: dict[str, object] = {
                    "is_operating": int(is_operating),
                    "operating_state": state,
                    "voltage_raw": round(values["voltage_raw"], 4),
                    "rotation_raw": round(values["rotation_raw"], 4),
                    "pressure_raw": round(values["pressure_raw"], 4),
                    "vibration_raw": round(values["vibration_raw"], 4),
                    "relative_vibration_z": round(vibration_z, 4),
                    "relative_vibration_zone": vibration_zone(vibration_z),
                }
                result.records.append(self._record(asset, observed_at, measurements))
                continue

            if runtime.product_started_at is None:
                runtime.product_started_at = observed_at
                runtime.product_type = choose_product(runtime)

            active_episode, active_ramp = active_cnc_episode(asset_episodes, observed_at)
            protected_failure_window = bool(
                active_episode and str(active_episode.issue["component"]) in {"TWF", "OSF"}
            )
            if active_episode and protected_failure_window:
                signal_strength = float(active_episode.issue["signal_strength"])
                physical_ramp = clamp(
                    active_ramp * (0.55 + 0.45 * signal_strength), 0.0, 1.0
                )
                if active_ramp >= 0.999:
                    physical_ramp = 1.0
                if str(active_episode.issue["component"]) == "TWF":
                    runtime.tool_wear_min = max(
                        runtime.tool_wear_min, 180.0 + 40.0 * physical_ramp
                    )
                    if active_ramp >= 0.999:
                        runtime.tool_wear_min = max(runtime.tool_wear_min, 220.0)
                else:
                    runtime.tool_wear_min = max(
                        runtime.tool_wear_min, 185.0 + 40.0 * physical_ramp
                    )
                    if active_ramp >= 0.999:
                        runtime.tool_wear_min = max(runtime.tool_wear_min, 225.0)

            values = coupled_cnc_values(runtime, asset_episodes, observed_at)
            if is_operating:
                runtime.product_ticks += 1

            if is_operating and runtime.product_ticks >= product_ticks:
                cutting_min, cutting_max = PRODUCT_CUTTING_MINUTES[runtime.product_type]
                cutting_minutes = runtime.rng.uniform(cutting_min, cutting_max)
                wear_increment = cutting_minutes * TOOL_WEAR_EXPOSURE_FACTOR
                runtime.tool_wear_min += wear_increment
                if active_episode and str(active_episode.issue["component"]) == "TWF":
                    runtime.tool_wear_min = min(runtime.tool_wear_min, 220.0)
                runtime.product_counter += 1
                result.production_events.append(
                    {
                        "product_id": f"PRD-{asset['asset_id']}-{runtime.product_counter:07d}",
                        "cnc_asset_id": asset["asset_id"],
                        "cycle_started_at": _iso(runtime.product_started_at),
                        "cycle_completed_at": _iso(observed_at + tick),
                        "product_type": runtime.product_type,
                        "cutting_minutes": round(cutting_minutes, 4),
                        "tool_wear_increment_min": round(wear_increment, 4),
                    }
                )
                runtime.product_started_at = observed_at + tick
                runtime.product_ticks = 0
                runtime.product_type = choose_product(runtime)
                if (
                    runtime.tool_wear_min >= runtime.tool_change_threshold_min
                    and not protected_failure_window
                ):
                    completed_at = observed_at + tick + timedelta(minutes=30)
                    result.maintenance_events.append(
                        {
                            "maintenance_id": (
                                f"MNT-TOOL-{asset['asset_id']}-{runtime.product_counter:07d}"
                            ),
                            "asset_id": asset["asset_id"],
                            "maintenance_type": "planned_tool_change",
                            "started_at": _iso(observed_at + tick),
                            "completed_at": _iso(completed_at),
                            "tool_replaced": 1,
                            "source_event_id": "",
                        }
                    )
                    runtime.tool_reset_at = observed_at + tick
                    runtime.tool_change_threshold_min = runtime.rng.uniform(180.0, 235.0)
                    runtime.planned_maintenance_until = completed_at

            measurements = {
                "is_operating": int(is_operating),
                "operating_state": state,
                "product_type": runtime.product_type,
                "air_temperature_k": round(values["air_temperature_k"], 4),
                "process_temperature_k": round(values["process_temperature_k"], 4),
                "rotational_speed_rpm": round(values["rotational_speed_rpm"], 4),
                "torque_nm": round(values["torque_nm"], 4),
                "tool_wear_min": round(runtime.tool_wear_min, 4),
            }
            result.records.append(self._record(asset, observed_at, measurements))

        return result

    def _record(
        self,
        asset: dict[str, str],
        observed_at: datetime,
        measurements: dict[str, object],
    ) -> SensorRecord:
        self._sequence += 1
        return SensorRecord(
            schema_version=SENSOR_RECORD_SCHEMA_VERSION,
            run_id=self.run_id,
            sequence=self._sequence,
            asset_id=asset["asset_id"],
            observed_at=observed_at,
            measurements=measurements,
            generator_version=GENERATOR_VERSION,
            asset_type=asset["asset_type"],
            site_id=asset["site_id"],
            cell_id=asset["cell_id"],
        )
