import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ContextAssistantDrawer } from "./ContextAssistantDrawer";
import {
  deterministicReliabilityAssistantAnswer,
  groundedReliabilityAssistantAnswer,
  reliabilityAssistantClarificationCandidates,
  reliabilityAssistantPrompts,
  reliabilityAssistantResponseBlocks,
  type ReliabilityAssistantContext,
} from "./assistantContext";

const selectedContext: ReliabilityAssistantContext = {
  assetId: "CNC-03",
  assetName: "CNC-03 spindle",
  eventId: "event-84",
  failureProbability: 0.84,
  estimatedDowntimeMinutes: 120,
  estimatedLostUnits: 25,
  productVariant: "HX-M",
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

  it("keeps workspace-scope questions available without an asset selection", async () => {
    await renderDrawer({
      context: {
        roleKind: "operations",
        workspaceName: "Smart Factory A",
        workspaceMetrics: {
          totalAssets: 80,
          normal: 72,
          attention: 4,
          warning: 3,
          critical: 1,
          dataQualityHold: 2,
          averageRisk: 0.12,
          estimatedDowntimeMinutes: 180,
          pendingDecisions: 5,
        },
      },
    });
    expect(container.textContent).toContain("Smart Factory A");
    expect(container.textContent).toContain("전체 80대");
    expect(container.textContent).toContain("지금 판단 대기 중인 항목은 무엇인가요?");
    expect(container.textContent).toContain("생산 영향이 큰 Case부터 요약해줘");
    expect(container.querySelector("textarea")?.hasAttribute("disabled")).toBe(false);
    expect(container.querySelector(".rw-context-assistant__prompts")).not.toBeNull();
  });

  it("changes engineering prompts when the selected asset is normal and monitoring-only", () => {
    const prompts = reliabilityAssistantPrompts({
      ...selectedContext,
      roleKind: "engineering",
      statusCode: "normal",
      statusLabel: "정상",
      failureProbability: 0.03,
      recommendedDecisionCode: "continue_monitoring",
      recommendedDecisionLabel: "계속 모니터링",
    });
    expect(prompts.map((prompt) => prompt.label)).toEqual([
      "왜 이 설비는 점검보다 모니터링이 우선인가요?",
      "현재 정상 판단을 뒷받침하는 신호는 무엇인가요?",
      "어떤 변화가 생기면 점검이 필요해지나요?",
      "불필요한 정비를 피하는 것이 어떤 운영 가치를 보호하나요?",
    ]);
    expect(prompts.some((prompt) => prompt.label.includes("이상으로 판단"))).toBe(false);
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
    expect(container.textContent).toContain("현장 행동과 회사 가치가 연결되도록 설명합니다");
    expect(container.textContent).not.toContain("Agent Review Packet");
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
    expect(groundedReliabilityAssistantAnswer(selectedContext, "왜 이 설비가 우선인가?")).toContain("진동 RMS 6.2 mm/s");
    expect(groundedReliabilityAssistantAnswer(selectedContext, "현재 핵심 근거 요약")).toContain("진동 RMS 6.2 mm/s");
    expect(groundedReliabilityAssistantAnswer(selectedContext, "현재 핵심 근거 요약")).toContain("검증된 SOP 안내 2건");
    expect(groundedReliabilityAssistantAnswer(selectedContext, "현재 핵심 근거 요약")).not.toContain("local_sop_metadata_retriever");
  });

  it("corrects a false abnormal premise and keeps internal model fields out of the answer", () => {
    const answer = groundedReliabilityAssistantAnswer({
      ...selectedContext,
      assetId: "CNC-S01-L02-03",
      assetName: "1구역 · 2셀 · CNC 가공기 3",
      failureProbability: 0.08,
      statusLabel: "정상",
      recommendedDecisionLabel: "계속 모니터링",
      estimatedDowntimeMinutes: 60,
      priorityReasons: [
        "status normal",
        "generator failure score 0.0106629027662835 model unit",
        "model selected threshold 0.06999999999999999 model unit",
        "asset criticality adjustment 0.0 model unit",
      ],
      evidenceItems: ["모델 산출 위험 점수 0.011", "위험 판정 기준값 0.07"],
    }, "왜 이 설비가 이상으로 판단됐나요?");

    expect(answer).toContain("고장이나 이상으로 확정된 상태가 아닙니다");
    expect(answer).toContain("위험도는 8%");
    expect(answer).toContain("추세를 계속 관찰하는 것이 적절합니다");
    expect(answer).toContain("최대 60분의 잠재 비가동");
    expect(answer).not.toContain("generator failure score");
    expect(answer).not.toContain("model selected threshold");
    expect(answer).not.toContain("모델 산출 위험 점수");
    expect(answer).not.toContain("위험 판정 기준값");
    expect(answer).not.toContain("0.0106629027662835");
  });

  it("frames cost and KPI questions as value protection without claiming booked savings", () => {
    const answer = groundedReliabilityAssistantAnswer(
      selectedContext,
      "이 조치의 비용 절감과 KPI 가치는?",
    );
    expect(answer).toContain("생산 연속성을 보호");
    expect(answer).toContain("최대 120분의 잠재 비가동");
    expect(answer).toContain("계획 생산 약 25개의 손실 가능성");
    expect(answer).toContain("실제 절감액이 아니라 보호 대상 노출");
    expect(answer).not.toContain("비용을 절감했습니다");
  });

  it("builds deterministic response blocks from validated case and workspace context", () => {
    const caseBlocks = reliabilityAssistantResponseBlocks(
      selectedContext,
      "왜 이 설비가 우선이고 생산 영향은 무엇인가요?",
    );
    expect(caseBlocks.map((block) => block.type)).toContain("metric_strip");
    expect(caseBlocks.map((block) => block.type)).toContain("evidence_list");
    const metricBlock = caseBlocks.find((block) => block.type === "metric_strip");
    expect(metricBlock?.type === "metric_strip" ? metricBlock.metrics.map((metric) => metric.value) : []).toEqual(
      expect.arrayContaining(["84%", "2시간", "25", "1"]),
    );

    const workspaceBlocks = reliabilityAssistantResponseBlocks({
      workspaceMetrics: {
        totalAssets: 12,
        normal: 8,
        attention: 1,
        warning: 2,
        critical: 1,
        dataQualityHold: 0,
        averageRisk: 0.28,
        estimatedDowntimeMinutes: 180,
        pendingDecisions: 3,
      },
      workspaceTopRisks: [
        { assetLabel: "CNC-01", risk: 0.91, status: "critical" },
        { assetLabel: "CNC-02", risk: 0.72, status: "warning" },
      ],
    }, "위험도가 높은 설비부터 보여줘");
    expect(workspaceBlocks.map((block) => block.type)).toEqual(["metric_strip", "ranked_risk"]);
  });

  it("asks for an asset choice only when a singular workspace question is ambiguous", () => {
    const context: ReliabilityAssistantContext = {
      workspaceAssets: [
        { assetId: "CNC-S04-L04-01", assetLabel: "4구역 · 4셀 · CNC 가공기 1", eventId: "e-1", risk: 0.82, status: "warning" },
        { assetId: "CNC-S04-L04-02", assetLabel: "4구역 · 4셀 · CNC 가공기 2", eventId: "e-2", risk: 0.61, status: "warning" },
        { assetId: "COMP-01", assetLabel: "압축기 1", eventId: "e-3", risk: 0.2, status: "normal" },
      ],
    };
    expect(reliabilityAssistantClarificationCandidates(context, "4구역 CNC 상태 보여줘").map((item) => item.assetId)).toEqual([
      "CNC-S04-L04-01",
      "CNC-S04-L04-02",
    ]);
    expect(reliabilityAssistantClarificationCandidates(context, "CNC 중에서 위험도가 가장 높은 설비는?")).toEqual([]);
    expect(reliabilityAssistantClarificationCandidates(context, "CNC-S04-L04-01 상태 보여줘")).toEqual([]);
  });

  it("renders structured answer blocks and clarification candidates without exposing raw query UI", async () => {
    await renderDrawer({
      context: {
        ...selectedContext,
        surfaceLabel: "생산 영향",
        surfaceDetail: "수량 · 비용 · 제품 영향",
      },
      messages: [{
        id: "assistant-structured",
        role: "assistant",
        text: "현재 Case의 노출 지표를 기준으로 우선순위를 설명합니다.",
        blocks: reliabilityAssistantResponseBlocks(selectedContext, "생산 영향과 위험도를 요약해줘"),
      }],
      clarification: {
        question: "CNC 상태 보여줘",
        candidates: [
          { assetId: "CNC-01", assetLabel: "CNC 가공기 1", eventId: "e-1", risk: 0.8, status: "warning" },
          { assetId: "CNC-02", assetLabel: "CNC 가공기 2", eventId: "e-2", risk: 0.6, status: "warning" },
        ],
      },
    });
    expect(container.textContent).toContain("현재 화면생산 영향수량 · 비용 · 제품 영향");
    expect(container.textContent).toContain("선택 Case 핵심 지표");
    expect(container.textContent).toContain("대상 확인");
    expect(container.textContent).toContain("CNC 가공기 1");
    expect(container.textContent).toContain("전체 범위로 계속");
    expect(container.textContent).not.toContain("Generated SQL");
    expect(container.textContent).not.toContain("Cypher");
  });
});
