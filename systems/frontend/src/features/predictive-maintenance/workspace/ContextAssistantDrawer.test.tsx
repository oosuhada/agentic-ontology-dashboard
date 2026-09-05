import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ContextAssistantDrawer } from "./ContextAssistantDrawer";
import {
  deterministicReliabilityAssistantAnswer,
  groundedReliabilityAssistantAnswer,
  reliabilityAssistantPrompts,
  type ReliabilityAssistantContext,
} from "./assistantContext";

const selectedContext: ReliabilityAssistantContext = {
  assetId: "CNC-03",
  assetName: "CNC-03 spindle",
  eventId: "event-84",
  failureProbability: 0.84,
  currentLifecycleLabel: "점검 완료",
  nextLifecycleLabel: "정비안 검토",
  primaryActionLabel: "정비안 검토",
  evidenceCount: 3,
  evidenceSummary: "진동 상승과 온도 편차 근거가 연결되어 있습니다.",
  workOrderCount: 1,
  maintenanceState: "검토 대기",
  observedAt: "2026-09-02T09:00:00+09:00",
  priorityReasons: ["진동 기여도가 가장 큼", "점검 요청 대기"],
  evidenceItems: ["진동 RMS 6.2 mm/s", "온도 78 C"],
  historyItems: ["24시간 내 유사 이벤트 2건"],
  aiSummary: "현재 진동 상승과 온도 편차를 함께 검토해야 합니다.",
  aiSummaryMode: "llm",
  aiProvider: "openai-compatible",
  retrievalProvider: "local_sop_metadata_retriever",
  retrievalCount: 2,
};

let container: HTMLDivElement;
let root: Root;

