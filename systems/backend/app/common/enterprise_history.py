"""Deterministic enterprise history corpus for the manufacturing demo.

The demo used to carry only a handful of company-context records.  This module
builds a coherent 18-month operating history from one fixed model so RAG,
ontology traversal, reporting, and finance/maintenance views can all point to
the same synthetic facts.  Nothing here represents a real company record.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Any


KST = timezone(timedelta(hours=9))

_MONTHS = [
    (2025, month) for month in range(3, 13)
] + [
    (2026, month) for month in range(1, 9)
]

_COMPONENTS = (
    ("tooling", "공구 홀더/인서트", "공구 마모 편차 증가", "툴 홀더 체결 상태 확인 및 인서트 교환"),
    ("spindle", "스핀들/베어링", "고부하 구간 진동 및 전력 피크 증가", "스핀들 정렬·윤활 상태 확인 및 베어링 점검"),
    ("cooling", "냉각 회로", "공정 온도 회복 지연", "필터 세척·냉각수 보충·유량 확인"),
    ("drive", "서보 드라이브", "토크 추종 오차와 드라이브 경보", "드라이브 로그 확인 및 커넥터/모듈 점검"),
    ("sensor", "센서 하네스", "간헐적 신호 품질 저하", "커넥터 재체결·접지 확인·신호 검증"),
    ("lubrication", "윤활 계통", "윤활 압력 편차", "윤활 라인 점검·필터 교환·기준 압력 확인"),
)


def _iso(value: datetime) -> str:
    return value.astimezone(KST).isoformat()


def _asset_ids() -> list[str]:
    cnc = [
        f"CNC-S{site:02d}-L{line:02d}-{machine:02d}"
        for site in range(1, 5)
        for line in range(1, 6)
        for machine in range(1, 5)
    ]
    compressors = [f"CMP-S{site:02d}-UTIL-{machine:02d}" for site in range(1, 5) for machine in range(1, 3)]
    return cnc + compressors


def _assets() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, asset_id in enumerate(_asset_ids()):
        compressor = asset_id.startswith("CMP-")
        acquisition_year = 2018 + (index % 7)
        purchase = (62_000_000 + (index % 9) * 7_800_000) if not compressor else (48_000_000 + (index % 4) * 5_500_000)
        install = int(purchase * (0.11 + (index % 3) * 0.015))
        replacement = int((purchase + install) * (1.16 + (index % 5) * 0.025))
        age_years = 2026 - acquisition_year
        useful_life = 12 if not compressor else 15
        book_ratio = max(0.12, 1 - age_years / useful_life)
        result.append({
            "id": f"asset:{asset_id}",
            "asset_id": asset_id,
            "name": f"{'CNC 머시닝센터' if not compressor else '공기압축기'} {asset_id}",
            "asset_type": "cnc_machining_center" if not compressor else "air_compressor",
            "manufacturer": ("Hanul Machine" if index % 3 == 0 else "Mirae CNC") if not compressor else "Korea Air Systems",
            "model": f"{'HC' if not compressor else 'AC'}-{700 + index % 8}",
            "acquired_at": f"{acquisition_year}-{1 + index % 12:02d}-15",
            "purchase_price_krw": purchase,
            "installation_cost_krw": install,
            "replacement_value_krw": replacement,
            "book_value_krw": int((purchase + install) * book_ratio),
            "useful_life_years": useful_life,
            "warranty_end": f"{acquisition_year + 3}-{1 + index % 12:02d}-14",
            "criticality": ("critical" if index % 11 in (0, 1) else "high" if index % 5 == 0 else "medium"),
            "source_ref": f"asset-master:{asset_id}",
        })
    return result


def _materials() -> list[dict[str, Any]]:
    categories = (
        ("절삭 공구", "초경 인서트", 28_700, 12),
        ("정비 부품", "스핀들 베어링 세트", 1_180_000, 28),
        ("소모품", "가공 냉각수 20L", 94_000, 5),
        ("전장 예비품", "서보 드라이브 모듈", 4_860_000, 35),
        ("센서", "진동 센서", 680_000, 21),
        ("윤활", "윤활 필터 키트", 145_000, 9),
    )
    assets = _asset_ids()
    result: list[dict[str, Any]] = []
    for index in range(72):
        category, label, base_cost, base_lead = categories[index % len(categories)]
        related = [assets[(index * 3 + offset * 11) % len(assets)] for offset in range(3)]
        result.append({
            "id": f"material:HB-{index + 1:03d}",
            "name": f"{label} HB-{index + 1:03d}",
            "category": category,
            "unit_cost_krw": int(base_cost * (0.82 + (index % 9) * 0.045)),
            "on_hand_quantity": (index * 17) % 185,
            "reorder_point": 2 + index % 22,
            "lead_time_days": base_lead + index % 8,
            "preferred_vendor_id": f"vendor:V{1 + index % 14:02d}",
            "related_asset_ids": related,
            "source_ref": f"material-master:HB-{index + 1:03d}",
        })
    return result


def _vendors() -> list[dict[str, Any]]:
    return [
        {
            "id": f"vendor:V{index:02d}",
            "name": f"한빛 협력사 {index:02d}",
            "category": ("정밀부품" if index % 3 == 0 else "MRO" if index % 3 == 1 else "전장/센서"),
            "standard_lead_time_days": 7 + (index * 3) % 31,
            "on_time_delivery_rate": round(0.91 + (index % 7) * 0.011, 3),
            "quality_ppm": 110 + index * 17,
            "source_ref": f"vendor-master:V{index:02d}",
        }
        for index in range(1, 15)
    ]


def _maintenance_records(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assets = _asset_ids()
    material_ids = [str(item["id"]) for item in materials]
    result: list[dict[str, Any]] = []
    sequence = 1
    # 40 historical maintenance/inspection events per month x 18 months = 720.
    for month_index, (year, month) in enumerate(_MONTHS):
        days = monthrange(year, month)[1]
        for slot in range(40):
            asset_id = assets[(month_index * 19 + slot * 7) % len(assets)]
            key, component, symptom, action = _COMPONENTS[(slot + month_index) % len(_COMPONENTS)]
            occurred = datetime(year, month, 1 + (slot * 5 + month_index) % days, 1 + slot % 5, 10 + slot % 40, tzinfo=KST)
            work_type = ("inspection" if slot % 7 == 0 else "corrective_maintenance" if slot % 5 == 0 else "preventive_maintenance")
            downtime = 18 + ((slot * 13 + month_index * 9) % 168)
            material_id = material_ids[(slot + month_index * 3) % len(material_ids)]
            result.append({
                "id": f"history:ENT-{sequence:05d}",
                "asset_id": asset_id,
                "occurred_at": _iso(occurred),
                "work_type": work_type,
                "component_key": key,
                "component": component,
                "symptom": symptom,
                "action": action,
                "result": ("재관측 14일 동안 동일 경보 미발생" if slot % 4 else "개선 확인, 다음 예방정비 시 재점검 필요"),
                "downtime_minutes": downtime,
                "labor_minutes": max(20, downtime - 8 + slot % 22),
                "material_ids": [] if work_type == "inspection" else [material_id],
                "maintenance_cost_krw": 85_000 + downtime * 8_500 + (slot % 6) * 42_000,
                "work_order_ref": f"WO-HIST-{sequence:05d}",
                "source_ref": f"maintenance:ENT-{sequence:05d}",
            })
            sequence += 1
    return result


def _financial_periods() -> list[dict[str, Any]]:
    result = []
    for index, (year, month) in enumerate(_MONTHS):
        seasonal = (month % 4 - 1.5) * 0.018
        revenue = int(9_100_000_000 * (1 + index * 0.011 + seasonal))
        material_cost = int(revenue * (0.421 + (index % 3) * 0.006))
        labor_cost = int(revenue * 0.127)
        maintenance_opex = 182_000_000 + (index % 5) * 19_000_000
        operating_profit = revenue - material_cost - labor_cost - maintenance_opex - int(revenue * 0.218)
        result.append({
            "id": f"finance:{year}-{month:02d}",
            "period": f"{year}-{month:02d}",
            "revenue_krw": revenue,
            "material_cost_krw": material_cost,
            "labor_cost_krw": labor_cost,
            "maintenance_opex_krw": maintenance_opex,
            "maintenance_capex_krw": 80_000_000 + (index % 4) * 115_000_000,
            "operating_profit_krw": operating_profit,
            "budget_revenue_krw": int(revenue / (0.975 + (index % 5) * 0.008)),
            "currency": "KRW",
            "source_ref": f"finance-ledger:{year}-{month:02d}",
        })
    return result


def _kpi_snapshots(maintenance: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    metric_defs = (
        ("oee", "%", 0.806, 0.0021),
        ("mtbf_hours", "hour", 182.0, 2.6),
        ("mttr_minutes", "minute", 112.0, -1.4),
        ("unplanned_downtime_hours", "hour", 146.0, -2.2),
        ("schedule_attainment", "%", 0.932, 0.0017),
        ("first_pass_yield", "%", 0.971, 0.0006),
        ("decision_lead_time_minutes", "minute", 131.0, -2.5),
        ("report_lead_time_minutes", "minute", 54.0, -1.25),
        ("maintenance_backlog_count", "count", 48.0, -0.75),
    )
    for month_index, (year, month) in enumerate(_MONTHS):
        for key, unit, baseline, slope in metric_defs:
            value = baseline + slope * month_index
            if unit == "%":
                value = min(0.995, value)
            value += ((month_index % 4) - 1.5) * (0.001 if unit == "%" else 0.8)
            result.append({
                "id": f"kpi:{key}:{year}-{month:02d}",
                "metric_key": key,
                "period": f"{year}-{month:02d}",
                "value": round(value, 4 if unit == "%" else 1),
                "unit": unit,
                "source_label": "enterprise simulation actual",
                "source_ref": f"kpi-ledger:{key}:{year}-{month:02d}",
            })
    return result


def _meetings_and_decisions() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    meetings: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    assets = _asset_ids()
    decision_no = 1
    start = datetime(2025, 3, 3, 9, 0, tzinfo=KST)
    # 78 weekly reliability meetings across the 18-month history.
    for week in range(78):
        occurred = start + timedelta(days=7 * week)
        asset_id = assets[(week * 11) % len(assets)]
        decision_ids = []
        for branch in range(2):
            decision_id = f"decision:ENT-{decision_no:04d}"
            decision_ids.append(decision_id)
            decisions.append({
                "id": decision_id,
                "title": f"{asset_id} {'점검 우선순위' if branch == 0 else '부품/생산 대응'} 결정",
                "decided_at": _iso(occurred + timedelta(minutes=32 + branch * 9)),
                "owner_org_unit_id": "org:production-operations" if branch else "org:reliability-engineering",
                "decision": (
                    "최근 90일 정비 이력과 현재 위험 근거를 대조해 교대 내 점검 우선순위를 지정한다."
                    if branch == 0
                    else "예비품 재고와 생산계획 영향을 함께 확인하고 승인 전 SCM/생산 대응을 병행한다."
                ),
                "related_asset_ids": [asset_id],
                "source_ref": f"decision:ENT-{decision_no:04d}",
            })
            decision_no += 1
        meetings.append({
            "id": f"meeting:WEEKLY-{occurred.date().isoformat()}",
            "title": f"주간 Reliability 운영회의 · {occurred:%Y-%m-%d}",
            "occurred_at": _iso(occurred),
            "attendees": ["생산운영실", "설비신뢰성팀", "정비실행팀", "재무·SCM팀"],
            "summary": f"{asset_id}를 포함한 고위험 설비의 최근 정비 반복성, 생산 영향, 부품 가용성과 미결 Decision Case를 검토했다.",
            "decision_ids": decision_ids,
            "related_asset_ids": [asset_id],
            "source_ref": f"meeting:WEEKLY-{occurred.date().isoformat()}",
        })

    for month_index, (year, month) in enumerate(_MONTHS):
        occurred = datetime(year, month, min(26, monthrange(year, month)[1]), 16, 0, tzinfo=KST)
        decision_id = f"decision:ENT-{decision_no:04d}"
        decisions.append({
            "id": decision_id,
            "title": f"{year}-{month:02d} 월말 운영 리스크 원칙",
            "decided_at": _iso(occurred + timedelta(minutes=35)),
            "owner_org_unit_id": "org:executive-operations-council",
            "decision": "경영 보고는 위험 확률, 생산·재무 노출, 판단 지연, 조치 가능성, 근거 신뢰도를 분리해 표기한다.",
            "related_asset_ids": [],
            "source_ref": decision_id,
        })
        decision_no += 1
        meetings.append({
            "id": f"meeting:EXEC-{year}-{month:02d}",
            "title": f"{year}-{month:02d} 월말 운영 리스크 리뷰",
            "occurred_at": _iso(occurred),
            "attendees": ["경영 운영위원회", "생산운영실", "재무·SCM팀"],
            "summary": "월간 KPI actual, downtime 손실 노출, 반복 정비, 부품 조달 리스크와 다음 달 CAPEX/OPEX 우선순위를 검토했다.",
            "decision_ids": [decision_id],
            "related_asset_ids": [],
            "source_ref": f"meeting:EXEC-{year}-{month:02d}",
        })
    return meetings, decisions


def _documents(finance: list[dict[str, Any]]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    components = [item[1] for item in _COMPONENTS]
    for index in range(45):
        component = components[index % len(components)]
        version = 1 + index // len(components)
        documents.append({
            "id": f"doc:sop:HB-{index + 1:03d}",
            "title": f"{component} 점검 및 정비 표준절차 HB-{index + 1:03d}",
            "document_type": "site_sop",
            "version": f"v{version}.0",
            "effective_from": f"{2024 + version}-{1 + index % 12:02d}-01",
            "content": f"{component} 이상 징후 발생 시 작업 전 안전 격리, 최근 센서 추세와 정비 이력 확인, 현장 점검, 측정값 기록, 관리자 승인 후 정비 실행 순으로 진행한다. 측정 근거 없이 자동 교체 또는 자동 승인을 하지 않는다.",
            "tags": ["SOP", "점검", "정비", component],
            "related_asset_ids": [],
            "source_ref": f"knowledge:sop:HB-{index + 1:03d}:v{version}.0",
        })
    for item in finance:
        period = str(item["period"])
        documents.append({
            "id": f"doc:finance-statement:{period}",
            "title": f"{period} 월간 손익 및 정비비 요약",
            "document_type": "financial_statement",
            "content": (
                f"{period} 매출 {item['revenue_krw']:,}원, 재료비 {item['material_cost_krw']:,}원, "
                f"정비 OPEX {item['maintenance_opex_krw']:,}원, 정비 CAPEX {item['maintenance_capex_krw']:,}원, "
                f"영업이익 {item['operating_profit_krw']:,}원. 운영 의사결정용 월마감 synthetic actual이다."
            ),
            "tags": ["재무", "P&L", "OPEX", "CAPEX", period],
            "related_asset_ids": [],
            "source_ref": f"finance-statement:{period}",
        })
        documents.append({
            "id": f"doc:operations-review:{period}",
            "title": f"{period} Reliability 월간 운영보고",
            "document_type": "operations_report",
            "content": f"{period}의 OEE, MTBF, MTTR, 비계획 정지, Decision Lead Time, backlog 추세와 반복 고장 설비를 월말 운영위원회에 보고했다.",
            "tags": ["Reliability", "KPI", "운영보고", period],
            "related_asset_ids": [],
            "source_ref": f"operations-report:{period}",
        })
    for index in range(14):
        documents.append({
            "id": f"doc:vendor-bulletin:{index + 1:02d}",
            "title": f"협력사 기술 Bulletin {index + 1:02d}",
            "document_type": "vendor_bulletin",
            "content": "고부하 운전 시 베어링 윤활, 냉각 상태, 서보 드라이브 온도와 커넥터 체결 상태를 정기 점검하고 교체 전 현장 측정값과 장비 이력을 확인한다.",
            "tags": ["vendor", "service bulletin", "bearing", "cooling", "drive"],
            "related_asset_ids": [],
            "source_ref": f"vendor-bulletin:{index + 1:02d}",
        })
    return documents


def enterprise_history_context() -> dict[str, list[dict[str, Any]]]:
    """Return the fixed, internally consistent synthetic enterprise corpus."""

    assets = _assets()
    materials = _materials()
    vendors = _vendors()
    maintenance = _maintenance_records(materials)
    finance = _financial_periods()
    kpis = _kpi_snapshots(maintenance)
    meetings, decisions = _meetings_and_decisions()
    documents = _documents(finance)
    return {
        "assets": assets,
        "materials": materials,
        "vendors": vendors,
        "maintenance_records": maintenance,
        "financial_periods": finance,
        "kpi_snapshots": kpis,
        "meeting_minutes": meetings,
        "decisions": decisions,
        "documents": documents,
    }


__all__ = ["enterprise_history_context"]
