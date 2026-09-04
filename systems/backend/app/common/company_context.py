"""Read-only company and operational context for the manufacturing workspace.

The context enriches RAG, ontology projection, and UI composition. Current
workflow state remains owned by the closed-loop domain, while historical and
business records provide decision context and traceable source references.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Iterable

from .runtime_settings import project_root


_TOKEN = re.compile(r"[0-9A-Za-z가-힣_.:-]+")

@lru_cache(maxsize=1)
def load_company_context() -> dict[str, Any]:
    path = project_root() / "data" / "fixtures" / "company" / "company-context.json"
    return json.loads(path.read_text(encoding="utf-8"))


def public_company_context(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or load_company_context()
    return {
        key: payload[key]
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
    return {
        "id": str(record.get("id") or f"{kind}:{title}"),
        "title": title,
        "document_type": kind,
        "content": _flatten_text(record),
        "tags": [kind],
        "related_asset_ids": list(record.get("related_asset_ids") or ([record["asset_id"]] if record.get("asset_id") else [])),
        "source_ref": str(record.get("source_ref") or f"company-context:{record.get('id') or kind}"),
        "structured": record,
    }


def company_documents(context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    context = context or load_company_context()
    documents = [dict(item) for item in context.get("documents") or []]
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
        broad_business_score = 2 if any(token in query.lower() for token in ("매출", "비용", "원가", "자재", "재고", "회의", "의사결정", "정비", "조직", "kpi", "revenue", "cost", "material", "meeting")) else 0
        score = metadata_score + broad_business_score + overlap
        if score <= 0:
            continue
        ranked.append((score, str(document.get("id") or ""), document))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [
        {
            **document,
            "retrieval_score": score,
            "context_kind": "company_operational_context",
        }
        for score, _, document in ranked[: max(1, top_k)]
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