async function renderDrawer(props: Partial<React.ComponentProps<typeof ContextAssistantDrawer>> = {}) {
  await act(async () => {
    root.render(
      <ContextAssistantDrawer
        open
        onClose={() => undefined}
        context={selectedContext}
        onSubmit={() => undefined}
        {...props}
      />,
    );
  });
}

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
    .IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("ContextAssistantDrawer", () => {
  it("renders nothing in the closed state", async () => {
    await renderDrawer({ open: false });
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(container.textContent).toBe("");
  });

  it("renders selected asset operational context without inventing lifecycle state", async () => {
    await renderDrawer();
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    expect(container.textContent).toContain("CNC-03 spindle");
    expect(container.textContent).toContain("위험도84%");
    expect(container.textContent).toContain("현재 단계점검 완료");
    expect(container.textContent).toContain("다음 단계정비안 검토");
    expect(container.textContent).toContain("다음 행동정비안 검토");
    expect(container.textContent).toContain("근거3");
  });

  it("shows a no-selection context and disables free-form submission", async () => {
    await renderDrawer({ context: null });
    expect(container.textContent).toContain("선택 없음");
    expect(container.textContent).toContain("설비나 이벤트를 선택");
    expect(container.querySelector("textarea")?.hasAttribute("disabled")).toBe(true);
    expect(container.querySelector(".rw-context-assistant__prompts")).toBeNull();
  });

  it("only exposes suggested prompts backed by available context", () => {
    const prompts = reliabilityAssistantPrompts({
      assetId: "CNC-03",
      failureProbability: 0.84,
      currentLifecycleLabel: "점검 완료",
      evidenceCount: 2,
    });
    expect(prompts.map((prompt) => prompt.id)).toEqual(["priority", "evidence", "lifecycle"]);
    expect(prompts.map((prompt) => prompt.id)).not.toContain("next-action");
    expect(prompts.map((prompt) => prompt.id)).not.toContain("work-history");
    expect(prompts.map((prompt) => prompt.id)).not.toContain("post-maintenance");

    const postMaintenancePrompts = reliabilityAssistantPrompts({
      assetId: "CNC-03",
      postMaintenanceSummary: "정비 후 위험도 변화가 연결됨",
    });
    expect(postMaintenancePrompts.map((prompt) => prompt.id)).toEqual(["post-maintenance"]);
  });

  it("closes from the close button and Escape key", async () => {
    const onClose = vi.fn();
    await renderDrawer({ onClose });
    const closeButton = container.querySelector<HTMLButtonElement>('[aria-label="Reliability Assistant 닫기"]');
    expect(closeButton).not.toBeNull();
    await act(async () => closeButton?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onClose).toHaveBeenCalledTimes(1);

    await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("renders an explicit empty-message state", async () => {
    await renderDrawer({ messages: [] });
    expect(container.textContent).toContain("아직 질문 없음");
    expect(container.textContent).toContain("Agent Review Packet");
  });

  it("renders safe execution activity without exposing private chain-of-thought", async () => {
    await renderDrawer({
      messages: [
        {
          id: "assistant-run-1",
          role: "assistant",
          text: "연결 근거를 기준으로 정비 이력과 SOP를 함께 확인했습니다.",
          contextHint: "연결 근거 · 4건",
          activityTrace: {
            runId: "run-1",
            route: "hybrid",
            status: "succeeded",
            evidenceCount: 4,
            claimCount: 2,
            checkpointSequence: 3,
            durationMs: 128,
            steps: [
              {
                id: "step-1",
                label: "RAG 문서 검색",
                detail: "승인된 문서와 정비 이력을 검색했습니다.",
                store: "pgvector",
                status: "succeeded",
                latencyMs: 82,
              },
            ],
          },
        },
      ],
    });
    expect(container.textContent).toContain("작업 기록");
    expect(container.textContent).toContain("RAG 문서 검색");
    expect(container.textContent).toContain("pgvector");
    expect(container.textContent).toContain("근거 4건 · 검증 주장 2건");
    expect(container.textContent).toContain("모델 내부 사고 과정은 포함하지 않습니다");
    expect(container.textContent).not.toContain("chain-of-thought content");
  });

  it("shows grounded live sources and cannot execute or approve work", async () => {
    await renderDrawer();
    expect(container.textContent).toContain("LLM 근거 요약");
    expect(container.textContent).toContain("검증된 SOP 안내 · 2");
    expect(container.textContent).not.toContain("local_sop_metadata_retriever");
    expect(container.textContent).toContain("업무를 승인·실행하거나 workflow 상태를 변경하지 않습니다");
    expect(deterministicReliabilityAssistantAnswer(selectedContext)).toContain("규칙 기반");
    expect(deterministicReliabilityAssistantAnswer(selectedContext)).toContain("승인이나 실행 판단이 아닙니다");
  });

  it("builds prompt labels from the selected live context", () => {
    const prompts = reliabilityAssistantPrompts(selectedContext);
    expect(prompts.find((prompt) => prompt.id === "priority")?.label).toContain("CNC-03 spindle (84%)");
    expect(prompts.find((prompt) => prompt.id === "evidence")?.label).toContain("3건");
    expect(prompts.find((prompt) => prompt.id === "lifecycle")?.label).toContain("점검 완료");
    expect(prompts.find((prompt) => prompt.id === "next-action")?.label).toContain("정비안 검토");
  });

  it("answers priority and evidence questions from Agent Review grounding", () => {
    expect(groundedReliabilityAssistantAnswer(selectedContext, "왜 이 설비가 우선인가?")).toContain("진동 기여도가 가장 큼");
    expect(groundedReliabilityAssistantAnswer(selectedContext, "현재 핵심 근거 요약")).toContain("진동 RMS 6.2 mm/s");
    expect(groundedReliabilityAssistantAnswer(selectedContext, "현재 핵심 근거 요약")).toContain("검증된 SOP 안내 2건");
    expect(groundedReliabilityAssistantAnswer(selectedContext, "현재 핵심 근거 요약")).not.toContain("local_sop_metadata_retriever");
  });
});
