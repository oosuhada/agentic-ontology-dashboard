# AI4I Product Data Gap Analysis

## Purpose

AI4I is useful for a reproducible machine-failure benchmark, but it is not a complete manufacturing operations dataset. This document separates what is observed, what is derived, and what is synthetic so that reports do not present invented operational context as measured fact.

## Gap matrix

| Product need | AI4I coverage | MVP treatment | Truth label |
|---|---|---|---|
| Equipment identity | only row/product ID | synthetic equipment master | synthetic |
| Sensor snapshot | six operating fields | use original-compatible fields | observed |
| Sensor history | independent rows, no equipment time series | short deterministic history per Gold fixture | synthetic |
| Machine failure target | available | train/evaluate binary model | observed label |
| Failure mode | five mode labels | post-hoc evaluation and fixture hypothesis | observed label / predicted hypothesis |
| Plant line and process | absent | fixture metadata | synthetic |
| Equipment criticality | absent | low/medium/high fixture field | synthetic |
| Assigned engineer | absent | fixture metadata | synthetic |
| Last maintenance | absent | fixture metadata | synthetic |
| Spare-parts inventory | absent | maintenance context fixture | synthetic |
| Production impact | absent | transparent rule from criticality and downtime assumptions | estimated |
| Work order/approval | absent | local SQLite demo record | user-entered demo state |
| Maintenance manual | absent | local cited context fixture; Project 3 adapter later | synthetic reference |
| Root cause confirmation | absent | never claim confirmation; show prediction/hypothesis only | unavailable |
| Real-time streaming | absent | replay short fixture windows | synthetic simulation |

## Product constraints caused by the gaps

1. **No temporal causality claim.** The benchmark observations are independent. Fixture histories support UI demonstration, not time-series model validation.
2. **No confirmed root cause.** Failure-mode output is a model hypothesis or post-hoc label, never a field inspection result.
3. **No real financial ROI claim.** Impact values are estimates with visible assumptions.
4. **No automatic work execution.** Decisions and notes are local demo records only.
5. **No customer generalization claim.** Performance on AI4I does not establish deployment performance on a real factory.
6. **No use of mode labels as features.** Doing so would leak target-generation information.

## Synthetic metadata policy

Synthetic values must be stored in fixture files or context providers and carry one of these source types:

- `observed`: direct AI4I-compatible sensor value
- `derived`: deterministic calculation from observed fields
- `predicted`: model output
- `estimated`: transparent operational rule
- `synthetic`: product-demo metadata
- `user_entered`: local decision, note, or checklist update

Reports may combine these values but must preserve source type and avoid wording that upgrades an estimate or hypothesis into a fact.

## Transition to Project 3

The fixture maintenance context is behind `MaintenanceContextProvider`. A later Project 3 provider may replace it with graph/document evidence for equipment-part relationships, maintenance history, manuals, and similar cases. The Evidence, Report, and UI contracts must not change when the provider changes.
