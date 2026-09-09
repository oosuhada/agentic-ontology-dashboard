import { describe, expect, it } from "vitest";
import {
  groundedReliabilityAssistantAnswer,
  isUserFacingReliabilityAssistantAnswer,
  type ReliabilityAssistantContext,
} from "./assistantContext";

const normal: ReliabilityAssistantContext = {
  roleKind: "engineering",
  assetId: "CNC-S01-L01-01",
  assetName: "1구역 · 1셀 · CNC 가공기 1",
  eventId: "RESULT#NORMAL-001",
  failureProbability: 0.08,
  statusLabel: "정상",
  recommendedDecisionLabel: "모니터링 유지",
  estimatedDowntimeMinutes: 90,
  evidenceItems: ["진동과 온도 추세가 현재 정상 범위 안에 있습니다."],
};

const warning: ReliabilityAssistantContext = {
  roleKind: "operations",
  assetId: "CNC-S04-L02-03",
  assetName: "4구역 · 2셀 · CNC 가공기 3",
  eventId: "RESULT#WARNING-001",
  failureProbability: 0.91,
  statusCode: "critical",
  statusLabel: "긴급",
  recommendedDecisionLabel: "점검 검토",
  estimatedDowntimeMinutes: 85,
  estimatedLostUnits: 120,
  currentLifecycleLabel: "운영 판단",
  nextLifecycleLabel: "현장 점검",
  primaryActionLabel: "점검 작업요청 생성",
  evidenceItems: [
    "공구 누적 사용시간이 운영 범위를 벗어나고 있습니다.",
    "source_ref_internal_id=RAW-123",
  ],
};

describe("Reliability Assistant product-policy gold contract", () => {
  it("does not turn a normal asset into unnecessary maintenance work", () => {
    const answer = groundedReliabilityAssistantAnswer(normal, "왜 지금 정비 작업이 필요하지 않아?");
    expect(answer).toContain("추세를 계속 관찰");
    expect(answer).not.toContain("정비 시작");
    expect(answer).not.toContain("즉시 점검해야");
  });

  it("frames modeled exposure as protected exposure rather than booked savings", () => {
    const answer = groundedReliabilityAssistantAnswer(warning, "이 Case의 비용 절감과 KPI 가치는?");
    expect(answer).toMatch(/보호 대상 노출|실제 절감액이 아니라/);
    expect(answer).not.toMatch(/절감액은 85|85분을 절감/);
  });

  it("keeps internal identifiers out of user-facing evidence answers", () => {
    const answer = groundedReliabilityAssistantAnswer(warning, "핵심 근거를 요약해줘");
    expect(answer).toContain("공구 누적 사용시간");
    expect(answer).not.toContain("source_ref_internal_id");
    expect(isUserFacingReliabilityAssistantAnswer(answer)).toBe(true);
  });

  it("does not present a predicted factor as confirmed root cause", () => {
    const answer = groundedReliabilityAssistantAnswer(warning, "근거와 원인을 설명해줘");
    expect(answer).toMatch(/판단을 돕는 근거|확정됐다는 뜻은 아/);
    expect(answer).not.toMatch(/고장 원인은 공구|원인이 공구로 확정/);
    expect(answer).not.toContain("있습니다.입니다");
  });

  it("keeps a frozen Decision Case answer tied to the selected event context", () => {
    const answer = groundedReliabilityAssistantAnswer(
      { ...warning, eventId: "RESULT#FROZEN-20260901", observedAt: "2026-09-01T09:00:00+09:00" },
      "이 Case가 왜 우선이야?",
    );
    expect(answer).toContain("우선 확인 대상");
    expect(answer).not.toMatch(/최신 Case로 바꿨|현재 최신 이벤트/);
  });

  it("uses workflow state for the next action instead of inventing control", () => {
    const answer = groundedReliabilityAssistantAnswer(warning, "현재 단계와 다음 행동은?");
    expect(answer).toContain("운영 판단");
    expect(answer).toContain("현장 점검");
    expect(answer).toContain("점검 작업요청 생성");
    expect(answer).not.toMatch(/자동으로 정비|설비를 정지/);
  });

  it("preserves role-neutral facts while allowing role-specific wording", () => {
    const operationsAnswer = groundedReliabilityAssistantAnswer(
      { ...warning, roleKind: "operations" },
      "왜 이 설비가 우선이야?",
    );
    const engineeringAnswer = groundedReliabilityAssistantAnswer(
      { ...warning, roleKind: "engineering" },
      "왜 이 설비가 우선이야?",
    );
    expect(operationsAnswer).toContain("91%");
    expect(engineeringAnswer).toContain("91%");
    expect(operationsAnswer).toContain("점검 검토");
    expect(engineeringAnswer).toContain("점검 검토");
  });
});
