# AI Workflow Plans

AI, LLM, agent review, SOP grounding, and evaluation-related implementation plans live here. Closed-loop runtime, AssetDetailViewModel, and non-AI product workflow plans remain in `docs/plans/`.

## Current Canonical Plan

- `2026-08-29-001-ai-context-orchestration-adapter-plan.md`: AI context orchestration plan covering adapter-based domain context, polling watcher materialization, ontology/SOP exploration, KG Level 0 traces, and deferred RAG/LangGraph gates.
- `2026-08-29-002-product-result-evidence-materialization-plan.md`: prerequisite product-evidence boundary plan covering Generator output validation, Product Result/Evidence materialization, lineage, checksum, and ViewModel consumption boundaries.
- `2026-08-29-003-evidence-snapshot-consistency-guard-plan.md`: sibling projection and guard plan ensuring UI ViewModel, Report, Closed-loop Recommendation Input, and Agent Review consume the same Product Result/Evidence snapshot without making ViewModel the Closed-loop input.
- `2026-08-27-001-pr130-sop-sensor-judgment-proposal.md`: Agent Review Packet, SOP judgment, scenario-based agent rationale, LLM summary, and minimum eval plan.

Use the 2026-08-29 AI context plan as the current source of truth for the next AI workflow architecture slice. Use the Product Result/Evidence materialization plan as its lower trusted-evidence prerequisite, not as an AI-only pipeline. Use the Evidence Snapshot Consistency Guard plan when discussing how UI, Report, Closed-loop, and Agent Review share one evidence basis while remaining separate projections. Use the 2026-08-27 plan as the baseline source for read-only agent review, SOP maturity gate, field inspection reference, and LLM summary sequencing.

## Removed As Duplicates

- `2026-08-24-001-feat-asset-detail-ui-agent-flow-plan.md`: folded into the current canonical PR #130 plan.
- `2026-08-27-001-sop-grounding-consumption-contract-proposal.md`: folded into the current canonical PR #130 plan.
