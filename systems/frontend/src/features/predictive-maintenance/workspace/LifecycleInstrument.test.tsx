import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ActivityTimeline } from "./ActivityTimeline";
import { LifecycleInstrument } from "./LifecycleInstrument";

describe("LifecycleInstrument", () => {
  it("prioritizes the current and next lifecycle steps in the compact instrument", () => {
    const html = renderToString(
      <LifecycleInstrument
        completedSteps={[{ id: "evidence", label: "근거 확인" }]}
        current={{ id: "decision", label: "운영 판단" }}
        next={{ id: "inspection", label: "현장 점검" }}
      />,
    );

    expect(html).toContain("이전 완료 단계");
    expect(html).toContain("근거 확인");
    expect(html).toContain("현재 단계");
    expect(html).toContain("운영 판단");
    expect(html).toContain("다음 단계");
    expect(html).toContain("현장 점검");
    expect(html).not.toContain("활동 이력");
  });

  it("shows every completed presentation step only when expanded", () => {
    const html = renderToString(
      <LifecycleInstrument
        completedSteps={[
          { id: "prediction", label: "예측 생성" },
          { id: "evidence", label: "근거 검토" },
        ]}
        current={{ id: "decision", label: "운영 판단" }}
        next={{ id: "inspection", label: "현장 점검" }}
        expanded
      />,
    );

    expect(html).toContain("이전 완료 · 2단계");
    expect(html).toContain("예측 생성");
    expect(html).toContain("근거 검토");
    expect(html).toContain("Lifecycle 요약");
  });

  it("renders an explicit terminal state when there is no next step", () => {
    const html = renderToString(
      <LifecycleInstrument
        completedSteps={[{ id: "maintenance", label: "정비 완료" }]}
        current={{ id: "normal", label: "정상 운영" }}
        next={null}
      />,
    );

    expect(html).toContain("정상 운영");
    expect(html).toContain("다음 단계 없음");
  });
});

describe("ActivityTimeline", () => {
  it("uses visible icon-and-text semantics for blocked and failed activity", () => {
    const html = renderToString(
      <ActivityTimeline
        items={[
          { id: "blocked", label: "정비 승인 대기", status: "blocked", actor: "운영 관리자" },
          { id: "failed", label: "재예측 실패", status: "failed", occurredAt: "2026-09-02T00:30:00Z" },
        ]}
      />,
    );

    expect(html).toContain('data-status="blocked"');
    expect(html).toContain("차단됨");
    expect(html).toContain("정비 승인 대기");
    expect(html).toContain('data-status="failed"');
    expect(html).toContain("실패");
    expect(html).toContain("재예측 실패");
  });

  it("renders a useful empty timeline state", () => {
    const html = renderToString(<ActivityTimeline items={[]} />);
    expect(html).toContain("아직 기록된 활동이 없습니다.");
  });
});
