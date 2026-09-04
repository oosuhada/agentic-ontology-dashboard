import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { OperationalFocus } from "./OperationalFocus";
import type { OperationalFocusProps } from "./OperationalFocus";

function props(overrides: Partial<OperationalFocusProps> = {}): OperationalFocusProps {
  return {
    asset: { id: "CNC-017", name: "CNC Spindle 017", contextLabel: "Line 2 · Cell 04" },
    situation: {
      statusLabel: "고위험",
      headline: "스핀들 이상 징후가 생산 계획에 영향을 줄 수 있습니다.",
      detail: "현재 선택된 이벤트의 정본 상태와 영향만 요약합니다.",
      tone: "warning",
      risk: { label: "고장 위험", valueLabel: "84%" },
      operationalImpact: "계획 생산량 지연 가능",
    },
    evidence: [
      { id: "e-1", label: "진동 증가", value: "+18%" },
      { id: "e-2", label: "토크 편차", value: "2.4σ" },
      { id: "e-3", label: "온도 추세", value: "+7.2°C" },
    ],
    lifecycle: { currentLabel: "현장 점검 대기", nextLabel: "점검 결과 검토", ownerLabel: "Maintenance · Shift B" },
    primaryAction: { label: "현장 점검 열기" },
    freshness: { label: "2분 전", observedAt: "2026-09-02T00:35:00Z", sourceLabel: "Asset detail read model" },
    onPrimaryAction: () => undefined,
    ...overrides,
  };
}

describe("OperationalFocus", () => {
  it("renders the operational hierarchy in reading order", () => {
    const html = renderToString(<OperationalFocus {...props()} />);
    const terms = [
      "CNC Spindle 017",
      "고위험",
      "계획 생산량 지연 가능",
      "진동 증가",
      "현장 점검 대기",
      "Maintenance · Shift B",
      "현장 점검 열기",
      "2분 전",
    ];
    const positions = terms.map((term) => html.indexOf(term));

    expect(positions.every((position) => position >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it("limits evidence to four summary items", () => {
    const html = renderToString(
      <OperationalFocus
        {...props({
          evidence: [
            { id: "e-1", label: "Evidence 1" },
            { id: "e-2", label: "Evidence 2" },
            { id: "e-3", label: "Evidence 3" },
            { id: "e-4", label: "Evidence 4" },
            { id: "e-5", label: "Evidence 5" },
          ],
        })}
      />,
    );

    expect(html).toContain("Evidence 4");
    expect(html).not.toContain("Evidence 5");
  });

  it("shows normalized post-maintenance state without changing the component structure", () => {
    const html = renderToString(
      <OperationalFocus
        {...props({
          situation: {
            statusLabel: "정상 운영 중",
            headline: "정비 후 예측 완료",
            tone: "normal",
            risk: { label: "고장 위험", previousValueLabel: "84%", valueLabel: "0.2%" },
            operationalImpact: "현재 생산 영향 없음",
          },
          lifecycle: { currentLabel: "정비 효과 확인", nextLabel: "정상 모니터링", ownerLabel: "Reliability Engineering" },
          primaryAction: { label: "정비 효과 확인" },
        })}
      />,
    );

    expect(html).toContain("정비 후 예측 완료");
    expect(html).toContain("84%");
    expect(html).toContain("0.2%");
    expect(html).toContain("정상 운영 중");
    expect(html).toContain("tone-normal");
  });

  it("preserves a disabled primary action reason for read-only or server-blocked states", () => {
    const html = renderToString(
      <OperationalFocus
        {...props({
          primaryAction: {
            label: "작업 생성",
            disabled: true,
            disabledReason: "현재 preview에서는 업무 데이터 변경이 차단됩니다.",
          },
        })}
      />,
    );

    expect(html).toContain("disabled=\"\"");
    expect(html).toContain("현재 preview에서는 업무 데이터 변경이 차단됩니다.");
    expect(html).toContain("aria-describedby");
  });
});
