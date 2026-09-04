# LLM Report Trial Preflight Decision

## Decision

`INSUFFICIENT_LIVE_EVIDENCE`

This is a normal negative exit from the U0A preflight. It is not a rejection of
all future LLM use and it is not approval for production routing.

This note preserves the document-only conclusion from the superseded local
`feat/llm-necessity-preflight` branch. The evaluator code from that branch is
not carried into the current runtime closed-loop plan branch.

## Reproducible baseline

- Gold fixture baseline ref: `2eaeb06`
- Original evaluator branch commit: `3aa2207`
- Policy: `llm-report-trial-preflight-v1`
- Dataset mode: Gold fixture only
- Independent samples: 8 events / 7 assets
- Repeats: 3 per event-role pair
- Role evaluations: 48 Reports and 48 Layouts
- Runtime integration: `not_run`
- Domain user validation: `not_evaluated`

Original branch command:

```bash
APP_ENV=test PYTHONPATH=systems/backend \
  python3 scripts/evaluate_llm_preflight.py --repeats 3
```

## Measured result

| Measure | Numerator / denominator | Execution mode | Result |
|---|---:|---|---:|
| Simple Gold cases | 7 / 8 independent events | deterministic complexity policy | 87.5% |
| Complex Gold cases | 0 / 8 independent events | deterministic complexity policy | 0% |
| Not-eligible Gold cases | 1 / 8 independent events | deterministic complexity policy | 12.5% |
| Live Report successes | 0 / 0 live attempts | live provider not configured | not evaluated |
| Safe Report fallbacks | 48 / 48 role evaluations | deterministic fallback | 100% |
| Safe Layout fallbacks | 48 / 48 role evaluations | deterministic fallback | 100% |

The fixture inputs contain 3-4 history rows, 0-5 top factors, zero free-text
maintenance notes, and one distinct SOP source per event. Under the committed
engineering policy, this does not create a complex fixture cohort.

The preflight itself refuses to contact a configured live provider. A live run
requires a separate authorized evaluator with data-handling approval and a
predeclared call, latency, and cost budget.

## Claim boundary

- The 48/48 results prove fallback contract behavior, not live LLM quality.
- `runtime.llm_available=true` is a fixture flag, not provider success evidence.
- Zero complex Gold cases does not prove that real PostgreSQL Runtime events are
  simple because Runtime samples were not executed in this run.
- Team review and future LLM Judge output cannot establish maintenance accuracy,
  user time savings, downtime reduction, or cost reduction.
- This document is not implementation evidence for the current branch because
  the evaluator code was intentionally not carried forward.

## Next gate

Do not start a live provider comparison until all of the following exist:

1. Canonical PostgreSQL Artifact-to-Evidence samples are available and classified.
2. At least the policy minimum number of independent complex events exists.
3. Provider endpoint, retention, region, and credential handling are approved.
4. The live call, latency, and cost budgets are committed before execution.
5. Template and LLM outputs can be checked against the same Evidence snapshot.

If verified Runtime data still contains no complex cohort, record
`INSUFFICIENT_COMPLEX_CASES` and keep the deterministic report.
