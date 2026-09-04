"""Read-only company and operational context for the manufacturing workspace.

The context enriches RAG, ontology projection, and UI composition. Current
workflow state remains owned by the closed-loop domain, while historical and
business records provide decision context and traceable source references.
"""

from __future__ import annotations

import json
import hashlib
import re
from functools import lru_cache
from typing import Any, Iterable

from .enterprise_history import enterprise_history_context
from .runtime_settings import project_root


_TOKEN = re.compile(r"[0-9A-Za-z가-힣_.:-]+")

@lru_cache(maxsize=1)
def load_company_context() -> dict[str, Any]:
    path = project_root() / "data" / "fixtures" / "company" / "company-context.json"
    context = json.loads(path.read_text(encoding="utf-8"))
    generated = enterprise_history_context()
    for key, items in generated.items():
        existing = [dict(item) for item in context.get(key) or [] if isinstance(item, dict)]
        existing_ids = {
            str(item.get("id") or item.get("asset_id") or item.get("name"))
            for item in existing
        }
        existing.extend(
            dict(item)
            for item in items
            if str(item.get("id") or item.get("asset_id") or item.get("name")) not in existing_ids
        )
        context[key] = existing
    context["corpus_summary"] = {
        key: len(value)
        for key, value in context.items()
        if isinstance(value, list)
    }
    context["corpus_summary"]["generated_history_months"] = 18
    context["corpus_summary"]["synthetic"] = True
    return context


