"""Typed visual pipeline contracts and safe pushdown planning."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


NodeType = Literal["source", "select", "filter", "join", "aggregate", "window", "quality", "sink"]


class PipelineNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    type: NodeType
    config: dict[str, Any]


class PipelineEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: str
    target: str


class PipelinePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodes: tuple[PipelineNode, ...] = Field(min_length=2, max_length=100)
    edges: tuple[PipelineEdge, ...] = Field(min_length=1, max_length=200)
    row_budget: int = Field(default=1_000_000, ge=1, le=10_000_000)

    @model_validator(mode="after")
    def validate_graph(self):
        ids = {node.id for node in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("duplicate pipeline node id")
        if any(edge.source not in ids or edge.target not in ids for edge in self.edges):
            raise ValueError("pipeline edge references unknown node")
        if not any(node.type == "source" for node in self.nodes) or not any(node.type == "sink" for node in self.nodes):
            raise ValueError("pipeline requires source and sink")
        return self


class PipelinePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    valid: bool
    pushdown_provider: str
    sql_preview: str
    estimated_rows: int
    estimated_bytes: int
    keyset_pagination: str
    cancellation: str
    issues: tuple[str, ...]
    materialization: dict[str, Any]
    nodes: tuple[dict[str, Any], ...]


SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identifier(value: str) -> str:
    if not SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError("unsafe pipeline identifier")
    return f'"{value}"'


def plan_pipeline(request: PipelinePlanRequest) -> PipelinePlan:
    source = next(node for node in request.nodes if node.type == "source")
    table = _identifier(str(source.config.get("table", "canonical_equipment")))
    columns = ["machine_id", "failure_probability", "temperature"]
    where = []
    group_by = []
    issues: list[str] = []
    for node in request.nodes:
        if node.type == "select":
            selected = node.config.get("columns", columns)
            columns = [_identifier(str(column)) for column in selected]
        elif node.type == "filter":
            field = _identifier(str(node.config.get("field", "failure_probability")))
            operator = node.config.get("operator", ">=")
            if operator not in {"=", ">", ">=", "<", "<=", "!="}:
                raise ValueError("unsupported filter operator")
            where.append(f"{field} {operator} $1")
        elif node.type == "join" and not node.config.get("keys"):
            issues.append("unsafe Cartesian join blocked")
        elif node.type == "aggregate":
            group_by = [_identifier(str(item)) for item in node.config.get("group_by", [])]
    sql = f"SELECT {', '.join(columns)} FROM {table}"
    if where: sql += " WHERE " + " AND ".join(where)
    if group_by: sql += " GROUP BY " + ", ".join(group_by)
    sql += " AND machine_id > $cursor" if where else " WHERE machine_id > $cursor"
    sql += " ORDER BY machine_id LIMIT $page_size"
    estimated_rows = min(request.row_budget, 100_000)
    return PipelinePlan(
        valid=not issues,
        pushdown_provider="postgresql",
        sql_preview=sql,
        estimated_rows=estimated_rows,
        estimated_bytes=estimated_rows * 96,
        keyset_pagination="machine_id > cursor; no deep OFFSET",
        cancellation="durable job cancellation token checked between batches",
        issues=tuple(issues),
        materialization={
            "mode": "incremental",
            "output": "immutable Dataset Version",
            "quality_gate": "schema + null-rate + marking propagation",
            "preview_is_materialization": False,
        },
        nodes=tuple({"id": node.id, "type": node.type, "state": "blocked" if node.type == "join" and issues else "ready"} for node in request.nodes),
    )


def sample_pipeline() -> PipelinePlanRequest:
    return PipelinePlanRequest(
        nodes=(
            PipelineNode(id="source", type="source", config={"table": "canonical_equipment"}),
            PipelineNode(id="filter", type="filter", config={"field": "failure_probability", "operator": ">=", "value": 0.7}),
            PipelineNode(id="quality", type="quality", config={"rule": "machine_id not null"}),
            PipelineNode(id="sink", type="sink", config={"dataset": "high-risk-assets"}),
        ),
        edges=(PipelineEdge(source="source", target="filter"), PipelineEdge(source="filter", target="quality"), PipelineEdge(source="quality", target="sink")),
    )


__all__ = ["PipelineEdge", "PipelineNode", "PipelinePlan", "PipelinePlanRequest", "plan_pipeline", "sample_pipeline"]
