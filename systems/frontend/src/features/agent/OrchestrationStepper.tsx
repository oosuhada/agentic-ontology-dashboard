import { Tag } from "@blueprintjs/core";
import { Check, CircleAlert, GitMerge, Network, Route, Search, ShieldCheck } from "lucide-react";
import type { AgentRunResponse, OrchestrationStep } from "./types";

interface OrchestrationStepperProps {
  run: AgentRunResponse;
}

interface DisplayStep {
  id: string;
  label: string;
  detail: string;
  status: "succeeded" | "failed" | "skipped" | "running";
  latencyMs: number | null;
  store: string | null;
  icon: typeof Route;
}

function collectSteps(steps: OrchestrationStep[]): DisplayStep[] {
  return steps.map((step) => ({
    id: step.name,
    label: step.name.replace(/^collect_/, "Collect ").replaceAll("_", " "),
    detail: step.detail,
    status: step.status,
    latencyMs: step.latency_ms,
    store: step.store,
    icon: step.store === "neo4j" ? Network : Search,
  }));
}

function stepIntent(status: DisplayStep["status"]): "success" | "danger" | "warning" | "none" {
  if (status === "succeeded") return "success";
  if (status === "failed") return "danger";
  if (status === "running") return "warning";
  return "none";
}

export function OrchestrationStepper({ run }: OrchestrationStepperProps) {
  const state = run.state;
  const collect = collectSteps(state.steps);
  const hasEvidence = state.evidence.length > 0;
  const completed = state.status === "succeeded";
  const displaySteps: DisplayStep[] = [
    {
      id: "route",
      label: "Route request",
      detail: `${state.route} plan · scoped to ${state.project_id}/${state.workspace_id}`,
      status: "succeeded",
      latencyMs: null,
      store: null,
      icon: Route,
    },
    ...collect,
    {
      id: "merge_evidence",
      label: "Merge evidence",
      detail: `${state.evidence.length} scoped evidence items after deduplication`,
      status: hasEvidence ? "succeeded" : state.status === "failed" ? "failed" : "skipped",
      latencyMs: null,
      store: null,
      icon: GitMerge,
    },
    {
      id: "validate_claims",
      label: "Validate claims",
      detail: completed
        ? `${state.claims.length} claims reference known evidence IDs`
        : state.error ?? "Validation did not complete",
      status: completed ? "succeeded" : state.status === "failed" ? "failed" : "running",
      latencyMs: null,
      store: null,
      icon: ShieldCheck,
    },
  ];

  return (
    <ol className="agent-orchestration-stepper" aria-label="Orchestration lineage">
      {displaySteps.map((step, index) => {
        const Icon = step.icon;
        return (
          <li key={`${step.id}:${index}`} className={`status-${step.status}`}>
            <div className="agent-step-marker">
              <Icon size={14} aria-hidden />
              {index < displaySteps.length - 1 ? <span aria-hidden /> : null}
            </div>
            <div className="agent-step-copy">
              <header>
                <strong>{step.label}</strong>
                <div>
                  {step.store ? <Tag minimal>{step.store}</Tag> : null}
                  <Tag minimal intent={stepIntent(step.status)}>
                    {step.status === "succeeded" ? <Check size={10} /> : step.status === "failed" ? <CircleAlert size={10} /> : null}
                    {step.status}
                  </Tag>
                </div>
              </header>
              <p>{step.detail}</p>
              {step.latencyMs !== null ? <small>{step.latencyMs} ms</small> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