def public_company_context(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or load_company_context()
    # Keep the workspace bootstrap bounded even though the server-side corpus is
    # deliberately large.  Full history remains available to retrieval and
    # ontology projection through ``load_company_context``.
    bounded = dict(payload)
    bounded["maintenance_records"] = sorted(
        payload.get("maintenance_records") or [],
        key=lambda item: str(item.get("occurred_at") or ""),
        reverse=True,
    )[:24]
    bounded["meeting_minutes"] = sorted(
        payload.get("meeting_minutes") or [],
        key=lambda item: str(item.get("occurred_at") or ""),
        reverse=True,
    )[:12]
    bounded["decisions"] = sorted(
        payload.get("decisions") or [],
        key=lambda item: str(item.get("decided_at") or ""),
        reverse=True,
    )[:24]
    bounded["kpi_snapshots"] = sorted(
        payload.get("kpi_snapshots") or [],
        key=lambda item: str(item.get("period") or ""),
        reverse=True,
    )[:54]
    result = {
        key: bounded[key]
        for key in (
            "schema_version",
            "context_kind",
            "company",
            "organization_units",
            "plants",
            "products",
            "materials",
            "business_metrics",
            "maintenance_records",
            "meeting_minutes",
            "decisions",
        )
    }
    result["assets"] = list(bounded.get("assets") or [])
    result["vendors"] = list(bounded.get("vendors") or [])
    result["financial_periods"] = list(bounded.get("financial_periods") or [])
    result["kpi_snapshots"] = list(bounded.get("kpi_snapshots") or [])
    result["corpus_summary"] = dict(payload.get("corpus_summary") or {})
    return result


def _tokens(value: str) -> set[str]:
    return {item.lower() for item in _TOKEN.findall(value) if len(item) > 1}


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return str(value)


def _record_document(record: dict[str, Any], *, kind: str, title: str) -> dict[str, Any]:
    content = _flatten_text(record)
    source_updated_at = (
        record.get("source_updated_at")
        or record.get("occurred_at")
        or record.get("decided_at")
        or record.get("effective_from")
        or record.get("period")
    )
    return {
        "id": str(record.get("id") or f"{kind}:{title}"),
        "title": title,
        "document_type": kind,
        "content": content,
        "tags": [kind],
        "related_asset_ids": list(record.get("related_asset_ids") or ([record["asset_id"]] if record.get("asset_id") else [])),
        "source_ref": str(record.get("source_ref") or f"company-context:{record.get('id') or kind}"),
        "source_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "source_updated_at": str(source_updated_at) if source_updated_at else None,
        "structured": record,
    }


def _normalize_document(document: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(document)
    content = str(normalized.get("content") or normalized.get("title") or "")
    normalized.setdefault("source_sha256", hashlib.sha256(content.encode("utf-8")).hexdigest())
    normalized.setdefault(
        "source_updated_at",
        normalized.get("effective_from") or normalized.get("occurred_at") or normalized.get("period"),
    )
    normalized.setdefault("related_asset_ids", [])
    return normalized


def company_documents(context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    context = context or load_company_context()
    documents = [_normalize_document(item) for item in context.get("documents") or []]
    documents.extend(
        _record_document(item, kind="maintenance_history", title=f"과거 정비 {item.get('asset_id', '')} {item.get('component', '')}")
        for item in context.get("maintenance_records") or []
    )
    documents.extend(
        _record_document(item, kind="meeting_minutes", title=str(item.get("title") or "운영 회의록"))
        for item in context.get("meeting_minutes") or []
    )
    documents.extend(
        _record_document(item, kind="decision_record", title=str(item.get("title") or "과거 의사결정"))
        for item in context.get("decisions") or []
    )
    documents.extend(
        _record_document(item, kind="material_master", title=str(item.get("name") or "자재"))
        for item in context.get("materials") or []
    )
    documents.extend(
        _record_document(item, kind="product_economics", title=str(item.get("name") or "제품"))
        for item in context.get("products") or []
    )
    documents.extend(
        _record_document(item, kind="business_metric", title=str(item.get("name") or "경영 지표"))
        for item in context.get("business_metrics") or []
    )
    documents.extend(
        _record_document(item, kind="organization_unit", title=str(item.get("name") or "조직"))
        for item in context.get("organization_units") or []
    )
    documents.extend(
        _record_document(item, kind="asset_master", title=str(item.get("name") or item.get("asset_id") or "설비"))
        for item in context.get("assets") or []
    )
    documents.extend(
        _record_document(item, kind="vendor_master", title=str(item.get("name") or "협력사"))
        for item in context.get("vendors") or []
    )
    documents.extend(
        _record_document(item, kind="financial_actual", title=f"{item.get('period', '')} 재무 actual")
        for item in context.get("financial_periods") or []
    )
    documents.extend(
        _record_document(item, kind="kpi_actual", title=f"{item.get('period', '')} {item.get('metric_key', 'KPI')}")
        for item in context.get("kpi_snapshots") or []
    )
    return documents


def retrieve_company_documents(
    query: str,
    *,
    asset_id: str | None = None,
    top_k: int = 4,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Small deterministic RAG retriever for company and operational records.

    Metadata matches are weighted above lexical overlap so asset history and
    business context remain stable, traceable, and explainable.
    """

    query_tokens = _tokens(query)
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for document in company_documents(context):
        related_assets = {str(item) for item in document.get("related_asset_ids") or []}
        text = " ".join(
            [
                str(document.get("title") or ""),
                str(document.get("content") or ""),
                " ".join(str(item) for item in document.get("tags") or []),
            ]
        )
        overlap = len(query_tokens & _tokens(text))
        metadata_score = 8 if asset_id and asset_id in related_assets else 0
        query_lower = query.lower()
        broad_business_score = 2 if any(token in query_lower for token in ("매출", "비용", "원가", "자재", "재고", "회의", "의사결정", "정비", "조직", "kpi", "revenue", "cost", "material", "meeting")) else 0
        kind = str(document.get("document_type") or "")
        intent_score = 0
        intent_groups = {
            "maintenance_history": ("정비", "고장", "수리", "maintenance", "repair"),
            "asset_master": ("장비 가격", "설비 가격", "취득", "교체비", "장부가", "asset", "replacement"),
            "financial_actual": ("재무", "손익", "매출", "영업이익", "opex", "capex", "finance", "p&l"),
            "financial_statement": ("재무", "손익", "매출", "영업이익", "opex", "capex", "finance", "p&l"),
            "kpi_actual": ("kpi", "oee", "mtbf", "mttr", "가동률", "downtime", "lead time"),
            "meeting_minutes": ("회의", "회의록", "meeting", "review"),
            "decision_record": ("의사결정", "결정", "승인", "decision"),
            "material_master": ("자재", "부품", "재고", "조달", "lead time", "inventory", "part"),
            "site_sop": ("sop", "절차", "점검 방법", "정비 방법", "매뉴얼"),
        }
        if any(token in query_lower for token in intent_groups.get(kind, ())):
            intent_score = 5
        score = metadata_score + broad_business_score + intent_score + overlap
        if score <= 0:
            continue
        ranked.append((score, str(document.get("id") or ""), document))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected: list[tuple[int, dict[str, Any]]] = []
    kind_counts: dict[str, int] = {}
    # A larger corpus makes naive top-k brittle: dozens of decisions for one
    # asset can crowd out its maintenance/material/finance evidence.  Keep a
    # small per-kind cap so the answer packet receives heterogeneous evidence.
    per_kind_cap = max(2, min(3, top_k // 2 or 2))
    for score, _, document in ranked:
        kind = str(document.get("document_type") or "unknown")
        if kind_counts.get(kind, 0) >= per_kind_cap:
            continue
        selected.append((score, document))
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        if len(selected) >= max(1, top_k):
            break
    return [
        {
            **document,
            "retrieval_score": score,
            "context_kind": "company_operational_context",
        }
        for score, document in selected
    ]


def matching_maintenance_history(asset_id: str) -> list[dict[str, Any]]:
    context = load_company_context()
    return [
        dict(item)
        for item in context.get("maintenance_records") or []
        if str(item.get("asset_id")) == asset_id
    ]


def iter_company_records(kind: str) -> Iterable[dict[str, Any]]:
    context = load_company_context()
    value = context.get(kind) or []
    return (dict(item) for item in value if isinstance(item, dict))
