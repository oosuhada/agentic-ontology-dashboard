# Workbench Visual Baselines

## Execution contract

The checked Playwright contract is `web/e2e/workbench-governance.spec.ts`.

Each reference run uses Chromium at `1440 × 1000`, disables CSS animations, hides the caret, captures a full-page PNG and attaches it to the Playwright report. The tests also verify stable structural measurements so a screenshot is not accepted when the information architecture has collapsed.

## Stage 48 — Ontology Workbench

- Route: `/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/ontology`
- Artifact: `stage48-ontology-workbench-1440x1000`
- Required landmarks:
  - global workbench header
  - multi-store Ask panel
  - Object Set rail
  - Project 3 graph pane
  - Object Inspector
- Desktop grid baseline:
  - left rail: `255px`
  - center graph: greater than `650px` at the reference viewport
  - right inspector: `300px`
- Route acceptance:
  - direct deep link
  - reload preservation
  - browser back/forward restoration
  - unauthorized project rejection
  - mismatched project/workspace rejection

## Agent Evidence Workbench

- Route: `/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/agent`
- Artifact: `agent-evidence-workbench-1440x1000`
- Required landmarks:
  - governed query rail
  - grounded answer
  - validated claims
  - evidence source cards
  - orchestration lineage
  - persisted trace
- Interaction acceptance:
  - direct deep link with question/object prefill
  - scoped POST `/api/agent/query`
  - claim evidence ID selects and scrolls to its evidence card
  - URL `?run=` restores the persisted run after reload
  - unauthorized Project is rejected

## Stage 51 — Governance Workbench

- Route: `/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/governance`
- Artifact: `stage51-governance-workbench-1440x1000`
- Required landmarks:
  - Project governance boundary callout
  - Overview
  - Agent Runs
  - Projection Health
  - Data Lineage
  - Approvals
  - Access & Policy
- Security acceptance:
  - quality auditor receives read-only governance
  - FDE may retry a failed projection when authorized
  - process engineer cannot open the workbench
  - tenant-level account controls remain in the Admin app and are not rendered here

## Updating the baseline

A visual baseline change is accepted only when:

1. the route, scope and permission tests still pass;
2. the structural measurements still pass or this document is intentionally revised;
3. the attached PNG is reviewed for clipping, empty panels, hidden error states and density regressions;
4. any intentional information-architecture change is recorded in the Stage summary or ADR.
