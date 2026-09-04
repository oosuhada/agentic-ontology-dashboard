"""In-memory graph experiment for read-only agent review context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentContextNode:
    node_id: str
    node_type: str
    label: str
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentContextEdge:
    source_id: str
    relation: str
    target_id: str


@dataclass
class AgentContextGraph:
    nodes: dict[str, AgentContextNode] = field(default_factory=dict)
    edges: list[AgentContextEdge] = field(default_factory=list)

    def add_node(
        self,
        node_id: str,
        node_type: str,
        label: str,
        source_refs: list[str] | None = None,
    ) -> None:
        if node_id in self.nodes:
            return
        self.nodes[node_id] = AgentContextNode(
            node_id=node_id,
            node_type=node_type,
            label=label,
            source_refs=tuple(source_refs or ()),
        )

    def add_edge(self, source_id: str, relation: str, target_id: str) -> None:
        edge = AgentContextEdge(source_id=source_id, relation=relation, target_id=target_id)
        if edge not in self.edges:
            self.edges.append(edge)

    def neighbors(self, source_id: str, relation: str) -> list[AgentContextNode]:
        return [
            self.nodes[edge.target_id]
            for edge in self.edges
            if edge.source_id == source_id
            and edge.relation == relation
            and edge.target_id in self.nodes
        ]


def build_agent_context_graph(packet: dict[str, Any]) -> AgentContextGraph:
    """Build a read-only relationship graph from an Agent Review Packet."""

    graph = AgentContextGraph()
    asset_id = str(packet.get("asset_id") or "")
    snapshot_id = _snapshot_node_id(packet)
    graph.add_node(snapshot_id, "PredictionSnapshot", snapshot_id, packet.get("source_refs") or [])
    if asset_id:
        graph.add_node(f"Asset:{asset_id}", "Asset", str(packet.get("asset_label") or asset_id))
        graph.add_edge(snapshot_id, "observed_asset", f"Asset:{asset_id}")

    for traversal in (packet.get("ontology_context") or {}).get("traversals") or []:
        if not isinstance(traversal, dict):
            continue
        component_id = str(traversal.get("component_id") or "")
        if not component_id:
            continue
        component_node_id = f"Component:{component_id}"
        graph.add_node(
            component_node_id,
            "Component",
            str(traversal.get("component_label") or component_id),
            traversal.get("source_refs") or [],
        )
        graph.add_edge(snapshot_id, "implicates_component", component_node_id)

        location_ref = str(traversal.get("location_source_ref") or "")
        location_label = traversal.get("location_label")
        if location_ref and location_label:
            location_node_id = f"InspectionLocation:{location_ref}"
            graph.add_node(
                location_node_id,
                "InspectionLocation",
                str(location_label),
                [location_ref],
            )
            graph.add_edge(component_node_id, "checked_at", location_node_id)

        for factor_ref in traversal.get("factor_refs") or []:
            factor_node_id = f"Factor:{factor_ref}"
            graph.add_node(factor_node_id, "Factor", str(factor_ref), [str(factor_ref)])
            graph.add_edge(snapshot_id, "has_factor", factor_node_id)
            graph.add_edge(factor_node_id, "maps_to_component", component_node_id)

        for sop_id in traversal.get("sop_ids") or []:
            sop_node_id = f"SOP:{sop_id}"
            graph.add_node(sop_node_id, "SOP", str(sop_id))
            graph.add_edge(component_node_id, "guided_by_sop", sop_node_id)

        for part in traversal.get("spare_parts") or []:
            if not isinstance(part, dict):
                continue
            part_id = str(part.get("part_id") or "")
            if not part_id:
                continue
            part_node_id = f"SparePart:{part_id}"
            graph.add_node(
                part_node_id,
                "SparePart",
                str(part.get("part_label") or part_id),
                [str(part.get("source_ref") or "")],
            )
            graph.add_edge(component_node_id, "has_spare_part_candidate", part_node_id)

        for event in traversal.get("similar_events") or []:
            if not isinstance(event, dict):
                continue
            similar_event_id = str(event.get("similar_event_id") or "")
            if not similar_event_id:
                continue
            event_node_id = f"SimilarEvent:{similar_event_id}"
            graph.add_node(
                event_node_id,
                "SimilarEvent",
                similar_event_id,
                [str(event.get("source_ref") or "")],
            )
            graph.add_edge(component_node_id, "has_similar_event", event_node_id)
            outcome = str(event.get("outcome") or "")
            if outcome:
                outcome_node_id = f"Outcome:{similar_event_id}"
                graph.add_node(outcome_node_id, "Outcome", outcome)
                graph.add_edge(event_node_id, "resulted_in", outcome_node_id)

    return graph


def answer_agent_context_graph(packet: dict[str, Any]) -> dict[str, Any]:
    """Answer the current Level 1 facets through graph traversal."""

    graph = build_agent_context_graph(packet)
    snapshot_id = _snapshot_node_id(packet)
    components = graph.neighbors(snapshot_id, "implicates_component")
    component = components[0] if components else None
    if component is None:
        return {
            "component_id": None,
            "factor_refs": [],
            "location_label": None,
            "sop_ids": [],
            "spare_part_ids": [],
            "similar_event_ids": [],
            "similar_event_outcomes": [],
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "boundary": _boundary(packet),
        }

    component_id = component.node_id.removeprefix("Component:")
    factor_refs = [
        edge.source_id.removeprefix("Factor:")
        for edge in graph.edges
        if edge.relation == "maps_to_component" and edge.target_id == component.node_id
    ]
    locations = graph.neighbors(component.node_id, "checked_at")
    spare_parts = graph.neighbors(component.node_id, "has_spare_part_candidate")
    similar_events = graph.neighbors(component.node_id, "has_similar_event")
    outcomes = [
        outcome.label
        for event in similar_events
        for outcome in graph.neighbors(event.node_id, "resulted_in")
    ]
    sops = graph.neighbors(component.node_id, "guided_by_sop")
    return {
        "component_id": component_id,
        "factor_refs": factor_refs,
        "location_label": locations[0].label if locations else None,
        "sop_ids": [sop.node_id.removeprefix("SOP:") for sop in sops],
        "spare_part_ids": [
            part.node_id.removeprefix("SparePart:") for part in spare_parts
        ],
        "similar_event_ids": [
            event.node_id.removeprefix("SimilarEvent:") for event in similar_events
        ],
        "similar_event_outcomes": outcomes,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "boundary": _boundary(packet),
    }


def _snapshot_node_id(packet: dict[str, Any]) -> str:
    snapshot = packet.get("snapshot_basis") or {}
    return "PredictionSnapshot:" + str(
        snapshot.get("evidence_payload_reference")
        or packet.get("generated_at")
        or packet.get("asset_id")
        or "unknown"
    )


def _boundary(packet: dict[str, Any]) -> str:
    if packet["review_draft"]["priority_label"] == "미확정":
        return "data_quality_hold_no_invention"
    if packet["closed_loop_boundary"]["mutation_allowed"] is False:
        return "no_closed_loop_mutation"
    return "unsafe_mutation_boundary"
