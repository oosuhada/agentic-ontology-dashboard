"""JSON-backed adapter for versioned Maintenance cost reference inputs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.maintenance.cost_analysis_schema import ExecutionTiming
from app.maintenance.cost_basis import (
    CoolingSystemRestoreCostBasis,
    CostBasisResolutionContext,
    ToolReplacementCostBasis,
)


def _money(value: int | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {"low_minor": value, "base_minor": value, "high_minor": value}


def _duration(value: int | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {"low_minutes": value, "base_minutes": value, "high_minutes": value}


def _rate(value: int | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {
        "low_minor_per_minute": value,
        "base_minor_per_minute": value,
        "high_minor_per_minute": value,
    }


def _money_band(value: dict[str, int] | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {
        "low_minor": int(value["low"]),
        "base_minor": int(value["base"]),
        "high_minor": int(value["high"]),
    }


def _duration_band(value: dict[str, int] | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {
        "low_minutes": int(value["low"]),
        "base_minutes": int(value["base"]),
        "high_minutes": int(value["high"]),
    }


def _rate_band(value: dict[str, int] | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {
        "low_minor_per_minute": int(value["low"]),
        "base_minor_per_minute": int(value["base"]),
        "high_minor_per_minute": int(value["high"]),
    }


def _expected_loss(
    consequence: dict[str, int], probability_source: dict[str, Any] | None
) -> dict[str, int] | None:
    """Derive expected loss without creating or interpolating a Prediction value."""

    if probability_source is None:
        return None
    probability = Decimal(str(probability_source["failure_probability"]))

    def expected(band: str) -> int:
        return int(
            (Decimal(int(consequence[band])) * probability).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )

    return {
        "low_minor": expected("low"),
        "base_minor": expected("base"),
        "high_minor": expected("high"),
    }


class JsonMaintenanceCostBasisProvider:
    """Load immutable Action-specific cost documents into calculator inputs."""

    def __init__(
        self,
        tool_replacement_path: str | Path,
        cooling_system_restore_path: str | Path | None = None,
    ) -> None:
        self.tool_replacement_path = Path(tool_replacement_path)
        self.cooling_system_restore_path = (
            Path(cooling_system_restore_path)
            if cooling_system_restore_path is not None
            else None
        )

    @staticmethod
    def _read_document(path: Path, *, action_code: str) -> dict[str, Any]:
        document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if document.get("action_code") != action_code:
            raise ValueError(f"cost basis action_code must be {action_code}")
        return document

    @staticmethod
    def _require_applicable(
        *,
        document: dict[str, Any],
        context: CostBasisResolutionContext,
    ) -> None:
        requirements = document.get("applicability")
        if not isinstance(requirements, dict) or not requirements:
            raise ValueError("cost basis must declare typed applicability requirements")
        actual = context.model_dump()
        reasons = [
            (
                f"missing_{name}"
                if actual.get(name) is None
                else f"{name}_mismatch"
            )
            for name, expected in requirements.items()
            if actual.get(name) != expected
        ]
        if reasons:
            raise ValueError(
                f"{document.get('action_code')} cost basis is not applicable: "
                + ", ".join(reasons)
            )

    @staticmethod
    def _execution_rate(
        *,
        assumed_execution_at: datetime,
        execution_policy: dict[str, Any],
        normal_labor_rate: int,
        night_labor_rate: int,
    ) -> tuple[str, int]:
        execution_timezone = ZoneInfo(execution_policy["timezone"])
        night_start_hour = int(execution_policy["night_window"]["start_hour"])
        night_end_hour = int(execution_policy["night_window"]["end_hour"])
        local_hour = assumed_execution_at.astimezone(execution_timezone).hour
        is_night = local_hour >= night_start_hour or local_hour < night_end_hour
        return (
            ("night", night_labor_rate)
            if is_night
            else ("normal", normal_labor_rate)
        )

    def tool_replacement_basis(
        self,
        *,
        calculated_at: datetime,
        context: CostBasisResolutionContext,
    ) -> ToolReplacementCostBasis:
        if calculated_at.tzinfo is None or calculated_at.utcoffset() is None:
            raise ValueError("calculated_at must include a timezone offset")
        document = self._read_document(
            self.tool_replacement_path,
            action_code="TOOL_REPLACEMENT",
        )
        self._require_applicable(document=document, context=context)
        scope = document.get("replacement_scope", {})
        if scope.get("quantity") != 1 or scope.get("unit") != "piece":
            raise ValueError("TOOL_REPLACEMENT cost basis must describe exactly one insert")

        policy = document["demo_policy_inputs"]
        execution_policy = document["execution_time_policy"]
        planned_delay = timedelta(
            hours=int(execution_policy["planned_window_delay_hours"])
        )
        parts_reference = int(document["parts_cost"]["reference_minor"])
        labor_rates = document["labor_rate_per_minute"]
        normal_labor_rate = int(labor_rates["normal_minor"])
        night_labor_rate = int(labor_rates["night_minor"])
        if int(execution_policy["normal_rate_minor_per_minute"]) != normal_labor_rate:
            raise ValueError("execution policy normal rate must match labor basis")
        if int(execution_policy["night_rate_minor_per_minute"]) != night_labor_rate:
            raise ValueError("execution policy night rate must match labor basis")
        labor_duration = policy["labor_duration_minutes"]["sensitivity"]
        external_service_cost = policy["external_service_cost_minor"]["sensitivity"]
        expected_downtime = policy["expected_downtime_minutes"]["sensitivity"]
        production_loss_rate = policy["production_loss_rate_minor_per_minute"][
            "sensitivity"
        ]
        failure_consequence = policy["failure_consequence_cost_minor"]["sensitivity"]
        scenario_probabilities = policy["expected_failure_loss_minor"][
            "scenario_probabilities"
        ]
        scenarios = []
        for timing in ExecutionTiming:
            incurs_replacement = timing in {
                ExecutionTiming.IMMEDIATE,
                ExecutionTiming.PLANNED_WINDOW,
            }
            is_reinspection = timing is ExecutionTiming.REINSPECT_AFTER
            is_no_action = timing is ExecutionTiming.NO_ACTION_BASELINE
            assumed_execution_at = None
            labor_rate_type = "not_applicable"
            labor_rate = 0
            if timing is ExecutionTiming.IMMEDIATE:
                assumed_execution_at = calculated_at
            elif timing is ExecutionTiming.PLANNED_WINDOW:
                assumed_execution_at = calculated_at + planned_delay
            if assumed_execution_at is not None:
                labor_rate_type, labor_rate = self._execution_rate(
                    assumed_execution_at=assumed_execution_at,
                    execution_policy=execution_policy,
                    normal_labor_rate=normal_labor_rate,
                    night_labor_rate=night_labor_rate,
                )
            scenarios.append(
                {
                    "execution_timing": timing,
                    "assumed_execution_at": assumed_execution_at,
                    "labor_rate_type": labor_rate_type,
                    "parts_cost": _money(parts_reference if incurs_replacement else 0),
                    "labor_duration": (
                        _duration(0)
                        if is_no_action
                        else None
                        if is_reinspection
                        else _duration_band(labor_duration)
                    ),
                    "labor_rate_per_minute": _rate(labor_rate),
                    "external_service_cost": _money_band(external_service_cost),
                    "expected_downtime": (
                        _duration(0)
                        if is_no_action
                        else None
                        if is_reinspection
                        else _duration_band(expected_downtime)
                    ),
                    "production_loss_rate_per_minute": (
                        _rate(0) if is_no_action else _rate_band(production_loss_rate)
                    ),
                    "expected_failure_loss": _expected_loss(
                        failure_consequence,
                        scenario_probabilities[timing.value],
                    ),
                    "confidence": "low",
                }
            )

        reference = "data/fixtures/maintenance_cost/tool-insert-cost-basis-v1.json"
        return ToolReplacementCostBasis(
            currency=document["currency"],
            currency_minor_unit=document["currency_minor_unit"],
            scenarios=tuple(scenarios),
            assumptions=(
                "부품비와 노무단가는 공개 참고자료이며 실제 사업장 견적·급여가 아니다.",
                "즉시·12시간 후 비용 산정 가정 시각은 서버 시각에서 계산하고 Asia/Seoul 22:00~06:00에는 단일 50% 야간 가산 데모 요율을 적용한다. 실제 WorkOrder 일정이 아니다.",
                "438원/분은 현재 인건비 기준에 야간 가산을 적용한 운영 참고값이며 최종 비용은 통상임금·연장/휴일 중복 가산과 사업장 실적으로 재검증한다.",
                "작업시간, 정지시간, 생산손실률과 고장 결과비용은 출처를 연결한 합성 데모 민감도 값이다.",
                "외주비 0원은 사내 작업, 예비 인서트 보유, 외부 출동 없음 조건에서만 유효하다.",
                "미래 위험확률이 없는 계획정비·재점검은 임의 추정하지 않고 insufficient로 처리한다.",
                "비용 분석은 의사결정 참고값이며 추천·승인·실행 명령이 아니다.",
            ),
            input_sources=(
                {
                    "input_name": "one_carbide_insert_public_catalog_reference",
                    "source_kind": "public_reference",
                    "source_reference": f"{reference}#parts_cost",
                    "confidence": "low",
                },
                {
                    "input_name": "mechanical_maintenance_public_wage_reference",
                    "source_kind": "public_reference",
                    "source_reference": f"{reference}#labor_rate_per_minute",
                    "confidence": "medium",
                },
                {
                    "input_name": "night_labor_premium_policy",
                    "source_kind": "public_reference",
                    "source_reference": f"{reference}#execution_time_policy",
                    "confidence": "medium",
                },
                {
                    "input_name": "tool_replacement_duration_demo_policy",
                    "source_kind": "assumption",
                    "source_reference": f"{reference}#demo_policy_inputs/labor_duration_minutes",
                    "confidence": "low",
                },
                {
                    "input_name": "in_house_service_cost_policy",
                    "source_kind": "policy",
                    "source_reference": f"{reference}#demo_policy_inputs/external_service_cost_minor",
                    "confidence": "medium",
                },
                {
                    "input_name": "preventive_downtime_demo_policy",
                    "source_kind": "assumption",
                    "source_reference": f"{reference}#demo_policy_inputs/expected_downtime_minutes",
                    "confidence": "low",
                },
                {
                    "input_name": "synthetic_production_loss_rate",
                    "source_kind": "assumption",
                    "source_reference": f"{reference}#demo_policy_inputs/production_loss_rate_minor_per_minute",
                    "confidence": "low",
                },
                {
                    "input_name": "synthetic_failure_consequence_and_probability",
                    "source_kind": "assumption",
                    "source_reference": f"{reference}#demo_policy_inputs/expected_failure_loss_minor",
                    "confidence": "low",
                },
            ),
            price_version=document["basis_id"],
            calculation_policy_version="maintenance-cost-policy-v2",
        )

    def cooling_system_restore_basis(
        self,
        *,
        calculated_at: datetime,
        context: CostBasisResolutionContext,
    ) -> CoolingSystemRestoreCostBasis:
        if calculated_at.tzinfo is None or calculated_at.utcoffset() is None:
            raise ValueError("calculated_at must include a timezone offset")
        if self.cooling_system_restore_path is None:
            raise ValueError("COOLING_SYSTEM_RESTORE cost-basis path is unavailable")
        document = self._read_document(
            self.cooling_system_restore_path,
            action_code="COOLING_SYSTEM_RESTORE",
        )
        self._require_applicable(document=document, context=context)
        scope = document.get("restoration_scope", {})
        if scope.get("component_replacement_included") is not False:
            raise ValueError(
                "COOLING_SYSTEM_RESTORE basis must exclude component replacement"
            )

        policy = document["demo_policy_inputs"]
        parts_reference = int(document["parts_cost"]["reference_minor"])
        external_service_reference = int(
            document["external_service_cost"]["reference_minor"]
        )
        if parts_reference != 0 or external_service_reference != 0:
            raise ValueError(
                "bounded cooling restoration basis requires zero parts and external cost"
            )
        execution_policy = document["execution_time_policy"]
        planned_delay = timedelta(
            hours=int(execution_policy["planned_window_delay_hours"])
        )
        labor_rates = document["labor_rate_per_minute"]
        normal_labor_rate = int(labor_rates["normal_minor"])
        night_labor_rate = int(labor_rates["night_minor"])
        if int(execution_policy["normal_rate_minor_per_minute"]) != normal_labor_rate:
            raise ValueError("execution policy normal rate must match labor basis")
        if int(execution_policy["night_rate_minor_per_minute"]) != night_labor_rate:
            raise ValueError("execution policy night rate must match labor basis")

        labor_duration = policy["labor_duration_minutes"]["sensitivity"]
        expected_downtime = policy["expected_downtime_minutes"]["sensitivity"]
        production_loss_rate = policy["production_loss_rate_minor_per_minute"][
            "sensitivity"
        ]
        expected_failure_loss = policy["expected_failure_loss_minor"][
            "scenario_values"
        ]
        scenarios = []
        for timing in ExecutionTiming:
            performs_restore = timing in {
                ExecutionTiming.IMMEDIATE,
                ExecutionTiming.PLANNED_WINDOW,
            }
            assumed_execution_at = None
            labor_rate_type = "not_applicable"
            labor_rate = 0
            if timing is ExecutionTiming.IMMEDIATE:
                assumed_execution_at = calculated_at
            elif timing is ExecutionTiming.PLANNED_WINDOW:
                assumed_execution_at = calculated_at + planned_delay
            if assumed_execution_at is not None:
                labor_rate_type, labor_rate = self._execution_rate(
                    assumed_execution_at=assumed_execution_at,
                    execution_policy=execution_policy,
                    normal_labor_rate=normal_labor_rate,
                    night_labor_rate=night_labor_rate,
                )
            scenarios.append(
                {
                    "execution_timing": timing,
                    "assumed_execution_at": assumed_execution_at,
                    "labor_rate_type": labor_rate_type,
                    "parts_cost": _money(parts_reference),
                    "labor_duration": (
                        _duration_band(labor_duration)
                        if performs_restore
                        else _duration(0)
                    ),
                    "labor_rate_per_minute": _rate(labor_rate),
                    "external_service_cost": _money(external_service_reference),
                    "expected_downtime": (
                        _duration_band(expected_downtime)
                        if performs_restore
                        else _duration(0)
                    ),
                    "production_loss_rate_per_minute": (
                        _rate_band(production_loss_rate)
                        if performs_restore
                        else _rate(0)
                    ),
                    "expected_failure_loss": _money_band(
                        expected_failure_loss[timing.value]
                    ),
                    "confidence": "low",
                }
            )

        reference = (
            "data/fixtures/maintenance_cost/"
            "cooling-system-restore-cost-basis-v1.json"
        )
        return CoolingSystemRestoreCostBasis(
            currency=document["currency"],
            currency_minor_unit=document["currency_minor_unit"],
            scenarios=tuple(scenarios),
            assumptions=(
                "복구 범위는 냉각 경로 세척·막힘 해소·동작 확인이며 팬·펌프·칠러 등 부품 교체를 포함하지 않는다.",
                "부품비와 외주비 0원은 예비부품 교체와 외부 출동이 없는 사내 복구 범위에서만 유효하다.",
                "즉시·12시간 후 비용 산정 가정 시각은 서버 시각에서 계산하고 Asia/Seoul 22:00~06:00에는 단일 50% 야간 가산 데모 요율을 적용한다. 실제 WorkOrder 일정이 아니다.",
                "작업시간, 정지시간과 생산손실률은 출처를 연결한 합성 데모 민감도 값이다.",
                "냉각 이상 전용 미래 위험확률이 없으므로 계획정비·재점검·미조치는 임의 추정하지 않고 insufficient로 처리한다.",
                "비용 분석은 의사결정 참고값이며 추천·승인·실행 명령이 아니다.",
            ),
            input_sources=(
                {
                    "input_name": "cooling_restore_no_component_replacement_scope",
                    "source_kind": "policy",
                    "source_reference": f"{reference}#parts_cost",
                    "confidence": "medium",
                },
                {
                    "input_name": "cooling_restore_in_house_service_scope",
                    "source_kind": "policy",
                    "source_reference": f"{reference}#external_service_cost",
                    "confidence": "medium",
                },
                {
                    "input_name": "mechanical_maintenance_public_wage_reference",
                    "source_kind": "public_reference",
                    "source_reference": f"{reference}#labor_rate_per_minute",
                    "confidence": "medium",
                },
                {
                    "input_name": "night_labor_premium_policy",
                    "source_kind": "public_reference",
                    "source_reference": f"{reference}#execution_time_policy",
                    "confidence": "medium",
                },
                {
                    "input_name": "cooling_restore_duration_demo_policy",
                    "source_kind": "assumption",
                    "source_reference": f"{reference}#demo_policy_inputs/labor_duration_minutes",
                    "confidence": "low",
                },
                {
                    "input_name": "cooling_restore_downtime_demo_policy",
                    "source_kind": "assumption",
                    "source_reference": f"{reference}#demo_policy_inputs/expected_downtime_minutes",
                    "confidence": "low",
                },
                {
                    "input_name": "synthetic_production_loss_rate",
                    "source_kind": "assumption",
                    "source_reference": f"{reference}#demo_policy_inputs/production_loss_rate_minor_per_minute",
                    "confidence": "low",
                },
                {
                    "input_name": "cooling_failure_probability_unavailable",
                    "source_kind": "assumption",
                    "source_reference": f"{reference}#demo_policy_inputs/expected_failure_loss_minor",
                    "confidence": "low",
                },
            ),
            price_version=document["basis_id"],
            calculation_policy_version="maintenance-cost-policy-v2",
        )


__all__ = ["JsonMaintenanceCostBasisProvider"]
