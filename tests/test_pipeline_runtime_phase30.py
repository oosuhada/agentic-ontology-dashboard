import pytest

from ontology_dashboard.pipeline_runtime import PipelineEdge, PipelineNode, PipelinePlanRequest, plan_pipeline, sample_pipeline


def test_sample_pipeline_uses_pushdown_keyset_and_immutable_materialization() -> None:
    plan = plan_pipeline(sample_pipeline())
    assert plan.valid is True
    assert plan.pushdown_provider == "postgresql"
    assert "$cursor" in plan.sql_preview and "OFFSET" not in plan.sql_preview
    assert plan.materialization["output"] == "immutable Dataset Version"
    assert plan.materialization["preview_is_materialization"] is False


def test_unsafe_identifier_and_cartesian_join_are_blocked() -> None:
    unsafe = sample_pipeline().model_copy(update={"nodes": (
        PipelineNode(id="source", type="source", config={"table": "equipment; DROP TABLE users"}),
        PipelineNode(id="sink", type="sink", config={}),
    ), "edges": (PipelineEdge(source="source", target="sink"),)})
    with pytest.raises(ValueError, match="unsafe pipeline identifier"):
        plan_pipeline(unsafe)
    cartesian = PipelinePlanRequest(
        nodes=(PipelineNode(id="source", type="source", config={}), PipelineNode(id="join", type="join", config={}), PipelineNode(id="sink", type="sink", config={})),
        edges=(PipelineEdge(source="source", target="join"), PipelineEdge(source="join", target="sink")),
    )
    assert plan_pipeline(cartesian).valid is False
    assert "unsafe Cartesian join blocked" in plan_pipeline(cartesian).issues


def test_graph_contract_rejects_unknown_edges() -> None:
    with pytest.raises(ValueError, match="unknown node"):
        PipelinePlanRequest(
            nodes=(PipelineNode(id="source", type="source", config={}), PipelineNode(id="sink", type="sink", config={})),
            edges=(PipelineEdge(source="missing", target="sink"),),
        )

