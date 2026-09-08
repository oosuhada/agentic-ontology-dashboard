"""Deterministic response planning for the read-only Operations assistant.

The planner intentionally decides *what* evidence is required before any
free-form answer generation occurs.  It does not generate SQL or Cypher.  The
runtime maps logical stores to governed adapters (PostgreSQL, Project 3/Neo4j,
and vector/RAG) and can degrade individual stores without losing the whole
answer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .contracts import AgentRoute


LogicalStore = Literal["relational", "graph", "vector"]
Presentation = Literal[
    "metric_summary",
    "risk_ranking",
    "comparison",
    "relationship",
    "evidence",
    "narrative",
]


@dataclass(frozen=True)
class AgentResponseContract:
    version: str
    intent: str
    scope: Literal["workspace", "object"]
    required_facts: tuple[str, ...]
    required_entities: tuple[str, ...]
    stores: tuple[LogicalStore, ...]
    presentation: Presentation

    def as_payload(self) -> dict[str, object]:
        return asdict(self)


def _contains(question: str, *tokens: str) -> bool:
    normalized = question.casefold()
    return any(token.casefold() in normalized for token in tokens)


def _requested_store_override(route: AgentRoute) -> tuple[LogicalStore, ...] | None:
    if route == "auto":
        return None
    if route == "relational":
        return ("relational",)
    if route == "graph":
        return ("graph",)
    if route == "vector":
        return ("vector",)
    return ("relational", "graph", "vector")


def plan_agent_response_contract(
    question: str,
    *,
    route: AgentRoute = "auto",
    object_id: str | None = None,
) -> AgentResponseContract:
    """Plan bounded evidence requirements from the user's wording.

    This is deliberately conservative.  PostgreSQL remains authoritative for
    live operational state; graph is added only for relationship/path questions;
    vector is added for document/procedure/policy evidence.
    """

    asks_relationship = _contains(
        question,
        "연결",
        "관계",
        "경로",
        "영향 범위",
        "어디까지 영향",
        "부품",
        "구성품",
        "공급업체",
        "bom",
        "upstream",
        "downstream",
        "connected",
        "relationship",
        "path",
        "component",
        "supplier",
        "depends on",
        "dependency",
    )
    asks_document = _contains(
        question,
        "sop",
        "매뉴얼",
        "절차",
        "정책",
        "회의",
        "보고서",
        "문서",
        "manual",
        "procedure",
        "policy",
        "meeting",
        "document",
        "guidance",
    )
    asks_company_context = _contains(
        question,
        "kpi",
        "재무",
        "매출",
        "손익",
        "회의",
        "의사결정",
        "회사 가치",
        "finance",
        "financial",
        "revenue",
        "meeting",
        "business value",
        "decision context",
    )
    asks_risk = _contains(
        question,
        "위험",
        "리스크",
        "고장",
        "우선",
        "상위",
        "risk",
        "failure",
        "priority",
        "highest",
        "top",
    )
    asks_impact = _contains(
        question,
        "생산",
        "영향",
        "손실",
        "비가동",
        "비용",
        "가치",
        "kpi",
        "production",
        "impact",
        "loss",
        "downtime",
        "cost",
        "value",
    )
    asks_history = _contains(
        question,
        "이력",
        "과거",
        "재발",
        "정비 전후",
        "history",
        "previous",
        "recurrence",
        "before",
        "after",
    )
    asks_workflow = _contains(
        question,
        "점검",
        "정비",
        "작업",
        "승인",
        "판단 대기",
        "inspection",
        "maintenance",
        "work order",
        "approval",
        "pending decision",
    )
    asks_comparison = _contains(
        question,
        "비교",
        "차이",
        "전후",
        "compare",
        "comparison",
        "difference",
        "versus",
        " vs ",
    )

    required_facts: list[str] = []
    if asks_risk:
        required_facts.extend(("current_risk", "risk_status"))
    if asks_impact:
        required_facts.extend(("downtime_exposure", "production_exposure"))
    if asks_history:
        required_facts.append("maintenance_history")
    if asks_workflow:
        required_facts.extend(("workflow_state", "recommended_next_action"))
    if asks_relationship:
        required_facts.append("relationship_paths")
    if asks_document:
        required_facts.append("governed_knowledge")
    if asks_company_context:
        required_facts.append("company_context")
    if not required_facts:
        required_facts.append("operational_context")

    required_entities = ["asset" if object_id else "workspace"]
    if asks_relationship:
        required_entities.extend(("component", "line", "product"))
    if asks_document:
        required_entities.append("knowledge_document")
    if asks_company_context:
        required_entities.append("organization_context")

    override = _requested_store_override(route)
    if override is not None:
        stores = override
    else:
        inferred: list[LogicalStore] = ["relational"]
        if asks_relationship:
            inferred.append("graph")
        if (
            asks_document
            or asks_company_context
            or asks_history
            or _contains(question, "근거", "왜", "evidence", "why")
        ):
            inferred.append("vector")
        stores = tuple(dict.fromkeys(inferred))

    if asks_comparison:
        presentation: Presentation = "comparison"
        intent = "compare_operational_context"
    elif asks_relationship:
        presentation = "relationship"
        intent = "trace_operational_relationships"
    elif asks_risk and not object_id:
        presentation = "risk_ranking"
        intent = "prioritize_operational_risk"
    elif asks_risk or asks_impact or asks_workflow:
        presentation = "metric_summary"
        intent = "summarize_operational_case"
    elif asks_document or _contains(question, "근거", "evidence", "why", "왜"):
        presentation = "evidence"
        intent = "explain_grounded_evidence"
    else:
        presentation = "narrative"
        intent = "summarize_operational_context"

    return AgentResponseContract(
        version="1.0",
        intent=intent,
        scope="object" if object_id else "workspace",
        required_facts=tuple(dict.fromkeys(required_facts)),
        required_entities=tuple(dict.fromkeys(required_entities)),
        stores=stores,
        presentation=presentation,
    )


def route_for_response_contract(contract: AgentResponseContract) -> Literal[
    "relational", "graph", "vector", "hybrid"
]:
    if len(contract.stores) > 1:
        return "hybrid"
    return contract.stores[0]
